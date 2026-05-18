"""Tiny HTTP server for AirDrop-style file transfer over WiFi.

The badge advertises itself over BLE (so the phone sees it in Nearby /
the Oreo Pair flow), but the actual file bytes flow over WiFi because
the BLE GATT path is too slow and there's no Classic-BT OBEX on this
firmware. When WiFi is up, this module:

  GET  /          serves a one-page upload form (HTML in-line below)
  POST /upload    parses one multipart file part, writes it to flash,
                  routes by extension:
                       .png .jpg .jpeg .gif  -> apps/gallery/assets/raw/
                       .md                   -> documents/
                       .txt                  -> documents/
                       (anything else)        -> rejected with 415
  GET  /favicon.ico  204 (silences browser noise)

Design notes
------------
* Single-threaded, non-blocking. `tick()` is called from the OS run
  loop; we only ever process one HTTP request per tick. A long upload
  freezes the UI for the duration — acceptable for v1 because the
  phone-side share takes a couple of seconds for typical photos.
* Multipart parsing is streamed: we never hold the full payload in
  RAM. Chunks land directly into the on-disk file as they arrive,
  with a sliding-window check for the closing boundary marker.
* No HTTPS. The transfer happens on the local LAN; adding TLS would
  pull in ~30 KB of code and zero security benefit for a peer who
  could already sniff the broadcast.

Public surface:
    http_server.start(os_obj)   open listening socket on WiFi IP
    http_server.tick()          accept + handle a pending request
    http_server.stop()          close listening socket
    http_server.url()           "http://192.168.x.y/" — show on screen
"""

import gc

try:
    import socket as _socket
except ImportError:
    _socket = None

try:
    import os as _os
except ImportError:
    _os = None


PORT          = 80
MAX_BODY      = 2 * 1024 * 1024   # 2 MB hard cap — bigger than any badge asset
READ_CHUNK    = 2048
RECV_TIMEOUT       = 3            # seconds — per-recv() during streaming
HEAD_DEADLINE_MS   = 1500         # hard cap on header-read for tiny requests
                                  # (beacons / session/new). Anything slower
                                  # than this is almost certainly a TLS probe
                                  # or a stuck client and would otherwise
                                  # freeze the run loop one beacon at a time.

# Session lifecycle
SESSION_TTL_MS         = 60 * 1000   # beacon must refresh within this
SESSION_MAX            = 8           # never track more than this many concurrent
SESSION_CHARSET        = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I/l

_lsock     = None
_bound_ip  = None

# Token state machine. Each sender registers itself by hitting /beacon
# with a 6-char id. The badge UI lists them as pending, and the user
# explicitly approves (or denies) before any /upload bytes are accepted.
#
#   _sessions[id] = {
#       "state":     "pending" | "approved" | "denied",
#       "last_ms":   ticks_ms of last beacon hit,
#       "addr":      requesting peer ip (for display),
#       "uploads":   completed upload count for this session,
#   }
_sessions = {}

# Live upload progress so the WiFi app can render a real-time bar while
# bytes are flowing in. None when no upload is in flight.
#   {"id": "...", "filename": "...", "received": int, "total": int}
_progress = None



# ── routing tables ──────────────────────────────────────────────────────

_GALLERY_DIR  = "apps/gallery/assets/optimized"   # was /raw — Gallery
                                                  # only reads optimized/
                                                  # at runtime, so raw
                                                  # uploads were invisible
                                                  # until a laptop deploy
                                                  # re-ran the optimiser.
                                                  # We now upload pre-
                                                  # converted .r565 binaries
                                                  # straight into here.
_DOCS_DIR     = "documents"

# .r565 is our on-device-renderable image format: 6-byte header
# (magic 'R5' + width LE16 + height LE16), then W*H 2-byte RGB565
# pixels. The browser does the conversion before upload — see the
# canvas pipeline in _UPLOAD_FORM below.
_IMG_EXTS = (".r565",)
_DOC_EXTS = (".md", ".txt")


def _ensure_dir(path):
    """mkdir -p — tolerates intermediate dirs already existing."""
    if _os is None:
        return
    parts = path.split("/")
    cur = ""
    for p in parts:
        if not p:
            continue
        cur = (cur + "/" + p) if cur else p
        try:
            _os.mkdir(cur)
        except OSError:
            pass


def _route_for(filename):
    """Pick the on-disk directory + accept policy for an upload. Returns
    (dest_dir, kind_label) on accept, or (None, reason_string) on reject."""
    if not filename:
        return None, "no filename"
    fl = filename.lower()
    for ext in _IMG_EXTS:
        if fl.endswith(ext):
            return _GALLERY_DIR, "image"
    for ext in _DOC_EXTS:
        if fl.endswith(ext):
            return _DOCS_DIR, "document"
    return None, "unsupported type"


def _safe_filename(raw):
    """Strip path separators + non-printable chars. Phones occasionally
    POST filenames with directory parts; we ignore them so an upload
    can never escape the target dir."""
    if not raw:
        return ""
    name = raw.replace("\\", "/").rsplit("/", 1)[-1]
    out  = []
    for ch in name:
        c = ord(ch)
        # printable ASCII except path separators (already handled) and
        # null. Anything weirder gets dropped so the FS doesn't choke.
        if 32 <= c < 127 and ch not in "/\\?*:|\"<>":
            out.append(ch)
    return "".join(out)[:64] or "upload"


# ── server lifecycle ────────────────────────────────────────────────────

def start(os_obj=None):
    """Open the listening socket on the current WiFi IP. Safe to call
    multiple times — re-binds if WiFi reconnected to a different IP."""
    global _lsock, _bound_ip
    if _socket is None:
        return False
    # Resolve current WiFi IP via the wifi module.
    try:
        from oreoWare import wifi
        ip = wifi.ip()
    except Exception:
        ip = None
    if not ip:
        return False
    # If we're already bound on this IP, nothing to do.
    if _lsock is not None and _bound_ip == ip:
        return True
    stop()
    try:
        s = _socket.socket()
        # SO_REUSEADDR so a fast WiFi flap doesn't leave us in TIME_WAIT
        # waiting to bind. MicroPython doesn't always expose SOL_SOCKET
        # constants, so wrap the setsockopt in its own try.
        try:
            s.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
        except Exception:
            pass
        addr = _socket.getaddrinfo(ip, PORT)[0][-1]
        s.bind(addr)
        s.listen(2)
        s.setblocking(False)
        _lsock = s
        _bound_ip = ip
        try:
            print("[http] listening on %s:%d" % (ip, PORT))
        except Exception:
            pass
        return True
    except Exception as e:
        try:
            print("[http] bind failed: %s" % e)
        except Exception:
            pass
        _lsock = None
        _bound_ip = None
        return False


def stop():
    global _lsock, _bound_ip
    if _lsock is not None:
        try:
            _lsock.close()
        except Exception:
            pass
    _lsock = None
    _bound_ip = None


def url():
    """The address users should type on their phone. Prefers the
    mDNS hostname (oreo.local) over the raw IP because it survives
    DHCP-lease rotation and reads better off a tiny screen."""
    if _bound_ip is None:
        return ""
    return "http://oreo.local/"


def url_fallback():
    """Raw-IP version, shown beneath the mDNS URL for users on networks
    where multicast DNS doesn't work (some corporate WiFi)."""
    if _bound_ip is None:
        return ""
    return "http://%s/" % _bound_ip


def is_running():
    return _lsock is not None


# ── session state queries (UI hooks) ────────────────────────────────────

def _prune_sessions():
    """Drop sessions that haven't beaconed in SESSION_TTL_MS. Called
    cheaply on every query so the UI never shows ghosts."""
    try:
        import time as _t
        now = _t.ticks_ms()
    except Exception:
        return
    stale = []
    for sid, s in _sessions.items():
        last = s.get("last_ms", 0)
        try:
            if _t.ticks_diff(now, last) > SESSION_TTL_MS:
                stale.append(sid)
        except Exception:
            pass
    for sid in stale:
        _sessions.pop(sid, None)


def list_sessions():
    """Snapshot for the WiFi/Transfer UI. Returns sessions sorted by
    last-seen so the newest beacons are on top."""
    _prune_sessions()
    items = []
    for sid, s in _sessions.items():
        items.append({
            "id":      sid,
            "state":   s.get("state", "pending"),
            "addr":    s.get("addr", ""),
            "uploads": s.get("uploads", 0),
            "last_ms": s.get("last_ms", 0),
        })
    items.sort(key=lambda v: v.get("last_ms", 0), reverse=True)
    return items


def approve(sid):
    """User tapped Allow on the WiFi/Transfer page."""
    if sid in _sessions:
        _sessions[sid]["state"] = "approved"
        return True
    return False


def deny(sid):
    if sid in _sessions:
        _sessions[sid]["state"] = "denied"
        return True
    return False


def progress():
    """Live upload progress dict, or None if no transfer is in flight."""
    return _progress




def _new_session_id():
    """Generate a 6-char alphanumeric id excluding ambiguous chars
    (0/O, 1/I, l). os.urandom would be ideal but isn't always present
    on MicroPython; time-mixed prand works for our scale."""
    import time as _t
    try:
        import os as _o
        seed = int.from_bytes(_o.urandom(4), "big")
    except Exception:
        seed = _t.ticks_ms() ^ id(_sessions)
    out = []
    n = len(SESSION_CHARSET)
    for _ in range(6):
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        out.append(SESSION_CHARSET[seed % n])
    return "".join(out)


def tick():
    """Accept and handle one pending request, if any. Cheap when idle
    (one non-blocking accept() syscall that ENOENTs out)."""
    if _lsock is None:
        return
    try:
        cli, _addr = _lsock.accept()
    except OSError:
        # EAGAIN — no pending connection. The common path.
        return
    except Exception:
        return
    try:
        cli.settimeout(RECV_TIMEOUT)
    except Exception:
        pass
    try:
        _handle(cli)
    except Exception as e:
        try:
            print("[http] handler crashed: %s" % e)
        except Exception:
            pass
    finally:
        try:
            cli.close()
        except Exception:
            pass
    gc.collect()


# ── request handling ────────────────────────────────────────────────────

def _read_until(sock, sep, max_len, deadline_ms=None):
    """Buffered recv that returns once `sep` appears in the stream.
    Returns (head_bytes, tail_bytes_after_sep) or (None, None) on
    timeout / overflow.

    `deadline_ms` is a hard wallclock cap measured from now. We need
    this so a TLS probe (browser ever-helpfully tries https first)
    can't pin the run loop for the full RECV_TIMEOUT × N recvs while
    the badge stops accepting button input.
    """
    try:
        import time as _t
        if deadline_ms is not None:
            deadline = _t.ticks_add(_t.ticks_ms(), int(deadline_ms))
        else:
            deadline = None
    except Exception:
        deadline = None
    buf = bytearray()
    while True:
        if len(buf) > max_len:
            return None, None
        if deadline is not None:
            try:
                if _t.ticks_diff(deadline, _t.ticks_ms()) <= 0:
                    return None, None
            except Exception:
                pass
        try:
            chunk = sock.recv(READ_CHUNK)
        except OSError:
            return None, None
        if not chunk:
            return None, None
        # Cheap TLS-handshake reject: a ClientHello starts with the
        # record-type byte 0x16. If the very first byte we ever see
        # is that, the browser was talking HTTPS — bail immediately
        # so we don't burn RECV_TIMEOUT waiting for header bytes
        # that will never come.
        if len(buf) == 0 and chunk and chunk[0] == 0x16:
            return None, None
        buf.extend(chunk)
        idx = buf.find(sep)
        if idx >= 0:
            head = bytes(buf[:idx])
            tail = bytes(buf[idx + len(sep):])
            return head, tail


def _parse_headers(head):
    """Returns (method, path, {header: value}). Headers are lowercased."""
    try:
        text = head.decode("utf-8", "ignore")
    except Exception:
        text = ""
    lines = text.split("\r\n")
    if not lines:
        return "", "", {}
    parts = lines[0].split(" ")
    method = parts[0] if len(parts) > 0 else ""
    path   = parts[1] if len(parts) > 1 else "/"
    headers = {}
    for line in lines[1:]:
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        headers[k.strip().lower()] = v.strip()
    return method, path, headers


def _send_status(sock, code, reason, body=b"", content_type="text/html; charset=utf-8"):
    head = ("HTTP/1.1 %d %s\r\n"
            "Content-Type: %s\r\n"
            "Content-Length: %d\r\n"
            "Connection: close\r\n\r\n") % (code, reason, content_type, len(body))
    try:
        sock.send(head.encode())
        if body:
            sock.send(body)
    except Exception:
        pass


_UPLOAD_FORM = (
    b"<!doctype html><html lang='en'><head>"
    b"<meta name='viewport' content='width=device-width,initial-scale=1'>"
    b"<meta name='theme-color' content='#0F0C1C'>"
    b"<title>Send to Oreo</title>"
    b"<style>"
    b":root{--bg:#0F0C1C;--card:#1C1A2E;--cardb:#26213E;--bord:#2A2640;"
    b"--ink:#F5E6DC;--dim:#C8B8B0;--mute:#8A8294;--pri:#FF5D68;"
    b"--gold:#FFD166;--teal:#3DDC97;--lilac:#A29BFE}"
    b"*{box-sizing:border-box}"
    b"html,body{margin:0;padding:0;background:var(--bg);color:var(--ink);"
    b"font-family:-apple-system,system-ui,Segoe UI,Roboto,sans-serif;"
    b"-webkit-font-smoothing:antialiased;min-height:100vh}"
    b"body{display:flex;flex-direction:column;align-items:center;padding:24px 16px;"
    b"background-image:radial-gradient(60% 50% at 20% 0%,rgba(255,93,104,.12),transparent 60%),"
    b"radial-gradient(50% 45% at 85% 100%,rgba(162,155,254,.08),transparent 60%)}"
    b".brand{display:flex;align-items:center;gap:10px;margin-bottom:18px}"
    b".brand .mark{width:32px;height:32px;border-radius:6px;border:1px solid rgba(255,93,104,.4);"
    b"background:var(--card);display:grid;place-items:center;font-weight:700;color:var(--pri);"
    b"box-shadow:0 0 24px rgba(255,93,104,.2)}"
    b".brand h1{margin:0;font-size:22px;font-weight:600;letter-spacing:-.01em}"
    b".panel{width:100%;max-width:440px;background:var(--card);border:1px solid var(--bord);"
    b"border-radius:14px;overflow:hidden}"
    b".pad{padding:24px}"
    b"h2{margin:0 0 6px;font-size:18px;font-weight:600}"
    b".sub{margin:0;color:var(--dim);font-size:13px;line-height:1.55}"
    b".code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:34px;"
    b"letter-spacing:.32em;color:var(--pri);margin:12px 0 6px;"
    b"text-shadow:0 0 30px rgba(255,93,104,.35)}"
    b".pulse{display:inline-block;width:8px;height:8px;border-radius:5px;background:var(--gold);"
    b"margin-right:8px;vertical-align:middle;animation:p 1.4s ease-in-out infinite}"
    b"@keyframes p{0%,100%{opacity:.25;transform:scale(.85)}50%{opacity:1;transform:scale(1)}}"
    b".chip{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;"
    b"font-size:11px;text-transform:uppercase;letter-spacing:.12em;background:var(--cardb);color:var(--dim)}"
    b".drop{border:2px dashed var(--bord);border-radius:10px;padding:22px;text-align:center;"
    b"cursor:pointer;transition:.2s border-color,.2s background;background:rgba(38,33,62,.4)}"
    b".drop:hover,.drop.over{border-color:var(--pri);background:rgba(255,93,104,.06)}"
    b".drop input{display:none}"
    b".drop .icon{font-size:30px;color:var(--pri);margin-bottom:4px;line-height:1}"
    b".drop .l1{font-weight:600;margin:6px 0 2px;font-size:14px}"
    b".drop .l2{margin:0;color:var(--mute);font-size:12px}"
    b".preview{display:none;align-items:center;gap:12px;background:var(--cardb);"
    b"border:1px solid var(--bord);border-radius:10px;padding:12px 14px}"
    b".thumb{width:60px;height:60px;border-radius:6px;background:var(--bg);flex-shrink:0;"
    b"display:grid;place-items:center;font-size:20px;color:var(--mute);overflow:hidden}"
    b".thumb img{width:100%;height:100%;object-fit:cover}"
    b".pmeta{flex:1;min-width:0}"
    b".pmeta .n{font-weight:600;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}"
    b".pmeta .s{font-size:12px;color:var(--mute);margin-top:2px}"
    b".btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;"
    b"background:var(--pri);color:var(--bg);border:0;border-radius:8px;padding:13px 18px;"
    b"font-size:15px;font-weight:600;width:100%;cursor:pointer;transition:.15s background}"
    b".btn:hover{background:#C8434C}"
    b".btn:disabled{background:#4A4458;color:var(--mute);cursor:not-allowed}"
    b".btn.ghost{background:transparent;color:var(--ink);border:1px solid var(--bord)}"
    b".btn.ghost:hover{background:var(--cardb)}"
    b".status{display:flex;align-items:center;gap:10px;padding:11px 13px;border-radius:8px;"
    b"background:var(--cardb);font-size:13px;color:var(--dim)}"
    b".status .dot{width:8px;height:8px;border-radius:5px;background:var(--mute)}"
    b".status.live .dot{background:var(--gold);animation:p 1.4s ease-in-out infinite}"
    b".status.ok .dot{background:var(--teal)}"
    b".status.err .dot{background:var(--pri)}"
    b".progress{height:6px;background:var(--bord);border-radius:4px;overflow:hidden;margin-top:14px}"
    b".bar{height:100%;background:linear-gradient(90deg,var(--pri),var(--lilac));"
    b"width:0;transition:width .15s ease-out}"
    b".pct{margin-top:8px;font-size:12px;color:var(--mute);display:flex;justify-content:space-between}"
    b".stack>*+*{margin-top:14px}"
    b".hide{display:none!important}"
    b".foot{margin-top:18px;font-size:11px;color:var(--mute);text-align:center;max-width:440px}"
    b".foot a{color:var(--dim);text-decoration:none;border-bottom:1px dashed var(--bord)}"
    b"</style></head><body>"
    b"<div class='brand'><div class='mark'>o</div><h1>Send to Oreo</h1></div>"
    b"<div class='panel'>"
    b"<div id='wait' class='pad stack'>"
    b"<span class='chip'><span class='pulse'></span>waiting for badge</span>"
    b"<h2>Show this code on the badge</h2>"
    b"<p class='sub'>Open <b>Settings &rsaquo; WiFi &rsaquo; Send files</b> "
    b"and tap <b>A</b> on the matching code to approve.</p>"
    b"<div class='code' id='sid'>------</div>"
    b"<div class='status live' id='wstat'><span class='dot'></span>"
    b"<span id='wmsg'>pinging badge…</span></div></div>"
    b"<div id='form' class='pad stack hide'>"
    b"<span class='chip' style='background:rgba(61,220,151,.15);color:var(--teal)'>"
    b"approved as <span id='okid' style='font-family:ui-monospace,monospace'></span></span>"
    b"<h2>Pick a file to send</h2>"
    b"<p class='sub'>Images convert to RGB565 in your browser before upload "
    b"(max 240&times;240). Text and Markdown land in Reader.</p>"
    b"<label class='drop' id='drop'>"
    b"<input id='file' type='file' accept='image/*,.txt,.md'>"
    b"<div class='icon'>&uarr;</div>"
    b"<p class='l1'>Tap to choose or drop here</p>"
    b"<p class='l2'>PNG &middot; JPG &middot; GIF &middot; TXT &middot; MD</p></label>"
    b"<div class='preview' id='preview'>"
    b"<div class='thumb' id='thumb'>?</div>"
    b"<div class='pmeta'><div class='n' id='pname'>&mdash;</div>"
    b"<div class='s' id='psize'>&mdash;</div></div></div>"
    b"<button id='go' class='btn' disabled>Send to badge</button>"
    b"<div class='progress'><div class='bar' id='bar'></div></div>"
    b"<div class='pct hide' id='pct'><span id='pctn'>0%</span>"
    b"<span id='pctb'>0 / 0 KB</span></div></div>"
    b"<div id='done' class='pad stack hide' style='text-align:center'>"
    b"<div style='font-size:42px;color:var(--teal);line-height:1'>&#10003;</div>"
    b"<h2>Sent!</h2><p class='sub'>Open the matching app on your badge to view it.</p>"
    b"<button class='btn' onclick='location.reload()'>Send another</button></div>"
    b"</div>"
    b"<div class='foot'>Peer-to-peer on your local network. "
    b"Powered by <a href='https://oreo.pages.dev' target='_blank'>oreo.pages.dev</a></div>"
    b"<script>"
    b"const $=id=>document.getElementById(id);"
    b"const MAX_DIM=240;"
    b"let sid=null,approved=false,beaconTimer=null,picked=null;"
    b"const urlPrefill=(()=>{try{return new URL(location.href).searchParams.get('prefill')||'';}"
    b"catch(e){return '';}})();"
    b"function fmtKB(n){return (n/1024)<1024?(Math.round(n/1024)+' KB'):"
    b"((n/1024/1024).toFixed(2)+' MB');}"
    b"function setWaitStatus(cls,msg){const s=$('wstat');s.className='status '+cls;$('wmsg').textContent=msg;}"
    b"async function bootSession(){"
    b"  if(urlPrefill&&urlPrefill.length===6){sid=urlPrefill.toUpperCase();$('sid').textContent=sid;return;}"
    b"  try{const r=await fetch('/session/new');const j=await r.json();sid=j.id;$('sid').textContent=sid;}"
    b"  catch(e){setWaitStatus('err','badge unreachable');}}"
    b"async function beacon(){"
    b"  if(!sid||approved)return;"
    b"  try{const r=await fetch('/beacon?id='+sid);const j=await r.json();"
    b"      if(j.state==='approved'){approved=true;clearInterval(beaconTimer);"
    b"        $('wait').classList.add('hide');$('form').classList.remove('hide');$('okid').textContent=sid;}"
    b"      else if(j.state==='denied'){clearInterval(beaconTimer);"
    b"        $('wait').innerHTML=\"<h2>Denied</h2><p class='sub'>The badge owner rejected this session.</p>"
    b"<button class='btn ghost' onclick='location.reload()'>Try again</button>\";}"
    b"      else{setWaitStatus('live','waiting for tap on badge…');}}"
    b"  catch(e){setWaitStatus('err','badge unreachable - check WiFi');}}"
    b"function onFile(file){"
    b"  if(!file)return;picked=file;"
    b"  $('preview').style.display='flex';$('drop').style.display='none';"
    b"  $('pname').textContent=file.name;$('psize').textContent=fmtKB(file.size);"
    b"  const th=$('thumb');th.innerHTML='';"
    b"  if(file.type.startsWith('image/')){"
    b"    const im=document.createElement('img');im.src=URL.createObjectURL(file);th.appendChild(im);}"
    b"  else{th.textContent=file.name.split('.').pop().toUpperCase();}"
    b"  $('go').disabled=false;}"
    b"async function imgToR565(file){"
    b"  const img=new Image();img.src=URL.createObjectURL(file);"
    b"  await new Promise((r,j)=>{img.onload=r;img.onerror=j;});"
    b"  const sc=Math.min(1,MAX_DIM/Math.max(img.width,img.height));"
    b"  const w=Math.max(1,Math.round(img.width*sc)),h=Math.max(1,Math.round(img.height*sc));"
    b"  const c=document.createElement('canvas');c.width=w;c.height=h;"
    b"  const ctx=c.getContext('2d');"
    b"  ctx.fillStyle='#000';ctx.fillRect(0,0,w,h);ctx.drawImage(img,0,0,w,h);"
    b"  const px=ctx.getImageData(0,0,w,h).data;"
    b"  const out=new Uint8Array(6+w*h*2);"
    b"  out[0]=0x52;out[1]=0x35;"
    b"  out[2]=w&0xff;out[3]=(w>>8)&0xff;"
    b"  out[4]=h&0xff;out[5]=(h>>8)&0xff;"
    b"  let o=6;"
    b"  for(let i=0;i<px.length;i+=4){"
    b"    const r=px[i]>>3,g=px[i+1]>>2,b=px[i+2]>>3;"
    b"    const v=(r<<11)|(g<<5)|b;out[o++]=(v>>8)&0xff;out[o++]=v&0xff;}"
    b"  return new Blob([out],{type:'application/octet-stream'});}"
    b"async function send(){"
    b"  if(!picked||!sid)return;$('go').disabled=true;$('pct').classList.remove('hide');"
    b"  let payload=picked,name=picked.name;"
    b"  if(picked.type.startsWith('image/')){"
    b"    try{payload=await imgToR565(picked);name=name.replace(/\\.[^.]+$/,'')+'.r565';}"
    b"    catch(err){alert('Image decode failed: '+err);$('go').disabled=false;return;}}"
    b"  const fd=new FormData();fd.append('f',payload,name);"
    b"  const xhr=new XMLHttpRequest();"
    b"  xhr.upload.addEventListener('progress',(ev)=>{"
    b"    if(ev.lengthComputable){const p=ev.loaded/ev.total;"
    b"      $('bar').style.width=(p*100)+'%';"
    b"      $('pctn').textContent=Math.round(p*100)+'%';"
    b"      $('pctb').textContent=fmtKB(ev.loaded)+' / '+fmtKB(ev.total);}});"
    b"  xhr.onload=()=>{if(xhr.status===200){"
    b"    $('form').classList.add('hide');$('done').classList.remove('hide');}"
    b"    else{alert('Upload failed: '+xhr.status);$('go').disabled=false;}};"
    b"  xhr.onerror=()=>{alert('Network error - check WiFi.');$('go').disabled=false;};"
    b"  xhr.open('POST','/upload?token='+sid);xhr.send(fd);}"
    b"document.addEventListener('DOMContentLoaded',async()=>{"
    b"  await bootSession();setWaitStatus('live','waiting for tap on badge…');"
    b"  beaconTimer=setInterval(beacon,2000);beacon();"
    b"  $('file').addEventListener('change',e=>onFile(e.target.files[0]));"
    b"  const dz=$('drop');"
    b"  ['dragenter','dragover'].forEach(ev=>dz.addEventListener(ev,e=>{e.preventDefault();dz.classList.add('over');}));"
    b"  ['dragleave','drop'].forEach(ev=>dz.addEventListener(ev,e=>{e.preventDefault();dz.classList.remove('over');}));"
    b"  dz.addEventListener('drop',e=>{if(e.dataTransfer.files[0])onFile(e.dataTransfer.files[0]);});"
    b"  $('go').addEventListener('click',send);});"
    b"</script></body></html>"
)


def _parse_query(path):
    """Return (path_without_query, {key: value}) — minimal urlparse
    replacement since MicroPython doesn't ship one. Decodes %xx."""
    if "?" not in path:
        return path, {}
    pure, _, qs = path.partition("?")
    out = {}
    for part in qs.split("&"):
        if not part:
            continue
        k, _, v = part.partition("=")
        out[_pct(k)] = _pct(v)
    return pure, out


def _pct(s):
    """Tiny percent-decode. Only handles the ASCII subset we expect
    in our query params — IDs are alphanumeric, no spaces."""
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "%" and i + 2 < len(s):
            try:
                out.append(chr(int(s[i + 1:i + 3], 16)))
                i += 3
                continue
            except ValueError:
                pass
        out.append(c)
        i += 1
    return "".join(out)


def _peer_addr(sock):
    """Best-effort peer address for the session log."""
    try:
        addr = sock.getpeername()
        return "%s:%d" % (addr[0], addr[1])
    except Exception:
        return ""


def _handle(sock):
    """One request, one response. Closes on return."""
    head, after_head = _read_until(sock, b"\r\n\r\n", 8 * 1024,
                                   deadline_ms=HEAD_DEADLINE_MS)
    if head is None:
        _send_status(sock, 408, "Request Timeout", b"timeout")
        return
    method, full_path, headers = _parse_headers(head)
    path, qs = _parse_query(full_path)

    if method == "GET" and path in ("/", "/index.html"):
        _send_status(sock, 200, "OK", _UPLOAD_FORM)
        return
    if method == "GET" and path == "/favicon.ico":
        _send_status(sock, 204, "No Content", b"")
        return
    if method == "GET" and path == "/beacon":
        _handle_beacon(sock, qs, _peer_addr(sock))
        return
    if method == "GET" and path == "/session/new":
        _handle_session_new(sock, _peer_addr(sock))
        return
    if method == "POST" and path == "/upload":
        _handle_upload(sock, headers, after_head, qs)
        return

    _send_status(sock, 404, "Not Found", b"not found")


def _handle_session_new(sock, peer_addr):
    """Hand the sender a freshly-minted session id so it doesn't have
    to roll its own (saves us from collisions between two phones that
    both picked the same client-side random)."""
    _prune_sessions()
    if len(_sessions) >= SESSION_MAX:
        _send_status(sock, 503, "Service Unavailable",
                     b'{"error":"too many active sessions"}',
                     content_type="application/json")
        return
    sid = _new_session_id()
    try:
        import time as _t
        now = _t.ticks_ms()
    except Exception:
        now = 0
    _sessions[sid] = {"state": "pending", "last_ms": now,
                      "addr": peer_addr, "uploads": 0}
    body = ('{"id":"%s","state":"pending"}' % sid).encode()
    _send_status(sock, 200, "OK", body, content_type="application/json")


def _handle_beacon(sock, qs, peer_addr):
    """Heartbeat from a sender's browser. Bumps last_ms so the session
    stays alive, and reports the current state so the UI on the phone
    can switch from 'Waiting…' to 'Ready' once the badge approves."""
    sid = qs.get("id", "")
    if not sid or len(sid) != 6:
        _send_status(sock, 400, "Bad Request",
                     b'{"error":"missing id"}',
                     content_type="application/json")
        return
    _prune_sessions()
    try:
        import time as _t
        now = _t.ticks_ms()
    except Exception:
        now = 0
    s = _sessions.get(sid)
    if s is None:
        if len(_sessions) >= SESSION_MAX:
            _send_status(sock, 503, "Service Unavailable",
                         b'{"error":"too many sessions"}',
                         content_type="application/json")
            return
        _sessions[sid] = {"state": "pending", "last_ms": now,
                          "addr": peer_addr, "uploads": 0}
        state = "pending"
    else:
        s["last_ms"] = now
        if peer_addr:
            s["addr"] = peer_addr
        state = s["state"]
    body = ('{"id":"%s","state":"%s"}' % (sid, state)).encode()
    _send_status(sock, 200, "OK", body, content_type="application/json")


def _handle_upload(sock, headers, body_prefix, qs):
    """Stream a single multipart part to disk. Phones POST exactly one
    file per share, so we don't try to handle multi-part bodies — we
    extract the first file part and ignore everything after.

    Gated on `?token=XXXXXX`: the session must exist AND be in state
    "approved", which only happens after the user explicitly taps Allow
    on the badge's WiFi/Transfer page. Without that the badge silently
    accepting uploads from anyone on the LAN would be a footgun.
    """
    token = qs.get("token", "")
    s = _sessions.get(token) if token else None
    if s is None or s.get("state") != "approved":
        _send_status(sock, 403, "Forbidden",
                     b'{"error":"token not approved"}',
                     content_type="application/json")
        return
    ctype = headers.get("content-type", "")
    if "multipart/form-data" not in ctype:
        _send_status(sock, 400, "Bad Request", b"expected multipart/form-data")
        return
    # Extract boundary= from the Content-Type header. RFC 7578 wraps it
    # in quotes sometimes; strip them.
    bidx = ctype.find("boundary=")
    if bidx < 0:
        _send_status(sock, 400, "Bad Request", b"missing boundary")
        return
    boundary = ctype[bidx + len("boundary="):].split(";", 1)[0].strip().strip('"')
    if not boundary:
        _send_status(sock, 400, "Bad Request", b"empty boundary")
        return
    boundary_marker = ("--" + boundary).encode()

    try:
        clen = int(headers.get("content-length", "0"))
    except ValueError:
        clen = 0
    if clen <= 0 or clen > MAX_BODY:
        _send_status(sock, 413, "Payload Too Large", b"file too large")
        return

    # Find the first part's header block.
    head_buf = bytearray(body_prefix)
    bytes_read = len(body_prefix)
    while head_buf.find(b"\r\n\r\n") < 0:
        if bytes_read > 16 * 1024 or bytes_read >= clen:
            _send_status(sock, 400, "Bad Request", b"part header missing")
            return
        try:
            chunk = sock.recv(READ_CHUNK)
        except OSError:
            _send_status(sock, 408, "Request Timeout", b"timeout reading part header")
            return
        if not chunk:
            _send_status(sock, 400, "Bad Request", b"truncated")
            return
        head_buf.extend(chunk)
        bytes_read += len(chunk)
    hdr_end = head_buf.find(b"\r\n\r\n")
    part_head = bytes(head_buf[:hdr_end])
    rest      = bytes(head_buf[hdr_end + 4:])

    # Extract filename from Content-Disposition.
    cd = ""
    for line in part_head.decode("utf-8", "ignore").split("\r\n"):
        if line.lower().startswith("content-disposition:"):
            cd = line
            break
    fname = ""
    fkey = "filename="
    fi = cd.find(fkey)
    if fi >= 0:
        rest_cd = cd[fi + len(fkey):]
        if rest_cd.startswith('"'):
            end = rest_cd.find('"', 1)
            if end > 0:
                fname = rest_cd[1:end]
        else:
            fname = rest_cd.split(";", 1)[0].strip()
    fname = _safe_filename(fname)

    dest_dir, kind = _route_for(fname)
    if dest_dir is None:
        _send_status(sock, 415, "Unsupported Media Type",
                     ("rejected: " + str(kind)).encode())
        return

    _ensure_dir(dest_dir)
    dst_path = dest_dir + "/" + fname
    # If something with this name already exists, suffix a counter so we
    # don't clobber. Cheap and predictable.
    if _os is not None:
        try:
            _os.stat(dst_path)
            base = fname
            ext = ""
            dot = base.rfind(".")
            if dot > 0:
                base, ext = base[:dot], base[dot:]
            i = 1
            while True:
                cand = "%s/%s-%d%s" % (dest_dir, base, i, ext)
                try:
                    _os.stat(cand)
                    i += 1
                except OSError:
                    dst_path = cand
                    break
        except OSError:
            pass

    # Stream the rest of the body into the file, scanning for the
    # closing boundary. The "tail buffer" trick: keep the last
    # (len(boundary)+8) bytes unwritten until we're sure they're not
    # the start of the closing marker.
    closing = b"\r\n" + boundary_marker
    tail_keep = len(closing) + 4
    written = 0
    try:
        f = open(dst_path, "wb")
    except Exception:
        _send_status(sock, 500, "Internal Error",
                     b"write failed (out of space?)")
        return

    # Publish a live progress slot the WiFi UI polls every frame to
    # render the progress bar. Total here is the *body length*, not
    # the file length (we don't know the file length until we hit the
    # closing boundary). Off by ~boundary-length bytes — good enough.
    global _progress
    _progress = {"id": token, "filename": fname,
                 "received": 0, "total": clen}

    try:
        buf = bytearray(rest)
        body_left = clen - bytes_read  # bytes still on the wire after we filled head_buf
        while True:
            # If `buf` contains the closing boundary, flush up to it and stop.
            idx = buf.find(closing)
            if idx >= 0:
                f.write(bytes(buf[:idx]))
                written += idx
                break
            # Otherwise flush all but the last tail_keep bytes (they
            # might be the start of the boundary).
            if len(buf) > tail_keep:
                cut = len(buf) - tail_keep
                f.write(bytes(buf[:cut]))
                written += cut
                buf = buf[cut:]
            if body_left <= 0 and not buf:
                f.write(bytes(buf))
                written += len(buf)
                break
            try:
                chunk = sock.recv(READ_CHUNK)
            except OSError:
                break
            if not chunk:
                f.write(bytes(buf))
                written += len(buf)
                break
            body_left -= len(chunk)
            buf.extend(chunk)
            # Live progress update — the WiFi UI samples this at 4 Hz
            # so an O(1) dict assignment per chunk is fine.
            _progress["received"] = written + max(0, len(buf) - tail_keep)
            if written > MAX_BODY:
                break
    finally:
        try:
            f.close()
        except Exception:
            pass
        _progress = None

    if written <= 0:
        try:
            _os.remove(dst_path)
        except Exception:
            pass
        _send_status(sock, 400, "Bad Request", b"empty upload")
        return

    # Mark the upload on the session so the WiFi UI can show "got 2
    # files from session ABCD12" instead of just "approved".
    if token in _sessions:
        _sessions[token]["uploads"] = _sessions[token].get("uploads", 0) + 1

    # Surface the new file in the notification panel so the user knows
    # where it landed without having to open the Gallery or Reader.
    target_app = "gallery" if kind == "image" else "reader"
    try:
        from oreoOS import notifications
        notifications.push("wifi",
                           "Received %s" % kind,
                           "%s · %d KB" % (fname[:18], written // 1024),
                           target=target_app)
    except Exception:
        pass

    # We deliberately DON'T auto-launch the receiving app — the file
    # is already on flash and Gallery / Reader will pick it up the
    # next time the user opens those apps. The notification above is
    # the "your file arrived" cue.

    body = (b"<!doctype html><html><head>"
            b"<meta http-equiv='refresh' content='2; url=/'>"
            b"<title>Sent</title>"
            b"<style>body{font-family:-apple-system,system-ui,sans-serif;"
            b"background:#0f0c1c;color:#f5e6dc;text-align:center;padding-top:80px}"
            b"h1{color:#ff5d68}</style></head><body>"
            b"<h1>Sent &#10003;</h1>"
            b"<p>Returning to upload form...</p></body></html>")
    _send_status(sock, 200, "OK", body)

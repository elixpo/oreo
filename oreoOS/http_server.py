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
RECV_TIMEOUT  = 8                 # seconds — per-recv() during streaming


_lsock = None
_bound_ip = None


# ── routing tables ──────────────────────────────────────────────────────

_GALLERY_DIR  = "apps/gallery/assets/raw"
_DOCS_DIR     = "documents"

_IMG_EXTS = (".png", ".jpg", ".jpeg", ".gif")
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
    """The address users should type on their phone — shown on-screen
    by the BT app's Transfer row. Returns "" if we're not listening."""
    if _bound_ip is None:
        return ""
    return "http://%s/" % _bound_ip


def is_running():
    return _lsock is not None


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

def _read_until(sock, sep, max_len):
    """Buffered recv that returns once `sep` appears in the stream.
    Returns (head_bytes, tail_bytes_after_sep) or (None, None) on
    timeout / overflow."""
    buf = bytearray()
    while True:
        if len(buf) > max_len:
            return None, None
        try:
            chunk = sock.recv(READ_CHUNK)
        except OSError:
            return None, None
        if not chunk:
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
    b"<!doctype html><html><head>"
    b"<meta name='viewport' content='width=device-width,initial-scale=1'>"
    b"<title>Send to Oreo</title>"
    b"<style>"
    b"body{font-family:-apple-system,system-ui,sans-serif;"
    b"background:#0f0c1c;color:#f5e6dc;margin:0;padding:24px;"
    b"display:flex;flex-direction:column;align-items:center;min-height:100vh}"
    b"h1{color:#ff5d68;margin:8px 0 4px}p{color:#a89898;margin:4px 0 24px;font-size:14px}"
    b"form{background:#1c1a2e;border:2px solid #ff5d68;border-radius:8px;"
    b"padding:24px;width:100%;max-width:380px}"
    b"input[type=file]{width:100%;color:#f5e6dc;margin-bottom:16px}"
    b"button{background:#ff5d68;color:#0f0c1c;border:0;border-radius:6px;"
    b"padding:14px 20px;font-size:16px;font-weight:bold;width:100%}"
    b".hint{margin-top:16px;color:#a89898;font-size:12px}"
    b"</style></head><body>"
    b"<h1>Send to Oreo</h1>"
    b"<p>Photos &middot; .txt &middot; .md</p>"
    b"<form method='POST' action='/upload' enctype='multipart/form-data'>"
    b"<input type='file' name='f' accept='.png,.jpg,.jpeg,.gif,.txt,.md' required>"
    b"<button type='submit'>Upload</button>"
    b"<p class='hint'>Photos land in Gallery, text/md in Reader.</p>"
    b"</form></body></html>"
)


def _handle(sock):
    """One request, one response. Closes on return."""
    head, after_head = _read_until(sock, b"\r\n\r\n", 8 * 1024)
    if head is None:
        _send_status(sock, 408, "Request Timeout", b"timeout")
        return
    method, path, headers = _parse_headers(head)

    if method == "GET" and path in ("/", "/index.html"):
        _send_status(sock, 200, "OK", _UPLOAD_FORM)
        return
    if method == "GET" and path == "/favicon.ico":
        _send_status(sock, 204, "No Content", b"")
        return
    if method == "POST" and path == "/upload":
        _handle_upload(sock, headers, after_head)
        return

    _send_status(sock, 404, "Not Found", b"not found")


def _handle_upload(sock, headers, body_prefix):
    """Stream a single multipart part to disk. Phones POST exactly one
    file per share, so we don't try to handle multi-part bodies — we
    extract the first file part and ignore everything after."""
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
                # Body exhausted without finding boundary — write the
                # leftover and call it done. Some phones omit the final
                # CRLF before the boundary on truncation; we trust the
                # Content-Length anyway.
                f.write(bytes(buf))
                written += len(buf)
                break
            try:
                chunk = sock.recv(READ_CHUNK)
            except OSError:
                break
            if not chunk:
                # Connection closed early — write what we held back.
                f.write(bytes(buf))
                written += len(buf)
                break
            body_left -= len(chunk)
            buf.extend(chunk)
            if written > MAX_BODY:
                break
    finally:
        try:
            f.close()
        except Exception:
            pass

    if written <= 0:
        try:
            _os.remove(dst_path)
        except Exception:
            pass
        _send_status(sock, 400, "Bad Request", b"empty upload")
        return

    # Surface the new file in the notification panel so the user knows
    # where it landed without having to open the Gallery or Reader.
    try:
        from oreoOS import notifications
        notifications.push("bt",
                           "Received %s" % kind,
                           "%s · %d KB" % (fname[:18], written // 1024),
                           target=("gallery" if kind == "image" else "reader"))
    except Exception:
        pass

    body = (b"<!doctype html><html><head>"
            b"<meta http-equiv='refresh' content='2; url=/'>"
            b"<title>Sent</title>"
            b"<style>body{font-family:-apple-system,system-ui,sans-serif;"
            b"background:#0f0c1c;color:#f5e6dc;text-align:center;padding-top:80px}"
            b"h1{color:#ff5d68}</style></head><body>"
            b"<h1>Sent &#10003;</h1>"
            b"<p>Returning to upload form...</p></body></html>")
    _send_status(sock, 200, "OK", body)

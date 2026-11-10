"""High-level badge operations, driven over the raw REPL.

Every operation sends a short MicroPython 1.28 snippet that reports back
with `@OREO:<json>` lines (events) and, for downloads, `@B:<base64>` lines
(data). Anything else the badge prints (OreoOS log lines such as
"[wifi] connecting") is passed through as chatter.

Snippets only use what the badge firmware has: os.ilistdir/stat/statvfs,
json, binascii, hashlib, time.sleep_ms, and the OreoOS modules
(oreoOS.config, oreoOS.storage, oreoOS.store, oreoWare.wifi,
oreoWare.battery).
"""

import base64
import binascii
import hashlib
import json
import posixpath

from .errors import BadgeError, OreoError, redact

EVENT = "@OREO:"
DATA = "@B:"

PRELUDE = (
    "import json as _j\n"
    "def _e(o):\n"
    " print('@OREO:'+_j.dumps(o))\n"
)

B64 = (
    "try:\n"
    " import binascii as _b\n"
    "except ImportError:\n"
    " import ubinascii as _b\n"
)

# Paths `oreo rm` refuses without --force: removing them stops OreoOS booting.
PROTECTED = ("/", "/main.py", "/boot.py", "/oreoOS", "/oreoWare", "/apps",
             "/apps/launcher", "/assets")

PUSH_CHUNK = 4096        # raw bytes per exec (about 5.5 KB of base64 code)
PULL_CHUNK = 3072        # raw bytes per @B: line
FREE_RESERVE = 64 * 1024  # keep this much flash free after a push


def lit(value):
    """A Python literal for `value`, valid MicroPython source."""
    return repr(value)


def norm(path):
    """Badge path -> absolute, normalised ('/a/b'). Accepts ':a/b' too."""
    p = (path or "/").strip()
    if p.startswith(":"):
        p = p[1:]
    if not p.startswith("/"):
        p = "/" + p
    p = posixpath.normpath(p)
    if p.startswith("//"):
        p = p[1:]
    return p


class OutputParser:
    """Splits streamed badge output into events, data chunks and chatter."""

    def __init__(self, on_event=None, on_data=None, on_text=None):
        self._buf = b""
        self.events = []
        self.text = []
        self.on_event = on_event
        self.on_data = on_data
        self.on_text = on_text

    def feed(self, chunk):
        self._buf += chunk.replace(b"\x04", b"")
        while b"\n" in self._buf:
            line, self._buf = self._buf.split(b"\n", 1)
            self._line(line.rstrip(b"\r"))

    def finish(self):
        if self._buf.strip():
            self._line(self._buf.rstrip(b"\r"))
        self._buf = b""

    def _line(self, raw):
        s = raw.decode("utf-8", "replace")
        if s.startswith(EVENT):
            try:
                ev = json.loads(s[len(EVENT):])
            except ValueError:
                self._text(s)
                return
            self.events.append(ev)
            if self.on_event:
                self.on_event(ev)
        elif s.startswith(DATA):
            data = binascii.a2b_base64(s[len(DATA):])
            if self.on_data:
                self.on_data(data)
        else:
            self._text(s)

    def _text(self, s):
        self.text.append(s)
        if self.on_text:
            self.on_text(s)


class Badge:
    """One session with one badge. Opens on first use."""

    def __init__(self, link, on_text=None):
        self.link = link
        self.on_text = on_text
        self.entered = False

    # ── session ──────────────────────────────────────────────────────
    def connect(self):
        if not self.entered:
            self.link.enter()
            self.entered = True
        return self

    def finish(self, mode="soft"):
        """Leave OreoOS running again (unless mode == 'none')."""
        if self.entered or getattr(self.link, "t", None) is not None:
            self.link.restart(mode)
        self.entered = False

    # ── exec helpers ─────────────────────────────────────────────────
    def run(self, code, timeout=15, on_event=None, on_data=None, secrets=()):
        self.connect()
        parser = OutputParser(on_event, on_data, self.on_text)
        try:
            self.link.exec(PRELUDE + code, timeout=timeout, consumer=parser.feed)
        except BadgeError as e:
            raise BadgeError(redact(e.message, secrets), redact(e.detail, secrets),
                             hint=e.hint)
        except OreoError as e:
            raise OreoError(redact(e.message, secrets), hint=e.hint)
        parser.finish()
        return parser

    def result(self, code, timeout=15, on_event=None, secrets=()):
        """Run code and return the last event it emitted."""
        parser = self.run(code, timeout=timeout, on_event=on_event, secrets=secrets)
        if not parser.events:
            raise BadgeError("the badge sent no result", detail="\n".join(parser.text))
        return parser.events[-1]

    # ── device info ──────────────────────────────────────────────────
    def info(self):
        code = (
            "import os, sys, gc\n"
            "r={}\n"
            "try:\n"
            " u=os.uname()\n"
            " r['machine']=u.machine\n"
            " r['fw']=u.version\n"
            " r['release']=u.release\n"
            "except Exception:\n"
            " pass\n"
            "try:\n"
            " v=sys.implementation.version\n"
            " r['mpy']='%d.%d.%d'%(v[0],v[1],v[2])\n"
            "except Exception:\n"
            " r['mpy']=None\n"
            "try:\n"
            " from oreoOS import config as c\n"
            " r['os']=c.VERSION\n"
            " r['date']=getattr(c,'RELEASE_DATE','')\n"
            " r['bt_auto']=bool(getattr(c,'BT_AUTO_ENABLE',False))\n"
            "except Exception:\n"
            " r['os']=None\n"
            "try:\n"
            " from oreoOS import storage as s\n"
            " r['storage']=s.usage()\n"
            "except Exception:\n"
            " s=os.statvfs('/')\n"
            " r['storage']={'stats':{'total':s[1]*s[2],'free':s[1]*s[4],"
            "'used':s[1]*(s[2]-s[4])},'buckets':None}\n"
            "try:\n"
            " from oreoWare import wifi as w\n"
            " up=bool(w.is_connected())\n"
            " r['wifi']={'up':up,'ip':w.ip() if up else None,'saved':len(w.list_saved())}\n"
            "except Exception:\n"
            " r['wifi']=None\n"
            "try:\n"
            " from oreoWare import battery as b\n"
            " r['battery']={'pct':b.read_percent(),'v':b.read_voltage()}\n"
            "except Exception:\n"
            " r['battery']=None\n"
            "gc.collect()\n"
            "try:\n"
            " r['mem_free']=gc.mem_free()\n"
            "except Exception:\n"
            " pass\n"
            "_e(r)\n"
        )
        return self.result(code, timeout=60)

    def banner(self):
        """Firmware identity only (cheap; used by doctor)."""
        code = (
            "import os, sys\n"
            "r={'impl':sys.implementation.name}\n"
            "try:\n"
            " v=sys.implementation.version\n"
            " r['mpy']='%d.%d.%d'%(v[0],v[1],v[2])\n"
            " u=os.uname()\n"
            " r['machine']=u.machine\n"
            " r['fw']=u.version\n"
            "except Exception:\n"
            " pass\n"
            "try:\n"
            " os.stat('/oreoOS/config.py')\n"
            " from oreoOS import config as c\n"
            " r['os']=c.VERSION\n"
            "except Exception:\n"
            " r['os']=None\n"
            "_e(r)\n"
        )
        return self.result(code)

    # ── files ────────────────────────────────────────────────────────
    def stat(self, path):
        """{'dir': bool, 'size': int} or None when missing."""
        code = (
            "import os\n"
            "try:\n"
            " s=os.stat(%s)\n"
            " _e({'dir':bool(s[0]&0x4000),'size':s[6]})\n"
            "except OSError:\n"
            " _e({'missing':1})\n" % lit(norm(path))
        )
        r = self.result(code)
        return None if r.get("missing") else r

    def ls(self, path="/"):
        """[{'name', 'dir', 'size'}], directories first."""
        p = norm(path)
        code = (
            "import os\n"
            "try:\n"
            " s=os.stat(%(p)s)\n"
            "except OSError:\n"
            " s=None\n"
            "if s is None:\n"
            " _e({'missing':1})\n"
            "elif not s[0]&0x4000:\n"
            " _e({'file':[%(n)s,0,s[6]]})\n"
            "else:\n"
            " r=[]\n"
            " for x in os.ilistdir(%(p)s):\n"
            "  r.append([x[0],1 if x[1]&0x4000 else 0,x[3] if len(x)>3 else 0])\n"
            " _e({'ls':r})\n" % {"p": lit(p), "n": lit(posixpath.basename(p))}
        )
        r = self.result(code)
        if r.get("missing"):
            raise OreoError("%s: not found on the badge" % p)
        rows = [r["file"]] if "file" in r else r["ls"]
        out = [{"name": n, "dir": bool(d), "size": s} for n, d, s in rows]
        out.sort(key=lambda e: (not e["dir"], e["name"].lower()))
        return out

    def walk(self, path):
        """Yield (badge_path, size) for every file under a directory."""
        p = norm(path)
        for e in self.ls(p):
            child = posixpath.join(p, e["name"])
            if e["dir"]:
                for item in self.walk(child):
                    yield item
            else:
                yield child, e["size"]

    def free(self):
        r = self.result(
            "import os\n"
            "s=os.statvfs('/')\n"
            "_e({'free':s[1]*s[4],'total':s[1]*s[2]})\n")
        return r["free"], r["total"]

    def mkdirs(self, path):
        p = norm(path)
        if p == "/":
            return
        self.result(
            "import os\n"
            "c=''\n"
            "for x in %s.split('/'):\n"
            " if not x:\n"
            "  continue\n"
            " c=c+'/'+x\n"
            " try:\n"
            "  os.mkdir(c)\n"
            " except OSError:\n"
            "  pass\n"
            "_e({'ok':1})\n" % lit(p))

    def write_file(self, data, remote, progress=None, verify=True,
                   chunk=PUSH_CHUNK, reserve=FREE_RESERVE):
        """Copy bytes to `remote` atomically (temp file, then rename)."""
        dest = norm(remote)
        free, _ = self.free()
        if len(data) + reserve > free:
            from .ui import human
            raise OreoError("not enough space on the badge: %s needed, %s free"
                            % (human(len(data)), human(max(0, free - reserve))),
                            hint="free some space (`oreo info`, `oreo rm`)")
        parent = posixpath.dirname(dest)
        if parent and parent != "/":
            self.mkdirs(parent)
        tmp = dest + ".part"
        self.run("import os\n" + B64 +
                 "_f=open(%s,'wb')\n_w=_f.write\n_d=_b.a2b_base64\n" % lit(tmp))
        done = 0
        try:
            for i in range(0, len(data), chunk):
                piece = data[i:i + chunk]
                self.link.exec("_w(_d(%s))" % lit(base64.b64encode(piece)), timeout=15)
                done += len(piece)
                if progress:
                    progress(done, len(data))
            r = self.result(
                "_f.close()\n"
                "try:\n"
                " os.rename(%(t)s,%(d)s)\n"
                "except OSError:\n"
                " os.remove(%(d)s)\n"
                " os.rename(%(t)s,%(d)s)\n"
                "_e({'size':os.stat(%(d)s)[6]})\n" % {"t": lit(tmp), "d": lit(dest)})
        except BaseException:   # Ctrl-C too: do not leave a .part file behind
            try:
                self.link.exec("try:\n _f.close()\nexcept Exception:\n pass\n"
                               "try:\n os.remove(%s)\nexcept Exception:\n pass\n" % lit(tmp))
            except Exception:
                pass
            raise
        if progress and not data:
            progress(0, 0)
        if r["size"] != len(data):
            raise OreoError("%s: badge has %d bytes, expected %d" % (dest, r["size"], len(data)))
        if verify:
            want = hashlib.sha256(data).hexdigest()
            got = self.sha256(dest)
            if got is not None and got != want:
                raise OreoError("%s: checksum mismatch after copy" % dest,
                                hint="try again; if it repeats, try another cable")
        return dest

    def sha256(self, remote):
        r = self.result(
            B64 +
            "try:\n"
            " import hashlib\n"
            " h=hashlib.sha256()\n"
            " f=open(%s,'rb')\n"
            " while 1:\n"
            "  c=f.read(2048)\n"
            "  if not c:\n"
            "   break\n"
            "  h.update(c)\n"
            " f.close()\n"
            " _e({'sha':_b.hexlify(h.digest()).decode()})\n"
            "except ImportError:\n"
            " _e({'sha':None})\n" % lit(norm(remote)), timeout=60)
        return r["sha"]

    def read_file(self, remote, progress=None, chunk=PULL_CHUNK):
        src = norm(remote)
        st = self.stat(src)
        if st is None:
            raise OreoError("%s: not found on the badge" % src)
        if st["dir"]:
            raise OreoError("%s is a directory" % src, hint="use `oreo pull -r`")
        total = st["size"]
        buf = bytearray()

        def on_data(piece):
            buf.extend(piece)
            if progress:
                progress(len(buf), total)
        self.run(
            B64 +
            "_f=open(%s,'rb')\n"
            "while 1:\n"
            " c=_f.read(%d)\n"
            " if not c:\n"
            "  break\n"
            " print('@B:'+_b.b2a_base64(c).decode().strip())\n"
            "_f.close()\n" % (lit(src), chunk), on_data=on_data)
        if len(buf) != total:
            raise OreoError("%s: received %d of %d bytes" % (src, len(buf), total))
        return bytes(buf)

    def rm(self, path, recursive=False):
        p = norm(path)
        code = (
            "import os\n"
            "def _rm(p):\n"
            " if os.stat(p)[0]&0x4000:\n"
            "  if not %(r)s:\n"
            "   raise OSError(21)\n"
            "  for x in list(os.ilistdir(p)):\n"
            "   _rm((p.rstrip('/'))+'/'+x[0])\n"
            "  if p!='/':\n"
            "   os.rmdir(p)\n"
            " else:\n"
            "  os.remove(p)\n"
            "try:\n"
            " os.stat(%(p)s)\n"
            "except OSError:\n"
            " _e({'missing':1})\n"
            "else:\n"
            " try:\n"
            "  _rm(%(p)s)\n"
            "  _e({'ok':1})\n"
            " except OSError as x:\n"
            "  _e({'err':x.args[0] if x.args else 0})\n"
            % {"p": lit(p), "r": "True" if recursive else "False"})
        r = self.result(code, timeout=60)
        if r.get("missing"):
            raise OreoError("%s: not found on the badge" % p)
        if "err" in r:
            if r["err"] == 21:
                raise OreoError("%s is a directory" % p, hint="use `oreo rm -r`")
            raise OreoError("could not remove %s (errno %s)" % (p, r["err"]))
        return p

    # ── wifi (oreoWare.wifi) ─────────────────────────────────────────
    def wifi_scan(self, timeout_s=15):
        code = (
            "import time\n"
            "from oreoWare import wifi as w\n"
            "try:\n"
            " w.auto_stop()\n"
            "except Exception:\n"
            " pass\n"
            "if not w.scan_start():\n"
            " _e({'error':w.scan_error() or 'radio error'})\n"
            "else:\n"
            " r=w.scan_poll()\n"
            " while r=='busy':\n"
            "  time.sleep_ms(100)\n"
            "  r=w.scan_poll()\n"
            " if r=='done':\n"
            "  _e({'nets':w.nearby(),'saved':list(w.saved_ssids())})\n"
            " else:\n"
            "  _e({'error':w.scan_error() or r})\n"
        )
        r = self.result(code, timeout=timeout_s)
        if "error" in r:
            raise OreoError("Wi-Fi scan failed on the badge: %s" % r["error"],
                            hint="try again; see issue #120 if it keeps failing")
        saved = set(r.get("saved") or ())
        for n in r["nets"]:
            n["saved"] = n["ssid"] in saved
        return r["nets"]

    def wifi_connect(self, ssid, password, save=True, timeout_ms=15000):
        """Join `ssid`. Returns {'result', 'ip', 'saved'}. The password is
        sent to the badge once and never printed, logged or returned."""
        code = (
            "import time\n"
            "from oreoWare import wifi as w\n"
            "_s=%(s)s\n"
            "_p=%(p)s\n"
            "try:\n"
            " w.auto_stop()\n"
            "except Exception:\n"
            " pass\n"
            "r=w.CONN_BUSY if w.connect_begin(_s,_p,%(t)d) else w.connect_poll()\n"
            "while r==w.CONN_BUSY:\n"
            " time.sleep_ms(200)\n"
            " r=w.connect_poll()\n"
            "ok=r==w.CONN_OK\n"
            "sv=False\n"
            "if ok and %(save)s:\n"
            " sv=bool(w.add_saved(_s,_p))\n"
            # connect_poll() marked it "last" before it was saved; mark it
            # again so the next boot joins it without scanning first.
            " try:\n"
            "  w._mark_last(_s)\n"
            " except Exception:\n"
            "  pass\n"
            "_p=None\n"
            "_e({'result':r,'ip':w.ip() if ok else None,'saved':sv})\n"
            % {"s": lit(ssid), "p": lit(password or ""), "t": int(timeout_ms),
               "save": "True" if save else "False"})
        return self.result(code, timeout=timeout_ms / 1000.0 + 15,
                           secrets=(password,) if password else ())

    def wifi_save(self, ssid, password, priority=10):
        r = self.result(
            "from oreoWare import wifi as w\n"
            "_e({'saved':bool(w.add_saved(%s,%s,%d))})\n"
            % (lit(ssid), lit(password or ""), int(priority)),
            secrets=(password,) if password else ())
        return r["saved"]

    def wifi_saved(self):
        """Saved networks, without passwords (they never leave the badge)."""
        r = self.result(
            "from oreoWare import wifi as w\n"
            "r=[]\n"
            "for n in w.list_saved():\n"
            " r.append({'ssid':n.get('ssid'),'priority':n.get('priority'),"
            "'metered':bool(n.get('metered')),'last':bool(n.get('last')),"
            "'open':not n.get('password')})\n"
            "_e({'saved':r})\n")
        return r["saved"]

    def wifi_forget(self, ssid):
        """Returns (removed, from_deploy) — from_deploy: the network is also
        in the deploy-time secrets and will be re-added at the next boot."""
        r = self.result(
            "from oreoWare import wifi as w\n"
            "d=False\n"
            "try:\n"
            " d=%(s)s in [n.get('ssid') for n in w._secrets_networks()]\n"
            "except Exception:\n"
            " pass\n"
            "_e({'removed':bool(w.remove_saved(%(s)s)),'deploy':d})\n" % {"s": lit(ssid)})
        return r["removed"], r["deploy"]

    def wifi_online(self, timeout_s=90):
        """Bring Wi-Fi up from the saved list (for App Store calls)."""
        return self.result(
            "from oreoWare import wifi as w\n"
            "ok=bool(w.is_connected())\n"
            "if not ok:\n"
            " try:\n"
            "  ok=bool(w.connect_from_config())\n"
            " except Exception as x:\n"
            "  print('[wifi]',x)\n"
            "_e({'online':ok,'ip':w.ip() if ok else None})\n", timeout=timeout_s)

    # ── apps (oreoOS.store) ──────────────────────────────────────────
    def apps(self):
        """{'installed': [...], 'catalogue': [...]} from flash (no network)."""
        return self.result(
            "import os\n"
            "from oreoOS import store as S\n"
            "inst=[]\n"
            "try:\n"
            " names=os.listdir('/apps')\n"
            "except OSError:\n"
            " names=[]\n"
            "for n in sorted(names):\n"
            " if n in S.HIDDEN_INSTALLED:\n"
            "  continue\n"
            " m=S.installed_manifest(n)\n"
            " if not m:\n"
            "  continue\n"
            " inst.append({'id':n,'name':m.get('name',n),'version':S.installed_version(n),"
            "'default':S.is_default(n)})\n"
            "cat=[]\n"
            "for e in S.catalogue()[0]:\n"
            " cat.append({'id':e['id'],'name':e['name'],'version':e['version'],"
            "'size':e['size'],'tagline':e['tagline'],'category':e['category'],"
            "'state':S.app_state(e)})\n"
            "_e({'installed':inst,'catalogue':cat})\n", timeout=30)

    def apps_refresh(self):
        r = self.result(
            "from oreoOS import store as S\n"
            "ok=S.refresh()\n"
            "_e({'ok':bool(ok),'error':S.last_error()})\n", timeout=60)
        return r["ok"], r.get("error") or ""

    def app_install(self, app_id, progress=None):
        def on_event(ev):
            if progress and "p" in ev:
                progress(ev["p"], ev.get("t") or 0)
        r = self.result(
            "from oreoOS import store as S\n"
            "def _cb(a,t,l):\n"
            " _e({'p':a,'t':t})\n"
            "ok,msg=S.install(%s,_cb)\n"
            "_e({'ok':bool(ok),'msg':msg})\n" % lit(app_id),
            timeout=90, on_event=on_event)
        return r["ok"], r["msg"]

    def app_remove(self, app_id):
        r = self.result(
            "from oreoOS import store as S\n"
            "ok,msg=S.uninstall(%s)\n"
            "_e({'ok':bool(ok),'msg':msg})\n" % lit(app_id), timeout=60)
        return r["ok"], r["msg"]

    # ── running code ─────────────────────────────────────────────────
    def run_source(self, source, on_output):
        """Run a script, streaming its output; no timeout."""
        self.connect()
        if isinstance(source, str):
            source = source.encode("utf-8")
        return self.link.exec(source, timeout=None, consumer=on_output)

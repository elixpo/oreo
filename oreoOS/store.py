"""App Store — remote catalogue of installable apps, fetched from
the project's GitHub repo and cached locally.

Listing source
==============
We hit the GitHub Contents API for the `apps_market/` directory of the
OreoOS repo and treat every subfolder containing a `main.py` + a
`manifest.json` as an installable entry. For each entry we cache:

    {dir, name, icon_url, author,  files: [{path, download_url, size}]}

The cache lives at `/store_cache.json` on flash. A press in the Store
app overwrites it with a fresh fetch — otherwise the in-memory copy
stays sticky for the OS session so navigating in / out of the app
doesn't re-spend the API budget.

Install
=======
`install(dir)` walks the cached `files` list, fetches each
`download_url`, and writes it to `apps/<dir>/<rel_path>`. Uninstall is
still local: `rm -rf apps/<dir>/`.

No-network behaviour
====================
If the cache exists, we surface it as the source of truth even when
WiFi is down. The UI shows a "stale" / "offline" pill so the user
knows they're looking at the last successful refresh.
"""

import gc
import os as _os
import time

try:
    import json as _json
except ImportError:
    _json = None

# Raw-socket HTTP. We bypass urequests because its `timeout=` flag on
# this MicroPython 1.28 build only covers the connect, not the body
# read — which lets a slow GitHub edge wedge the OS run loop for
# minutes. socket.settimeout() applies to every recv() so the timeout
# is enforced end-to-end. Same fix we'll back-port to ota.py later.
try:
    import socket as _socket
    import ssl    as _ssl
    _RAW_OK = True
except ImportError:
    _RAW_OK = False


def _bc(msg):
    """One-line USB-CDC breadcrumb — tail with `mpremote connect ...`
    while the Store app is open to see exactly where a hang lands."""
    try:
        print("[store] " + msg)
    except Exception:
        pass


def _http_get(url, accept_raw=False, timeout_s=4):
    """Tiny GET that returns the body as bytes (or None on failure).

    `accept_raw=True` flips the Accept header to application/vnd.github.raw
    so file fetches return the raw file body instead of JSON-wrapped
    base64. Used by the install path.
    """
    if not _RAW_OK:
        return None
    # Parse https://host[:port]/path
    if not url.startswith("https://"):
        return None
    rest = url[len("https://"):]
    slash = rest.find("/")
    if slash < 0:
        host, path = rest, "/"
    else:
        host, path = rest[:slash], rest[slash:]
    port = 443
    if ":" in host:
        host, p = host.split(":", 1)
        try: port = int(p)
        except ValueError: port = 443

    accept = ("application/vnd.github.raw" if accept_raw
              else "application/vnd.github+json")

    s = None
    raw = None
    # Wallclock guard — even if a single recv stalls a few times in
    # quick succession, the outer loop notices we've blown the budget
    # and bails. Belt-and-suspenders next to settimeout.
    deadline = None
    try:
        import time as _t
        deadline = _t.ticks_add(_t.ticks_ms(), int(timeout_s * 1000) + 500)
    except Exception:
        pass

    auth_hdr = ""
    try:
        from oreoOS.config import GH_TOKEN as _TOK
        if _TOK:
            auth_hdr = "Authorization: Bearer " + _TOK + "\r\n"
    except Exception:
        pass

    try:
        _bc("  dns " + host)
        addr = _socket.getaddrinfo(host, port)[0][-1]
        _bc("  connect " + host + ":" + str(port))
        raw = _socket.socket()
        raw.settimeout(timeout_s)
        raw.connect(addr)
        _bc("  ssl handshake")
        s = _ssl.wrap_socket(raw, server_hostname=host)
        # CRITICAL: settimeout BEFORE connect applies to the raw
        # socket, but MicroPython's SSLSocket wraps it and doesn't
        # always inherit the timeout — set again on the wrapped
        # socket so subsequent .read() calls actually honour it.
        try:
            s.settimeout(timeout_s)
        except Exception:
            pass

        req = (
            "GET %s HTTP/1.1\r\n"
            "Host: %s\r\n"
            "User-Agent: %s\r\n"
            "Accept: %s\r\n"
            "Accept-Encoding: identity\r\n"
            "%s"
            "Connection: close\r\n\r\n"
        ) % (path, host, USER_AGENT, accept, auth_hdr)
        _bc("  write request")
        s.write(req.encode())

        _bc("  read body")
        buf = bytearray()
        while True:
            # Wallclock check — if we've blown our budget, bail no
            # matter what settimeout says.
            try:
                import time as _t2
                if deadline is not None and \
                   _t2.ticks_diff(deadline, _t2.ticks_ms()) <= 0:
                    _bc("  read deadline blown after %d bytes" % len(buf))
                    break
            except Exception:
                pass
            try:
                chunk = s.read(2048)
            except Exception as e:
                _bc("  read err: " + str(e))
                break
            if not chunk:
                break
            buf.extend(chunk)
            if len(buf) > 256 * 1024:
                break
    except Exception as e:
        _bc("http_get FAIL %s: %s" % (host, e))
        return None
    finally:
        for _h in (s, raw):
            try:
                if _h is not None:
                    _h.close()
            except Exception:
                pass

    # Split off the response head — body starts after \r\n\r\n.
    head_end = buf.find(b"\r\n\r\n")
    if head_end < 0:
        return None
    head = bytes(buf[:head_end])
    body = bytes(buf[head_end + 4:])

    # Parse the status line for breadcrumbs + 200-check.
    status = 0
    line0  = head.split(b"\r\n", 1)[0]
    parts  = line0.split(b" ", 2)
    if len(parts) >= 2:
        try: status = int(parts[1])
        except ValueError: status = 0
    if status != 200:
        _bc("http_get %s -> HTTP %d" % (host, status))
        return None

    # If the response was chunked (rare for github.com but defensive),
    # decode chunks. We detect it via Transfer-Encoding header.
    if b"\r\ntransfer-encoding: chunked" in (b"\r\n" + head.lower()):
        body = _dechunk(body)

    return body


def _dechunk(body):
    out = bytearray()
    i   = 0
    while i < len(body):
        nl = body.find(b"\r\n", i)
        if nl < 0:
            break
        try:
            n = int(body[i:nl].split(b";")[0], 16)
        except Exception:
            break
        i = nl + 2
        if n == 0:
            break
        out.extend(body[i:i + n])
        i += n + 2
    return bytes(out)


# ── tunables ────────────────────────────────────────────────────────────

STORE_REPO   = "elixpo/oreo"
# Branch/tag/sha on the repo to pull the catalogue from. Defaults to
# `main`; override via oreoOS/config.py `STORE_REF = "feat/app-market"`
# while apps_market/ hasn't landed on main yet, otherwise the API
# returns 404 and the page shows an empty catalogue.
try:
    from oreoOS.config import STORE_REF as _CFG_REF
    STORE_REF = _CFG_REF
except Exception:
    STORE_REF = "main"
MARKET_PATH  = "apps_market"
CACHE_PATH   = "/store_cache.json"

T_API        = 6        # seconds — GitHub Contents API call
T_FILE       = 25       # seconds — raw-file download (per file)

USER_AGENT   = "OreoBadge-Store"
APPS_DIR     = "apps"


# In-memory mirror of the catalogue. Loaded lazily on first access.
_catalogue       = None
_cache_ms        = 0      # ticks_ms at last successful refresh
_last_refresh_ok = None   # True / False / None — never-tried | succeeded | failed
_last_error      = ""     # human-readable summary for the page


# ── filesystem helpers ──────────────────────────────────────────────────

def _exists(path):
    try:
        _os.stat(path); return True
    except OSError:
        return False


def _isdir(path):
    try:
        return (_os.stat(path)[0] & 0x4000) != 0
    except OSError:
        return False


def _ensure_dir(path):
    """mkdir -p — tolerates already-exists silently."""
    parts = path.split("/")
    cur = ""
    for p in parts:
        if not p:
            continue
        cur = cur + "/" + p if cur else p
        try:
            _os.mkdir(cur)
        except OSError:
            pass


def _rm_tree(path):
    """rm -rf — swallows errors so a partial uninstall doesn't hang."""
    try:
        for f in _os.listdir(path):
            child = path + "/" + f
            if _isdir(child):
                _rm_tree(child)
            else:
                try: _os.remove(child)
                except OSError: pass
        try: _os.rmdir(path)
        except OSError: pass
    except OSError:
        pass


# ── GitHub API wrappers ─────────────────────────────────────────────────

def _api(path):
    """GET https://api.github.com/repos/<repo>/contents/<path>?ref=<ref>.

    Records the last error into the module-level `_last_error` slot so
    the UI can surface a real reason ("404 on main — apps_market not
    merged?", "timeout", etc.) instead of a generic empty list.
    """
    global _last_error
    if not _RAW_OK or _json is None:
        _last_error = "no socket / json"
        return None
    url = ("https://api.github.com/repos/%s/contents/%s?ref=%s"
           % (STORE_REPO, path, STORE_REF))
    _bc("API GET " + path + "@" + STORE_REF)
    body = _http_get(url, accept_raw=False, timeout_s=T_API)
    if body is None:
        _last_error = "api %s@%s timeout/error" % (path, STORE_REF)
        return None
    try:
        data = _json.loads(body.decode("utf-8"))
    except Exception as e:
        _last_error = "api parse: " + str(e)[:32]
        return None
    _bc("API OK %s (%d entries)" %
        (path, len(data) if isinstance(data, list) else 1))
    return data


def _walk(path):
    """Recursive list of every FILE under `path` in the repo. Returns
    [{path, download_url, size}] — used at install time."""
    out = []
    items = _api(path)
    if not isinstance(items, list):
        return out
    for it in items:
        if it.get("type") == "dir":
            out.extend(_walk(it["path"]))
        elif it.get("type") == "file":
            out.append({
                "path":         it["path"],
                "download_url": it.get("download_url") or "",
                "size":         it.get("size", 0),
            })
    return out


def _fetch_manifest(app_path):
    """Read the manifest.json for a single market app via the API."""
    if _json is None:
        return {}
    url = ("https://api.github.com/repos/%s/contents/%s/manifest.json?ref=%s"
           % (STORE_REPO, app_path, STORE_REF))
    _bc("manifest GET " + app_path)
    body = _http_get(url, accept_raw=True, timeout_s=T_API)
    if body is None:
        return {}
    try:
        return _json.loads(body.decode("utf-8"))
    except Exception:
        return {}


# ── catalogue lifecycle ─────────────────────────────────────────────────

def _load_cache_from_disk():
    """Re-hydrate _catalogue from the on-flash JSON cache, if any."""
    global _catalogue, _cache_ms
    if not _exists(CACHE_PATH) or _json is None:
        return False
    try:
        with open(CACHE_PATH) as f:
            blob = _json.loads(f.read())
        _catalogue = blob.get("apps", []) or []
        _cache_ms  = int(blob.get("fetched_ms", 0))
        return True
    except Exception:
        return False


def _save_cache_to_disk():
    if _json is None:
        return
    try:
        with open(CACHE_PATH, "w") as f:
            f.write(_json.dumps({
                "fetched_ms": _cache_ms,
                "apps":       _catalogue or [],
            }))
    except Exception:
        pass


def refresh(force=False):
    """Pull a fresh catalogue from GitHub. Returns the new list (which
    may be empty if the network failed). On any failure, the in-memory
    cache is left untouched so the UI can fall back to stale entries.

    `force=True` is the API the Store app calls when the user presses
    A. Without force, repeated calls inside the same OS session reuse
    the in-memory copy.
    """
    global _catalogue, _cache_ms, _last_refresh_ok, _last_error
    if not force and _catalogue is not None:
        return _catalogue

    # WiFi gate — same defensive check as the OTA path. If WiFi isn't
    # up, we don't even try to call the API; the local cache is the
    # only thing we can show.
    try:
        from oreoWare import wifi
        if not wifi.is_connected():
            if _catalogue is None:
                _load_cache_from_disk()
            _last_refresh_ok = False
            _last_error      = "wifi down"
            return _catalogue or []
    except Exception:
        pass

    _last_error = ""
    listing = _api(MARKET_PATH)
    if not isinstance(listing, list):
        # API call failed (_api logged the reason into _last_error).
        # Fall back to disk cache so the user still sees something
        # rather than an empty page; flag the attempt as failed so the
        # UI can show an ERROR pill rather than a clean state.
        if _catalogue is None:
            _load_cache_from_disk()
        _last_refresh_ok = False
        return _catalogue or []

    # Single-call catalogue. Display name + icon + author come from the
    # manifest, fetched lazily by get_details() when the user opens an
    # app's detail page. The previous N+1 pattern was the source of
    # "stuck on LOADING" — any single GET that hung on body-read would
    # take the whole catalogue down.
    fresh = []
    for it in listing:
        if it.get("type") != "dir":
            continue
        name_dir = it.get("name", "")
        app_path = it.get("path", "")
        if not name_dir or not app_path:
            continue
        fresh.append({
            "dir":    name_dir,
            "name":   name_dir,    # placeholder; details page upgrades this
            "icon":   None,
            "author": None,
            "path":   app_path,
        })

    _catalogue       = fresh
    _last_refresh_ok = True
    _details_cache.clear()
    try:
        _cache_ms = time.ticks_ms()
    except Exception:
        _cache_ms = 0
    _save_cache_to_disk()
    return _catalogue


def last_refresh_ok():
    """Tri-state: True / False / None (never tried this boot)."""
    return _last_refresh_ok


def last_error():
    return _last_error


# Per-app detail cache so repeatedly opening + closing the details page
# for the same app doesn't re-hit GitHub. Cleared by refresh().
_details_cache = {}


def get_details(name_dir):
    """Lazy fetch of the manifest + file listing for one market app.

    Returns a dict:
        {
            "name":       human display name from manifest, fallback dir
            "icon":       manifest 'icon' field (filename) or None
            "author":     manifest 'author' field or None
            "description": manifest 'description' field or "" (if any)
            "files":      [{path, download_url, size}, ...] for install()
            "bytes":      total bytes the install would download
            "ok":         True iff both API calls returned cleanly
        }

    Cached in-memory per OS session; the next refresh() invalidates
    every entry so a contributor pushing a manifest change can be
    picked up without rebooting.
    """
    if name_dir in _details_cache:
        return _details_cache[name_dir]
    cat = list_market()
    entry = None
    for e in cat:
        if e["dir"] == name_dir:
            entry = e
            break
    if not entry:
        return {"ok": False}

    manifest = _fetch_manifest(entry["path"])
    files    = _walk(entry["path"])
    total    = sum(f.get("size", 0) for f in files)
    out = {
        "name":         manifest.get("name",        name_dir),
        "icon":         manifest.get("icon",        None),
        "author":       manifest.get("author",      None),
        "description":  manifest.get("description", "") or "",
        "files":        files,
        "bytes":        total,
        "ok":           bool(manifest) and bool(files),
    }
    _details_cache[name_dir] = out
    # Also patch the catalogue entry so the list view picks up the
    # nicer display name on the next paint.
    if manifest:
        entry["name"]   = out["name"]
        entry["icon"]   = out["icon"]
        entry["author"] = out["author"]
    return out


# When refresh() succeeds we wipe the per-app details cache so a
# contributor pushing a manifest update isn't masked by stale cache.
def _invalidate_details():
    _details_cache.clear()


def list_market():
    """Read-only listing for the UI. Returns the in-memory catalogue
    (loading the disk cache on first call) and tags each entry with
    its current install state."""
    global _catalogue
    if _catalogue is None:
        if not _load_cache_from_disk():
            _catalogue = []
    for e in _catalogue:
        e["installed"] = is_installed(e["dir"])
    return _catalogue


def cache_age_ms():
    """ticks_diff from the last successful refresh, or None if no
    cache has been populated this boot."""
    if not _cache_ms:
        return None
    try:
        return time.ticks_diff(time.ticks_ms(), _cache_ms)
    except Exception:
        return None


# ── install / uninstall ─────────────────────────────────────────────────

def is_installed(name):
    """An app is 'installed' iff /apps/<name>/main.py exists."""
    return _exists(APPS_DIR + "/" + name + "/main.py")


def install(name):
    """Download every file under `apps_market/<name>/` on GitHub and
    write it to `apps/<name>/<relative>`. Returns True iff main.py
    landed cleanly.

    Network and storage errors are non-fatal per-file; the function
    keeps going so the user gets a partial install rather than a
    nothing-at-all failure (they can hit A again to retry).
    """
    if not _RAW_OK:
        return False
    # Reuse the file tree the details page already walked. Cheap when
    # the user clicks Install from the details page (no extra API
    # calls); falls back to a fresh walk for any caller that bypasses
    # the details flow.
    details = get_details(name)
    if not details.get("ok"):
        return False
    files = details.get("files") or []
    if not files:
        return False
    cat = list_market()
    entry = None
    for e in cat:
        if e["dir"] == name:
            entry = e
            break
    if not entry:
        return False

    root_prefix = entry["path"] + "/"
    target_root = APPS_DIR + "/" + name

    for f in files:
        rel = f["path"]
        if not rel.startswith(root_prefix):
            continue
        rel = rel[len(root_prefix):]
        dst = target_root + "/" + rel
        parent = dst.rsplit("/", 1)[0] if "/" in dst else ""
        if parent:
            _ensure_dir(parent)
        _bc("install GET " + rel)
        body = _http_get(f["download_url"], accept_raw=False,
                         timeout_s=T_FILE)
        if body is None:
            continue
        try:
            with open(dst, "wb") as out:
                out.write(body)
        except Exception:
            pass
        gc.collect()

    return is_installed(name)


def uninstall(name):
    """rm -rf /apps/<name>/. The remote catalogue is untouched."""
    dst = APPS_DIR + "/" + name
    if not _exists(dst):
        return True
    _rm_tree(dst)
    return not _exists(dst)

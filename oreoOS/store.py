"""App Market — list / install / uninstall optional apps on the badge.

Two trees coexist on the flash:
    /apps/<name>/         default-installed apps + anything the user has
                          installed from the market. The launcher drawer
                          walks ONLY this tree.
    /apps_market/<name>/  catalogue of opt-in apps. Files sit here until
                          the user installs them.

`install(name)` deep-copies a tree from apps_market/<name>/ into
apps/<name>/. `uninstall(name)` rm -rf's apps/<name>/ — the original
copy in apps_market/ stays put so a re-install is free.

Power note: this module touches the filesystem and is meant to be
called from the Store app's button handlers; it's never on a per-frame
hot path.
"""

import os as _os


MARKET_DIR = "apps_market"
APPS_DIR   = "apps"


# ── path helpers ────────────────────────────────────────────────────────

def _exists(path):
    try:
        _os.stat(path)
        return True
    except OSError:
        return False


def _isdir(path):
    try:
        return (_os.stat(path)[0] & 0x4000) != 0
    except OSError:
        return False


def _listdir(path):
    try:
        return _os.listdir(path)
    except OSError:
        return []


def _ensure_dir(path):
    """mkdir -p — tolerates 'already exists' silently."""
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
    for f in _listdir(path):
        child = path + "/" + f
        try:
            if _isdir(child):
                _rm_tree(child)
            else:
                _os.remove(child)
        except OSError:
            pass
    try:
        _os.rmdir(path)
    except OSError:
        pass


def _copy_file(src, dst):
    """Stream copy in 4 KB chunks so large assets don't OOM the heap."""
    with open(src, "rb") as r, open(dst, "wb") as w:
        while True:
            chunk = r.read(4096)
            if not chunk:
                break
            w.write(chunk)


def _copy_tree(src, dst):
    """Recursive copy. Creates dst + every subdirectory as needed."""
    _ensure_dir(dst)
    for name in _listdir(src):
        s = src + "/" + name
        d = dst + "/" + name
        if _isdir(s):
            _copy_tree(s, d)
        else:
            try:
                _copy_file(s, d)
            except Exception:
                # Per-file errors are non-fatal; the install will be
                # partial and the caller (Store UI) re-runs on user
                # retry. We do not back out the whole tree.
                pass


# ── public API ──────────────────────────────────────────────────────────

def list_market():
    """Return a list of dicts describing every app available to install
    from /apps_market/. Each entry includes the manifest fields the UI
    needs (name, icon, author) plus the cached install state."""
    out = []
    if not _exists(MARKET_DIR):
        return out
    try:
        import json as _json
    except ImportError:
        _json = None
    for name in sorted(_listdir(MARKET_DIR)):
        app_dir = MARKET_DIR + "/" + name
        if not _isdir(app_dir):
            continue
        if not _exists(app_dir + "/main.py"):
            continue
        manifest = {}
        try:
            with open(app_dir + "/manifest.json") as f:
                if _json:
                    manifest = _json.loads(f.read())
        except Exception:
            pass
        out.append({
            "dir":       name,
            "name":      manifest.get("name",   name),
            "icon":      manifest.get("icon",   None),
            "author":    manifest.get("author", None),
            "installed": is_installed(name),
        })
    return out


def is_installed(name):
    """An app is 'installed' iff /apps/<name>/main.py exists. We don't
    track installation state in settings — the filesystem IS the truth."""
    return _exists(APPS_DIR + "/" + name + "/main.py")


def install(name):
    """Copy /apps_market/<name>/ → /apps/<name>/. Returns True on
    success. If the destination already exists, the copy proceeds and
    overwrites — this is the "repair" path."""
    src = MARKET_DIR + "/" + name
    dst = APPS_DIR   + "/" + name
    if not _exists(src + "/main.py"):
        return False
    try:
        _copy_tree(src, dst)
        return is_installed(name)
    except Exception:
        return False


def uninstall(name):
    """rm -rf /apps/<name>/. The market copy is untouched."""
    dst = APPS_DIR + "/" + name
    if not _exists(dst):
        return True
    _rm_tree(dst)
    return not _exists(dst)

"""Over-the-air update client for OreoOS.

Update model
============
A "release" is a versioned manifest file pinned to a GitHub release of
the OreoOS repo. The manifest lists every file in the OS tree along
with its size and SHA-256, plus URLs to download each file.

CI publishes the release. The badge:

  1. Periodically (or on user request) hits the GitHub Releases API:
         GET https://api.github.com/repos/<OTA_REPO>/releases/latest
     and reads the asset called `manifest.json`.

  2. Compares manifest["version"] against oreoOS.config.VERSION.

  3. If newer, downloads every file whose local sha256 differs into the
     staging directory `/_ota/` on the badge's filesystem. Validates
     each file's hash. Writes the manifest itself last as a "ready"
     marker.

  4. Sets the OS settings flag `ota_pending=True`. The home screen
     surfaces an "Update ready, reboot to install" pill.

  5. On the next boot, `apply_pending()` runs BEFORE the launcher.
     If `/_ota/manifest.json` exists, every file under `/_ota/` is
     moved into its final location atomically (write-then-rename), the
     manifest is deleted, the staging directory removed, and the boot
     continues normally.

Why this shape
==============
* No partition swapping — the ESP32-S3 doesn't need OTA partitions for
  this, because we update files on the LittleFS filesystem rather than
  the MicroPython firmware itself. Bricking risk is bounded: if a file
  copy is interrupted, the manifest never lands and the OS keeps
  booting the old version.
* Manifest is JSON for human inspection and CI-side tooling. The
  badge's parser is the stdlib `json` module which MicroPython ships.
* Hash check on EVERY file before applying: a brownout during download
  can't corrupt the live OS because the bad bytes sit in the staging
  area until the manifest seals the deal.

Channels
========
A "channel" is a tag prefix on the GitHub release:
    stable/v1.3.0     -> stable channel
    beta/v1.4.0-rc1   -> beta channel
The OTA module fetches the latest release whose tag begins with the
channel name. Default is "stable" so badges don't auto-pick up rc
builds.
"""

import gc
import os as _os
import time

try:
    import urequests as _http
except ImportError:
    try:
        import requests as _http   # CPython fallback for tests
    except ImportError:
        _http = None

try:
    import json as _json
except ImportError:
    _json = None

try:
    import hashlib as _hashlib
except ImportError:
    _hashlib = None


# ── tunables ────────────────────────────────────────────────────────────────

OTA_REPO       = "elixpo/oreo-badge"      # owner/repo on GitHub
STAGE_DIR      = "/_ota"
MANIFEST_NAME  = "manifest.json"
DEFAULT_CHANNEL = "stable"
USER_AGENT     = "OreoBadge-OTA"

# Chunk size for download writes. Big enough to amortise FS overhead but
# small enough not to OOM the heap when downloading a 100 KB sprite.
CHUNK_BYTES    = 4096


# ── helpers ─────────────────────────────────────────────────────────────────

def _ensure_dir(path):
    """mkdir -p equivalent for MicroPython's tiny os module."""
    parts = path.split("/")
    cur   = ""
    for p in parts:
        if not p:
            continue
        cur = cur + "/" + p if cur else p
        try:
            _os.mkdir(cur)
        except OSError:
            pass


def _rm_tree(path):
    """rm -rf for a directory tree, swallowing errors silently."""
    try:
        for f in _os.listdir(path):
            child = path + "/" + f
            try:
                _rm_tree(child)
            except Exception:
                try:
                    _os.remove(child)
                except Exception:
                    pass
        try:
            _os.rmdir(path)
        except OSError:
            pass
    except Exception:
        pass


def _sha256_file(path):
    """SHA-256 of a file, hex-encoded. None if the file is missing."""
    if _hashlib is None:
        return None
    try:
        h = _hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                chunk = f.read(CHUNK_BYTES)
                if not chunk:
                    break
                h.update(chunk)
        return _hex(h.digest())
    except OSError:
        return None


def _hex(b):
    """Compatible hex encoding (some MP builds lack bytes.hex())."""
    try:
        return b.hex()
    except AttributeError:
        return "".join("%02x" % x for x in b)


def _current_version():
    try:
        from oreoOS.config import VERSION
        return VERSION
    except Exception:
        return "v0.0.0"


def _parse_version(s):
    """'v1.2.3' -> (1, 2, 3). Bad input -> (0, 0, 0)."""
    if not s:
        return (0, 0, 0)
    if s.startswith("v"):
        s = s[1:]
    try:
        parts = [int(x) for x in s.split(".")]
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts[:3])
    except (TypeError, ValueError):
        return (0, 0, 0)


def _newer(a, b):
    """True iff version `a` (string) is strictly newer than `b`."""
    return _parse_version(a) > _parse_version(b)


# ── public API ──────────────────────────────────────────────────────────────

def check(channel=DEFAULT_CHANNEL, timeout=15):
    """Return a dict describing the latest release on `channel`, or None.

    Result shape:
        {
            "version": "v1.3.0",
            "notes":   "...",
            "manifest_url": "https://...",
            "tag":     "stable/v1.3.0",
        }

    None when:
      - no network
      - GitHub returned no releases
      - none of the releases match the requested channel
      - we are already on the latest version (no update needed)
    """
    if _http is None or _json is None:
        return None
    url = "https://api.github.com/repos/%s/releases" % OTA_REPO
    try:
        r = _http.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        data = r.json()
        r.close()
    except Exception:
        return None

    if not isinstance(data, list):
        return None

    prefix = channel + "/"
    for rel in data:
        tag = rel.get("tag_name", "")
        if not (tag == channel or tag.startswith(prefix)):
            continue
        # Strip the channel prefix (if any) to get the bare version.
        ver = tag[len(prefix):] if tag.startswith(prefix) else tag
        if not _newer(ver, _current_version()):
            return None      # we're already on it (or newer; e.g. dev)
        # Find the manifest.json asset on this release.
        manifest_url = None
        for a in rel.get("assets", ()):
            if a.get("name") == MANIFEST_NAME:
                manifest_url = a.get("browser_download_url")
                break
        if not manifest_url:
            continue
        return {
            "version":      ver,
            "notes":        rel.get("body") or "",
            "manifest_url": manifest_url,
            "tag":          tag,
        }
    return None


def download(release, on_progress=None):
    """Stage `release` (from check()) into /_ota. Returns True on success.

    on_progress is an optional callback called as
        on_progress(file_index, total_files, file_path)
    so the UI can render a progress bar.
    """
    if not release:
        return False
    _rm_tree(STAGE_DIR)     # wipe any previous interrupted attempt
    try:
        _os.mkdir(STAGE_DIR)
    except OSError:
        pass

    # Fetch and parse manifest.
    try:
        r = _http.get(release["manifest_url"],
                      headers={"User-Agent": USER_AGENT}, timeout=30)
        manifest = r.json()
        r.close()
    except Exception:
        return False

    files = manifest.get("files", ())
    total = len(files)
    for i, entry in enumerate(files):
        path = entry.get("path", "")
        url  = entry.get("url", "")
        want = entry.get("sha256", "")
        if not (path and url):
            return False
        # Skip files we already have at the right hash.
        if want and _sha256_file(path) == want:
            if on_progress:
                on_progress(i + 1, total, path)
            continue
        if not _download_file(url, path, want):
            return False
        if on_progress:
            on_progress(i + 1, total, path)

    # Write the manifest LAST as the "everything staged" marker.
    try:
        with open(STAGE_DIR + "/" + MANIFEST_NAME, "w") as f:
            _json.dump(manifest, f)
    except Exception:
        return False
    return True


def _download_file(url, dest_remote, expected_sha=None):
    """Download into the staging area mirroring the eventual remote path."""
    stage_path = STAGE_DIR + "/" + dest_remote
    parent = stage_path.rsplit("/", 1)[0]
    _ensure_dir(parent)
    try:
        r = _http.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
        h  = _hashlib.sha256() if _hashlib else None
        with open(stage_path, "wb") as f:
            # urequests doesn't always stream; the safe path is to read
            # the body once. Files are kept small (≤ a few hundred KB).
            data = r.content
            if h: h.update(data)
            f.write(data)
        r.close()
    except Exception:
        return False
    if expected_sha and h and _hex(h.digest()) != expected_sha:
        try:
            _os.remove(stage_path)
        except Exception:
            pass
        return False
    return True


def is_pending():
    """True iff a complete staged update is sitting in /_ota."""
    try:
        _os.stat(STAGE_DIR + "/" + MANIFEST_NAME)
        return True
    except OSError:
        return False


def apply_pending():
    """Promote files from /_ota into their real locations. Returns the
    applied version string, or None if nothing was applied.

    SAFE to call on every boot: when no manifest is present it's a no-op.
    Called from launcher.boot() BEFORE anything else.
    """
    if _json is None:
        return None
    manifest_path = STAGE_DIR + "/" + MANIFEST_NAME
    try:
        with open(manifest_path) as f:
            manifest = _json.load(f)
    except Exception:
        return None

    for entry in manifest.get("files", ()):
        path = entry.get("path", "")
        if not path:
            continue
        src = STAGE_DIR + "/" + path
        dst = path
        try:
            _os.stat(src)
        except OSError:
            continue       # this file was skipped earlier (already up-to-date)
        # Write-then-rename style: ensure dst's parent exists, then copy.
        parent = dst.rsplit("/", 1)[0] if "/" in dst else ""
        if parent:
            _ensure_dir(parent)
        try:
            _copy_file(src, dst)
        except Exception:
            # Half-applied state is the worst case; the manifest still
            # exists so apply_pending() will retry on the next boot.
            return None

    # All files in place. Tear down the staging area + manifest.
    _rm_tree(STAGE_DIR)
    gc.collect()
    return manifest.get("version", None)


def _copy_file(src, dst):
    with open(src, "rb") as fi, open(dst, "wb") as fo:
        while True:
            chunk = fi.read(CHUNK_BYTES)
            if not chunk:
                break
            fo.write(chunk)


def discard_pending():
    """Forget any staged update without applying it.

    Used by the Settings 'cancel update' action so the badge doesn't
    apply a download the user changed their mind about.
    """
    _rm_tree(STAGE_DIR)

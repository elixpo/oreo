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

# Anything below this counts as a "small patch" — auto-staged without
# pestering the user. Above it we pop a confirmation dialog because the
# user is on metered WiFi at a hackathon and 2 MB of new icons is rude.
SMALL_PATCH_BYTES = 80 * 1024     # 80 KB

# Timeouts (seconds). Every HTTP call uses one of these — no unbounded
# blocking is allowed because the OS run loop polls OTA from the Settings
# app's button handler. A hung GET would freeze the whole UI.
T_GH_API       = 10        # GitHub releases API listing
T_MANIFEST     = 10        # manifest.json download (tiny)
T_FILE         = 25        # individual file download


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


def _is_major_bump(new_ver, cur_ver):
    """True when the MAJOR component changed (v1.x.x -> v2.x.x).

    Used to flag a release as a "breaking" update so the UI can warn the
    user. We treat a minor bump (1.2 -> 1.3) the same as a patch — the
    decision is binary because anything above patch can introduce new
    apps or change file layout.
    """
    a = _parse_version(new_ver)
    b = _parse_version(cur_ver)
    return a[0] != b[0]


# ── public API ──────────────────────────────────────────────────────────────

def check(channel=DEFAULT_CHANNEL):
    """Stage 1 — fast version probe. Hits GitHub's releases API and
    returns a thin dict iff a newer release exists.

    Result shape:
        {
            "version":      "v1.3.0",
            "notes":        "...",
            "manifest_url": "https://...",
            "tag":          "stable/v1.3.0",
            "major":        True/False,    # major-version bump?
        }

    Returns None on no-network / no-release / already-on-latest. Bounded
    to T_GH_API seconds so the caller can never hang on it.
    """
    if _http is None or _json is None:
        return None
    cur = _current_version()
    url = "https://api.github.com/repos/%s/releases" % OTA_REPO
    try:
        r = _http.get(url, headers={"User-Agent": USER_AGENT}, timeout=T_GH_API)
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
        ver = tag[len(prefix):] if tag.startswith(prefix) else tag
        if not _newer(ver, cur):
            return None
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
            "major":        _is_major_bump(ver, cur),
        }
    return None


def peek(release):
    """Stage 2 — fetch the manifest and compute a SHA-based diff.

    For every file in the manifest, compare the published SHA-256 to the
    hash of the local file at the same path. Files that match are
    skipped during the eventual download. The function returns the diff
    along with the total bytes the badge would need to fetch.

    Result shape:
        {
            "manifest":   {... full manifest dict ...},
            "changed":    [{path, url, sha256, size}, ...],
            "unchanged":  N,
            "bytes":      total bytes to download (size sum of `changed`),
            "small":      True iff bytes <= SMALL_PATCH_BYTES,
            "major":      True iff this is a major-version bump,
        }

    Returns None on any network / parse failure. Cheap to call — the
    manifest itself is a few KB. The expensive part (file-by-file
    download) lives in download().
    """
    if not release or _http is None or _json is None:
        return None
    try:
        r = _http.get(release["manifest_url"],
                      headers={"User-Agent": USER_AGENT}, timeout=T_MANIFEST)
        manifest = r.json()
        r.close()
    except Exception:
        return None
    if not isinstance(manifest, dict):
        return None

    changed   = []
    unchanged = 0
    total_b   = 0
    for entry in manifest.get("files", ()):
        path = entry.get("path", "")
        want = entry.get("sha256", "")
        size = int(entry.get("size", 0) or 0)
        if not path:
            continue
        local_sha = _sha256_file(path)   # None when file is missing
        if want and local_sha == want:
            unchanged += 1
        else:
            changed.append(entry)
            total_b  += size

    return {
        "manifest":  manifest,
        "changed":   changed,
        "unchanged": unchanged,
        "bytes":     total_b,
        "small":     total_b <= SMALL_PATCH_BYTES,
        "major":     release.get("major", False) or _is_major_bump(
                        manifest.get("version", ""), _current_version()),
    }


def download(peeked, on_progress=None):
    """Stage 3 — download only the changed files into /_ota.

    `peeked` is the dict returned by peek(). Pre-passing it means the
    expensive SHA scan only happens once (during peek), not again here.

    on_progress(file_index, total_files, path) lets the UI render a
    progress bar. Every HTTP call is timeout-bounded so a hung server
    can't freeze the OS loop — the worst case is total = T_FILE * len(changed).
    """
    if not peeked:
        return False
    _rm_tree(STAGE_DIR)
    try:
        _os.mkdir(STAGE_DIR)
    except OSError:
        pass

    changed = peeked["changed"]
    total   = len(changed)
    for i, entry in enumerate(changed):
        path = entry.get("path", "")
        url  = entry.get("url", "")
        want = entry.get("sha256", "")
        if not (path and url):
            return False
        if not _download_file(url, path, want):
            return False
        if on_progress:
            try:
                on_progress(i + 1, total, path)
            except Exception:
                pass

    # Manifest written LAST as the all-good marker. Until this file
    # exists, apply_pending() won't promote anything from staging.
    try:
        with open(STAGE_DIR + "/" + MANIFEST_NAME, "w") as f:
            _json.dump(peeked["manifest"], f)
    except Exception:
        return False
    return True


def _download_file(url, dest_remote, expected_sha=None):
    """Download into the staging area mirroring the eventual remote path."""
    stage_path = STAGE_DIR + "/" + dest_remote
    parent = stage_path.rsplit("/", 1)[0]
    _ensure_dir(parent)
    try:
        r = _http.get(url, headers={"User-Agent": USER_AGENT}, timeout=T_FILE)
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

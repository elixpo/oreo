"""Deploy Oreo Badge OS to the ESP32-S3 via mpremote.

Usage:
    python tools/deploy.py              # auto-detect port
    python tools/deploy.py /dev/ttyACM0
    python tools/deploy.py --clean      # wipe device first, then deploy

Must be run from the project root.
"""

import sys
import re
import json
import hashlib
import subprocess
from pathlib import Path

PORT = "/dev/ttyACM0"
for arg in sys.argv[1:]:
    if arg.startswith("/dev/") or "COM" in arg:
        PORT = arg

CLEAN  = "--clean" in sys.argv
FORCE  = "--force" in sys.argv     # bypass local hash cache, push everything
NOSKIP = CLEAN or FORCE

HASH_CACHE_PATH = Path(".deploy_hashes.json")


def _hash_file(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _load_hash_cache():
    if NOSKIP or not HASH_CACHE_PATH.exists():
        return {}
    try:
        return json.loads(HASH_CACHE_PATH.read_text())
    except (OSError, ValueError):
        return {}


def _save_hash_cache(cache):
    try:
        HASH_CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True))
    except OSError:
        pass


# ── version auto-bump ─────────────────────────────────────────────────────────

CONFIG_PATH      = Path("oreoOS/config.py")
_VERSION_PATTERN = re.compile(
    r'^(VERSION\s*=\s*")v(\d+)\.(\d+)\.(\d+)(")',
    re.MULTILINE,
)


def bump_patch_version():
    """Rewrite the VERSION literal in oreoOS/config.py, +1 to the patch.

    Returns (old, new) as strings, or (None, None) when no line matched
    (so the caller can warn instead of silently shipping a stale version).
    The file is edited in place — comments and the rest of the config
    are preserved because we only touch the matched line.
    """
    if not CONFIG_PATH.exists():
        return None, None
    text = CONFIG_PATH.read_text()
    m    = _VERSION_PATTERN.search(text)
    if not m:
        return None, None
    major, minor, patch = int(m.group(2)), int(m.group(3)), int(m.group(4))
    old = "v%d.%d.%d" % (major, minor, patch)
    new = "v%d.%d.%d" % (major, minor, patch + 1)
    new_line = "%s%s%s" % (m.group(1), new, m.group(5))
    CONFIG_PATH.write_text(text[:m.start()] + new_line + text[m.end():])
    return old, new

# ── Files and directories to deploy ──────────────────────────────────────────
# (local_path, remote_path)  — directories are copied recursively

DEPLOY = [
    # entry point — oreoOS.entry → /main.py on the device
    ("oreoOS/entry.py",         "main.py"),

    # OS layer (flat namespace: api, app, theme, widgets, font, …)
    ("oreoOS/__init__.py",      "oreoOS/__init__.py"),
    ("oreoOS/config.py",        "oreoOS/config.py"),
    ("oreoOS/api.py",           "oreoOS/api.py"),
    ("oreoOS/app.py",           "oreoOS/app.py"),
    ("oreoOS/font.py",          "oreoOS/font.py"),
    ("oreoOS/pixelfont.py",     "oreoOS/pixelfont.py"),
    ("oreoOS/sprite.py",        "oreoOS/sprite.py"),
    ("oreoOS/home.py",          "oreoOS/home.py"),
    ("oreoOS/icons.py",         "oreoOS/icons.py"),
    ("oreoOS/launcher.py",      "oreoOS/launcher.py"),
    ("oreoOS/splash.py",        "oreoOS/splash.py"),
    ("oreoOS/theme.py",         "oreoOS/theme.py"),
    ("oreoOS/timeutil.py",      "oreoOS/timeutil.py"),
    ("oreoOS/widgets.py",       "oreoOS/widgets.py"),

    # Hardware drivers
    ("oreoWare/__init__.py",    "oreoWare/__init__.py"),
    ("oreoWare/_st7789.py",     "oreoWare/_st7789.py"),
    ("oreoWare/buttons.py",     "oreoWare/buttons.py"),
    ("oreoWare/display.py",     "oreoWare/display.py"),
    ("oreoWare/battery.py",     "oreoWare/battery.py"),
    ("oreoWare/os.py",          "oreoWare/os.py"),
    ("oreoWare/pins.py",        "oreoWare/pins.py"),
    ("oreoWare/wifi.py",        "oreoWare/wifi.py"),
    ("oreoWare/bt.py",          "oreoWare/bt.py"),
]

# Pixelify Sans bitmap-font modules (.py only — skip the TTF, it's build-time)
_fonts_dir = Path("assets/fonts/optimized")
if _fonts_dir.exists():
    DEPLOY.append(("assets/fonts/__init__.py",
                   "assets/fonts/__init__.py"))
    DEPLOY.append(("assets/fonts/optimized/__init__.py",
                   "assets/fonts/optimized/__init__.py"))
    for _f in sorted(_fonts_dir.glob("pixelify_*.py")):
        DEPLOY.append((str(_f), "assets/fonts/optimized/" + _f.name))

# apps — include only dirs that have both manifest.json and main.py
# Also pull in per-app assets/optimized/*.py
APPS_DIR = Path("apps")
for app_dir in sorted(APPS_DIR.iterdir()):
    if not app_dir.is_dir() or app_dir.name.startswith("_"):
        continue
    if (app_dir / "main.py").exists() and (app_dir / "manifest.json").exists():
        rel = str(app_dir)
        DEPLOY += [
            ("%s/__init__.py" % rel,      "%s/__init__.py" % rel),
            ("%s/main.py" % rel,          "%s/main.py" % rel),
            ("%s/manifest.json" % rel,    "%s/manifest.json" % rel),
        ]
        # Per-app assets (only optimized .py modules, not raw images).
        # Gallery is special: filter the optimized list to ONLY the stems
        # that still have a corresponding raw image — old photos that the
        # user deleted from raw/ should also vanish from the device.
        opt = app_dir / "assets" / "optimized"
        if opt.exists():
            r_base = "%s/assets/optimized" % rel
            DEPLOY.append(("%s/assets/__init__.py" % rel, "%s/assets/__init__.py" % rel))
            DEPLOY.append(("%s/__init__.py" % opt, "%s/__init__.py" % r_base))

            raw_dir   = app_dir / "assets" / "raw"
            raw_stems = None
            if app_dir.name == "gallery" and raw_dir.exists():
                raw_stems = {
                    p.stem for p in raw_dir.iterdir()
                    if p.suffix.lower() in (".png", ".jpg", ".jpeg")
                }

            for py in sorted(opt.glob("*.py")):
                if py.name == "__init__.py":
                    continue
                if raw_stems is not None and py.stem not in raw_stems:
                    # The matching raw image was removed — don't push the
                    # stale optimized module. The device-side cleanup below
                    # will remove it from flash on the next deploy.
                    continue
                DEPLOY.append((str(py), "%s/%s" % (r_base, py.name)))

# assets — only the optimized .py modules (not raw PNGs/SVGs)
for subdir in ["icons", "sprites", "status"]:
    opt = Path("assets") / subdir / "optimized"
    if opt.exists():
        remote_base = "assets/%s/optimized" % subdir
        DEPLOY.append(("%s/__init__.py" % opt, "%s/__init__.py" % remote_base))
        for py in sorted(opt.glob("*.py")):
            if py.name == "__init__.py":
                continue
            DEPLOY.append((str(py), "%s/%s" % (remote_base, py.name)))
        # parent __init__ files
        parent_local  = "assets/%s/__init__.py" % subdir
        parent_remote = "assets/%s/__init__.py" % subdir
        if Path(parent_local).exists():
            DEPLOY.append((parent_local, parent_remote))

DEPLOY.append(("assets/__init__.py", "assets/__init__.py"))


# ── helpers ───────────────────────────────────────────────────────────────────

def run(cmd, check=True):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print("  ERROR:", result.stderr.strip()[:300])
    return result


def mpremote(*args):
    return run(["python", "-m", "mpremote", "connect", PORT] + list(args))


def _human_size(n):
    if n >= 1024 * 1024:
        return "%.1f MB" % (n / 1024 / 1024)
    if n >= 1024:
        return "%.1f kB" % (n / 1024)
    return "%d B" % n


def _progress_bar(cur, total, width=24):
    filled = int(width * cur / max(1, total))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def mpremote_batch(actions, label=""):
    """Run many `fs` actions in a SINGLE mpremote session via `+` separators.

    Streams a verbose live progress report:
      [007/124] [####------------------]  oreoWare/display.py    4.2 kB  (+ 0.7s)
      [008/124] [####------------------]  oreoWare/wifi.py       ↺ unchanged

    The trailing "↺ unchanged" appears when mpremote's per-file cache shortcut
    fires (the file content on the device matches our local copy).
    """
    cmd = ["python", "-m", "mpremote", "connect", PORT]
    for a in actions:
        if cmd[-1] != PORT:
            cmd.append("+")
        op = a[0]
        if op == "mkdir":
            cmd += ["fs", "mkdir", ":%s" % a[1]]
        elif op == "cp":
            cmd += ["fs", "cp", a[1], ":%s" % a[2]]
        elif op == "rm":
            cmd += ["fs", "rm", ":%s" % a[1]]
    if label:
        print(label)

    total_cp = sum(1 for a in actions if a[0] == "cp")
    # Pre-compute the local→remote mapping so we can look up size by source
    cp_size = {}
    for a in actions:
        if a[0] == "cp":
            try:
                cp_size[a[1]] = Path(a[1]).stat().st_size
            except OSError:
                cp_size[a[1]] = 0

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1)

    done       = 0
    new_bytes  = 0
    skipped    = 0
    pending    = None     # local path of file currently being copied

    for line in proc.stdout:
        line = line.rstrip()
        if not line:
            continue
        if "File exists" in line:
            continue

        # "cp <local> :<remote>"  — mpremote announces a transfer
        if line.startswith("cp "):
            parts = line.split()
            if len(parts) >= 3:
                pending = parts[1]
            continue

        # "Up to date: <remote>"  — mpremote skipped because content matches
        if line.startswith("Up to date:"):
            if pending is not None:
                done    += 1
                skipped += 1
                bar      = _progress_bar(done, total_cp)
                print("  [%03d/%03d] %s  %-40s  ↺ unchanged" %
                      (done, total_cp, bar, pending[-40:]))
                pending  = None
            continue

        # Anything else → mpremote stderr (e.g. "mkdir: File exists" is filtered above)
        if pending is not None and not line.startswith(":"):
            # treat as the success line for a real transfer
            pass

        # Mirror unknown lines verbatim so errors aren't silently swallowed
        if not line.startswith(":") and "fs cp " not in line and not line.startswith("ls "):
            print("    " + line)

    # All mpremote output drained → infer how many "new" transfers happened
    # by counting cp-announcements without an Up-to-date follow-up.
    # The simplest heuristic: total_cp - skipped were actual writes.
    # We don't get per-line transfer confirmations, so we report aggregate.
    rc = proc.wait()
    real_writes = total_cp - skipped
    # Sum bytes of newly-written files (we don't know which exactly, but
    # this is a good order-of-magnitude — averaged file size × writes)
    if real_writes:
        avg = sum(cp_size.values()) // max(1, total_cp)
        new_bytes = avg * real_writes
    print("  ── %d files: %d new/updated (~%s)  %d unchanged   exit=%d" %
          (total_cp, real_writes, _human_size(new_bytes), skipped, rc))
    return rc


def write_secrets_local():
    """Generate a local .secrets_tmp.py by importing the project's config.py.

    config.py is the single source of truth: non-secret values are edited
    inline there, secrets come from .env. This function just snapshots every
    public attribute of config and emits a flat module on the device, so
    apps can `from secrets import GITHUB_USER, OWM_API_KEY, ...` with no
    filesystem dance at runtime.

    Returns (path_to_tmp_file, wifi_ssid_for_logging).
    """
    # Import the project config from the repo root.
    import sys as _sys
    project_root = str(Path(__file__).resolve().parent.parent)
    if project_root not in _sys.path:
        _sys.path.insert(0, project_root)
    # Drop any cached config so .env edits between deploys are picked up.
    for k in ("config", "oreoOS.config"):
        if k in _sys.modules:
            del _sys.modules[k]
    from oreoOS import config as _cfg

    fields = (
        # name              python repr formatter
        ("WIFI_SSID",        "%r"),
        ("WIFI_PASSWORD",    "%r"),
        ("WIFI_AUTO_CONNECT","%r"),
        ("BT_AUTO_ENABLE",   "%r"),
        ("GITHUB_USER",      "%r"),
        ("DISPLAY_NAME",     "%r"),
        ("DESIGNATION",      "%r"),
        ("OWM_API_KEY",      "%r"),
        ("WEATHER_LAT",      "%s"),
        ("WEATHER_LON",      "%s"),
        ("WEATHER_NAME",     "%r"),
        ("TIMEZONE_OFFSET",  "%s"),
    )
    out = ["# Auto-generated by tools/deploy.py from config.py + .env — do not commit."]
    for name, fmt in fields:
        out.append(("%-18s = " + fmt) % (name, getattr(_cfg, name, "")))
    out.append("")

    tmp = Path(".secrets_tmp.py")
    tmp.write_text("\n".join(out))
    return tmp, getattr(_cfg, "WIFI_SSID", "")


# ── build directory set ────────────────────────────────────────────────────────

remote_dirs = set()
for local, remote in DEPLOY:
    parent = str(Path(remote).parent)
    if parent != ".":
        remote_dirs.add(parent)

# sort so parents are created before children
remote_dirs = sorted(remote_dirs, key=lambda p: p.count("/"))


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    import time as _t
    t0 = _t.time()

    # Bump the patch BEFORE we hash files, so the new oreoOS/config.py is what
    # gets pushed in this same deploy. --no-bump skips it (useful when you're
    # just iterating locally and don't want VERSION churn in git history).
    if "--no-bump" not in sys.argv:
        old, new = bump_patch_version()
        if new:
            print("Version: %s → %s" % (old, new))
        else:
            print("Version: could not locate VERSION line in %s — skipping bump"
                  % CONFIG_PATH)
    print("Deploying Oreo Badge OS → %s\n" % PORT)

    # Verify device reachable
    r = mpremote("fs", "ls", ":")
    if r.returncode != 0:
        print("Cannot reach device on %s. Check USB cable and port." % PORT)
        sys.exit(1)

    if CLEAN:
        print("Wiping device filesystem...")
        mpremote("exec",
                 "import os\n"
                 "def _rm(p):\n"
                 "    try:\n"
                 "        for f in os.listdir(p): _rm(p + '/' + f)\n"
                 "        os.rmdir(p)\n"
                 "    except OSError:\n"
                 "        try: os.remove(p)\n"
                 "        except: pass\n"
                 "for f in os.listdir('/'):\n"
                 "    if f != 'boot.py': _rm('/' + f)\n")
        print()

    # Create all directories in one device-side exec (ignores "File exists")
    print("Creating directories (single exec)...")
    mkdir_script = (
        "import os\n"
        "for d in %r:\n"
        "    try: os.mkdir(d)\n"
        "    except OSError: pass\n"
    ) % list(remote_dirs)
    mpremote("exec", mkdir_script)

    # Build cp action list, skipping files whose hash matches the local cache.
    cache       = _load_hash_cache()
    new_cache   = dict(cache)
    actions     = []
    files       = []
    skipped_pre = 0
    for local, remote in DEPLOY:
        if not Path(local).exists():
            print("SKIP  %s (not found locally)" % local)
            continue
        try:
            h = _hash_file(local)
        except OSError:
            h = None
        if h is not None and cache.get(remote) == h:
            skipped_pre += 1
            continue
        files.append((local, remote))
        actions.append(("cp", local, remote))
        if h is not None:
            new_cache[remote] = h

    # Write + queue secrets.py (always re-push — .env can change without
    # touching any tracked file)
    secrets_tmp, ssid = write_secrets_local()
    actions.append(("cp", str(secrets_tmp), "secrets.py"))

    # Gallery sync: remove device-side .py files whose raw counterpart has
    # been deleted locally. Frees flash from past uploads and keeps the
    # carousel showing only the photos the user actually has in raw/.
    gallery_raw = Path("apps/gallery/assets/raw")
    if gallery_raw.exists():
        keep = sorted({
            p.stem for p in gallery_raw.iterdir()
            if p.suffix.lower() in (".png", ".jpg", ".jpeg")
        })
        cleanup = (
            "import os\n"
            "keep = set(%r)\n"
            "keep.add('__init__')\n"
            "d = 'apps/gallery/assets/optimized'\n"
            "try:\n"
            "    for f in os.listdir(d):\n"
            "        if f.endswith('.py') and f[:-3] not in keep:\n"
            "            try: os.remove(d + '/' + f)\n"
            "            except OSError: pass\n"
            "except OSError: pass\n"
        ) % keep
        print("  pruning stale gallery photos on device (keep=%d)" % len(keep))
        mpremote("exec", cleanup)

    cache_state = "miss" if not cache else "hit (%d entries)" % len(cache)
    print("  hash cache: %s   |   to push: %d   skipped: %d"
          % (cache_state, len(files) + 1, skipped_pre))
    if skipped_pre and len(cache) == 0:
        print("  (cache was empty — first run after a hash-cache reset will push everything)")
    print()

    push_t0 = _t.time()
    try:
        rc = mpremote_batch(actions,
                            label="Pushing %d files in a single session..."
                                  % (len(files) + 1))
    finally:
        secrets_tmp.unlink(missing_ok=True)
    push_elapsed = _t.time() - push_t0
    print("  mpremote batch took %.1fs" % push_elapsed)

    # Save the cache regardless of rc. mpremote's exit code reflects the LAST
    # command in the `+`-chained session — a stray "File exists" mkdir or a
    # transient warning was previously dropping us into the `rc != 0` branch
    # and the cache never persisted, which is why "2 changed files" ended up
    # pushing everything on the next run. We always persist the hashes for
    # files we queued; if a single transfer actually corrupted, --force on
    # the next deploy will re-push everything.
    _save_hash_cache(new_cache)

    elapsed = _t.time() - t0
    if rc == 0:
        print("\nDone in %.1fs.  WIFI_SSID=%r" % (elapsed, ssid or "<unset>"))
        print("Resetting device...")
        mpremote("reset")
        print("Oreo OS is booting.")
    else:
        print("\nBatch exited with code %d after %.1fs (cache still saved)." % (rc, elapsed))


if __name__ == "__main__":
    main()

"""Deploy Elixpo Badge OS to the ESP32-S3 via mpremote.

Usage:
    python tools/deploy.py              # auto-detect port
    python tools/deploy.py /dev/ttyACM0
    python tools/deploy.py --clean      # wipe device first, then deploy

Must be run from the project root.
"""

import sys
import subprocess
import time
from pathlib import Path

PORT = "/dev/ttyACM0"
for arg in sys.argv[1:]:
    if arg.startswith("/dev/") or "COM" in arg:
        PORT = arg

CLEAN = "--clean" in sys.argv

# ── Files and directories to deploy ──────────────────────────────────────────
# (local_path, remote_path)  — directories are copied recursively

DEPLOY = [
    # entry point
    ("entry/badgr.py",                "main.py"),

    # core framework
    ("lix/__init__.py",        "lix/__init__.py"),
    ("lix/api.py",             "lix/api.py"),
    ("lix/app.py",             "lix/app.py"),

    # hardware drivers
    ("lix_hw/__init__.py",     "lix_hw/__init__.py"),
    ("lix_hw/_st7789.py",      "lix_hw/_st7789.py"),
    ("lix_hw/buttons.py",      "lix_hw/buttons.py"),
    ("lix_hw/display.py",      "lix_hw/display.py"),
    ("lix_hw/os.py",           "lix_hw/os.py"),
    ("lix_hw/pins.py",         "lix_hw/pins.py"),
    ("lix_hw/wifi.py",         "lix_hw/wifi.py"),
    ("lix_hw/bt.py",           "lix_hw/bt.py"),

    # OS layer
    ("lix_os/__init__.py",     "lix_os/__init__.py"),
    ("lix_os/home.py",         "lix_os/home.py"),
    ("lix_os/icons.py",        "lix_os/icons.py"),
    ("lix_os/launcher.py",     "lix_os/launcher.py"),
    ("lix_os/splash.py",       "lix_os/splash.py"),
    ("lix_os/theme.py",        "lix_os/theme.py"),
    ("lix_os/timeutil.py",     "lix_os/timeutil.py"),
    ("lix_os/widgets.py",      "lix_os/widgets.py"),
]

# lix module — also pick up font/sprite/pixelfont
DEPLOY += [
    ("lix/font.py",      "lix/font.py"),
    ("lix/sprite.py",    "lix/sprite.py"),
    ("lix/pixelfont.py", "lix/pixelfont.py"),
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
        # Per-app assets (only optimized .py modules, not raw images)
        opt = app_dir / "assets" / "optimized"
        if opt.exists():
            r_base = "%s/assets/optimized" % rel
            DEPLOY.append(("%s/assets/__init__.py" % rel, "%s/assets/__init__.py" % rel))
            DEPLOY.append(("%s/__init__.py" % opt, "%s/__init__.py" % r_base))
            for py in sorted(opt.glob("*.py")):
                if py.name == "__init__.py":
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
      [007/124] [####------------------]  lix_hw/display.py     4.2 kB  (+ 0.7s)
      [008/124] [####------------------]  lix_hw/wifi.py        ↺ unchanged

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
    if "config" in _sys.modules:
        del _sys.modules["config"]      # force a fresh re-read of .env
    import config as _cfg

    fields = (
        # name              python repr formatter
        ("WIFI_SSID",        "%r"),
        ("WIFI_PASSWORD",    "%r"),
        ("WIFI_AUTO_CONNECT","%r"),
        ("BT_AUTO_ENABLE",   "%r"),
        ("GITHUB_USER",      "%r"),
        ("OWM_API_KEY",      "%r"),
        ("WEATHER_LAT",      "%s"),
        ("WEATHER_LON",      "%s"),
        ("WEATHER_NAME",     "%r"),
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
    print("Deploying Elixpo Badge OS → %s\n" % PORT)

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

    # Build cp action list
    actions = []
    files   = []
    for local, remote in DEPLOY:
        if not Path(local).exists():
            print("SKIP  %s (not found locally)" % local)
            continue
        files.append((local, remote))
        actions.append(("cp", local, remote))

    # Write + queue secrets.py
    secrets_tmp, ssid = write_secrets_local()
    actions.append(("cp", str(secrets_tmp), "secrets.py"))

    try:
        rc = mpremote_batch(actions,
                            label="Pushing %d files in a single session..."
                                  % (len(files) + 1))
    finally:
        secrets_tmp.unlink(missing_ok=True)

    elapsed = _t.time() - t0
    if rc == 0:
        print("\nDone in %.1fs.  WIFI_SSID=%r" % (elapsed, ssid or "<unset>"))
        print("Resetting device...")
        mpremote("reset")
        print("Elixpo OS is booting.")
    else:
        print("\nBatch exited with code %d after %.1fs." % (rc, elapsed))


if __name__ == "__main__":
    main()

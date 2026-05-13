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


def mpremote_batch(actions, label=""):
    """Run many `fs` actions in a SINGLE mpremote session via `+` separators.

    actions = [("mkdir", remote_dir), ("cp", local, remote), ...]
    Output is streamed so we can see progress; errors are tolerated.
    """
    cmd = ["python", "-m", "mpremote", "connect", PORT]
    for a in actions:
        if cmd[-1] != PORT:        # add separator between actions
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
    # Stream output so the user sees progress
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1)
    for line in proc.stdout:
        line = line.rstrip()
        if line and "File exists" not in line:
            print("  " + line)
    return proc.wait()


def _read_env():
    """Read .env and .env.local — later overrides earlier."""
    env = {}
    for fname in (".env", ".env.local"):
        p = Path(fname)
        if not p.exists():
            continue
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def write_secrets_local():
    """Generate a local .secrets_tmp.py from .env. Returns (path, ssid)."""
    env = _read_env()
    ssid = env.get("WIFI_SSID", "")
    pw   = env.get("WIFI_PASSWORD", "")
    src = (
        '# Auto-generated by tools/deploy.py from .env — do not commit.\n'
        'WIFI_SSID     = %r\n'
        'WIFI_PASSWORD = %r\n'
    ) % (ssid, pw)
    tmp = Path(".secrets_tmp.py")
    tmp.write_text(src)
    return tmp, ssid


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

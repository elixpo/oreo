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

    # OS layer
    ("lix_os/__init__.py",     "lix_os/__init__.py"),
    ("lix_os/home.py",         "lix_os/home.py"),
    ("lix_os/icons.py",        "lix_os/icons.py"),
    ("lix_os/launcher.py",     "lix_os/launcher.py"),
    ("lix_os/panda.py",        "lix_os/panda.py"),
    ("lix_os/splash.py",       "lix_os/splash.py"),
    ("lix_os/theme.py",        "lix_os/theme.py"),
    ("lix_os/timeutil.py",     "lix_os/timeutil.py"),
]

# apps — include only dirs that have both manifest.json and main.py
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
        print("  ERROR:", result.stderr.strip())
    return result


def mpremote(*args):
    return run(["python", "-m", "mpremote", "connect", PORT] + list(args))


def mkdir_p(remote_dir):
    """Create directory and parents on device (ignore if exists)."""
    parts = Path(remote_dir).parts
    for i in range(1, len(parts) + 1):
        d = "/".join(parts[:i])
        mpremote("fs", "mkdir", ":%s" % d)   # ignore errors — dir may exist


def cp(local, remote):
    r = mpremote("fs", "cp", local, ":%s" % remote)
    return r.returncode == 0


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
    print("Deploying Elixpo Badge OS → %s\n" % PORT)

    # Verify device reachable
    r = mpremote("fs", "ls", ":")
    if r.returncode != 0:
        print("Cannot reach device on %s. Check USB cable and port." % PORT)
        sys.exit(1)

    if CLEAN:
        print("Wiping device filesystem...")
        mpremote("exec", "import os; [os.remove(f) for f in os.listdir('/') if f != 'boot.py']")
        print()

    print("Creating directories...")
    for d in remote_dirs:
        print("  /%s" % d)
        mkdir_p(d)
    print()

    print("Copying %d files..." % len(DEPLOY))
    ok = fail = 0
    for local, remote in DEPLOY:
        if not Path(local).exists():
            print("  SKIP  %-45s (not found locally)" % local)
            continue
        success = cp(local, remote)
        if success:
            print("  OK    %s" % remote)
            ok += 1
        else:
            print("  FAIL  %s" % remote)
            fail += 1

    print("\n%d copied, %d failed." % (ok, fail))

    if fail == 0:
        print("\nResetting device...")
        mpremote("reset")
        print("Done — Elixpo OS booting on device.")
    else:
        print("\nSome files failed. Fix errors above and re-run.")


if __name__ == "__main__":
    main()

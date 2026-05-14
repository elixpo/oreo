"""Cut an OreoOS release from your laptop. No CI required.

Usage:
    python tools/release.py vX.Y.Z [--channel stable|beta] [--notes "..."] [--dry-run]

What it does, in order:

  1. Confirms the version isn't already a tag on the remote.
  2. Bumps oreoOS/config.py:VERSION to the requested string (no-op if
     already correct).
  3. Commits + tags + pushes the bump.
  4. Runs tools/build_release.py to produce dist/<version>/.
  5. Calls `gh release create` to publish the GitHub Release with
     manifest.json + bundle.tar + every per-file asset attached.

Once `gh release create` returns, every badge in the field with WiFi
will see the new version on its next background-check tick (within 6h
of the release).

Requirements:
  * `gh` CLI installed + authenticated (`gh auth status`)
  * `git` configured with push access to the repo
  * a clean working tree (this script refuses to release with
    uncommitted changes unless --force is passed)

Channel convention:
  stable/vX.Y.Z   — what badges pick up by default
  beta/vX.Y.Z     — opt-in, marked as prerelease

Pass --dry-run to print the gh / git commands without executing them.
That's the safest way to preview a release.
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT  = Path(__file__).resolve().parent.parent
CONFIG     = REPO_ROOT / "oreoOS" / "config.py"
VERSION_RE = re.compile(r'(VERSION\s*=\s*")v\d+\.\d+\.\d+(")')


def run(cmd, dry, capture=False, check=True):
    """Echo + execute (or echo only when dry-run)."""
    pretty = " ".join(str(c) for c in cmd)
    print("$", pretty)
    if dry:
        return ""
    if capture:
        r = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
        if check and r.returncode != 0:
            sys.exit("  ✗ exit %d\n%s" % (r.returncode, r.stderr.strip()))
        return r.stdout.strip()
    rc = subprocess.run(cmd, cwd=REPO_ROOT).returncode
    if check and rc != 0:
        sys.exit("  ✗ exit %d" % rc)
    return ""


# ── pre-flight ──────────────────────────────────────────────────────────────

def _check_clean(force, dry):
    if force:
        return
    status = run(["git", "status", "--porcelain"], dry, capture=True, check=False)
    if status:
        sys.exit(
            "✗ working tree is not clean:\n"
            + status
            + "\n  Commit / stash first, or rerun with --force."
        )


def _check_tools(dry):
    for tool in ("git", "gh"):
        if shutil.which(tool) is None:
            sys.exit("✗ required tool not found on PATH: %s" % tool)
    auth = run(["gh", "auth", "status"], dry, capture=True, check=False)
    if not dry and "Logged in" not in auth and "Active account" not in auth:
        sys.exit("✗ `gh auth status` failed — run `gh auth login` first.")


def _tag_exists(tag, dry):
    if dry:
        return False
    out = run(["git", "ls-remote", "--tags", "origin", tag], dry, capture=True)
    return bool(out.strip())


# ── version bump ────────────────────────────────────────────────────────────

def _bump_version(target_version, dry):
    txt = CONFIG.read_text()
    m   = VERSION_RE.search(txt)
    if not m:
        sys.exit("✗ could not find VERSION literal in %s" % CONFIG)
    current = re.search(r'v\d+\.\d+\.\d+', m.group(0)).group(0)
    if current == target_version:
        print("  version already at %s — no bump needed" % target_version)
        return False
    new_line = '%s%s%s' % (m.group(1), target_version, m.group(2))
    new_txt  = txt[:m.start()] + new_line + txt[m.end():]
    print("  %s → %s in oreoOS/config.py" % (current, target_version))
    if not dry:
        CONFIG.write_text(new_txt)
    return True


# ── main flow ───────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("version", help="vX.Y.Z (must start with v)")
    ap.add_argument("--channel", default="stable",
                    choices=("stable", "beta"),
                    help="release channel (default: stable)")
    ap.add_argument("--notes", default="",
                    help="release notes body. If omitted, gh prompts you.")
    ap.add_argument("--force", action="store_true",
                    help="skip the clean-working-tree check (dangerous).")
    ap.add_argument("--dry-run", action="store_true",
                    help="print every step without executing.")
    args = ap.parse_args()

    if not re.fullmatch(r"v\d+\.\d+\.\d+", args.version):
        sys.exit("✗ version must look like vX.Y.Z (got: %r)" % args.version)

    dry = args.dry_run
    tag = "%s/%s" % (args.channel, args.version)

    print("──────────────────────────────────────────────")
    print("Releasing OreoOS %s on channel %s" % (args.version, args.channel))
    print("Tag: %s" % tag)
    print("Dry-run: %s" % ("yes" if dry else "no"))
    print("──────────────────────────────────────────────\n")

    # 1. Pre-flight.
    _check_tools(dry)
    _check_clean(args.force, dry)
    if _tag_exists(tag, dry):
        sys.exit("✗ tag %s already exists on origin." % tag)

    # 2. Bump VERSION + commit + tag + push.
    bumped = _bump_version(args.version, dry)
    if bumped:
        run(["git", "add", "oreoOS/config.py"], dry)
        run(["git", "commit", "-m", "release: %s" % args.version], dry)
    run(["git", "tag", tag], dry)
    run(["git", "push"], dry)
    run(["git", "push", "origin", tag], dry)

    # 3. Build the release artefacts. asset_base_url points at the URL
    # gh will use once the upload step has finished.
    asset_base = "https://github.com/elixpo/oreo-badge/releases/download/%s/" % tag
    run([
        sys.executable, "tools/build_release.py",
        "--version", args.version,
        "--channel", args.channel,
        "--asset-base-url", asset_base,
        "--notes", args.notes,
        "--out",   "dist",
    ], dry)

    # 4. Flatten the per-file assets into upload/ — the manifest's URLs
    # reference path-flattened names (slashes → underscores). build_release
    # already mirrored the tree; we just rename for upload.
    dist_files = REPO_ROOT / "dist" / args.version / "files"
    upload_dir = REPO_ROOT / "dist" / args.version / "_upload"
    if not dry:
        if upload_dir.exists():
            shutil.rmtree(upload_dir)
        upload_dir.mkdir(parents=True)
        for p in dist_files.rglob("*"):
            if p.is_file():
                rel = p.relative_to(dist_files)
                flat = str(rel).replace("/", "_")
                shutil.copyfile(p, upload_dir / flat)
        # Add manifest + bundle alongside.
        shutil.copyfile(REPO_ROOT / "dist" / args.version / "manifest.json",
                        upload_dir / "manifest.json")
        shutil.copyfile(REPO_ROOT / "dist" / args.version / "bundle.tar",
                        upload_dir / "bundle.tar")

    # 5. Create the GitHub Release.
    prerelease_flag = ["--prerelease"] if args.channel != "stable" else []
    notes = args.notes or ("OreoOS %s — %s channel." % (args.version, args.channel))
    run([
        "gh", "release", "create", tag,
        "--title", "OreoOS %s (%s)" % (args.version, args.channel),
        "--notes", notes,
        *prerelease_flag,
        "--target", "main",
        str(upload_dir) + "/*",
    ], dry)

    print("\n✓ release %s pushed and published." % tag)
    if not dry:
        print("  Badges on this channel will pick it up within 6 h of next")
        print("  background check (Settings → Check Update to force it now).")


if __name__ == "__main__":
    main()

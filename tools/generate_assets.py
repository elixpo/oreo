"""Generate Elixpo Badge assets via the Pollinations AI image API.

Top-level icons:
  python tools/generate_assets.py              # all active entries
  python tools/generate_assets.py home_bg

Per-app sprites (prompts/<app>/<name>.md → apps/<app>/assets/raw/<name>.png):
  python tools/generate_assets.py --app flappy           # all prompts under prompts/flappy/
  python tools/generate_assets.py --app flappy obstacle  # single sprite

Theme reference: prompts/THEME.md
"""

import os
import sys
import urllib.request
import urllib.parse
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
load_dotenv(".env.local")   # also try .env.local

KEY  = os.getenv("POLLINATIONS_KEY")
BASE = "https://gen.pollinations.ai/image"


def _read_prompt(path):
    """Read prompt text from a .md file (the block after '## Prompt')."""
    md = Path(path)
    if not md.exists():
        return None
    text = md.read_text()
    marker = "## Prompt"
    if marker in text:
        after = text.split(marker, 1)[1]
        lines = []
        for line in after.splitlines():
            if line.startswith("##"):
                break
            lines.append(line)
        return " ".join(l.strip() for l in lines if l.strip())
    return None


def download_to(prompt, out_path, width=200, height=200):
    """Generic download — saves the generated PNG to out_path."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    print("→ %s  (%dx%d)\n  %s..." % (out_path, width, height, prompt[:90]))

    headers = {
        "Authorization": "Bearer %s" % KEY if KEY else "",
        "User-Agent":    "ElixpoBadge/1.0",
    }
    enc = urllib.parse.quote(prompt)
    url = "%s/%s?width=%d&height=%d&seed=42&nologo=true&model=gptimage" % (
        BASE, enc, width, height
    )
    for attempt in range(4):
        try:
            req  = urllib.request.Request(url, headers=headers)
            resp = urllib.request.urlopen(req, timeout=90)
            data = resp.read()
            if len(data) < 1000:
                print("  WARN small (%d bytes), retry" % len(data))
                time.sleep(15 * (attempt + 1))
                continue
            out_path.write_bytes(data)
            print("  saved %d bytes" % len(data))
            return True
        except Exception as e:
            wait = 20 * (attempt + 1)
            print("  attempt %d error: %s — retry in %ds" % (attempt + 1, e, wait))
            time.sleep(wait)
    return False


def generate_app(app_name, only_names=None):
    """Generate all assets for one app: prompts/<app>/*.md → apps/<app>/assets/raw/*.png"""
    prompts_dir = Path("prompts") / app_name
    out_dir     = Path("apps") / app_name / "assets" / "raw"

    if not prompts_dir.exists():
        print("No prompts directory at %s" % prompts_dir)
        return

    mds = sorted(prompts_dir.glob("*.md"))
    if only_names:
        mds = [m for m in mds if m.stem in only_names]
    if not mds:
        print("No .md prompt files in %s" % prompts_dir)
        return

    print("Generating %d sprite(s) for app '%s'...\n" % (len(mds), app_name))
    for md in mds:
        prompt = _read_prompt(md)
        if not prompt:
            print("  SKIP %s — no ## Prompt block" % md.name)
            continue
        out = out_dir / ("%s.png" % md.stem)
        download_to(prompt, out, width=200, height=200)
        time.sleep(8)
    print("\nDone. Run:  python tools/optimize_assets.py --app %s" % app_name)




# ── Active assets ──────────────────────────────────────────────────────────────
# Each entry: name → (width, height) or None to use default 200×200.
# Prompt text is read from prompts/<name>.md automatically.
# Comment out entries you don't want to regenerate.

ACTIVE = {
    "home_bg":    (200, 200),
    "apps_icon":  (200, 200),
    # "flappy_icon":  None,
    # "snake_icon":   None,
    # "gamepad_icon": None,
    # "commits_icon": None,
    # "settings_icon": None,
    # "bluetooth_icon": None,
    # "wifi_icon": None,
    # "about_icon": None,
    # "identity_icon": None,
    # "elixpo_pet_icon": None,
    # "elixpo_sketch_icon": None,
    # "IR_Quest_icon": None,
    # "commits_breaker_icon": None,
    # "wallpaper_icon": None,
    # "gallery_icon": None,
    # "flappy_panda_up":   None,
    # "flappy_panda_down": None,
}

# ── Inline fallback prompts (used if no .md file exists) ─────────────────────
# Edit the .md files in prompts/ instead — these are last-resort only.

_FALLBACK_PROMPTS = {}

# ── Style constants (appended to all prompts that don't have their own style) ─

PANDA_BASE = (
    "cute panda character with big eyes, black and white panda with pink cheeks, "
    "wearing a red badge with letter E on chest"
)

ICON_STYLE = (
    "pixel art cartoon style, thick dark outline, pastel vibrant colors, "
    "cute kawaii style, white background, square crop, no text, no watermark"
)

# ── Download ──────────────────────────────────────────────────────────────────

def download(name, width=200, height=200):
    """Top-level icon: prompts/<name>.md → assets/icons/raw/<name>.png."""
    prompt = _read_prompt("prompts/%s.md" % name) or _FALLBACK_PROMPTS.get(name)
    if not prompt:
        print("  SKIP %s — no prompt at prompts/%s.md" % (name, name))
        return
    download_to(prompt, "assets/icons/raw/%s.png" % name, width, height)


def main():
    # ── per-app mode ─────────────────────────────────────────────────────────
    if "--app" in sys.argv:
        idx = sys.argv.index("--app")
        rest = sys.argv[idx + 1:]
        if not rest:
            print("Usage: generate_assets.py --app <app> [name ...]")
            return
        app, *only = rest
        generate_app(app, only_names=only or None)
        return

    # ── top-level icons mode ─────────────────────────────────────────────────
    targets = sys.argv[1:]
    active  = {k: v for k, v in ACTIVE.items()}
    if targets:
        active = {k: active.get(k, (200, 200)) for k in targets}
    if not active:
        print("No active entries. Uncomment entries in ACTIVE dict or pass names as args.")
        return

    print("Generating %d asset(s)...\n" % len(active))
    for name, dims in active.items():
        w, h = dims if dims else (200, 200)
        download(name, w, h)
        time.sleep(8)

    print("\nDone. Run:  python tools/optimize_assets.py")


if __name__ == "__main__":
    main()

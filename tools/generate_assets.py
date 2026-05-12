"""Generate Elixpo Badge assets via the Pollinations AI image API.

Usage:
    python tools/generate_assets.py              # all active entries
    python tools/generate_assets.py home_bg      # single asset by name

Workflow:
  1. Edit/create  prompts/<name>.md   — prompt text + theme notes
  2. Uncomment    ACTIVE[<name>]       — in this file
  3. Run          python tools/generate_assets.py [name]
  4. Run          python tools/optimize_assets.py [name]
  5. Asset is ready in assets/icons/<name>.py

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


def _read_prompt(name):
    """Read prompt text from prompts/<name>.md (the block after '## Prompt')."""
    md = Path("prompts/%s.md" % name)
    if not md.exists():
        return None
    text = md.read_text()
    marker = "## Prompt"
    if marker in text:
        after = text.split(marker, 1)[1]
        # collect lines until next ## heading or end
        lines = []
        for line in after.splitlines():
            if line.startswith("##"):
                break
            lines.append(line)
        return " ".join(l.strip() for l in lines if l.strip())
    return None


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
    prompt = _read_prompt(name) or _FALLBACK_PROMPTS.get(name)
    if not prompt:
        print("  SKIP %s — no prompt found (add prompts/%s.md)" % (name, name))
        return

    out_dir = Path("asset/icons")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / ("%s.png" % name)

    print("→ %s  (%dx%d)" % (name, width, height))
    print("  %s..." % prompt[:100])

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
                print("  WARN: response too small (%d bytes): %s" % (len(data), data[:100]))
                time.sleep(15 * (attempt + 1))
                continue
            out.write_bytes(data)
            print("  saved %d bytes → %s" % (len(data), out))
            return
        except Exception as e:
            wait = 20 * (attempt + 1)
            print("  attempt %d error: %s — retry in %ds" % (attempt + 1, e, wait))
            time.sleep(wait)

    print("  FAILED after 4 attempts: %s" % name)


def main():
    targets = sys.argv[1:]
    active  = {k: v for k, v in ACTIVE.items()}   # copy

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

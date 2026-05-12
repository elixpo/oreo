"""Generate app icons via pollinations.ai (qwen-image model).

Reads POLLINATIONS_KEY from .env.local, downloads each icon as a
200×200 PNG into asset/icons/, then resizes/pads to exact square.

Run from project root:
    python tools/gen_icons.py
"""

import os
import sys
import urllib.request
import urllib.parse
import time
from pathlib import Path

# ── load API key ──────────────────────────────────────────────────────────────
KEY = ""
env = Path(".env.local")
if env.exists():
    for line in env.read_text().splitlines():
        if line.startswith("POLLINATIONS_KEY="):
            KEY = line.split("=", 1)[1].strip()

if not KEY:
    print("ERROR: POLLINATIONS_KEY not found in .env.local")
    sys.exit(1)

MODEL  = "qwen-image"
BASE   = "https://image.pollinations.ai/prompt"
SIZE   = 200

# ── icon definitions ──────────────────────────────────────────────────────────
# Style anchor: match the gallery icon — pixel art cartoon, thick dark outline,
# pastel colours, white/transparent bg, square crop, no text.

STYLE = (
    "pixel art cartoon style, thick dark outline, pastel vibrant colors, "
    "cute kawaii style, white background, square crop, no text, no watermark, "
    "same style as a cute pixel art duck in a picture frame"
)

PANDA_BASE = (
    "cute panda character with big eyes, black and white panda with pink cheeks, "
    "wearing a red badge with letter E on chest"
)

ICONS = {
    "flappy_icon": (
        "pixel art cartoon icon: " + PANDA_BASE + " sitting inside a small yellow biplane, "
        "flying between green pipes, side view, cheerful expression, "
        "blue sky background. " + STYLE
    ),
    "snake_icon": (
        "pixel art cartoon icon: " + PANDA_BASE + " holding a long green pixel snake "
        "coiled around their arm, playful pose, dark green snake with pixel squares, "
        "white background. " + STYLE
    ),
    "gamepad_icon": (
        "pixel art cartoon icon: " + PANDA_BASE + " holding a small teal game controller "
        "with dpad and buttons, excited gaming pose, controller glowing teal, "
        "white background. " + STYLE
    ),
    "wifi_icon": (
        "pixel art cartoon icon: " + PANDA_BASE + " holding up a teal wifi signal bar "
        "icon and a blue bluetooth symbol, one in each hand, happy expression, "
        "white background. " + STYLE
    ),
    "about_icon": (
        "pixel art cartoon icon: " + PANDA_BASE + " reading a small open book, "
        "studious expression with small glasses, cute pose, "
        "white background. " + STYLE
    ),
    "identity_icon": (
        "pixel art cartoon icon: " + PANDA_BASE + " holding up a badge/ID card "
        "with star on it, proud pose, lanyard around neck, "
        "white background. " + STYLE
    ),
}

# ── download ──────────────────────────────────────────────────────────────────

out_dir = Path("asset/icons")
out_dir.mkdir(parents=True, exist_ok=True)

headers = {
    "Authorization": "Bearer %s" % KEY,
    "User-Agent":    "ElixpoBadge/1.0",
}

for name, prompt in ICONS.items():
    out = out_dir / ("%s.png" % name)
    print("→ %s" % name)
    print("  %s..." % prompt[:80])

    enc = urllib.parse.quote(prompt)
    url = "%s/%s?width=%d&height=%d&seed=42&nologo=true&model=%s" % (
        BASE, enc, SIZE, SIZE, MODEL
    )

    try:
        req  = urllib.request.Request(url, headers=headers)
        resp = urllib.request.urlopen(req, timeout=60)
        data = resp.read()
        if len(data) < 1000:
            print("  WARN: response too small (%d bytes) — may be an error" % len(data))
            print("  Response:", data[:200])
        else:
            out.write_bytes(data)
            print("  ✓ saved %d bytes → %s" % (len(data), out))
    except Exception as e:
        print("  ERROR: %s" % e)

    time.sleep(1.5)   # be polite to the API

print("\nAll done. Run the sim to see the icons.")

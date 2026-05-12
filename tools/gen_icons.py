import os
import sys
import urllib.request
import urllib.parse
import time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()


KEY = os.getenv("POLLINATIONS_KEY")
BASE   = "https://gen.pollinations.ai/image"
SIZE   = 200


STYLE = (
    "pixel art cartoon style, thick dark outline, pastel vibrant colors, "
    "cute kawaii style, white background, square crop, no text, no watermark, "
)

PANDA_BASE = (
    "cute panda character with big eyes, black and white panda with pink cheeks, "
    "wearing a red badge with letter E on chest"
)

ICONS = {
    # "flappy_icon": (
    #     "pixel art cartoon icon: " + PANDA_BASE + " sitting inside a tiny yellow biplane, "
    #     "flying between two green pipes, side view, arms out for balance, cheerful grin, "
    #     "bright blue sky background, propeller spinning. " + STYLE
    # ),
    # "snake_icon": (
    #     "pixel art cartoon icon: " + PANDA_BASE + " holding a long green pixel snake "
    #     "coiled around their arm, playful pose, dark green snake with bright pixel squares, "
    #     "white background. " + STYLE
    # ),
    # "gamepad_icon": (
    #     "pixel art cartoon icon: " + PANDA_BASE + " holding a small teal game controller "
    #     "with dpad and ABXY buttons, excited gaming pose, controller glowing teal, "
    #     "white background. " + STYLE
    # ),
    "commits_icon": (
        "pixel art cartoon icon: " + PANDA_BASE + " typing on a tiny laptop, "
        "green commit graph bars glowing on screen, sparkles around laptop, "
        "coding expression, white background. " + STYLE
    ),
    # "settings_icon": (
    #     "pixel art cartoon icon: " + PANDA_BASE + " holding a large gear cog in one hand "
    #     "and a wifi signal bar in the other, bluetooth symbol floating nearby, "
    #     "tinkering happy expression, white background. " + STYLE
    # ),
    # "about_icon": (
    #     "pixel art cartoon icon: " + PANDA_BASE + " reading a small open book, "
    #     "studious expression with tiny round glasses, white background. " + STYLE
    # ),
    # "identity_icon": (
    #     "pixel art cartoon icon: " + PANDA_BASE + " holding up a conference ID badge card "
    #     "with a star on it, proud pose, lanyard around neck, white background. " + STYLE
    # ),
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
    url = "%s/%s?width=200&height=200&seed=42&nologo=true&model=gptimage" % (
        BASE, enc
    )

    for attempt in range(4):
        try:
            req  = urllib.request.Request(url, headers=headers)
            resp = urllib.request.urlopen(req, timeout=90)
            data = resp.read()
            if len(data) < 1000:
                print("  WARN: response too small (%d bytes)" % len(data))
                print("  Response:", data[:200])
                wait = 15 * (attempt + 1)
                print("  Retrying in %ds..." % wait)
                time.sleep(wait)
                continue
            out.write_bytes(data)
            print("  saved %d bytes → %s" % (len(data), out))
            break
        except Exception as e:
            wait = 20 * (attempt + 1)
            print("  attempt %d error: %s — waiting %ds" % (attempt + 1, e, wait))
            time.sleep(wait)

    time.sleep(8)   # generous gap between icons

print("\nAll done. Run the sim to see the icons.")

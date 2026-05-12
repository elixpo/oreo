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
    # "commits_icon": (
    #     "pixel art cartoon icon: " + PANDA_BASE + " typing on a tiny laptop, "
    #     "green commit graph bars glowing on screen, sparkles around laptop, "
    #     "coding expression, white background. " + STYLE
    # ),
    # "settings_icon": (
    #     "pixel art cartoon icon: " + PANDA_BASE + " holding a large gear cog in one hand "
    #     "and a wifi signal bar in the other, bluetooth symbol floating nearby, "
    #     "tinkering happy expression, white background. " + STYLE
    # ),
    # "bluetooth_icon": (
    #     "8-bit pixel art icon of the bluetooth symbol, bold chunky letter B shape with "
    #     "two diagonal lines, electric blue color, thick black pixel outline, "
    #     "heavy blocky 8bit pixels, very pixelated retro style, "
    #     "square white background, symbol only, no characters, no text. " + STYLE
    # ),
    # "wifi_icon": (
    #     "8-bit pixel art icon of wifi signal bars, four chunky concentric arc bars "
    #     "stacked small to large with a dot at bottom, bright teal color, "
    #     "thick black pixel outline, heavy blocky 8bit pixels, very pixelated retro style, "
    #     "square white background, symbol only, no characters, no text. " + STYLE
    # ),
    # "about_icon": (
    #     "pixel art cartoon icon: " + PANDA_BASE + " reading a small open book, "
    #     "studious expression with tiny round glasses, white background. " + STYLE
    # ),
    # "identity_icon": (
    #     "pixel art cartoon icon: " + PANDA_BASE + " holding up a conference ID badge card "
    #     "with a star on it, proud pose, lanyard around neck, white background. " + STYLE
    # ),
    # "elixpo_pet_icon": (
    #     "pixel art cartoon icon: " + PANDA_BASE + " sitting happily with a tiny heart "
    #     "floating above its head, three small colourful stat bars beside it showing "
    #     "happiness hunger and cleanliness, cute cozy tamagotchi virtual pet style, "
    #     "soft pastel warm background. " + STYLE
    # ),
    # "elixpo_sketch_icon": (
    #     "pixel art cartoon icon: " + PANDA_BASE + " holding two large knob dials "
    #     "like an Etch-A-Sketch toy, small pixel canvas behind showing a heart drawn "
    #     "in chunky pixels, tiny artist beret on head, excited creative expression, "
    #     "white background. " + STYLE
    # ),
    # "IR_Quest_icon": (
    #     "pixel art cartoon icon: " + PANDA_BASE + " holding a glowing infrared beacon "
    #     "device like a torch, shooting hot-pink IR signal arc waves outward, "
    #     "explorer safari hat on head, dark navy adventure background with glowing "
    #     "pink signal rings radiating out. " + STYLE
    # ),
    # "commits_breaker_icon": (
    #     "pixel art cartoon icon: " + PANDA_BASE + " playing brick breaker arcade game, "
    #     "rows of colourful bricks at top shaped like git commit squares, "
    #     "panda swinging a paddle at the bottom, green glowing ball bouncing upward, "
    #     "retro arcade cabinet style, dark background with neon colours. " + STYLE
    # ),
    "wallpaper_icon": (
        "pixel art cartoon icon: " + PANDA_BASE + " painting a tiny rectangular screen "
        "canvas with a brush, screen showing a beautiful pixel art starfield pattern "
        "with circuit board lines and glowing dots, artist smock on, paint palette "
        "in other hand, neon teal and magenta colours on canvas, white background. " + STYLE
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

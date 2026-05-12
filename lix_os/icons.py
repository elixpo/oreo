"""Icon loading with PIL-based PNG support for the simulator.

Priority:
  1. asset/icons/{icon_filename}    — PNG loaded via PIL → RGB565 bytes (runtime)
  2. assets/icons/{app_dir}.py      — pre-converted .py module (hardware-safe)
  3. None                           — caller falls back to letter tile

On hardware MicroPython PIL is not available, so only path 2 works.
Pre-convert PNGs with:  python tools/convert_asset.py asset/icons/foo.png assets/icons/foo.py --size 32 32
"""

import struct

_cache: dict = {}

ICON_SIZE = 32   # rendered at 32×32 in all icon tiles


def _png_to_rgb565(path: str, size=ICON_SIZE) -> bytes | None:
    """Load a PNG and return RGB565 big-endian bytes, or None on failure."""
    try:
        from PIL import Image
        img = Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
        bg_r, bg_g, bg_b = 8, 8, 20   # badge background colour for transparency
        pixels = []
        for y in range(size):
            for x in range(size):
                r, g, b, a = img.getpixel((x, y))
                if a < 64:
                    r, g, b = bg_r, bg_g, bg_b
                word = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                pixels.append(word)
        return struct.pack(">%dH" % len(pixels), *pixels)
    except Exception:
        return None


def load(app_dir: str, icon_filename: str | None = None) -> tuple | None:
    """Return (data_bytes, W, H) for the icon, or None if not found.

    data_bytes is RGB565 big-endian — compatible with display.blit().
    """
    key = icon_filename or app_dir
    if key in _cache:
        return _cache[key]

    result = None

    # ── Try PNG from asset/icons/ ─────────────────────────────────────────
    candidates = []
    if icon_filename:
        candidates.append("asset/icons/%s" % icon_filename)
    candidates += [
        "asset/icons/%s_icon.png" % app_dir,
        "asset/icons/%s.png"      % app_dir,
    ]
    for path in candidates:
        data = _png_to_rgb565(path)
        if data:
            result = (data, ICON_SIZE, ICON_SIZE)
            break

    # ── Fall back to pre-converted .py module ─────────────────────────────
    if result is None:
        try:
            name = (icon_filename or app_dir).replace("-", "_").replace(".", "_")
            mod  = __import__("assets.icons.%s" % name, None, None, ["DATA", "W", "H"])
            result = (mod.DATA, mod.W, mod.H)
        except (ImportError, AttributeError):
            pass

    _cache[key] = result
    return result

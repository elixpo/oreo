"""Asset optimizer for Elixpo Badge.

Takes raw PNGs from asset/icons/ (any size, from GPT Image) and produces:

  asset/icons/optimized/{name}.png   — 200×200, full-color, lossless-compressed
  assets/icons/{name}.py             — 32×32 RGB565 Python module for display.blit()

The optimized PNG keeps original colors intact (no palette quantization that
kills pixel art). The hardware .py fills any transparent/white pixels with the
badge background color so blit() looks right on the dark display.

Run from project root:
    python tools/optimize_assets.py              # all icons
    python tools/optimize_assets.py snake_icon   # single icon by stem name
"""

import sys
import struct
from pathlib import Path
from PIL import Image

# ── config ────────────────────────────────────────────────────────────────────

RAW_DIR      = Path("asset/icons")
OPT_DIR      = Path("asset/icons/optimized")
HW_DIR       = Path("assets/icons")

DISPLAY_SIZE = 200     # optimized PNG size
ICON_SIZE    = 32      # hardware blit size
BADGE_BG     = (8, 8, 20)   # badge bg color — fills transparent pixels in .py


# ── helpers ───────────────────────────────────────────────────────────────────

def _resize_clean(src: Image.Image, size: int) -> Image.Image:
    """Resize to size×size using LANCZOS, preserving RGBA."""
    return src.convert("RGBA").resize((size, size), Image.LANCZOS)


def _fill_transparent(img: Image.Image, fill_rgb: tuple) -> Image.Image:
    """Replace transparent pixels with fill_rgb, return RGB image.

    Only replaces truly transparent pixels (alpha < 128). Opaque pixels —
    including white ones — are left completely unchanged.
    """
    img = img.convert("RGBA")
    bg  = Image.new("RGBA", img.size, (fill_rgb[0], fill_rgb[1], fill_rgb[2], 255))
    bg.paste(img, mask=img.split()[3])   # paste using alpha channel as mask
    return bg.convert("RGB")


def _to_rgb565_bytes(img_rgb: Image.Image) -> bytes:
    """Convert an RGB image to RGB565 big-endian bytes."""
    w, h = img_rgb.size
    px   = img_rgb.load()
    words = []
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            words.append(((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3))
    return struct.pack(">%dH" % len(words), *words)


def _write_py_module(path: Path, data: bytes, w: int, h: int):
    words = struct.unpack_from(">%dH" % (len(data) // 2), data)
    chunk = 16
    lines = [
        '"""Auto-generated bitmap — do not edit. Re-run tools/optimize_assets.py."""',
        "W = %d" % w,
        "H = %d" % h,
        "DATA = (",
    ]
    for i in range(0, len(words), chunk):
        row = words[i:i + chunk]
        lines.append("    b'" + "".join(
            "\\x%02x\\x%02x" % (v >> 8, v & 0xFF) for v in row
        ) + "'")
    lines.append(")")
    path.write_text("\n".join(lines) + "\n")


# ── per-file processing ───────────────────────────────────────────────────────

def optimize(src: Path):
    raw_kb = src.stat().st_size // 1024
    print("  %-32s  %3dkB raw" % (src.stem, raw_kb), end="  →")

    img_raw = Image.open(src)

    # ── optimized display PNG (200×200, full color, no palette reduction) ─────
    OPT_DIR.mkdir(parents=True, exist_ok=True)
    opt_img  = _resize_clean(img_raw, DISPLAY_SIZE)
    # Composite onto white background so the PNG is RGB (no alpha needed for display)
    opt_bg   = Image.new("RGBA", opt_img.size, (255, 255, 255, 255))
    opt_bg.paste(opt_img, mask=opt_img.split()[3])
    opt_rgb  = opt_bg.convert("RGB")
    opt_out  = OPT_DIR / ("%s.png" % src.stem)
    # Save with maximum compression but no palette quantization
    opt_rgb.save(opt_out, format="PNG", optimize=True, compress_level=9)
    print("  %3dkB opt" % (opt_out.stat().st_size // 1024), end="  |")

    # ── hardware .py (32×32 RGB565, transparent → badge bg) ──────────────────
    HW_DIR.mkdir(parents=True, exist_ok=True)
    hw_img   = _resize_clean(img_raw, ICON_SIZE)
    hw_rgb   = _fill_transparent(hw_img, BADGE_BG)
    hw_data  = _to_rgb565_bytes(hw_rgb)
    hw_out   = HW_DIR / ("%s.py" % src.stem)
    _write_py_module(hw_out, hw_data, ICON_SIZE, ICON_SIZE)
    print("  %dB hw" % hw_out.stat().st_size)


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    targets = sys.argv[1:]
    sources = sorted(s for s in RAW_DIR.glob("*.png") if s.parent == RAW_DIR)
    if targets:
        sources = [s for s in sources if s.stem in targets]
    if not sources:
        print("No PNGs found in", RAW_DIR)
        return

    print("Optimizing %d icon(s)...\n" % len(sources))
    for src in sources:
        optimize(src)

    print("\nDone.")
    print("  Display PNGs  →", OPT_DIR)
    print("  Hardware .py  →", HW_DIR)


if __name__ == "__main__":
    main()

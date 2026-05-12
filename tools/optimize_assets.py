"""Asset optimizer for Elixpo Badge.

Reads raw PNGs from assets/icons/raw/ and produces:
  assets/icons/raw/{name}.png        — kept as source truth
  assets/icons/optimized/{name}.py   — 32×32 RGB565 .py module for display.blit()

For _bg suffix files, output is 80×60 (×4 scale = 320×240 screen).

Run from project root:
    python tools/optimize_assets.py              # all icons
    python tools/optimize_assets.py snake_icon   # single icon by stem name

SVG status icons:
    python tools/optimize_assets.py --status     # rasterize assets/status/raw/*.svg
"""

import sys
import struct
from pathlib import Path
from PIL import Image

# ── config ────────────────────────────────────────────────────────────────────

RAW_DIR      = Path("assets/icons/raw")
HW_DIR       = Path("assets/icons/optimized")

ICON_SIZE    = 32
BG_W         = 80
BG_H         = 60
BADGE_BG     = (255, 248, 235)   # warm cream — fills transparent pixels

STATUS_SVG_DIR = Path("assets/status/raw")
STATUS_HW_DIR  = Path("assets/status/optimized")
STATUS_SIZE    = 13
STATUS_BG      = (255, 93, 104)  # pink status bar — composite SVGs onto this


# ── helpers ───────────────────────────────────────────────────────────────────

def _resize_clean(src: Image.Image, size: int) -> Image.Image:
    return src.convert("RGBA").resize((size, size), Image.LANCZOS)


def _fill_transparent(img: Image.Image, fill_rgb: tuple) -> Image.Image:
    img = img.convert("RGBA")
    bg  = Image.new("RGBA", img.size, (fill_rgb[0], fill_rgb[1], fill_rgb[2], 255))
    bg.paste(img, mask=img.split()[3])
    return bg.convert("RGB")


def _to_rgb565_bytes(img_rgb: Image.Image) -> bytes:
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


# ── icon processing ───────────────────────────────────────────────────────────

def optimize(src: Path):
    raw_kb = src.stat().st_size // 1024
    print("  %-32s  %3dkB raw  →" % (src.stem, raw_kb), end="")

    HW_DIR.mkdir(parents=True, exist_ok=True)
    img_raw = Image.open(src)
    is_bg   = src.stem.endswith("_bg")

    if is_bg:
        hw_img  = img_raw.convert("RGBA").resize((BG_W, BG_H), Image.LANCZOS)
        hw_rgb  = _fill_transparent(hw_img, BADGE_BG)
        hw_data = _to_rgb565_bytes(hw_rgb)
        hw_out  = HW_DIR / ("%s.py" % src.stem)
        _write_py_module(hw_out, hw_data, BG_W, BG_H)
    else:
        hw_img  = _resize_clean(img_raw, ICON_SIZE)
        hw_rgb  = _fill_transparent(hw_img, BADGE_BG)
        hw_data = _to_rgb565_bytes(hw_rgb)
        hw_out  = HW_DIR / ("%s.py" % src.stem)
        _write_py_module(hw_out, hw_data, ICON_SIZE, ICON_SIZE)

    print("  %dB  → %s" % (hw_out.stat().st_size, hw_out))


# ── SVG status icon processing ────────────────────────────────────────────────

def optimize_status_svgs():
    """Rasterize SVGs to white-on-pink status icons.

    Uses the SVG alpha channel as a mask only — all opaque pixels become white,
    regardless of the original SVG fill colour.
    """
    try:
        import cairosvg
        from io import BytesIO
    except ImportError:
        print("cairosvg not installed — run: pip install cairosvg")
        return

    STATUS_HW_DIR.mkdir(parents=True, exist_ok=True)
    svgs = sorted(STATUS_SVG_DIR.glob("*.svg"))
    if not svgs:
        print("No SVGs found in", STATUS_SVG_DIR)
        return

    print("Processing %d SVG(s) from %s...\n" % (len(svgs), STATUS_SVG_DIR))
    for svg in svgs:
        name = svg.stem.replace("_icon", "").replace("bluetooh", "bluetooth")
        hi   = STATUS_SIZE * 4
        png  = cairosvg.svg2png(url=str(svg), output_width=hi, output_height=hi)
        img  = Image.open(BytesIO(png)).convert("RGBA").resize(
            (STATUS_SIZE, STATUS_SIZE), Image.LANCZOS)

        # Build white icon on pink background using alpha mask only
        alpha = img.split()[3]
        out_img = Image.new("RGB", (STATUS_SIZE, STATUS_SIZE),
                            (STATUS_BG[0], STATUS_BG[1], STATUS_BG[2]))
        white = Image.new("RGB", (STATUS_SIZE, STATUS_SIZE), (255, 255, 255))
        out_img.paste(white, mask=alpha)

        data = _to_rgb565_bytes(out_img)
        out  = STATUS_HW_DIR / ("%s.py" % name)
        _write_py_module(out, data, STATUS_SIZE, STATUS_SIZE)
        print("  %-30s → %s" % (svg.name, out))


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    if "--status" in sys.argv:
        optimize_status_svgs()
        return

    targets = [a for a in sys.argv[1:] if not a.startswith("--")]
    sources = sorted(s for s in RAW_DIR.glob("*.png") if s.parent == RAW_DIR)
    if targets:
        sources = [s for s in sources if s.stem in targets]
    if not sources:
        print("No PNGs found in", RAW_DIR)
        return

    print("Optimizing %d icon(s)...\n" % len(sources))
    for src in sources:
        optimize(src)
    print("\nDone.  Hardware .py  →", HW_DIR)


if __name__ == "__main__":
    main()

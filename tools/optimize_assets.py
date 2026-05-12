"""Asset optimizer for Elixpo Badge.

Top-level icons (32×32):
  assets/icons/raw/{name}.png   →   assets/icons/optimized/{name}.py

Status icons (13×13 white-on-pink, rasterized from SVG):
  assets/status/raw/*.svg       →   assets/status/optimized/*.py

Per-app sprites/backgrounds (arbitrary size via SIZES table or _bg suffix):
  apps/<app>/assets/raw/*.png   →   apps/<app>/assets/optimized/*.py

Run from project root:
    python tools/optimize_assets.py                 # all top-level icons
    python tools/optimize_assets.py snake_icon      # single icon
    python tools/optimize_assets.py --status        # SVG status icons
    python tools/optimize_assets.py --app flappy    # all sprites in apps/flappy/assets/raw
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

# Chroma-key magenta. Packs to RGB565 0xF81F (bytes [0xF8, 0x1F]). Any sprite
# pixel matching this value is treated as transparent by display.blit().
CHROMA_KEY = (248, 0, 248)

# Per-app: fill for OPAQUE assets (transparent pixels get this colour, no key).
PER_APP_FILL = {
    "flappy":   (120, 200, 240),
}

# Per-app: stems that should be treated as OPAQUE (no chroma key, full coverage).
# Everything else uses CHROMA_KEY as the transparent fill.
PER_APP_OPAQUE = {
    "flappy":   {"background", "grass"},
}

# Per-app asset target sizes (W, H) by file stem.
# Names matching neither this table nor _bg fall back to 32×32.
PER_APP_SIZES = {
    # flappy game — sprite sizes chosen for chroma-key transparency on hardware
    "panda_up_a":   (24, 24),   # alive frame 0 — idle engine
    "panda_up_b":   (24, 24),   # alive frame 1 — exhaust on (alternates with _a)
    "panda_down":   (24, 24),   # falling
    "panda_crash":  (24, 24),   # death frame 0 — tumbling
    "panda_blast":  (24, 24),   # death frame 1 — explosion
    "obstacle":     (24, 80),   # tall pipe segment so 1-2 blits cover a column
    "background":   (80, 48),   # ×4 scale at app init → 320×192 full bg
    "cloud":        (40, 20),
    "grass":        (80, 16),   # full-width tile, taller for thicker grass strip
}


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

def optimize_app(app_name, fill_override=None):
    """Optimize app sprites → optimized/*.py.

    Sources (per-file preference):
      apps/<app>/assets/transparent/<name>.png  (background removed — preferred)
      apps/<app>/assets/raw/<name>.png          (fallback)

    Cleared (alpha=0) pixels are filled with:
      • PER_APP_FILL[app] (e.g. sky blue) for stems in PER_APP_OPAQUE[app]
      • CHROMA_KEY magenta for everything else → blit() treats as transparent
    """
    raw_dir  = Path("apps") / app_name / "assets" / "raw"
    tr_dir   = Path("apps") / app_name / "assets" / "transparent"
    out_dir  = Path("apps") / app_name / "assets" / "optimized"
    out_dir.mkdir(parents=True, exist_ok=True)

    opaque_fill = fill_override or PER_APP_FILL.get(app_name, BADGE_BG)
    opaque_set  = PER_APP_OPAQUE.get(app_name, set())

    raw_pngs = sorted(raw_dir.glob("*.png"))
    sources  = []
    for r in raw_pngs:
        tr = tr_dir / r.name
        sources.append(tr if tr.exists() else r)

    if not sources:
        print("No raw PNGs in", raw_dir)
        return

    print("Optimizing %d asset(s) for app '%s'  [opaque-fill=rgb%s, chroma-key=rgb%s]...\n"
          % (len(sources), app_name, opaque_fill, CHROMA_KEY))
    for src in sources:
        size = PER_APP_SIZES.get(src.stem)
        if size is None:
            size = (BG_W, BG_H) if src.stem.endswith("_bg") else (ICON_SIZE, ICON_SIZE)

        w, h = size
        is_opaque = src.stem in opaque_set
        fill      = opaque_fill if is_opaque else CHROMA_KEY

        img_raw  = Image.open(src)
        hw_img   = img_raw.convert("RGBA").resize((w, h), Image.LANCZOS)
        hw_rgb   = _fill_transparent(hw_img, fill)
        hw_data  = _to_rgb565_bytes(hw_rgb)
        out      = out_dir / ("%s.py" % src.stem)
        _write_py_module(out, hw_data, w, h)
        kind = "opaque" if is_opaque else "key"
        print("  %-25s  →  %dx%d  %5dB  [%s]" %
              (src.stem, w, h, out.stat().st_size, kind))


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

    if "--app" in sys.argv:
        idx = sys.argv.index("--app")
        if idx + 1 >= len(sys.argv):
            print("Usage: optimize_assets.py --app <app_name> [--fill R,G,B]")
            return
        app = sys.argv[idx + 1]
        # Optional --fill R,G,B override
        fill = None
        if "--fill" in sys.argv:
            fi = sys.argv.index("--fill")
            if fi + 1 < len(sys.argv):
                try:
                    fill = tuple(int(x) for x in sys.argv[fi + 1].split(","))
                    if len(fill) != 3:
                        raise ValueError
                except ValueError:
                    print("--fill expects R,G,B (e.g. 120,200,240)")
                    return
        optimize_app(app, fill_override=fill)
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

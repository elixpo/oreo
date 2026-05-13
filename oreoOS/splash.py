"""Animated boot splash — Oreo OS, 320×240 landscape.

Sequence (~2.6 s):
  0.00–0.25  fancy background fades in (dimmed)
  0.10–0.55  mascot drops down from above the screen, settles centre-top
  0.55–0.85  "OREO OS" title types in, scale=3 bright white
  0.80–1.05  "Built By a GenZ" tagline fades in beneath the title
  1.05–2.10  loading bar fills
  2.30–2.60  white-out + fade to black

The background prefers `assets/sprites/optimized/splash_bg.py` (run
`tools/optimize_assets.py splash_bg` after dropping a raw image into
`assets/sprites/raw/`). When that file is absent we paint a procedural
warm confetti-tone gradient so the splash still looks intentional on a
fresh checkout.
"""

import struct
import time
from oreoOS import api
from oreoOS import theme

SW = api.SCREEN_W
SH = api.SCREEN_H

# ── layout (centred vertical stack) ──────────────────────────────────────────
# Logo (72×72) → "OREO OS" title → "Built By a GenZ" tagline → loading bar.

_MW, _MH       = 72, 72
_LOGO_REST_Y   = 30                       # final mascot top y
_TITLE_Y       = _LOGO_REST_Y + _MH + 12  # below logo
_TAGLINE_Y     = _TITLE_Y + 30            # below title (scale=3 → 24 px tall)
_BAR_W         = SW - 80
_BAR_X         = (SW - _BAR_W) // 2
_BAR_Y         = SH - 30

TOTAL_MS       = 2600
TAGLINE        = "Built By a GenZ"
TITLE          = "OREO OS"
BG_DIM         = 0.30          # fraction of original brightness


# ── mascot loader (cached) ───────────────────────────────────────────────────

_mascot = None

def _get_mascot():
    global _mascot
    if _mascot is not None:
        return _mascot if _mascot is not False else None
    try:
        from PIL import Image
        img = Image.open("assets/sprites/raw/mascot.png").convert("RGBA").resize(
            (_MW, _MH), Image.LANCZOS)
        bg = Image.new("RGBA", (_MW, _MH), (theme.BG_R, theme.BG_G, theme.BG_B, 255))
        bg.paste(img, mask=img.split()[3])
        rgb = bg.convert("RGB")
        px  = rgb.load()
        words = []
        for y in range(_MH):
            for x in range(_MW):
                r, g, b = px[x, y]
                words.append(((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3))
        data = struct.pack(">%dH" % len(words), *words)
        _mascot = (data, _MW, _MH)
        return _mascot
    except Exception:
        pass
    try:
        import assets.sprites.optimized.mascot as m
        _mascot = (m.DATA, m.W, m.H)
        return _mascot
    except (ImportError, AttributeError):
        pass
    _mascot = False
    return None


# ── dimmed background (cached) ───────────────────────────────────────────────

_bg = None

def _dim_buf(src, factor):
    """RGB565 big-endian bytes → new bytearray, every pixel × factor."""
    n   = len(src) // 2
    out = bytearray(len(src))
    fac = int(factor * 256)
    for i in range(n):
        v = (src[i*2] << 8) | src[i*2 + 1]
        r = ((v >> 11) & 0x1F) * fac >> 8
        g = ((v >>  5) & 0x3F) * fac >> 8
        b = ( v        & 0x1F) * fac >> 8
        v2 = (r << 11) | (g << 5) | b
        out[i*2]     = v2 >> 8
        out[i*2 + 1] = v2 & 0xFF
    return out


def _get_bg():
    """Return (data, w, h) for a full-screen dimmed splash backdrop, or None."""
    global _bg
    if _bg is not None:
        return _bg if _bg is not False else None
    try:
        import assets.sprites.optimized.splash_bg as m
        if m.W == SW and m.H == SH:
            _bg = (_dim_buf(m.DATA, BG_DIM), SW, SH)
            return _bg
    except (ImportError, AttributeError):
        pass
    _bg = False
    return None


# ── procedural fallback bg (festive gradient + confetti dots) ────────────────

def _draw_procedural_bg(d):
    """Three-band vertical gradient (pink → cream → gold) with a sparse
    deterministic confetti scatter. Theme-on-brand so the splash looks
    intentional even before a real backdrop asset has been baked."""
    for y in range(SH):
        if y < SH // 3:
            t = y / (SH // 3)
            r = int(theme.PRIMARY_R * (1 - t) + theme.BG_R * t * 0.7)
            g = int(theme.PRIMARY_G * (1 - t) + theme.BG_G * t * 0.7)
            b = int(theme.PRIMARY_B * (1 - t) + theme.BG_B * t * 0.7)
        elif y > (2 * SH) // 3:
            t = (y - 2 * SH // 3) / (SH // 3)
            r = int(theme.BG_R * (1 - t) * 0.7 + theme.GOLD_R * t)
            g = int(theme.BG_G * (1 - t) * 0.7 + theme.GOLD_G * t)
            b = int(theme.BG_B * (1 - t) * 0.7 + theme.GOLD_B * t)
        else:
            r, g, b = int(theme.BG_R * 0.6), int(theme.BG_G * 0.55), int(theme.BG_B * 0.5)
        d.rect(0, y, SW, 1, api.rgb(r, g, b), fill=True)
    seed = 0xC0FFEE
    palette = [theme.PRIMARY, theme.GOLD, theme.TEAL]
    for _ in range(60):
        seed = (seed * 1103515245 + 12345) & 0xFFFFFFFF
        x = seed % SW
        seed = (seed * 1103515245 + 12345) & 0xFFFFFFFF
        y = seed % SH
        # avoid the centre 200×130 strip where the logo / title sit
        if (SW - 200) // 2 < x < (SW + 200) // 2 and \
           (SH - 130) // 2 < y < (SH + 130) // 2:
            continue
        col = palette[seed % 3]
        sz  = 2 + (seed >> 4) % 3
        d.rect(x, y, sz, sz, col, fill=True)


# ── helpers ──────────────────────────────────────────────────────────────────

def _ms():       return time.ticks_ms()
def _diff(a, b): return time.ticks_diff(a, b)

def _phase(elapsed, s, e):
    t = elapsed / TOTAL_MS
    if t < s:  return 0.0
    if t >= e: return 1.0
    return (t - s) / (e - s)


def _draw_text_centered(d, s, y, color, scale=1):
    w = len(s) * 8 * scale
    d.text(s, (SW - w) // 2, y, color, scale=scale)


# ── show_splash ──────────────────────────────────────────────────────────────

def show_splash(os_obj):
    d     = os_obj.display
    start = _ms()
    bg    = _get_bg()
    bg_drawn = False

    while True:
        elapsed = _diff(_ms(), start)
        if elapsed >= TOTAL_MS:
            break

        # Background — paint once, then reuse. The logo / text draw on top
        # of the same pixels every frame; redrawing the full bg per frame
        # would blow the 30-fps budget without a backbuffer.
        if not bg_drawn:
            if bg:
                data, bw, bh = bg
                d.blit(data, 0, 0, bw, bh)
            else:
                _draw_procedural_bg(d)
            bg_drawn = True

        # ── logo: slides down from y=-mh to y=_LOGO_REST_Y (ease-out cubic)
        p_logo = _phase(elapsed, 0.04, 0.21)
        if p_logo > 0:
            mascot = _get_mascot()
            y      = int(-_MH + (_LOGO_REST_Y + _MH) * (1 - (1 - p_logo) ** 3))
            if mascot:
                data, mw, mh = mascot
                try:
                    d.blit(data, (SW - mw) // 2, y, mw, mh)
                except Exception:
                    d.rect((SW - _MW) // 2, y, _MW, _MH, theme.PRIMARY, fill=True)
            else:
                d.rect((SW - _MW) // 2, y, _MW, _MH, theme.PRIMARY, fill=True)

        # ── title: types in, scale=3 bright white ──────────────────────────
        p_title = _phase(elapsed, 0.21, 0.33)
        if p_title > 0:
            n = max(1, int(p_title * len(TITLE)))
            _draw_text_centered(d, TITLE[:n], _TITLE_Y, api.WHITE, scale=3)

        # ── tagline: appears once title finishes typing ────────────────────
        p_tag = _phase(elapsed, 0.31, 0.40)
        if p_tag > 0:
            _draw_text_centered(d, TAGLINE, _TAGLINE_Y, theme.GOLD, scale=2)

        # ── loading bar ────────────────────────────────────────────────────
        p_bar = _phase(elapsed, 0.40, 0.81)
        if p_bar > 0:
            d.rect(_BAR_X, _BAR_Y, _BAR_W, 5, api.rgb(80, 60, 60), fill=True)
            filled = max(2, int(p_bar * _BAR_W))
            d.rect(_BAR_X, _BAR_Y, filled, 5, theme.PRIMARY, fill=True)

        # ── final fade ─────────────────────────────────────────────────────
        p_fade = _phase(elapsed, 0.88, 1.00)
        if p_fade >= 1.0:
            d.clear(api.BLACK)

        d.present()
        time.sleep_ms(20)

    d.clear(api.BLACK)
    d.present()

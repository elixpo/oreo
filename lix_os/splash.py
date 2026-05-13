"""Animated boot splash — Elixpo OS, 320×240 landscape.

Sequence (~3 s):
  0.00–0.30  gradient background sweeps in
  0.20–0.80  mascot fades in (row-reveal top→bottom)
  0.70–1.20  "OREO" types in
  1.10–1.50  "OS" appears
  1.40–2.10  loading bar fills
  2.60–3.00  fade to black
"""

import struct
import time
from lix import api
from lix_os import theme

SW = api.SCREEN_W   # 320
SH = api.SCREEN_H   # 240

# ── layout ────────────────────────────────────────────────────────────────────
# Single-line: [MASCOT] ELIXPO OS   (mascot left, text right, vertically centred)

_MW, _MH = 72, 72
_MX  = 24
_MY  = (SH - _MH) // 2          # 84
_TX  = _MX + _MW + 16           # 112 — text starts right of mascot
_TY  = _MY + (_MH - 16) // 2    # vertically centre 16px text (scale=2→16px tall)
_BAR_X = 20
_BAR_Y = SH - 28
_BAR_W = SW - 40

TOTAL_MS = 5000

# ── mascot loader (cached) ────────────────────────────────────────────────────

_mascot = None

def _get_mascot():
    global _mascot
    if _mascot is not None:
        return _mascot if _mascot is not False else None
    # Try PIL first — composites cleanly on cream BG (works on sim; no PIL on hw)
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
    # Hardware fallback — uses pre-baked assets/sprites/optimized/mascot.py
    try:
        import assets.sprites.optimized.mascot as m
        _mascot = (m.DATA, m.W, m.H)
        return _mascot
    except (ImportError, AttributeError):
        pass
    _mascot = False
    return None

# ── helpers ───────────────────────────────────────────────────────────────────

def _ms():     return time.ticks_ms()
def _diff(a, b): return time.ticks_diff(a, b)

def _phase(elapsed, s, e):
    t = elapsed / TOTAL_MS
    if t < s:  return 0.0
    if t >= e: return 1.0
    return (t - s) / (e - s)

def _lerp(a, b, t):
    return int(a + (b - a) * t)

def _draw_gradient(d):
    """Warm celebration gradient: pink at top → cream in center → gold at bottom."""
    d.rect(0, 0, SW, SH, api.rgb(theme.BG_R, theme.BG_G, theme.BG_B), fill=True)
    # pink sweep from top
    for y in range(60):
        t = (1.0 - y / 60) ** 2
        r = _lerp(theme.BG_R, theme.PRIMARY_R, t)
        g = _lerp(theme.BG_G, theme.PRIMARY_G, t)
        b = _lerp(theme.BG_B, theme.PRIMARY_B, t)
        d.rect(0, y, SW, 1, api.rgb(r, g, b), fill=True)
    # gold sweep from bottom
    for y in range(SH - 50, SH):
        t = ((y - (SH - 50)) / 50) ** 2
        r = _lerp(theme.BG_R, theme.GOLD_R, t)
        g = _lerp(theme.BG_G, theme.GOLD_G, t)
        b = _lerp(theme.BG_B, theme.GOLD_B, t)
        d.rect(0, y, SW, 1, api.rgb(r, g, b), fill=True)

# ── show_splash ───────────────────────────────────────────────────────────────

def show_splash(os_obj):
    d     = os_obj.display
    start = _ms()
    drawn_bg = False

    while True:
        elapsed = _diff(_ms(), start)
        if elapsed >= TOTAL_MS:
            break

        if not drawn_bg:
            _draw_gradient(d)
            drawn_bg = True

        # all phase fractions are within 0.0–1.0 of TOTAL_MS=5000
        p1 = _phase(elapsed, 0.00, 0.08)   # teal sweep:  0–400ms
        if p1 > 0:
            lx = int(p1 * SW)
            d.rect(0, _BAR_Y - 6, lx, 1, theme.TEAL, fill=True)

        # mascot pops in all at once (no row-reveal)
        p2 = _phase(elapsed, 0.10, 0.12)   # trigger:     500ms–600ms
        if p2 >= 1.0:
            mascot = _get_mascot()
            if mascot:
                data, mw, mh = mascot
                try:
                    d.blit(data, _MX, _MY, mw, mh)
                except Exception:
                    d.rect(_MX, _MY, _MW, _MH, theme.PRIMARY, fill=True)
            else:
                d.rect(_MX, _MY, _MW, _MH, theme.PRIMARY, fill=True)

        p3 = _phase(elapsed, 0.18, 0.52)   # "OREO OS" types in: 900ms–2600ms
        if p3 > 0:
            label = "OREO OS"
            n = max(1, int(p3 * len(label)))
            d.text(label[:n], _TX, _TY, theme.TEXT_BRIGHT, scale=2)

        p5 = _phase(elapsed, 0.58, 0.88)   # loading bar: 2900ms–4400ms
        if p5 > 0:
            d.rect(_BAR_X, _BAR_Y, _BAR_W, 5, api.rgb(200, 180, 160), fill=True)
            filled = max(2, int(p5 * _BAR_W))
            d.rect(_BAR_X, _BAR_Y, filled, 5, theme.PRIMARY, fill=True)
            pct = int(p5 * 100)
            d.text("%d%%" % pct, _BAR_X + _BAR_W + 6, _BAR_Y - 2, theme.MUTED)

        p6 = _phase(elapsed, 0.92, 1.00)   # fade:        4600ms–5000ms
        if p6 >= 1.0:
            d.clear(api.BLACK)

        d.present()

    d.clear(api.BLACK)
    d.present()

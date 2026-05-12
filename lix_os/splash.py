"""Animated boot splash — Elixpo OS, 320×240 landscape.

Sequence (~3 s):
  0.00–0.30  gradient background sweeps in
  0.20–0.80  mascot fades in (row-reveal top→bottom)
  0.70–1.20  "ELIXPO" types in
  1.10–1.50  "BADGE OS" appears
  1.40–2.10  loading bar fills
  2.60–3.00  fade to black
"""

import struct
import time
from lix import api
from lix_os import theme
from lix_os.panda import draw_panda, PANDA_W, PANDA_H

SW = api.SCREEN_W   # 320
SH = api.SCREEN_H   # 240

# ── layout ────────────────────────────────────────────────────────────────────

_MW, _MH = 72, 72
_MX = 30
_MY = (SH - _MH) // 2        # 84
_TX = _MX + _MW + 20         # 122
_TY = _MY + 4
_SUB_Y = _TY + 40
_VER_Y = _SUB_Y + 20
_BAR_X = 20
_BAR_Y = SH - 28
_BAR_W = SW - 40

TOTAL_MS = 3000

# ── mascot loader (cached) ────────────────────────────────────────────────────

_mascot = None

def _get_mascot():
    global _mascot
    if _mascot is not None:
        return _mascot if _mascot is not False else None
    try:
        import assets.mascot as m
        _mascot = (m.DATA, m.W, m.H)
        return _mascot
    except (ImportError, AttributeError):
        pass
    try:
        from PIL import Image
        img = Image.open("asset/mascot.png").convert("RGBA").resize(
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
    """Vertical gradient: dark at edges, warm glow at centre."""
    mid = SH // 2
    for y in range(SH):
        dist = abs(y - mid) / mid
        t    = 1.0 - dist * dist
        r = _lerp(theme.BG_R, 0,  t)
        g = _lerp(theme.BG_G, 70, t)
        b = _lerp(theme.BG_B, 65, t)
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

        p1 = _phase(elapsed, 0.0, 0.30)
        if p1 > 0:
            lx = int(p1 * SW)
            d.rect(0, _BAR_Y - 6, lx, 1, theme.TEAL, fill=True)

        p2 = _phase(elapsed, 0.20, 0.80)
        if p2 > 0:
            mascot = _get_mascot()
            if mascot:
                data, mw, mh = mascot
                rows = max(1, int(p2 * mh))
                try:
                    d.blit(data, _MX, _MY, mw, min(mh, rows))
                except Exception:
                    draw_panda(d, _MX, _MY, ps=4,
                               max_rows=max(1, int(p2 * PANDA_H)))
            else:
                draw_panda(d, _MX, _MY, ps=4,
                           max_rows=max(1, int(p2 * PANDA_H)))

        p3 = _phase(elapsed, 0.70, 1.20)
        if p3 > 0:
            n = max(1, int(p3 * 6))
            d.text("ELIXPO"[:n], _TX, _TY, theme.TEXT_BRIGHT, scale=4)

        p4 = _phase(elapsed, 1.10, 1.50)
        if p4 > 0:
            n = max(1, int(p4 * 8))
            d.text("BADGE OS"[:n], _TX + 4, _SUB_Y, theme.TEAL, scale=2)
            if p4 > 0.9:
                d.text("v0.1", _TX + 4, _VER_Y, theme.MUTED)

        p5 = _phase(elapsed, 1.40, 2.10)
        if p5 > 0:
            d.rect(_BAR_X, _BAR_Y, _BAR_W, 5, api.rgb(30, 26, 40), fill=True)
            filled = max(2, int(p5 * _BAR_W))
            d.rect(_BAR_X, _BAR_Y, filled, 5, theme.PRIMARY, fill=True)
            pct = int(p5 * 100)
            d.text("%d%%" % pct, _BAR_X + _BAR_W + 6, _BAR_Y - 2, theme.MUTED)

        p6 = _phase(elapsed, 2.60, 3.00)
        if p6 >= 1.0:
            d.clear(api.BLACK)

        d.present()

    d.clear(api.BLACK)
    d.present()

"""Animated boot splash for Elixpo OS.

Sequence (total ≈ 3 seconds):
  0.00–0.25s  dark bg + accent scanline sweep top→bottom
  0.15–0.70s  panda materialises row-by-row from top
  0.60–1.10s  "ELIXPO" letters type in left→right at scale 4
  1.00–1.40s  "BADGE OS" subtitle appears + version
  1.30–1.90s  loading bar fills left→right
  1.90–2.60s  hold + gentle pulse on accent rails
  2.60–3.00s  fade to black (clear) → hand off to home screen
"""

import time
import struct
from lix import api
from lix_os.panda import draw_panda, PANDA_W, PANDA_H

# mascot sprite — loaded once, falls back to pixel panda if missing
_mascot = None

def _get_mascot():
    global _mascot
    if _mascot is not None:
        return _mascot
    try:
        import assets.mascot as m
        _mascot = (m.DATA, m.W, m.H)
        return _mascot
    except (ImportError, AttributeError):
        pass
    try:
        from PIL import Image
        import struct
        img = Image.open("asset/mascot.png").convert("RGBA").resize((72, 72), Image.LANCZOS)
        bg = Image.new("RGBA", (72, 72), (8, 8, 20, 255))
        bg.paste(img, mask=img.split()[3])
        rgb = bg.convert("RGB")
        px = rgb.load()
        words = []
        for y in range(72):
            for x in range(72):
                r, g, b = px[x, y]
                words.append(((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3))
        data = struct.pack(">%dH" % len(words), *words)
        _mascot = (data, 72, 72)
    except Exception:
        _mascot = False  # sentinel: skip, use pixel panda
    return _mascot

# --- timing ------------------------------------------------------------------

def _ms():
    return time.ticks_ms()

def _diff(a, b):
    return time.ticks_diff(a, b)


# --- palette -----------------------------------------------------------------

BG      = api.rgb(8, 8, 20)
PRIMARY = api.rgb(0, 220, 200)
ACCENT  = api.rgb(255, 80, 200)
MUTED   = api.rgb(120, 120, 150)
_BLACK  = api.BLACK

# --- panda position (ps=4 → 80×72 px) ---------------------------------------

_PS     = 4
_PW     = PANDA_W * _PS   # 80
_PH     = PANDA_H * _PS   # 72
_PANDA_X = (api.SCREEN_W - _PW) // 2   # 80
_PANDA_Y = 20

# "ELIXPO" at scale=4: 6 chars × 32px = 192px → x=24 to x=216
_TEXT_X   = 24
_TEXT_Y   = _PANDA_Y + _PH + 8       # just below panda
_SUB_Y    = _TEXT_Y + 38             # "BADGE OS" scale=2
_VER_Y    = _SUB_Y + 20
_BAR_X    = 20
_BAR_Y    = _VER_Y + 18
_BAR_W    = api.SCREEN_W - 40

TOTAL_MS  = 3000


def _lerp(a, b, t):
    return a + (b - a) * t


def _phase(elapsed, start_frac, end_frac):
    """Return 0.0–1.0 for a sub-range of the splash, clamped."""
    t = elapsed / TOTAL_MS
    if t < start_frac:
        return 0.0
    if t >= end_frac:
        return 1.0
    return (t - start_frac) / (end_frac - start_frac)


def show_splash(os_obj):
    d     = os_obj.display
    start = _ms()

    while True:
        elapsed = _diff(_ms(), start)
        if elapsed >= TOTAL_MS:
            break

        d.clear(BG)

        # ── Phase 1: scanline sweep (0–0.25 s) ────────────────────────────
        p1 = _phase(elapsed, 0.0, 0.25)
        if p1 > 0:
            sy = int(p1 * api.SCREEN_H)
            # Fading trail
            d.rect(0, max(0, sy - 30), api.SCREEN_W, 30, api.rgb(0, 40, 35), fill=True)
            d.rect(0, max(0, sy - 3),  api.SCREEN_W,  3, PRIMARY, fill=True)

        # ── Phase 2: mascot/panda reveal (0.15–0.72 s) ───────────────────
        p2 = _phase(elapsed, 0.15, 0.72)
        if p2 > 0:
            mascot = _get_mascot()
            if mascot and mascot is not False:
                data, mw, mh = mascot
                # Reveal rows top-down by clipping draw area
                rows_visible = max(1, int(p2 * mh))
                mx = _PANDA_X - (mw - _PW) // 2   # centre the 72px sprite
                # blit the sprite; rows below visible count are still BG
                try:
                    d.blit(data, mx, _PANDA_Y, mw, min(mh, rows_visible))
                except Exception:
                    draw_panda(d, _PANDA_X, _PANDA_Y, ps=_PS, max_rows=max(1, int(p2 * PANDA_H)))
            else:
                rows = max(1, int(p2 * PANDA_H))
                draw_panda(d, _PANDA_X, _PANDA_Y, ps=_PS, max_rows=rows)

        # ── Phase 3: "ELIXPO" types in (0.60–1.10 s) ─────────────────────
        p3 = _phase(elapsed, 0.60, 1.10)
        if p3 > 0:
            n = max(1, int(p3 * 6))
            d.text("ELIXPO"[:n], _TEXT_X, _TEXT_Y, PRIMARY, scale=4)

        # ── Phase 4: subtitle + version (1.00–1.45 s) ────────────────────
        p4 = _phase(elapsed, 1.00, 1.45)
        if p4 > 0:
            # Fade in by character count
            n_sub = max(1, int(p4 * 8))
            d.text("BADGE OS"[:n_sub], 72, _SUB_Y, api.WHITE, scale=2)
            if p4 > 0.8:
                d.text("v0.1", 100, _VER_Y, MUTED)

        # ── Phase 5: loading bar (1.30–2.00 s) ───────────────────────────
        p5 = _phase(elapsed, 1.30, 2.00)
        if p5 > 0:
            d.rect(_BAR_X, _BAR_Y, _BAR_W, 5, api.rgb(25, 25, 40), fill=True)
            filled = int(p5 * _BAR_W)
            if filled > 0:
                d.rect(_BAR_X, _BAR_Y, filled, 5, PRIMARY, fill=True)
            # loading label
            pct = int(p5 * 100)
            d.text("%d%%" % pct, _BAR_X + _BAR_W + 4, _BAR_Y - 2, MUTED)

        # ── Phase 6: accent rails pulse (1.90–2.60 s) ────────────────────
        p6 = _phase(elapsed, 1.90, 2.60)
        if p6 > 0:
            # Pulse between PRIMARY and ACCENT
            pulse = abs((p6* 2) % 2 - 1)  # triangle wave 0→1→0→1...
            rail_c = api.rgb(
                int(_lerp(0, 255, pulse)),
                int(_lerp(220, 80, pulse)),
                int(_lerp(200, 200, pulse)),
            )
            d.rect(20, _TEXT_Y - 6, api.SCREEN_W - 40, 2, rail_c, fill=True)
            d.rect(20, _BAR_Y + 10, api.SCREEN_W - 40, 2, rail_c, fill=True)

        # ── Phase 7: fade to black (2.60–3.00 s) ─────────────────────────
        p7 = _phase(elapsed, 2.60, 3.00)
        if p7 > 0:
            # Overlay semi-transparent black using repeated dark rect
            # (no alpha on framebuf — fake it with a dark rect at increasing opacity)
            lvl = int(p7 * 8)
            fade_c = api.rgb(lvl, lvl, lvl + 2)
            for _ in range(int(p7 * 6)):
                d.rect(0, 0, api.SCREEN_W, api.SCREEN_H, _BLACK, fill=True)

        d.present()

    # Final clear
    d.clear(_BLACK)
    d.present()

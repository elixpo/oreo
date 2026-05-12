"""Elixpo mascot — pixel panda sprite and draw helpers.

The sprite is a 20-column × 18-row grid.  Each 'pixel' is rendered as a
ps×ps block of real display pixels, so at ps=4 the panda is 80×72 display px.

Characters:
  ' ' = transparent (skip)
  'W' = white
  'B' = dark (near-black, not pure black so it pops on dark backgrounds)
"""

from lix import api

# fmt: off
PANDA = [
    "    BBBB    BBBB    ",  #  0: ears
    "    BWWB    BWWB    ",  #  1: ear inner
    "    BBBB    BBBB    ",  #  2: ear base
    "   WWWWWWWWWWWWWW   ",  #  3: forehead
    "  WWWWWWWWWWWWWWWW  ",  #  4
    " WWWWWWWWWWWWWWWWWW ",  #  5
    " WWBBBBWWWWWWBBBBWW ",  #  6: eye patches top
    " WWBWBBWWWWWWBBWBWW ",  #  7: eyes (W = shine dot)
    " WWBBBBWWWWWWBBBBWW ",  #  8: eye patches bottom
    " WWWWWWWWWWWWWWWWWW ",  #  9: cheeks
    " WWWWWWWWBBWWWWWWWW ",  # 10: nose
    " WWWWWWWWBBWWWWWWWW ",  # 11: nose
    " WWWWWWWWWWWWWWWWWW ",  # 12: lower cheeks
    " WWWWWWWWWWWWWWWWWW ",  # 13
    "  WWWWWWWWWWWWWWWW  ",  # 14: chin
    "   WWWWWWWWWWWWWW   ",  # 15
    "    WWWWWWWWWWWW    ",  # 16
    "     WWWWWWWWWW     ",  # 17
]
# fmt: on

PANDA_W = 20
PANDA_H = 18

_W = api.WHITE
_B = api.rgb(18, 18, 22)


def draw_panda(d, x, y, ps=4, max_rows=None):
    """Draw the panda mascot at (x, y).

    ps       — pixels per panda-grid-cell (default 4 → 80×72 px)
    max_rows — reveal rows 0..max_rows-1 only (None = draw all)
    """
    n = PANDA_H if max_rows is None else min(max_rows, PANDA_H)
    for row in range(n):
        line = PANDA[row]
        for col in range(PANDA_W):
            ch = line[col]
            if ch == ' ':
                continue
            color = _W if ch == 'W' else _B
            d.rect(x + col * ps, y + row * ps, ps, ps, color, fill=True)


def panda_pixel_w(ps=4):
    return PANDA_W * ps

def panda_pixel_h(ps=4):
    return PANDA_H * ps

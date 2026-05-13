"""Shared UI widgets used across Elixpo OS apps.

Goal: every app has the same visual chrome (header bar, hint footer, panel
backgrounds) so the OS feels cohesive. Apps just call:

    from lix_os import widgets
    widgets.draw_header(d, "SETTINGS")
    widgets.draw_hint  (d, "A=select  HOME=back")

and the look is consistent.
"""

from lix import api
from lix_os import theme

HEADER_H = 26
HINT_H   = 16


def draw_header(d, title, color=None):
    """Pink app header with a centred title in framebuf 8×8 (scale=2).

    Drawn at the top of the screen. Single C-call text render — cheap to
    repaint every frame.
    """
    SW = api.SCREEN_W
    bg = color or theme.STATUS_BG
    d.rect(0, 0, SW, HEADER_H, bg, fill=True)
    d.rect(0, HEADER_H - 1, SW, 1, theme.PRIMARY, fill=True)   # accent line
    tx = (SW - len(title) * 8 * 2) // 2
    d.text(title, tx, (HEADER_H - 16) // 2, api.WHITE, scale=2)


def draw_hint(d, text, color=None):
    """Small grey hint text at the very bottom of the screen.

    Use for "press X for Y" prompts so apps don't have to handcode the bar.
    """
    SW = api.SCREEN_W
    SH = api.SCREEN_H
    y  = SH - HINT_H
    d.rect(0, y, SW, HINT_H, theme.DOCK_BG, fill=True)
    tx = (SW - len(text) * 8) // 2
    d.text(text, tx, y + 4, color or theme.TEXT_BRIGHT)


def draw_panel(d, x, y, w, h, color=None, border=True):
    """Filled panel + optional accent border. Useful for cards / dialogs."""
    fill_color = color or theme.CARD
    d.rect(x, y, w, h, fill_color, fill=True)
    if border:
        d.rect(x, y, w, 1, theme.PRIMARY, fill=True)
        d.rect(x, y + h - 1, w, 1, theme.PRIMARY, fill=True)


def play_area():
    """(x, y, w, h) of the screen region between header and hint bar."""
    SW = api.SCREEN_W
    SH = api.SCREEN_H
    return (0, HEADER_H, SW, SH - HEADER_H - HINT_H)

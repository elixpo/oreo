"""Elixpo OS home screen.

Layout (240×320):
  ┌─ status bar (y=0, h=24) ─────────────────────────────┐
  │  HH:MM        Day DD Mon   [wifi] [bt] [bat]          │
  ├──────────────────────────────────────────────────────-┤
  │                                                       │
  │            [panda ps=2 → 40×36px]                    │
  │                                                       │
  │              HH : MM                  (scale 4)       │
  │                        :SS            (scale 2)       │
  │           Day, DD Month Year          (scale 1)       │
  │                                                       │
  ├──────────────────────────────────────────────────────-┤
  │  bottom dock — app icon squares                       │
  └───────────────────────────────────────────────────────┘

Navigation:
  LEFT / RIGHT  — move between dock icons
  A             — open selected dock icon (apps panel)
"""

import time
from lix import api
from lix_os import timeutil
from lix_os.panda import draw_panda

import lix

# ── palette ──────────────────────────────────────────────────────────────────

BG       = api.rgb(8, 8, 20)
PRIMARY  = api.rgb(0, 220, 200)
ACCENT   = api.rgb(255, 80, 200)
MUTED    = api.rgb(100, 100, 130)
STATUS   = api.rgb(15, 15, 32)
DOCK_BG  = api.rgb(18, 18, 36)
DOCK_SEL = api.rgb(0, 180, 160)

# App-icon palette (cycles over apps in dock)
_ICON_COLORS = [
    api.rgb(255, 80, 200),   # magenta
    api.rgb(0, 200, 255),    # cyan
    api.rgb(255, 160, 0),    # amber
    api.rgb(120, 220, 80),   # lime
    api.rgb(200, 80, 255),   # violet
]

# ── icons drawn with rects ───────────────────────────────────────────────────

def _icon_wifi(d, x, y, on=True):
    """3-bar WiFi icon (12×10 px)."""
    c = PRIMARY if on else MUTED
    d.rect(x + 4, y + 7, 4, 3, c, fill=True)     # bottom bar (signal)
    d.rect(x + 2, y + 4, 8, 2, c, fill=True)     # mid arc
    d.rect(x,     y + 1, 12, 2, c, fill=True)    # top arc
    if not on:
        d.rect(x, y + 9, 12, 1, api.rgb(200, 50, 50), fill=True)  # strike


def _icon_bt(d, x, y, on=True):
    """Stylised Bluetooth icon (8×12 px)."""
    c = api.rgb(80, 140, 255) if on else MUTED
    d.rect(x + 3, y,      2, 12, c, fill=True)   # vertical spine
    d.rect(x + 3, y,      4,  2, c, fill=True)   # top right diagonal
    d.rect(x + 3, y + 10, 4,  2, c, fill=True)   # bottom right diagonal
    d.rect(x + 3, y + 5,  4,  2, c, fill=True)   # mid right


def _icon_battery(d, x, y, pct=80):
    """Horizontal battery icon (16×8 px)."""
    d.rect(x, y, 14, 8, MUTED, fill=False)
    d.rect(x + 14, y + 2, 2, 4, MUTED, fill=True)  # terminal nub
    filled = max(0, int((pct / 100) * 12))
    fc = api.rgb(80, 220, 80) if pct > 30 else api.rgb(255, 80, 80)
    if filled:
        d.rect(x + 1, y + 1, filled, 6, fc, fill=True)


def _icon_apps(d, x, y, size=14):
    """2×2 grid of squares — 'apps' launcher icon."""
    half = (size - 2) // 2
    d.rect(x,        y,        half, half, PRIMARY, fill=True)
    d.rect(x + half + 2, y,    half, half, PRIMARY, fill=True)
    d.rect(x,        y + half + 2, half, half, PRIMARY, fill=True)
    d.rect(x + half + 2, y + half + 2, half, half, PRIMARY, fill=True)


# ── dock entry ───────────────────────────────────────────────────────────────

class _DockEntry:
    def __init__(self, label, action, color=None):
        self.label  = label
        self.action = action   # callable or string passed to os.launch
        self.color  = color or PRIMARY


# ── home screen ──────────────────────────────────────────────────────────────

_STATUS_H = 24
_DOCK_H   = 56
_DOCK_Y   = api.SCREEN_H - _DOCK_H

_PANDA_PS = 2                          # panda at 40×36 px
_PANDA_X  = (api.SCREEN_W - 20 * _PANDA_PS) // 2
_PANDA_Y  = _STATUS_H + 4


class Home(lix.App):
    name = "home"

    def __init__(self, app_list):
        self._apps    = app_list
        self._dock    = []
        self._dock_sel = 0
        self._dirty   = True
        self._last_sec = -1
        self._blink   = True          # colon blink state

    def on_enter(self, os):
        super().on_enter(os)
        self._build_dock()
        self._dirty = True

    def _build_dock(self):
        self._dock = [_DockEntry("APPS", "__appmenu__", PRIMARY)]
        # Add the first 3 real apps as quick-launch icons
        colors = _ICON_COLORS[:]
        for a in self._apps[:3]:
            c = colors.pop(0) if colors else PRIMARY
            self._dock.append(_DockEntry(a["name"][:4].upper(), a["dir"], c))

    def on_button_press(self, btn):
        if btn == api.BTN_LEFT  and self._dock_sel > 0:
            self._dock_sel -= 1
            self._dirty = True
        elif btn == api.BTN_RIGHT and self._dock_sel < len(self._dock) - 1:
            self._dock_sel += 1
            self._dirty = True
        elif btn == api.BTN_A:
            entry = self._dock[self._dock_sel]
            self.os.launch(entry.action)

    def update(self, dt):
        h, m, s, wd, day, mon, yr = timeutil.now()
        if s != self._last_sec:
            self._last_sec = s
            self._blink    = not self._blink
            self._dirty    = True

    def draw(self, d):
        if not self._dirty:
            return

        h, m, s, wd, day, mon, yr = timeutil.now()

        d.clear(BG)

        # ── status bar ─────────────────────────────────────────────────────
        d.rect(0, 0, api.SCREEN_W, _STATUS_H, STATUS, fill=True)
        d.text("%02d:%02d" % (h, m), 4, 7, api.WHITE)
        date_str = "%s %d %s" % (wd, day, mon)
        d.text(date_str, 52, 7, MUTED)
        _icon_wifi(d, api.SCREEN_W - 90, 6)
        _icon_bt  (d, api.SCREEN_W - 72, 6)
        _icon_battery(d, api.SCREEN_W - 52, 8, pct=85)

        # ── panda mascot ───────────────────────────────────────────────────
        draw_panda(d, _PANDA_X, _PANDA_Y, ps=_PANDA_PS)

        # ── hero clock ─────────────────────────────────────────────────────
        clock_y = _PANDA_Y + 20 * _PANDA_PS + 10   # just below panda

        # HH:MM at scale=4 (each char 32px wide)
        colon = ":" if self._blink else " "
        time_str = "%02d%s%02d" % (h, colon, m)   # "09:45" = 5 chars × 32 = 160px
        time_x   = (api.SCREEN_W - 5 * 8 * 4) // 2  # center 160px in 240px → x=40
        d.text(time_str, time_x, clock_y, PRIMARY, scale=4)

        # :SS at scale=2 (aligned to right of HH:MM)
        sec_x = time_x + 5 * 8 * 4 + 4
        d.text(":%02d" % s, sec_x - 2, clock_y + 14, MUTED, scale=2)

        # Date line
        date_y = clock_y + 38
        full_date = "%s, %d %s %d" % (wd, day, mon, yr)
        date_px   = len(full_date) * 8
        d.text(full_date, (api.SCREEN_W - date_px) // 2, date_y, MUTED)

        # ── dock ───────────────────────────────────────────────────────────
        d.rect(0, _DOCK_Y, api.SCREEN_W, _DOCK_H, DOCK_BG, fill=True)
        d.rect(0, _DOCK_Y, api.SCREEN_W, 1, api.rgb(30, 30, 60), fill=True)

        icon_w    = 44
        gap       = 8
        total_w   = len(self._dock) * icon_w + (len(self._dock) - 1) * gap
        icon_x    = (api.SCREEN_W - total_w) // 2
        icon_y    = _DOCK_Y + 6

        for i, entry in enumerate(self._dock):
            selected = (i == self._dock_sel)
            bg = DOCK_SEL if selected else api.rgb(30, 30, 50)
            d.rect(icon_x, icon_y, icon_w, icon_w - 6, bg, fill=True)
            if selected:
                d.rect(icon_x, icon_y, icon_w, icon_w - 6, PRIMARY, fill=False)

            # Icon
            if entry.action == "__appmenu__":
                _icon_apps(d, icon_x + 15, icon_y + 4)
            else:
                # First letter of app in a small colored square
                lbl_color = entry.color
                d.rect(icon_x + 12, icon_y + 3, 20, 16, lbl_color, fill=True)
                d.text(entry.label[0], icon_x + 16, icon_y + 5, api.BLACK, scale=2)

            # Label below icon
            lbl = entry.label[:4]
            lbl_x = icon_x + (icon_w - len(lbl) * 8) // 2
            d.text(lbl, lbl_x, icon_y + icon_w - 12, api.WHITE if selected else MUTED)

            icon_x += icon_w + gap

        # Hint
        d.text("<  >  nav    A  open", 20, api.SCREEN_H - 12, api.rgb(60, 60, 80))

        self._dirty = False

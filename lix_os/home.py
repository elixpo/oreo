"""Elixpo OS — home screen.

Layout (240×320):
  ┌─ status bar (h=22) ──────────────────────────────────┐
  │  HH:MM   Day DD Mon      [wifi] [bt] [bat]           │
  ├──────────────────────────────────────────────────────┤
  │               mascot (72×72)                         │  y≈28
  ├──────────────────────────────────────────────────────┤
  │            HH : MM          (scale=3, 120px)         │  y≈110
  │              : SS           (scale=2, below)         │  y≈150
  │         Day, DD Mon YYYY    (scale=1)                │  y≈175
  ├──────────────────────────────────────────────────────┤
  │  dock: APPS + quick-launch tiles                     │  y=264
  └──────────────────────────────────────────────────────┘

Navigation:
  LEFT / RIGHT  — move dock selection
  A             — open selected tile
"""

import time
from lix import api
from lix_os import timeutil
import lix

# ── palette ──────────────────────────────────────────────────────────────────

BG       = api.rgb(8, 8, 20)
BG2      = api.rgb(12, 12, 28)          # subtle secondary bg
PRIMARY  = api.rgb(0, 220, 200)
ACCENT   = api.rgb(255, 80, 200)
MUTED    = api.rgb(90, 90, 120)
MUTED2   = api.rgb(60, 60, 85)
STATUS   = api.rgb(10, 10, 24)
DOCK_BG  = api.rgb(14, 14, 30)
DOCK_SEL = api.rgb(0, 50, 46)
WHITE    = api.WHITE

_ICON_COLORS = [
    api.rgb(255, 80, 200),
    api.rgb(0, 180, 255),
    api.rgb(255, 160, 0),
    api.rgb(100, 220, 80),
    api.rgb(180, 80, 255),
]

# ── mascot sprite (loaded once) ───────────────────────────────────────────────

_mascot = None

def _load_mascot():
    global _mascot
    if _mascot is not None:
        return _mascot
    try:
        import assets.mascot as m
        _mascot = (m.DATA, m.W, m.H)
    except ImportError:
        _mascot = None
    return _mascot


# ── status bar icons ──────────────────────────────────────────────────────────

def _icon_wifi(d, x, y):
    c = PRIMARY
    d.rect(x + 5, y + 8, 3, 3, c, fill=True)   # dot
    d.rect(x + 3, y + 5, 7, 2, c, fill=True)   # inner arc
    d.rect(x + 1, y + 2, 11, 2, c, fill=True)  # outer arc


def _icon_bt(d, x, y):
    c = api.rgb(80, 140, 255)
    d.rect(x + 4, y,     2, 12, c, fill=True)
    d.rect(x + 4, y,     5,  2, c, fill=True)
    d.rect(x + 4, y + 5, 5,  2, c, fill=True)
    d.rect(x + 4, y +10, 5,  2, c, fill=True)


def _icon_battery(d, x, y, pct=85):
    fc = api.rgb(80, 220, 80) if pct > 30 else api.rgb(255, 80, 80)
    d.rect(x, y, 18, 8, MUTED, fill=False)
    d.rect(x + 18, y + 2, 2, 4, MUTED, fill=True)
    filled = max(1, int((pct / 100) * 16))
    d.rect(x + 1, y + 1, filled, 6, fc, fill=True)


# ── grid background ───────────────────────────────────────────────────────────

def _draw_grid(d):
    """Subtle dot grid on the dark background."""
    dot = api.rgb(18, 18, 38)
    for gy in range(24, 264, 18):
        for gx in range(6, 240, 18):
            d.pixel(gx, gy, dot)


# ── apps icon ─────────────────────────────────────────────────────────────────

def _draw_apps_icon(d, x, y, size=14):
    h = (size - 2) // 2
    d.rect(x,         y,         h, h, PRIMARY, fill=True)
    d.rect(x + h + 2, y,         h, h, PRIMARY, fill=True)
    d.rect(x,         y + h + 2, h, h, PRIMARY, fill=True)
    d.rect(x + h + 2, y + h + 2, h, h, PRIMARY, fill=True)


# ── dock ─────────────────────────────────────────────────────────────────────

class _DockEntry:
    __slots__ = ("label", "action", "color")
    def __init__(self, label, action, color=None):
        self.label  = label
        self.action = action
        self.color  = color or PRIMARY


_STATUS_H = 22
_DOCK_H   = 56
_DOCK_Y   = api.SCREEN_H - _DOCK_H   # 264

_MASCOT_W = 72
_MASCOT_H = 72
_MASCOT_X = (api.SCREEN_W - _MASCOT_W) // 2   # 84
_MASCOT_Y = _STATUS_H + 4                       # 26

# Clock sits below mascot
_CLOCK_Y  = _MASCOT_Y + _MASCOT_H + 6          # 104   (scale=3 → 24px tall)
_SEC_Y    = _CLOCK_Y + 26                       # 130   (scale=2 → 16px tall)
_DATE_Y   = _SEC_Y + 20                         # 150


# ── home screen app ───────────────────────────────────────────────────────────

class Home(lix.App):
    name = "home"

    def __init__(self, app_list):
        self._apps     = app_list
        self._dock     = []
        self._dock_sel = 0
        self._dirty    = True
        self._last_sec = -1
        self._blink    = True

    def on_enter(self, os):
        super().on_enter(os)
        self._build_dock()
        self._dirty = True

    def _build_dock(self):
        self._dock = [_DockEntry("APPS", "__appmenu__", PRIMARY)]
        colors = list(_ICON_COLORS)
        for a in self._apps[:3]:
            c = colors.pop(0) if colors else PRIMARY
            self._dock.append(_DockEntry(a["name"][:4].upper(), a["dir"], c))

    def on_button_press(self, btn):
        if btn == api.BTN_LEFT and self._dock_sel > 0:
            self._dock_sel -= 1
            self._dirty = True
        elif btn == api.BTN_RIGHT and self._dock_sel < len(self._dock) - 1:
            self._dock_sel += 1
            self._dirty = True
        elif btn == api.BTN_A:
            self.os.launch(self._dock[self._dock_sel].action)

    def update(self, dt):
        _, _, s, *_ = timeutil.now()
        if s != self._last_sec:
            self._last_sec = s
            self._blink    = not self._blink
            self._dirty    = True

    def draw(self, d):
        if not self._dirty:
            return

        h, m, s, wd, day, mon, yr = timeutil.now()

        # ── background ────────────────────────────────────────────────────
        d.clear(BG)
        _draw_grid(d)

        # Soft card behind clock area
        d.rect(10, _MASCOT_Y - 2, api.SCREEN_W - 20, _DOCK_Y - _MASCOT_Y + 2,
               BG2, fill=True)

        # ── status bar ────────────────────────────────────────────────────
        d.rect(0, 0, api.SCREEN_W, _STATUS_H, STATUS, fill=True)
        # thin accent line under status bar
        d.rect(0, _STATUS_H - 1, api.SCREEN_W, 1, api.rgb(0, 80, 72), fill=True)

        d.text("%02d:%02d" % (h, m), 4, 6, WHITE)
        date_str = "%s %d %s" % (wd, day, mon)
        d.text(date_str, 52, 6, MUTED)

        _icon_wifi   (d, api.SCREEN_W - 92, 5)
        _icon_bt     (d, api.SCREEN_W - 72, 5)
        _icon_battery(d, api.SCREEN_W - 52, 7, pct=85)

        # ── mascot ────────────────────────────────────────────────────────
        m_data = _load_mascot()
        if m_data:
            data, mw, mh = m_data
            d.blit(data, _MASCOT_X, _MASCOT_Y, mw, mh)
        else:
            # fallback: draw code panda
            from lix_os.panda import draw_panda
            draw_panda(d, _MASCOT_X + 6, _MASCOT_Y + 4, ps=3)

        # ── hero clock ────────────────────────────────────────────────────
        # "HH MM" at scale=3: 5 chars × 24px = 120px, centered → x=60
        # Use a space instead of colon so we can draw a blinking colon ourselves
        hh_str  = "%02d" % h
        mm_str  = "%02d" % m
        colon_c = PRIMARY if self._blink else MUTED2

        cx = (api.SCREEN_W - 5 * 8 * 3) // 2  # = 60

        d.text(hh_str,  cx,          _CLOCK_Y, PRIMARY, scale=3)
        d.text(":",     cx + 2*8*3,  _CLOCK_Y, colon_c, scale=3)
        d.text(mm_str,  cx + 3*8*3,  _CLOCK_Y, PRIMARY, scale=3)

        # Seconds on next line, right-aligned under MM
        sec_str = ":%02d" % s
        sec_x   = cx + 3*8*3 + 2*8*3 - len(sec_str)*8*2   # right-align to end of MM
        sec_x   = min(sec_x, api.SCREEN_W - len(sec_str) * 8 * 2 - 4)
        d.text(sec_str, sec_x, _SEC_Y, MUTED, scale=2)

        # Date
        full_date = "%s, %d %s %d" % (wd, day, mon, yr)
        date_px   = len(full_date) * 8
        d.text(full_date, max(0, (api.SCREEN_W - date_px) // 2), _DATE_Y, MUTED)

        # ── dock ──────────────────────────────────────────────────────────
        d.rect(0, _DOCK_Y, api.SCREEN_W, _DOCK_H, DOCK_BG, fill=True)
        d.rect(0, _DOCK_Y, api.SCREEN_W, 1, PRIMARY, fill=True)

        icon_w = 44
        gap    = 8
        n      = len(self._dock)
        total  = n * icon_w + (n - 1) * gap
        ix     = (api.SCREEN_W - total) // 2
        iy     = _DOCK_Y + 5

        for i, entry in enumerate(self._dock):
            sel = (i == self._dock_sel)
            tile_bg = DOCK_SEL if sel else api.rgb(22, 22, 44)
            d.rect(ix, iy, icon_w, 40, tile_bg, fill=True)

            if sel:
                d.rect(ix, iy, icon_w, 40, entry.color, fill=False)
                d.rect(ix + 2, _DOCK_Y + _DOCK_H - 5, icon_w - 4, 3,
                       entry.color, fill=True)

            # Icon graphic
            if entry.action == "__appmenu__":
                _draw_apps_icon(d, ix + 15, iy + 6, size=14)
            else:
                # Try to load app icon bitmap; fallback to letter square
                app_icon = _try_load_icon(entry.action)
                if app_icon:
                    data, iw, ih = app_icon
                    d.blit(data, ix + (icon_w - iw) // 2, iy + 2, iw, ih)
                else:
                    d.rect(ix + 12, iy + 3, 20, 18, entry.color, fill=True)
                    d.text(entry.label[0], ix + 16, iy + 5, api.BLACK, scale=2)

            lbl   = entry.label[:4]
            lbl_x = ix + (icon_w - len(lbl) * 8) // 2
            d.text(lbl, lbl_x, iy + 30, WHITE if sel else MUTED)
            ix += icon_w + gap

        self._dirty = False


# ── icon loader (cached) ──────────────────────────────────────────────────────

_icon_cache: dict = {}

def _try_load_icon(app_dir):
    if app_dir in _icon_cache:
        return _icon_cache[app_dir]
    try:
        mod = __import__("assets.icons.%s" % app_dir, None, None, ["DATA", "W", "H"])
        result = (mod.DATA, mod.W, mod.H)
    except (ImportError, AttributeError):
        result = None
    _icon_cache[app_dir] = result
    return result

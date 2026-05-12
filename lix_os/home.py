"""Elixpo OS — home screen.

Layout (240×320):
  ┌─ status bar (h=22) ─────────────────────────────────┐
  │  HH:MM    [wifi] [bt] [bat]                          │
  ├─────────────────────────────────────────────────────-┤
  │          mascot (72×72)    vertically centered       │
  │           HH:MM  scale=3                             │
  │          Day DD Mon YYYY                             │
  ├──────────────────────────────────────────────────────┤
  │               [APPS]  (dock, centered)               │  y=264
  └──────────────────────────────────────────────────────┘

Navigation:  LEFT/RIGHT cycle dock (wraps), A to open.
"""

import time
from lix import api
from lix_os import timeutil
import lix

# ── palette ──────────────────────────────────────────────────────────────────

BG       = api.rgb(8, 8, 20)
BG2      = api.rgb(12, 12, 28)
PRIMARY  = api.rgb(0, 220, 200)
ACCENT   = api.rgb(255, 80, 200)
MUTED    = api.rgb(90, 90, 120)
MUTED2   = api.rgb(60, 60, 85)
STATUS   = api.rgb(10, 10, 24)
DOCK_BG  = api.rgb(14, 14, 30)
DOCK_SEL = api.rgb(0, 50, 46)
WHITE    = api.WHITE

# ── layout constants ─────────────────────────────────────────────────────────

_STATUS_H = 22
_DOCK_H   = 56
_DOCK_Y   = api.SCREEN_H - _DOCK_H        # 264
_MAIN_TOP = _STATUS_H                      # 22
_MAIN_H   = _DOCK_Y - _MAIN_TOP           # 242

_MASCOT_W = 72
_MASCOT_H = 72

# Content block: mascot(72) + gap(8) + clock(24) + gap(6) + date(8) = 118px
# Centre that block in _MAIN_H (242px)
_BLOCK_H    = _MASCOT_H + 8 + 24 + 6 + 8   # 118
_BLOCK_TOP  = _MAIN_TOP + (_MAIN_H - _BLOCK_H) // 2   # ≈84

_MASCOT_X = (api.SCREEN_W - _MASCOT_W) // 2   # 84
_MASCOT_Y = _BLOCK_TOP                          # ≈84

_CLOCK_Y  = _MASCOT_Y + _MASCOT_H + 8          # ≈164
_DATE_Y   = _CLOCK_Y + 24 + 6                  # ≈194

# ── mascot loader (cached, PIL-friendly) ──────────────────────────────────────

_mascot_cache = None

def _load_mascot():
    global _mascot_cache
    if _mascot_cache is not None:
        return _mascot_cache if _mascot_cache is not False else None
    # 1. pre-converted module
    try:
        import assets.mascot as m
        _mascot_cache = (m.DATA, m.W, m.H)
        return _mascot_cache
    except (ImportError, AttributeError):
        pass
    # 2. PIL runtime load
    try:
        from PIL import Image
        import struct
        img = Image.open("asset/mascot.png").convert("RGBA").resize(
            (_MASCOT_W, _MASCOT_H), Image.LANCZOS)
        bg = Image.new("RGBA", (_MASCOT_W, _MASCOT_H), (8, 8, 20, 255))
        bg.paste(img, mask=img.split()[3])
        rgb = bg.convert("RGB")
        px = rgb.load()
        words = []
        for y in range(_MASCOT_H):
            for x in range(_MASCOT_W):
                r, g, b = px[x, y]
                words.append(((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3))
        data = struct.pack(">%dH" % len(words), *words)
        _mascot_cache = (data, _MASCOT_W, _MASCOT_H)
        return _mascot_cache
    except Exception:
        pass
    _mascot_cache = False
    return None


# ── icon loader (for dock) ────────────────────────────────────────────────────

def _load_icon(app_dir, icon_filename=None):
    from lix_os.icons import load
    return load(app_dir, icon_filename)


# ── status bar icons ──────────────────────────────────────────────────────────

def _icon_wifi(d, x, y):
    c = PRIMARY
    d.rect(x + 5, y + 8, 3, 3, c, fill=True)
    d.rect(x + 3, y + 5, 7, 2, c, fill=True)
    d.rect(x + 1, y + 2, 11, 2, c, fill=True)


def _icon_bt(d, x, y):
    c = api.rgb(80, 140, 255)
    d.rect(x + 4, y,      2, 12, c, fill=True)
    d.rect(x + 4, y,      5,  2, c, fill=True)
    d.rect(x + 4, y + 5,  5,  2, c, fill=True)
    d.rect(x + 4, y + 10, 5,  2, c, fill=True)


def _icon_battery(d, x, y, pct=85):
    fc = api.rgb(80, 220, 80) if pct > 30 else api.rgb(255, 80, 80)
    d.rect(x, y, 18, 8, MUTED, fill=False)
    d.rect(x + 18, y + 2, 2, 4, MUTED, fill=True)
    filled = max(1, int((pct / 100) * 16))
    d.rect(x + 1, y + 1, filled, 6, fc, fill=True)


# ── dot grid background ───────────────────────────────────────────────────────

def _draw_grid(d):
    dot = api.rgb(18, 18, 38)
    for gy in range(24, _DOCK_Y, 18):
        for gx in range(6, 240, 18):
            d.pixel(gx, gy, dot)


# ── apps icon (2×2 grid of squares) ──────────────────────────────────────────

def _draw_apps_icon(d, x, y, size=14):
    h = (size - 2) // 2
    d.rect(x,         y,         h, h, PRIMARY, fill=True)
    d.rect(x + h + 2, y,         h, h, PRIMARY, fill=True)
    d.rect(x,         y + h + 2, h, h, PRIMARY, fill=True)
    d.rect(x + h + 2, y + h + 2, h, h, PRIMARY, fill=True)


# ── dock entry ────────────────────────────────────────────────────────────────

class _DockEntry:
    __slots__ = ("label", "action", "icon_file", "color")
    def __init__(self, label, action, icon_file=None, color=None):
        self.label     = label
        self.action    = action
        self.icon_file = icon_file
        self.color     = color or PRIMARY


# ── Home app ─────────────────────────────────────────────────────────────────

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
        # Only APPS entry on the home dock — single centred button
        self._dock = [_DockEntry("APPS", "__appmenu__", color=PRIMARY)]
        self._dock_sel = 0

    def on_button_press(self, btn):
        n = len(self._dock)
        if btn == api.BTN_LEFT:
            self._dock_sel = (self._dock_sel - 1) % n
            self._dirty = True
        elif btn == api.BTN_RIGHT:
            self._dock_sel = (self._dock_sel + 1) % n
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

        # Soft card behind main content area
        d.rect(10, _MAIN_TOP + 2, api.SCREEN_W - 20, _DOCK_Y - _MAIN_TOP - 4,
               BG2, fill=True)

        # ── status bar ────────────────────────────────────────────────────
        d.rect(0, 0, api.SCREEN_W, _STATUS_H, STATUS, fill=True)
        d.rect(0, _STATUS_H - 1, api.SCREEN_W, 1, api.rgb(0, 80, 72), fill=True)

        time_str = "%02d:%02d" % (h, m)
        d.text(time_str, 4, 6, WHITE)

        _icon_wifi   (d, api.SCREEN_W - 92, 5)
        _icon_bt     (d, api.SCREEN_W - 72, 5)
        _icon_battery(d, api.SCREEN_W - 52, 7, pct=85)

        # ── mascot ────────────────────────────────────────────────────────
        mascot = _load_mascot()
        if mascot:
            data, mw, mh = mascot
            d.blit(data, _MASCOT_X, _MASCOT_Y, mw, mh)
        else:
            from lix_os.panda import draw_panda
            draw_panda(d, _MASCOT_X + 6, _MASCOT_Y + 2, ps=3)

        # ── hero clock — "HH:MM" scale=3, 120px wide, centered ────────────
        clock_str = "%02d:%02d" % (h, m)
        colon_c   = PRIMARY if self._blink else MUTED2
        # Draw HH, blink colon, MM separately
        char_w = 8 * 3   # 24px per char at scale=3
        total_w = 5 * char_w   # "HH:MM" = 5 chars × 24px = 120px
        cx = (api.SCREEN_W - total_w) // 2   # 60

        d.text("%02d" % h, cx,              _CLOCK_Y, PRIMARY, scale=3)
        d.text(":",        cx + 2 * char_w, _CLOCK_Y, colon_c, scale=3)
        d.text("%02d" % m, cx + 3 * char_w, _CLOCK_Y, PRIMARY, scale=3)

        # ── date — "Wed 12 May 2026" centered ────────────────────────────
        date_str = "%s %d %s %d" % (wd, day, mon, yr)
        date_px  = len(date_str) * 8
        date_x   = max(2, (api.SCREEN_W - date_px) // 2)
        d.text(date_str, date_x, _DATE_Y, MUTED)

        # ── dock ──────────────────────────────────────────────────────────
        d.rect(0, _DOCK_Y, api.SCREEN_W, _DOCK_H, DOCK_BG, fill=True)
        d.rect(0, _DOCK_Y, api.SCREEN_W, 1, PRIMARY, fill=True)

        TILE_W = 52
        TILE_H = 42
        n      = len(self._dock)
        gap    = 10
        total  = n * TILE_W + (n - 1) * gap
        ix     = (api.SCREEN_W - total) // 2
        iy     = _DOCK_Y + (_DOCK_H - TILE_H) // 2

        for i, entry in enumerate(self._dock):
            sel    = (i == self._dock_sel)
            tile_c = DOCK_SEL if sel else api.rgb(22, 22, 44)
            d.rect(ix, iy, TILE_W, TILE_H, tile_c, fill=True)
            if sel:
                d.rect(ix, iy, TILE_W, TILE_H, entry.color, fill=False)
                d.rect(ix + 3, _DOCK_Y + _DOCK_H - 5, TILE_W - 6, 3,
                       entry.color, fill=True)

            if entry.action == "__appmenu__":
                _draw_apps_icon(d, ix + 19, iy + 8, size=14)
            else:
                icon = _load_icon(entry.action, entry.icon_file)
                if icon:
                    idata, iw, ih = icon
                    d.blit(idata, ix + (TILE_W - iw) // 2, iy + 3, iw, ih)
                else:
                    d.rect(ix + 14, iy + 4, 24, 20, entry.color, fill=True)
                    d.text(entry.label[0], ix + 18, iy + 7, api.BLACK, scale=2)

            ix += TILE_W + gap

        self._dirty = False

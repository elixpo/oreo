"""Elixpo OS — home screen, 320×240 landscape, celebration theme.

Layout:
  ┌─ status bar h=22 (pink bar) ───────────────────────────────┐
  │  [wifi] [bt] [bat]                              17:06       │
  ├────────────────────────────────────────────────────────────┤
  │  (home_bg asset, warm jungle/celebration bg)               │
  │                                                            │
  │          17:06       (scale=4, dark text, centred)         │
  │       Tue 12 May 2026  (centred)                           │
  │                                                            │
  ├────────────────────────────────────────────────────────────┤
  │            [APPS icon]   (cream dock, centred)             │
  └────────────────────────────────────────────────────────────┘

Nav: LEFT/RIGHT wrap, A to open.
"""

import time
from lix import api
from lix_os import theme, timeutil
import lix

SW = api.SCREEN_W   # 320
SH = api.SCREEN_H   # 240

_STATUS_H = 22
_DOCK_H   = 44
_DOCK_Y   = SH - _DOCK_H        # 196
_MAIN_TOP = _STATUS_H            # 22
_MAIN_H   = _DOCK_Y - _MAIN_TOP  # 174

# Clock block: 32px (HH:MM scale=4) + 8 gap + 8 (date) = 48px, centred
_CLOCK_Y = _MAIN_TOP + (_MAIN_H - 48) // 2   # ≈ 85
_DATE_Y  = _CLOCK_Y + 32 + 8                  # ≈ 125

# ── asset loaders (pipeline only — no procedural fallback drawing) ─────────────

_bg_cache   = None
_apps_cache = None


def _load_bg():
    global _bg_cache
    if _bg_cache is not None:
        return _bg_cache if _bg_cache is not False else None
    try:
        import assets.icons.optimized.home_bg as m
        _bg_cache = (m.DATA, m.W, m.H)
        return _bg_cache
    except (ImportError, AttributeError):
        pass
    try:
        from PIL import Image
        import struct
        img = Image.open("assets/icons/raw/home_bg.png").convert("RGBA")
        img = img.resize((80, 60), Image.LANCZOS)
        bg  = Image.new("RGBA", (80, 60),
                        (theme.BG_R, theme.BG_G, theme.BG_B, 255))
        bg.paste(img, mask=img.split()[3])
        rgb = bg.convert("RGB")
        px  = rgb.load()
        words = []
        for y in range(60):
            for x in range(80):
                r, g, b = px[x, y]
                words.append(((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3))
        data = struct.pack(">%dH" % len(words), *words)
        _bg_cache = (data, 80, 60)
        return _bg_cache
    except Exception:
        _bg_cache = False
    return None


def _load_apps_icon():
    global _apps_cache
    if _apps_cache is not None:
        return _apps_cache if _apps_cache is not False else None
    from lix_os.icons import load
    result = load("apps", "apps_icon.png")
    _apps_cache = result if result else False
    return result


# ── status bar icons ──────────────────────────────────────────────────────────
# Procedural fallbacks — replaced automatically when assets/status/<name>.py exists

def _load_status_icon(name):
    """Try to load a pre-baked 13×13 status icon. Returns (data,w,h) or None."""
    try:
        mod = __import__("assets.status.optimized.%s" % name,
                         None, None, ["DATA", "W", "H"])
        return (mod.DATA, mod.W, mod.H)
    except ImportError:
        return None


def _icon_wifi(d, x, y, connected=False):
    name = "wifi" if connected else "wifi_disabled"
    icon = _load_status_icon(name)
    if icon:
        d.blit(icon[0], x, y, icon[1], icon[2])
        return
    c = api.WHITE if connected else api.rgb(180, 100, 100)
    d.rect(x + 5, y + 9,  3, 2, c, fill=True)
    d.rect(x + 2, y + 6,  9, 2, c, fill=True)
    if connected:
        d.rect(x,   y + 3, 13, 2, c, fill=True)


def _icon_bt(d, x, y, active=False):
    icon = _load_status_icon("bluetooth")
    if icon:
        # Dim the icon if BT is off
        d.blit(icon[0], x, y, icon[1], icon[2])
        return
    c = api.WHITE if active else api.rgb(180, 100, 100)
    d.rect(x + 3, y,      2, 13, c, fill=True)
    d.rect(x + 5, y,      2,  2, c, fill=True)
    d.rect(x + 7, y + 2,  2,  2, c, fill=True)
    d.rect(x + 5, y + 4,  2,  2, c, fill=True)
    d.rect(x + 5, y + 7,  2,  2, c, fill=True)
    d.rect(x + 7, y + 9,  2,  2, c, fill=True)
    d.rect(x + 5, y + 11, 2,  2, c, fill=True)
    d.rect(x,     y + 3,  3,  2, c, fill=True)
    d.rect(x,     y + 8,  3,  2, c, fill=True)


def _icon_battery(d, x, y, pct=85):
    d.rect(x,      y,     20, 10, api.WHITE, fill=False)
    d.rect(x + 20, y + 3,  2,  4, api.WHITE, fill=True)
    filled = max(1, int((pct / 100) * 18))
    d.rect(x + 1,  y + 1, filled, 8, api.WHITE, fill=True)


# ── dock entry ────────────────────────────────────────────────────────────────

class _DockEntry:
    __slots__ = ("label", "action", "icon_file")
    def __init__(self, label, action, icon_file=None):
        self.label     = label
        self.action    = action
        self.icon_file = icon_file


# ── Home app ─────────────────────────────────────────────────────────────────

class Home(lix.App):
    name = "home"

    def __init__(self, app_list):
        self._apps      = app_list
        self._dock      = [_DockEntry("APPS", "__appmenu__", "apps_icon.png")]
        self._dock_sel  = 0
        self._dirty     = True
        self._last_sec  = -1
        self._blink     = True
        self._wifi_ok   = False
        self._bt_on     = False
        self._last_net  = -1   # refresh network status every 5s

    def on_enter(self, os):
        super().on_enter(os)
        self._dirty = True

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
        # Poll network status every ~5 seconds
        if s % 5 == 0 and s != self._last_net:
            self._last_net = s
            try:
                from lix_hw import wifi as _w, bt as _b
                wifi_ok = _w.is_connected()
                bt_on   = _b.is_active()
            except Exception:
                wifi_ok = False
                bt_on   = False
            if wifi_ok != self._wifi_ok or bt_on != self._bt_on:
                self._wifi_ok  = wifi_ok
                self._bt_on    = bt_on
                self._dirty    = True

    def draw(self, d):
        if not self._dirty:
            return

        h, m, s, wd, day, mon, yr = timeutil.now()

        # ── background ────────────────────────────────────────────────────
        d.clear(theme.BG)   # warm ivory fallback

        bg = _load_bg()
        if bg:
            data, bw, bh = bg
            d.blit_scale(data, 0, _MAIN_TOP, bw, bh, 4, dim=0.45)

        # ── status bar ────────────────────────────────────────────────────
        d.rect(0, 0, SW, _STATUS_H, theme.STATUS_BG, fill=True)

        # time on the LEFT
        time_str = "%02d:%02d" % (h, m)
        d.text(time_str, 6, 7, api.WHITE)

        # icons on the RIGHT: battery | bt | wifi  ←  right edge
        _icon_battery(d, SW - 28, 6, pct=85)
        _icon_bt     (d, SW - 44, 4, active=self._bt_on)
        _icon_wifi   (d, SW - 60, 5, connected=self._wifi_ok)

        # ── hero clock ────────────────────────────────────────────────────
        char_w  = 8 * 4                   # 32px per char at scale=4
        total_w = 5 * char_w              # 160px for "HH:MM"
        cx      = (SW - total_w) // 2     # 80

        colon_c = theme.TEXT_BRIGHT if self._blink else theme.MUTED

        d.text("%02d" % h, cx,              _CLOCK_Y, theme.TEXT_BRIGHT, scale=4)
        d.text(":",        cx + 2 * char_w, _CLOCK_Y, colon_c,           scale=4)
        d.text("%02d" % m, cx + 3 * char_w, _CLOCK_Y, theme.TEXT_BRIGHT, scale=4)

        # ── date ──────────────────────────────────────────────────────────
        date_str = "%s %d %s %d" % (wd, day, mon, yr)
        dx = max(0, (SW - len(date_str) * 8) // 2)
        d.text(date_str, dx, _DATE_Y, api.WHITE)

        # ── dock ──────────────────────────────────────────────────────────
        d.rect(0, _DOCK_Y, SW, _DOCK_H, theme.DOCK_BG, fill=True)
        d.rect(0, _DOCK_Y, SW, 1, theme.PRIMARY, fill=True)

        ICON_SZ  = 32
        TILE_PAD = 4
        n        = len(self._dock)
        gap      = 20
        total    = n * ICON_SZ + (n - 1) * gap
        ix       = (SW - total) // 2
        iy       = _DOCK_Y + (_DOCK_H - ICON_SZ) // 2

        for i, entry in enumerate(self._dock):
            sel = (i == self._dock_sel)
            if sel:
                d.rect(ix - TILE_PAD, iy - TILE_PAD,
                       ICON_SZ + TILE_PAD * 2, ICON_SZ + TILE_PAD * 2,
                       theme.SEL_BORDER, fill=False)

            if entry.action == "__appmenu__":
                icon = _load_apps_icon()
                if icon:
                    idata, iw, ih = icon
                    d.blit(idata, ix + (ICON_SZ - iw) // 2,
                           iy + (ICON_SZ - ih) // 2, iw, ih)
                else:
                    _draw_grid_fallback(d, ix + 2, iy + 2, ICON_SZ - 4)
            else:
                from lix_os.icons import load as _load
                icon = _load(entry.action, entry.icon_file)
                if icon:
                    idata, iw, ih = icon
                    d.blit(idata, ix + (ICON_SZ - iw) // 2,
                           iy + (ICON_SZ - ih) // 2, iw, ih)

            ix += ICON_SZ + gap

        self._dirty = False


def _draw_grid_fallback(d, x, y, size):
    """3×3 squares — shown only until apps_icon.png is generated & optimised."""
    cell = (size - 4) // 3
    gap  = 2
    cols = [theme.PRIMARY, theme.TEAL,  theme.GOLD,
            theme.TEAL,    theme.ORANGE, theme.PRIMARY,
            theme.GOLD,    theme.PRIMARY, theme.PURPLE]
    i = 0
    for row in range(3):
        for col in range(3):
            d.rect(x + col * (cell + gap), y + row * (cell + gap),
                   cell, cell, cols[i % len(cols)], fill=True)
            i += 1

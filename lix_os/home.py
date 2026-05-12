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

_bg_cache         = None
_apps_cache       = None
_scaled_bg_cache  = None   # pre-rendered 320×240 RGB565 (big-endian) bytearray


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


def _get_scaled_bg():
    """Return (bytes, w, h) for the pre-scaled & dimmed home background.

    Built once on first call; cached for the lifetime of the process.
    Scaling at draw time is too slow (~100ms) and causes visible flicker.
    """
    global _scaled_bg_cache
    if _scaled_bg_cache is not None:
        return _scaled_bg_cache if _scaled_bg_cache is not False else None

    bg = _load_bg()
    if not bg:
        _scaled_bg_cache = False
        return None

    import struct
    data, bw, bh = bg
    SCALE = 4
    DIM   = 0.45
    sw    = bw * SCALE
    sh    = bh * SCALE
    n     = bw * bh
    words = struct.unpack(">%dH" % n, data[:n * 2])

    out  = bytearray(sw * sh * 2)
    row  = bytearray(sw * 2)

    br, bg_, bb = theme.BG_R, theme.BG_G, theme.BG_B

    for src_row in range(bh):
        base_w = src_row * bw
        for col in range(bw):
            v = words[base_w + col]
            # apply dim
            r = ((v >> 11) & 0x1F) << 3
            g = ((v >>  5) & 0x3F) << 2
            b = ( v        & 0x1F) << 3
            r = int(r + (br  - r) * DIM)
            g = int(g + (bg_ - g) * DIM)
            b = int(b + (bb  - b) * DIM)
            v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            # big-endian bytes (high byte first) — matches framebuf convention
            b1 = v >> 8
            b0 = v & 0xFF
            base = col * SCALE * 2
            for dx in range(SCALE):
                row[base + dx * 2]     = b1
                row[base + dx * 2 + 1] = b0

        row_start = src_row * SCALE * sw * 2
        for dy in range(SCALE):
            s = row_start + dy * sw * 2
            out[s:s + sw * 2] = row

    _scaled_bg_cache = (out, sw, sh)
    return _scaled_bg_cache


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
        self._apps         = app_list
        self._dock         = [_DockEntry("APPS", "__appmenu__", "apps_icon.png")]
        self._dock_sel     = 0
        self._dirty        = True   # full redraw (background + everything)
        self._clock_dirty  = False  # repaint only clock+date band
        self._status_dirty = False  # repaint only status bar
        self._last_sec     = -1
        self._blink        = True
        self._wifi_ok      = False
        self._bt_on        = False
        self._last_net     = -1

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
            # Only the clock area needs repainting on tick — NOT the full screen
            self._clock_dirty = True
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
                self._wifi_ok = wifi_ok
                self._bt_on   = bt_on
                self._status_dirty = True

    def draw(self, d):
        full = self._dirty
        clock_only  = (not full) and getattr(self, "_clock_dirty", False)
        status_only = (not full) and getattr(self, "_status_dirty", False)
        if not (full or clock_only or status_only):
            return

        h, m, s, wd, day, mon, yr = timeutil.now()

        if full:
            # ── background (uses cached pre-scaled buffer) ──────────────
            sbg = _get_scaled_bg()
            if sbg:
                data, sw, sh = sbg
                d.blit(data, 0, _MAIN_TOP, sw, sh)
            else:
                d.clear(theme.BG)

            self._draw_status_bar(d, h, m)
            self._draw_clock_area(d, h, m, wd, day, mon, yr)
            self._draw_dock(d)
            self._dirty = False
            self._clock_dirty = False
            self._status_dirty = False
            return

        if clock_only:
            # Clear ONLY the clock+date area, then redraw
            self._draw_clock_area(d, h, m, wd, day, mon, yr)
            self._clock_dirty = False

        if status_only:
            self._draw_status_bar(d, h, m)
            self._status_dirty = False

    def _draw_status_bar(self, d, h, m):
        d.rect(0, 0, SW, _STATUS_H, theme.STATUS_BG, fill=True)
        d.text("%02d:%02d" % (h, m), 6, 7, api.WHITE)
        _icon_battery(d, SW - 28, 6, pct=85)
        _icon_bt     (d, SW - 44, 4, active=self._bt_on)
        _icon_wifi   (d, SW - 60, 5, connected=self._wifi_ok)

    def _draw_clock_area(self, d, h, m, wd, day, mon, yr):
        # Repaint just the clock band over the (cached) background.
        # We re-blit the relevant slice of the cached scaled bg as our "erase".
        sbg = _get_scaled_bg()
        if sbg:
            data, sw, sh = sbg
            # Slice rows _CLOCK_Y..(_DATE_Y+8) from the cached bg
            slice_y = _CLOCK_Y - _MAIN_TOP
            slice_h = (_DATE_Y + 8) - _CLOCK_Y
            row_bytes = sw * 2
            start = slice_y * row_bytes
            end   = start + slice_h * row_bytes
            d.blit(data[start:end], 0, _CLOCK_Y, sw, slice_h)
        else:
            d.rect(0, _CLOCK_Y, SW, (_DATE_Y + 8) - _CLOCK_Y, theme.BG, fill=True)

        char_w  = 8 * 4
        total_w = 5 * char_w
        cx      = (SW - total_w) // 2
        colon_c = theme.TEXT_BRIGHT if self._blink else theme.MUTED
        d.text("%02d" % h, cx,              _CLOCK_Y, theme.TEXT_BRIGHT, scale=4)
        d.text(":",        cx + 2 * char_w, _CLOCK_Y, colon_c,           scale=4)
        d.text("%02d" % m, cx + 3 * char_w, _CLOCK_Y, theme.TEXT_BRIGHT, scale=4)

        date_str = "%s %d %s %d" % (wd, day, mon, yr)
        dx = max(0, (SW - len(date_str) * 8) // 2)
        d.text(date_str, dx, _DATE_Y, api.WHITE)

        # ── dock ──────────────────────────────────────────────────────────
    def _draw_dock(self, d):
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
            else:
                from lix_os.icons import load as _load
                icon = _load(entry.action, entry.icon_file)
            if icon:
                idata, iw, ih = icon
                d.blit(idata, ix + (ICON_SZ - iw) // 2,
                       iy + (ICON_SZ - ih) // 2, iw, ih)
            elif entry.action == "__appmenu__":
                _draw_grid_fallback(d, ix + 2, iy + 2, ICON_SZ - 4)
            ix += ICON_SZ + gap


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

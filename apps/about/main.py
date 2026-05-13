"""About — Oreo OS info, build metadata, and credits.

Scrollable card with: OS branding, version, build, hardware, runtime stats
(free RAM, uptime, IP), and creator credits.

Controls:
  UP/DOWN  scroll
  HOME     back to apps drawer
"""

import gc
import sys
import time

import oreoOS
from oreoOS import api, pixelfont
from oreoOS import theme, widgets


SW = api.SCREEN_W
SH = api.SCREEN_H


def _load_mascot():
    try:
        m = __import__("assets.sprites.optimized.mascot", None, None, ["DATA", "W", "H"])
        return (bytearray(m.DATA), m.W, m.H)
    except (ImportError, AttributeError):
        return None


def _kb(b):
    return "%d kB" % (b // 1024)


def _os_version():
    """Single source of truth for the OS version string lives in launcher.VERSION."""
    try:
        from oreoOS.launcher import VERSION
        return VERSION
    except Exception:
        return "v?.?.?"


class App(oreoOS.App):
    name = "About"

    def on_enter(self, os):
        super().on_enter(os)
        self._os      = os
        self._dirty   = True
        self._mascot  = _load_mascot()
        self._boot_ms = time.ticks_ms()
        self._last_s  = -1
        self._scroll  = 0
        self._max_scroll = 0
        try:
            from oreoWare import wifi
            self._ip = wifi.ip() or "—"
        except Exception:
            self._ip = "—"
        # Pixelify font cache
        try:
            self._pf_title = pixelfont.load("pixelify_24")
            self._pf_body  = pixelfont.load("pixelify_12")
        except (ImportError, AttributeError):
            self._pf_title = None
            self._pf_body  = None

    def update(self, dt):
        s = time.ticks_diff(time.ticks_ms(), self._boot_ms) // 1000
        if s != self._last_s:
            self._last_s = s
            self._dirty  = True

    def on_button_press(self, btn):
        if btn == api.BTN_UP:
            self._scroll = max(0, self._scroll - 12)
            self._dirty = True
        elif btn == api.BTN_DOWN:
            self._scroll = min(self._max_scroll, self._scroll + 12)
            self._dirty = True

    def _info_rows(self):
        secs = self._last_s
        return [
            ("OS",       "Oreo OS"),
            ("Version",  _os_version()),
            ("Codename", "Sweet Sandwich"),
            ("Board",    "ESP32-S3-DevKitC-1"),
            ("Memory",   _kb(gc.mem_free()) + " free"),
            ("Display",  "ST7789  320x240"),
            # MicroPython's sys.implementation.version is a 5-tuple
            # (major, minor, patch, releaselevel, serial) — slice to 3 ints.
            ("Runtime",  "MicroPython %d.%d.%d" % tuple(sys.implementation.version[:3])),
            ("IP",       self._ip[:18]),
            ("Uptime",   "%02d:%02d:%02d" % (secs // 3600,
                                            (secs % 3600) // 60,
                                             secs % 60)),
        ]

    def draw(self, d):
        if not self._dirty:
            return
        d.clear(theme.BG)
        widgets.draw_header(d, "ABOUT")
        widgets.draw_hint  (d, "UP/DOWN=scroll  HOME=back")

        # Scrollable content panel
        panel_x = 8
        panel_y = widgets.HEADER_H + 4
        panel_w = SW - 16
        panel_h = SH - widgets.HEADER_H - widgets.HINT_H - 8
        d.rect(panel_x, panel_y, panel_w, panel_h, theme.CARD, fill=True)
        d.rect(panel_x, panel_y, panel_w, 2, theme.PRIMARY, fill=True)

        # ── content layout (drawn into "virtual" Y, then translated by scroll)
        cy_logical = 0    # logical y inside the panel; 0 = top of panel
        draw_y     = lambda y: panel_y + 6 + y - self._scroll

        # mascot + title block
        if self._mascot:
            data, mw, mh = self._mascot
            mx = panel_x + 12
            my = draw_y(cy_logical)
            if panel_y <= my <= panel_y + panel_h - mh:
                d.blit(data, mx, my, mw, mh)
            elif my + mh > panel_y and my < panel_y + panel_h:
                # partial — let display clip handle it
                d.blit(data, mx, my, mw, mh)

        tcol_x = panel_x + 96
        ty = draw_y(cy_logical + 4)
        if self._pf_title and panel_y <= ty <= panel_y + panel_h - 24:
            self._pf_title.text(d, "OREO", tcol_x, ty, theme.PRIMARY)
        elif panel_y <= ty <= panel_y + panel_h - 24:
            d.text("OREO", tcol_x, ty, theme.PRIMARY, scale=3)
        ty2 = draw_y(cy_logical + 32)
        if self._pf_body and panel_y <= ty2 <= panel_y + panel_h - 16:
            self._pf_body.text(d, "OS", tcol_x, ty2, theme.TEAL)
        elif panel_y <= ty2 <= panel_y + panel_h - 16:
            d.text("OS", tcol_x, ty2, theme.TEAL, scale=2)

        cy_logical += 84    # mascot block

        # ── info rows
        for label, value in self._info_rows():
            yy = draw_y(cy_logical)
            if panel_y - 12 <= yy <= panel_y + panel_h:
                d.text(label, panel_x + 16, yy, theme.MUTED)
                d.text(str(value), panel_x + 100, yy, theme.TEXT_BRIGHT)
            cy_logical += 14

        cy_logical += 10

        # ── credits section
        sep_y = draw_y(cy_logical)
        if panel_y <= sep_y <= panel_y + panel_h:
            d.rect(panel_x + 16, sep_y, panel_w - 32, 1, theme.PRIMARY, fill=True)
        cy_logical += 8

        for line, col, scale in [
                ("Crafted by",                          theme.MUTED,       1),
                ("@Circuit-Overtime",                   theme.PRIMARY,     2),
                ("in India",                            theme.TEXT_BRIGHT, 1),
                ("",                                    theme.MUTED,       1),
                ("Powered by Lix HAL +",                theme.TEXT_DIM,    1),
                ("MicroPython on the",                  theme.TEXT_DIM,    1),
                ("Elixpo Badge platform.",              theme.TEXT_DIM,    1),
                ("",                                    theme.MUTED,       1),
                ("Source on GitHub at",                 theme.TEXT_DIM,    1),
                ("github.com/Circuit-",                 theme.TEAL,        1),
                ("Overtime/elixpo-badge",               theme.TEAL,        1),
        ]:
            yy = draw_y(cy_logical)
            if panel_y - 16 <= yy <= panel_y + panel_h:
                lw = len(line) * 8 * scale
                d.text(line, panel_x + (panel_w - lw) // 2, yy, col, scale=scale)
            cy_logical += 10 * scale + 4

        # ── scrollbar
        if cy_logical > panel_h - 12:
            self._max_scroll = cy_logical - panel_h + 16
            track_h = panel_h - 8
            thumb_h = max(16, track_h * panel_h // cy_logical)
            thumb_y = panel_y + 4 + (track_h - thumb_h) * self._scroll \
                                          // max(1, self._max_scroll)
            d.rect(panel_x + panel_w - 4, panel_y + 4, 2, track_h, theme.MUTED2, fill=True)
            d.rect(panel_x + panel_w - 4, thumb_y, 2, thumb_h, theme.PRIMARY, fill=True)
        else:
            self._max_scroll = 0

        self._dirty = False

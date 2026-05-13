"""About — mascot + Elixpo OS info + build metadata.

Standardized header, optional mascot sprite on the left, info column on
the right with version / IP / uptime / free-RAM.
"""

import gc
import time
import sys

import lix
from lix import api
from lix_os import theme, widgets


def _load_mascot():
    try:
        m = __import__("assets.sprites.optimized.mascot", None, None, ["DATA", "W", "H"])
        return (bytearray(m.DATA), m.W, m.H)
    except (ImportError, AttributeError):
        return None


def _kb(b):
    return "%d kB" % (b // 1024)


class App(lix.App):
    name = "About"

    def on_enter(self, os):
        super().on_enter(os)
        self._os      = os
        self._dirty   = True
        self._mascot  = _load_mascot()
        self._boot_ms = time.ticks_ms()
        self._last_s  = -1
        try:
            from lix_hw import wifi
            self._ip = wifi.ip() or "—"
        except Exception:
            self._ip = "—"

    def update(self, dt):
        s = time.ticks_diff(time.ticks_ms(), self._boot_ms) // 1000
        if s != self._last_s:
            self._last_s = s
            self._dirty  = True

    def on_button_press(self, btn):
        if btn == api.BTN_A:
            self._os.quit()

    def draw(self, d):
        if not self._dirty:
            return
        d.clear(theme.BG)
        widgets.draw_header(d, "ABOUT")
        widgets.draw_hint  (d, "A=close  HOME=back")

        # Mascot on the left
        if self._mascot:
            data, mw, mh = self._mascot
            d.blit(data, 16, widgets.HEADER_H + 24, mw, mh)
        else:
            d.rect(16, widgets.HEADER_H + 24, 72, 72, theme.PRIMARY, fill=True)

        # Info column on the right
        col_x = 110
        y     = widgets.HEADER_H + 12
        d.text("ELIXPO",   col_x, y, theme.PRIMARY,     scale=3); y += 28
        d.text("BADGE OS", col_x, y, theme.TEAL,        scale=2); y += 20

        secs = self._last_s
        rows = [
            ("Ver",    "v0.1"),
            ("IP",     self._ip[:14]),
            ("Free",   _kb(gc.mem_free())),
            ("Up",     "%02d:%02d:%02d" % (secs // 3600,
                                          (secs % 3600) // 60,
                                           secs % 60)),
        ]
        for label, value in rows:
            d.text(label, col_x,     y, theme.MUTED)
            d.text(value, col_x + 36, y, theme.TEXT_BRIGHT)
            y += 12

        self._dirty = False

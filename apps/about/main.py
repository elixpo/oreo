"""About — system info: OS, chip, RAM, uptime. Uptime doubles as a 'time since
boot' clock until we add a real RTC module."""

import gc
import sys
import time

import lix
from lix import api


PRIMARY = (0, 220, 200)
ACCENT  = (255, 80, 200)
MUTED   = (140, 140, 170)


def _format_uptime_ms(ms):
    secs = ms // 1000
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    return "%02d:%02d:%02d" % (h, m, s)


def _kb(b):
    return "%d kB" % (b // 1024)


class App(lix.App):
    name = "About"

    def on_enter(self, os):
        super().on_enter(os)
        self.boot_ms = time.ticks_ms()
        self.last_sec = -1
        self.dirty = True

    def update(self, dt):
        elapsed_sec = time.ticks_diff(time.ticks_ms(), self.boot_ms) // 1000
        if elapsed_sec != self.last_sec:
            self.last_sec = elapsed_sec
            self.dirty = True

    def draw(self, d):
        if not self.dirty:
            return
        bg = api.rgb(8, 8, 20)
        primary = api.rgb(*PRIMARY)
        muted = api.rgb(*MUTED)

        d.clear(bg)
        # header
        d.rect(0, 0, api.SCREEN_W, 30, primary, fill=True)
        d.text("ABOUT", 8, 11, api.BLACK, scale=2)
        d.text("ELIXPO", api.SCREEN_W - 70, 11, api.BLACK, scale=2)

        # body — labels left, values right
        free = gc.mem_free()
        used = gc.mem_alloc()
        total = free + used
        uptime = _format_uptime_ms(time.ticks_diff(time.ticks_ms(), self.boot_ms))
        impl = sys.implementation
        mp_ver = ".".join(str(p) for p in impl.version)

        rows = [
            ("OS",     "Elixpo v0.1"),
            ("Chip",   "ESP32-S3"),
            ("Python", "MicroPython"),
            ("Ver",    mp_ver),
            ("RAM",    "%s / %s" % (_kb(used), _kb(total))),
            ("Free",   _kb(free)),
            ("Uptime", uptime),
        ]
        y = 50
        for label, value in rows:
            d.text(label, 16, y, muted, scale=2)
            d.text(value, 110, y, api.WHITE, scale=2)
            y += 24

        # divider + footer
        d.rect(0, api.SCREEN_H - 40, api.SCREEN_W, 40, api.rgb(*ACCENT), fill=True)
        d.text("HOME  menu", 70, api.SCREEN_H - 28, api.BLACK, scale=2)

        self.dirty = False

"""Settings — WiFi / BT / brightness / version.

Five rows, UP/DOWN to select, A toggles or actions, HOME exits.
"""

import oreoOS
from oreoOS import api
from oreoOS import theme, widgets

SW = api.SCREEN_W
SH = api.SCREEN_H

ROW_H        = 28
ROW_PAD_X    = 18
ROW_TOP_Y    = widgets.HEADER_H + 8


class _Row:
    __slots__ = ("label", "kind", "getter", "setter")
    def __init__(self, label, kind, getter=None, setter=None):
        self.label  = label
        self.kind   = kind        # "toggle" | "info" | "action" | "slider"
        self.getter = getter
        self.setter = setter


class App(oreoOS.App):
    name = "Settings"

    def on_enter(self, os):
        self._os    = os
        self._sel   = 0
        self._dirty = True

        # Lazily import the WiFi / BT modules so the sim doesn't crash.
        try:
            from oreoWare import wifi as _w, bt as _b
            self._wifi = _w
            self._bt   = _b
        except Exception:
            self._wifi = None
            self._bt   = None

        self._brightness = 100   # logical brightness (0..100), backlight is pure HIGH for now
        self._rows = [
            _Row("WiFi",       "toggle",
                 getter=lambda: self._wifi and self._wifi.is_connected(),
                 setter=lambda v: self._toggle_wifi(v)),
            _Row("WiFi IP",    "info",
                 getter=lambda: (self._wifi.ip() if self._wifi else None) or "—"),
            _Row("Bluetooth",  "toggle",
                 getter=lambda: self._bt and self._bt.is_active(),
                 setter=lambda v: self._bt and self._bt.set_active(v)),
            _Row("Brightness", "slider",
                 getter=lambda: self._brightness,
                 setter=lambda v: self._set_brightness(v)),
            _Row("Version",    "info",
                 getter=lambda: "v0.1"),
            _Row("Reboot",     "action",
                 setter=lambda v: self._reboot()),
        ]

    # ── actions ──────────────────────────────────────────────────────────
    def _toggle_wifi(self, on):
        if not self._wifi:
            return
        if on:
            self._wifi.connect_from_config()
        else:
            self._wifi.disconnect()

    def _set_brightness(self, v):
        self._brightness = max(0, min(100, v))
        # Drive the LCD backlight via the PWM helper on the Display object.
        try:
            setter = getattr(self._os.display, "set_brightness", None)
            if setter:
                setter(self._brightness)
        except Exception:
            pass

    def _reboot(self):
        try:
            import machine
            machine.reset()
        except Exception:
            self._os.quit()

    # ── input ────────────────────────────────────────────────────────────
    def on_button_press(self, btn):
        n = len(self._rows)
        if   btn == api.BTN_UP:    self._sel = (self._sel - 1) % n; self._dirty = True
        elif btn == api.BTN_DOWN:  self._sel = (self._sel + 1) % n; self._dirty = True
        elif btn == api.BTN_LEFT:
            self._adjust(-10); self._dirty = True
        elif btn == api.BTN_RIGHT:
            self._adjust(+10); self._dirty = True
        elif btn == api.BTN_A:
            self._activate(); self._dirty = True

    def _adjust(self, delta):
        row = self._rows[self._sel]
        if row.kind == "slider":
            row.setter(row.getter() + delta)

    def _activate(self):
        row = self._rows[self._sel]
        if row.kind == "toggle":
            row.setter(not row.getter())
        elif row.kind == "action":
            row.setter(None)

    def update(self, dt):
        pass

    # ── render ───────────────────────────────────────────────────────────
    def draw(self, d):
        if not self._dirty:
            return
        d.clear(theme.BG)
        widgets.draw_header(d, "SETTINGS")
        widgets.draw_hint  (d, "A=toggle  L/R=slider  HOME=back")

        for i, row in enumerate(self._rows):
            y   = ROW_TOP_Y + i * ROW_H
            sel = (i == self._sel)
            if sel:
                d.rect(0, y - 2, SW, ROW_H - 2, theme.DOCK_SEL, fill=True)
                d.rect(0, y - 2, 4, ROW_H - 2, theme.PRIMARY,  fill=True)

            d.text(row.label, ROW_PAD_X, y + 6, theme.TEXT_BRIGHT, scale=2)

            val_x = SW - 18
            self._draw_value(d, row, val_x, y)

        self._dirty = False

    def _draw_value(self, d, row, right_x, y):
        if row.kind == "toggle":
            on = bool(row.getter())
            label = "ON" if on else "OFF"
            color = theme.GREEN if on else theme.MUTED
            d.text(label, right_x - len(label) * 8 * 2, y + 6, color, scale=2)
        elif row.kind == "slider":
            v = int(row.getter())
            # Slider bar
            bar_w = 80
            bar_x = right_x - bar_w
            d.rect(bar_x, y + 10,         bar_w, 4, theme.MUTED2, fill=True)
            fill_w = int(bar_w * v / 100)
            d.rect(bar_x, y + 10, fill_w, 4, theme.PRIMARY, fill=True)
            d.text("%d" % v, bar_x - 32, y + 6, theme.TEXT_BRIGHT)
        elif row.kind == "info":
            s = str(row.getter() or "—")[:14]
            d.text(s, right_x - len(s) * 8, y + 7, theme.MUTED)
        elif row.kind == "action":
            d.text(">", right_x - 8, y + 6, theme.PRIMARY, scale=2)

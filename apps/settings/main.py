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
    __slots__ = ("label", "kind", "getter", "setter", "step")
    def __init__(self, label, kind, getter=None, setter=None, step=10):
        self.label  = label
        self.kind   = kind        # "toggle" | "info" | "action" | "slider"
        self.getter = getter
        self.setter = setter
        # Per-row L/R adjustment step. 10 is right for percent-style sliders
        # (brightness 0-100); minute counters use 1 so 1->30 isn't 3 jumps.
        self.step   = step


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

        # Power-manager settings live in the SETTINGS dict in oreoOS.power.
        # Default to "on, 120 s" if the module isn't importable for any reason
        # (e.g. running on the build host without the power.py file).
        try:
            from oreoOS import power as _pm
            self._pm = _pm
            _pm.load_settings(os)
        except Exception:
            self._pm = None

        self._rows = [
            _Row("WiFi",        "toggle",
                 getter=lambda: self._wifi and self._wifi.is_connected(),
                 setter=lambda v: self._toggle_wifi(v)),
            _Row("WiFi IP",     "info",
                 getter=lambda: (self._wifi.ip() if self._wifi else None) or "—"),
            _Row("Bluetooth",   "toggle",
                 getter=lambda: self._bt and self._bt.is_active(),
                 setter=lambda v: self._bt and self._bt.set_active(v)),
            _Row("Brightness",  "slider",
                 getter=lambda: self._brightness,
                 setter=lambda v: self._set_brightness(v)),
            _Row("Auto Sleep",  "toggle",
                 getter=self._idle_enabled,
                 setter=self._set_idle_enabled),
            _Row("Sleep After", "slider",
                 getter=self._idle_minutes,
                 setter=self._set_idle_minutes,
                 step=1),
            _Row("Touch Wake",  "toggle",
                 getter=self._touch_wake,
                 setter=self._set_touch_wake),
            _Row("Version",     "info",
                 getter=self._os_version),
            _Row("Reboot",      "action",
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

    # ── power-manager getters / setters ──────────────────────────────────
    # The slider for "Sleep After" is in MINUTES (more user-friendly than
    # seconds for a 1–30 minute range). Persist as seconds internally so
    # the power manager's tick math stays in milliseconds without a unit
    # conversion every frame.
    def _idle_enabled(self):
        if not self._pm: return True
        return bool(self._pm.SETTINGS.get("idle_enable", True))

    def _set_idle_enabled(self, v):
        if not self._pm: return
        self._pm.SETTINGS["idle_enable"] = bool(v)
        self._pm.save_settings(self._os)

    def _idle_minutes(self):
        if not self._pm: return 2
        return max(1, int(self._pm.SETTINGS.get("idle_seconds", 120) / 60))

    def _set_idle_minutes(self, v):
        if not self._pm: return
        v = max(1, min(30, int(v)))
        self._pm.SETTINGS["idle_seconds"] = v * 60
        self._pm.save_settings(self._os)

    def _touch_wake(self):
        if not self._pm: return True
        return bool(self._pm.SETTINGS.get("touch_wake", True))

    def _set_touch_wake(self, v):
        if not self._pm: return
        self._pm.SETTINGS["touch_wake"] = bool(v)
        self._pm.save_settings(self._os)

    @staticmethod
    def _os_version():
        """Pull the live VERSION constant from the launcher so the Settings
        row stays in sync with the actual deployed OS — no double bookkeeping."""
        try:
            from oreoOS import launcher
            return getattr(launcher, "VERSION", "?")
        except Exception:
            return "?"

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
            self._adjust(-1); self._dirty = True
        elif btn == api.BTN_RIGHT:
            self._adjust(+1); self._dirty = True
        elif btn == api.BTN_A:
            self._activate(); self._dirty = True

    def _adjust(self, sign):
        """sign is +1 or -1 — multiplied by the row's own step."""
        row = self._rows[self._sel]
        if row.kind == "slider":
            row.setter(row.getter() + sign * row.step)

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

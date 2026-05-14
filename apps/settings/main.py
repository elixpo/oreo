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
PAD_TOP      = 8                  # breathing-room below the header
PAD_BOT      = 8                  # breathing-room above the hint bar
ROW_TOP_Y    = widgets.HEADER_H + PAD_TOP

# How many full rows fit inside the play area (used as the scroll window).
_PLAY_H       = SH - widgets.HEADER_H - widgets.HINT_H - PAD_TOP - PAD_BOT
VISIBLE_ROWS  = max(1, _PLAY_H // ROW_H)


class _Row:
    __slots__ = ("label", "kind", "getter", "setter", "step", "max_val",
                 "on_label", "off_label")
    def __init__(self, label, kind, getter=None, setter=None,
                 step=10, max_val=100,
                 on_label="ON", off_label="OFF"):
        self.label   = label
        self.kind    = kind        # "toggle" | "info" | "action" | "slider"
        self.getter  = getter
        self.setter  = setter
        # Per-row L/R adjustment step. 10 is right for percent-style sliders
        # (brightness 0-100); minute counters use 1 so 1->30 isn't 3 jumps.
        self.step    = step
        # Full-scale value the slider's progress-bar fills at. 100 for
        # brightness; 10 for the auto-sleep timer (so the bar reads full
        # when sleep-after is at its max 10 min).
        self.max_val = max_val
        # Custom labels for toggle rows where ON/OFF doesn't read well
        # ("App View" reads "Cat" / "Grid" instead).
        self.on_label  = on_label
        self.off_label = off_label


class App(oreoOS.App):
    name = "Settings"

    def on_enter(self, os):
        self._os         = os
        self._sel        = 0
        self._scroll_top = 0           # first visible row index
        self._dirty      = True

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
                 step=1, max_val=10),
            _Row("Touch Wake",  "toggle",
                 getter=self._touch_wake,
                 setter=self._set_touch_wake),
            _Row("Categorical", "toggle",
                 getter=self._app_view_categorical,
                 setter=self._set_app_view_categorical),
            _Row("App View",    "toggle",
                 getter=self._app_view_is_categories,
                 setter=self._set_app_view_categories,
                 on_label="Cat", off_label="Grid"),
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
        return max(0, int(self._pm.SETTINGS.get("idle_seconds", 120) / 60))

    def _set_idle_minutes(self, v):
        if not self._pm: return
        # 0 = auto-sleep off (power.py also skips when seconds == 0).
        # 10 = top cap so the slider doesn't run off into hours.
        v = max(0, min(10, int(v)))
        self._pm.SETTINGS["idle_seconds"] = v * 60
        self._pm.save_settings(self._os)

    def _touch_wake(self):
        if not self._pm: return True
        return bool(self._pm.SETTINGS.get("touch_wake", True))

    def _set_touch_wake(self, v):
        if not self._pm: return
        self._pm.SETTINGS["touch_wake"] = bool(v)
        self._pm.save_settings(self._os)

    # ── apps drawer view ────────────────────────────────────────────────
    # The launcher reads os.settings_get("app_view", "grid"). We toggle it
    # between "categories" (grouped per APP_CATEGORIES in config.py) and
    # "grid" (flat 4-col grid of every app).
    def _app_view_categorical(self):
        return self._os.settings_get("app_view", "grid") == "categories"

    def _set_app_view_categorical(self, v):
        self._os.settings_set("app_view", "categories" if v else "grid")

    # ── Apps-drawer view mode ───────────────────────────────────────────
    # Persisted on the OS settings dict; the launcher reads this each time
    # it loads to decide grid-vs-category layout.
    def _app_view_is_categories(self):
        try:
            return self._os.settings_get("app_view", "grid") == "categories"
        except Exception:
            return False

    def _set_app_view_categories(self, v):
        try:
            self._os.settings_set("app_view", "categories" if v else "grid")
        except Exception:
            pass

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
        if   btn == api.BTN_UP:    self._sel = (self._sel - 1) % n
        elif btn == api.BTN_DOWN:  self._sel = (self._sel + 1) % n
        elif btn == api.BTN_LEFT:  self._adjust(-1)
        elif btn == api.BTN_RIGHT: self._adjust(+1)
        elif btn == api.BTN_A:     self._activate()
        # Auto-scroll: keep the selected row inside the visible window.
        if self._sel < self._scroll_top:
            self._scroll_top = self._sel
        elif self._sel >= self._scroll_top + VISIBLE_ROWS:
            self._scroll_top = self._sel - VISIBLE_ROWS + 1
        # Clamp (handles wrap-around from DOWN past last row → 0)
        max_top = max(0, n - VISIBLE_ROWS)
        if self._scroll_top > max_top:
            self._scroll_top = max_top
        if self._scroll_top < 0:
            self._scroll_top = 0
        self._dirty = True

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

        n        = len(self._rows)
        top      = self._scroll_top
        end      = min(n, top + VISIBLE_ROWS)
        for vis_i, i in enumerate(range(top, end)):
            row = self._rows[i]
            y   = ROW_TOP_Y + vis_i * ROW_H
            sel = (i == self._sel)
            if sel:
                d.rect(0, y - 2, SW, ROW_H - 2, theme.DOCK_SEL, fill=True)
                d.rect(0, y - 2, 4, ROW_H - 2, theme.PRIMARY,  fill=True)
            d.text(row.label, ROW_PAD_X, y + 6, theme.TEXT_BRIGHT, scale=2)
            self._draw_value(d, row, SW - 18, y)

        self._dirty = False

    def _draw_value(self, d, row, right_x, y):
        if row.kind == "toggle":
            on    = bool(row.getter())
            label = row.on_label if on else row.off_label
            color = theme.GREEN if on else theme.MUTED
            d.text(label, right_x - len(label) * 8 * 2, y + 6, color, scale=2)
        elif row.kind == "slider":
            v       = int(row.getter())
            max_val = max(1, int(row.max_val))
            # "off" reads better than "0" for the sleep-after slider; the
            # brightness slider keeps numeric 0 (unambiguous percent).
            value_s = "off" if (v == 0 and row.max_val <= 30) else "%d" % v
            val_w   = len(value_s) * 8
            val_x   = right_x - val_w                          # right-aligned
            # Bar sits to the LEFT of the value with a comfortable gap. With
            # the value now anchored to the right edge there is no more risk
            # of overlapping a long label like "Sleep After".
            bar_w   = 50
            bar_x   = val_x - bar_w - 10
            d.rect(bar_x, y + 10, bar_w, 4, theme.MUTED2, fill=True)
            fill_w  = int(bar_w * v / max_val)
            d.rect(bar_x, y + 10, fill_w, 4, theme.PRIMARY, fill=True)
            d.text(value_s, val_x, y + 6, theme.TEXT_BRIGHT)
        elif row.kind == "info":
            s = str(row.getter() or "—")[:14]
            d.text(s, right_x - len(s) * 8, y + 7, theme.MUTED)
        elif row.kind == "action":
            d.text(">", right_x - 8, y + 6, theme.PRIMARY, scale=2)

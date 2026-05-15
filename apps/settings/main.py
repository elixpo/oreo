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
    name         = "Settings"
    author       = "Circuit-Overtime"
    SHOW_LOADING = True     # pulls the pink slide-down panel while on_enter
                            # wires up WiFi / BT / power manager imports.

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
            _Row("WiFi",        "action",
                 getter=lambda: self._wifi_summary(),
                 setter=lambda v: self._open_wifi()),
            _Row("Bluetooth",   "action",
                 getter=lambda: self._bt_summary(),
                 setter=lambda v: self._open_bt()),
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
            _Row("Categorical", "toggle",
                 getter=self._app_view_categorical,
                 setter=self._set_app_view_categorical),
            _Row("App View",    "toggle",
                 getter=self._app_view_is_categories,
                 setter=self._set_app_view_categories,
                 on_label="Cat", off_label="Grid"),
            _Row("Storage",     "action",
                 setter=lambda v: self._open_storage()),
            _Row("Sync Time",   "action",
                 getter=lambda: self._sync_time_summary(),
                 setter=lambda v: self._sync_time()),
            _Row("Version",     "info",
                 getter=self._os_version),
            _Row("Check Update","action",
                 setter=lambda v: self._check_update()),
            _Row("Install Update","action",
                 setter=lambda v: self._install_update()),
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

    # ── OTA actions ──────────────────────────────────────────────────────
    # Three-stage flow so the UI never blocks on a long HTTP call without
    # the user knowing what's happening:
    #   1. check()  — hit GitHub releases (T_GH_API timeout, ~10 s max)
    #   2. peek()   — fetch the manifest, compute SHA diff, total bytes
    #   3. download() — only the changed files (bounded per-file timeout)
    #
    # We store intermediate state on the OS settings dict so the home
    # screen / About page can render a status pill without re-checking.
    def _check_update(self):
        try:
            from oreoOS import ota
        except Exception:
            self._set_ota_status("error"); return

        rel = self._ota_safe(lambda: ota.check())
        if not rel:
            self._set_ota_status("up-to-date")
            return

        peeked = self._ota_safe(lambda: ota.peek(rel))
        if not peeked:
            self._set_ota_status("peek-failed")
            return

        # Park everything we just learned so _install_update / the
        # confirmation popup can act on it without re-fetching.
        self._os.settings_set("ota_pending_version", rel.get("version", ""))
        self._os.settings_set("ota_pending_bytes",   peeked["bytes"])
        self._os.settings_set("ota_pending_major",   peeked["major"])
        self._os.settings_set("ota_pending_changed", len(peeked["changed"]))
        # Stash the manifest URL too in case the popup needs to re-peek
        # on the next boot (cleared in _install_update).
        self._os.settings_set("ota_pending_url", rel["manifest_url"])

        # Small + non-major patches auto-stage in the background. Anything
        # bigger requires user confirmation — Settings flips a flag the
        # home screen reads to draw a confirmation popup.
        if peeked["small"] and not peeked["major"]:
            self._set_ota_status("downloading")
            ok = self._ota_safe(lambda: ota.download(peeked))
            self._set_ota_status("ready" if ok else "download-failed")
        else:
            # Defer to the popup. The home screen reads this flag.
            self._set_ota_status("needs-confirm")
            self._os.settings_set("ota_pending_peek_ok", True)

    def _install_update(self):
        """Triggered after the user confirms in the popup. Downloads (if
        not already staged) then reboots so the boot hook applies."""
        try:
            from oreoOS import ota
        except Exception:
            return

        if not ota.is_pending():
            # Need to actually fetch the bytes first. Re-peek so we don't
            # rely on transient state; this is the user-explicit path so
            # showing "downloading" is appropriate.
            rel = self._ota_safe(lambda: ota.check())
            if not rel:
                return
            peeked = self._ota_safe(lambda: ota.peek(rel))
            if not peeked:
                return
            self._set_ota_status("downloading")
            ok = self._ota_safe(lambda: ota.download(peeked))
            if not ok:
                self._set_ota_status("download-failed")
                return
            self._set_ota_status("ready")
        # Clear the popup flag and kick the chip.
        self._os.settings_set("ota_pending_peek_ok", False)
        self._reboot()

    def _set_ota_status(self, s):
        try:
            self._os.settings_set("ota_status", s)
        except Exception:
            pass

    @staticmethod
    def _ota_safe(callable_):
        """Run an OTA call inside try/except so a thrown HTTP error never
        bubbles up into the UI's button-press handler."""
        try:
            return callable_()
        except Exception:
            return None

    def _reboot(self):
        try:
            import machine
            machine.reset()
        except Exception:
            self._os.quit()

    def _open_storage(self):
        try:
            self._os.launch("storage")
        except Exception:
            pass

    # ── time sync ───────────────────────────────────────────────────────
    # Manual NTP re-sync. The boot path runs this once when WiFi comes up;
    # this row lets the user kick it again after they fix a bad clock or
    # land in a new timezone without rebooting. Result is mirrored to the
    # notif panel via timeutil's module-level last_sync_status.
    def _sync_time(self):
        try:
            from oreoOS import timeutil
            timeutil.sync_from_ntp()
        except Exception:
            pass

    def _sync_time_summary(self):
        try:
            from oreoOS import timeutil
            status = timeutil.last_sync_status()
        except Exception:
            return ""
        return {
            "ok":      "synced",
            "no-wifi": "no wifi",
            "failed":  "failed",
            "never":   "tap A",
        }.get(status, "tap A")

    def _open_wifi(self):
        try:
            self._os.launch("wifi")
        except Exception:
            pass

    def _wifi_summary(self):
        if not self._wifi:
            return "—"
        try:
            if self._wifi.is_connected():
                ip = self._wifi.ip() or ""
                return ip or "on"
            return "off"
        except Exception:
            return "—"

    def _open_bt(self):
        try:
            self._os.launch("bt")
        except Exception:
            pass

    def _bt_summary(self):
        if not self._bt:
            return "—"
        try:
            return "on" if self._bt.is_active() else "off"
        except Exception:
            return "—"

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
            # Phone-style: action rows can carry a preview string via
            # their getter ("WiFi  HomeNet >"). Empty / missing falls
            # back to bare chevron.
            chev_w = 16
            preview = ""
            if row.getter is not None:
                try:
                    preview = str(row.getter() or "")[:14]
                except Exception:
                    preview = ""
            if preview:
                d.text(preview,
                       right_x - chev_w - len(preview) * 8,
                       y + 7, theme.MUTED, scale=1)
            d.text(">", right_x - chev_w + 4, y + 6, theme.PRIMARY, scale=2)

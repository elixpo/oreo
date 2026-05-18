"""WiFi — phone-style detail screen.

Two modes:

  main : the per-row info screen (status / IP / power / auto-connect /
         saved-networks / speed / ping). UP/DOWN walks rows, A toggles
         or drills in.
  nets : the saved-networks sub-page. UP/DOWN walks entries, A connects
         to the focused entry (and promotes it to priority 1), B removes
         it, LEFT toggles its `metered` flag. HOME/B exits the sub-page
         back to main.

Saved networks live in `/wifi.json` on flash, managed by oreoWare.wifi.
The first network from .env is auto-seeded into /wifi.json on first
boot via the wifi module's bootstrap path.
"""

import oreoOS
from oreoOS import api, theme, widgets


SW = api.SCREEN_W
SH = api.SCREEN_H

ROW_H        = 22
ROW_PAD_X    = 12
ROW_TOP_Y    = widgets.HEADER_H + 6
VALUE_X      = 138
AUTOCON_GAP  = 8

POWER_LABELS = {
    "off":      "Off",
    "eco":      "Eco",
    "balanced": "Balanced",
    "max":      "Max",
}

POWER_HINTS = {
    "off":      "radio off",
    "eco":      "5 dBm  · PS",
    "balanced": "11 dBm · PS",
    "max":      "19 dBm · full",
}


def _bars(rssi_dbm):
    if rssi_dbm is None:
        return "----"
    if rssi_dbm >= -50:  return "####"
    if rssi_dbm >= -65:  return "###-"
    if rssi_dbm >= -75:  return "##--"
    if rssi_dbm >= -85:  return "#---"
    return "----"


class App(oreoOS.App):
    name         = "WiFi"
    author       = "Circuit-Overtime"
    SHOW_LOADING = True

    # Logical row indices — keeps cycle code readable when we re-order.
    (ROW_STATUS, ROW_SSID, ROW_IP, ROW_RSSI, ROW_POWER,
     ROW_NETS, ROW_SPEED, ROW_PING, ROW_AUTOCONNECT) = range(9)
    ROWS = (ROW_STATUS, ROW_SSID, ROW_IP, ROW_RSSI, ROW_POWER,
            ROW_NETS, ROW_SPEED, ROW_PING, ROW_AUTOCONNECT)

    def on_enter(self, os_):
        super().on_enter(os_)
        self._os    = os_
        self._sel   = self.ROW_STATUS
        self._dirty = True

        try:
            from oreoWare import wifi
            self._wifi = wifi
        except Exception:
            self._wifi = None

        # 5 Hz info refresh so RSSI and IP track reality without the user
        # having to back out and reopen the app.
        self._poll_t  = 0.0
        self._poll_dt = 0.2
        self._snap    = self._read()

        # Sub-page state
        self._mode    = "main"          # "main" | "nets"
        self._nets    = []              # cached saved-networks list
        self._nets_sel = 0

        # One-shot result strings shown under their respective rows.
        # `_speed_label` and `_ping_label` are set after a test runs;
        # they survive until the row's value re-renders normally.
        self._speed_label = ""
        self._ping_label  = ""
        self._busy        = ""          # "speed" | "ping" while a test runs

    # ── data ────────────────────────────────────────────────────────────
    def _read(self):
        if not self._wifi:
            return {"connected": False}
        try:
            return self._wifi.info()
        except Exception:
            return {"connected": False}

    def _power_mode(self):
        if not self._wifi:
            return "balanced"
        try:
            return self._wifi.get_power_mode()
        except Exception:
            return "balanced"

    def _autoconnect(self):
        try:
            return bool(self._os.settings_get("wifi_autoconnect", True))
        except Exception:
            return True

    def _reload_nets(self):
        try:
            self._nets = self._wifi.list_saved() if self._wifi else []
        except Exception:
            self._nets = []
        if self._nets_sel >= len(self._nets):
            self._nets_sel = max(0, len(self._nets) - 1)

    # ── input ───────────────────────────────────────────────────────────
    def on_button_press(self, btn):
        if self._mode == "nets":
            return self._on_button_nets(btn)
        return self._on_button_main(btn)

    def _on_button_main(self, btn):
        if btn == api.BTN_HOME:
            self._os.quit()
            return
        if btn == api.BTN_UP:
            self._sel = (self._sel - 1) % len(self.ROWS)
        elif btn == api.BTN_DOWN:
            self._sel = (self._sel + 1) % len(self.ROWS)
        elif btn == api.BTN_A:
            self._activate_row()
        else:
            return
        self._dirty = True

    def _on_button_nets(self, btn):
        if btn in (api.BTN_HOME, api.BTN_B) and not self._nets:
            # Empty list — only escape is back out.
            self._mode = "main"
            self._dirty = True
            return
        if btn == api.BTN_HOME:
            self._mode = "main"
            self._dirty = True
            return
        n = len(self._nets)
        if n == 0:
            return
        if btn == api.BTN_UP:
            self._nets_sel = (self._nets_sel - 1) % n
        elif btn == api.BTN_DOWN:
            self._nets_sel = (self._nets_sel + 1) % n
        elif btn == api.BTN_A:
            self._connect_saved(self._nets[self._nets_sel])
        elif btn == api.BTN_B:
            self._forget_saved(self._nets[self._nets_sel])
        elif btn == api.BTN_LEFT:
            self._toggle_metered(self._nets[self._nets_sel])
        else:
            return
        self._dirty = True

    def _activate_row(self):
        if not self._wifi:
            return
        r = self._sel
        if r == self.ROW_STATUS:
            if self._snap.get("connected"):
                try:
                    self._wifi.disconnect()
                except Exception:
                    pass
            else:
                try:
                    self._wifi.connect_from_config()
                except Exception:
                    pass
            self._snap = self._read()
        elif r == self.ROW_POWER:
            modes = self._wifi.POWER_MODES
            cur   = self._power_mode()
            try:
                nxt = modes[(modes.index(cur) + 1) % len(modes)]
            except ValueError:
                nxt = modes[0]
            try:
                self._wifi.set_power_mode(nxt)
                self._os.settings_set("wifi_power_mode", nxt)
            except Exception:
                pass
            self._snap = self._read()
        elif r == self.ROW_AUTOCONNECT:
            try:
                self._os.settings_set("wifi_autoconnect",
                                      not self._autoconnect())
            except Exception:
                pass
        elif r == self.ROW_NETS:
            self._reload_nets()
            self._nets_sel = 0
            self._mode     = "nets"
        elif r == self.ROW_SPEED:
            self._run_speed_test()
        elif r == self.ROW_PING:
            self._run_ping()

    # ── async-ish helpers (blocking but with a "Testing..." paint) ──────
    def _paint_busy(self, label):
        """Force a frame showing the busy label so the user sees that
        the device hasn't frozen during the synchronous test call."""
        self._busy = label
        self._dirty = True
        try:
            self.draw(self._os.display)
            self._os.display.present()
        except Exception:
            pass

    def _run_speed_test(self):
        if not self._wifi or not self._snap.get("connected"):
            self._speed_label = "no link"
            return
        self._speed_label = "testing…"
        self._paint_busy("speed")
        try:
            ok, kbps, ms = self._wifi.speed_test()
        except Exception:
            ok, kbps, ms = (False, 0, 0)
        self._busy = ""
        if not ok or kbps <= 0:
            self._speed_label = "failed"
        elif kbps >= 1000:
            self._speed_label = "%.1f Mbps · %d ms" % (kbps / 1000.0, ms)
        else:
            self._speed_label = "%d kbps · %d ms" % (kbps, ms)
        self._dirty = True

    def _run_ping(self):
        if not self._wifi or not self._snap.get("connected"):
            self._ping_label = "no link"
            return
        self._ping_label = "pinging…"
        self._paint_busy("ping")
        try:
            ok, rtt = self._wifi.ping()
        except Exception:
            ok, rtt = (False, None)
        self._busy = ""
        if not ok or rtt is None:
            self._ping_label = "timeout"
        else:
            self._ping_label = "%d ms" % rtt
        self._dirty = True

    # ── saved-network actions ───────────────────────────────────────────
    def _connect_saved(self, net):
        ssid = net.get("ssid") or ""
        pw   = net.get("password") or ""
        if not ssid:
            return
        # Promote to priority 1 so it auto-reconnects next boot.
        try:
            self._wifi.set_priority(ssid, 1)
        except Exception:
            pass
        # Synchronous connect — blocks the run loop briefly. We don't
        # paint a busy label because the existing Status row already
        # flips "ON"/"OFF" once it's settled.
        try:
            self._wifi.connect(ssid, pw)
        except Exception:
            pass
        self._snap = self._read()
        self._reload_nets()
        self._mode = "main"

    def _forget_saved(self, net):
        ssid = net.get("ssid") or ""
        if not ssid:
            return
        try:
            self._wifi.remove_saved(ssid)
        except Exception:
            pass
        self._reload_nets()

    def _toggle_metered(self, net):
        ssid = net.get("ssid") or ""
        if not ssid:
            return
        try:
            self._wifi.add_saved(ssid, net.get("password") or "",
                                 priority=int(net.get("priority", 10)),
                                 metered=not bool(net.get("metered")))
        except Exception:
            pass
        self._reload_nets()

    # ── update ──────────────────────────────────────────────────────────
    def update(self, dt):
        self._poll_t += dt
        if self._poll_t < self._poll_dt:
            return
        self._poll_t = 0.0
        fresh = self._read()
        if fresh != self._snap:
            self._snap = fresh
            self._dirty = True

    # ── render ──────────────────────────────────────────────────────────
    def draw(self, d):
        if not self._dirty:
            return
        self._dirty = False
        d.clear(theme.BG)
        if self._mode == "nets":
            self._draw_nets(d)
            return
        widgets.draw_header(d, "WIFI")
        widgets.draw_hint(d, "A=select  HOME=back")

        snap = self._snap
        rows = [
            ("Status",       "ON" if snap.get("connected") else "OFF",
                             theme.PRIMARY if snap.get("connected")
                                            else theme.MUTED),
            ("SSID",         snap.get("ssid") or "—",       theme.TEXT_BRIGHT),
            ("IP",           snap.get("ip") or "—",         theme.TEXT_DIM),
            ("RSSI",         self._rssi_value(snap),        theme.TEXT_DIM),
            ("Power",        POWER_LABELS.get(self._power_mode(), "?"),
                                                             theme.TEAL),
            ("Networks",     self._nets_summary(),          theme.TEXT_BRIGHT),
            ("Speed",        self._speed_label or "—",      theme.TEAL),
            ("Ping",         self._ping_label  or "—",      theme.TEAL),
            ("Auto-connect", "ON" if self._autoconnect() else "OFF",
                             theme.TEXT_BRIGHT),
        ]
        for i, (label, value, color) in enumerate(rows):
            y = ROW_TOP_Y + i * ROW_H
            if i == self.ROW_AUTOCONNECT:
                y += AUTOCON_GAP
            sel = (i == self._sel)
            if sel:
                d.rect(4, y - 2, SW - 8, ROW_H - 1,
                       theme.DOCK_SEL, fill=True)
                d.rect(4, y - 2, SW - 8, 1, theme.SEL_BORDER, fill=True)
                d.rect(4, y + ROW_H - 4, SW - 8, 1,
                       theme.SEL_BORDER, fill=True)
            d.text(label, ROW_PAD_X, y + 4, theme.TEXT_BRIGHT, scale=1)
            d.text(str(value)[:20], VALUE_X, y + 4, color, scale=1)

        # Thin divider above Auto-connect.
        sep_y = ROW_TOP_Y + self.ROW_AUTOCONNECT * ROW_H + AUTOCON_GAP // 2 - 1
        d.rect(ROW_PAD_X, sep_y, SW - 2 * ROW_PAD_X, 1, theme.MUTED2, fill=True)

    def _nets_summary(self):
        try:
            n = len(self._wifi.list_saved()) if self._wifi else 0
        except Exception:
            n = 0
        return "%d saved" % n

    def _draw_nets(self, d):
        widgets.draw_header(d, "NETWORKS")
        widgets.draw_hint(d, "A=connect  B=forget  L=metered")
        if not self._nets:
            self._reload_nets()
        if not self._nets:
            d.text("no saved networks", ROW_PAD_X, ROW_TOP_Y + 16,
                   theme.MUTED, scale=1)
            d.text("flash /wifi.json or add via .env",
                   ROW_PAD_X, ROW_TOP_Y + 34, theme.MUTED2, scale=1)
            return
        cur_ssid = self._snap.get("ssid") or ""
        for i, n in enumerate(self._nets):
            y = ROW_TOP_Y + i * ROW_H
            sel = (i == self._nets_sel)
            if sel:
                d.rect(4, y - 2, SW - 8, ROW_H - 1,
                       theme.DOCK_SEL, fill=True)
                d.rect(4, y - 2, SW - 8, 1, theme.SEL_BORDER, fill=True)
                d.rect(4, y + ROW_H - 4, SW - 8, 1,
                       theme.SEL_BORDER, fill=True)
            ssid = (n.get("ssid") or "?")[:18]
            d.text(ssid, ROW_PAD_X, y + 4, theme.TEXT_BRIGHT, scale=1)
            # Right side: priority number + active dot + metered $.
            pri = "p%d" % int(n.get("priority", 10))
            d.text(pri, VALUE_X, y + 4, theme.MUTED, scale=1)
            x = VALUE_X + 28
            if n.get("ssid") == cur_ssid:
                d.text("●", x, y + 4, theme.PRIMARY, scale=1)
                x += 12
            if n.get("metered"):
                d.text("$", x, y + 4, theme.GOLD, scale=1)

    def _rssi_value(self, snap):
        rssi = snap.get("rssi")
        if rssi is None:
            return "—"
        return "%d dBm %s" % (rssi, _bars(rssi))

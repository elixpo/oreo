"""WiFi — phone-style detail screen.

Replaces the two-row WiFi/IP entries in Settings. Shows live status,
DHCP-assigned IP / subnet / gateway / DNS, RSSI bars, and a single
"power mode" cycle (off / eco / balanced / max) that bundles TX power
and power-save state together.

Controls:
  UP/DOWN  pick a row
  A        toggle (status) / cycle (power mode) / disconnect (IP row)
  HOME     back to Settings
"""

import oreoOS
from oreoOS import api, theme, widgets


SW = api.SCREEN_W
SH = api.SCREEN_H

ROW_H        = 22
ROW_PAD_X    = 12
ROW_TOP_Y    = widgets.HEADER_H + 6
VALUE_X      = 138        # left edge of the right-aligned value column
AUTOCON_GAP  = 8          # extra breathing room above the Auto-connect row
                          # so it reads as a separate group from the live
                          # link-info rows above it

# Power-mode helpers — bound at on_enter so the build host (no wifi
# module) doesn't crash module import.

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
    """Map RSSI to a 4-cell bar string. -50 dBm or stronger = full."""
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
    ROW_STATUS, ROW_SSID, ROW_IP, ROW_SUBNET, ROW_GATEWAY, \
        ROW_RSSI, ROW_POWER, ROW_AUTOCONNECT = range(8)
    ROWS = (ROW_STATUS, ROW_SSID, ROW_IP, ROW_SUBNET, ROW_GATEWAY,
            ROW_RSSI, ROW_POWER, ROW_AUTOCONNECT)

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

    # ── input ───────────────────────────────────────────────────────────
    def on_button_press(self, btn):
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
        widgets.draw_header(d, "WIFI")
        widgets.draw_hint(d, "A=toggle/cycle  HOME=back")

        snap = self._snap
        rows = [
            ("Status",       "ON" if snap.get("connected") else "OFF",
                             theme.PRIMARY if snap.get("connected")
                                            else theme.MUTED),
            ("SSID",         snap.get("ssid") or "—",       theme.TEXT_BRIGHT),
            ("IP",           snap.get("ip") or "—",         theme.TEXT_DIM),
            ("Subnet",       snap.get("subnet") or "—",     theme.TEXT_DIM),
            ("Gateway",      snap.get("gateway") or "—",    theme.TEXT_DIM),
            ("RSSI",         self._rssi_value(snap),        theme.TEXT_DIM),
            ("Power",        POWER_LABELS.get(self._power_mode(), "?"),
                                                             theme.TEAL),
            ("Auto-connect", "ON" if self._autoconnect() else "OFF",
                             theme.TEXT_BRIGHT),
        ]
        for i, (label, value, color) in enumerate(rows):
            # Auto-connect sits in its own group below the live link-info
            # rows; nudge it down so the visual break matches its logical
            # role as a persistent preference rather than a live readout.
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

        # Thin divider in the gap above Auto-connect to make the group
        # break read as deliberate, not as a bug.
        sep_y = ROW_TOP_Y + self.ROW_AUTOCONNECT * ROW_H + AUTOCON_GAP // 2 - 1
        d.rect(ROW_PAD_X, sep_y, SW - 2 * ROW_PAD_X, 1, theme.MUTED2, fill=True)

        # Mode sub-line — small caption under the Power row.
        mode = self._power_mode()
        hint = POWER_HINTS.get(mode, "")
        if hint:
            y = ROW_TOP_Y + self.ROW_POWER * ROW_H + ROW_H - 4
            d.text(hint, VALUE_X, y, theme.MUTED, scale=1)

    def _rssi_value(self, snap):
        rssi = snap.get("rssi")
        if rssi is None:
            return "—"
        return "%d dBm %s" % (rssi, _bars(rssi))

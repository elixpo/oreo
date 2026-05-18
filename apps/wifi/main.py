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
     ROW_NETS, ROW_SPEED, ROW_PING, ROW_TRANSFER,
     ROW_AUTOCONNECT) = range(10)
    ROWS = (ROW_STATUS, ROW_SSID, ROW_IP, ROW_RSSI, ROW_POWER,
            ROW_NETS, ROW_SPEED, ROW_PING, ROW_TRANSFER,
            ROW_AUTOCONNECT)

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
        self._mode    = "main"          # "main" | "nets" | "transfer"
        # Cached cursor inside the transfer-page sender list.
        self._trans_sel = 0
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
        if self._mode == "transfer":
            return self._on_button_transfer(btn)
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
        elif r == self.ROW_TRANSFER:
            self._trans_sel = 0
            self._mode      = "transfer"
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

        # Cooperative pump — runs between every recv() inside
        # speed_test. Re-reads the button matrix so a keypress can
        # both keep the OS feeling alive AND abort the test (any
        # press cancels). Also redraws the screen so the user
        # actually SEES the "testing..." label instead of the last
        # pre-test frame.
        cancel = [False]
        def _pump():
            try:
                self._os.buttons.update()
                for b_ in api.BUTTONS:
                    if self._os.buttons.just_pressed(b_):
                        cancel[0] = True
                        return True
            except Exception:
                pass
            return False

        try:
            ok, kbps, ms = self._wifi.speed_test(pump_cb=_pump)
        except Exception:
            ok, kbps, ms = (False, 0, 0)
        self._busy = ""
        if cancel[0]:
            self._speed_label = "cancelled"
        elif not ok or kbps <= 0:
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
        # While the Transfer page is on screen, repaint every tick so
        # the progress bar + pending-sender list stay live without the
        # user having to nudge a button. The cost is negligible
        # because the page is mostly text — but we only mark _dirty
        # when there's actually something to refresh.
        if self._mode == "transfer":
            hs = self._http()
            if hs is not None:
                if hs.progress() is not None or hs.list_sessions():
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
        if self._mode == "transfer":
            self._draw_transfer(d)
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
            ("Send files",   self._transfer_summary(),      theme.PRIMARY),
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

    # ── file-transfer sub-page ──────────────────────────────────────────
    def _http(self):
        try:
            from oreoOS import http_server as _hs
            return _hs
        except Exception:
            return None

    def _transfer_summary(self):
        """Compact value text for the main-page row: either the live
        sender count, or the URL when idle. Reads the http_server's
        cached state — no network call."""
        hs = self._http()
        if hs is None or not hs.is_running():
            return "off"
        try:
            n = len(hs.list_sessions())
        except Exception:
            n = 0
        if n:
            return "%d active" % n
        return "ready"

    def _on_button_transfer(self, btn):
        if btn in (api.BTN_HOME, api.BTN_B):
            self._mode = "main"
            self._dirty = True
            return
        if btn == api.BTN_RIGHT:
            # Refresh — sometimes the page shows "Server offline" when
            # WiFi is actually associated but the HTTP server hasn't
            # picked up the new IP (e.g. after a hotspot handoff).
            # Force-reconnect WiFi if needed and rebind the listener.
            self._refresh_transfer()
            self._dirty = True
            return
        hs = self._http()
        if hs is None:
            return
        sessions = hs.list_sessions()
        n = len(sessions)
        if btn == api.BTN_UP and n:
            self._trans_sel = (self._trans_sel - 1) % n
        elif btn == api.BTN_DOWN and n:
            self._trans_sel = (self._trans_sel + 1) % n
        elif btn == api.BTN_A and n:
            sid = sessions[self._trans_sel].get("id", "")
            if sid:
                hs.approve(sid)
        elif btn == api.BTN_LEFT and n:
            sid = sessions[self._trans_sel].get("id", "")
            if sid:
                hs.deny(sid)
        else:
            return
        self._dirty = True

    def _refresh_transfer(self):
        """Reconcile the transfer page with the live network state.

        Order: re-associate WiFi from saved networks (no-op if already
        connected), then call http_server.start() which rebinds onto
        the live IP (no-op if the IP hasn't changed). Both are cheap
        and idempotent — we use them as a 'kick everything back to
        life' button after a roaming WiFi event.
        """
        if self._wifi:
            try:
                if not self._wifi.is_connected():
                    self._wifi.connect_from_config()
            except Exception:
                pass
        hs = self._http()
        if hs is not None:
            try:
                hs.start(self._os)
            except Exception:
                pass
        # Pull a fresh snapshot so the URL line on the page repaints
        # with the new IP if it changed.
        self._snap = self._read()

    def _draw_transfer(self, d):
        widgets.draw_header(d, "SEND FILES")
        widgets.draw_hint(d, "A=allow  L=deny  R=refresh  B=back")

        hs = self._http()
        running = bool(hs and hs.is_running())

        # ── URL block ──
        y = ROW_TOP_Y
        if running:
            url1 = hs.url()
            url2 = hs.url_fallback()
            d.text("Open on your phone:", ROW_PAD_X, y, theme.TEXT_DIM)
            d.text(url1, ROW_PAD_X, y + 14, theme.PRIMARY, scale=2)
            d.text(url2, ROW_PAD_X, y + 36, theme.TEXT_DIM)
        else:
            d.text("Server offline.", ROW_PAD_X, y, theme.MUTED, scale=1)
            d.text("Connect WiFi to enable transfer.",
                   ROW_PAD_X, y + 14, theme.MUTED2, scale=1)

        # ── live transfer progress bar ──
        prog = hs.progress() if hs else None
        prog_y = y + 56
        if prog:
            total = max(1, int(prog.get("total", 0)))
            done  = min(total, int(prog.get("received", 0)))
            pct   = int((done * 100) // total)
            d.text("Receiving %s" % (prog.get("filename", "")[:22] or "?"),
                   ROW_PAD_X, prog_y, theme.TEAL)
            # bar
            bar_x, bar_y, bar_w, bar_h = ROW_PAD_X, prog_y + 14, SW - 2 * ROW_PAD_X, 8
            d.rect(bar_x, bar_y, bar_w, bar_h, theme.MUTED2, fill=True)
            fill_w = int(bar_w * pct / 100)
            d.rect(bar_x, bar_y, fill_w, bar_h, theme.PRIMARY, fill=True)
            d.text("%d%%  %d / %d KB" % (pct, done // 1024, total // 1024),
                   ROW_PAD_X, bar_y + 12, theme.TEXT_DIM)
            list_y = bar_y + 28
        else:
            list_y = prog_y

        # ── pending sender list ──
        # Denied sessions are hidden from the on-badge list: the badge
        # has already made its decision, and surfacing rejected
        # devices is just visual noise. The phone-side page still
        # gets the "denied" verdict from its next beacon poll so the
        # user there can hit refresh and try again with a fresh ID.
        sessions_all = hs.list_sessions() if hs else []
        sessions = [s for s in sessions_all if s.get("state") != "denied"]
        # Clamp the cursor in case a session disappeared between ticks.
        if self._trans_sel >= len(sessions):
            self._trans_sel = max(0, len(sessions) - 1)

        d.rect(ROW_PAD_X, list_y, SW - 2 * ROW_PAD_X, 1, theme.MUTED2, fill=True)
        list_y += 6
        if not sessions:
            d.text("no senders connected",
                   ROW_PAD_X + 2, list_y, theme.MUTED2)
            return

        # State -> dot colour. RGB tuples instead of theme constants
        # because we need a clean green, and the theme palette doesn't
        # ship one — primary is pink-red, teal is too cyan.
        dot_color = {
            "pending":  api.rgb(255, 209, 102),    # yellow
            "approved": api.rgb( 61, 220, 151),    # green
            "denied":   api.rgb(255,  93, 104),    # red — visible only
                                                   # in the brief window
                                                   # before the row is
                                                   # filtered out
        }
        DOT_SIZE   = 8
        DOT_RIGHT  = ROW_PAD_X + 2   # pad from the right edge
        BAR_PAD    = 8               # gap on either side of the bar
        ROW_INNER  = ROW_H - 4

        prog = hs.progress() if hs else None

        for i, s in enumerate(sessions[:5]):
            row_y = list_y + i * ROW_H
            sel   = (i == self._trans_sel)
            if sel:
                d.rect(4, row_y - 2, SW - 8, ROW_H - 1,
                       theme.DOCK_SEL, fill=True)
                d.rect(4, row_y - 2, SW - 8, 1, theme.SEL_BORDER, fill=True)
                d.rect(4, row_y + ROW_H - 4, SW - 8, 1,
                       theme.SEL_BORDER, fill=True)
            sid   = s.get("id", "------")
            state = s.get("state", "pending")

            # ID at scale=1 (smaller than before — the page got too
            # busy with the old scale=2 codes once we added a progress
            # bar and a status dot to the same row).
            d.text(sid, ROW_PAD_X, row_y + 6, theme.TEXT_BRIGHT, scale=1)

            # Status dot, right side, vertically centred in the row.
            dx = SW - DOT_RIGHT - DOT_SIZE
            dy = row_y + (ROW_INNER - DOT_SIZE) // 2 + 2
            d.rect(dx, dy, DOT_SIZE, DOT_SIZE,
                   dot_color.get(state, theme.MUTED), fill=True)

            # Mid-row progress bar — only when THIS session is the one
            # currently receiving. Spans the area between the ID text
            # and the status dot.
            if prog and prog.get("id") == sid:
                # Approximate where the SID text ends. Codes are 6
                # chars × 8 px at scale=1 = 48 px.
                bar_x = ROW_PAD_X + 6 * 8 + BAR_PAD
                bar_w = dx - BAR_PAD - bar_x
                if bar_w > 8:
                    total = max(1, int(prog.get("total", 0)))
                    done  = min(total, int(prog.get("received", 0)))
                    pct_w = int(bar_w * done / total)
                    bar_y = row_y + (ROW_INNER - 4) // 2 + 2
                    d.rect(bar_x, bar_y, bar_w, 4,
                           theme.MUTED2, fill=True)
                    d.rect(bar_x, bar_y, pct_w, 4,
                           theme.PRIMARY, fill=True)

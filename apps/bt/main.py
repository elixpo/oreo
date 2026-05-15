"""Bluetooth — phone-style detail screen.

Top section: this badge's own identity — GAP name + public MAC (split
across two lines so the full address is legible). Below: a Paired
section (slice 3 wires in the bond store) and a Nearby section that
fills as a BLE central-role scan runs.

Discovery is filtered: BLE advertisements whose appearance falls in the
audio category (speakers / earbuds / headsets / hearing aids) — or
whose service UUIDs include audio profiles — are dropped before the
list ever paints. Phones, computers, tablets, and generic devices pass
through; each gets a one-letter type tag.

Controls:
  UP/DOWN  walk rows
  A        toggle status (on the Status row) / pair (Nearby) /
           actions (Paired — wired in slice 3)
  B        start / stop scan
  HOME     back to Settings
"""

import time
import oreoOS
from oreoOS import api, theme, widgets


SW = api.SCREEN_W
SH = api.SCREEN_H

PAD_X        = 10
HEADER_Y     = widgets.HEADER_H + 4
IDENTITY_H   = 56     # Name + two-line MAC + state
SECTION_GAP  = 6
ROW_H        = 18
SCAN_DUR_MS  = 8000

_TYPE_LETTER = {
    "phone":    "P",
    "computer": "C",
    "tablet":   "T",
    "watch":    "W",
    "display":  "D",
    "other":    "·",
}


def _bars(rssi):
    if rssi is None:    return "----"
    if rssi >= -50:     return "####"
    if rssi >= -65:     return "###-"
    if rssi >= -75:     return "##--"
    if rssi >= -85:     return "#---"
    return "----"


class App(oreoOS.App):
    name         = "Bluetooth"
    author       = "Circuit-Overtime"
    SHOW_LOADING = True

    def on_enter(self, os_):
        super().on_enter(os_)
        self._os    = os_
        self._dirty = True

        # `_rows` is rebuilt on every refresh so selection lives by a
        # stable composite key (kind + index) rather than a row index
        # that shifts when scan results stream in.
        self._sel_key   = ("status", 0)
        self._poll_t    = 0.0
        self._poll_dt   = 0.5         # refresh list every 500 ms
        self._scan_t    = 0.0
        self._scan_left = 0           # ms remaining in current scan

        # Pair-flow overlay state: None (no overlay) or a dict tracking
        # which device the user picked + what the overlay is currently
        # showing ("confirm" | "running" | "done" | "failed").
        self._overlay = None

        try:
            from oreoWare import bt
            self._bt = bt
        except Exception:
            self._bt = None

        self._rows = self._build_rows()

    # ── data ────────────────────────────────────────────────────────────
    def _build_rows(self):
        """Flat list of row records:
              ("status",   active_bool)
              ("paired",   bond_entry_or_None)   # placeholder in slice 2
              ("nearby",   discovered_dict)
        Plus zero-arg headers so the renderer can paint section labels.
        """
        rows = [("status",  self._bt and self._bt.is_active())]

        # Paired section — bond store comes in slice 3. For now render
        # a clear empty state so the user sees the placeholder.
        rows.append(("header", "Paired (0 / 3)"))
        rows.append(("paired_empty", None))

        # Nearby section — fed by the live scan.
        nearby = []
        if self._bt:
            try:
                nearby = self._bt.scan_results()
            except Exception:
                nearby = []
        scan_label = "Nearby"
        if self._bt and self._bt.scan_is_active():
            scan_label += "  (scanning…)"
        elif nearby:
            scan_label += "  (%d)" % len(nearby)
        rows.append(("header", scan_label))
        if not nearby:
            rows.append(("nearby_empty", None))
        else:
            for entry in nearby[:8]:    # cap on-screen to keep paint cheap
                rows.append(("nearby", entry))

        return rows

    def _selectable(self, row):
        kind = row[0]
        return kind in ("status", "nearby")

    def _sel_index(self):
        """Index in self._rows that matches self._sel_key."""
        kind, ident = self._sel_key
        for i, r in enumerate(self._rows):
            if r[0] != kind:
                continue
            if kind == "status":
                return i
            if kind == "nearby":
                payload = r[1]
                if payload and payload.get("mac") == ident:
                    return i
        # Fall back: first selectable row
        for i, r in enumerate(self._rows):
            if self._selectable(r):
                return i
        return 0

    def _move_sel(self, step):
        cur = self._sel_index()
        n   = len(self._rows)
        i   = cur
        for _ in range(n):
            i = (i + step) % n
            if self._selectable(self._rows[i]):
                self._set_sel(self._rows[i])
                return

    def _set_sel(self, row):
        kind = row[0]
        if kind == "status":
            self._sel_key = ("status", 0)
        elif kind == "nearby":
            payload = row[1]
            self._sel_key = ("nearby", payload.get("mac"))

    # ── lifecycle ──────────────────────────────────────────────────────
    def update(self, dt):
        # Scan countdown — stop and rebuild rows when the time runs out
        # so the "(scanning…)" label disappears without user action.
        if self._scan_left > 0:
            self._scan_left = max(0, self._scan_left - int(dt * 1000))

        self._poll_t += dt
        if self._poll_t < self._poll_dt:
            return
        self._poll_t = 0.0
        fresh = self._build_rows()
        if fresh != self._rows:
            self._rows  = fresh
            self._dirty = True

    def on_button_press(self, btn):
        if btn == api.BTN_HOME:
            if self._bt and self._bt.scan_is_active():
                try:
                    self._bt.scan_stop()
                except Exception:
                    pass
            self._os.quit()
            return
        if btn == api.BTN_UP:
            self._move_sel(-1)
            self._dirty = True
        elif btn == api.BTN_DOWN:
            self._move_sel(+1)
            self._dirty = True
        elif btn == api.BTN_B:
            self._toggle_scan()
        elif btn == api.BTN_A:
            self._activate_selected()

    def _toggle_scan(self):
        if not self._bt:
            return
        if self._bt.scan_is_active():
            try:
                self._bt.scan_stop()
            except Exception:
                pass
            self._scan_left = 0
        else:
            try:
                self._bt.scan_start(SCAN_DUR_MS)
                self._scan_left = SCAN_DUR_MS
            except Exception:
                pass
        self._dirty = True

    def _activate_selected(self):
        idx = self._sel_index()
        row = self._rows[idx]
        kind, payload = row[0], row[1]
        if kind == "status":
            if not self._bt:
                return
            try:
                self._bt.set_active(not self._bt.is_active())
            except Exception:
                pass
            self._dirty = True
        elif kind == "nearby":
            # Pair flow lands in slice 3 — for now we just remember the
            # last requested target and surface it as a notification so
            # the user can see the round-trip wiring is in place.
            mac  = payload.get("mac", "?")
            name = payload.get("name", "?")
            try:
                from oreoOS import notifications
                notifications.push("bt", "Pair queued",
                                   "%s · %s" % (name[:14], mac[-8:]),
                                   target=None)
            except Exception:
                pass
            self._dirty = True

    # ── render ──────────────────────────────────────────────────────────
    def draw(self, d):
        if not self._dirty:
            return
        self._dirty = False
        d.clear(theme.BG)
        widgets.draw_header(d, "BLUETOOTH")
        widgets.draw_hint(d, "A=select  B=scan  HOME=back")

        self._draw_identity(d)

        list_top   = HEADER_Y + IDENTITY_H + SECTION_GAP
        list_h     = SH - list_top - widgets.HINT_H - 4
        max_rows   = max(1, list_h // ROW_H)

        sel_idx = self._sel_index()
        # Scroll the body so the selected row stays visible (selectable
        # rows can be deep into the list when many devices are nearby).
        body_rows = self._rows[1:]   # row[0] is "status" — drawn in identity
        if sel_idx == 0:
            # selection is on the Status row in the identity panel —
            # no body scrolling needed; reset.
            top = 0
        else:
            body_sel = sel_idx - 1
            top = max(0, body_sel - max_rows + 1)

        for vi in range(top, min(len(body_rows), top + max_rows)):
            row = body_rows[vi]
            y   = list_top + (vi - top) * ROW_H
            self._draw_row(d, y, row, sel_idx == vi + 1)

    def _draw_identity(self, d):
        x  = PAD_X
        y  = HEADER_Y
        name = self._bt.own_name() if self._bt else "Oreo"
        mac  = self._bt.own_mac()  if self._bt else "—"
        active = bool(self._bt and self._bt.is_active())

        d.text("This badge", x, y, theme.MUTED, scale=1)
        d.text(name, x, y + 12, theme.TEXT_BRIGHT, scale=2)

        # MAC: split AA:BB:CC:DD:EE:FF after the second colon for two
        # tidy 8-char lines if needed; on 320 px wide it fits one line
        # but the user wanted two-line so the field is unambiguous.
        if len(mac) > 8:
            half = (len(mac) // 3) * 3 + 2   # break on a colon if possible
            top_mac = mac[:half]
            bot_mac = mac[half + 1:] if mac[half:half + 1] == ":" else mac[half:]
        else:
            top_mac, bot_mac = mac, ""
        d.text(top_mac, x + 140, y + 12, theme.TEXT_DIM, scale=1)
        if bot_mac:
            d.text(bot_mac, x + 140, y + 24, theme.TEXT_DIM, scale=1)

        # Status indicator (matches the Settings BT toggle visually).
        sel_status = (self._sel_key[0] == "status")
        sy = y + 36
        if sel_status:
            d.rect(x - 2, sy - 2, SW - 2 * (x - 2), 18,
                   theme.DOCK_SEL, fill=True)
            d.rect(x - 2, sy - 2, SW - 2 * (x - 2), 1,
                   theme.SEL_BORDER, fill=True)
            d.rect(x - 2, sy + 15,  SW - 2 * (x - 2), 1,
                   theme.SEL_BORDER, fill=True)
        d.text("Status", x, sy + 4, theme.TEXT_BRIGHT, scale=1)
        label = "Discoverable" if active else "Off"
        color = theme.PRIMARY if active else theme.MUTED
        d.text(label, SW - PAD_X - len(label) * 8, sy + 4, color, scale=1)

    def _draw_row(self, d, y, row, selected):
        kind, payload = row[0], row[1]
        if kind == "header":
            d.text(str(payload), PAD_X, y + 2, theme.MUTED, scale=1)
            d.rect(PAD_X, y + 14, SW - 2 * PAD_X, 1,
                   theme.MUTED2, fill=True)
            return
        if kind == "paired_empty":
            d.text("no paired devices", PAD_X + 6, y + 2,
                   theme.MUTED2, scale=1)
            return
        if kind == "nearby_empty":
            msg = "scan to discover (B)"
            d.text(msg, PAD_X + 6, y + 2, theme.MUTED2, scale=1)
            return

        # ── nearby device row ─────────────────────────────────────────
        bg = theme.DOCK_SEL if selected else None
        if bg is not None:
            d.rect(PAD_X - 2, y, SW - 2 * (PAD_X - 2), ROW_H - 2,
                   bg, fill=True)
            d.rect(PAD_X - 2, y, SW - 2 * (PAD_X - 2), 1,
                   theme.SEL_BORDER, fill=True)
            d.rect(PAD_X - 2, y + ROW_H - 3, SW - 2 * (PAD_X - 2), 1,
                   theme.SEL_BORDER, fill=True)

        type_tag = _TYPE_LETTER.get(payload.get("type", "other"), "·")
        d.text(type_tag, PAD_X, y + 4, theme.PRIMARY, scale=1)

        name = (payload.get("name") or "(unknown)")[:18]
        d.text(name, PAD_X + 14, y + 4, theme.TEXT_BRIGHT, scale=1)

        rssi = payload.get("rssi")
        if rssi is not None:
            rstr = "%d %s" % (rssi, _bars(rssi))
            d.text(rstr, SW - PAD_X - len(rstr) * 8, y + 4,
                   theme.TEXT_DIM, scale=1)

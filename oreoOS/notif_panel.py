"""OS-level notification panel.

A single instance lives on the OS object (`os._notif_panel`). The run
loop in launcher.py intercepts BTN_C globally, calls `toggle()`, and
while `is_active()` is True routes all subsequent input through the
panel rather than the running app.

Layout (slides down from the top, full width):

  pink header strip  ── bell + "NOTIFICATIONS"
  quick-settings row ── three chunky pills:  WiFi  •  BT  •  Bright
  notif card list    ── one per push, newest first
  hint band          ── A=open  B=clear  C/HOME=close

Focus model:
  _focus == "quick"   LEFT/RIGHT cycles pills, A toggles/cycles
  _focus == "list"    UP/DOWN walks cards,  A opens target, B clears all
  UP at top of list → focus = "quick"
  DOWN from quick   → focus = "list" (if list is non-empty)

Quick settings are wired directly into oreoWare modules — `bt.set_active`,
`wifi.connect_from_config`/`wifi.disconnect`, `display.set_brightness`.
The panel never blocks for I/O; toggles fire and the panel re-renders
the new state next frame.
"""

import time
from oreoOS import api, theme, widgets


SW = api.SCREEN_W
SH = api.SCREEN_H

_ANIM_DUR = 0.18      # slide-in duration (seconds)

# Quick-settings pill geometry.
_PILL_W   = (SW - 4 * 12) // 3      # three pills with 12 px gaps
_PILL_H   = 38
_PILL_PAD = 12
_PILL_Y   = 26

_CARD_H   = 34
_CARD_GAP = 4
_LIST_Y   = _PILL_Y + _PILL_H + 10

# Brightness preset cycle — A on the Brightness pill steps through these.
_BRIGHT_STEPS = (25, 50, 75, 100)


def _draw_bell(d, x, y, color):
    """Tiny hand-bell beside the panel title."""
    d.rect(x + 4, y,     4, 1, color, fill=True)
    d.rect(x + 3, y + 1, 6, 1, color, fill=True)
    d.rect(x + 2, y + 2, 8, 1, color, fill=True)
    d.rect(x + 2, y + 3, 8, 1, color, fill=True)
    d.rect(x + 2, y + 4, 8, 1, color, fill=True)
    d.rect(x + 1, y + 5, 10, 1, color, fill=True)
    d.rect(x + 5, y + 7, 2, 2, color, fill=True)


def _draw_kind_glyph(d, x, y, kind, ink):
    """12×12 per-kind notification glyph (file / ota / other)."""
    if kind == "file":
        d.rect(x + 1, y,     8, 12, ink, fill=False)
        d.rect(x + 1, y,     8, 1,  ink, fill=True)
        d.rect(x + 1, y + 11, 8, 1, ink, fill=True)
        d.rect(x + 1, y, 1, 12, ink, fill=True)
        d.rect(x + 8, y, 1, 12, ink, fill=True)
        d.rect(x + 6, y,     3, 1, ink, fill=True)
        d.rect(x + 7, y + 1, 2, 1, ink, fill=True)
        d.rect(x + 8, y + 2, 1, 1, ink, fill=True)
        d.rect(x + 3, y + 4, 4, 1, ink, fill=True)
        d.rect(x + 3, y + 7, 4, 1, ink, fill=True)
    elif kind == "ota":
        d.rect(x + 4, y,     2, 7, ink, fill=True)
        d.rect(x + 2, y + 6, 6, 1, ink, fill=True)
        d.rect(x + 3, y + 7, 4, 1, ink, fill=True)
        d.rect(x + 4, y + 8, 2, 1, ink, fill=True)
        d.rect(x + 1, y + 10, 1, 2, ink, fill=True)
        d.rect(x + 8, y + 10, 1, 2, ink, fill=True)
        d.rect(x + 1, y + 11, 8, 1, ink, fill=True)
    else:
        d.rect(x + 4, y + 1, 2, 2, ink, fill=True)
        d.rect(x + 1, y + 4, 8, 2, ink, fill=True)
        d.rect(x + 4, y + 7, 2, 2, ink, fill=True)
        d.rect(x + 3, y + 9, 4, 1, ink, fill=True)


class NotifPanel:
    """Drawn over the running app when active. The run loop calls
    `tick(dt)` → `handle_button(b)` (returns True when consumed) →
    `draw(d)` from inside its frame loop."""

    def __init__(self, os_obj):
        self._os    = os_obj
        self.open   = False        # logical state (independent of anim)
        self._t     = 0.0          # animation progress 0..1
        self._dir   = 0            # +1 opening, -1 closing
        self._focus = "quick"      # "quick" | "list"
        self._quick_sel = 0
        self._list_sel  = 0

    # ── visibility ──────────────────────────────────────────────────────
    def is_active(self):
        """True while the panel is on-screen — used by the run loop to
        suppress app input + force a frame redraw every tick."""
        return self.open or self._t > 0

    def toggle(self):
        if self.open:
            self._dir = -1
        else:
            self.open = True
            self._dir = 1
            self._focus = "quick"
            self._quick_sel = 0
            self._list_sel  = 0
            self._mark_read()

    def close(self):
        if self.open:
            self._dir = -1

    def _mark_read(self):
        try:
            from oreoOS import notifications
            notifications.mark_read()
        except Exception:
            pass

    # ── per-frame ───────────────────────────────────────────────────────
    def tick(self, dt):
        if self._dir == 0:
            return
        self._t += self._dir * (dt / _ANIM_DUR)
        if self._t >= 1.0:
            self._t   = 1.0
            self._dir = 0
        elif self._t <= 0.0:
            self._t    = 0.0
            self._dir  = 0
            self.open  = False

    # ── input ───────────────────────────────────────────────────────────
    def handle_button(self, btn):
        """Returns True if the panel consumed the button; the run loop
        skips app dispatch in that case."""
        if not self.open:
            return False

        if btn == api.BTN_C or btn == api.BTN_HOME:
            self.close()
            return True

        items = self._items()
        if self._focus == "quick":
            return self._handle_quick(btn, items)
        return self._handle_list(btn, items)

    def _handle_quick(self, btn, items):
        if btn == api.BTN_LEFT:
            self._quick_sel = (self._quick_sel - 1) % 3
        elif btn == api.BTN_RIGHT:
            self._quick_sel = (self._quick_sel + 1) % 3
        elif btn == api.BTN_DOWN:
            if items:
                self._focus = "list"
                self._list_sel = 0
        elif btn == api.BTN_A:
            if self._quick_sel == 0:
                self._toggle_wifi()
            elif self._quick_sel == 1:
                self._toggle_bt()
            else:
                self._cycle_brightness()
        else:
            return True   # swallow everything else while panel is open
        return True

    def _handle_list(self, btn, items):
        n = len(items)
        if btn == api.BTN_UP:
            if self._list_sel == 0:
                self._focus = "quick"
            else:
                self._list_sel -= 1
        elif btn == api.BTN_DOWN:
            self._list_sel = min(n - 1, self._list_sel + 1)
        elif btn == api.BTN_A and n:
            target = items[self._list_sel].get("target")
            try:
                from oreoOS import notifications
                notifications.remove_at(self._list_sel)
            except Exception:
                pass
            self.open = False
            self._t   = 0.0
            self._dir = 0
            if target:
                self._os.launch(target)
        elif btn == api.BTN_B:
            try:
                from oreoOS import notifications
                notifications.clear()
            except Exception:
                pass
            self._list_sel = 0
            self._focus    = "quick"
        return True

    # ── quick-setting actions ───────────────────────────────────────────
    def _toggle_wifi(self):
        try:
            from oreoWare import wifi
            if wifi.is_connected():
                wifi.disconnect()
            else:
                wifi.connect_from_config()
        except Exception:
            pass

    def _toggle_bt(self):
        try:
            from oreoWare import bt
            bt.set_active(not bt.is_active())
        except Exception:
            pass

    def _cycle_brightness(self):
        cur = getattr(self._os, "_last_brightness", 100)
        try:
            i = _BRIGHT_STEPS.index(cur)
            nxt = _BRIGHT_STEPS[(i + 1) % len(_BRIGHT_STEPS)]
        except ValueError:
            nxt = _BRIGHT_STEPS[0]
        try:
            self._os.display.set_brightness(nxt)
            self._os._last_brightness = nxt
        except Exception:
            pass

    # ── data ────────────────────────────────────────────────────────────
    def _items(self):
        try:
            from oreoOS import notifications
            return notifications.items()
        except Exception:
            return []

    # ── render ──────────────────────────────────────────────────────────
    def draw(self, d):
        if self._t <= 0:
            return
        items   = self._items()
        full_h  = SH - widgets.HINT_H
        offset  = int(full_h * (1.0 - self._t))
        panel_y = -offset

        # Backdrop
        d.rect(0, panel_y, SW, full_h, theme.DOCK_BG, fill=True)
        d.rect(0, panel_y + full_h - 2, SW, 2, theme.PRIMARY, fill=True)

        # Header
        title    = "NOTIFICATIONS"
        title_w  = len(title) * 8
        title_x  = (SW - title_w) // 2
        d.rect(0, panel_y, SW, 22, theme.PRIMARY, fill=True)
        d.text(title, title_x, panel_y + 7, theme.BG, scale=1)
        _draw_bell(d, title_x - 16, panel_y + 4, theme.BG)

        self._draw_quick_row(d, panel_y)
        self._draw_list(d, panel_y, items, full_h)
        self._draw_hint(d, panel_y, full_h)

    def _draw_quick_row(self, d, panel_y):
        # Three pills: WiFi / BT / Brightness.
        labels = ("WiFi", "BT", "Bright")
        states = self._quick_states()
        for i in range(3):
            x = _PILL_PAD + i * (_PILL_W + _PILL_PAD)
            y = panel_y + _PILL_Y
            on = states[i]["on"]
            sel = (self._focus == "quick" and self._quick_sel == i)
            fill = theme.PRIMARY if on else theme.CARD
            d.rect(x, y, _PILL_W, _PILL_H, fill, fill=True)
            if sel:
                # Selection ring (one-pixel border in pink).
                d.rect(x,         y,             _PILL_W, 1,        theme.SEL_BORDER, fill=True)
                d.rect(x,         y + _PILL_H-1, _PILL_W, 1,        theme.SEL_BORDER, fill=True)
                d.rect(x,         y,             1,       _PILL_H,  theme.SEL_BORDER, fill=True)
                d.rect(x+_PILL_W-1, y,           1,       _PILL_H,  theme.SEL_BORDER, fill=True)
            txt_color = theme.BG if on else theme.TEXT_BRIGHT
            label = labels[i]
            d.text(label, x + (_PILL_W - len(label) * 8) // 2,
                   y + 6, txt_color, scale=1)
            sub = states[i]["sub"]
            d.text(sub, x + (_PILL_W - len(sub) * 8) // 2,
                   y + 22, txt_color, scale=1)

    def _quick_states(self):
        out = [
            {"on": False, "sub": "off"},
            {"on": False, "sub": "off"},
            {"on": False, "sub": "100"},
        ]
        try:
            from oreoWare import wifi
            connected = wifi.is_connected()
            out[0]["on"]  = bool(connected)
            out[0]["sub"] = "on" if connected else "off"
        except Exception:
            pass
        try:
            from oreoWare import bt
            active = bt.is_active()
            out[1]["on"]  = bool(active)
            out[1]["sub"] = "on" if active else "off"
        except Exception:
            pass
        bright = getattr(self._os, "_last_brightness", 100)
        out[2]["on"]  = bright >= 50
        out[2]["sub"] = "%d%%" % bright
        return out

    def _draw_list(self, d, panel_y, items, full_h):
        list_top = panel_y + _LIST_Y
        list_h   = full_h - _LIST_Y - 18    # leave room for hint

        if not items:
            msg = "no notifications"
            d.text(msg, (SW - len(msg) * 8) // 2,
                   list_top + list_h // 2 - 4, theme.MUTED, scale=1)
            return

        max_cards = max(1, list_h // (_CARD_H + _CARD_GAP))
        top = max(0, self._list_sel - max_cards + 1) if self._focus == "list" else 0
        for i in range(top, min(len(items), top + max_cards)):
            it = items[i]
            y  = list_top + (i - top) * (_CARD_H + _CARD_GAP)
            sel = (self._focus == "list" and i == self._list_sel)
            bg  = theme.DOCK_SEL if sel else theme.CARD
            d.rect(8, y, SW - 16, _CARD_H, bg, fill=True)
            if sel:
                # Simple 1-px outline; rounded version lives in launcher.
                d.rect(8,           y,            SW - 16, 1,       theme.SEL_BORDER, fill=True)
                d.rect(8,           y + _CARD_H-1, SW - 16, 1,      theme.SEL_BORDER, fill=True)
                d.rect(8,           y,            1,       _CARD_H, theme.SEL_BORDER, fill=True)
                d.rect(SW - 9,      y,            1,       _CARD_H, theme.SEL_BORDER, fill=True)
            kind = it.get("kind", "")
            ink  = (theme.GOLD if kind == "file"
                    else theme.PRIMARY if kind == "ota"
                    else theme.TEAL)
            _draw_kind_glyph(d, 14, y + 9, kind, ink)
            title = it.get("title", "")[:24]
            body  = it.get("body",  "")[:28]
            d.text(title, 34, y + 6, theme.TEXT_BRIGHT, scale=1)
            if body:
                d.text(body, 34, y + 18, theme.TEXT_DIM, scale=1)

    def _draw_hint(self, d, panel_y, full_h):
        if self._focus == "quick":
            hint = "L/R=switch  A=toggle  C=close"
        else:
            hint = "A=open  B=clear  C=close"
        d.text(hint, (SW - len(hint) * 8) // 2,
               panel_y + full_h - 14, theme.TEXT_DIM, scale=1)


def get(os_obj):
    """Singleton accessor — caches the panel on the OS object so the
    run-loop and the launcher both see the same instance."""
    panel = getattr(os_obj, "_notif_panel", None)
    if panel is None:
        panel = NotifPanel(os_obj)
        os_obj._notif_panel = panel
    return panel

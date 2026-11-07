"""OS-level notification panel.

A single instance lives on the OS object (`os._notif_panel`). The run
loop in launcher.py intercepts BTN_C globally, calls `toggle()`, and
while `is_active()` is True routes all subsequent input through the
panel rather than the running app. Apps that use C themselves set
`CAPTURES_C = True` (see `hotkey_allowed`): a single C then goes to the
app and a quick double-tap of C opens the panel, unless the app also sets
`C_DOUBLE_TAP = False` (C is too busy there, e.g. Doom's strafe).

Layout (slides down from the top, full screen):

  pink header strip  ── bell + "NOTIFICATIONS"
  quick tiles        ── WiFi • BT • Torch
                        Update • Settings
  brightness row     ── wide range slider with live %
  time row           ── clock + manual NTP sync
  notif card list    ── one per push, newest first, eased scrolling
  hint band          ── context hint for the focused row

Focus model:
  _focus == "quick"   LEFT/RIGHT walks the five tiles, UP/DOWN moves
                      between the tile rows, A activates, DOWN from the
                      second row drops to "bright"
  _focus == "bright"  LEFT/RIGHT adjusts ±10 %, UP back to the tiles,
                      DOWN drops to "time"
  _focus == "time"    A syncs, DOWN drops to "list" (if non-empty)
  _focus == "list"    UP/DOWN walks cards, A opens target, B clears all,
                      UP at top → "time"

Torch: the Torch tile turns the whole screen white at full backlight.
HOME (or C) restores the previous brightness and returns to the app.

Quick settings are wired directly into oreoWare modules — `bt.set_active`,
`wifi.connect_from_config`/`wifi.disconnect`, `display.set_brightness`.
The Settings and Update tiles close the panel and launch their app. The
panel never blocks for I/O except the WiFi association wait, which can
be cancelled with any key.

Rendering: while sliding, the panel paints every frame. Once fully open
it covers the whole screen, the run loop stops painting the app under
it, and the panel repaints only when its content changes (input, a toast,
a scroll step, or the twice-a-second status refresh).
"""

import time
from oreoOS import api, theme, widgets


SW = api.SCREEN_W
SH = api.SCREEN_H

_ANIM_DUR = 0.18      # slide-in duration (seconds)
_REFRESH_MS = 500     # live status (clock, BT pulse) repaint cadence

# Quick tiles: three on the first row, two wider ones on the second.
_PILL_PAD = 12
_PILL_H   = 30
_PILL_GAP = 4
_PILL_Y   = 26
_PILL_W   = (SW - 4 * _PILL_PAD) // 3
_PILL_W2  = (SW - 3 * _PILL_PAD) // 2
_PILL_Y2  = _PILL_Y + _PILL_H + _PILL_GAP

Q_WIFI, Q_BT, Q_TORCH, Q_UPDATE, Q_SETTINGS = 0, 1, 2, 3, 4
_N_QUICK  = 5

_BRIGHT_Y    = _PILL_Y2 + _PILL_H + 6
_BRIGHT_H    = 20
_BRIGHT_PAD  = 12
_BRIGHT_STEP = 10               # ± per LEFT/RIGHT tap on the slider
_BRIGHT_MIN  = 10               # don't let users blank the screen accidentally
_BRIGHT_MAX  = 100

_TIME_Y      = _BRIGHT_Y + _BRIGHT_H + 4
_TIME_H      = 18
_TIME_PAD    = 12

_CARD_H   = 34
_CARD_GAP = 4
_LIST_Y   = _TIME_Y + _TIME_H + 6
_HINT_H   = 16
_LIST_H   = SH - _LIST_Y - _HINT_H - 2


def hotkey_allowed(app):
    """True when C should open the panel over `app`.

    Apps that need C as a control set `CAPTURES_C = True` on the class, or
    on the instance at runtime (e.g. only while a game is being played).
    """
    try:
        return not getattr(app, "CAPTURES_C", False)
    except Exception:
        return True


DOUBLE_TAP_MS = 350


def double_tap_opens(app):
    """True when a double-tap of C should open the panel over an app that
    captures C. Apps opt out with `C_DOUBLE_TAP = False`."""
    try:
        return bool(getattr(app, "C_DOUBLE_TAP", True))
    except Exception:
        return True


def quick_nav(sel, btn):
    """Next quick-tile index for a d-pad press, or None to leave the tile
    rows downward (to the brightness slider). Row 1: 0 1 2, row 2: 3 4."""
    if btn == api.BTN_LEFT:
        return (sel - 1) % _N_QUICK
    if btn == api.BTN_RIGHT:
        return (sel + 1) % _N_QUICK
    if btn == api.BTN_DOWN:
        if sel < 3:
            return Q_UPDATE if sel < 2 else Q_SETTINGS
        return None
    if btn == api.BTN_UP:
        if sel >= 3:
            return Q_WIFI if sel == Q_UPDATE else Q_TORCH
        return sel
    return sel


def _outline(d, x, y, w, h, color):
    d.rect(x,         y,         w, 1, color, fill=True)
    d.rect(x,         y + h - 1, w, 1, color, fill=True)
    d.rect(x,         y,         1, h, color, fill=True)
    d.rect(x + w - 1, y,         1, h, color, fill=True)


def _draw_torch(d, x, y, color):
    """12×12 torch glyph: light rays on the left, lens, head, handle."""
    d.rect(x,     y + 1,  1, 2, color, fill=True)     # rays
    d.rect(x,     y + 5,  1, 2, color, fill=True)
    d.rect(x,     y + 9,  1, 2, color, fill=True)
    d.rect(x + 2, y + 2,  1, 8, color, fill=True)     # lens rim
    d.rect(x + 3, y + 3,  4, 6, color, fill=True)     # head
    d.rect(x + 7, y + 4,  5, 4, color, fill=True)     # handle


def _draw_update(d, x, y, color):
    """12×12 download-into-tray glyph for the Update tile."""
    _draw_kind_glyph(d, x, y, "ota", color)


def _draw_bell(d, x, y, color):
    """Tiny hand-bell beside the panel title."""
    d.rect(x + 4, y,     4, 1, color, fill=True)
    d.rect(x + 3, y + 1, 6, 1, color, fill=True)
    d.rect(x + 2, y + 2, 8, 1, color, fill=True)
    d.rect(x + 2, y + 3, 8, 1, color, fill=True)
    d.rect(x + 2, y + 4, 8, 1, color, fill=True)
    d.rect(x + 1, y + 5, 10, 1, color, fill=True)
    d.rect(x + 5, y + 7, 2, 2, color, fill=True)


def _draw_gear(d, x, y, color):
    """12×12 gear glyph for the Settings quick-action pill."""
    # outer teeth — four nubs at N/S/E/W
    d.rect(x + 5, y,      2, 2, color, fill=True)
    d.rect(x + 5, y + 10, 2, 2, color, fill=True)
    d.rect(x,     y + 5,  2, 2, color, fill=True)
    d.rect(x + 10, y + 5, 2, 2, color, fill=True)
    # body
    d.rect(x + 3, y + 2, 6, 8, color, fill=True)
    d.rect(x + 2, y + 3, 8, 6, color, fill=True)
    # hub punch-out (background)
    d.rect(x + 5, y + 5, 2, 2, theme.CARD, fill=True)


def _draw_clock(d, x, y, color):
    """12×12 clock-face glyph for the time-sync row."""
    d.rect(x + 2, y,     8, 1, color, fill=True)
    d.rect(x + 2, y + 11, 8, 1, color, fill=True)
    d.rect(x,     y + 2, 1, 8, color, fill=True)
    d.rect(x + 11, y + 2, 1, 8, color, fill=True)
    d.rect(x + 1, y + 1, 1, 1, color, fill=True)
    d.rect(x + 10, y + 1, 1, 1, color, fill=True)
    d.rect(x + 1, y + 10, 1, 1, color, fill=True)
    d.rect(x + 10, y + 10, 1, 1, color, fill=True)
    # hands (12 + 3 o'clock)
    d.rect(x + 5, y + 3, 2, 4, color, fill=True)
    d.rect(x + 6, y + 5, 4, 2, color, fill=True)


def _draw_sun(d, x, y, color):
    """12×12 sun glyph for the brightness slider label."""
    d.rect(x + 5, y,      2, 2, color, fill=True)
    d.rect(x + 5, y + 10, 2, 2, color, fill=True)
    d.rect(x,     y + 5,  2, 2, color, fill=True)
    d.rect(x + 10, y + 5, 2, 2, color, fill=True)
    d.rect(x + 1, y + 1, 2, 2, color, fill=True)
    d.rect(x + 9, y + 1, 2, 2, color, fill=True)
    d.rect(x + 1, y + 9, 2, 2, color, fill=True)
    d.rect(x + 9, y + 9, 2, 2, color, fill=True)
    d.rect(x + 4, y + 3, 4, 6, color, fill=True)
    d.rect(x + 3, y + 4, 6, 4, color, fill=True)


def _draw_kind_glyph(d, x, y, kind, ink):
    """12×12 per-kind notification glyph (file / ota / reject / other)."""
    if kind == "reject":
        # Crossed-circle "no" symbol — diagonal slash inside a hollow O.
        # Used for BT-rejected transfers (wrong file type, oversize image)
        # so the user can tell at a glance the notif is bad-news, not
        # a fresh delivery.
        d.rect(x + 3, y,     6, 1, ink, fill=True)
        d.rect(x + 3, y + 11, 6, 1, ink, fill=True)
        d.rect(x,     y + 3, 1, 6, ink, fill=True)
        d.rect(x + 11, y + 3, 1, 6, ink, fill=True)
        d.rect(x + 1, y + 1, 2, 2, ink, fill=True)
        d.rect(x + 9, y + 1, 2, 2, ink, fill=True)
        d.rect(x + 1, y + 9, 2, 2, ink, fill=True)
        d.rect(x + 9, y + 9, 2, 2, ink, fill=True)
        # diagonal slash
        for i in range(8):
            d.rect(x + 2 + i, y + 9 - i, 1, 1, ink, fill=True)
        return
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
        self._focus = "quick"      # "quick" | "bright" | "time" | "list"
        self._quick_sel = 0
        self._list_sel  = 0
        self._list_top  = 0
        self._scroll    = widgets.Scroller(0, dur=0.16)
        self._dirty     = True
        self._refresh_ms = 0
        self._uncovered  = False   # closed since the run loop last asked
        # Torch: None when off, else the brightness to restore.
        self._torch_prev = None
        # Transient toast shown in the time-sync row while a manual sync
        # is in flight, then for ~1.5 s after it finishes. None = display
        # the live clock instead. (start_ms, text, color_key)
        self._time_toast = None
        self._toast_ms   = 1500

    # ── visibility ──────────────────────────────────────────────────────
    def is_active(self):
        """True while the panel is on-screen — used by the run loop to
        suppress app input + force a frame redraw every tick."""
        return self.open or self._t > 0

    def is_closing(self):
        return self._dir < 0

    def covers_screen(self):
        """Fully open (or torch on): nothing of the app is visible, so the
        run loop can skip painting it."""
        return self.open and self._t >= 1.0 and self._dir == 0

    def keeps_awake(self):
        """The torch must not be cut off by the idle sleep timer."""
        return self._torch_prev is not None

    def torch_on(self):
        return self._torch_prev is not None

    def toggle(self):
        if self._torch_prev is not None:
            self._torch_off()
            return
        if self.open:
            self._dir = -1
        else:
            self.open = True
            self._dir = 1
            self._focus = "quick"
            self._quick_sel = 0
            self._list_sel  = 0
            self._list_top  = 0
            self._scroll.set_target(0, snap=True)
            self._dirty = True
            self._mark_read()

    def close(self):
        if self._torch_prev is not None:
            self._torch_off()
            return
        if self.open:
            self._dir = -1

    def _close_now(self):
        """Drop the panel without the slide (before launching an app or
        when leaving the torch). The run loop sees is_active() go False
        and asks the app for a full repaint."""
        self.open = False
        self._t   = 0.0
        self._dir = 0
        self._uncovered = True

    def invalidate(self):
        """Something painted over the open panel: repaint next frame."""
        self._dirty = True

    def consume_closed(self):
        """True once after the panel left the screen (slide finished,
        torch off, or an instant close) so the run loop can ask the app
        underneath for a full repaint."""
        if self._uncovered:
            self._uncovered = False
            return True
        return False

    def _mark_read(self):
        try:
            from oreoOS import notifications
            notifications.mark_read()
        except Exception:
            pass

    # ── per-frame ───────────────────────────────────────────────────────
    def tick(self, dt):
        if self._scroll.step(dt):
            self._dirty = True
        if self._dir == 0:
            if self.open and self._torch_prev is None:
                now = time.ticks_ms()
                if time.ticks_diff(now, self._refresh_ms) >= _REFRESH_MS:
                    self._refresh_ms = now
                    self._dirty = True
            return
        self._dirty = True
        self._t += self._dir * (dt / _ANIM_DUR)
        if self._t >= 1.0:
            self._t   = 1.0
            self._dir = 0
        elif self._t <= 0.0:
            self._t    = 0.0
            self._dir  = 0
            self.open  = False
            self._uncovered = True

    # ── input ───────────────────────────────────────────────────────────
    def handle_button(self, btn):
        """Returns True if the panel consumed the button; the run loop
        skips app dispatch in that case."""
        if not self.open:
            return False
        self._dirty = True

        if self._torch_prev is not None:
            # Torch eats every key; HOME (or C) restores and returns.
            if btn == api.BTN_HOME or btn == api.BTN_C:
                self._torch_off()
            return True

        if btn == api.BTN_C or btn == api.BTN_HOME:
            self.close()
            return True

        items = self._items()
        if self._focus == "quick":
            return self._handle_quick(btn, items)
        if self._focus == "bright":
            return self._handle_bright(btn, items)
        if self._focus == "time":
            return self._handle_time(btn, items)
        return self._handle_list(btn, items)

    def _handle_quick(self, btn, items):
        if btn == api.BTN_A:
            sel = self._quick_sel
            if sel == Q_WIFI:
                self._toggle_wifi()
            elif sel == Q_BT:
                self._toggle_bt()
            elif sel == Q_TORCH:
                self._torch_start()
            elif sel == Q_UPDATE:
                self._open_app("updates")
            else:
                self._open_app("settings")
            return True
        nxt = quick_nav(self._quick_sel, btn)
        if nxt is None:
            self._focus = "bright"
        else:
            self._quick_sel = nxt
        return True

    def _handle_bright(self, btn, items):
        if btn == api.BTN_LEFT:
            self._adjust_brightness(-_BRIGHT_STEP)
        elif btn == api.BTN_RIGHT:
            self._adjust_brightness(+_BRIGHT_STEP)
        elif btn == api.BTN_UP:
            self._focus = "quick"
            if self._quick_sel < Q_UPDATE:
                self._quick_sel = Q_UPDATE
        elif btn == api.BTN_DOWN:
            self._focus = "time"
        return True

    def _handle_time(self, btn, items):
        if btn == api.BTN_A:
            self._sync_time()
        elif btn == api.BTN_UP:
            self._focus = "bright"
        elif btn == api.BTN_DOWN:
            if items:
                self._focus = "list"
                self._list_sel = 0
                self._follow_list()
        return True

    def _handle_list(self, btn, items):
        n = len(items)
        if btn == api.BTN_UP:
            if self._list_sel == 0:
                self._focus = "time"
            else:
                self._list_sel -= 1
        elif btn == api.BTN_DOWN:
            self._list_sel = max(0, min(n - 1, self._list_sel + 1))
        elif btn == api.BTN_A and n:
            target = items[self._list_sel].get("target")
            try:
                from oreoOS import notifications
                notifications.remove_at(self._list_sel)
            except Exception:
                pass
            self._close_now()
            if target:
                self._os.launch(target)
            return True
        elif btn == api.BTN_B:
            try:
                from oreoOS import notifications
                notifications.clear()
            except Exception:
                pass
            self._list_sel = 0
            self._focus    = "quick"
        self._follow_list()
        return True

    def _follow_list(self):
        """Keep the selected card inside the list window; the Scroller
        glides the cards to the new top."""
        per = _CARD_H + _CARD_GAP
        vis = max(1, (_LIST_H + _CARD_GAP) // per)
        if self._list_sel < self._list_top:
            self._list_top = self._list_sel
        elif self._list_sel >= self._list_top + vis:
            self._list_top = self._list_sel - vis + 1
        if self._focus != "list":
            self._list_top = 0
        self._scroll.set_target(self._list_top * per)

    # ── quick-setting actions ───────────────────────────────────────────
    def _toggle_wifi(self):
        """Drive the WiFi RADIO state, not the association state.

        The old behaviour was: "if connected → disconnect; else →
        connect_from_config". That made the chip look like a no-op
        any time auto-association failed: tap → radio up → can't
        associate → is_connected() stays False → chip still reads
        "OFF" → next tap thinks it's currently off and tries the same
        thing again. Now the chip tracks radio_on(): one tap powers
        the MAC up (and *tries* to associate), another tap powers it
        fully down. Association status surfaces as the sub-label.
        """
        try:
            from oreoWare import wifi
            on_now = False
            try:
                on_now = bool(wifi.is_radio_on())
            except Exception:
                # Old build without is_radio_on — fall back to the
                # association check (no worse than before).
                on_now = bool(wifi.is_connected())
            if on_now:
                wifi.radio_off() if hasattr(wifi, "radio_off") else wifi.disconnect()
            else:
                if hasattr(wifi, "radio_on"):
                    wifi.radio_on()
                # Commit the visible ON state before association blocks in
                # connect_from_config(). This makes the single button press
                # acknowledge immediately even when no saved AP is reachable.
                try:
                    self._dirty = True
                    self.draw(self._os.display)
                    self._os.display.present()
                except Exception:
                    pass
                # Non-blocking: the run loop ticks wifi.auto_tick() and
                # starts the file-transfer server once the link is up.
                # Older wifi.py without auto_begin falls back to the
                # blocking connect, pumping input so a press cancels it.
                if hasattr(wifi, "auto_begin"):
                    wifi.auto_begin()
                else:
                    try:
                        wifi.connect_from_config(pump_cb=self._wifi_cancel_pump)
                    except TypeError:
                        wifi.connect_from_config()
        except Exception:
            pass
        self._dirty = True

    def _wifi_cancel_pump(self):
        """Called from inside wifi.connect_from_config's wait loop.
        Returns True on any keypress so the user can cancel the
        in-flight 'searching…' attempt without waiting for the
        per-network timeout."""
        try:
            self._os.buttons.update()
            for b_ in api.BUTTONS:
                if self._os.buttons.just_pressed(b_):
                    return True
        except Exception:
            pass
        return False

    def _toggle_bt(self):
        try:
            from oreoWare import bt
            bt.set_active(not bt.is_active())
        except Exception:
            pass

    def _adjust_brightness(self, delta):
        cur = getattr(self._os, "_last_brightness", 100)
        nxt = max(_BRIGHT_MIN, min(_BRIGHT_MAX, cur + delta))
        if nxt == cur:
            return
        try:
            self._os.display.set_brightness(nxt)
            self._os._last_brightness = nxt
            from oreoWare.display import save_brightness
            save_brightness(nxt)
        except Exception:
            pass

    def _torch_start(self):
        """Full-white screen at full backlight. The user's brightness is
        kept in _last_brightness (untouched) and restored on exit."""
        prev = getattr(self._os, "_last_brightness", 100)
        self._torch_prev = prev
        self._dirty = True
        try:
            self._os.display.set_brightness(100)
        except Exception:
            pass

    def _torch_off(self):
        prev = self._torch_prev
        self._torch_prev = None
        if prev is None:
            return
        try:
            self._os.display.set_brightness(prev)
        except Exception:
            pass
        self._close_now()

    def _sync_time(self):
        # ~2 s blocking call. We post a "syncing…" toast first so the
        # next frame can paint it before we vanish into the network
        # round-trip; the result toast appears on the frame after.
        self._time_toast = (time.ticks_ms(), "syncing…", "muted")
        try:
            from oreoOS import timeutil
            ok, msg = timeutil.sync_from_ntp()
        except Exception:
            ok, msg = False, "failed"
        key = "ok" if ok else "err"
        self._time_toast = (time.ticks_ms(), msg, key)

    def _open_app(self, name):
        # Close the panel synchronously and hand control to the app —
        # a one-tap shortcut from inside whatever app is running.
        self._close_now()
        try:
            self._os.launch(name)
        except Exception:
            pass

    # ── data ────────────────────────────────────────────────────────────
    def _items(self):
        try:
            from oreoOS import notifications
            return notifications.items()
        except Exception:
            return []

    def _update_state(self):
        """(on, sub-label) for the Update tile, from the flags the OTA
        background check leaves in the OS settings."""
        try:
            status = self._os.settings_get("ota_status", "")
            if status in ("needs-confirm", "ready"):
                ver = self._os.settings_get("ota_pending_version", "") or "new"
                return True, str(ver)[:12]
        except Exception:
            pass
        return False, "check"

    # ── render ──────────────────────────────────────────────────────────
    def draw(self, d):
        if self._t <= 0:
            return
        if not self._dirty:
            return
        self._dirty = False
        if self._torch_prev is not None:
            d.rect(0, 0, SW, SH, api.WHITE, fill=True)
            return
        items   = self._items()
        full_h  = SH
        offset  = int(full_h * (1.0 - self._t))
        panel_y = -offset

        # Backdrop
        d.rect(0, panel_y, SW, full_h, theme.DOCK_BG, fill=True)

        # The list scrolls under the rows above it, so it is painted first
        # and the fixed rows clip it by drawing over the top edge.
        self._draw_list(d, panel_y, items)

        d.rect(0, panel_y + 22, SW, _LIST_Y - 22, theme.DOCK_BG, fill=True)
        self._draw_quick_rows(d, panel_y)
        self._draw_brightness(d, panel_y)
        self._draw_time_row(d, panel_y)

        # Header
        title    = "NOTIFICATIONS"
        title_w  = len(title) * 8
        title_x  = (SW - title_w) // 2
        d.rect(0, panel_y, SW, 22, theme.PRIMARY, fill=True)
        d.text(title, title_x, panel_y + 7, theme.BG, scale=1)
        _draw_bell(d, title_x - 16, panel_y + 4, theme.BG)

        self._draw_hint(d, panel_y, full_h)

    def _pill(self, d, x, y, w, on, sel, label, sub, glyph):
        fill = theme.PRIMARY if on else theme.CARD
        d.rect(x, y, w, _PILL_H, fill, fill=True)
        if sel:
            _outline(d, x, y, w, _PILL_H, theme.SEL_BORDER)
            if on:
                _outline(d, x + 1, y + 1, w - 2, _PILL_H - 2, theme.BG)
        ink = theme.BG if on else theme.TEXT_BRIGHT
        if glyph is not None:
            glyph(d, x + 6, y + (_PILL_H - 12) // 2, theme.BG if on else theme.PRIMARY)
            tx0 = x + 22
            tw  = w - 26
        else:
            tx0 = x
            tw  = w
        lbl = label[:max(1, tw // 8)]
        d.text(lbl, tx0 + (tw - len(lbl) * 8) // 2, y + 5, ink, scale=1)
        if sub:
            sub = sub[:max(1, tw // 8)]
            d.text(sub, tx0 + (tw - len(sub) * 8) // 2, y + 17, ink, scale=1)

    def _draw_quick_rows(self, d, panel_y):
        states = self._quick_states()
        q = self._focus == "quick"
        s = self._quick_sel
        y1 = panel_y + _PILL_Y
        y2 = panel_y + _PILL_Y2
        x  = _PILL_PAD
        self._pill(d, x, y1, _PILL_W, states[0][0], q and s == Q_WIFI,
                   "WiFi", states[0][1], None)
        x += _PILL_W + _PILL_PAD
        self._pill(d, x, y1, _PILL_W, states[1][0], q and s == Q_BT,
                   "BT", states[1][1], None)
        x += _PILL_W + _PILL_PAD
        self._pill(d, x, y1, _PILL_W, False, q and s == Q_TORCH,
                   "Torch", "A = on", _draw_torch)
        up_on, up_sub = self._update_state()
        x = _PILL_PAD
        self._pill(d, x, y2, _PILL_W2, up_on, q and s == Q_UPDATE,
                   "Update", up_sub, _draw_update)
        x += _PILL_W2 + _PILL_PAD
        self._pill(d, x, y2, _PILL_W2, False, q and s == Q_SETTINGS,
                   "Settings", "open", _draw_gear)

    def _quick_states(self):
        wifi_s = (False, "off")
        bt_s   = (False, "off")
        try:
            from oreoWare import wifi
            connected = False
            radio_on = False
            try:
                connected = bool(wifi.is_connected())
            except Exception:
                pass
            try:
                radio_on = bool(wifi.is_radio_on())
            except Exception:
                radio_on = connected
            if connected:
                cur = ""
                try: cur = wifi.ssid() or ""
                except Exception: pass
                wifi_s = (radio_on, cur[:10] if cur else "on")
            elif radio_on:
                wifi_s = (True, "no link")
        except Exception:
            pass
        try:
            from oreoWare import bt
            active = bool(bt.is_active())
            # Blink "transferring" while a peer is connected. The panel
            # refreshes twice a second while open, so alternating the
            # sublabel is enough to make the BT chip visibly pulse.
            try:
                busy = bt.is_busy()
            except Exception:
                busy = False
            if busy:
                phase = (time.ticks_ms() // 500) & 1
                bt_s = (active, "transfer…" if phase else "transferring")
            else:
                bt_s = (active, "on" if active else "off")
        except Exception:
            pass
        return (wifi_s, bt_s)

    def _draw_brightness(self, d, panel_y):
        """Wide horizontal range slider showing current backlight level."""
        x = _BRIGHT_PAD
        y = panel_y + _BRIGHT_Y
        w = SW - 2 * _BRIGHT_PAD
        h = _BRIGHT_H

        sel = (self._focus == "bright")
        d.rect(x, y, w, h, theme.CARD, fill=True)
        if sel:
            _outline(d, x, y, w, h, theme.SEL_BORDER)

        _draw_sun(d, x + 6, y + (h - 12) // 2, theme.PRIMARY)

        bright = getattr(self._os, "_last_brightness", 100)
        bright = max(_BRIGHT_MIN, min(_BRIGHT_MAX, int(bright)))

        # Slider track + fill — track is the full inner width, fill
        # proportional to the brightness value.
        track_x = x + 24
        track_w = w - 24 - 44
        track_y = y + (h - 4) // 2
        d.rect(track_x, track_y, track_w, 4, theme.MUTED2, fill=True)

        fill_w = max(2, (track_w * bright) // _BRIGHT_MAX)
        d.rect(track_x, track_y, fill_w, 4, theme.PRIMARY, fill=True)

        # Handle dot — small square at the fill end so it's obvious which
        # direction LEFT/RIGHT moves the value.
        handle_x = track_x + fill_w - 3
        d.rect(handle_x, track_y - 3, 6, 10, theme.PRIMARY, fill=True)

        val = "%d%%" % bright
        d.text(val, x + w - len(val) * 8 - 8,
               y + (h - 8) // 2, theme.TEXT_BRIGHT, scale=1)

    def _draw_list(self, d, panel_y, items):
        list_top = panel_y + _LIST_Y
        list_h   = _LIST_H

        if not items:
            msg = "no notifications"
            d.text(msg, (SW - len(msg) * 8) // 2,
                   list_top + list_h // 2 - 4, theme.MUTED, scale=1)
            return

        per  = _CARD_H + _CARD_GAP
        off  = self._scroll.value
        first = max(0, off // per)
        last  = min(len(items), (off + list_h) // per + 1)
        for i in range(first, last):
            it = items[i]
            y  = list_top + i * per - off
            sel = (self._focus == "list" and i == self._list_sel)
            bg  = theme.DOCK_SEL if sel else theme.CARD
            d.rect(8, y, SW - 16, _CARD_H, bg, fill=True)
            if sel:
                _outline(d, 8, y, SW - 16, _CARD_H, theme.SEL_BORDER)
            kind = it.get("kind", "")
            ink  = (theme.GOLD if kind == "file"
                    else theme.PRIMARY if kind == "ota"
                    else theme.PRIMARY if kind == "reject"
                    else theme.TEAL)
            _draw_kind_glyph(d, 14, y + 9, kind, ink)
            title = it.get("title", "")[:24]
            body  = it.get("body",  "")[:28]
            d.text(title, 34, y + 6, theme.TEXT_BRIGHT, scale=1)
            if body:
                d.text(body, 34, y + 18, theme.TEXT_DIM, scale=1)

    def _draw_time_row(self, d, panel_y):
        """Time-sync row beneath the brightness slider. Shows the current
        wall-clock time and (when focused) a "Sync now" affordance. A
        recent sync result temporarily replaces the clock with a toast."""
        x = _TIME_PAD
        y = panel_y + _TIME_Y
        w = SW - 2 * _TIME_PAD
        h = _TIME_H

        sel = (self._focus == "time")
        d.rect(x, y, w, h, theme.CARD, fill=True)
        if sel:
            _outline(d, x, y, w, h, theme.SEL_BORDER)

        _draw_clock(d, x + 6, y + (h - 12) // 2, theme.PRIMARY)

        toast = self._time_toast
        if toast is not None:
            start_ms, msg, key = toast
            if time.ticks_diff(time.ticks_ms(), start_ms) > self._toast_ms \
                    and msg != "syncing…":
                self._time_toast = None
                toast = None

        if toast is not None:
            _, msg, key = toast
            color = (theme.PRIMARY if key == "ok"
                     else theme.GOLD if key == "err"
                     else theme.MUTED)
            d.text(msg[:28], x + 24, y + (h - 8) // 2, color, scale=1)
        else:
            # Live clock readout — HH:MM in the local timezone, plus a
            # right-aligned action hint when focused so the user knows A
            # triggers a manual sync.
            try:
                from oreoOS import timeutil as _tu
                hour, minute, _s, _wd, _d, _m, _y = _tu.now()
                clock = "%02d:%02d" % (hour, minute)
            except Exception:
                clock = "--:--"
            d.text(clock, x + 24, y + (h - 8) // 2,
                   theme.TEXT_BRIGHT, scale=1)
            action = "A=sync ↻" if sel else "Sync time"
            d.text(action, x + w - len(action) * 8 - 8,
                   y + (h - 8) // 2,
                   theme.PRIMARY if sel else theme.MUTED, scale=1)

    def _draw_hint(self, d, panel_y, full_h):
        if self._focus == "quick":
            hint = "D-pad=move  A=select  C=close"
        elif self._focus == "bright":
            hint = "L/R=adjust  UP=back  C=close"
        elif self._focus == "time":
            hint = "A=sync  UP/DOWN=move  C=close"
        else:
            hint = "A=open  B=clear  C=close"
        hy = panel_y + full_h - _HINT_H
        d.rect(0, hy, SW, _HINT_H, theme.DOCK_BG, fill=True)
        d.rect(0, hy, SW, 1, theme.PRIMARY, fill=True)
        d.text(hint, (SW - len(hint) * 8) // 2, hy + 5, theme.TEXT_DIM, scale=1)


def get(os_obj):
    """Singleton accessor — caches the panel on the OS object so the
    run-loop and the launcher both see the same instance."""
    panel = getattr(os_obj, "_notif_panel", None)
    if panel is None:
        panel = NotifPanel(os_obj)
        os_obj._notif_panel = panel
    return panel

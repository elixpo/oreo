"""Gamepad — button-press tester with a stylised gamepad layout.

A faux-controller is drawn on-screen with a D-pad on the left, three action
buttons (A/B/C) on the right, and the HOME button as a thin centre pill.
Each on-screen button:

  • lights up PRIMARY while held (live `is_pressed`)
  • flashes GOLD for ~150 ms on every `just_pressed` edge
  • shows a small press-count number underneath

HOME button:
  • Single tap: registered as a button event (does NOT exit).
  • Double tap within 400 ms: returns to the apps drawer.

This makes it useful as both a wiring sanity-check AND a way to confirm the
HOME-double-tap behaviour without ever leaving the test screen.
"""

import time
import lix
from lix import api
from lix_os import theme, widgets

SW = api.SCREEN_W
SH = api.SCREEN_H

DOUBLE_TAP_MS = 400
FLASH_MS      = 150


class App(lix.App):
    name = "Gamepad"

    def on_enter(self, os):
        self._os         = os
        self._held       = {b: False for b, _ in self._labels()}
        self._counts     = {b: 0     for b, _ in self._labels()}
        self._flash      = {b: 0     for b, _ in self._labels()}   # 0 or absolute ticks_ms expiry
        self._event      = "tap any button"
        self._home_t     = -10000                                  # last HOME tick
        self._home_hint  = ""
        self._dirty      = True

    @staticmethod
    def _labels():
        return [
            (api.BTN_HOME,  "HOME"),
            (api.BTN_A,     "A"),
            (api.BTN_B,     "B"),
            (api.BTN_C,     "C"),
            (api.BTN_UP,    "UP"),
            (api.BTN_DOWN,  "DN"),
            (api.BTN_LEFT,  "L"),
            (api.BTN_RIGHT, "R"),
        ]

    # ── HOME intercept (OS-level run_loop calls this BEFORE quitting) ────
    def on_home_press(self):
        """Double-tap to exit. Returning True suppresses the OS default
        (which would route to the apps drawer)."""
        now = time.ticks_ms()
        if time.ticks_diff(now, self._home_t) < DOUBLE_TAP_MS:
            # second tap within window → let OS take it (return False)
            return False
        # first tap (or stale)
        self._home_t                = now
        self._counts[api.BTN_HOME]  = self._counts.get(api.BTN_HOME, 0) + 1
        self._flash[api.BTN_HOME]   = now + FLASH_MS
        self._event                 = "HOME (tap again to exit)"
        self._home_hint             = "tap again to exit"
        self._dirty                 = True
        return True   # don't exit yet

    def on_button_press(self, btn):
        # HOME comes through on_home_press; all others come here.
        self._event              = "PRESS %s" % self._name_for(btn)
        self._counts[btn]        = self._counts.get(btn, 0) + 1
        self._flash[btn]         = time.ticks_ms() + FLASH_MS
        self._dirty              = True

    def on_button_release(self, btn):
        self._event = "RELEASE %s" % self._name_for(btn)
        self._dirty = True

    def _name_for(self, btn):
        for b, lbl in self._labels():
            if b == btn:
                return lbl
        return "?"

    def update(self, dt):
        btns = self._os.buttons
        now  = time.ticks_ms()
        # live held state
        for b, _ in self._labels():
            held = btns.is_pressed(b)
            if held != self._held[b]:
                self._held[b] = held
                self._dirty   = True
        # expire flash timers
        for b in list(self._flash.keys()):
            if self._flash[b] and time.ticks_diff(now, self._flash[b]) >= 0:
                self._flash[b] = 0
                self._dirty    = True
        # clear stale HOME "tap again" hint after the window closes
        if self._home_hint and time.ticks_diff(now, self._home_t) > DOUBLE_TAP_MS:
            self._home_hint = ""
            self._dirty     = True

    # ── render: stylised gamepad layout ───────────────────────────────────
    def draw(self, d):
        if not self._dirty:
            return
        d.clear(theme.BG)
        widgets.draw_header(d, "GAMEPAD")
        widgets.draw_hint  (d, "HOME x2 = exit")

        # The "controller body" — wide pill
        body_x = 14
        body_y = widgets.HEADER_H + 8
        body_w = SW - 28
        body_h = SH - widgets.HEADER_H - widgets.HINT_H - 16
        # subtle shadow + body
        d.rect(body_x + 2, body_y + 2, body_w, body_h, theme.MUTED2, fill=True)
        d.rect(body_x,     body_y,     body_w, body_h, theme.CARD,   fill=True)
        d.rect(body_x,     body_y,     body_w, 3,      theme.PRIMARY, fill=True)

        # ── D-pad cluster (left half) ─────────────────────────────────────
        dpad_cx = body_x + 50
        dpad_cy = body_y + body_h // 2 + 4
        dsz     = 22
        self._draw_btn(d, dpad_cx - dsz // 2, dpad_cy - dsz - 22,
                       dsz, dsz, api.BTN_UP)
        self._draw_btn(d, dpad_cx - dsz // 2, dpad_cy + 22,
                       dsz, dsz, api.BTN_DOWN)
        self._draw_btn(d, dpad_cx - dsz - 22, dpad_cy - dsz // 2,
                       dsz, dsz, api.BTN_LEFT)
        self._draw_btn(d, dpad_cx + 22,       dpad_cy - dsz // 2,
                       dsz, dsz, api.BTN_RIGHT)
        # cross hub
        d.rect(dpad_cx - 4, dpad_cy - 4, 8, 8, theme.MUTED, fill=True)

        # ── action cluster (right half: A/B/C in a triangle) ──────────────
        act_cx = body_x + body_w - 60
        act_cy = body_y + body_h // 2 + 4
        asz    = 28
        # A: bottom-right
        self._draw_btn(d, act_cx + 16,        act_cy + 8,        asz, asz, api.BTN_A)
        # B: top-right
        self._draw_btn(d, act_cx + 16,        act_cy - asz - 6,  asz, asz, api.BTN_B)
        # C: left
        self._draw_btn(d, act_cx - asz - 4,   act_cy - asz // 2, asz, asz, api.BTN_C)

        # ── HOME pill (centred along the top) ─────────────────────────────
        pill_w = 56
        pill_h = 14
        pill_x = body_x + (body_w - pill_w) // 2
        pill_y = body_y + 14
        # held / flash colouring
        fill_c, text_c = self._btn_colours(api.BTN_HOME)
        d.rect(pill_x, pill_y, pill_w, pill_h, fill_c, fill=True)
        d.rect(pill_x, pill_y, pill_w,  1,     theme.PRIMARY, fill=True)
        d.text("HOME", pill_x + (pill_w - 4 * 8) // 2, pill_y + 3, text_c)

        # ── event line ────────────────────────────────────────────────────
        evt = self._event[:32]
        d.text(evt, (SW - len(evt) * 8) // 2,
               SH - widgets.HINT_H - 14, theme.PRIMARY)

        # ── home-double-tap hint (gold, fades after 400 ms) ───────────────
        if self._home_hint:
            d.text(self._home_hint,
                   (SW - len(self._home_hint) * 8) // 2,
                   SH - widgets.HINT_H - 26, theme.GOLD)

        self._dirty = False

    # ── helpers ──────────────────────────────────────────────────────────
    def _btn_colours(self, btn):
        now    = time.ticks_ms()
        flash  = self._flash.get(btn, 0)
        held   = self._held.get(btn, False)
        flashing = flash and time.ticks_diff(now, flash) < 0
        if flashing:
            return theme.GOLD, api.WHITE
        if held:
            return theme.PRIMARY, api.WHITE
        return theme.DOCK_BG, theme.TEXT_BRIGHT

    def _draw_btn(self, d, x, y, w, h, btn):
        fill_c, text_c = self._btn_colours(btn)
        # raised look: shadow + face
        d.rect(x + 1, y + 1, w, h, theme.MUTED2, fill=True)
        d.rect(x,     y,     w, h, fill_c,       fill=True)
        d.rect(x,     y,     w, 1, theme.PRIMARY, fill=True)
        # label
        lbl = self._name_for(btn)
        lw  = len(lbl) * 8
        d.text(lbl, x + (w - lw) // 2, y + (h - 8) // 2 - 2, text_c)
        # press counter
        cnt = "x%d" % self._counts.get(btn, 0)
        cw  = len(cnt) * 8
        d.text(cnt, x + (w - cw) // 2, y + h - 9, text_c)

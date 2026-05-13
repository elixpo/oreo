"""Gamepad — button-press tester.

Visual diagnostic for the badge's 8 buttons. Each button is drawn as a
labelled tile that:

  • lights up PRIMARY while held (live `is_pressed` state)
  • flashes GOLD for ~150 ms on every `just_pressed` edge
  • shows a per-button press counter underneath

A footer line shows the most-recent event ("PRESS A", "RELEASE B", ...).

Useful for breadboard bring-up and for confirming that the OS isn't
swallowing or duplicating events.
"""

import time
import lix
from lix import api
from lix_os import theme, widgets

SW = api.SCREEN_W
SH = api.SCREEN_H


_BUTTONS = [
    (api.BTN_HOME,  "HOME"),
    (api.BTN_A,     "A"),
    (api.BTN_B,     "B"),
    (api.BTN_C,     "C"),
    (api.BTN_UP,    "UP"),
    (api.BTN_DOWN,  "DOWN"),
    (api.BTN_LEFT,  "LEFT"),
    (api.BTN_RIGHT, "RIGHT"),
]

# Grid: 4 columns × 2 rows of tiles.
COLS         = 4
TILE_W       = 70
TILE_H       = 64
TILE_GAP_X   = 6
TILE_GAP_Y   = 8
FLASH_MS     = 150


class App(lix.App):
    name = "Gamepad"

    def on_enter(self, os):
        self._os       = os
        self._held     = {b: False for b, _ in _BUTTONS}
        self._counts   = {b: 0     for b, _ in _BUTTONS}
        self._flash    = {b: 0     for b, _ in _BUTTONS}   # ticks_ms() until
        self._event    = "press any button..."
        self._dirty    = True

    # NOTE: We bypass the app-level on_button_press / release callbacks and
    # poll directly each frame so we get the *raw* states (including the
    # HOME button, which the OS swallows for "exit" — we still see the edge
    # in is_pressed/just_pressed before the OS handles it).
    def on_button_press(self, btn):
        # Don't exit on HOME — the OS run-loop already routes HOME → quit.
        # We just want to see the event in the UI.
        self._event = "PRESS %s" % self._label_for(btn)
        self._counts[btn] = self._counts.get(btn, 0) + 1
        self._flash[btn]  = time.ticks_ms() + FLASH_MS
        self._dirty       = True

    def on_button_release(self, btn):
        self._event = "RELEASE %s" % self._label_for(btn)
        self._dirty = True

    def _label_for(self, btn):
        for b, lbl in _BUTTONS:
            if b == btn:
                return lbl
        return "?"

    def update(self, dt):
        btns = self._os.buttons
        now  = time.ticks_ms()
        # Sample held state every frame for the live highlight.
        for b, _ in _BUTTONS:
            held = btns.is_pressed(b)
            if held != self._held[b]:
                self._held[b] = held
                self._dirty   = True
        # Time-out the flash highlights.
        for b in list(self._flash.keys()):
            if self._flash[b] and time.ticks_diff(now, self._flash[b]) >= 0:
                self._flash[b] = 0
                self._dirty    = True

    def draw(self, d):
        if not self._dirty:
            return
        d.clear(theme.BG)
        widgets.draw_header(d, "GAMEPAD TEST")
        widgets.draw_hint  (d, "HOME=back")

        # 4×2 grid of tiles, centred horizontally
        total_w = COLS * TILE_W + (COLS - 1) * TILE_GAP_X
        x0      = (SW - total_w) // 2
        y0      = widgets.HEADER_H + 8

        now = time.ticks_ms()
        for i, (btn, label) in enumerate(_BUTTONS):
            col = i % COLS
            row = i // COLS
            tx  = x0 + col * (TILE_W + TILE_GAP_X)
            ty  = y0 + row * (TILE_H + TILE_GAP_Y)

            held  = self._held[btn]
            flash = self._flash[btn] and time.ticks_diff(now, self._flash[btn]) < 0
            fill_c = theme.GOLD if flash else (theme.PRIMARY if held else theme.CARD)
            text_c = api.WHITE if (held or flash) else theme.TEXT_BRIGHT

            d.rect(tx, ty, TILE_W, TILE_H, fill_c, fill=True)
            d.rect(tx, ty, TILE_W, 2,  theme.PRIMARY, fill=True)
            # label
            lx = tx + (TILE_W - len(label) * 16) // 2
            d.text(label, lx, ty + 8, text_c, scale=2)
            # press counter
            cnt = "x%d" % self._counts[btn]
            cx = tx + (TILE_W - len(cnt) * 8) // 2
            d.text(cnt, cx, ty + TILE_H - 14, text_c)

        # Footer event line just above the hint bar
        ev_y = SH - widgets.HINT_H - 16
        d.text(self._event[:32],
               (SW - len(self._event[:32]) * 8) // 2, ev_y,
               theme.PRIMARY)

        self._dirty = False

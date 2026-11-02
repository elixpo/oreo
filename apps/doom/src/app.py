"""Doom — Freedoom running on the badge's built-in Doom engine.

The engine is the firmware's _oreo_doom module (GPL-2.0-or-later, see
firmware/usermods/oreo_doom). The game data is Freedoom in the badge's
"doom" flash partition, written by ./deploy --full. Each frame the app
hands the engine the held buttons, the engine runs and renders, and the
frame is copied to the screen as is.

Controls:
  D-pad      move / turn (menus: navigate)
  A          fire (menus: select)
  B          use, open doors (prompts: yes)
  C (hold)   strafe with LEFT/RIGHT; C+UP cycles weapons
  HOME       game menu; twice within 1 s returns to OreoOS

Leaving with HOME twice keeps the game in memory, so opening Doom again
resumes it. Quitting from Doom's own menu ends the engine for this boot.
"""

import gc
import time
import oreoOS
from oreoOS import api, theme, widgets

try:
    import _oreo_doom as doom
except ImportError:
    doom = None

EXIT_TAP_MS = 1000

PLAYING  = "playing"
NO_ENGINE = "no-engine"
NO_DATA  = "no-data"
QUIT     = "quit"
FAILED   = "failed"

MESSAGES = {
    NO_ENGINE: ("This firmware has no", "Doom engine.", "Update the badge firmware."),
    NO_DATA:   ("No Doom game data.", "Reflash the badge with", "./deploy --full"),
    QUIT:      ("Doom has quit.", "Restart the badge", "to play again."),
}


class App(oreoOS.App):
    name = "Doom"

    # C is Doom's strafe button, so the notification panel stays shut.
    CAPTURES_C = True

    def on_enter(self, os):
        self._os = os
        self._home_t = -10000
        self._error = 0
        self._dirty = True
        self._state = self._start()

    def _start(self):
        if doom is None:
            return NO_ENGINE
        if doom.running():
            return PLAYING
        if not doom.available():
            return NO_DATA
        gc.collect()
        try:
            rc = doom.start()
        except OSError:
            return NO_DATA
        if rc == 0:
            return PLAYING
        if rc == -2:
            return QUIT
        self._error = rc
        return FAILED

    def realtime_mode(self):
        return self._state == PLAYING

    def on_home_press(self):
        """First HOME is Doom's menu key; a second within 1 s leaves."""
        if self._state != PLAYING:
            return False
        now = time.ticks_ms()
        if time.ticks_diff(now, self._home_t) < EXIT_TAP_MS:
            return False
        self._home_t = now
        return True

    def update(self, dt):
        if self._state != PLAYING:
            return
        buttons = self._os.buttons
        mask = 0
        for b in api.BUTTONS:
            if buttons.is_pressed(b):
                mask |= 1 << b
        drawn = doom.tick(mask)
        if drawn < 0:
            self._state = QUIT if doom.exit_code() == 0 else FAILED
            self._error = doom.exit_code()
            self._dirty = True
        elif drawn:
            self._dirty = True

    def draw(self, d):
        if not self._dirty:
            return
        self._dirty = False
        if self._state == PLAYING:
            d.blit_fullscreen(doom.frame())
            return
        d.clear(theme.BG)
        widgets.draw_header(d, "DOOM")
        lines = MESSAGES.get(self._state) or (
            "Doom stopped with", "error %d." % self._error, "Restart the badge.")
        y = widgets.HEADER_H + 40
        for line in lines:
            d.text(line, (api.SCREEN_W - len(line) * 8) // 2, y, theme.TEXT_BRIGHT)
            y += 20
        widgets.draw_hint(d, "HOME = back")

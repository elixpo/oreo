"""Template app for Lix OS.

To create a new app:
  1. Copy this folder to  /apps/<your-app-name>/
  2. Edit manifest.json (set name, author, etc.)
  3. Rewrite this file with your app's logic
  4. Reboot the badge — your app appears in the menu

The OS finds apps by scanning /apps/ for folders containing manifest.json.
The class MUST be named `App` and subclass `lix.App`.
"""

import lix
from lix import api


class App(lix.App):
    name = "Template"

    # ----- lifecycle -----------------------------------------------------

    def on_enter(self, os):
        """Called once when the app starts. Initialize state here."""
        super().on_enter(os)
        self.counter = 0
        self.dirty = True

    def on_exit(self):
        """Called once when the app exits (HOME pressed). Save / release here."""
        pass

    # ----- input ---------------------------------------------------------
    # HOME is intercepted by the OS — apps never see it.

    def on_button_press(self, btn):
        if btn == api.BTN_A:
            self.counter += 1
            self.dirty = True
        elif btn == api.BTN_B:
            self.counter -= 1
            self.dirty = True

    def on_button_release(self, btn):
        pass

    # ----- frame loop ----------------------------------------------------

    def update(self, dt):
        """Called every frame. dt = seconds since last frame.
        Update animations, timers, game state — but don't draw here."""
        pass

    def draw(self, d):
        """Called every frame after update(). Draw to the framebuffer.
        DO NOT call d.present() — the OS does that automatically."""
        if not self.dirty:
            return                                # skip wasted redraws
        d.clear(api.rgb(20, 20, 40))
        d.rect(0, 0, api.SCREEN_W, 30, api.rgb(255, 100, 30), fill=True)
        d.text(self.name, 8, 11, api.BLACK, scale=2)
        d.text("counter: %d" % self.counter, 30, 110, api.WHITE, scale=2)
        d.text("A: +1   B: -1",               30, 180, api.rgb(160, 160, 180))
        d.text("HOME: exit",                  30, api.SCREEN_H - 40, api.rgb(160, 160, 180))
        self.dirty = False

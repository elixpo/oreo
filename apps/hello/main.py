"""Hello — minimal demo app proving the lix.App lifecycle."""

import lix
from lix import api


class App(lix.App):
    name = "Hello"

    def on_enter(self, os):
        super().on_enter(os)
        self.t = 0.0
        self.last_sec = -1
        self.dirty = True

    def update(self, dt):
        self.t += dt
        sec = int(self.t)
        if sec != self.last_sec:
            self.last_sec = sec
            self.dirty = True

    def draw(self, d):
        if not self.dirty:
            return
        d.clear(api.rgb(20, 20, 40))
        d.rect(0, 0, api.SCREEN_W, 30, api.rgb(255, 100, 30), fill=True)
        d.text("Hello", 8, 11, api.BLACK, scale=2)

        d.text("hello, world!", 30, 80, api.WHITE, scale=2)
        d.text("alive: %ds" % self.last_sec, 30, 130, api.rgb(255, 220, 100), scale=2)

        d.text("press HOME to return", 22, api.SCREEN_H - 40, api.rgb(160, 160, 180))
        self.dirty = False

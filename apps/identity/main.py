"""Identity Card — the badge's default 'who I am' screen.

Edit the constants below to change what's shown. Later the Settings app will
move these into a persistent config file so they survive reboots without
editing source.
"""

import lix
from lix import api


# ----- edit me ------------------------------------------------------------
NAME    = "Ayushman"
HANDLE  = "@Circuit-Overtime"
ROLE    = "Builder of Lix"
ACCENT  = (255, 200, 0)         # title bar / footer / handle color (R,G,B)
# --------------------------------------------------------------------------


class App(lix.App):
    name = "Identity"

    def on_enter(self, os):
        super().on_enter(os)
        self._drawn = False

    def update(self, dt):
        pass

    def draw(self, d):
        if self._drawn:
            return
        accent = api.rgb(*ACCENT)
        bg     = api.rgb(12, 12, 24)

        d.clear(bg)

        # top accent bar
        d.rect(0, 0, api.SCREEN_W, 50, accent, fill=True)
        d.text("BADGE", 14, 18, api.BLACK, scale=2)

        # name (big)
        d.text(NAME, 16, 90, api.WHITE, scale=4)

        # handle (medium, in accent)
        d.text(HANDLE, 16, 150, accent, scale=2)

        # role (small, muted)
        d.text(ROLE, 16, 185, api.rgb(180, 180, 200), scale=2)

        # divider line
        d.line(16, 230, api.SCREEN_W - 16, 230, api.rgb(60, 60, 100))

        # bottom strip
        d.rect(0, api.SCREEN_H - 40, api.SCREEN_W, 40, accent, fill=True)
        d.text("LIX OS", 72, api.SCREEN_H - 28, api.BLACK, scale=2)

        # footer hint
        d.text("HOME: menu", 130, 244, api.rgb(140, 140, 170))

        self._drawn = True

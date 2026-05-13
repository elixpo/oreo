"""IR Quest — coming soon.

The dialogue tree + IR comms layer aren't shipped yet. This stub keeps
the launcher tile alive so the slot is visible in the apps drawer, but
opening it just shows a friendly "coming soon" card.

Full implementation tracked separately — restore from git history when
the IR transport lands.
"""

import oreoOS
from oreoOS import api
from oreoOS import theme, widgets

SW = api.SCREEN_W
SH = api.SCREEN_H


class App(oreoOS.App):
    name         = "IR Quest"
    SHOW_LOADING = False

    def on_enter(self, os):
        self._os    = os
        self._dirty = True

    def on_button_press(self, btn):
        pass

    def update(self, dt):
        pass

    def draw(self, d):
        if not self._dirty:
            return
        d.clear(theme.BG)
        widgets.draw_header(d, "IR QUEST")
        widgets.draw_hint  (d, "HOME=back")

        # Centred card with a pink accent + big "Coming Soon" line.
        cw, ch = SW - 40, 130
        cx, cy = (SW - cw) // 2, (SH - ch) // 2
        d.rect(cx + 2, cy + 2, cw, ch, theme.MUTED2, fill=True)
        d.rect(cx,     cy,     cw, ch, theme.CARD,   fill=True)
        d.rect(cx,     cy,     cw, 3,  theme.PRIMARY, fill=True)

        title = "Coming Soon"
        tw    = len(title) * 24                  # scale=3 → 8*3 px per glyph
        d.text(title, (SW - tw) // 2, cy + 28, theme.PRIMARY, scale=3)

        sub = "IR comms in development"
        sw  = len(sub) * 8
        d.text(sub, (SW - sw) // 2, cy + 70, theme.TEXT_BRIGHT)

        hint = "keep an eye up @elixpo"
        hw   = len(hint) * 8
        d.text(hint, (SW - hw) // 2, cy + 92, theme.MUTED)

        self._dirty = False

"""IR Quest — branching NPC dialogue with simple choices.

Conference badge gimmick: walk up to a kiosk / another badge, swap IDs over
IR, and unlock dialogue branches. The IR exchange itself is a stub for now;
the dialogue tree is fully playable offline.

Controls:
  UP/DOWN — pick choice
  A       — confirm
  B       — back to previous node
  HOME    — exit
"""

import oreoOS
from oreoOS import api
from oreoOS import theme, widgets

SW = api.SCREEN_W
SH = api.SCREEN_H

# ── tiny dialogue tree ───────────────────────────────────────────────────────
# Each node: speaker, lines (list of strings), choices (list of (label, target_id))
# target_id "__exit__" closes the app.

DIALOGUE = {
    "start": {
        "speaker": "ORACLE",
        "lines":   ["Welcome, traveller.", "Why have you come?"],
        "choices": [
            ("Seek a quest",   "quest"),
            ("Just exploring", "explore"),
            ("Leave",          "__exit__"),
        ],
    },
    "quest": {
        "speaker": "ORACLE",
        "lines":   ["A panda is lost.", "Three pings near the",
                    "festival tents. Find", "and bring it back."],
        "choices": [
            ("Accept",  "accepted"),
            ("Decline", "decline"),
        ],
    },
    "accepted": {
        "speaker": "ORACLE",
        "lines":   ["Bless your sparkles!", "Bring the panda home."],
        "choices": [("Onward", "__exit__")],
    },
    "decline": {
        "speaker": "ORACLE",
        "lines":   ["Maybe another time."],
        "choices": [("Back", "start")],
    },
    "explore": {
        "speaker": "ORACLE",
        "lines":   ["The badge senses",
                    "other travellers via",
                    "IR.  Hold A near a",
                    "friend to swap.",
                    "(IR comms coming soon.)"],
        "choices": [("Back", "start")],
    },
}


class App(oreoOS.App):
    name         = "IR Quest"
    SHOW_LOADING = False

    def on_enter(self, os):
        self._os    = os
        self._node  = "start"
        self._sel   = 0
        self._hist  = []           # back-button stack
        self._dirty = True

    def on_button_press(self, btn):
        node = DIALOGUE[self._node]
        ch   = node["choices"]
        if btn == api.BTN_UP:
            self._sel = (self._sel - 1) % len(ch); self._dirty = True
        elif btn == api.BTN_DOWN:
            self._sel = (self._sel + 1) % len(ch); self._dirty = True
        elif btn == api.BTN_A:
            target = ch[self._sel][1]
            if target == "__exit__":
                self._os.quit()
                return
            self._hist.append(self._node)
            self._node = target
            self._sel  = 0
            self._dirty = True
        elif btn == api.BTN_B and self._hist:
            self._node = self._hist.pop()
            self._sel  = 0
            self._dirty = True

    def update(self, dt):
        pass

    def draw(self, d):
        if not self._dirty:
            return
        d.clear(theme.BG)
        widgets.draw_header(d, "IR QUEST")
        widgets.draw_hint  (d, "A=ok  B=back  HOME=exit")

        node = DIALOGUE[self._node]

        # Speaker bar
        sp_y = widgets.HEADER_H + 8
        d.rect(8, sp_y, SW - 16, 18, theme.TEAL, fill=True)
        d.text(node["speaker"], 16, sp_y + 2, api.WHITE, scale=2)

        # Dialogue card
        card_y = sp_y + 22
        card_h = 100
        d.rect(8, card_y, SW - 16, card_h, theme.CARD, fill=True)
        d.rect(8, card_y, SW - 16, 2,    theme.PRIMARY, fill=True)
        for i, line in enumerate(node["lines"][:5]):
            d.text(line, 16, card_y + 8 + i * 16, theme.TEXT_BRIGHT, scale=2)

        # Choices
        cy = card_y + card_h + 6
        for i, (label, _target) in enumerate(node["choices"]):
            sel = (i == self._sel)
            color = theme.PRIMARY if sel else theme.TEXT_BRIGHT
            prefix = ">" if sel else " "
            d.text("%s %s" % (prefix, label), 24, cy + i * 14, color, scale=1)

        self._dirty = False

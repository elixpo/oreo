"""Elixpo Pet — Tamagotchi-style panda care game.

Stats: hunger / happiness / health, each 0..100.
Drift: hunger -1/15s, happiness -1/20s, health follows the worse of the two.
Buttons:
  A — feed   (+30 hunger,  -3 happiness if very full)
  B — play   (+15 happiness, -10 hunger)
  C — sleep  (regen all stats slowly while held)
  HOME — exit
Persistent: state saved on exit to apps/pet/state.txt.
"""

import time
import lix
from lix import api
from lix_os import theme, widgets

SW = api.SCREEN_W
SH = api.SCREEN_H

STATE_PATH = "apps/pet/state.txt"


def _load_state():
    try:
        with open(STATE_PATH) as f:
            parts = f.read().strip().split(",")
            return (int(parts[0]), int(parts[1]), int(parts[2]))
    except Exception:
        return (80, 80, 90)

def _save_state(h, hp, hl):
    try:
        with open(STATE_PATH, "w") as f:
            f.write("%d,%d,%d" % (h, hp, hl))
    except Exception:
        pass


def _load_mascot():
    try:
        m = __import__("assets.sprites.optimized.mascot", None, None, ["DATA", "W", "H"])
        return (bytearray(m.DATA), m.W, m.H)
    except (ImportError, AttributeError):
        return None


def _clamp(v):
    return max(0, min(100, int(v)))


class App(lix.App):
    name = "Elixpo Pet"

    def on_enter(self, os):
        self._os                = os
        self._mascot            = _load_mascot()
        self._hunger, self._happy, self._health = _load_state()
        self._last_tick         = time.ticks_ms()
        self._anim_t            = 0.0
        self._msg               = ""
        self._msg_left          = 0.0
        self._dirty             = True
        self._sleeping          = False

    def on_exit(self):
        _save_state(self._hunger, self._happy, self._health)

    def on_button_press(self, btn):
        if btn == api.BTN_A:
            # Feed
            if self._hunger >= 95:
                self._happy = _clamp(self._happy - 3)
                self._flash("Too full!")
            else:
                self._hunger = _clamp(self._hunger + 30)
                self._flash("Yum!")
        elif btn == api.BTN_B:
            if self._hunger < 15:
                self._flash("Too hungry to play")
            else:
                self._happy  = _clamp(self._happy  + 15)
                self._hunger = _clamp(self._hunger - 10)
                self._flash("Plays!")
        elif btn == api.BTN_C:
            self._sleeping = True
            self._flash("zZz...")
        self._dirty = True

    def on_button_release(self, btn):
        if btn == api.BTN_C and self._sleeping:
            self._sleeping = False
            self._dirty = True

    def _flash(self, s):
        self._msg = s
        self._msg_left = 1.0

    def update(self, dt):
        # Wall-clock drift
        now    = time.ticks_ms()
        elapsed = time.ticks_diff(now, self._last_tick) / 1000.0
        self._last_tick = now
        self._anim_t  += dt
        self._msg_left = max(0.0, self._msg_left - dt)

        # Decay (slower while sleeping; sleeping also slowly heals)
        rate = 0.3 if self._sleeping else 1.0
        self._hunger = _clamp(self._hunger - 0.07 * elapsed * rate)
        self._happy  = _clamp(self._happy  - 0.05 * elapsed * rate)
        if self._sleeping:
            self._health = _clamp(self._health + 0.10 * elapsed)
        else:
            # Health follows the worse of hunger/happy
            worst = min(self._hunger, self._happy)
            target = (self._health + worst) / 2
            self._health = _clamp(target * 0.99 + 1.0 if worst > 30 else target * 0.97)
        self._dirty = True

    def draw(self, d):
        if not self._dirty:
            return
        d.clear(theme.BG)
        widgets.draw_header(d, "ELIXPO PET")
        widgets.draw_hint  (d, "A=feed  B=play  C=sleep")

        # Mascot, bobbing
        bob = int(2 * (abs((self._anim_t * 2) % 2 - 1)))    # 0..2 sine-ish
        if self._mascot:
            data, mw, mh = self._mascot
            d.blit(data, 20, widgets.HEADER_H + 20 + bob, mw, mh)
        else:
            d.rect(20, widgets.HEADER_H + 20 + bob, 72, 72, theme.PRIMARY, fill=True)

        # Stat bars
        bx = 110
        bw = SW - bx - 20
        for i, (label, val, col) in enumerate([
                ("Hunger",   self._hunger, theme.PRIMARY),
                ("Happiness",self._happy,  theme.TEAL),
                ("Health",   self._health, theme.GOLD)]):
            by = widgets.HEADER_H + 22 + i * 28
            d.text(label, bx, by, theme.TEXT_BRIGHT)
            # bar
            d.rect(bx, by + 12, bw, 8, theme.MUTED2,  fill=True)
            d.rect(bx, by + 12, bw * val // 100, 8, col, fill=True)
            d.text("%d" % val, bx + bw - 24, by, theme.MUTED)

        # Status / flash message
        msg = self._msg if self._msg_left > 0 else ("sleeping..." if self._sleeping else "")
        if msg:
            d.text(msg, (SW - len(msg) * 8) // 2, SH - widgets.HINT_H - 14, theme.PRIMARY)

        self._dirty = False

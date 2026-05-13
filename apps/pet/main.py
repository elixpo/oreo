"""Elixpo Pet — Tamagotchi-style panda companion.

Three stats (hunger / happiness / health) drift slowly so the player feels
they're maintaining a real pet on a daily routine rather than minute-by-
minute. Five sprite expressions are picked from current state:

  hungry   hunger < 35
  sad      happiness < 35
  sleep    while C held (and slowly heals)
  eat      brief moment after A pressed
  happy    default

When the user feeds (A) or plays (B), short-lived "heart" particles spawn
from the panda for tactile feedback.

Controls:
  A      feed   (+30 hunger, brief 'eat' face + heart particles)
  B      play   (+15 happiness, -10 hunger, heart particles)
  C      sleep  (held — regen all stats slowly)
  HOME   apps drawer (uses OS default)
"""

import time
import lix
from lix import api
from lix_os import theme, widgets

SW = api.SCREEN_W
SH = api.SCREEN_H

STATE_PATH = "apps/pet/state.txt"

# Decay rates per second — TUNED to feel like a daily routine.
# Each stat drops ~30 points over a 12-hour idle period.
DECAY_HUNGER  = 0.0007   # ~30 pts / 12 h
DECAY_HAPPY   = 0.0005
EAT_FACE_MS   = 1200     # show 'eat' face for this long after a feed


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


def _try_sprite(name):
    """Load apps/pet/assets/optimized/<name>.py → (bytearray, w, h) or None."""
    try:
        m = __import__("apps.pet.assets.optimized." + name, None, None,
                       ["DATA", "W", "H"])
        return (bytearray(m.DATA), m.W, m.H)
    except (ImportError, AttributeError):
        return None


def _try_mascot():
    """Fallback to the OS mascot if the per-pet sprites haven't been generated."""
    try:
        m = __import__("assets.sprites.optimized.mascot", None, None,
                       ["DATA", "W", "H"])
        return (bytearray(m.DATA), m.W, m.H)
    except (ImportError, AttributeError):
        return None


def _clamp(v):
    return max(0, min(100, int(v)))


# ─── particle effect ─────────────────────────────────────────────────────────

class _HeartParticle:
    """One floating heart that rises from the panda for ~700 ms."""
    __slots__ = ("x", "y0", "t", "max_t", "vx")
    def __init__(self, x, y, vx):
        self.x      = x
        self.y0     = y
        self.t      = 0.0
        self.max_t  = 0.8
        self.vx     = vx

    def update(self, dt):
        self.t += dt
        return self.t < self.max_t

    def draw(self, d, heart_sprite):
        if self.t >= self.max_t:
            return
        # rise upward, drift sideways
        prog = self.t / self.max_t
        x = int(self.x + self.vx * prog)
        y = int(self.y0 - prog * 40)
        if heart_sprite:
            data, w, h = heart_sprite
            d.blit(data, x - w // 2, y - h // 2, w, h)
        else:
            # procedural pixel heart fallback
            for dy, dx_pairs in [(0, [-2, -1, 1, 2]),
                                  (1, [-3, -2, -1, 0, 1, 2, 3]),
                                  (2, [-3, -2, -1, 0, 1, 2, 3]),
                                  (3, [-2, -1, 0, 1, 2]),
                                  (4, [-1, 0, 1])]:
                for dx in dx_pairs:
                    d.rect(x + dx, y + dy, 1, 1, theme.PRIMARY, fill=True)


# ─── App ─────────────────────────────────────────────────────────────────────

class App(lix.App):
    name         = "Elixpo Pet"
    SHOW_LOADING = False

    def on_enter(self, os):
        self._os        = os
        self._sprites   = {k: _try_sprite("panda_" + k)
                           for k in ("happy", "hungry", "sad", "sleep", "eat")}
        self._fallback  = _try_mascot()
        self._heart_spr = _try_sprite("heart")
        self._hunger, self._happy, self._health = _load_state()
        self._last_tick = time.ticks_ms()
        self._anim_t    = 0.0
        self._msg       = ""
        self._msg_left  = 0.0
        self._eat_left  = 0.0
        self._sleeping  = False
        self._hearts    = []
        self._dirty     = True

    def on_exit(self):
        _save_state(self._hunger, self._happy, self._health)

    def on_button_press(self, btn):
        if btn == api.BTN_A:
            if self._hunger >= 95:
                self._happy = _clamp(self._happy - 3)
                self._flash("Too full!")
            else:
                self._hunger    = _clamp(self._hunger + 30)
                self._eat_left  = EAT_FACE_MS / 1000.0
                self._flash("Yum!")
                self._spawn_hearts(3)
        elif btn == api.BTN_B:
            if self._hunger < 15:
                self._flash("Too hungry to play")
            else:
                self._happy  = _clamp(self._happy  + 15)
                self._hunger = _clamp(self._hunger - 10)
                self._flash("Plays!")
                self._spawn_hearts(2)
        elif btn == api.BTN_C:
            self._sleeping = True
            self._flash("zZz...")
        self._dirty = True

    def on_button_release(self, btn):
        if btn == api.BTN_C and self._sleeping:
            self._sleeping = False
            self._dirty    = True

    def _flash(self, s):
        self._msg = s
        self._msg_left = 1.2

    def _spawn_hearts(self, n):
        """Spawn `n` heart particles drifting up from the panda."""
        # panda is at ~(50, 80) → spawn at top of panda
        for i in range(n):
            vx = (i - n // 2) * 10
            self._hearts.append(_HeartParticle(80, 100, vx))

    # ── update ──────────────────────────────────────────────────────────
    def update(self, dt):
        now    = time.ticks_ms()
        wall_dt = time.ticks_diff(now, self._last_tick) / 1000.0
        self._last_tick = now
        self._anim_t  += dt
        self._msg_left = max(0.0, self._msg_left - dt)
        self._eat_left = max(0.0, self._eat_left - dt)

        rate = 0.4 if self._sleeping else 1.0
        self._hunger = _clamp(self._hunger - DECAY_HUNGER * wall_dt * rate * 100)
        self._happy  = _clamp(self._happy  - DECAY_HAPPY  * wall_dt * rate * 100)
        if self._sleeping:
            self._health = _clamp(self._health + 0.05 * wall_dt)
        else:
            worst = min(self._hunger, self._happy)
            target = (self._health + worst) / 2
            self._health = _clamp(target * 0.99 + (1.0 if worst > 30 else -0.5))

        # Tick particles
        self._hearts = [p for p in self._hearts if p.update(dt)]
        self._dirty  = True

    # ── sprite picker ───────────────────────────────────────────────────
    def _pick_expression(self):
        if self._sleeping:
            return "sleep"
        if self._eat_left > 0:
            return "eat"
        if self._hunger < 35:
            return "hungry"
        if self._happy < 35:
            return "sad"
        return "happy"

    # ── render ──────────────────────────────────────────────────────────
    def draw(self, d):
        if not self._dirty:
            return
        d.clear(theme.BG)
        widgets.draw_header(d, "ELIXPO PET")
        widgets.draw_hint  (d, "A=feed  B=play  C=sleep")

        # ── mascot — picked by current emotional state ─────────────────
        key      = self._pick_expression()
        sprite   = self._sprites.get(key) or self._fallback
        bob      = int(2 * (abs((self._anim_t * 2) % 2 - 1)))
        sx, sy   = 16, widgets.HEADER_H + 24 + bob
        if sprite:
            data, mw, mh = sprite
            d.blit(data, sx, sy, mw, mh)
        else:
            d.rect(sx, sy, 64, 64, theme.PRIMARY, fill=True)

        # ── stat rows on the right with heart icons ─────────────────────
        bx     = 100
        bw     = SW - bx - 20
        bars   = [("Hunger",    self._hunger, theme.PRIMARY),
                  ("Happiness", self._happy,  theme.TEAL),
                  ("Health",    self._health, theme.GOLD)]
        for i, (label, val, col) in enumerate(bars):
            by = widgets.HEADER_H + 18 + i * 30
            d.text(label, bx, by, theme.TEXT_BRIGHT)
            # heart sprite as the row icon (or pink rect fallback)
            if self._heart_spr:
                hd, hw, hh = self._heart_spr
                d.blit(hd, bx + bw - hw, by, hw, hh)
            else:
                d.rect(bx + bw - 12, by, 10, 8, theme.PRIMARY, fill=True)
            # bar
            d.rect(bx, by + 12, bw - 22, 8, theme.MUTED2, fill=True)
            d.rect(bx, by + 12, (bw - 22) * val // 100, 8, col, fill=True)
            d.text("%d" % val, bx + bw - 22 - 24, by, theme.MUTED)

        # ── heart particles ─────────────────────────────────────────────
        for p in self._hearts:
            p.draw(d, self._heart_spr)

        # ── status message ──────────────────────────────────────────────
        msg = self._msg if self._msg_left > 0 else \
              ("sleeping..." if self._sleeping else "")
        if msg:
            d.text(msg, (SW - len(msg) * 8) // 2,
                   SH - widgets.HINT_H - 14, theme.PRIMARY)

        self._dirty = False

"""Oreo Pet — Tamagotchi-style panda companion.

UI: panda centred on a soft bg, three "heart row" stats above (hunger /
happiness / health — 5 hearts each, filled vs empty), a speech-bubble
callout below showing the pet's current thought.

Decay is intentionally slow — you should feel like you're caring for a pet
on a *daily* routine. Each stat drops roughly 25 pts every 24 h idle.

Controls:
  A      feed   (+30 hunger,    spawns floating hearts)
  B      play   (+15 happiness, spawns floating hearts)
  C      sleep  (held — regen all stats slowly)
  HOME   apps drawer (OS default)
"""

import time
import oreoOS
from oreoOS import api
from oreoOS import theme, widgets

SW = api.SCREEN_W
SH = api.SCREEN_H

STATE_PATH = "apps/pet/state.txt"

# Per-second decay — slowed ~3× from the previous tune so the pet survives
# a normal multi-day on-off cadence without auto-starving. At 0.00045 pt/s
# a full hunger bar drains in roughly 60 hours of *foreground* time on the
# badge (the OS only ticks update() while the pet app is open). Combine
# with the badge being off most of the day and real-world feed frequency
# is about every 2–3 days.
DECAY_HUNGER = 0.00045
DECAY_HAPPY  = 0.00030
EAT_FACE_MS  = 1200      # show 'eat' expression for this long after feeding


# ─── helpers ─────────────────────────────────────────────────────────────────

def _load_state():
    try:
        with open(STATE_PATH) as f:
            a, b, c = f.read().strip().split(",")
            return (int(a), int(b), int(c))
    except Exception:
        return (80, 80, 90)

def _save_state(h, hp, hl):
    try:
        with open(STATE_PATH, "w") as f:
            f.write("%d,%d,%d" % (h, hp, hl))
    except Exception:
        pass

def _clamp(v):
    return max(0, min(100, int(v)))

def _try_sprite(modpath):
    try:
        m = __import__(modpath, None, None, ["DATA", "W", "H"])
        return (bytearray(m.DATA), m.W, m.H)
    except (ImportError, AttributeError):
        return None


# ─── heart particle (rises from panda when feeding/playing) ─────────────────

class _HeartParticle:
    __slots__ = ("x", "y0", "t", "max_t", "vx")
    def __init__(self, x, y, vx):
        self.x, self.y0, self.vx = x, y, vx
        self.t, self.max_t = 0.0, 0.9

    def update(self, dt):
        self.t += dt
        return self.t < self.max_t

    def draw(self, d, heart_sprite):
        if self.t >= self.max_t:
            return
        prog = self.t / self.max_t
        x    = int(self.x + self.vx * prog)
        y    = int(self.y0 - prog * 50)
        if heart_sprite:
            data, w, h = heart_sprite
            d.blit(data, x - w // 2, y - h // 2, w, h)
        else:
            # 5×5 pixel-heart fallback
            for dy, cols in [(0, (-2, -1, 1, 2)),
                              (1, range(-3, 4)),
                              (2, range(-3, 4)),
                              (3, range(-2, 3)),
                              (4, (-1, 0, 1))]:
                for dx in cols:
                    d.rect(x + dx, y + dy, 1, 1, theme.PRIMARY, fill=True)


def _draw_heart(d, x, y, filled=True):
    """Tiny 7×7 pixel heart — used for the stat rows."""
    col = theme.PRIMARY if filled else theme.MUTED2
    for dy, cols in [(0, (1, 2, 4, 5)),
                      (1, (0, 1, 2, 3, 4, 5, 6)),
                      (2, (0, 1, 2, 3, 4, 5, 6)),
                      (3, (1, 2, 3, 4, 5)),
                      (4, (2, 3, 4)),
                      (5, (3,))]:
        for dx in cols:
            d.rect(x + dx, y + dy, 1, 1, col, fill=True)


def _draw_speech_bubble(d, x, y, w, h, text, color):
    """Centred speech-bubble callout below the panda."""
    d.rect(x, y, w, h, theme.CARD, fill=True)
    d.rect(x, y, w, 2, theme.PRIMARY, fill=True)
    # Bottom-left "tail" — three short rows pointing at the panda
    d.rect(x + 12, y + h,     6, 2, theme.CARD,    fill=True)
    d.rect(x + 14, y + h + 2, 4, 2, theme.CARD,    fill=True)
    # Centred text
    tw = len(text) * 8
    d.text(text, x + (w - tw) // 2, y + (h - 8) // 2, color)


# ─── App ─────────────────────────────────────────────────────────────────────

class App(oreoOS.App):
    name         = "Oreo Pet"
    SHOW_LOADING = False

    def on_enter(self, os):
        self._os = os
        # Sprites
        keys = ("happy", "hungry", "sad", "sleep", "eat")
        self._sprites   = {k: _try_sprite("apps.pet.assets.optimized.panda_" + k)
                           for k in keys}
        self._fallback  = _try_sprite("assets.sprites.optimized.mascot")
        self._heart_spr = _try_sprite("apps.pet.assets.optimized.heart")

        self._hunger, self._happy, self._health = _load_state()
        self._last_tick = time.ticks_ms()
        self._anim_t    = 0.0
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
            else:
                self._hunger    = _clamp(self._hunger + 30)
                self._eat_left  = EAT_FACE_MS / 1000.0
                self._spawn_hearts(3)
        elif btn == api.BTN_B:
            if self._hunger > 15:
                self._happy  = _clamp(self._happy  + 15)
                self._hunger = _clamp(self._hunger - 10)
                self._spawn_hearts(2)
        elif btn == api.BTN_C:
            self._sleeping = True
        self._dirty = True

    def on_button_release(self, btn):
        if btn == api.BTN_C and self._sleeping:
            self._sleeping = False
            self._dirty = True

    def _spawn_hearts(self, n):
        for i in range(n):
            vx = (i - n // 2) * 12
            self._hearts.append(_HeartParticle(SW // 2, 100, vx))

    def update(self, dt):
        now      = time.ticks_ms()
        wall_dt  = time.ticks_diff(now, self._last_tick) / 1000.0
        self._last_tick = now
        self._anim_t   += dt
        self._eat_left  = max(0.0, self._eat_left - dt)

        # Decay (much slower when asleep)
        rate = 0.3 if self._sleeping else 1.0
        self._hunger = _clamp(self._hunger - DECAY_HUNGER * wall_dt * 100 * rate)
        self._happy  = _clamp(self._happy  - DECAY_HAPPY  * wall_dt * 100 * rate)
        if self._sleeping:
            self._health = _clamp(self._health + 0.05 * wall_dt)
        else:
            worst        = min(self._hunger, self._happy)
            target       = (self._health + worst) // 2
            self._health = _clamp(target)

        self._hearts = [p for p in self._hearts if p.update(dt)]
        self._dirty  = True

    # ── sprite + thought picker ─────────────────────────────────────────
    def _pick_state(self):
        if self._sleeping:        return "sleep", "zZz..."
        if self._eat_left > 0:    return "eat",   "Yum!"
        if self._hunger < 35:     return "hungry","I'm hungry!"
        if self._happy < 35:      return "sad",   "Play with me?"
        if self._hunger > 90:     return "happy", "So full!"
        if self._happy  > 90:     return "happy", "Heehee!"
        return "happy", "I'm doing great"

    # ── render ──────────────────────────────────────────────────────────
    def draw(self, d):
        if not self._dirty:
            return
        d.clear(theme.BG)
        widgets.draw_header(d, "ELIXPO PET")
        widgets.draw_hint  (d, "A=feed  B=play  C=sleep")

        key, thought = self._pick_state()

        # ── stat rows: heart-grid above the panda ─────────────────────
        row_y = widgets.HEADER_H + 6
        for i, (label, val, _col) in enumerate([
                ("Hunger",    self._hunger, theme.PRIMARY),
                ("Happiness", self._happy,  theme.TEAL),
                ("Health",    self._health, theme.GOLD)]):
            ry = row_y + i * 12
            # 5 heart pips
            filled = val * 5 // 100
            for k in range(5):
                _draw_heart(d, 124 + k * 12, ry, filled=(k < filled))
            # Label on the left
            d.text(label, 16, ry, theme.TEXT_BRIGHT)
            # % readout on the right
            d.text("%d%%" % val, SW - 4 * 8 - 6, ry, theme.MUTED)

        # ── centred panda ─────────────────────────────────────────────
        sprite  = self._sprites.get(key) or self._fallback
        bob     = int(2 * (abs((self._anim_t * 2) % 2 - 1)))
        if sprite:
            data, mw, mh = sprite
            px = (SW - mw) // 2
            py = widgets.HEADER_H + 48 + bob
            d.blit(data, px, py, mw, mh)
        else:
            d.rect((SW - 64) // 2, widgets.HEADER_H + 48 + bob,
                   64, 64, theme.PRIMARY, fill=True)

        # ── heart particles (in front of panda) ───────────────────────
        for p in self._hearts:
            p.draw(d, self._heart_spr)

        # ── thought callout under the panda ───────────────────────────
        bw = max(110, len(thought) * 8 + 24)
        bx = (SW - bw) // 2
        by = SH - widgets.HINT_H - 24
        _draw_speech_bubble(d, bx, by, bw, 18, thought, theme.PRIMARY)

        self._dirty = False

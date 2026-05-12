"""Flappy Panda — Elixpo Badge edition.

Landscape 320×240. Mona-style physics (gravity + flap impulse), parallax
scenery (distant hills + clouds + grass), pipe-with-spike obstacles, three
state machine (INTRO → PLAY → GAME_OVER), persistent high score.

Sprites (under apps/flappy/assets/optimized/):
  panda_up.py / panda_down.py   — 24×24, flying / diving
  mona_sheet.py                 — 7×2 grid of 24×24 (optional; used if present)
  obstacle.py                   — 24×24 pipe segment with spike cap
  background.py                 — 80×30 distant hills (scaled ×4 horizontally)
  grass.py                      — 80×10 ground tile
  (clouds drawn procedurally)

Controls: A or UP = flap.
"""

import time
import lix
from lix import api, font

SW = api.SCREEN_W   # 320
SH = api.SCREEN_H   # 240

# ── physics ──────────────────────────────────────────────────────────────────

GRAVITY     = 480.0   # px/s²
FLAP_VY     = -180.0  # px/s
VY_CAP      = 320.0   # px/s
SCROLL      = 90.0    # px/s
SPAWN_SEC   = 1.7     # seconds between obstacle spawns
OBSTACLE_W  = 24
GAP_H       = 78
PANDA_X     = 40
GROUND_H    = 38      # thicker grass strip
GRASS_TOP   = 8       # how far the grass tile pokes above the dirt

# ── colours ──────────────────────────────────────────────────────────────────

C_SKY      = api.rgb(120, 200, 240)
C_SKY_DEEP = api.rgb( 95, 175, 220)
C_CLOUD    = api.WHITE
C_CLOUD_SH = api.rgb(230, 230, 240)
C_GROUND   = api.rgb( 96,  62,  40)
C_SHADOW   = api.rgb( 20,  40,  60)
C_TITLE    = api.rgb(255,  93, 104)
C_TEXT     = api.WHITE
C_DIM      = api.rgb(200, 180, 160)
C_HI       = api.rgb(255, 230,  80)

# ── persistent high score ────────────────────────────────────────────────────

HISCORE_PATH = "apps/flappy/hiscore.txt"

def _load_hiscore():
    try:
        with open(HISCORE_PATH, "r") as f:
            return int(f.read().strip() or "0")
    except Exception:
        return 0

def _save_hiscore(v):
    try:
        with open(HISCORE_PATH, "w") as f:
            f.write(str(int(v)))
    except Exception:
        pass

# ── asset loaders ────────────────────────────────────────────────────────────

_assets = {}   # name → (data, w, h) or None

def _try_import(modname):
    try:
        return __import__(modname, None, None, ["DATA", "W", "H"])
    except (ImportError, AttributeError):
        return None

def _load(name):
    if name in _assets:
        return _assets[name]
    mod = _try_import("apps.flappy.assets.optimized.%s" % name)
    if mod and hasattr(mod, "DATA"):
        result = (mod.DATA, mod.W, mod.H)
    else:
        result = None
    _assets[name] = result
    return result

# ── LCG RNG ──────────────────────────────────────────────────────────────────

_seed = 12345
def _rand():
    global _seed
    _seed = (_seed * 1103515245 + 12345) & 0x7FFFFFFF
    return _seed

def _rand_gap_y(top_margin, bot_margin):
    lo = top_margin
    hi = SH - GROUND_H - GAP_H - bot_margin
    return lo + _rand() % max(1, hi - lo)

# ── obstacle ─────────────────────────────────────────────────────────────────

class Obstacle:
    def __init__(self):
        self.x        = float(SW)
        self.gap_y    = _rand_gap_y(24, 12)
        self.passed   = False

    def update(self, dt):
        self.x -= SCROLL * dt

    def bounds(self):
        # Top hitbox (above gap), bottom hitbox (below gap)
        return (
            (int(self.x), 0,                                   OBSTACLE_W, self.gap_y),
            (int(self.x), self.gap_y + GAP_H,                  OBSTACLE_W,
                          SH - GROUND_H - self.gap_y - GAP_H),
        )

    def draw(self, d):
        obs = _load("obstacle")
        x = int(self.x)
        if obs:
            data, ow, oh = obs
            # Top: stack tiles from y=gap_y-oh upward to y=0
            y = self.gap_y - oh
            while y > -oh:
                d.blit(data, x, max(0, y), ow, oh)
                # crude clipping when y < 0: just stop drawing past the top
                if y <= 0:
                    break
                y -= oh
            # Bottom: stack tiles from y=gap_y+GAP_H downward to ground
            y = self.gap_y + GAP_H
            while y < SH - GROUND_H:
                d.blit(data, x, y, ow, oh)
                y += oh
        else:
            # Procedural fallback: solid pipes
            d.rect(x, 0,                  OBSTACLE_W, self.gap_y,       api.GREEN, fill=True)
            d.rect(x, self.gap_y + GAP_H, OBSTACLE_W,
                   SH - GROUND_H - self.gap_y - GAP_H,                 api.GREEN, fill=True)

# ── panda ────────────────────────────────────────────────────────────────────

class Panda:
    def __init__(self):
        self.y         = float(SH // 2)
        self.vy        = 0.0
        self.score     = 0
        self.died_at_s = None     # seconds-since-death, set on die()
        self.alive_t   = 0.0      # seconds alive (for engine-puff anim phase)

    def jump(self):
        if not self.is_dead():
            self.vy = FLAP_VY

    def update(self, dt, obstacles):
        """dt is seconds."""
        if self.is_dead():
            self.died_at_s += dt
            return
        self.alive_t += dt
        self.vy = min(self.vy + GRAVITY * dt, VY_CAP)
        self.y += self.vy * dt
        # Ceiling
        if self.y < 0:
            self.y = 0.0
            self.vy = 0.0
        # Ground / floor
        if self.y + 24 > SH - GROUND_H:
            self.die()
            return
        # Collisions + score
        bx, by, bw, bh = self.bounds()
        for o in obstacles:
            for ox, oy, ow, oh in o.bounds():
                if (bx < ox + ow and bx + bw > ox and
                    by < oy + oh and by + bh > oy):
                    self.die()
                    return
            if not o.passed and o.x + OBSTACLE_W < bx:
                o.passed = True
                self.score += 1

    def bounds(self):
        # Slightly tighter than 24×24
        return (PANDA_X + 3, int(self.y) + 3, 18, 18)

    def is_dead(self):
        return self.died_at_s is not None

    def is_done_dying(self):
        return self.died_at_s is not None and self.died_at_s > 1.2

    def die(self):
        if self.died_at_s is None:
            self.died_at_s = 0.0

    def draw(self, d):
        py  = int(self.y)
        key = self._pick_sprite()
        sprite = _load(key)
        if sprite:
            data, sw, sh = sprite
            d.blit(data, PANDA_X, py, sw, sh)
        else:
            d.rect(PANDA_X, py, 24, 24, C_TITLE, fill=True)

    def _pick_sprite(self):
        """Choose which sprite key to render this frame.

        Alive:
          vy > 50  → panda_down (falling)
          else     → panda_up_a / panda_up_b alternating every ~150 ms
        Dying (~1.2 s total):
          first half  → panda_crash
          second half → panda_blast
        """
        if self.is_dead():
            return "panda_crash" if self.died_at_s < 0.5 else "panda_blast"
        if self.vy > 50:
            return "panda_down"
        # alternate every 150 ms based on accumulated alive time
        phase = int(self.alive_t / 0.15) & 1
        return "panda_up_b" if phase else "panda_up_a"

# ── scenery (parallax) ───────────────────────────────────────────────────────

class Scenery:
    def __init__(self):
        self.offset = 0.0

    def update(self, dt):
        self.offset += SCROLL * dt * 0.5    # parallax slower than obstacles

    def _tile_x(self, period, factor):
        return int(-(self.offset * factor) % period)

    def draw_sky(self, d):
        # vertical sky gradient — two bands
        d.rect(0, 0,        SW, SH // 2, C_SKY,      fill=True)
        d.rect(0, SH // 2,  SW, SH // 2 - GROUND_H, C_SKY_DEEP, fill=True)

    def draw_clouds(self, d):
        # 3 procedural clouds at different x positions, scrolling slowly
        base = self._tile_x(SW + 80, 0.25)
        positions = [(0, 30), (110, 22), (220, 38)]
        for px, py in positions:
            cx = ((px - base) % (SW + 80)) - 40
            self._cloud(d, cx, py)

    def _cloud(self, d, x, y):
        # Fluffy cloud: 4 overlapping circles approximated by rects
        d.rect(x +  6, y,      26, 10, C_CLOUD, fill=True)
        d.rect(x,      y + 4,  38, 10, C_CLOUD, fill=True)
        d.rect(x +  4, y + 12, 30,  6, C_CLOUD, fill=True)
        # subtle shadow under
        d.rect(x +  6, y + 14, 26,  2, C_CLOUD_SH, fill=True)

    def draw_background(self, d):
        bg = _load("background")
        if not bg:
            return
        data, bw, bh = bg                # bw=80, bh=30 typically
        y = SH - GROUND_H - bh           # band sits just above the ground
        x0 = -int(self.offset * 0.4) % bw - bw
        x = x0
        while x < SW:
            d.blit(data, x, y, bw, bh)
            x += bw

    def draw_ground(self, d):
        # Solid ground band
        d.rect(0, SH - GROUND_H, SW, GROUND_H, C_GROUND, fill=True)
        gr = _load("grass")
        if not gr:
            return
        data, gw, gh = gr   # 80×10
        y = SH - GROUND_H
        x0 = -int(self.offset * 1.0) % gw - gw
        x = x0
        while x < SW:
            d.blit(data, x, y, gw, gh)
            x += gw

# ── App ──────────────────────────────────────────────────────────────────────

INTRO, PLAY, OVER = 1, 2, 3

class App(lix.App):

    def on_enter(self, os):
        self._os         = os
        self._scenery    = Scenery()
        self._panda      = None
        self._obstacles  = []
        self._spawn_left = 0.0     # seconds until next obstacle
        self._state      = INTRO
        self._hiscore    = _load_hiscore()
        self._new_hi     = False
        self._blink_t    = 0.0

    def on_button_press(self, btn):
        if btn != api.BTN_A and btn != api.BTN_UP:
            return
        if self._state == INTRO:
            self._start_play()
        elif self._state == PLAY:
            if self._panda and not self._panda.is_dead():
                self._panda.jump()
        elif self._state == OVER:
            self._state = INTRO

    def _start_play(self):
        self._state       = PLAY
        self._panda       = Panda()
        self._obstacles   = []
        self._new_hi      = False
        self._spawn_left  = 0.6        # first obstacle in 600 ms

    def update(self, dt):
        # cap any pathological dt so a hiccup doesn't teleport the panda
        if dt > 0.1: dt = 0.1
        self._scenery.update(dt)
        self._blink_t += dt

        if self._state == PLAY:
            self._panda.update(dt, self._obstacles)

            if not self._panda.is_dead():
                self._spawn_left -= dt
                if self._spawn_left <= 0:
                    self._obstacles.append(Obstacle())
                    self._spawn_left = SPAWN_SEC
                for o in self._obstacles:
                    o.update(dt)
                self._obstacles = [o for o in self._obstacles if o.x > -OBSTACLE_W]

            if self._panda.is_done_dying():
                # latch high score
                if self._panda.score > self._hiscore:
                    self._hiscore = self._panda.score
                    self._new_hi = True
                    _save_hiscore(self._hiscore)
                self._state = OVER

    def draw(self, d):
        # ── world ────────────────────────────────────────────────────────────
        self._scenery.draw_sky(d)
        self._scenery.draw_clouds(d)
        self._scenery.draw_background(d)

        for o in self._obstacles:
            o.draw(d)

        self._scenery.draw_ground(d)

        if self._panda:
            self._panda.draw(d)

        # ── HUD / overlays ───────────────────────────────────────────────────
        if self._state == INTRO:
            self._draw_intro(d)
        elif self._state == PLAY:
            self._draw_hud(d)
        elif self._state == OVER:
            self._draw_hud(d)
            self._draw_gameover(d)

    def _shadow_text(self, d, s, x, y, scale=1):
        font.text(d, s, x + 1, y + 1, C_SHADOW, scale=scale)
        font.text(d, s, x,     y,     C_TEXT,   scale=scale)

    def _center_text(self, d, s, y, scale=1, color=None):
        w = font.measure(s, scale)
        x = (SW - w) // 2
        if color is None:
            self._shadow_text(d, s, x, y, scale=scale)
        else:
            font.text(d, s, x + 1, y + 1, C_SHADOW, scale=scale)
            font.text(d, s, x, y, color, scale=scale)

    def _draw_intro(self, d):
        self._center_text(d, "FLAPPY PANDA", 50, scale=3, color=C_TITLE)
        if self._hiscore > 0:
            self._center_text(d, "HIGH SCORE %d" % self._hiscore, 95, scale=2, color=C_HI)
        if int(self._blink_t * 2) % 2 == 0:
            self._center_text(d, "Press A to start", 140, scale=2)
        self._center_text(d, "Tap A or UP to flap", 175, scale=1, color=C_DIM)

    def _draw_hud(self, d):
        s = "SCORE %d" % (self._panda.score if self._panda else 0)
        self._shadow_text(d, s, 6, 4, scale=2)

    def _draw_gameover(self, d):
        self._center_text(d, "GAME OVER", 50, scale=3, color=C_TITLE)
        sc = self._panda.score if self._panda else 0
        self._center_text(d, "Score %d" % sc, 95, scale=2)
        if self._new_hi:
            self._center_text(d, "NEW HIGH SCORE!", 120, scale=2, color=C_HI)
        else:
            self._center_text(d, "Best %d" % self._hiscore, 120, scale=2, color=C_HI)
        if int(self._blink_t * 2) % 2 == 0:
            self._center_text(d, "Press A to retry", 165, scale=2)

    def on_exit(self):
        pass

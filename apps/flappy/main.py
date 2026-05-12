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

# Sprite sizing — bumped from 24→32 so the panda reads better at landscape scale
PANDA_SZ    = 32
OBSTACLE_W  = 32
OBSTACLE_H  = 96      # one tile covers ~half the playable area in a single blit
GAP_H       = 100
PANDA_X     = 44

# The background fills the FULL screen. The "ground" is just the 16-px grass
# strip at the bottom — no separate dirt rectangle.
GROUND_H    = 16
PLAY_H      = SH - GROUND_H   # 224

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

_assets = {}   # name → (bytearray_data, w, h) or None

def _try_import(modname):
    try:
        return __import__(modname, None, None, ["DATA", "W", "H"])
    except (ImportError, AttributeError):
        return None

def _load(name):
    """Return (bytearray, W, H) for a sprite, or None.

    Converts the immutable bytes DATA into a bytearray once and caches it, so
    the per-frame Display.blit() can wrap it directly without copying.
    """
    if name in _assets:
        return _assets[name]
    mod = _try_import("apps.flappy.assets.optimized.%s" % name)
    if mod and hasattr(mod, "DATA"):
        ba = bytearray(mod.DATA)            # one-time bytes → bytearray copy
        result = (ba, mod.W, mod.H)
    else:
        result = None
    _assets[name] = result
    return result


def _upscale_to_bytearray(data, w, h, scale_x, scale_y):
    """Nearest-neighbour upscale `data` (big-endian RGB565 bytes) → bytearray.

    Used once at app init to pre-render the background and grass strip at
    full screen width. After this, drawing the scenery is a single fast blit.
    """
    sw = w * scale_x
    sh = h * scale_y
    out  = bytearray(sw * sh * 2)
    row  = bytearray(sw * 2)
    for src_row in range(h):
        for col in range(w):
            base_src = (src_row * w + col) * 2
            b1 = data[base_src]
            b0 = data[base_src + 1]
            base = col * scale_x * 2
            for dx in range(scale_x):
                row[base + dx * 2]     = b1
                row[base + dx * 2 + 1] = b0
        row_start = src_row * scale_y * sw * 2
        for dy in range(scale_y):
            s = row_start + dy * sw * 2
            out[s: s + sw * 2] = row
    return out, sw, sh


# ── _bluedim kernel ──────────────────────────────────────────────────────────
# On MicroPython the kernel is compiled with @micropython.viper for near-C
# speed (76,800 pixels in ~30-50 ms vs ~700 ms in pure Python). On CPython we
# fall back to a regular function — perf is irrelevant in the simulator.
#
# The viper source lives in a string so CPython never has to parse the `ptr8`
# annotation (which only exists inside Viper's namespace).

_BLUEDIM_VIPER_SRC = """
@micropython.viper
def _bluedim_kernel(src: ptr8, dst: ptr8, n: int):
    i = 0
    while i < n:
        off = i << 1
        v = (src[off] << 8) | src[off + 1]
        r = ((v >> 11) & 0x1F) * 7  >> 4   # ×0.44 darken
        g = ((v >>  5) & 0x3F) * 7  >> 4   # ×0.44 darken
        b = ( v        & 0x1F) * 11 >> 4   # ×0.69 keep blue warmer
        if r > 31: r = 31
        if g > 63: g = 63
        if b > 31: b = 31
        v2 = (r << 11) | (g << 5) | b
        dst[off]     = v2 >> 8
        dst[off + 1] = v2 & 0xFF
        i += 1
"""

def _bluedim_kernel(src, dst, n):
    """Pure-Python fallback (CPython simulator). Replaced by Viper on hardware."""
    for i in range(n):
        off = i << 1
        v = (src[off] << 8) | src[off + 1]
        r = ((v >> 11) & 0x1F) * 7  >> 4
        g = ((v >>  5) & 0x3F) * 7  >> 4
        b = ( v        & 0x1F) * 11 >> 4
        if r > 31: r = 31
        if g > 63: g = 63
        if b > 31: b = 31
        v2 = (r << 11) | (g << 5) | b
        dst[off]     = v2 >> 8
        dst[off + 1] = v2 & 0xFF

try:
    import micropython as _mp     # pragma: no cover (MicroPython only)
    if hasattr(_mp, "viper"):
        _ns = {"micropython": _mp}
        exec(_BLUEDIM_VIPER_SRC, _ns)
        _bluedim_kernel = _ns["_bluedim_kernel"]
except Exception:
    # Any failure (no Viper, Viper compile error, etc.) → keep the Python fallback.
    pass


def _bluedim_bytearray(buf):
    """Darkened cool-tone copy of an RGB565-big-endian bytearray.

    Each pixel becomes ~44% as bright in R/G and ~69% in B, producing a
    night-time tint that contrasts well with bright text. Built once at
    app init for the menu-screen background overlay.
    """
    out = bytearray(len(buf))
    _bluedim_kernel(buf, out, len(buf) // 2)
    return out

# ── LCG RNG ──────────────────────────────────────────────────────────────────

_seed = 12345
def _rand():
    global _seed
    _seed = (_seed * 1103515245 + 12345) & 0x7FFFFFFF
    return _seed

def _rand_gap_y(top_margin, bot_margin):
    lo = top_margin
    hi = PLAY_H - GAP_H - bot_margin
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
            data, ow, oh = obs   # 24 × OBSTACLE_H
            # Top column: anchor the bottom tile flush with the gap, extend upward.
            top_h = self.gap_y
            if top_h > 0:
                y = self.gap_y - oh                 # bottom of the top column
                # Anchored tile sits flush at the gap edge.
                d.blit(data, x, y, ow, oh)
                # Extend upward with extra tiles if the column is taller than one tile.
                y -= oh
                while y > -oh:
                    d.blit(data, x, y, ow, oh)
                    y -= oh

            # Bottom column: anchor top tile flush with the gap edge.
            bot_y0 = self.gap_y + GAP_H
            bot_h  = SH - GROUND_H - bot_y0
            if bot_h > 0:
                y = bot_y0
                while y < SH - GROUND_H:
                    d.blit(data, x, y, ow, oh)
                    y += oh
        else:
            d.rect(x, 0,                  OBSTACLE_W, self.gap_y,       api.GREEN, fill=True)
            d.rect(x, self.gap_y + GAP_H, OBSTACLE_W,
                   SH - GROUND_H - self.gap_y - GAP_H,                  api.GREEN, fill=True)

# ── panda ────────────────────────────────────────────────────────────────────

class Panda:
    def __init__(self):
        # start high so there's time to react
        self.y          = float((SH - GROUND_H) // 3)
        self.vy         = 0.0
        self.score      = 0
        self.died_at_s  = None     # seconds since die()
        self.alive_t    = 0.0      # accumulated alive seconds (anim phase)
        self.has_jumped = False    # gravity engages on first jump (hover before)

    def jump(self):
        if not self.is_dead():
            self.has_jumped = True
            self.vy = FLAP_VY

    def update(self, dt, obstacles):
        """dt is seconds."""
        if self.is_dead():
            self.died_at_s += dt
            return
        self.alive_t += dt
        if not self.has_jumped:
            # gentle bob while waiting for first input
            import math
            self.y = (SH - GROUND_H) / 3 + math.sin(self.alive_t * 4) * 4
            return
        self.vy = min(self.vy + GRAVITY * dt, VY_CAP)
        self.y += self.vy * dt
        # Ceiling
        if self.y < 0:
            self.y = 0.0
            self.vy = 0.0
        # Ground / floor — panda is PANDA_SZ tall, ground line is just above the grass strip
        if self.y + PANDA_SZ > SH - GROUND_H:
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
        # Slightly tighter than PANDA_SZ to make collisions feel fair
        pad = 4
        return (PANDA_X + pad, int(self.y) + pad,
                PANDA_SZ - pad * 2, PANDA_SZ - pad * 2)

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
            d.rect(PANDA_X, py, PANDA_SZ, PANDA_SZ, C_TITLE, fill=True)

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
    """Pre-rendered scenery — built ONCE in build(), drawn as 2 big blits/frame.

    background (80×60) → upscaled ×4×4 → 320×240 (FULL screen)
    grass      (80×16) → upscaled ×4×1 → 320×16  (bottom strip)

    A second 320×240 buffer holds a blue-dimmed version of the bg, drawn
    instead of the bright bg on intro/gameover so menu text reads clearly.
    No dirt rectangle is drawn — the bg image owns every pixel up to the
    grass strip; collisions still use the logical ground at SH - GROUND_H.
    """
    def __init__(self):
        self.offset       = 0.0
        self._bg_data     = None   # (bytearray, sw, sh)
        self._bg_dim_data = None
        self._gr_data     = None

    def build(self):
        bg = _load("background")
        if bg:
            data, bw, bh = bg
            sx = max(1, SW // bw)
            sy = max(1, SH // bh)                        # cover FULL screen
            self._bg_data     = _upscale_to_bytearray(data, bw, bh, sx, sy)
            self._bg_dim_data = (
                _bluedim_bytearray(self._bg_data[0]),
                self._bg_data[1], self._bg_data[2]
            )

        gr = _load("grass")
        if gr:
            data, gw, gh = gr
            sx = max(1, SW // gw)
            self._gr_data = _upscale_to_bytearray(data, gw, gh, sx, 1)

    def update(self, dt):
        self.offset += SCROLL * dt * 0.5

    def draw_background(self, d, dim=False):
        bg = self._bg_dim_data if dim else self._bg_data
        if bg:
            buf, sw, sh = bg
            d.blit(buf, 0, 0, sw, sh)
        else:
            d.rect(0, 0, SW, SH, C_SKY if not dim else api.rgb(20, 30, 60), fill=True)

    def draw_clouds(self, d):
        # The bg asset paints its own sky+clouds; skip the procedural overlay
        # when we have a real background.
        if self._bg_data is not None:
            return
        base = int(-(self.offset * 0.25) % (SW + 80))
        for px, py in ((0, 30), (110, 22), (220, 38)):
            cx = ((px - base) % (SW + 80)) - 40
            d.rect(cx +  6, py,      26, 10, C_CLOUD, fill=True)
            d.rect(cx,      py + 4,  38, 10, C_CLOUD, fill=True)
            d.rect(cx +  4, py + 12, 30,  6, C_CLOUD, fill=True)
            d.rect(cx +  6, py + 14, 26,  2, C_CLOUD_SH, fill=True)

    def draw_ground(self, d):
        # No dirt rectangle — bg already shows the ground area.
        # Just overlay the scrolling grass strip flush with the bottom.
        if self._gr_data:
            buf, gw, gh = self._gr_data
            d.blit(buf, 0, SH - gh, gw, gh)

# ── App ──────────────────────────────────────────────────────────────────────

INTRO, PLAY, OVER = 1, 2, 3

class App(lix.App):

    def on_enter(self, os):
        self._os         = os
        self._scenery    = Scenery()
        self._scenery.build()       # one-time upscale of bg + grass (~150 ms total)
        self._panda      = None
        self._obstacles  = []
        self._spawn_left = 0.0
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
        # On menu screens we dim the bg so the title/score/hint text reads brightly.
        dim = self._state in (INTRO, OVER)
        self._scenery.draw_background(d, dim=dim)
        self._scenery.draw_clouds(d)

        # While playing we still show obstacles + panda animating in the foreground;
        # on the game-over screen we keep them visible so the player sees what hit them.
        if self._state in (PLAY, OVER):
            for o in self._obstacles:
                o.draw(d)

        self._scenery.draw_ground(d)

        if self._panda and self._state in (PLAY, OVER):
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

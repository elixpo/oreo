"""Flappy Panda — Elixpo badge game.

Display: 240×320 portrait. Game area: y=24..296 (272px tall).
Header: score / hi-score. Footer: tiny hint on title screen.

Panda sprite: 14×12 px pixel-art, drawn with d.rect() — no image load needed.
Pipes: chunky teal rectangles, gap of 72px, scroll left at 60px/s.
Physics: gravity 350px/s², flap impulse −140px/s. Terminal velocity 220px/s.

Controls: A or UP = flap. Any button on title/game-over = start / restart.
"""

import lix
from lix import api

# ── geometry ─────────────────────────────────────────────────────────────────

SW      = api.SCREEN_W   # 240
SH      = api.SCREEN_H   # 320
HEADER  = 24
FOOTER  = 24
TOP     = HEADER
BOTTOM  = SH - FOOTER    # 296
PLAY_H  = BOTTOM - TOP   # 272

# ── colours ──────────────────────────────────────────────────────────────────

C_BG      = api.rgb(8,   8,  20)
C_SKY     = api.rgb(14,  14, 38)
C_PIPE    = api.rgb(0,  180, 160)
C_PIPE_LT = api.rgb(0,  220, 200)
C_GROUND  = api.rgb(30,  30,  55)
C_HEAD    = api.rgb(0,  220, 200)
C_SCORE   = api.WHITE
C_TITLE   = api.rgb(0,  220, 200)
C_OVER    = api.rgb(255,  60, 100)
C_HINT    = api.rgb(90,  90, 130)
C_STAR    = api.rgb(60,  60, 100)

# panda palette
P_FUR    = api.rgb(200, 204, 203)
P_DARK   = api.rgb(38,  38,  48)
P_CHEEK  = api.rgb(255,  93, 104)
P_SHINE  = api.WHITE
P_YELLOW = api.rgb(255, 200,  40)  # propeller / plane

# ── physics ──────────────────────────────────────────────────────────────────

GRAVITY   = 350   # px/s²  (applied each second)
FLAP_VY   = -145  # px/s   (upward impulse)
VY_CAP    =  220  # px/s   (terminal falling speed)
PIPE_SPEED =  70  # px/s   scroll speed
GAP        =  72  # px     pipe opening height
PIPE_W     =  28  # px     pipe width
SPAWN_DIST = 120  # px     horizontal distance between pipes

# ── panda sprite (14×12 pixels) ──────────────────────────────────────────────
# Each row is a list of (dx, dy, w, h, color) rects relative to sprite origin.
# Origin = top-left of bounding box.

PW = 14   # sprite width
PH = 12   # sprite height

def _draw_panda(d, px, py, angle_deg=0):
    """Draw the pixel-art panda at (px, py).

    angle_deg > 0 = nose-down (just shifts the eye row down 1px for a tilt hint).
    """
    tilt = 1 if angle_deg > 15 else 0

    # body (fur)
    d.rect(px + 2, py + 3, 10, 8, P_FUR,  fill=True)
    # head
    d.rect(px + 2, py,     10, 6, P_FUR,  fill=True)
    # ears
    d.rect(px + 2, py,      2, 2, P_DARK, fill=True)
    d.rect(px + 10, py,     2, 2, P_DARK, fill=True)
    # eye patches
    d.rect(px + 3, py + 2 + tilt, 2, 2, P_DARK, fill=True)
    d.rect(px + 9, py + 2 + tilt, 2, 2, P_DARK, fill=True)
    # eyes (shine)
    d.rect(px + 4, py + 2 + tilt, 1, 1, P_SHINE, fill=True)
    d.rect(px + 10, py + 2 + tilt, 1, 1, P_SHINE, fill=True)
    # nose
    d.rect(px + 6, py + 4 + tilt, 2, 1, P_DARK, fill=True)
    # cheek blush
    d.rect(px + 3, py + 5, 2, 1, P_CHEEK, fill=True)
    d.rect(px + 9, py + 5, 2, 1, P_CHEEK, fill=True)
    # tiny propeller above head
    d.rect(px + 5, py - 3, 4, 1, P_YELLOW, fill=True)
    d.rect(px + 6, py - 3, 1, 3, P_DARK,   fill=True)


def _draw_pipe(d, x, gap_y):
    """Draw a pair of pipes centred on gap_y with GAP opening."""
    top_h    = gap_y - GAP // 2 - TOP
    bot_y    = gap_y + GAP // 2
    bot_h    = BOTTOM - bot_y

    if top_h > 0:
        d.rect(x, TOP,   PIPE_W, top_h, C_PIPE,    fill=True)
        d.rect(x, TOP + top_h - 4, PIPE_W, 4, C_PIPE_LT, fill=True)  # cap

    if bot_h > 0:
        d.rect(x, bot_y,  PIPE_W, 4,     C_PIPE_LT, fill=True)  # cap
        d.rect(x, bot_y + 4, PIPE_W, bot_h - 4, C_PIPE, fill=True)


# ── LCG RNG (no random module on MicroPython) ─────────────────────────────────

_seed = 42

def _lcg():
    global _seed
    _seed = (_seed * 1103515245 + 12345) & 0x7FFFFFFF
    return _seed

def _rand_gap_y():
    margin = 40
    lo = TOP + GAP // 2 + margin
    hi = BOTTOM - GAP // 2 - margin
    return lo + _lcg() % max(1, hi - lo)


# ── App ───────────────────────────────────────────────────────────────────────

# ── sprite loader ────────────────────────────────────────────────────────────

_sprites = {}   # "up" | "down" → (data, w, h) or None

def _load_sprite(key, filename):
    if key in _sprites:
        return _sprites[key]
    result = None
    try:
        from lix_os.icons import _png_to_rgb565
        data = _png_to_rgb565("asset/icons/%s" % filename, size=32)
        if data:
            result = (data, 32, 32)
    except Exception:
        pass
    _sprites[key] = result
    return result


# ── App ───────────────────────────────────────────────────────────────────────

class App(lix.App):

    def on_enter(self, os):
        self._os = os
        # pre-load sprites if generated
        _load_sprite("up",   "flappy_panda_up.png")
        _load_sprite("down", "flappy_panda_down.png")
        self._state   = "title"   # "title" | "play" | "over"
        self._score   = 0
        self._hiscore = 0
        self._panda_y = float(TOP + PLAY_H // 2 - PH // 2)
        self._vy      = 0.0
        self._pipes   = []   # list of [x, gap_y, scored]
        self._frame   = 0
        self._stars   = [((_lcg() % SW), TOP + (_lcg() % PLAY_H)) for _ in range(20)]

    def _reset(self):
        self._state   = "play"
        self._score   = 0
        self._panda_y = float(TOP + PLAY_H // 3)
        self._vy      = 0.0
        self._pipes   = []
        self._frame   = 0
        # seed first pipe off-screen right
        self._pipes.append([SW + 20, _rand_gap_y(), False])

    def update(self, dt):
        btn = self._os.buttons
        pressed_any = btn.just_pressed(api.BTN_A) or btn.just_pressed(api.BTN_UP)

        if self._state == "title":
            if pressed_any:
                self._reset()
            return

        if self._state == "over":
            if pressed_any:
                self._reset()
            return

        # ── playing ──────────────────────────────────────────────────────────
        self._frame += 1

        if pressed_any:
            self._vy = FLAP_VY

        # physics
        self._vy = min(self._vy + GRAVITY * dt, VY_CAP)
        self._panda_y += self._vy * dt

        py_int = int(self._panda_y)

        # ceiling / floor
        if py_int <= TOP or py_int + PH >= BOTTOM:
            self._die()
            return

        # scroll pipes
        dx = PIPE_SPEED * dt
        surviving = []
        for pipe in self._pipes:
            pipe[0] -= dx
            # score when panda passes pipe centre
            if not pipe[2] and pipe[0] + PIPE_W < SW // 4:
                pipe[2] = True
                self._score += 1
                if self._score > self._hiscore:
                    self._hiscore = self._score
            if pipe[0] + PIPE_W > -4:
                surviving.append(pipe)
        self._pipes = surviving

        # spawn new pipe
        if not self._pipes or self._pipes[-1][0] < SW - SPAWN_DIST:
            self._pipes.append([SW + 4, _rand_gap_y(), False])

        # collision
        px = SW // 4
        for pipe in self._pipes:
            if px + PW - 2 > pipe[0] and px < pipe[0] + PIPE_W:
                top_h = pipe[1] - GAP // 2 - TOP
                bot_y = pipe[1] + GAP // 2
                if py_int < TOP + top_h or py_int + PH > bot_y:
                    self._die()
                    return

    def _die(self):
        self._state = "over"

    def draw(self, d):
        d.clear(C_BG)

        # starfield
        for sx, sy in self._stars:
            d.rect(sx, sy, 1, 1, C_STAR, fill=True)

        # ground bar
        d.rect(0, BOTTOM, SW, FOOTER, C_GROUND, fill=True)

        # header bar
        d.rect(0, 0, SW, HEADER, api.rgb(10, 10, 24), fill=True)
        d.text("FLAPPY", 4, 4, C_TITLE)
        sc_str = "%d" % self._score
        d.text(sc_str, SW - len(sc_str) * 8 - 4, 4, C_SCORE)

        # pipes
        for pipe in self._pipes:
            _draw_pipe(d, int(pipe[0]), pipe[1])

        # panda — use PNG sprite if generated, else pixel rects
        py_int  = int(self._panda_y)
        tilt_vy = self._vy if self._state == "play" else 0
        sprite_key = "down" if tilt_vy > 60 else "up"
        sprite = _sprites.get(sprite_key)
        if sprite:
            sdata, sw_s, sh_s = sprite
            d.blit(sdata, SW // 4 - (sw_s - PW) // 2, py_int - (sh_s - PH) // 2, sw_s, sh_s)
        else:
            _draw_panda(d, SW // 4, py_int, angle_deg=tilt_vy)

        if self._state == "title":
            d.rect(40, 120, 160, 70, api.rgb(14, 14, 32), fill=True)
            d.rect(40, 120, 160, 2,  C_TITLE, fill=True)
            d.text("FLAPPY",  72, 130, C_TITLE, scale=2)
            d.text("PANDA",   80, 152, C_TITLE, scale=2)
            d.text("Press A to start", 48, 178, C_HINT)

        elif self._state == "over":
            d.rect(30, 130, 180, 56, api.rgb(18, 8, 14), fill=True)
            d.rect(30, 130, 180, 2,  C_OVER, fill=True)
            d.text("GAME OVER", 54, 138, C_OVER, scale=2)
            hs = "HI %d" % self._hiscore
            d.text(hs, (SW - len(hs) * 8) // 2, 162, C_SCORE)
            d.text("Press A to retry", 44, 178, C_HINT)

    def on_exit(self):
        pass

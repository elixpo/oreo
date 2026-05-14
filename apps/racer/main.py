"""Racer - panda kart, tilt-to-steer with the MPU6050.

How to play:
  * Hold the badge HORIZONTAL (screen facing up, +Y of the IMU pointing
    toward the top of the screen).
  * ROLL the badge left/right -> car steers left/right.
  * PITCH the badge forward (top edge down) -> accelerate AWAY from you.
  * PITCH the badge back   (top edge up)   -> brake / slow down.

Visual style follows Flappy: live game world keeps animating in the
background, with a dim scan-line overlay + shadow text on top for
INTRO and GAME OVER states. No opaque cards.

Three states:
    INTRO   - title, blink "Press A to start", world still scrolling behind
    PLAY    - obstacles scroll down (toward player), dodge them
    OVER    - crash visible, world dimmed, "Press A to retry"

Assets used (drop into apps/racer/assets/raw/, run:
  python tools/optimize_assets.py --app racer):
    racer_player.py        - 32x40 panda kart
    racer_player_crash.py  - 32x40 crashed-panda variant
    racer_enemy_a.py       - 32x40 oncoming car variant A
    racer_enemy_b.py       - 32x40 oncoming car variant B
    racer_tree.py          - 24x32 tree sprite for the verges
    racer_road.py          - 80x80 tarmac tile (with centre stripe)

If a sprite is missing, the game falls back to coloured rectangles so the
mechanics are playable even before the asset pipeline has run.

Hi-score persists in apps/racer/hi.txt.
"""

import oreoOS
from oreoOS import api


SW = api.SCREEN_W       # 320
SH = api.SCREEN_H       # 240

INTRO, PLAY, OVER = 1, 2, 3

# ── game tuning ──────────────────────────────────────────────────────────────
ROAD_W       = 200                      # rendered road width
ROAD_X       = (SW - ROAD_W) // 2
PLAY_TOP     = 0                        # full-screen for the Flappy look
PLAY_BOT     = SH
PLAY_H       = PLAY_BOT - PLAY_TOP

CAR_W, CAR_H = 32, 40
PLAYER_Y     = PLAY_BOT - CAR_H - 18

ENEMY_W, ENEMY_H = 32, 40
ENEMY_LANES  = (ROAD_X + 28, ROAD_X + ROAD_W // 2 - ENEMY_W // 2, ROAD_X + ROAD_W - ENEMY_W - 28)

MAX_STEER_PX_PER_S   = 220.0
ROAD_SCROLL_MIN      = 30.0
ROAD_SCROLL_MAX      = 220.0
ENEMY_SPAWN_SEC0     = 1.6
ENEMY_SPAWN_FLOOR    = 0.55

ROLL_DEADZONE_DEG    = 4.0
ROLL_SATURATION_DEG  = 30.0
PITCH_DEADZONE_DEG   = 5.0
PITCH_SATURATION_DEG = 25.0

# Flappy-derived palette — warm, bright, with consistent shadow colour.
C_GRASS      = api.rgb( 40, 110,  50)
C_ROAD       = api.rgb( 64,  64,  72)
C_DASH       = api.WHITE
C_TITLE      = api.rgb(255,  93, 104)   # pink
C_HI         = api.rgb(255, 230,  80)   # gold
C_TEXT       = api.WHITE
C_DIM        = api.rgb(200, 180, 160)
C_SHADOW     = api.rgb( 20,  30,  45)

HI_PATH = "apps/racer/hi.txt"


def _load_hi():
    try:
        with open(HI_PATH) as f:
            return int(f.read().strip() or "0")
    except Exception:
        return 0


def _save_hi(v):
    try:
        with open(HI_PATH, "w") as f:
            f.write(str(int(v)))
    except Exception:
        pass


def _try_sprite(name):
    try:
        m = __import__("apps.racer.assets.optimized." + name, None, None,
                       ["DATA", "W", "H"])
        return (bytearray(m.DATA), m.W, m.H)
    except (ImportError, AttributeError):
        return None


def _clamp(v, lo, hi):
    if v < lo: return lo
    if v > hi: return hi
    return v


def _norm_input(value, deadzone, saturation):
    """Signed angle (deg) -> -1..+1 with a dead-zone + saturation curve."""
    av = value if value >= 0 else -value
    if av < deadzone:
        return 0.0
    span = saturation - deadzone
    if span <= 0:
        return 1.0 if value > 0 else -1.0
    s = (av - deadzone) / span
    if s > 1.0:
        s = 1.0
    return s if value > 0 else -s


class _Enemy:
    __slots__ = ("x", "y", "spr")
    def __init__(self, x, y, spr):
        self.x, self.y, self.spr = x, y, spr


class App(oreoOS.App):
    name         = "Racer"
    SHOW_LOADING = True
    BLOCK_IDLE   = True

    def on_enter(self, os):
        self._os    = os
        self._state = INTRO
        self._hi    = _load_hi()
        self._new_hi = False
        self._blink  = 0.0
        self._dirty  = True

        self._spr_player  = _try_sprite("racer_player")
        self._spr_crash   = _try_sprite("racer_player_crash")
        self._spr_enemy_a = _try_sprite("racer_enemy_a")
        self._spr_enemy_b = _try_sprite("racer_enemy_b")
        self._spr_tree    = _try_sprite("racer_tree")
        self._spr_road    = _try_sprite("racer_road")

        self._imu = None
        try:
            from oreoWare import imu
            self._imu = imu.MPU6050()
            self._imu.calibrate(samples=80)
        except Exception:
            self._imu = None

        # Control mode: "IMU" (tilt) or "BTN" (D-pad). Persisted across
        # boots via the OS settings dict; falls back to BTN when no IMU
        # is detected so the game stays playable on a bare board.
        saved = os.settings_get("racer_mode", None)
        if saved in ("IMU", "BTN"):
            self._mode = saved
        else:
            self._mode = "IMU" if self._imu else "BTN"
        # Smoothed digital-input axes for BTN mode (lerp toward the held
        # state so tap-tap doesn't snap the car instantly).
        self._btn_steer    = 0.0
        self._btn_throttle = 0.0

        self._reset_run()

    def _save_mode(self):
        try:
            self._os.settings_set("racer_mode", self._mode)
        except Exception:
            pass

    def _reset_run(self):
        self._player_x   = ROAD_X + (ROAD_W - CAR_W) // 2
        self._enemies    = []
        self._spawn_left = ENEMY_SPAWN_SEC0
        self._spawn_int  = ENEMY_SPAWN_SEC0
        self._scroll_y   = 0.0
        self._scroll_v   = ROAD_SCROLL_MIN
        self._score      = 0
        self._tree_t     = 0.0
        self._dirty      = True

    # ── input ───────────────────────────────────────────────────────────
    def on_button_press(self, btn):
        if btn == api.BTN_A:
            if self._state == INTRO:
                self._state = PLAY
                self._reset_run()
            elif self._state == OVER:
                self._state = INTRO
            self._dirty = True
        elif btn == api.BTN_B and self._state in (INTRO, OVER):
            # Toggle control mode from the menus. Don't allow mid-race so the
            # user can't switch sources of input while a car is in motion.
            self._mode = "BTN" if self._mode == "IMU" else "IMU"
            self._save_mode()
            self._dirty = True

    def _read_inputs(self, dt):
        """Return (steer, throttle) each in -1..+1, per the active mode.

        IMU mode reads roll for steering and pitch for throttle.
        BTN mode lerps a digital axis toward the held button state so taps
        feel smooth (rather than instant teleport-style).
        """
        if self._mode == "IMU" and self._imu:
            try:
                pitch, roll = self._imu.tilt_deg()
                return (
                    _norm_input(roll,  ROLL_DEADZONE_DEG,  ROLL_SATURATION_DEG),
                    _norm_input(pitch, PITCH_DEADZONE_DEG, PITCH_SATURATION_DEG),
                )
            except Exception:
                pass

        # BTN mode (or IMU fallback when the sensor errored out).
        b = self._os.buttons
        try:
            left  = b.is_pressed(api.BTN_LEFT)
            right = b.is_pressed(api.BTN_RIGHT)
            up    = b.is_pressed(api.BTN_UP)
            down  = b.is_pressed(api.BTN_DOWN)
        except Exception:
            left = right = up = down = False

        tgt_steer    = (1.0 if right else 0.0) - (1.0 if left else 0.0)
        tgt_throttle = (1.0 if up    else 0.0) - (1.0 if down else 0.0)
        # Lerp toward target — 8/s = roll-on in ~125 ms when held, decay
        # back to 0 in the same time when released.
        lerp = min(1.0, dt * 8.0)
        self._btn_steer    += (tgt_steer    - self._btn_steer)    * lerp
        self._btn_throttle += (tgt_throttle - self._btn_throttle) * lerp
        return self._btn_steer, self._btn_throttle

    def update(self, dt):
        self._blink += dt

        steer, throttle = self._read_inputs(dt)

        if self._state == PLAY:
            self._player_x += steer * MAX_STEER_PX_PER_S * dt
            self._player_x  = _clamp(self._player_x,
                                     ROAD_X + 4,
                                     ROAD_X + ROAD_W - CAR_W - 4)

            target = ROAD_SCROLL_MIN + (
                ROAD_SCROLL_MAX - ROAD_SCROLL_MIN) * max(0.0, throttle)
            if throttle < -0.2:
                target = ROAD_SCROLL_MIN * 0.3
            self._scroll_v += (target - self._scroll_v) * min(1.0, dt * 4)

            self._scroll_y += self._scroll_v * dt
            self._tree_t   += self._scroll_v * dt

            self._spawn_left -= dt
            if self._spawn_left <= 0:
                self._spawn_int = max(
                    ENEMY_SPAWN_FLOOR,
                    ENEMY_SPAWN_SEC0 - self._score * 0.01)
                self._spawn_left = self._spawn_int
                lane = ENEMY_LANES[int(self._blink * 31) % 3]
                spr  = self._spr_enemy_a if int(self._blink * 17) & 1 else self._spr_enemy_b
                self._enemies.append(_Enemy(lane, PLAY_TOP - ENEMY_H, spr))

            new_enemies = []
            for e in self._enemies:
                e.y += self._scroll_v * dt
                if e.y > PLAY_BOT:
                    self._score += 1
                    continue
                if (abs((e.x + ENEMY_W // 2) - (self._player_x + CAR_W // 2))
                        < (CAR_W + ENEMY_W) // 2 - 6
                    and abs((e.y + ENEMY_H // 2) - (PLAYER_Y + CAR_H // 2))
                        < (CAR_H + ENEMY_H) // 2 - 6):
                    self._on_crash()
                    return
                new_enemies.append(e)
            self._enemies = new_enemies

            self._dirty = True

        elif self._state in (INTRO, OVER):
            # Keep the world animating behind the menus — Flappy style.
            self._scroll_v += (40.0 - self._scroll_v) * min(1.0, dt * 2)
            self._scroll_y += self._scroll_v * dt
            self._tree_t   += self._scroll_v * dt
            self._dirty     = True

    def _on_crash(self):
        if self._score > self._hi:
            self._hi     = self._score
            self._new_hi = True
            _save_hi(self._hi)
        else:
            self._new_hi = False
        self._state = OVER
        self._dirty = True

    # ── render ──────────────────────────────────────────────────────────
    def draw(self, d):
        if not self._dirty:
            return
        self._dirty = False

        self._draw_world(d)
        self._draw_enemies(d)
        self._draw_player(
            d,
            sprite=(self._spr_crash if self._state == OVER else self._spr_player))

        if self._state == PLAY:
            self._draw_hud(d)
        else:
            self._dim_world(d)
            if self._state == INTRO:
                self._draw_intro(d)
            else:
                self._draw_over(d)

    # ── world (road + trees scroll DOWN toward the player) ───────────────
    def _draw_world(self, d):
        d.clear(C_GRASS)

        # Road tiles: as scroll_y grows, the tile pattern slides DOWN. The
        # first tile starts slightly ABOVE the visible area; the modulo
        # offset pushes it INTO view as scroll grows — creates the illusion
        # the player is accelerating AWAY from the camera.
        if self._spr_road:
            data, rw, rh = self._spr_road
            y0 = PLAY_TOP + (int(self._scroll_y) % rh) - rh
            y  = y0
            while y < PLAY_BOT:
                x = ROAD_X
                while x < ROAD_X + ROAD_W:
                    d.blit(data, x, y, rw, rh)
                    x += rw
                y += rh
        else:
            d.rect(ROAD_X, PLAY_TOP, ROAD_W, PLAY_H, C_ROAD, fill=True)
            dash_h = 24
            gap    = 16
            step   = dash_h + gap
            y0     = PLAY_TOP + (int(self._scroll_y) % step) - step
            cx     = ROAD_X + ROAD_W // 2 - 2
            y      = y0
            while y < PLAY_BOT:
                yy = max(PLAY_TOP, y)
                hh = min(dash_h, PLAY_BOT - yy)
                if hh > 0:
                    d.rect(cx, yy, 4, hh, C_DASH, fill=True)
                y += step

        # Verge trees - same scroll math, so trees + road move together.
        if self._spr_tree:
            data, tw, th = self._spr_tree
            step = th + 24
            y0   = PLAY_TOP + (int(self._tree_t) % step) - step
            y    = y0
            while y < PLAY_BOT:
                if y + th > PLAY_TOP:
                    d.blit(data, ROAD_X - tw - 2,         y, tw, th)
                    d.blit(data, ROAD_X + ROAD_W + 2,     y, tw, th)
                y += step

    def _draw_enemies(self, d):
        for e in self._enemies:
            if e.spr:
                data, w, h = e.spr
                d.blit(data, int(e.x), int(e.y), w, h)
            else:
                d.rect(int(e.x), int(e.y), ENEMY_W, ENEMY_H, C_TITLE, fill=True)

    def _draw_player(self, d, sprite=None):
        if sprite:
            data, w, h = sprite
            d.blit(data, int(self._player_x), PLAYER_Y, w, h)
        else:
            d.rect(int(self._player_x), PLAYER_Y, CAR_W, CAR_H, C_HI, fill=True)

    def _draw_hud(self, d):
        # Score top-right with a 1-px shadow, no opaque box.
        s = "%d" % self._score
        self._shadow_text(d, s, SW - len(s) * 16 - 6, 6, C_TEXT, scale=2)
        # Thin speed bar bottom-left.
        bar_w = 60
        d.rect(8, SH - 12, bar_w, 4, C_SHADOW, fill=True)
        v_pct = (self._scroll_v - ROAD_SCROLL_MIN) / max(
            1.0, ROAD_SCROLL_MAX - ROAD_SCROLL_MIN)
        d.rect(8, SH - 12, int(bar_w * v_pct), 4, C_HI, fill=True)

    # ── overlay helpers (scan-line dim + shadow text) ────────────────────
    def _dim_world(self, d):
        for y in range(PLAY_TOP, PLAY_BOT, 2):
            d.rect(0, y, SW, 1, api.rgb(0, 0, 0), fill=True)

    def _shadow_text(self, d, s, x, y, color, scale=1):
        d.text(s, x + 1, y + 1, C_SHADOW, scale=scale)
        d.text(s, x,     y,     color,    scale=scale)

    def _center_text(self, d, s, y, color, scale=1):
        w = len(s) * 8 * scale
        self._shadow_text(d, s, (SW - w) // 2, y, color, scale)

    # ── menus ────────────────────────────────────────────────────────────
    def _draw_intro(self, d):
        self._center_text(d, "PANDA RACER", 40, C_TITLE, scale=3)
        if self._hi:
            self._center_text(d, "HIGH %d" % self._hi, 90, C_HI, scale=2)
        if not self._imu:
            self._center_text(d, "no IMU - sensor offline", 120, C_TITLE, scale=1)
        if int(self._blink * 2) % 2 == 0:
            self._center_text(d, "Press A to start", 140, C_TEXT, scale=2)
        self._center_text(d, "tilt to steer + throttle", 180, C_DIM, scale=1)
        self._center_text(d, "HOME = back",              200, C_DIM, scale=1)

    def _draw_over(self, d):
        self._center_text(d, "GAME OVER", 40, C_TITLE, scale=3)
        self._center_text(d, "Score %d" % self._score, 90, C_TEXT, scale=2)
        if self._new_hi:
            self._center_text(d, "NEW HIGH!", 120, C_HI, scale=2)
        else:
            self._center_text(d, "Best %d" % self._hi, 120, C_HI, scale=2)
        if int(self._blink * 2) % 2 == 0:
            self._center_text(d, "Press A to retry", 160, C_TEXT, scale=2)
        self._center_text(d, "HOME = back", 200, C_DIM, scale=1)

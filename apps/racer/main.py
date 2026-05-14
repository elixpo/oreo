"""Racer - panda kart, tilt-to-steer with the MPU6050.

How to play:
  * Hold the badge HORIZONTAL (screen facing up, +Y of the IMU pointing
    toward the top of the screen).
  * ROLL the badge left/right -> car steers left/right.
  * PITCH the badge forward (top edge down) -> accelerate.
  * PITCH the badge back   (top edge up)   -> brake / slow down.

The user said "yaw=steer, pitch=throttle" - we approximate yaw with the
ROLL accel reading because in a horizontal-card grip a wrist-twist looks
identical to a roll from the accelerometer's point of view, and using
the gyro for steering accumulates drift over a multi-minute play session.

Three states:
    INTRO   - title, blink "tilt to start"
    PLAY    - obstacles scroll down, dodge them
    OVER    - crash card, "press A to retry"

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

import time
import oreoOS
from oreoOS import api, theme, widgets


SW = api.SCREEN_W       # 320
SH = api.SCREEN_H       # 240

INTRO, PLAY, OVER = 1, 2, 3

# ── game tuning ──────────────────────────────────────────────────────────────
ROAD_W       = 200                      # rendered road width
ROAD_X       = (SW - ROAD_W) // 2
PLAY_TOP     = widgets.HEADER_H
PLAY_BOT     = SH - widgets.HINT_H
PLAY_H       = PLAY_BOT - PLAY_TOP

CAR_W, CAR_H = 32, 40
PLAYER_Y     = PLAY_BOT - CAR_H - 12

ENEMY_W, ENEMY_H = 32, 40
ENEMY_LANES  = (ROAD_X + 28, ROAD_X + ROAD_W // 2 - ENEMY_W // 2, ROAD_X + ROAD_W - ENEMY_W - 28)

MAX_STEER_PX_PER_S   = 220.0    # max horizontal speed of the player car
ROAD_SCROLL_MIN      = 30.0     # px/s — minimum forward speed
ROAD_SCROLL_MAX      = 220.0    # px/s — flat-out, pitched forward
ENEMY_SPAWN_SEC0     = 1.6      # first enemy interval; tightens with score
ENEMY_SPAWN_FLOOR    = 0.55

# Tilt mapping. roll -> steering, pitch -> throttle.
#  - dead-zone around 0 so the car doesn't drift on a flat hand
#  - clamp far past the saturation point so a steep tilt = full input
ROLL_DEADZONE_DEG    = 4.0
ROLL_SATURATION_DEG  = 30.0
PITCH_DEADZONE_DEG   = 5.0
PITCH_SATURATION_DEG = 25.0

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
    """Map a signed angle (deg) onto -1..+1 with a dead-zone."""
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
    """Oncoming car. Spawns at the top, scrolls down with the road."""
    __slots__ = ("x", "y", "spr")

    def __init__(self, x, y, spr):
        self.x = x
        self.y = y
        self.spr = spr


class App(oreoOS.App):
    name         = "Racer"
    SHOW_LOADING = True
    # When the racer is foregrounded we want the OS to NOT idle-sleep —
    # the user is actively driving even though no buttons are pressed.
    BLOCK_IDLE   = True

    def on_enter(self, os):
        self._os    = os
        self._state = INTRO
        self._hi    = _load_hi()
        self._new_hi = False
        self._blink  = 0.0
        self._dirty  = True

        # Sprite cache (loaded once, fall back to flat rects if missing)
        self._spr_player  = _try_sprite("racer_player")
        self._spr_crash   = _try_sprite("racer_player_crash")
        self._spr_enemy_a = _try_sprite("racer_enemy_a")
        self._spr_enemy_b = _try_sprite("racer_enemy_b")
        self._spr_tree    = _try_sprite("racer_tree")
        self._spr_road    = _try_sprite("racer_road")

        # IMU.  We deliberately catch ANY error so the game can still
        # render in the simulator / on a board without the IMU wired.
        self._imu = None
        try:
            from oreoWare import imu
            self._imu = imu.MPU6050()
            self._imu.calibrate(samples=80)   # ~0.4 s blocking on entry
        except Exception:
            self._imu = None

        self._reset_run()

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

    def update(self, dt):
        self._blink += dt

        steer = throttle = 0.0
        if self._imu:
            try:
                pitch, roll = self._imu.tilt_deg()
                steer    = _norm_input(roll,  ROLL_DEADZONE_DEG,  ROLL_SATURATION_DEG)
                throttle = _norm_input(pitch, PITCH_DEADZONE_DEG, PITCH_SATURATION_DEG)
            except Exception:
                steer = throttle = 0.0

        if self._state == PLAY:
            # ── player car ──────────────────────────────────────────────
            self._player_x += steer * MAX_STEER_PX_PER_S * dt
            self._player_x  = _clamp(self._player_x,
                                     ROAD_X + 4,
                                     ROAD_X + ROAD_W - CAR_W - 4)

            # Throttle: +1 = full speed, -1 = full brake.  Brake decays to 0
            # speed rather than going negative — no reverse.
            target = ROAD_SCROLL_MIN + (
                ROAD_SCROLL_MAX - ROAD_SCROLL_MIN) * max(0.0, throttle)
            # If user is braking, target the minimum
            if throttle < -0.2:
                target = ROAD_SCROLL_MIN * 0.3
            # Smooth approach so it doesn't feel jerky
            self._scroll_v += (target - self._scroll_v) * min(1.0, dt * 4)

            self._scroll_y += self._scroll_v * dt
            self._tree_t   += self._scroll_v * dt

            # ── enemy spawning ──────────────────────────────────────────
            self._spawn_left -= dt
            if self._spawn_left <= 0:
                # tighten interval as score climbs
                self._spawn_int = max(
                    ENEMY_SPAWN_FLOOR,
                    ENEMY_SPAWN_SEC0 - self._score * 0.01)
                self._spawn_left = self._spawn_int
                # pick a random lane + sprite
                lane = ENEMY_LANES[int(self._blink * 31) % 3]
                spr  = self._spr_enemy_a if int(self._blink * 17) & 1 else self._spr_enemy_b
                self._enemies.append(_Enemy(lane, PLAY_TOP - ENEMY_H, spr))

            # ── enemy movement + collision ──────────────────────────────
            new_enemies = []
            for e in self._enemies:
                e.y += self._scroll_v * dt
                if e.y > PLAY_BOT:
                    self._score += 1
                    continue
                # AABB collision
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
            # animate the trees scrolling in background so the screen
            # isn't static while the user reads the title
            self._tree_t += 30.0 * dt
            self._dirty   = True

    def _on_crash(self):
        if self._score > self._hi:
            self._hi = self._score
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

        if self._state == INTRO:
            widgets.draw_header(d, "RACER")
            widgets.draw_hint  (d, "A=start  HOME=back")
            self._draw_player(d, sprite=self._spr_player)
            self._draw_intro(d)
        elif self._state == PLAY:
            widgets.draw_hint(d, "Tilt: roll=steer  pitch=throttle")
            self._draw_enemies(d)
            self._draw_player(d, sprite=self._spr_player)
            self._draw_hud(d)
        elif self._state == OVER:
            widgets.draw_header(d, "CRASH!")
            widgets.draw_hint  (d, "A=continue  HOME=back")
            self._draw_enemies(d)
            self._draw_player(d, sprite=self._spr_crash or self._spr_player)
            self._draw_gameover(d)

    # ── render helpers ──────────────────────────────────────────────────
    def _draw_world(self, d):
        # Grass verges either side
        d.clear(api.rgb(40, 110, 50))
        # Road
        if self._spr_road:
            data, rw, rh = self._spr_road
            y = PLAY_TOP - (int(self._scroll_y) % rh)
            while y < PLAY_BOT:
                x = ROAD_X
                while x < ROAD_X + ROAD_W:
                    d.blit(data, x, y, rw, rh)
                    x += rw
                y += rh
        else:
            d.rect(ROAD_X, PLAY_TOP, ROAD_W, PLAY_H, api.rgb(64, 64, 72), fill=True)
            # centre dashes
            dash_h = 24
            gap    = 16
            step   = dash_h + gap
            y0     = PLAY_TOP - (int(self._scroll_y) % step)
            cx     = ROAD_X + ROAD_W // 2 - 2
            y      = y0
            while y < PLAY_BOT:
                yy = max(PLAY_TOP, y)
                d.rect(cx, yy, 4, min(dash_h, PLAY_BOT - yy),
                       api.WHITE, fill=True)
                y += step

        # Side trees (parallax). Skip the centre band; clusters left + right.
        if self._spr_tree:
            data, tw, th = self._spr_tree
            step = th + 24
            base = int(self._tree_t) % step
            y = PLAY_TOP - base
            while y < PLAY_BOT:
                if PLAY_TOP - th < y < PLAY_BOT:
                    d.blit(data, ROAD_X - tw - 2, y, tw, th)
                    d.blit(data, ROAD_X + ROAD_W + 2, y, tw, th)
                y += step

    def _draw_enemies(self, d):
        for e in self._enemies:
            if e.spr:
                data, w, h = e.spr
                d.blit(data, int(e.x), int(e.y), w, h)
            else:
                d.rect(int(e.x), int(e.y), ENEMY_W, ENEMY_H,
                       theme.PRIMARY, fill=True)

    def _draw_player(self, d, sprite=None):
        if sprite:
            data, w, h = sprite
            d.blit(data, int(self._player_x), PLAYER_Y, w, h)
        else:
            d.rect(int(self._player_x), PLAYER_Y, CAR_W, CAR_H,
                   theme.GOLD, fill=True)

    def _draw_hud(self, d):
        s = "%d" % self._score
        d.text(s, SW - len(s) * 16 - 6, 6, api.WHITE, scale=2)
        # speed mini-bar bottom-left
        bar_w   = 60
        d.rect(8, SH - widgets.HINT_H - 10, bar_w, 4,
               api.rgb(40, 40, 40), fill=True)
        v_pct = (self._scroll_v - ROAD_SCROLL_MIN) / max(
            1.0, ROAD_SCROLL_MAX - ROAD_SCROLL_MIN)
        d.rect(8, SH - widgets.HINT_H - 10, int(bar_w * v_pct), 4,
               theme.GOLD, fill=True)

    def _draw_intro(self, d):
        title = "PANDA RACER"
        d.text(title, (SW - len(title) * 24) // 2, 56, api.WHITE, scale=3)
        if self._hi:
            hi = "HIGH %d" % self._hi
            d.text(hi, (SW - len(hi) * 16) // 2, 92, theme.GOLD, scale=2)
        if not self._imu:
            warn = "no IMU - sensor offline"
            d.text(warn, (SW - len(warn) * 8) // 2, 124, theme.PRIMARY)
        if int(self._blink * 2) % 2 == 0:
            msg = "Press A to start"
            d.text(msg, (SW - len(msg) * 16) // 2, 148, api.WHITE, scale=2)
        hint = "Hold the badge flat. Tilt to steer."
        d.text(hint, (SW - len(hint) * 8) // 2, PLAY_BOT - 18, theme.GOLD)

    def _draw_gameover(self, d):
        band_h = 110
        band_y = (SH - band_h) // 2
        d.rect(0, band_y, SW, band_h, api.rgb(10, 14, 28), fill=True)
        d.rect(0, band_y, SW, 3, theme.PRIMARY, fill=True)
        d.rect(0, band_y + band_h - 3, SW, 3, theme.PRIMARY, fill=True)
        title = "GAME OVER"
        d.text(title, (SW - len(title) * 24) // 2, band_y + 14,
               api.WHITE, scale=3)
        score_line = "Score %d" % self._score
        d.text(score_line, (SW - len(score_line) * 16) // 2, band_y + 50,
               api.WHITE, scale=2)
        if self._new_hi:
            d.text("NEW HIGH!", (SW - 9 * 16) // 2, band_y + 74,
                   theme.GOLD, scale=2)
        else:
            best = "Best %d" % self._hi
            d.text(best, (SW - len(best) * 16) // 2, band_y + 74,
                   theme.GOLD, scale=2)

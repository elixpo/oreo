"""Doom — Freedoom Episode 1 on the badge's built-in Doom engine.

The engine is the firmware's _oreo_doom module (GPL-2.0-or-later, see
firmware/usermods/oreo_doom). The game data is Freedoom in the badge's
"doom" flash partition, written by ./deploy --full. Each frame the app
hands the engine the held buttons and the turning from the badge's tilt,
the engine runs and renders, and the frame is copied to the screen as is.

Controls:
  Tilt       tilt left/right to turn, further for faster (with the IMU)
  D-pad      UP/DOWN walk; LEFT/RIGHT strafe (turn without the IMU)
  A          fire (menus: select)
  B          use, open doors (prompts: yes)
  C (hold)   strafe with LEFT/RIGHT; C+UP cycles weapons
  HOME       game menu (prompts: no); twice within 1 s returns to OreoOS

Leaving with HOME twice keeps the game in memory, so opening Doom again
resumes it. Quit Game in Doom's menu also returns to OreoOS, with Doom back
at its title screen.
"""

import gc
import math
import time
import oreoOS
from oreoOS import api, theme, widgets

try:
    import _oreo_doom as doom
except ImportError:
    doom = None

EXIT_TAP_MS = 1000

# Tilt to turn, like a joystick: the side-to-side tilt from the way the badge
# was held when Doom opened sets the turn speed. Roll uses the IMU's X axis
# with tilting right positive, as Racer's steering does.
TILT_DEADZONE_DEG = 6           # held about level: no turning
TILT_FULL_DEG = 30              # this far or more: full speed
TURN_MAX_DPS = 180              # in-game turning at full tilt
NEUTRAL_SAMPLES = 20
MOUSE_UNITS_PER_DEG = 65536 / 360 / 8   # engine: angleturn -= mousex * 8

PLAYING   = "playing"
NO_ENGINE = "no-engine"
NO_DATA   = "no-data"
FAILED    = "failed"

MESSAGES = {
    NO_ENGINE: ("This firmware has no", "Doom engine.", "Update the badge firmware."),
    NO_DATA:   ("No Doom game data.", "Reflash the badge with", "./deploy --full"),
}


class App(oreoOS.App):
    name = "Doom"

    # C is Doom's strafe button, so the notification panel stays shut.
    CAPTURES_C = True

    def on_enter(self, os):
        self._os = os
        self._home_t = -10000
        self._error = 0
        self._dirty = True
        self._state = self._start()
        self._imu = self._start_tilt() if self._state == PLAYING else None

    def on_exit(self):
        if self._imu is not None:
            try:
                self._imu.sleep()
            except Exception:
                pass
            self._imu = None

    def _start(self):
        if doom is None:
            return NO_ENGINE
        if doom.running():
            return PLAYING
        if not doom.available():
            return NO_DATA
        gc.collect()
        try:
            rc = doom.start()
        except OSError:
            return NO_DATA
        if rc == 0:
            return PLAYING
        self._error = rc
        return FAILED

    # ── tilt ─────────────────────────────────────────────────────────────

    def _start_tilt(self):
        """Wake the IMU and take the current tilt as level; None without one."""
        imu = getattr(self._os, "_imu", None)
        if imu is None:
            try:
                from oreoWare import imu as imu_mod
                imu = imu_mod.detect()
            except Exception:
                imu = None
            if imu is None:
                return None
            try:
                self._os._imu = imu     # shared with Racer, as it does
            except Exception:
                pass
        try:
            imu.wake()
            time.sleep_ms(30)
            total = 0.0
            for _ in range(NEUTRAL_SAMPLES):
                total += self._roll(imu)
                time.sleep_ms(2)
        except Exception:
            return None
        self._neutral = total / NEUTRAL_SAMPLES
        self._turn_frac = 0.0
        self._tilt_t = time.ticks_us()
        return imu

    @staticmethod
    def _roll(imu):
        """Side-to-side tilt in degrees, positive tilting right."""
        ax, ay, az, _, _, _, _ = imu.read_raw()
        return math.degrees(math.atan2(ax, math.sqrt(ay * ay + az * az)))

    def _tilt_turn(self):
        """Engine turn units since the last call, or None without the IMU."""
        if self._imu is None:
            return None
        try:
            roll = self._roll(self._imu) - self._neutral
        except Exception:
            self._imu = None            # lost the IMU: buttons turn again
            return None
        now = time.ticks_us()
        dt = time.ticks_diff(now, self._tilt_t) / 1e6
        self._tilt_t = now
        tilt = abs(roll)
        if tilt < TILT_DEADZONE_DEG or dt <= 0 or dt > 0.25:
            return 0
        # Ease in, so small tilts aim finely and large ones turn fast.
        amount = min(1.0, (tilt - TILT_DEADZONE_DEG) / (TILT_FULL_DEG - TILT_DEADZONE_DEG))
        rate = TURN_MAX_DPS * amount * amount
        # The engine turns right for positive mouse movement.
        units = (rate if roll > 0 else -rate) * dt * MOUSE_UNITS_PER_DEG + self._turn_frac
        whole = int(units)
        self._turn_frac = units - whole
        return whole

    # ── app lifecycle ────────────────────────────────────────────────────

    def realtime_mode(self):
        return self._state == PLAYING

    def on_home_press(self):
        """First HOME is Doom's menu key; a second within 1 s leaves."""
        if self._state != PLAYING:
            return False
        now = time.ticks_ms()
        if time.ticks_diff(now, self._home_t) < EXIT_TAP_MS:
            return False
        self._home_t = now
        return True

    def update(self, dt):
        if self._state != PLAYING:
            return
        buttons = self._os.buttons
        mask = 0
        for b in api.BUTTONS:
            if buttons.is_pressed(b):
                mask |= 1 << b
        result = doom.tick(mask, self._tilt_turn())
        if result == 2:
            # Quit Game: Doom is back at its title screen; return to OreoOS.
            self._os.launch("__appmenu__")
        elif result < 0:
            self._state = FAILED
            self._error = doom.exit_code()
            self._dirty = True
        elif result:
            self._dirty = True

    def draw(self, d):
        if not self._dirty:
            return
        self._dirty = False
        if self._state == PLAYING:
            d.blit_fullscreen(doom.frame())
            return
        d.clear(theme.BG)
        widgets.draw_header(d, "DOOM")
        lines = MESSAGES.get(self._state) or (
            "Doom stopped with", "error %d." % self._error, "Restart the badge.")
        y = widgets.HEADER_H + 40
        for line in lines:
            d.text(line, (api.SCREEN_W - len(line) * 8) // 2, y, theme.TEXT_BRIGHT)
            y += 20
        widgets.draw_hint(d, "HOME = back")

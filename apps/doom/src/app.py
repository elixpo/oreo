"""Doom — Freedoom Episode 1 on the badge's built-in Doom engine.

The engine is the firmware's _oreo_doom module (GPL-2.0-or-later, see
firmware/usermods/oreo_doom). The game data is Freedoom in the badge's
"doom" flash partition, written by ./deploy --full. Each frame the app
hands the engine the held buttons and the gyro's turning, the engine runs
and renders, and the frame is copied to the screen as is.

Controls:
  Rotate     turn (gyro aiming, when the badge's IMU answers)
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

# Gyro aiming. The turn rate is measured about gravity, so it works however
# the badge is held or the IMU is mounted; rotating left turns left.
GYRO_LSB_PER_DPS = 131.0        # MPU-6050 at ±250 °/s (oreoWare.imu)
GYRO_GAIN = 1.5                 # in-game degrees per degree the badge turns
GYRO_DEADZONE_DPS = 1.5         # ignore drift below this
CALIBRATION_SAMPLES = 40
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
        self._imu = self._start_gyro() if self._state == PLAYING else None

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

    # ── gyro ─────────────────────────────────────────────────────────────

    def _start_gyro(self):
        """Wake the IMU and measure the gyro's bias; None without an IMU."""
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
            time.sleep_ms(30)           # gyro start-up
            sx = sy = sz = 0
            for _ in range(CALIBRATION_SAMPLES):
                _, _, _, _, gx, gy, gz = imu.read_raw()
                sx += gx
                sy += gy
                sz += gz
                time.sleep_ms(2)
        except Exception:
            return None
        n = CALIBRATION_SAMPLES
        self._bias = (sx / n, sy / n, sz / n)
        self._turn_frac = 0.0
        self._gyro_t = time.ticks_us()
        return imu

    def _gyro_turn(self):
        """Engine turn units since the last call, or None without the gyro."""
        if self._imu is None:
            return None
        try:
            ax, ay, az, _, gx, gy, gz = self._imu.read_raw()
        except Exception:
            self._imu = None            # lost the IMU: buttons turn again
            return None
        now = time.ticks_us()
        dt = time.ticks_diff(now, self._gyro_t) / 1e6
        self._gyro_t = now
        g = math.sqrt(ax * ax + ay * ay + az * az)
        if g == 0 or dt <= 0 or dt > 0.25:
            return 0
        bx, by, bz = self._bias
        # Rate about the up direction (the accelerometer reads +1 g upwards at
        # rest): positive means turning left, i.e. counter-clockwise from above.
        left_dps = ((gx - bx) * ax + (gy - by) * ay + (gz - bz) * az) / g / GYRO_LSB_PER_DPS
        if abs(left_dps) < GYRO_DEADZONE_DPS:
            return 0
        # The engine turns right for positive mouse movement.
        units = -left_dps * dt * GYRO_GAIN * MOUSE_UNITS_PER_DEG + self._turn_frac
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
        result = doom.tick(mask, self._gyro_turn())
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

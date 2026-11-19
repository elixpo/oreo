"""XPT2046 resistive touch on the PCB badge's 2.8" display module.

The controller shares the display's SPI bus (SCK 12, MOSI 11, and MISO 13,
which only it uses); its chip select is the AW9523B's P1_7
(pins.EXP_TOUCH_CS) and its pen interrupt PENIRQ is GPIO21
(pins.TOUCH_IRQ), low while the screen is pressed.

read() samples only while PENIRQ is low: it drops the bus to TOUCH_BAUD
(the XPT2046 tops out near 2.5 MHz), selects the chip through the
expander, takes SAMPLES readings of X, Y and pressure, then deselects it
and puts the bus back at the display's rate. Readings map to screen
coordinates through a calibration (raw range per axis, axis swap and
flips) that a calibration screen can replace with set_calibration().

create(display) returns a Touch on the PCB badge and None elsewhere.
"""

from oreoWare import pins

SCREEN_W = 320
SCREEN_H = 240

TOUCH_BAUD = 2_000_000
SAMPLES = 4
PRESSURE_MIN = 300          # z below this is a light brush or noise

# 12-bit, differential reference, PD bits 00 (PENIRQ stays enabled)
_CMD_X = 0xD0
_CMD_Y = 0x90
_CMD_Z1 = 0xB0
_CMD_Z2 = 0xC0

# Typical for MSP2807-type modules mounted landscape; check on the first
# board and replace with a measured calibration.
DEFAULT_CAL = {
    "x_min": 200, "x_max": 3900,     # raw X range
    "y_min": 200, "y_max": 3900,     # raw Y range
    "swap_xy": True,                 # the panel is portrait; the badge landscape
    "flip_x": False,
    "flip_y": True,
}


def _scale(v, lo, hi, size):
    if hi == lo:
        return 0
    p = (v - lo) * (size - 1) // (hi - lo)
    return 0 if p < 0 else (size - 1 if p > size - 1 else p)


def to_screen(raw_x, raw_y, cal=DEFAULT_CAL):
    """Raw 12-bit readings to (x, y) on the 320 x 240 screen."""
    if cal.get("swap_xy"):
        raw_x, raw_y = raw_y, raw_x
    x = _scale(raw_x, cal["x_min"], cal["x_max"], SCREEN_W)
    y = _scale(raw_y, cal["y_min"], cal["y_max"], SCREEN_H)
    if cal.get("flip_x"):
        x = SCREEN_W - 1 - x
    if cal.get("flip_y"):
        y = SCREEN_H - 1 - y
    return x, y


class Touch:
    def __init__(self, spi, expander, irq=None, restore_baud=None, miso=None):
        self._spi = spi
        self._exp = expander
        self._irq = irq
        self._restore = restore_baud
        self._miso = miso
        self._tx = bytearray(3)
        self._rx = bytearray(3)
        self._cal = dict(DEFAULT_CAL)

    def set_calibration(self, cal):
        c = dict(DEFAULT_CAL)
        c.update(cal or {})
        self._cal = c

    def calibration(self):
        return dict(self._cal)

    def touched(self):
        """True while the pen interrupt says the screen is pressed."""
        if self._irq is None:
            return True
        try:
            return self._irq.value() == 0
        except Exception:
            return False

    def _xfer(self, cmd):
        self._tx[0] = cmd
        self._spi.write_readinto(self._tx, self._rx)
        return ((self._rx[1] << 8) | self._rx[2]) >> 3

    def read_raw(self):
        """(raw_x, raw_y, pressure) averaged over SAMPLES, or None."""
        if not self.touched():
            return None
        kw = {"baudrate": TOUCH_BAUD}
        if self._miso is not None:
            kw["miso"] = self._miso
        sx = sy = sz = 0
        try:
            self._spi.init(**kw)
            self._exp.set_touch_cs(True)
            for _ in range(SAMPLES):
                sx += self._xfer(_CMD_X)
                sy += self._xfer(_CMD_Y)
                z1 = self._xfer(_CMD_Z1)
                z2 = self._xfer(_CMD_Z2)
                sz += z1 + 4095 - z2
        except Exception:
            return None
        finally:
            try:
                self._exp.set_touch_cs(False)
            except Exception:
                pass
            if self._restore is not None:
                try:
                    self._spi.init(baudrate=self._restore)
                except Exception:
                    pass
        z = sz // SAMPLES
        if z < PRESSURE_MIN:
            return None
        return sx // SAMPLES, sy // SAMPLES, z

    def read(self):
        """(x, y) on the screen while it's pressed, else None."""
        r = self.read_raw()
        if r is None:
            return None
        return to_screen(r[0], r[1], self._cal)


def create(display):
    """The PCB badge's touch screen, or None on the breadboard or on error."""
    if getattr(pins, "BOARD", "") != "pcb":
        return None
    try:
        from machine import Pin
        from oreoWare import aw9523
        exp = aw9523.get()
        spi = display._panel.spi
        if exp is None or spi is None:
            return None
        irq = Pin(pins.TOUCH_IRQ, Pin.IN, Pin.PULL_UP)
        return Touch(spi, exp, irq=irq, restore_baud=pins.DISPLAY_BAUD,
                     miso=Pin(pins.DISPLAY_MISO))
    except Exception:
        return None

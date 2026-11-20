"""AW9523B I2C expander on the PCB badge (0x58): buttons, corner LEDs,
amp enable, card detect, the switched 3.3 V supply and the touch chip select.

Port 0: the eight buttons (pins.EXP_BUTTON_ORDER), active low, with 10 kΩ
pull-ups on the board. Their interrupt is enabled, so ~INT (pins.EXP_INT)
goes low when one changes; reading port 0 clears it.

Port 1:
  P1_0-P1_3  corner LEDs. Each sinks the cathodes of three LEDs with no
             series resistor, so these pins only ever run in the chip's
             constant-current LED mode, never as GPIO outputs driven low.
  P1_4       AMP_EN, high = speaker amp on
  P1_5       SD_DET, input, low = card in
  P1_6       AUX_ON_N, low = IR receiver and status LED powered
  P1_7       touch controller chip select, high = deselected

get() returns the one shared instance on the PCB badge, set up on first
use, and None on the breadboard badge.
"""

from oreoWare import pins

ADDR = 0x58
CHIP_ID = 0x23

_IN0, _IN1 = 0x00, 0x01
_OUT0, _OUT1 = 0x02, 0x03
_CFG0, _CFG1 = 0x04, 0x05          # 1 = input
_INT0, _INT1 = 0x06, 0x07          # 0 = interrupt enabled
_ID = 0x10
_GCR = 0x11
_MODE0, _MODE1 = 0x12, 0x13        # 1 = GPIO, 0 = LED (constant current)
_DIM_P1 = (0x20, 0x21, 0x22, 0x23)  # current of P1_0..P1_3, 0-255

# GCR: ISEL = 11, a quarter of the 37 mA full scale (about 9 mA per channel,
# shared by the channel's three LEDs). Port 0 stays open-drain: it is all
# inputs.
_GCR_VALUE = 0x03

LED_TL, LED_TR, LED_BL, LED_BR = 0, 1, 2, 3


class AW9523:
    def __init__(self, i2c, addr=ADDR):
        self._i2c = i2c
        self._addr = addr
        self._b1 = bytearray(1)
        self._out1 = 0

    def _w(self, reg, value):
        self._b1[0] = value & 0xFF
        self._i2c.writeto_mem(self._addr, reg, self._b1)

    def _r(self, reg):
        self._i2c.readfrom_mem_into(self._addr, reg, self._b1)
        return self._b1[0]

    def chip_id(self):
        return self._r(_ID)

    def init(self):
        """Set every pin up. Safe to call again; it never turns a corner
        LED on, because the LED pins are held high until their current is
        zero and they are in LED mode."""
        self._w(_GCR, _GCR_VALUE)
        # LEDs off (pins high), amp off, AUX on (P1_6 low), touch deselected.
        self._out1 = pins.EXP_LED_BITS | pins.EXP_TOUCH_CS
        self._w(_OUT1, self._out1)
        self._w(_CFG1, pins.EXP_SD_DET)        # P1_5 input, the rest outputs
        for reg in _DIM_P1:
            self._w(reg, 0)
        self._w(_MODE1, 0xFF & ~pins.EXP_LED_BITS)   # P1_0-3 LED mode
        self._w(_MODE0, 0xFF)                  # port 0 GPIO
        self._w(_CFG0, 0xFF)                   # port 0 inputs
        self._w(_INT0, 0x00)                   # buttons interrupt
        self._w(_INT1, 0xFF)                   # port 1 doesn't
        self._r(_IN0)                          # clear a pending interrupt
        self._r(_IN1)

    # ── inputs ──────────────────────────────────────────────────────────
    def read_buttons(self):
        """Port 0 as a byte: bit n low = the button EXP_BUTTON_ORDER[n] is
        down. Also clears ~INT."""
        return self._r(_IN0)

    def card_present(self):
        return not (self._r(_IN1) & pins.EXP_SD_DET)

    # ── outputs ─────────────────────────────────────────────────────────
    def _set_out1(self, mask, on):
        v = (self._out1 | mask) if on else (self._out1 & ~mask)
        if v != self._out1:
            self._out1 = v
            self._w(_OUT1, v)

    def set_led(self, n, level):
        """Corner LED n (LED_TL..LED_BR) at 0-255."""
        if 0 <= n < 4:
            self._w(_DIM_P1[n], max(0, min(255, int(level))))

    def leds_off(self):
        for reg in _DIM_P1:
            self._w(reg, 0)

    def set_amp(self, on):
        self._set_out1(pins.EXP_AMP_EN, on)

    def set_aux(self, on):
        """Power the IR receiver and the status LED (P1_6 is active low)."""
        self._set_out1(pins.EXP_AUX_ON_N, not on)

    def set_touch_cs(self, selected):
        self._set_out1(pins.EXP_TOUCH_CS, not selected)


_dev = None


def get():
    """The PCB badge's expander, set up on first call; None elsewhere or
    when it doesn't answer."""
    global _dev
    if _dev is not None:
        return _dev
    if not getattr(pins, "EXPANDER", False):
        return None
    try:
        from machine import Pin, SoftI2C
        i2c = SoftI2C(scl=Pin(pins.I2C_SCL), sda=Pin(pins.I2C_SDA), freq=400_000)
        dev = AW9523(i2c, getattr(pins, "EXP_ADDR", ADDR))
        dev.init()
    except Exception:
        return None
    _dev = dev
    return dev

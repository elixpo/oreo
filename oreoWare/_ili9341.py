"""Minimal ILI9341 driver for the PCB badge's 2.8" 240x320 module (MSP2807
type), used in landscape as 320x240.

The same interface as oreoWare._st7789 (reset, init, resume, address
window, pixel bytes), so oreoWare.display and oreoOS.hostui drive either.
The address-window and memory-write commands (0x2A, 0x2B, 0x2C) are the
same on both, so the native splash and RV565 player need no change.

Differences from the ST7789: a TN panel, so no colour inversion; the
module's colour filter is BGR; and its own power, gamma and frame-rate
settings.
"""

from machine import Pin, SPI  # noqa: F401  (same imports as _st7789)
import time

_SWRESET = 0x01
_SLPOUT  = 0x11
_DISPON  = 0x29
_CASET   = 0x2A
_RASET   = 0x2B
_RAMWR   = 0x2C
_MADCTL  = 0x36
_VSCRSADD = 0x37
_PIXFMT  = 0x3A
_FRMCTR1 = 0xB1
_DFUNCTR = 0xB6
_PWCTR1  = 0xC0
_PWCTR2  = 0xC1
_VMCTR1  = 0xC5
_VMCTR2  = 0xC7
_GAMMASET = 0x26
_GMCTRP1 = 0xE0
_GMCTRN1 = 0xE1

# MADCTL: MV (row/column exchange, landscape) | BGR. The module sits on the
# badge with its header on the right. If the picture comes out upside down
# on a real board, use 0xE8 (MY | MX | MV | BGR); if it is mirrored, flip
# MX (0x40) alone.
MADCTL_LANDSCAPE = 0x28

# FRMCTR1 0x00, 0x1B: 70 Hz in normal mode (the default is 0x18, 79 Hz).
# A slower scan leaves more of each frame for the SPI write, so less tearing.
_FRAME_RATE = 0x1B

# Power-up sequence for the ILI9341 (the values in its application notes
# and the common Adafruit driver): power control A/B, driver timing,
# power-on sequence, pump ratio, VCOM, gamma.
_INIT = (
    (0xEF, b"\x03\x80\x02"),
    (0xCF, b"\x00\xC1\x30"),          # power control B
    (0xED, b"\x64\x03\x12\x81"),      # power-on sequence
    (0xE8, b"\x85\x00\x78"),          # driver timing A
    (0xCB, b"\x39\x2C\x00\x34\x02"),  # power control A
    (0xF7, b"\x20"),                  # pump ratio
    (0xEA, b"\x00\x00"),              # driver timing B
    (_PWCTR1, b"\x23"),
    (_PWCTR2, b"\x10"),
    (_VMCTR1, b"\x3E\x28"),
    (_VMCTR2, b"\x86"),
    (_VSCRSADD, b"\x00"),
    (_PIXFMT, b"\x55"),               # 16 bpp RGB565
    (_DFUNCTR, b"\x08\x82\x27"),
    (0xF2, b"\x00"),                  # 3-gamma off
    (_GAMMASET, b"\x01"),
    (_GMCTRP1, b"\x0F\x31\x2B\x0C\x0E\x08\x4E\xF1\x37\x07\x10\x03\x0E\x09\x00"),
    (_GMCTRN1, b"\x00\x0E\x14\x03\x11\x07\x31\xC1\x48\x08\x0F\x0C\x31\x36\x0F"),
)


class ILI9341:
    def __init__(self, spi, dc, cs, rst, bl, width=240, height=320):
        self.spi = spi
        self.dc, self.cs, self.rst, self.bl = dc, cs, rst, bl
        self.width, self.height = width, height
        self._win = bytearray(4)
        self._ramwr_cmd = bytes([_RAMWR])

    def _cmd(self, c, data=None):
        self.cs(0)
        self.dc(0)
        self.spi.write(bytes([c]))
        if data:
            self.dc(1)
            self.spi.write(data)
        self.cs(1)

    def _hard_reset(self):
        self.rst(1); time.sleep_ms(10)
        self.rst(0); time.sleep_ms(10)
        self.rst(1); time.sleep_ms(120)

    def init(self):
        self._hard_reset()
        self._cmd(_SWRESET); time.sleep_ms(150)
        self._configure(150, 100)

    def resume(self):
        """Put the panel in init()'s configuration without the resets, so
        a panel that is already set up keeps its picture. Used by
        oreoOS.hostui while FaleraOS is stopped at the raw REPL."""
        self._configure(120, 10)

    def _configure(self, slpout_ms, dispon_ms):
        for c, data in _INIT:
            self._cmd(c, data)
        self._cmd(_MADCTL, bytes([MADCTL_LANDSCAPE]))
        self._cmd(_FRMCTR1, bytes([0x00, _FRAME_RATE]))
        # Address window: set once; present() reissues RAMWR only.
        self._cmd(_CASET, b"\x00\x00\x01\x3F")         # cols 0..319
        self._cmd(_RASET, b"\x00\x00\x00\xEF")         # rows 0..239
        self._cmd(_SLPOUT); time.sleep_ms(slpout_ms)
        self._cmd(_DISPON); time.sleep_ms(dispon_ms)
        # The backlight stays off: oreoWare.display pushes a black frame
        # first, then turns it on.

    def set_window(self, x0, y0, x1, y1):
        w = self._win
        w[0] = x0 >> 8; w[1] = x0 & 0xff
        w[2] = x1 >> 8; w[3] = x1 & 0xff
        self._cmd(_CASET, w)
        w[0] = y0 >> 8; w[1] = y0 & 0xff
        w[2] = y1 >> 8; w[3] = y1 & 0xff
        self._cmd(_RASET, w)

    def fill(self, color565):
        self.set_window(0, 0, self.width - 1, self.height - 1)
        line = bytes([color565 >> 8, color565 & 0xff]) * self.width
        self.cs(0)
        self.dc(0); self.spi.write(bytes([_RAMWR]))
        self.dc(1)
        for _ in range(self.height):
            self.spi.write(line)
        self.cs(1)

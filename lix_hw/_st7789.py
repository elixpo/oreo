"""Minimal ST7789P3 driver for the SmartElex 2.0" 240x320 IPS panel.

Low-level only: reset, init, set address window, push pixel bytes.
Higher-level drawing (framebuf, primitives, text) belongs in lix_hw.display.

Leading-underscore module name signals: not part of the public lix_hw API.
"""

from machine import Pin, SPI
import time

# ----- ST7789 command opcodes -----
_SWRESET = 0x01
_SLPOUT  = 0x11
_NORON   = 0x13
_INVON   = 0x21
_DISPON  = 0x29
_CASET   = 0x2A
_RASET   = 0x2B
_RAMWR   = 0x2C
_MADCTL  = 0x36
_COLMOD  = 0x3A

# MADCTL orientation bits — landscape 320×240
# MX=1 (0x40) | MV=1 (0x20) = 0x60 → 90° CW rotation
_MADCTL_LANDSCAPE = 0x60


class ST7789:
    def __init__(self, spi, dc, cs, rst, bl, width=240, height=320):
        self.spi = spi
        self.dc, self.cs, self.rst, self.bl = dc, cs, rst, bl
        self.width, self.height = width, height
        self._win = bytearray(4)

    # --- low-level: send command (with optional data bytes) ---
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
        self._cmd(_SLPOUT);  time.sleep_ms(500)
        self._cmd(_COLMOD, b'\x55')                       # 16bpp RGB565
        self._cmd(_MADCTL, bytes([_MADCTL_LANDSCAPE]))    # landscape 320×240
        self._cmd(_CASET,  b'\x00\x00\x01\x3F')           # cols 0..319
        self._cmd(_RASET,  b'\x00\x00\x00\xEF')           # rows 0..239
        self._cmd(_INVON);  time.sleep_ms(10)        # IPS panels need inversion ON
        self._cmd(_NORON);  time.sleep_ms(10)
        self._cmd(_DISPON); time.sleep_ms(100)
        self.bl(1)

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

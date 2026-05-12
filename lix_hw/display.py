"""Display backend — implements lix.api.Display on the badge.

Strategy: keep a full 240*320*2 = 153KB RGB565 framebuffer in PSRAM, run all
draw primitives against it via MicroPython's `framebuf` module, then push the
whole buffer to the ST7789 in one SPI burst on present().

Byte-order note: framebuf stores RGB565 little-endian on ESP32, but ST7789
expects big-endian over SPI. We pre-swap colors as they enter the framebuf so
present() can dump the buffer verbatim without per-pixel conversion.
"""

import framebuf
from machine import Pin, SPI

from lix import api
from lix_hw import pins
from lix_hw._st7789 import ST7789


def _swap(c):
    return ((c & 0xff) << 8) | ((c >> 8) & 0xff)


class Display(api.Display):
    def __init__(self):
        spi = SPI(
            1,
            baudrate=pins.DISPLAY_BAUD,
            polarity=0, phase=0,
            sck=Pin(pins.DISPLAY_SCK),
            mosi=Pin(pins.DISPLAY_MOSI),
        )
        self._panel = ST7789(
            spi,
            dc =Pin(pins.DISPLAY_DC,    Pin.OUT),
            cs =Pin(pins.DISPLAY_CS,    Pin.OUT, value=1),
            rst=Pin(pins.DISPLAY_RESET, Pin.OUT, value=1),
            bl =Pin(pins.DISPLAY_BL,    Pin.OUT, value=0),
        )
        self._panel.init()
        self._buf = bytearray(api.SCREEN_W * api.SCREEN_H * 2)
        self._fb = framebuf.FrameBuffer(
            self._buf, api.SCREEN_W, api.SCREEN_H, framebuf.RGB565
        )

    def clear(self, color=api.BLACK):
        self._fb.fill(_swap(color))

    def pixel(self, x, y, color):
        self._fb.pixel(x, y, _swap(color))

    def line(self, x0, y0, x1, y1, color):
        self._fb.line(x0, y0, x1, y1, _swap(color))

    def rect(self, x, y, w, h, color, fill=False):
        if fill:
            self._fb.fill_rect(x, y, w, h, _swap(color))
        else:
            self._fb.rect(x, y, w, h, _swap(color))

    def text(self, s, x, y, color=api.WHITE, scale=1):
        # framebuf has a built-in 8x8 font, no native scaling.
        if scale == 1:
            self._fb.text(s, x, y, _swap(color))
            return
        # scale>1: render into a 1bpp mask, then expand any "lit" pixel to a scale*scale block.
        # Using 1bpp avoids the "black text invisible" trap of checking RGB565 for nonzero.
        char_h = 8
        char_w = 8 * len(s)
        mask = bytearray(((char_w + 7) // 8) * char_h)
        mask_fb = framebuf.FrameBuffer(mask, char_w, char_h, framebuf.MONO_HLSB)
        mask_fb.text(s, 0, 0, 1)
        swapped = _swap(color)
        for py in range(char_h):
            for px in range(char_w):
                if mask_fb.pixel(px, py):
                    self._fb.fill_rect(x + px * scale, y + py * scale, scale, scale, swapped)

    def blit(self, sprite, x, y, w, h):
        src = framebuf.FrameBuffer(bytearray(sprite), w, h, framebuf.RGB565)
        self._fb.blit(src, x, y)

    def present(self):
        p = self._panel
        p.set_window(0, 0, api.SCREEN_W - 1, api.SCREEN_H - 1)
        p.cs(0)
        p.dc(0); p.spi.write(b'\x2C')   # RAMWR
        p.dc(1); p.spi.write(self._buf)
        p.cs(1)

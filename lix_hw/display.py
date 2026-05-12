"""Display backend — implements lix.api.Display on the badge.

Framebuffer strategy:
  - Full 320×240×2 = 153 KB RGB565 framebuffer in PSRAM
  - All drawing goes through MicroPython framebuf primitives
  - present() pushes the buffer to ST7789 over SPI — but ONLY when the
    framebuffer was actually modified (dirty flag), preventing idle flicker.

Byte-order:
  framebuf stores RGB565 little-endian; ST7789 expects big-endian over SPI.
  _swap() pre-swaps colors as they enter framebuf so present() can dump
  the buffer verbatim without per-pixel conversion at flush time.
"""

import framebuf
import struct
from machine import Pin, SPI

from lix import api
from lix_hw import pins
from lix_hw._st7789 import ST7789


def _swap(c):
    return ((c & 0xFF) << 8) | ((c >> 8) & 0xFF)


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
        self._buf   = bytearray(api.SCREEN_W * api.SCREEN_H * 2)
        self._fb    = framebuf.FrameBuffer(
            self._buf, api.SCREEN_W, api.SCREEN_H, framebuf.RGB565
        )
        self._dirty = False   # only push SPI when something was drawn

    # ── primitives ────────────────────────────────────────────────────────────

    def clear(self, color=api.BLACK):
        self._fb.fill(_swap(color))
        self._dirty = True

    def pixel(self, x, y, color):
        self._fb.pixel(x, y, _swap(color))
        self._dirty = True

    def line(self, x0, y0, x1, y1, color):
        self._fb.line(x0, y0, x1, y1, _swap(color))
        self._dirty = True

    def rect(self, x, y, w, h, color, fill=False):
        if fill:
            self._fb.fill_rect(x, y, w, h, _swap(color))
        else:
            self._fb.rect(x, y, w, h, _swap(color))
        self._dirty = True

    def text(self, s, x, y, color=api.WHITE, scale=1):
        if scale == 1:
            self._fb.text(s, x, y, _swap(color))
            self._dirty = True
            return
        char_h = 8
        char_w = 8 * len(s)
        mask = bytearray(((char_w + 7) // 8) * char_h)
        mask_fb = framebuf.FrameBuffer(mask, char_w, char_h, framebuf.MONO_HLSB)
        mask_fb.text(s, 0, 0, 1)
        swapped = _swap(color)
        for py in range(char_h):
            for px in range(char_w):
                if mask_fb.pixel(px, py):
                    self._fb.fill_rect(
                        x + px * scale, y + py * scale, scale, scale, swapped)
        self._dirty = True

    def blit(self, sprite, x, y, w, h):
        # Sprite is big-endian RGB565 bytes. Our framebuf convention is also
        # big-endian (primitives go through _swap() to land that way), so
        # we just copy the raw bytes — framebuf.blit() is byte-level memcpy
        # for matching RGB565 → RGB565.
        n = w * h
        buf = bytearray(sprite[:n * 2])
        src = framebuf.FrameBuffer(buf, w, h, framebuf.RGB565)
        self._fb.blit(src, x, y)
        self._dirty = True

    def blit_scale(self, sprite, x, y, w, h, scale, dim=0.0):
        """Scale sprite up by `scale` and blit. dim 0.0–1.0 blends toward BG.

        Builds a pre-scaled bytearray (row by row with memcpy for Y repeats)
        then stamps it with a single framebuf.blit() call.
        """
        n   = w * h
        sw  = w * scale
        sh  = h * scale
        words = struct.unpack(">%dH" % n, sprite[:n * 2])

        if dim > 0:
            from lix_os import theme as _t
            br, bg_, bb = _t.BG_R, _t.BG_G, _t.BG_B

        out  = bytearray(sw * sh * 2)
        row  = bytearray(sw * 2)        # one scaled row, little-endian

        for src_row in range(h):
            base_w = src_row * w
            # build one horizontal scaled row
            for col in range(w):
                v = words[base_w + col]
                if dim > 0:
                    r = ((v >> 11) & 0x1F) << 3
                    g = ((v >>  5) & 0x3F) << 2
                    b = ( v        & 0x1F) << 3
                    r = int(r + (br  - r) * dim)
                    g = int(g + (bg_ - g) * dim)
                    b = int(b + (bb  - b) * dim)
                    v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                # store big-endian (matches framebuf convention here)
                b1 = v >> 8        # high byte first
                b0 = v & 0xFF      # low byte second
                base = col * scale * 2
                for dx in range(scale):
                    row[base + dx * 2]     = b1
                    row[base + dx * 2 + 1] = b0

            # stamp the row `scale` times vertically via memcpy
            row_start = src_row * scale * sw * 2
            for dy in range(scale):
                s = row_start + dy * sw * 2
                out[s: s + sw * 2] = row

        src_fb = framebuf.FrameBuffer(out, sw, sh, framebuf.RGB565)
        self._fb.blit(src_fb, x, y)
        self._dirty = True

    # ── flush ─────────────────────────────────────────────────────────────────

    def present(self):
        """Push framebuffer to display — no-op if nothing was drawn since last call."""
        if not self._dirty:
            return
        self._dirty = False
        p = self._panel
        p.set_window(0, 0, api.SCREEN_W - 1, api.SCREEN_H - 1)
        p.cs(0)
        p.dc(0); p.spi.write(b'\x2C')
        p.dc(1); p.spi.write(self._buf)
        p.cs(1)

    def present_rect(self, x, y, w, h):
        if not self._dirty:
            return
        self._dirty = False
        p = self._panel
        p.set_window(x, y, x + w - 1, y + h - 1)
        p.cs(0)
        p.dc(0); p.spi.write(b'\x2C')
        p.dc(1)
        stride = api.SCREEN_W * 2
        row_start = y * stride + x * 2
        row_len = w * 2
        buf = self._buf
        for _ in range(h):
            p.spi.write(buf[row_start: row_start + row_len])
            row_start += stride
        p.cs(1)

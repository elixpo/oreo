"""pygame implementation of api.Display.

Renders the 240×320 badge screen at SCALE× magnification.  Text uses the
embedded 8×8 bitmap font so positions exactly match the hardware.
"""

import pygame
from lix import api
from lix_sim.font8x8 import glyph

SCALE = 2  # 320×240 → 640×480


def _rgb565_to_rgb(c):
    r = ((c >> 11) & 0x1F) << 3
    g = ((c >> 5) & 0x3F) << 2
    b = (c & 0x1F) << 3
    return (r, g, b)


class SimDisplay(api.Display):
    def __init__(self, surface):
        self._surf = surface  # pygame Surface, SCALE×SCALE per badge pixel

    # --- primitives ----------------------------------------------------------

    def clear(self, color=api.BLACK):
        self._surf.fill(_rgb565_to_rgb(color))

    def pixel(self, x, y, color):
        if 0 <= x < api.SCREEN_W and 0 <= y < api.SCREEN_H:
            pygame.draw.rect(
                self._surf, _rgb565_to_rgb(color),
                (x * SCALE, y * SCALE, SCALE, SCALE),
            )

    def line(self, x0, y0, x1, y1, color):
        pygame.draw.line(
            self._surf, _rgb565_to_rgb(color),
            (x0 * SCALE, y0 * SCALE), (x1 * SCALE, y1 * SCALE),
            SCALE,
        )

    def rect(self, x, y, w, h, color, fill=False):
        r = pygame.Rect(x * SCALE, y * SCALE, w * SCALE, h * SCALE)
        c = _rgb565_to_rgb(color)
        if fill:
            pygame.draw.rect(self._surf, c, r)
        else:
            pygame.draw.rect(self._surf, c, r, max(1, SCALE // 2))

    def text(self, s, x, y, color=api.WHITE, scale=1):
        """Render string using the 8×8 bitmap font at the given scale.

        Each character cell is 8*scale badge pixels wide × 8*scale badge pixels
        tall — identical to MicroPython framebuf text().
        """
        c = _rgb565_to_rgb(color)
        char_px = 8 * scale * SCALE   # pixel width of one character in sim
        char_py = 8 * scale * SCALE   # pixel height

        for ci, ch in enumerate(s):
            cx = (x + ci * 8 * scale) * SCALE
            cy = y * SCALE
            if cx >= api.SCREEN_W * SCALE:  # past right edge — clip
                break
            bits = glyph(ch)
            for row in range(8):
                byte = bits[row]
                for col in range(8):
                    if byte & (1 << col):  # LSB = leftmost pixel, matches MicroPython framebuf
                        px = cx + col * scale * SCALE
                        py = cy + row * scale * SCALE
                        pygame.draw.rect(
                            self._surf, c,
                            (px, py, scale * SCALE, scale * SCALE),
                        )

    def blit(self, sprite, x, y, w, h):
        """Copy a w×h RGB565 sprite (bytes-like) to (x, y).

        Fast path: convert the whole sprite to a pygame Surface at once, then
        scale it and blit it — avoids a Python loop over every pixel.
        """
        import struct
        n = w * h
        # Unpack big-endian RGB565 words
        words = struct.unpack_from(">%dH" % n, sprite, 0)
        # Build a 24-bit RGB surface
        surf = pygame.Surface((w, h))
        pa   = pygame.PixelArray(surf)
        for row in range(h):
            for col in range(w):
                word = words[row * w + col]
                r = ((word >> 11) & 0x1F) << 3
                g = ((word >>  5) & 0x3F) << 2
                b = ( word        & 0x1F) << 3
                pa[col][row] = surf.map_rgb(r, g, b)
        del pa
        if SCALE != 1:
            surf = pygame.transform.scale(surf, (w * SCALE, h * SCALE))
        self._surf.blit(surf, (x * SCALE, y * SCALE))

    def blit_scale(self, sprite, x, y, w, h, scale):
        """Blit sprite scaled up by `scale` badge-pixels."""
        import struct
        n = w * h
        words = struct.unpack_from(">%dH" % n, sprite, 0)
        surf = pygame.Surface((w * scale, h * scale))
        pa   = pygame.PixelArray(surf)
        for row in range(h):
            for col in range(w):
                word = words[row * w + col]
                r = ((word >> 11) & 0x1F) << 3
                g = ((word >>  5) & 0x3F) << 2
                b = ( word        & 0x1F) << 3
                c = surf.map_rgb(r, g, b)
                for dy in range(scale):
                    for dx in range(scale):
                        pa[col * scale + dx][row * scale + dy] = c
        del pa
        out_w = w * scale * SCALE
        out_h = h * scale * SCALE
        if SCALE != 1:
            surf = pygame.transform.scale(surf, (out_w, out_h))
        self._surf.blit(surf, (x * SCALE, y * SCALE))

    def present(self):
        """No-op: run_sim calls pygame.display.flip() after each frame."""

    def present_rect(self, x, y, w, h):
        """No-op for the same reason."""

"""pygame implementation of api.Display.

Renders the 240×320 badge screen at SCALE× magnification.  Text uses the
embedded 8×8 bitmap font so positions exactly match the hardware.
"""

import pygame
from lix import api
from lix_sim.font8x8 import glyph

SCALE = 3  # 240×320 → 720×960


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
        """Copy a w×h RGB565 sprite (bytes-like) to (x, y)."""
        for row in range(h):
            for col in range(w):
                idx = (row * w + col) * 2
                if idx + 1 >= len(sprite):
                    break
                word = (sprite[idx] << 8) | sprite[idx + 1]
                self.pixel(x + col, y + row, word)

    def present(self):
        """No-op: run_sim calls pygame.display.flip() after each frame."""

    def present_rect(self, x, y, w, h):
        """No-op for the same reason."""

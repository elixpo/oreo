"""Keyboard-mapped button implementation for the pygame simulator.

Key → Badge button:
  Arrow keys            → UP / DOWN / LEFT / RIGHT
  Escape                → HOME  (universal back)
  Z                     → A     (primary confirm / select)
  X                     → B
  C  (or Tab)           → C
  Enter                 → A     (alternative confirm)

update() must be called once per frame before checking just_pressed /
just_released.  It processes pygame.KEYDOWN / KEYUP events from the queue.
"""

import pygame
from lix import api

_KEY_MAP = {
    pygame.K_UP:     api.BTN_UP,
    pygame.K_DOWN:   api.BTN_DOWN,
    pygame.K_LEFT:   api.BTN_LEFT,
    pygame.K_RIGHT:  api.BTN_RIGHT,
    pygame.K_ESCAPE: api.BTN_HOME,
    pygame.K_h:      api.BTN_HOME,
    pygame.K_z:      api.BTN_A,
    pygame.K_RETURN: api.BTN_A,
    pygame.K_x:      api.BTN_B,
    pygame.K_c:      api.BTN_C,
    pygame.K_TAB:    api.BTN_C,
}


class SimButtons(api.Buttons):
    def __init__(self):
        self._held     = set()
        self._pressed  = set()
        self._released = set()

    def update(self):
        """Process pygame key events. Call once per frame."""
        self._pressed.clear()
        self._released.clear()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                raise SystemExit
            if event.type == pygame.KEYDOWN:
                btn = _KEY_MAP.get(event.key)
                if btn is not None:
                    self._held.add(btn)
                    self._pressed.add(btn)
            if event.type == pygame.KEYUP:
                btn = _KEY_MAP.get(event.key)
                if btn is not None:
                    self._held.discard(btn)
                    self._released.add(btn)

    def is_pressed(self, btn):
        return btn in self._held

    def just_pressed(self, btn):
        return btn in self._pressed

    def just_released(self, btn):
        return btn in self._released

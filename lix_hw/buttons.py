"""Buttons backend — implements lix.api.Buttons via INPUT_PULLUP GPIOs.

Edge detection (just_pressed / just_released) works against the *previous* frame,
so update() must be called exactly once per frame by the OS loop. Apps don't
call update() themselves — they receive a Buttons instance that's already up to
date.
"""

from machine import Pin

from lix import api
from lix_hw import pins


_BTN_TO_GPIO = {
    api.BTN_HOME:  pins.BTN_HOME,
    api.BTN_A:     pins.BTN_A,
    api.BTN_B:     pins.BTN_B,
    api.BTN_C:     pins.BTN_C,
    api.BTN_UP:    pins.BTN_UP,
    api.BTN_DOWN:  pins.BTN_DOWN,
    api.BTN_LEFT:  pins.BTN_LEFT,
    api.BTN_RIGHT: pins.BTN_RIGHT,
}


class Buttons(api.Buttons):
    def __init__(self):
        self._pins = {b: Pin(g, Pin.IN, Pin.PULL_UP) for b, g in _BTN_TO_GPIO.items()}
        self._curr = {b: 1 for b in _BTN_TO_GPIO}
        self._prev = {b: 1 for b in _BTN_TO_GPIO}

    def update(self):
        for b, p in self._pins.items():
            self._prev[b] = self._curr[b]
            self._curr[b] = p.value()

    def is_pressed(self, btn):
        return self._curr[btn] == 0

    def just_pressed(self, btn):
        return self._curr[btn] == 0 and self._prev[btn] == 1

    def just_released(self, btn):
        return self._curr[btn] == 1 and self._prev[btn] == 0

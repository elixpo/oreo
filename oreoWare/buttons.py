"""Buttons backend — implements oreoOS.api.Buttons.

Two backends with the same edge logic: GPIOs with pull-ups on the breadboard
badge, and port 0 of the AW9523B expander on the PCB badge (pins.EXPANDER).

Edge detection (just_pressed / just_released) works against the *previous* frame,
so update() must be called exactly once per frame by the OS loop. Apps don't
call update() themselves — they receive a Buttons instance that's already up to
date.
"""

import time

from machine import Pin

from oreoOS import api
from oreoWare import pins


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

# Breadboard tactile switches typically bounce for 2-6 ms. Eight
# milliseconds removes duplicate edges without making a press feel delayed.
DEBOUNCE_MS = 8


class _GpioButtons(api.Buttons):
    def __init__(self):
        self._pins = {b: Pin(g, Pin.IN, Pin.PULL_UP) for b, g in _BTN_TO_GPIO.items()}
        self._button_index = {b: i for i, b in enumerate(api.BUTTONS)}
        self._irq_pending = bytearray(len(api.BUTTONS))
        self._irq_release_pending = bytearray(len(api.BUTTONS))
        self._pressed_edges = bytearray(len(api.BUTTONS))
        self._released_edges = bytearray(len(api.BUTTONS))
        self._last_edge_ms = [0] * len(api.BUTTONS)
        self._irq_handlers = []
        self._curr = {b: 1 for b in _BTN_TO_GPIO}
        self._prev = {b: 1 for b in _BTN_TO_GPIO}
        # Press-timestamp tracking — used by the run loop to synthesize
        # long-press auto-repeat events for navigation buttons (so any
        # scrollable list "just works" with a held UP/DOWN). None means
        # the button is up; an int = time.ticks_ms() at press edge.
        self._press_ms = {b: None for b in _BTN_TO_GPIO}

        # Latch falling edges even while native video inflate/LCD transfer is
        # running. The ISR only flips a preallocated byte; app callbacks and
        # allocations remain in the normal OS loop where they are safe.
        for b, p in self._pins.items():
            idx = self._button_index[b]
            pending = self._irq_pending
            releases = self._irq_release_pending
            def _edge(_pin, _idx=idx, _pending=pending,
                      _releases=releases):
                if _pin.value() == 0:
                    _pending[_idx] = 1
                else:
                    _releases[_idx] = 1
            self._irq_handlers.append(_edge)
            try:
                p.irq(trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING, handler=_edge)
            except Exception:
                pass

    def update(self):
        now = time.ticks_ms()
        for b, p in self._pins.items():
            idx = self._button_index[b]
            latched = self._irq_pending[idx]
            self._irq_pending[idx] = 0
            released = self._irq_release_pending[idx]
            self._irq_release_pending[idx] = 0
            self._step(b, idx, latched, released, p.value(), now)

    def _step(self, b, idx, latched, released, v, now):
        """One button's edge detection for this frame. v is its level now
        (0 = down); latched / released are edges caught by an IRQ since the
        last frame."""
        self._prev[b] = self._curr[b]
        self._pressed_edges[idx] = 0
        self._released_edges[idx] = 0

        elapsed = time.ticks_diff(now, self._last_edge_ms[idx])
        # IRQ latching preserves taps that occur during a display flush.
        # Polling the current level is the fallback when IRQ is absent.
        wants_press = bool(latched) or (v == 0 and self._curr[b] == 1)
        wants_release = (bool(released) or
                         (v == 1 and self._curr[b] == 0))

        if (wants_press and self._curr[b] == 1 and
                elapsed >= DEBOUNCE_MS):
            self._curr[b] = 0
            self._pressed_edges[idx] = 1
            self._last_edge_ms[idx] = now
            self._press_ms[b] = now
        elif (wants_release and self._curr[b] == 0 and
              elapsed >= DEBOUNCE_MS):
            self._curr[b] = 1
            self._released_edges[idx] = 1
            self._last_edge_ms[idx] = now
            self._press_ms[b] = None

    def raw_pressed(self):
        """The api button ids down right now, read straight from the pins
        (used by oreoOS.power while the run loop is paused)."""
        return [b for b, p in self._pins.items() if p.value() == 0]

    def is_pressed(self, btn):
        return self._curr[btn] == 0

    def just_pressed(self, btn):
        return bool(self._pressed_edges[self._button_index[btn]])

    def just_released(self, btn):
        return bool(self._released_edges[self._button_index[btn]])

    def pressed_for_ms(self, btn):
        """Milliseconds the button has been held, or 0 if currently up.

        Read by the OS run loop to fire auto-repeat events on navigation
        buttons. Cheap to call every frame — pure arithmetic on the
        cached press timestamp.
        """
        t = self._press_ms.get(btn)
        if t is None:
            return 0
        return time.ticks_diff(time.ticks_ms(), t)


# The expander's port 0 order (pins.EXP_BUTTON_ORDER) as api button ids.
_EXP_BUTTONS = tuple(getattr(api, "BTN_" + n) for n in pins.EXP_BUTTON_ORDER)
# Re-read the expander at least this often even without an interrupt, in
# case an edge on ~INT was missed.
EXP_POLL_MS = 50


class _ExpanderButtons(_GpioButtons):
    """The PCB badge: the buttons are port 0 of the AW9523B, read over I2C.

    The expander pulls ~INT (pins.EXP_INT) low when a button changes; an IRQ
    on that pin only sets a flag, and update() reads port 0 (one I2C read)
    when the flag is set, while ~INT is still low, or every EXP_POLL_MS.
    A tap that starts and ends inside one long display flush is seen as a
    press at the next read only if the button is still down; the breadboard
    backend's per-pin IRQs catch those."""

    def __init__(self):
        from oreoWare import aw9523
        self._exp = aw9523.get()
        self._button_index = {b: i for i, b in enumerate(api.BUTTONS)}
        self._pressed_edges = bytearray(len(api.BUTTONS))
        self._released_edges = bytearray(len(api.BUTTONS))
        self._last_edge_ms = [0] * len(api.BUTTONS)
        self._curr = {b: 1 for b in _EXP_BUTTONS}
        self._prev = {b: 1 for b in _EXP_BUTTONS}
        self._press_ms = {b: None for b in _EXP_BUTTONS}
        self._port = 0xFF
        self._last_read_ms = 0
        self._int_flag = bytearray(1)
        self._int_pin = None
        try:
            self._int_pin = Pin(pins.EXP_INT, Pin.IN)   # 10 kΩ pull-up on the board
            flag = self._int_flag

            def _int(_pin, _flag=flag):
                _flag[0] = 1
            self._int_handler = _int
            self._int_pin.irq(trigger=Pin.IRQ_FALLING, handler=_int)
        except Exception:
            pass
        self._read()

    def _read(self):
        if self._exp is None:
            # The expander didn't answer at boot (an I2C glitch): keep asking,
            # or the badge would have no buttons until a reboot.
            try:
                from oreoWare import aw9523
                self._exp = aw9523.get()
            except Exception:
                self._exp = None
            if self._exp is None:
                return
        try:
            self._port = self._exp.read_buttons()
        except Exception:
            pass                    # keep the last state; retry next frame
        self._last_read_ms = time.ticks_ms()

    def raw_pressed(self):
        """The api button ids down right now, read straight from the chip."""
        self._read()
        return [b for n, b in enumerate(_EXP_BUTTONS) if not (self._port >> n) & 1]

    def update(self):
        now = time.ticks_ms()
        due = time.ticks_diff(now, self._last_read_ms) >= EXP_POLL_MS
        low = False
        if self._int_pin is not None:
            try:
                low = self._int_pin.value() == 0
            except Exception:
                pass
        if self._int_flag[0] or low or due:
            self._int_flag[0] = 0
            self._read()
        port = self._port
        for n, b in enumerate(_EXP_BUTTONS):
            self._step(b, self._button_index[b], 0, 0, (port >> n) & 1, now)

Buttons = _ExpanderButtons if getattr(pins, "EXPANDER", False) else _GpioButtons

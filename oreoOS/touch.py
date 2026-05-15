"""TTP223 touch-pad gesture helper.

The pad is a single binary line (active-high), so the only gestures
worth detecting are short presses, double-taps within a window, and
long holds. This module turns those raw edges into named events so
apps don't all have to re-implement the same edge detection.

Usage in an app's update(dt):

    from oreoOS import touch
    ev = touch.poll(self._os)
    if ev == touch.TAP:           ...
    elif ev == touch.DOUBLE_TAP:  ...
    elif ev == touch.LONG_HOLD:   ...

Returns touch.NONE on every other frame. Callers don't need to track
state — this module owns the state machine on the OS singleton.

The home screen / launcher use double-tap to open the most-recent app
even when the pad is otherwise reserved for sleep-wake. Other apps can
ignore touch entirely (the events still fire harmlessly).
"""

import time

try:
    from machine import Pin
except ImportError:
    Pin = None

from oreoWare import pins


NONE        = 0
TAP         = 1
DOUBLE_TAP  = 2
LONG_HOLD   = 3

# Tunables — all in ms.
TAP_MAX_MS         = 250    # press shorter than this counts as a tap
DOUBLE_TAP_GAP_MS  = 350    # max gap between two taps to count as a double
LONG_HOLD_MS       = 800    # press held longer than this fires LONG_HOLD


# Module-level state. We don't put this on `os_obj` because the same
# Pin object can be shared across apps + the launcher and they'd all
# stomp each other.
_pin       = None
_pressed_t = 0           # ticks_ms when the current press started; 0 = idle
_released_t= 0           # ticks_ms when the previous tap ended (for double)
_long_fired= False       # don't fire LONG_HOLD twice per press


def _get_pin():
    global _pin
    if _pin is None and Pin is not None:
        try:
            _pin = Pin(pins.TOUCH_OUT, Pin.IN)
        except Exception:
            _pin = None
    return _pin


def poll(os_obj=None):
    """Return one of NONE / TAP / DOUBLE_TAP / LONG_HOLD per frame.

    Call once per frame in update(dt). On a frame where the user did
    nothing, returns NONE. Stateful — calls must be at frame cadence.
    """
    global _pressed_t, _released_t, _long_fired

    p = _get_pin()
    if p is None:
        return NONE
    now = time.ticks_ms()
    try:
        held = p.value() == 1
    except Exception:
        return NONE

    if held:
        # First sample of a new press → record start time.
        if _pressed_t == 0:
            _pressed_t  = now
            _long_fired = False
        # Long-hold fires once when threshold crossed.
        elif not _long_fired and \
             time.ticks_diff(now, _pressed_t) >= LONG_HOLD_MS:
            _long_fired = True
            return LONG_HOLD
        return NONE

    # Released branch — was the press a tap?
    if _pressed_t == 0:
        return NONE
    duration   = time.ticks_diff(now, _pressed_t)
    was_long   = _long_fired
    _pressed_t = 0
    _long_fired = False
    if was_long or duration > TAP_MAX_MS:
        # Long press already announced, OR press too long to count as tap.
        return NONE

    # Check for double-tap (second tap within DOUBLE_TAP_GAP_MS of the previous).
    if _released_t and time.ticks_diff(now, _released_t) <= DOUBLE_TAP_GAP_MS:
        _released_t = 0
        return DOUBLE_TAP

    _released_t = now
    return TAP


def reset():
    """Forget any in-flight press. Call when transitioning into/out of an
    app whose touch semantics differ (e.g. an app that uses LONG_HOLD
    extensively wants the next app to start with a clean state)."""
    global _pressed_t, _released_t, _long_fired
    _pressed_t  = 0
    _released_t = 0
    _long_fired = False

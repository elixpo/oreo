"""Power manager - drives the badge into low-power states when idle.

Lifecycle (all timers reset by ANY input event: button, IMU motion, touch):

    ACTIVE      normal frame loop, backlight 100%
        |
        | idle_seconds elapsed without an event
        v
    DEEP_SLEEP  CPU + RAM powered down (RTC alive), ~20 uA
                Wake sources we configure:
                  * any matrix button (ext1)
                  * TOUCH_OUT high pulse from the TTP223 (ext1)

The intermediate "screen-off / light-sleep" tier from the original power
plan is intentionally NOT implemented here. Reason: with the dead onboard
LDO we cannot reliably hold WiFi during light-sleep, and the extra UI tier
adds complexity without much battery win once the RAM is preserved by
deep-sleep RTC memory. Easy to add later.

Settings persisted on the device's RTC memory survive deep sleep:
    settings_get('idle_enable')   -> bool
    settings_get('idle_seconds')  -> int, default 120
    settings_get('touch_wake')    -> bool, default True

Apps can opt out for one frame by setting `BLOCK_IDLE = True` as a class
attribute (the racer does this so the inactivity timer never fires
mid-race even though no buttons are pressed).
"""

import time

try:
    import machine
except ImportError:
    machine = None

from oreoWare import pins


DEFAULT_IDLE_SECONDS = 120
SETTINGS = {
    "idle_enable":  True,
    "idle_seconds": DEFAULT_IDLE_SECONDS,
    "touch_wake":   True,
}


def load_settings(os_obj):
    """Pull persisted settings off the OS object if any were stored."""
    for k, default in SETTINGS.items():
        v = os_obj.settings_get(k, None)
        if v is not None:
            SETTINGS[k] = v


def save_settings(os_obj):
    for k, v in SETTINGS.items():
        os_obj.settings_set(k, v)


class PowerManager:
    """Polled from the main app loop, calls deepsleep() when idle elapses."""

    def __init__(self, os_obj):
        self._os         = os_obj
        self._last_event = time.ticks_ms()
        load_settings(os_obj)

    # ── public hooks the run loop calls ──────────────────────────────────
    def note_event(self):
        """Reset the idle clock. Called on any button press / motion."""
        self._last_event = time.ticks_ms()

    def tick(self, app):
        """Once per frame. Triggers deep sleep when the threshold elapses."""
        if not SETTINGS["idle_enable"]:
            return
        if getattr(app, "BLOCK_IDLE", False):
            self._last_event = time.ticks_ms()
            return
        idle_ms = SETTINGS["idle_seconds"] * 1000
        if time.ticks_diff(time.ticks_ms(), self._last_event) >= idle_ms:
            self.enter_deep_sleep()

    # ── transitions ──────────────────────────────────────────────────────
    def enter_deep_sleep(self):
        """Save state, configure wake sources, and call machine.deepsleep().

        Returns nothing - the chip resets out of this function. Next boot
        starts main.py from scratch; reset_cause() == DEEPSLEEP_RESET lets
        boot() decide to skip the splash for a faster wake.
        """
        if machine is None:                # build-host fallback
            return
        try:
            self._os.display.set_brightness(0)
        except Exception:
            pass
        # Wake mask: every matrix button + (optionally) the touch pad.
        wake_pins = [
            pins.BTN_HOME, pins.BTN_A, pins.BTN_B, pins.BTN_C,
            pins.BTN_UP, pins.BTN_DOWN, pins.BTN_LEFT, pins.BTN_RIGHT,
        ]
        # Matrix buttons are active-low (pulled up). They wake on FALLING edge.
        # TTP223 OUT is active-high → wakes on RISING edge. We configure both
        # via esp32.wake_on_ext1 with the right level mask.
        try:
            import esp32
            # First: buttons - any one going LOW (esp32.WAKEUP_ALL_LOW)
            button_mask = 0
            for p in wake_pins:
                button_mask |= (1 << p)
            esp32.wake_on_ext1(pins=[machine.Pin(p) for p in wake_pins],
                               level=esp32.WAKEUP_ALL_LOW)
            # Touch wake uses ext0 (single pin, edge-sensitive).  Only set
            # up when enabled in settings.
            if SETTINGS["touch_wake"]:
                esp32.wake_on_ext0(pin=machine.Pin(pins.TOUCH_OUT),
                                   level=esp32.WAKEUP_ANY_HIGH)
        except Exception:
            pass
        machine.deepsleep()


# ── reset-cause helper used by launcher.boot() to fast-path wake-from-sleep ──

def woke_from_deep_sleep():
    """True iff the previous reset was deep-sleep wake."""
    if machine is None:
        return False
    try:
        return machine.reset_cause() == machine.DEEPSLEEP_RESET
    except Exception:
        return False

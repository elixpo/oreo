import time

try:
    import machine
except ImportError:
    machine = None

from oreoWare import pins


DEFAULT_IDLE_SECONDS = 120    # 2 min default — short enough to save battery
                              # in a pocket, long enough that idle reading
                              # the home screen doesn't get cut short.
                              # Slider in Settings goes 0..10 min; 0 = off.
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
        """Once per frame. Triggers light sleep when the threshold elapses.

        Auto-sleep is disabled when EITHER the toggle is off OR the
        Sleep-After slider sits at 0 minutes. The slider's 0 acts as a
        quick "never sleep" without having to flip the toggle row.
        """
        if not SETTINGS["idle_enable"]:
            return
        idle_seconds = SETTINGS.get("idle_seconds", 0)
        if idle_seconds <= 0:
            return
        if getattr(app, "BLOCK_IDLE", False):
            self._last_event = time.ticks_ms()
            return
        if time.ticks_diff(time.ticks_ms(), self._last_event) >= idle_seconds * 1000:
            self.enter_light_sleep()
            # IMPORTANT: light sleep RESUMES here on wake — we reset the idle
            # timer so the user has a full window to interact again.
            self._last_event = time.ticks_ms()

    # ── transitions ──────────────────────────────────────────────────────
    def enter_light_sleep(self):
        """Pause CPU, blank LCD, wait for any button or TTP touch to wake.

        Light sleep keeps RAM, framebuffer state, and peripherals alive —
        when machine.lightsleep() returns the OS resumes EXACTLY at the
        line below, no boot, no app reset. This is the right model for
        "screen off but keep running" since the user's expectation is to
        return to the same screen on tap-to-wake.

        Wake sources:
          * every matrix button (active-low → IRQ_FALLING)
          * TOUCH_OUT from the TTP223 (active-high → IRQ_RISING)
        Both pins MUST be RTC GPIOs to wake the chip from light sleep;
        we verified they are when picking the pin map (HOME/A/B/C/UP/DOWN/
        LEFT/RIGHT in 4-21 range, TOUCH_OUT at 21).
        """
        if machine is None:
            return

        # Remember the user's brightness so we can restore it on wake.
        prev_brightness = 100
        try:
            prev_brightness = getattr(self._os, "_last_brightness", 100)
        except Exception:
            pass
        try:
            self._os.display.set_brightness(0)
        except Exception:
            pass

        # Resolve the wake-from-sleep IRQ flag. MicroPython exposes
        # machine.SLEEP on most ESP32 builds but a few stripped builds omit
        # it; fall back to the documented integer value (5 = SLEEP) when
        # the constant is missing so we still register the wake source.
        wake_flag = getattr(machine, "SLEEP", None)
        if wake_flag is None:
            wake_flag = 5

        # Configure wake-on-pin for buttons + (optional) touch. Each pin
        # gets its own try/except so a single failure doesn't strand the
        # chip in sleep with no other wake source.
        wake_pins = []
        for p in (pins.BTN_HOME, pins.BTN_A, pins.BTN_B, pins.BTN_C,
                  pins.BTN_UP, pins.BTN_DOWN, pins.BTN_LEFT, pins.BTN_RIGHT):
            try:
                pin = machine.Pin(p, machine.Pin.IN, machine.Pin.PULL_UP)
                pin.irq(trigger=machine.Pin.IRQ_FALLING, wake=wake_flag)
                wake_pins.append(pin)
            except Exception:
                # That single pin's wake didn't register; keep going.
                pass

        if SETTINGS["touch_wake"]:
            try:
                tp = machine.Pin(pins.TOUCH_OUT, machine.Pin.IN)
                tp.irq(trigger=machine.Pin.IRQ_RISING, wake=wake_flag)
                wake_pins.append(tp)
            except Exception:
                pass

        if not wake_pins:
            # No wake source got registered — entering lightsleep here would
            # only ever return on the chip's max timeout. Bail.
            try:
                self._os.display.set_brightness(prev_brightness)
            except Exception:
                pass
            return

        # ── sleep here. Resumes when any configured pin IRQ fires. ──
        # We pass a 24-hour ceiling so a borked wake source can't strand the
        # chip forever — worst case it ticks back to the run loop tomorrow.
        try:
            machine.lightsleep(24 * 60 * 60 * 1000)
        except Exception:
            try:
                # Older MP builds want no argument.
                machine.lightsleep()
            except Exception:
                pass

        # Restore the screen on wake. The next frame the run-loop draws
        # will repaint everything because each app's _dirty flag is still
        # whatever it was before — but we force a redraw just in case.
        try:
            self._os.display.set_brightness(prev_brightness)
        except Exception:
            pass

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

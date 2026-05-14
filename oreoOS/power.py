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

        # Soft-polled sleep. machine.lightsleep + Pin.irq(wake=) was
        # unreliable on this MicroPython build, so we just blank the LCD
        # and poll at 20 Hz. Pin objects are cached once outside the loop
        # so we don't churn the pin controller every tick.
        #
        # Wake conditions (any one of these breaks the loop):
        #   * a button that was UNPRESSED at sleep entry now reads PRESSED
        #   * the TTP223 pad that was IDLE at sleep entry now reads TOUCHED
        # We snapshot initial state on entry so a stuck press or a finger
        # already on the pad doesn't insta-wake us.
        btn_ids = (pins.BTN_HOME, pins.BTN_A, pins.BTN_B, pins.BTN_C,
                   pins.BTN_UP, pins.BTN_DOWN, pins.BTN_LEFT, pins.BTN_RIGHT)
        btn_pins = {}
        for b in btn_ids:
            try:
                btn_pins[b] = machine.Pin(b, machine.Pin.IN,
                                           machine.Pin.PULL_UP)
            except Exception:
                pass

        touch_pin = None
        if SETTINGS["touch_wake"]:
            try:
                touch_pin = machine.Pin(pins.TOUCH_OUT, machine.Pin.IN)
            except Exception:
                touch_pin = None

        # Initial state snapshot — buttons read HIGH when idle (active-low,
        # pulled-up), TTP reads LOW when no finger (active-high).
        initial_btn = {b: pin.value() for b, pin in btn_pins.items()}
        initial_tp  = touch_pin.value() if touch_pin else 0

        # Safety ceiling: 24 h so a wedged pin can't strand us forever.
        deadline = time.ticks_add(time.ticks_ms(), 24 * 60 * 60 * 1000)

        while True:
            # Any button gone from idle (1) to pressed (0) → single-press wake.
            woke = False
            for b, pin in btn_pins.items():
                if pin.value() == 0 and initial_btn[b] == 1:
                    woke = True
                    break
            if woke:
                break

            # TTP: rising edge from idle to touch → single-tap wake.
            if touch_pin is not None:
                if touch_pin.value() == 1 and initial_tp == 0:
                    break
                # If the user lifted their finger before sleep started
                # measuring, accept the next press: refresh the baseline.
                if touch_pin.value() == 0:
                    initial_tp = 0

            if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
                break
            # 30 ms poll = 33 Hz, snappier than 20 Hz at trivial CPU cost.
            time.sleep_ms(30)

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

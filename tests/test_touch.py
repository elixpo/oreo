"""Host tests for the PCB badge's touch screen: the XPT2046 driver
(oreoWare.touch), the touch events the run loop builds from it
(oreoOS.launcher.touch_step) and their routing to App.on_touch.
"""

import importlib.util
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── oreoWare.touch ──────────────────────────────────────────────────────────

class FakeIrq:
    def __init__(self, level):
        self.level = level

    def value(self):
        return self.level


class FakeSpi:
    """Answers each 3-byte transfer with the next reading for its command."""

    def __init__(self, readings, fail_after=None):
        self.readings = readings          # {command byte: 12-bit value}
        self.calls = []
        self.fail_after = fail_after
        self.xfers = 0

    def init(self, **kw):
        self.calls.append(("init", kw))

    def write_readinto(self, tx, rx):
        self.xfers += 1
        if self.fail_after is not None and self.xfers > self.fail_after:
            raise OSError("bus error")
        v = self.readings[tx[0]] << 3
        rx[0], rx[1], rx[2] = 0, (v >> 8) & 0xFF, v & 0xFF
        self.calls.append(("xfer", tx[0]))


class FakeExpander:
    def __init__(self, log):
        self.log = log

    def set_touch_cs(self, selected):
        self.log.append(("cs", selected))


class TouchDriverTest(unittest.TestCase):
    MODS = ("oreoWare", "oreoWare.pins", "oreoWare.touch")

    def setUp(self):
        self.saved = {k: sys.modules.get(k) for k in self.MODS}
        ow = types.ModuleType("oreoWare")
        ow.__path__ = [str(ROOT / "oreoWare")]
        sys.modules["oreoWare"] = ow
        pins = types.ModuleType("oreoWare.pins")
        pins.BOARD = "breadboard"
        sys.modules["oreoWare.pins"] = pins
        ow.pins = pins
        self.t = _load("oreoWare/touch.py", "oreoWare.touch")

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    def _touch(self, x=2000, y=1000, z1=600, z2=3000, level=0, fail_after=None):
        t = self.t
        spi = FakeSpi({t._CMD_X: x, t._CMD_Y: y, t._CMD_Z1: z1, t._CMD_Z2: z2},
                      fail_after)
        exp = FakeExpander(spi.calls)
        dev = t.Touch(spi, exp, irq=FakeIrq(level), restore_baud=40_000_000,
                      miso="MISO")
        return dev, spi

    def test_corners_map_to_screen_corners(self):
        cal = dict(self.t.DEFAULT_CAL, swap_xy=False, flip_x=False, flip_y=False)
        self.assertEqual(self.t.to_screen(200, 200, cal), (0, 0))
        self.assertEqual(self.t.to_screen(3900, 3900, cal), (319, 239))
        # out-of-range readings clamp to the edge
        self.assertEqual(self.t.to_screen(0, 9999, cal), (0, 239))

    def test_default_calibration_swaps_and_flips(self):
        # swap_xy: raw Y drives screen x; flip_y: raw X high -> top of screen
        self.assertEqual(self.t.to_screen(3900, 200), (0, 0))
        self.assertEqual(self.t.to_screen(200, 3900), (319, 239))

    def test_set_calibration_keeps_missing_keys(self):
        dev, _ = self._touch()
        dev.set_calibration({"flip_x": True})
        cal = dev.calibration()
        self.assertTrue(cal["flip_x"])
        self.assertEqual(cal["x_min"], self.t.DEFAULT_CAL["x_min"])

    def test_no_bus_traffic_while_not_pressed(self):
        dev, spi = self._touch(level=1)
        self.assertIsNone(dev.read())
        self.assertEqual(spi.calls, [])

    def test_read_selects_slows_samples_then_restores(self):
        dev, spi = self._touch()
        self.assertIsNotNone(dev.read_raw())
        self.assertEqual(spi.calls[0], ("init", {"baudrate": self.t.TOUCH_BAUD,
                                                 "miso": "MISO"}))
        self.assertEqual(spi.calls[1], ("cs", True))
        xfers = [c for c in spi.calls if c[0] == "xfer"]
        self.assertEqual(len(xfers), 4 * self.t.SAMPLES)
        self.assertEqual(spi.calls[-2], ("cs", False))
        self.assertEqual(spi.calls[-1], ("init", {"baudrate": 40_000_000}))

    def test_averaged_reading_and_pressure(self):
        dev, _ = self._touch(x=2000, y=1000, z1=600, z2=3000)
        self.assertEqual(dev.read_raw(), (2000, 1000, 600 + 4095 - 3000))

    def test_light_touch_is_ignored_but_bus_is_released(self):
        dev, spi = self._touch(z1=10, z2=4000)       # z = 105 < PRESSURE_MIN
        self.assertIsNone(dev.read())
        self.assertEqual(spi.calls[-2], ("cs", False))
        self.assertEqual(spi.calls[-1], ("init", {"baudrate": 40_000_000}))

    def test_bus_error_returns_none_and_releases_the_bus(self):
        dev, spi = self._touch(fail_after=3)
        self.assertIsNone(dev.read())
        self.assertIn(("cs", False), spi.calls)
        self.assertEqual(spi.calls[-1], ("init", {"baudrate": 40_000_000}))

    def test_read_returns_screen_point(self):
        dev, _ = self._touch(x=3900, y=200)
        self.assertEqual(dev.read(), (0, 0))

    def test_create_is_none_on_the_breadboard(self):
        self.assertIsNone(self.t.create(object()))


# ── oreoOS.launcher.touch_step ──────────────────────────────────────────────

class ScriptedTouch:
    """read() returns the next scripted point (or None), then None."""

    def __init__(self, script):
        self.script = list(script)

    def read(self):
        if not self.script:
            return None
        p = self.script.pop(0)
        if isinstance(p, Exception):
            raise p
        return p


def _launcher_harness():
    import test_c_key_rule as h
    return h


class TouchStepTest(unittest.TestCase):
    def setUp(self):
        self.h = _launcher_harness().GamepadDoubleTapTest("test_first_c_reaches_gamepad_second_opens_panel")
        self.h.setUp()
        self.step = self.h.launcher.touch_step

    def tearDown(self):
        self.h.tearDown()

    def events(self, script):
        t, state, out = ScriptedTouch(script), {}, []
        for _ in range(len(script) + 1):
            ev = self.step(t, state)
            if ev is not None:
                out.append(ev)
        return out

    def test_down_move_up(self):
        self.assertEqual(self.events([(10, 20), (10, 20), (30, 20), None]),
                         [("down", 10, 20), ("move", 30, 20), ("up", 30, 20)])

    def test_small_jitter_is_not_a_move(self):
        self.assertEqual(self.events([(100, 100), (101, 102), (99, 101), None]),
                         [("down", 100, 100), ("up", 100, 100)])

    def test_a_failed_reading_counts_as_lifted(self):
        self.assertEqual(self.events([(5, 5), OSError("bus")]),
                         [("down", 5, 5), ("up", 5, 5)])

    def test_nothing_when_untouched(self):
        self.assertEqual(self.events([None, None]), [])


# ── routing to App.on_touch in run_app ──────────────────────────────────────

class TouchRoutingTest(unittest.TestCase):
    def setUp(self):
        h = _launcher_harness()
        self.h = h.GamepadDoubleTapTest("test_first_c_reaches_gamepad_second_opens_panel")
        self.h.setUp()
        self.mod = h

    def tearDown(self):
        self.h.tearDown()

    def _run(self, touch_script, frames, panel_open=False):
        h, mod = self.h, self.mod
        App = sys.modules["oreoOS.app"].App

        class Recorder(App):
            name = "recorder"

            def __init__(self):
                self.events = []

            def on_enter(self, os_obj):
                pass

            def update(self, dt):
                pass

            def draw(self, d):
                pass

            def on_touch(self, event, x, y):
                self.events.append((event, x, y))

        os_obj = types.SimpleNamespace(
            display=mod._Display(), _quit_requested=False, _launch_request=None,
            _home_marked=True, _power=None, _just_woke=False,
            touch=ScriptedTouch(touch_script))
        os_obj.quit = lambda: setattr(os_obj, "_quit_requested", True)
        os_obj.launch = lambda n: setattr(os_obj, "_launch_request", n)
        os_obj.buttons = mod._Buttons([[]] * frames, os_obj, h.clock)
        h.panel.active = panel_open
        app = Recorder()
        h.launcher.run_app(os_obj, app)
        return app

    def test_app_gets_down_move_up(self):
        app = self._run([(50, 60), (80, 60), None], frames=4)
        self.assertEqual(app.events, [("down", 50, 60), ("move", 80, 60),
                                      ("up", 80, 60)])

    def test_open_panel_keeps_touches_from_the_app(self):
        app = self._run([(50, 60), None], frames=3, panel_open=True)
        self.assertEqual(app.events, [])

    def test_no_reads_while_busy_animates(self):
        busy = types.ModuleType("oreoOS.busy")
        busy.active = lambda: True
        saved = sys.modules.get("oreoOS.busy")
        sys.modules["oreoOS.busy"] = busy
        try:
            app = self._run([(50, 60), (80, 60), None], frames=4)
        finally:
            if saved is None:
                sys.modules.pop("oreoOS.busy", None)
            else:
                sys.modules["oreoOS.busy"] = saved
        self.assertEqual(app.events, [])

    def test_first_frame_is_not_read(self):
        touch = ScriptedTouch([])
        calls = []
        real = touch.read
        touch.read = lambda: calls.append(1) or real()
        h, mod = self.h, self.mod
        App = sys.modules["oreoOS.app"].App
        os_obj = types.SimpleNamespace(
            display=mod._Display(), _quit_requested=False, _launch_request=None,
            _home_marked=True, _power=None, _just_woke=False, touch=touch)
        os_obj.quit = lambda: setattr(os_obj, "_quit_requested", True)
        os_obj.launch = lambda n: setattr(os_obj, "_launch_request", n)
        os_obj.buttons = mod._Buttons([[], [], []], os_obj, h.clock)

        class Plain(App):
            name = "plain"

            def on_enter(self, os_obj):
                pass

            def update(self, dt):
                pass

            def draw(self, d):
                pass
        h.launcher.run_app(os_obj, Plain())
        frames = 4                                  # 3 scripted + the quit frame
        self.assertEqual(len(calls), frames - 1)

    def test_no_touch_screen_changes_nothing(self):
        h, mod = self.h, self.mod
        App = sys.modules["oreoOS.app"].App
        os_obj = types.SimpleNamespace(
            display=mod._Display(), _quit_requested=False, _launch_request=None,
            _home_marked=True, _power=None, _just_woke=False)
        os_obj.quit = lambda: setattr(os_obj, "_quit_requested", True)
        os_obj.launch = lambda n: setattr(os_obj, "_launch_request", n)
        os_obj.buttons = mod._Buttons([[], []], os_obj, h.clock)

        class Plain(App):
            name = "plain"

            def on_enter(self, os_obj):
                pass

            def update(self, dt):
                pass

            def draw(self, d):
                pass

        h.launcher.run_app(os_obj, Plain())   # must not raise


if __name__ == "__main__":
    unittest.main()

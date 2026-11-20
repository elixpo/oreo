"""Host tests for touch calibration (oreoOS/touchcal.py) and its row in
Settings: solving a calibration from four taps in every panel orientation,
the tap state machine, saving, and the Settings flow.
"""

import importlib.util
import itertools
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


class _Mods:
    NAMES = ("oreoWare", "oreoWare.pins", "oreoWare.touch", "oreoOS",
             "oreoOS.touchcal", "oreoOS.state")

    def __init__(self):
        self.saved = {k: sys.modules.get(k) for k in self.NAMES}

    def restore(self):
        for k, v in self.saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _modules():
    ow = types.ModuleType("oreoWare")
    ow.__path__ = [str(ROOT / "oreoWare")]
    sys.modules["oreoWare"] = ow
    pins = types.ModuleType("oreoWare.pins")
    pins.BOARD = "pcb"
    sys.modules["oreoWare.pins"] = pins
    touch = _load("oreoWare/touch.py", "oreoWare.touch")
    cal = _load("oreoOS/touchcal.py", "oreoOS.touchcal")
    return touch, cal


def _raw_for(screen, truth):
    """The raw (x, y) a panel calibrated as `truth` reports at a screen
    point: the inverse of touch.to_screen()."""
    sx, sy = screen
    if truth["flip_x"]:
        sx = 319 - sx
    if truth["flip_y"]:
        sy = 239 - sy
    rx = truth["x_min"] + sx * (truth["x_max"] - truth["x_min"]) / 319
    ry = truth["y_min"] + sy * (truth["y_max"] - truth["y_min"]) / 239
    if truth["swap_xy"]:
        rx, ry = ry, rx
    return int(round(rx)), int(round(ry))


class SolveTest(unittest.TestCase):
    def setUp(self):
        self.mods = _Mods()
        self.touch, self.cal = _modules()

    def tearDown(self):
        self.mods.restore()

    def test_every_orientation_maps_back_to_the_screen(self):
        checks = self.cal.TARGETS + ((160, 120), (5, 230), (310, 8))
        for swap, fx, fy in itertools.product((False, True), repeat=3):
            truth = {"x_min": 310, "x_max": 3790, "y_min": 260, "y_max": 3850,
                     "swap_xy": swap, "flip_x": fx, "flip_y": fy}
            taps = [_raw_for(t, truth) for t in self.cal.TARGETS]
            got = self.cal.solve(taps)
            self.assertIsNotNone(got, truth)
            self.assertEqual(got["swap_xy"], swap)
            for p in checks:
                x, y = self.touch.to_screen(*_raw_for(p, truth), cal=got)
                self.assertLessEqual(abs(x - p[0]), 2, (truth, p, (x, y)))
                self.assertLessEqual(abs(y - p[1]), 2, (truth, p, (x, y)))

    def test_taps_too_close_together_fail(self):
        self.assertIsNone(self.cal.solve([(2000, 2000)] * 4))
        self.assertIsNone(self.cal.solve([(2000, 2000), (2100, 2010),
                                          (2100, 2100), (2000, 2090)]))

    def test_wrong_number_of_points(self):
        self.assertIsNone(self.cal.solve([(0, 0)] * 3))


class FakeTouch:
    """read_raw() plays a script of readings (None = not pressed)."""

    def __init__(self, script=()):
        self.script = list(script)
        self.cal = None

    def read_raw(self):
        return self.script.pop(0) if self.script else None

    def set_calibration(self, cal):
        self.cal = cal


def _taps(points, hold=4):
    """A read_raw script: each point held for `hold` frames, then lifted."""
    out = []
    for x, y in points:
        out += [(x, y, 800)] * hold + [None]
    return out


TAPS = [(400, 400), (3600, 420), (3620, 3500), (380, 3480)]


class CalibrationTest(unittest.TestCase):
    def setUp(self):
        self.mods = _Mods()
        _, self.cal = _modules()

    def tearDown(self):
        self.mods.restore()

    def _run(self, script):
        c = self.cal.Calibration(FakeTouch(script))
        for _ in range(len(script) + 2):
            c.update()
        return c

    def test_four_taps_give_a_calibration(self):
        c = self._run(_taps(TAPS))
        self.assertEqual(c.state, "done")
        self.assertEqual(len(c.points), 4)
        self.assertFalse(c.result["swap_xy"])

    def test_a_brush_is_not_a_tap(self):
        c = self._run([(400, 400, 800), None] + _taps(TAPS[:1]))
        self.assertEqual(c.points, [(400, 400)])
        self.assertEqual(c.state, "target")

    def test_bad_taps_fail(self):
        c = self._run(_taps([(2000, 2000)] * 4))
        self.assertEqual(c.state, "failed")
        self.assertIsNone(c.result)

    def test_redraws_only_when_the_step_changes(self):
        c = self.cal.Calibration(FakeTouch(_taps(TAPS[:1])))
        calls = []
        d = types.SimpleNamespace(clear=lambda *a: calls.append("clear"),
                                  line=lambda *a: None, rect=lambda *a, **k: None,
                                  text=lambda *a, **k: None)
        theme = types.SimpleNamespace(BG=0, PRIMARY=1, TEXT_BRIGHT=2, MUTED=3,
                                      GREEN=4)
        c.draw(d, theme)
        c.draw(d, theme)
        self.assertEqual(calls, ["clear"])
        for _ in range(6):
            c.update()
        c.draw(d, theme)
        self.assertEqual(calls, ["clear", "clear"])

    def test_save_and_load_round_trip(self):
        store = {}
        st = types.ModuleType("oreoOS.state")
        st.load = lambda name, default=None: store.get(name, default)
        st.save = lambda name, data: store.__setitem__(name, data)
        sys.modules["oreoOS.state"] = st
        pkg = types.ModuleType("oreoOS")
        pkg.__path__ = [str(ROOT / "oreoOS")]
        pkg.state = st
        sys.modules["oreoOS"] = pkg
        self.assertIsNone(self.cal.load())
        result = self.cal.solve(TAPS)
        self.assertTrue(self.cal.save(result))
        self.assertEqual(self.cal.load(), result)
        store["touch"] = {"junk": 1}
        self.assertIsNone(self.cal.load())


# ── the Settings row ────────────────────────────────────────────────────────

class SettingsTouchRowTest(unittest.TestCase):
    def setUp(self):
        import test_badge_followups as f
        self.s = f.Stubs()
        self.s.add("oreoOS.netsvc", f.FakeNet())
        self.s.add("oreoWare.wifi", f.FakeWifi())
        self.store = {}
        st = types.ModuleType("oreoOS.state")
        st.load = lambda name, default=None: self.store.get(name, default)
        st.save = lambda name, data: self.store.__setitem__(name, data)
        self.saved_extra = {k: sys.modules.get(k) for k in
                            ("oreoOS.state", "oreoOS.touchcal", "oreoOS.power",
                             "oreoOS.store")}
        self.s.add("oreoOS.state", st)
        sys.modules["oreoOS.power"] = None          # import fails: skipped
        sys.modules.pop("oreoOS.touchcal", None)
        self.m = _load("apps/settings/src/app.py", "under_test")
        self.api = sys.modules["oreoOS.api"]

    def tearDown(self):
        for k, v in self.saved_extra.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
        self.s.close()

    def _app(self, touch):
        os_obj = types.SimpleNamespace(
            touch=touch, _last_brightness=80,
            settings_get=lambda k, d=None: d, settings_set=lambda k, v: None)
        app = self.m.App()
        app.on_enter(os_obj)
        return app

    def _labels(self, app):
        return [r.label for r in app._rows]

    def test_row_only_with_a_touch_screen(self):
        self.assertNotIn("Touch", self._labels(self._app(None)))
        labels = self._labels(self._app(FakeTouch()))
        self.assertIn("Touch", labels)
        self.assertEqual(labels[-3:], ["Touch", "Version", "Reboot"])

    def _open(self, touch):
        app = self._app(touch)
        app._sel = self._labels(app).index("Touch")
        app.on_button_press(self.api.BTN_A)
        self.assertIsNotNone(app._cal)
        return app

    def test_calibrating_saves_and_applies(self):
        touch = FakeTouch(_taps(TAPS))
        app = self._open(touch)
        for _ in range(30):
            app.update(0.016)
        self.assertEqual(app._cal.state, "done")
        self.assertIsNotNone(touch.cal)
        self.assertEqual(self.store["touch"], touch.cal)
        app.on_button_press(self.api.BTN_A)          # any button: back
        self.assertIsNone(app._cal)
        self.assertTrue(app._dirty)

    def test_b_cancels_without_saving(self):
        touch = FakeTouch(_taps(TAPS[:2]))
        app = self._open(touch)
        for _ in range(12):
            app.update(0.016)
        app.on_button_press(self.api.BTN_B)
        self.assertIsNone(app._cal)
        self.assertIsNone(touch.cal)
        self.assertNotIn("touch", self.store)

    def test_failed_then_a_tries_again(self):
        touch = FakeTouch(_taps([(2000, 2000)] * 4))
        app = self._open(touch)
        for _ in range(30):
            app.update(0.016)
        self.assertEqual(app._cal.state, "failed")
        app.on_button_press(self.api.BTN_A)
        self.assertEqual(app._cal.state, "target")
        self.assertEqual(app._cal.points, [])


if __name__ == "__main__":
    unittest.main()

"""Host tests for the OreoOS 2.0 shell UI helpers: the splash greeting
timeline and word-mask renderer, the eased Scroller, and a full splash
run against a fake display and clock.

The oreoOS package __init__ pulls in the launcher (and config), so the
modules under test are loaded from their files behind a stub package
that only carries api + theme.
"""

import importlib.util
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(relative_path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _stub_oreoos():
    """Install a minimal `oreoOS` package (api, theme, pixelfont) and
    return the previous sys.modules entries so tearDown can restore."""
    saved = {k: sys.modules.get(k) for k in
             ("oreoOS", "oreoOS.api", "oreoOS.theme", "oreoOS.pixelfont")}
    pkg = types.ModuleType("oreoOS")
    pkg.__path__ = [str(ROOT / "oreoOS")]
    sys.modules["oreoOS"] = pkg
    api = _load("oreoOS/api.py", "oreoOS.api")
    pkg.api = api
    theme = _load("oreoOS/theme.py", "oreoOS.theme")
    pkg.theme = theme
    pf = _load("oreoOS/pixelfont.py", "oreoOS.pixelfont")
    pkg.pixelfont = pf
    return saved


def _restore(saved):
    for k, v in saved.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v


class FakeClock:
    def __init__(self):
        self.t = 0

    def ticks_ms(self):
        return self.t

    def ticks_diff(self, a, b):
        return a - b

    def sleep_ms(self, ms):
        self.t += ms


class FakeDisplay:
    """Records calls; keeps a real RGB565 BE row buffer so blit_rows /
    copy_rows behave like the badge backend."""

    def __init__(self, sw, sh):
        self.sw, self.sh = sw, sh
        self.buf = bytearray(sw * sh * 2)
        self.calls = []
        self.presented = []

    def _log(self, *a):
        self.calls.append(a)

    def clear(self, color=0):
        self._log("clear")

    def rect(self, x, y, w, h, color, fill=False):
        self._log("rect", x, y, w, h)

    def text(self, s, x, y, color=0xFFFF, scale=1):
        self._log("text", s, x, y, scale)

    def blit(self, data, x, y, w, h):
        self._log("blit", x, y, w, h)

    def blit_mono(self, mask, x, y, w, h, color):
        self._log("blit_mono", x, y, w, h, color)

    def copy_rows(self, y, h):
        s = self.sw * 2
        return bytearray(self.buf[y * s:(y + h) * s])

    def blit_rows(self, src, y, h, src_y=0):
        s = self.sw * 2
        self.buf[y * s:(y + h) * s] = src[src_y * s:(src_y + h) * s]
        self._log("blit_rows", y, h)

    def present(self):
        self.presented.append(None)

    def present_rect(self, x, y, w, h):
        assert 0 <= y and y + h <= self.sh, (y, h)
        assert 0 <= x and x + w <= self.sw, (x, w)
        self.presented.append((x, y, w, h))

    def set_brightness(self, pct):
        self._log("bright", pct)


class SplashHelpersTest(unittest.TestCase):
    def setUp(self):
        self.saved = _stub_oreoos()
        self.sp = _load("oreoOS/splash.py", "oreoOS.splash")

    def tearDown(self):
        sys.modules.pop("oreoOS.splash", None)
        _restore(self.saved)

    def test_timeline_cycles_words_and_fades(self):
        sp = self.sp
        idx, a, dy = sp.greet_frame(0)
        self.assertEqual((idx, a, dy), (0, 0.0, sp.GREET_SLIDE))
        idx, a, dy = sp.greet_frame(sp.GREET_IN_MS + 10)
        self.assertEqual((idx, a, dy), (0, 1.0, 0))
        idx, a, dy = sp.greet_frame(sp.GREET_CYCLE_MS - 1)
        self.assertEqual(idx, 0)
        self.assertLess(a, 0.05)
        self.assertLess(dy, 0)
        idx, _, _ = sp.greet_frame(sp.GREET_CYCLE_MS)
        self.assertEqual(idx, 1)
        idx, _, _ = sp.greet_frame(sp.GREET_CYCLE_MS * len(sp.GREETINGS))
        self.assertEqual(idx, 0)

    def test_words_fit_the_band(self):
        sp = self.sp
        font = _load("assets/fonts/optimized/pixelify_24.py", "pf24_under_test")
        mask = bytearray(sp._MASK_STRIDE * font.GLYPH_H)
        for w in sp.GREETINGS:
            for ch in w:
                self.assertIn(ch, font._FONT)
            width = sp.build_word_mask(w, font._FONT, font.GLYPH_W,
                                       font.GLYPH_H, font.BPR, font.KERN,
                                       {}, mask, sp._MASK_STRIDE)
            self.assertLessEqual(width, sp._CLEAR_X1 - sp._CLEAR_X0, w)

    def test_mask_matches_per_pixel_render(self):
        sp = self.sp
        font = _load("assets/fonts/optimized/pixelify_24.py", "pf24_under_test")
        gw, gh, bpr, kern = font.GLYPH_W, font.GLYPH_H, font.BPR, font.KERN
        stride = sp._MASK_STRIDE
        for word in ("hello", "konnichiwa", "nomoshkar"):
            mask = bytearray(stride * gh)
            width = sp.build_word_mask(word, font._FONT, gw, gh, bpr, kern,
                                       {}, mask, stride)
            # Reference: the PixelFont renderer's layout, pixel by pixel.
            ref = set()
            x = (stride * 8 - width) // 2
            for ch in word:
                bits = font._FONT[ch]
                lo, adv = sp.glyph_extent(bits, gw, gh, bpr)
                for row in range(gh):
                    for col in range(gw):
                        if bits[row * bpr + (col >> 3)] & (0x80 >> (col & 7)):
                            ref.add((x + col - lo, row))
                x += adv + kern
            got = set()
            for row in range(gh):
                for px in range(stride * 8):
                    if mask[row * stride + (px >> 3)] & (0x80 >> (px & 7)):
                        got.add((px, row))
            self.assertEqual(got, ref, word)

    def test_lerp565_endpoints(self):
        sp = self.sp
        self.assertEqual(sp.lerp565(0x0000, 0xFFFF, 0.0), 0x0000)
        self.assertEqual(sp.lerp565(0x0000, 0xFFFF, 1.0), 0xFFFF)
        mid = sp.lerp565(0x0000, 0xFFFF, 0.5)
        self.assertEqual((mid >> 11) & 0x1F, 15)

    def test_full_splash_run_on_fake_display(self):
        sp = self.sp
        clock = FakeClock()
        sp.time = clock
        sp._get_bg = lambda: None            # procedural backdrop path
        sp._get_splash_logo = lambda: None
        os_obj = types.SimpleNamespace(display=FakeDisplay(sp.SW, sp.SH))
        s = sp.Splash(os_obj)
        s.intro()
        self.assertGreaterEqual(clock.t, sp.INTRO_MS)
        for i in range(60):                  # ~ a wifi connect, 80 ms pumps
            self.assertFalse(s.pump())
            clock.t += 80
            if i == 20:
                s.progress(0.5)
        s.finish()
        self.assertGreaterEqual(clock.t, sp.MIN_TOTAL_MS)
        d = os_obj.display
        monos = [c for c in d.calls if c[0] == "blit_mono"]
        self.assertTrue(monos, "greeting never drawn")
        # every greeting frame flushes only its band, never the full screen
        bands = [p for p in d.presented if p and p[1] == sp._BAND_Y]
        self.assertTrue(all(p[3] == sp._BAND_H for p in bands))
        self.assertEqual(d.presented.count(None), 1)   # only the backdrop
        self.assertEqual(s._bar_pos, 1.0)
        self.assertIsNone(s._snap)           # released


class ScrollerTest(unittest.TestCase):
    def setUp(self):
        self.saved = _stub_oreoos()
        self.w = _load("oreoOS/widgets.py", "oreoOS.widgets")

    def tearDown(self):
        sys.modules.pop("oreoOS.widgets", None)
        _restore(self.saved)

    def test_glides_and_lands_exactly(self):
        s = self.w.Scroller(0, dur=0.2)
        s.set_target(100)
        seen = []
        while s.step(1 / 30.0):
            seen.append(s.value)
        self.assertEqual(s.value, 100)
        self.assertEqual(seen, sorted(seen))       # monotonic
        self.assertGreater(seen[0], 10)            # ease-out: fast start
        self.assertFalse(s.moving())

    def test_retarget_mid_glide_continues_from_current(self):
        s = self.w.Scroller(0, dur=0.2)
        s.set_target(100)
        s.step(0.05)
        here = s.pos
        s.set_target(200)
        s.step(0.0001)
        self.assertAlmostEqual(s.pos, here, delta=1.0)

    def test_snap(self):
        s = self.w.Scroller(0)
        s.set_target(50, snap=True)
        self.assertEqual(s.value, 50)
        self.assertFalse(s.step(0.1))


class NotifPanelTest(unittest.TestCase):
    def setUp(self):
        self.saved = _stub_oreoos()
        sys.modules["oreoOS"].widgets = _load("oreoOS/widgets.py", "oreoOS.widgets")
        self.np = _load("oreoOS/notif_panel.py", "oreoOS.notif_panel")
        self.clock = FakeClock()
        self.np.time = self.clock
        sys.modules["oreoOS.widgets"]._time = None
        self.d = FakeDisplay(320, 240)
        self.os = types.SimpleNamespace(
            display=self.d, _last_brightness=40, launched=None,
            settings_get=lambda k, default=None: default)
        self.os.launch = lambda name: setattr(self.os, "launched", name)

    def tearDown(self):
        for k in ("oreoOS.notif_panel", "oreoOS.widgets"):
            sys.modules.pop(k, None)
        _restore(self.saved)

    def _open(self, p):
        p.toggle()
        for _ in range(10):
            p.tick(0.05)
        self.assertTrue(p.covers_screen())

    def test_hotkey_allowed(self):
        np = self.np

        class Plain:
            pass

        class Captures:
            CAPTURES_C = True

        self.assertTrue(np.hotkey_allowed(Plain()))
        self.assertFalse(np.hotkey_allowed(Captures()))
        inst = Plain()
        inst.CAPTURES_C = True            # runtime opt-in on the instance
        self.assertFalse(np.hotkey_allowed(inst))

    def test_quick_nav_grid(self):
        np, api = self.np, sys.modules["oreoOS.api"]
        self.assertEqual(np.quick_nav(np.Q_WIFI, api.BTN_DOWN), np.Q_UPDATE)
        self.assertEqual(np.quick_nav(np.Q_TORCH, api.BTN_DOWN), np.Q_SETTINGS)
        self.assertIsNone(np.quick_nav(np.Q_UPDATE, api.BTN_DOWN))
        self.assertEqual(np.quick_nav(np.Q_SETTINGS, api.BTN_UP), np.Q_TORCH)
        self.assertEqual(np.quick_nav(np.Q_SETTINGS, api.BTN_RIGHT), np.Q_WIFI)

    def test_full_height_and_torch_round_trip(self):
        np, api = self.np, sys.modules["oreoOS.api"]
        p = np.NotifPanel(self.os)
        self._open(p)
        p.draw(self.d)
        fills = [c for c in self.d.calls if c[0] == "rect"]
        self.assertIn(("rect", 0, 0, 320, 240), fills)   # full-height backdrop
        # Fully open + nothing changed → no repaint.
        self.d.calls.clear()
        p.draw(self.d)
        self.assertEqual(self.d.calls, [])
        # Torch: RIGHT, RIGHT, A.
        for b in (api.BTN_RIGHT, api.BTN_RIGHT, api.BTN_A):
            p.handle_button(b)
        self.assertTrue(p.torch_on())
        self.assertTrue(p.keeps_awake())
        self.assertIn(("bright", 100), self.d.calls)
        self.d.calls.clear()
        p.draw(self.d)
        self.assertEqual(self.d.calls, [("rect", 0, 0, 320, 240)])
        p.handle_button(api.BTN_A)                    # ignored
        self.assertTrue(p.torch_on())
        p.handle_button(api.BTN_HOME)
        self.assertFalse(p.torch_on())
        self.assertFalse(p.is_active())
        self.assertIn(("bright", 40), self.d.calls)
        self.assertEqual(self.os._last_brightness, 40)
        self.assertTrue(p.consume_closed())
        self.assertFalse(p.consume_closed())

    def test_c_toggle_also_leaves_torch(self):
        api = sys.modules["oreoOS.api"]
        p = self.np.NotifPanel(self.os)
        self._open(p)
        p._quick_sel = self.np.Q_TORCH
        p.handle_button(api.BTN_A)
        p.toggle()                                    # run loop's C path
        self.assertFalse(p.torch_on())
        self.assertFalse(p.is_active())

    def test_update_tile_launches_updates(self):
        api = sys.modules["oreoOS.api"]
        p = self.np.NotifPanel(self.os)
        self._open(p)
        p.handle_button(api.BTN_DOWN)                 # WiFi → Update
        p.handle_button(api.BTN_A)
        self.assertEqual(self.os.launched, "updates")
        self.assertFalse(p.is_active())


if __name__ == "__main__":
    unittest.main()

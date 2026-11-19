"""Host tests for the PCB badge support: board detection (oreoWare.board),
the PCB pin map (oreoWare.pins), the AW9523B expander (oreoWare.aw9523),
the expander buttons (oreoWare.buttons), the ILI9341 panel
(oreoWare._ili9341), and the panel choice in oreoOS.hostui.
"""

import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class _Saved:
    def __init__(self, names):
        self.saved = {k: sys.modules.get(k) for k in names}

    def restore(self):
        for k, v in self.saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


MODS = ("machine", "oreoWare", "oreoWare.board", "oreoWare.pins",
        "oreoWare.aw9523", "oreoWare.buttons", "oreoWare._ili9341",
        "oreoWare._st7789", "oreoOS", "oreoOS.api", "oreoOS.hostui", "framebuf")


class FakePin:
    IN, OUT, PULL_UP = 0, 1, 2
    IRQ_FALLING, IRQ_RISING = 4, 8
    made = []
    level = 1

    def __init__(self, n, *a, **k):
        self.n = n
        FakePin.made.append((n, a))

    def value(self, v=None):
        return FakePin.level

    def irq(self, **k):
        self.handler = k.get("handler")

    def __call__(self, v=None):
        return None


def _machine(i2c_cls=None):
    m = types.ModuleType("machine")
    m.Pin = FakePin
    if i2c_cls is not None:
        m.SoftI2C = i2c_cls
    m.SPI = object
    return m


def _oreoware_pkg():
    ow = types.ModuleType("oreoWare")
    ow.__path__ = [str(ROOT / "oreoWare")]
    return ow


# ── oreoWare.board ──────────────────────────────────────────────────────────

class BoardTest(unittest.TestCase):
    def setUp(self):
        self.saved = _Saved(MODS)
        sys.modules["oreoWare"] = _oreoware_pkg()
        FakePin.made = []

    def tearDown(self):
        self.saved.restore()

    def _board(self, i2c_cls, override=None):
        if i2c_cls is None:
            sys.modules["machine"] = None
        else:
            sys.modules["machine"] = _machine(i2c_cls)
        b = _load("oreoWare/board.py", "oreoWare.board")
        tmp = tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt")
        if override is not None:
            tmp.write(override)
        tmp.close()
        b.OVERRIDE_FILE = tmp.name if override is not None else tmp.name + ".missing"
        self.addCleanup(os.unlink, tmp.name)
        return b

    @staticmethod
    def _i2c(answer):
        class I2C:
            def __init__(self, **k):
                self.k = k

            def readfrom_mem(self, addr, reg, n):
                if isinstance(answer, Exception):
                    raise answer
                assert (addr, reg, n) == (0x58, 0x10, 1)
                return bytes([answer])
        return I2C

    def test_host_without_machine_is_breadboard(self):
        self.assertEqual(self._board(None).board(), "breadboard")

    def test_chip_id_means_pcb(self):
        b = self._board(self._i2c(0x23))
        self.assertEqual(b.board(), "pcb")
        self.assertTrue(b.is_pcb())

    def test_wrong_id_or_no_answer_is_breadboard_and_frees_the_pins(self):
        # A held LEFT button reads SDA low: a zero byte, not the ID.
        for answer in (0x00, 0xFF, OSError("ENODEV")):
            FakePin.made = []
            b = self._board(self._i2c(answer))
            self.assertEqual(b.board(), "breadboard")
            self.assertIn((6, (FakePin.IN, FakePin.PULL_UP)), FakePin.made)
            self.assertIn((7, (FakePin.IN, FakePin.PULL_UP)), FakePin.made)

    def test_probe_is_quick_and_needs_two_good_reads(self):
        made = []

        class I2C:
            answers = [0x23, 0x00]           # one stray ID, then not

            def __init__(self, **k):
                made.append(k)

            def readfrom_mem(self, addr, reg, n):
                return bytes([I2C.answers.pop(0)])
        b = self._board(I2C)
        self.assertEqual(b.board(), "breadboard")
        # 1 ms clock-stretch timeout, not SoftI2C's default 50 ms
        self.assertEqual(made[0].get("timeout"), 1000)

    def test_override_file_wins_and_is_cached(self):
        b = self._board(self._i2c(OSError()), override="PCB\n")
        self.assertEqual(b.board(), "pcb")
        b.OVERRIDE_FILE = "/nonexistent"
        self.assertEqual(b.board(), "pcb")          # decided once per boot
        b2 = self._board(self._i2c(0x23), override="bogus")
        self.assertEqual(b2.board(), "pcb")         # unknown text: probe


# ── oreoWare.pins ──────────────────────────────────────────────────────────

def _load_pins(board_name):
    ow = _oreoware_pkg()
    sys.modules["oreoWare"] = ow
    board = types.ModuleType("oreoWare.board")
    board.board = lambda: board_name
    sys.modules["oreoWare.board"] = board
    ow.board = board
    pins = _load("oreoWare/pins.py", "oreoWare.pins")
    ow.pins = pins
    return pins


class PinsTest(unittest.TestCase):
    def setUp(self):
        self.saved = _Saved(MODS)

    def tearDown(self):
        self.saved.restore()

    def test_breadboard_pins_unchanged(self):
        p = _load_pins("breadboard")
        self.assertEqual((p.BOARD, p.DISPLAY_DRIVER, p.EXPANDER), ("breadboard", "st7789", False))
        self.assertEqual((p.I2C_SDA, p.I2C_SCL, p.IMU_INT), (42, 47, 3))
        self.assertEqual((p.BTN_HOME, p.BTN_LEFT, p.BTN_RIGHT), (9, 6, 7))
        self.assertEqual((p.I2S_BCLK, p.I2S_LRCLK, p.I2S_DOUT), (41, 21, 46))

    def test_pcb_pin_map(self):
        p = _load_pins("pcb")
        self.assertEqual((p.BOARD, p.DISPLAY_DRIVER, p.EXPANDER), ("pcb", "ili9341", True))
        # Same as the breadboard: display, microSD, IR, status LED, battery.
        self.assertEqual((p.DISPLAY_MOSI, p.DISPLAY_SCK, p.DISPLAY_CS, p.DISPLAY_DC,
                          p.DISPLAY_RESET, p.DISPLAY_BL), (11, 12, 14, 15, 16, 17))
        self.assertEqual((p.SD_CLK, p.SD_CMD, p.SD_D0), (38, 39, 40))
        self.assertEqual((p.IR_TX, p.IR_RX, p.LED_STATUS, p.ADC_VBAT), (2, 18, 48, 1))
        # Moved on the PCB (circuit/elixpo/README.md, Pin map).
        self.assertEqual((p.I2C_SDA, p.I2C_SCL, p.EXP_INT, p.IMU_INT), (6, 7, 3, 4))
        self.assertEqual((p.I2S_BCLK, p.I2S_LRCLK, p.I2S_DOUT), (8, 9, 10))
        self.assertEqual((p.DISPLAY_MISO, p.TOUCH_IRQ, p.EXP_ADDR), (13, 21, 0x58))
        self.assertEqual(p.EXPANSION, (5, 41, 42, 47))
        self.assertIsNone(p.BTN_HOME)
        self.assertEqual(p.EXP_BUTTON_ORDER,
                         ("UP", "DOWN", "LEFT", "RIGHT", "A", "B", "C", "HOME"))
        self.assertEqual((p.EXP_AMP_EN, p.EXP_SD_DET, p.EXP_AUX_ON_N, p.EXP_TOUCH_CS),
                         (0x10, 0x20, 0x40, 0x80))

    def test_pcb_pins_match_the_schematic(self):
        sch = (ROOT / "circuit" / "elixpo" / "generate_badge_schematic.py").read_text()
        for gpio, net in (("IO6", "I2C_SDA"), ("IO7", "I2C_SCL"), ("IO3", "EXP_INT"),
                          ("IO4", "IMU_INT"), ("IO21", "TOUCH_IRQ")):
            self.assertRegex(sch, r'\("%s", \d+, "%s"\)' % (gpio, net))
        p = _load_pins("pcb")
        for n, name in enumerate(p.EXP_BUTTON_ORDER):
            self.assertIn('("P0_%d", %d, "BTN_%s")' % (n, n + 5 if n < 4 else n + 6, name), sch)


# ── oreoWare.aw9523 ────────────────────────────────────────────────────────

class FakeBus:
    def __init__(self, port0=0xFF, port1=0xFF):
        self.writes = []
        self.regs = {0x00: port0, 0x01: port1, 0x10: 0x23}

    def writeto_mem(self, addr, reg, buf):
        assert addr == 0x58
        self.writes.append((reg, buf[0]))

    def readfrom_mem_into(self, addr, reg, buf):
        buf[0] = self.regs.get(reg, 0)


class AW9523Test(unittest.TestCase):
    def setUp(self):
        self.saved = _Saved(MODS)
        _load_pins("pcb")
        self.mod = _load("oreoWare/aw9523.py", "oreoWare.aw9523")

    def tearDown(self):
        self.saved.restore()

    def test_init_never_lights_a_corner_led_as_a_gpio(self):
        bus = FakeBus()
        dev = self.mod.AW9523(bus)
        dev.init()
        order = [r for r, _v in bus.writes]
        w = dict(bus.writes)
        # LED pins held high (off) and their current zero before LED mode.
        self.assertLess(order.index(0x03), order.index(0x13))
        for dim in (0x20, 0x21, 0x22, 0x23):
            self.assertEqual(w[dim], 0)
            self.assertLess(order.index(dim), order.index(0x13))
        self.assertEqual(w[0x03] & 0x0F, 0x0F)
        self.assertEqual(w[0x13] & 0x0F, 0x00)      # P1_0-3 in LED mode
        self.assertEqual(w[0x13] & 0xF0, 0xF0)      # P1_4-7 GPIO
        # AUX on (P1_6 low), touch deselected (P1_7 high), amp off.
        self.assertEqual(w[0x03] & 0xF0, 0x80)
        self.assertEqual(w[0x05], 0x20)             # only SD_DET is an input on port 1
        self.assertEqual((w[0x04], w[0x06], w[0x07]), (0xFF, 0x00, 0xFF))
        for reg, v in bus.writes:
            if reg == 0x03:
                self.assertEqual(v & 0x0F, 0x0F)

    def test_outputs_and_inputs(self):
        bus = FakeBus(port0=0b11101110, port1=0x00)
        dev = self.mod.AW9523(bus)
        dev.init()
        bus.writes.clear()
        dev.set_amp(True)
        dev.set_aux(False)
        dev.set_touch_cs(True)
        dev.set_amp(True)                           # unchanged: no write
        self.assertEqual(bus.writes, [(0x03, 0x9F), (0x03, 0xDF), (0x03, 0x5F)])
        bus.writes.clear()
        dev.set_led(self.mod.LED_BR, 300)
        dev.set_led(9, 10)                          # no such LED: ignored
        self.assertEqual(bus.writes, [(0x23, 255)])
        self.assertEqual(dev.read_buttons(), 0b11101110)
        self.assertTrue(dev.card_present())
        self.assertEqual(dev.chip_id(), 0x23)

    def test_get_is_none_on_the_breadboard(self):
        _load_pins("breadboard")
        mod = _load("oreoWare/aw9523.py", "oreoWare.aw9523")
        self.assertIsNone(mod.get())


# ── oreoWare.buttons (expander backend) ────────────────────────────────────

class FakeClock:
    def __init__(self):
        self.t = 1000

    def ticks_ms(self):
        return self.t

    def ticks_diff(self, a, b):
        return a - b

    def ticks_add(self, a, b):
        return a + b


class FakeExpander:
    def __init__(self):
        self.port = 0xFF
        self.reads = 0

    def read_buttons(self):
        self.reads += 1
        return self.port


class ExpanderButtonsTest(unittest.TestCase):
    def setUp(self):
        self.saved = _Saved(MODS)
        sys.modules["machine"] = _machine()
        pins = _load_pins("pcb")
        pkg = types.ModuleType("oreoOS")
        pkg.__path__ = [str(ROOT / "oreoOS")]
        sys.modules["oreoOS"] = pkg
        self.api = _load("oreoOS/api.py", "oreoOS.api")
        pkg.api = self.api
        self.exp = FakeExpander()
        aw = types.ModuleType("oreoWare.aw9523")
        aw.get = lambda: self.exp
        sys.modules["oreoWare.aw9523"] = aw
        sys.modules["oreoWare"].aw9523 = aw
        self.mod = _load("oreoWare/buttons.py", "oreoWare.buttons")
        self.clock = FakeClock()
        self.mod.time = self.clock
        FakePin.level = 1                          # ~INT idle high
        self.assertIs(self.mod.Buttons, self.mod._ExpanderButtons)
        self.b = self.mod.Buttons()
        self.pins = pins

    def tearDown(self):
        self.saved.restore()

    def _frame(self, port, ms=20, irq=True):
        self.exp.port = port
        if irq:
            self.b._int_flag[0] = 1
        self.clock.t += ms
        self.b.update()

    def test_press_and_release_from_port0(self):
        api = self.api
        a_bit = self.pins.EXP_BUTTON_ORDER.index("A")
        self._frame(0xFF & ~(1 << a_bit))
        self.assertTrue(self.b.just_pressed(api.BTN_A))
        self.assertTrue(self.b.is_pressed(api.BTN_A))
        self.assertFalse(self.b.is_pressed(api.BTN_B))
        self._frame(0xFF & ~(1 << a_bit))
        self.assertFalse(self.b.just_pressed(api.BTN_A))
        self.assertGreater(self.b.pressed_for_ms(api.BTN_A), 0)
        self._frame(0xFF)
        self.assertTrue(self.b.just_released(api.BTN_A))
        self.assertFalse(self.b.is_pressed(api.BTN_A))

    def test_every_bit_maps_to_its_button(self):
        for n, name in enumerate(self.pins.EXP_BUTTON_ORDER):
            self._frame(0xFF & ~(1 << n))
            btn = getattr(self.api, "BTN_" + name)
            self.assertTrue(self.b.just_pressed(btn), name)
            self.assertEqual(self.b.raw_pressed(), [btn])
            self._frame(0xFF)

    def test_reads_only_on_interrupt_or_poll(self):
        start = self.exp.reads
        self._frame(0xFF, ms=10, irq=False)
        self.assertEqual(self.exp.reads, start)          # idle: no I2C
        self._frame(0xFF, ms=10, irq=True)
        self.assertEqual(self.exp.reads, start + 1)       # ~INT fired
        self._frame(0xFF, ms=self.mod.EXP_POLL_MS, irq=False)
        self.assertEqual(self.exp.reads, start + 2)       # safety poll

    def test_expander_missing_at_boot_is_retried(self):
        api = self.api
        aw = sys.modules["oreoWare.aw9523"]
        aw.get = lambda: None                        # no answer during boot
        b = self.mod.Buttons()
        self.assertIsNone(b._exp)
        aw.get = lambda: self.exp                    # the bus recovers
        a_bit = self.pins.EXP_BUTTON_ORDER.index("A")
        self.exp.port = 0xFF & ~(1 << a_bit)
        b._int_flag[0] = 1
        self.clock.t += 20
        b.update()                                   # asks again, then reads
        self.assertIs(b._exp, self.exp)
        self.assertTrue(b.just_pressed(api.BTN_A))

    def test_debounce(self):
        api = self.api
        a = ~(1 << self.pins.EXP_BUTTON_ORDER.index("A")) & 0xFF
        self._frame(a)
        self._frame(0xFF, ms=2)                          # bounce: ignored
        self.assertTrue(self.b.is_pressed(api.BTN_A))
        self._frame(0xFF, ms=20)
        self.assertFalse(self.b.is_pressed(api.BTN_A))


# ── oreoWare._ili9341 ──────────────────────────────────────────────────────

class RecordingSPI:
    def __init__(self):
        self.log = []
        self.dc_level = 0

    def write(self, data):
        self.log.append((self.dc_level, bytes(data)))


class ILI9341Test(unittest.TestCase):
    def setUp(self):
        self.saved = _Saved(MODS)
        sys.modules["machine"] = _machine()
        self.mod = _load("oreoWare/_ili9341.py", "oreoWare._ili9341")
        self.mod.time = types.SimpleNamespace(sleep_ms=lambda ms: None)

    def tearDown(self):
        self.saved.restore()

    def _panel(self):
        spi = RecordingSPI()

        def dc(v):
            spi.dc_level = v
        p = self.mod.ILI9341(spi, dc=dc, cs=lambda v: None, rst=lambda v: None,
                             bl=lambda v: None)
        return p, spi

    def _commands(self, spi):
        cmds = {}
        last = None
        for level, data in spi.log:
            if level == 0:
                last = data[0]
                cmds.setdefault(last, [])
            else:
                cmds[last].append(data)
        return cmds

    def test_init_is_landscape_rgb565_without_inversion(self):
        p, spi = self._panel()
        p.init()
        cmds = self._commands(spi)
        self.assertIn(0x01, cmds)                        # software reset
        self.assertEqual(cmds[0x36], [bytes([self.mod.MADCTL_LANDSCAPE])])
        self.assertEqual(self.mod.MADCTL_LANDSCAPE & 0x20, 0x20)   # MV: landscape
        self.assertEqual(cmds[0x3A], [b"\x55"])          # 16 bpp
        self.assertEqual(cmds[0x2A], [b"\x00\x00\x01\x3F"])        # 320 columns
        self.assertEqual(cmds[0x2B], [b"\x00\x00\x00\xEF"])        # 240 rows
        self.assertNotIn(0x21, cmds)                     # TN panel: no inversion
        order = [d[0] for level, d in spi.log if level == 0]
        self.assertLess(order.index(0x11), order.index(0x29))      # sleep out, then on

    def test_resume_has_no_reset(self):
        p, spi = self._panel()
        p.resume()
        self.assertNotIn(0x01, self._commands(spi))

    def test_same_interface_as_st7789(self):
        p, spi = self._panel()
        for attr in ("init", "resume", "set_window", "fill", "bl", "cs", "dc", "spi",
                     "_ramwr_cmd"):
            self.assertTrue(hasattr(p, attr), attr)
        self.assertEqual(p._ramwr_cmd, b"\x2C")
        p.set_window(1, 2, 300, 200)
        cmds = self._commands(spi)
        self.assertEqual(cmds[0x2A][-1], bytes([0, 1, 1, 44]))
        self.assertEqual(cmds[0x2B][-1], bytes([0, 2, 0, 200]))


# ── oreoOS.hostui picks the panel ──────────────────────────────────────────

class HostUiPanelTest(unittest.TestCase):
    def setUp(self):
        self.saved = _Saved(MODS)

    def tearDown(self):
        self.saved.restore()

    def _panel_class(self, driver):
        made = []

        class Panel:
            def __init__(self, *a, **k):
                made.append(type(self).__name__)

            def resume(self):
                pass

            def bl(self, v):
                pass

        class ST7789(Panel):
            pass

        class ILI9341(Panel):
            pass

        m = _machine()
        m.SPI = lambda *a, **k: None
        sys.modules["machine"] = m
        ow = types.ModuleType("oreoWare")
        ow.__path__ = []
        sys.modules["oreoWare"] = ow
        pins = types.ModuleType("oreoWare.pins")
        for k, v in dict(DISPLAY_CS=14, DISPLAY_RESET=16, DISPLAY_DC=15, DISPLAY_MOSI=11,
                         DISPLAY_SCK=12, DISPLAY_BL=17, DISPLAY_BAUD=40000000).items():
            setattr(pins, k, v)
        if driver:
            pins.DISPLAY_DRIVER = driver
        st = types.ModuleType("oreoWare._st7789")
        st.ST7789 = ST7789
        il = types.ModuleType("oreoWare._ili9341")
        il.ILI9341 = ILI9341
        sys.modules.update({"oreoWare.pins": pins, "oreoWare._st7789": st,
                            "oreoWare._ili9341": il})
        ow.pins, ow._st7789, ow._ili9341 = pins, st, il
        ui = _load("oreoOS/hostui.py", "oreoOS.hostui")
        ui._panel()
        return made

    def test_pcb_uses_ili9341(self):
        self.assertEqual(self._panel_class("ili9341"), ["ILI9341"])

    def test_breadboard_and_older_pins_use_st7789(self):
        self.assertEqual(self._panel_class("st7789"), ["ST7789"])
        self.assertEqual(self._panel_class(None), ["ST7789"])


if __name__ == "__main__":
    unittest.main()


# ── oreoWare.os: the expander is set up before the display ─────────────────

class OsInitOrderTest(unittest.TestCase):
    NAMES = ("oreoOS", "oreoOS.api", "oreoOS.state", "oreoWare", "oreoWare.pins",
             "oreoWare.display", "oreoWare.buttons", "oreoWare.aw9523",
             "oreoWare.touch", "oreoWare.os")

    def setUp(self):
        self.saved = _Saved(self.NAMES)

    def tearDown(self):
        self.saved.restore()

    def _os(self, board):
        order = []
        pkg = types.ModuleType("oreoOS")
        pkg.__path__ = [str(ROOT / "oreoOS")]
        sys.modules["oreoOS"] = pkg
        pkg.api = _load("oreoOS/api.py", "oreoOS.api")
        st = types.ModuleType("oreoOS.state")
        st.load = lambda name, default=None: default
        st.save = lambda name, data: None
        sys.modules["oreoOS.state"] = pkg.state = st
        ow = _oreoware_pkg()
        sys.modules["oreoWare"] = ow
        mods = {
            "pins": {"BOARD": board},
            "display": {"Display": lambda: order.append("display") or types.SimpleNamespace()},
            "buttons": {"Buttons": lambda: order.append("buttons") or object()},
            "aw9523": {"get": lambda: order.append("expander") or object()},
            "touch": {"create": lambda d: None},
        }
        for name, attrs in mods.items():
            m = types.ModuleType("oreoWare." + name)
            for k, v in attrs.items():
                setattr(m, k, v)
            sys.modules["oreoWare." + name] = m
            setattr(ow, name, m)
        os_mod = _load("oreoWare/os.py", "oreoWare.os")
        os_mod.OS()
        return order

    def test_pcb_sets_up_the_expander_first(self):
        order = self._os("pcb")
        self.assertEqual(order[:2], ["expander", "display"])

    def test_breadboard_never_touches_the_expander(self):
        self.assertNotIn("expander", self._os("breadboard"))

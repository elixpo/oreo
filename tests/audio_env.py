"""Shared host stand-ins for the audio tests: the real oreoOS and oreoWare
modules the audio stack uses (api, theme, state, mediaui, player, audio),
loaded from their files, with stubs for the hardware and the parts that
draw fonts or start threads (widgets, cache), plus fake I2S, expander,
display, socket and MP3 decoder.

    env = audio_env.Env(tmpdir)        # installs the modules
    app_mod = env.load_app("apps_market/radio", "radio")
    ...
    env.close()                        # restores sys.modules
"""

import importlib
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_KEYS = ("oreoOS", "oreoWare", "apps")


class FakeI2S:
    TX = 1
    MONO = 0
    instances = []

    def __init__(self, ident, sck=None, ws=None, sd=None, mode=None, bits=None,
                 format=None, rate=None, ibuf=None):
        self.args = dict(sck=sck, ws=ws, sd=sd, mode=mode, bits=bits, format=format,
                         rate=rate, ibuf=ibuf)
        self.rate = rate
        self.writes = []
        self.cb = None
        self.closed = False
        FakeI2S.instances.append(self)

    def irq(self, cb):
        self.cb = cb

    def write(self, buf):
        self.writes.append(bytes(buf))
        return len(buf)

    def deinit(self):
        self.closed = True

    def fire(self, n=1):
        """n transfers complete (the scheduled callback runs)."""
        for _ in range(n):
            if self.cb is not None and not self.closed:
                self.cb(self)


class FakeExpander:
    def __init__(self):
        self.amp = False
        self.log = []

    def set_amp(self, on):
        self.amp = on
        self.log.append(on)


class FakeDisplay:
    def __init__(self):
        self.texts = []

    def clear(self, color=0):
        self.texts = []

    def rect(self, *a, **k):
        pass

    def text(self, s, x, y, color=0, scale=1):
        self.texts.append(str(s))

    def present(self):
        pass

    def joined(self):
        return "\n".join(self.texts)


class FakeOS:
    def __init__(self, audio=None):
        self.display = FakeDisplay()
        self.audio = audio
        self.quit_called = False
        self.settings = {}

    def quit(self):
        self.quit_called = True

    def settings_get(self, k, d=None):
        return self.settings.get(k, d)

    def settings_set(self, k, v):
        self.settings[k] = v


class FakeSock:
    """A connected socket: replies with `data` (bytes) in pieces of at most
    `piece` bytes; after the data, EOF (or timeouts when `hang`)."""

    def __init__(self, data, piece=700, hang=False):
        self.data = bytearray(data)
        self.piece = piece
        self.hang = hang
        self.sent = bytearray()
        self.closed = False

    def settimeout(self, t):
        pass

    def write(self, b):
        self.sent.extend(b)
        return len(b)

    def readinto(self, mv):
        if not self.data:
            if self.hang:
                raise OSError(110)
            return 0
        n = min(len(mv), self.piece, len(self.data))
        mv[:n] = self.data[:n]
        del self.data[:n]
        return n

    def close(self):
        self.closed = True


class FakeNet:
    """connect(host, port, tls, timeout) for the player: replies[host] is a
    list of FakeSocks handed out in turn (or exceptions to raise)."""

    def __init__(self, replies):
        self.replies = replies
        self.calls = []
        self.socks = []

    def __call__(self, host, port, tls, timeout):
        self.calls.append((host, port, tls))
        r = self.replies[host].pop(0)
        if isinstance(r, Exception):
            raise r
        self.socks.append(r)
        return r


class FakeDecoder:
    """Stands in for _oreo_audio.MP3Decoder: the "MP3" is raw int16 PCM at
    `hz`, so tests can follow every sample through the player."""

    def __init__(self, hz=22050):
        self.hz = hz
        self.frames = 0
        self.closed = False
        self.resets = 0

    def decode(self, data, pcm, flush=False):
        n = min(len(data), len(pcm)) & ~1
        pcm[:n] = bytes(data[:n])
        if n:
            self.frames += 1
        return n, n // 2, self.hz if n else 0, 1

    def info(self):
        return (self.hz, 1, 64, self.frames, 0)

    def reset(self):
        self.resets += 1

    def deinit(self):
        self.closed = True


def http_reply(body, status="200 OK", headers=()):
    head = "HTTP/1.0 %s\r\n" % status
    for k, v in headers:
        head += "%s: %s\r\n" % (k, v)
    return head.encode() + b"\r\n" + body


class SyncRefresh:
    """oreoOS.cache.Refresh without a thread: fn runs at start()."""

    IDLE, RUNNING, DONE = 0, 1, 2
    log = []

    def __init__(self, fn):
        self.fn = fn
        self.state = 0
        self.result = None
        self.error = None

    def busy(self):
        return self.state == 1

    def start(self, use_thread=True):
        SyncRefresh.log.append(self)
        try:
            self.result = self.fn()
        except Exception as e:
            self.result = None
            self.error = str(e)
        self.state = 2
        return True

    def poll(self):
        if self.state == 2:
            self.state = 0
            return True
        return False


class Env:
    def __init__(self, state_dir, board="pcb"):
        self.saved = {k: v for k, v in sys.modules.items()
                      if k.split(".")[0] in _KEYS}
        for k in list(self.saved):
            del sys.modules[k]
        ow = types.ModuleType("oreoWare")
        ow.__path__ = [str(ROOT / "oreoWare")]
        sys.modules["oreoWare"] = ow
        pins = types.ModuleType("oreoWare.pins")
        pins.BOARD = board
        pins.I2S_BCLK, pins.I2S_LRCLK, pins.I2S_DOUT = 8, 9, 10
        sys.modules["oreoWare.pins"] = pins
        ow.pins = pins
        oo = types.ModuleType("oreoOS")
        oo.__path__ = [str(ROOT / "oreoOS")]
        sys.modules["oreoOS"] = oo
        widgets = types.ModuleType("oreoOS.widgets")
        widgets.HEADER_H, widgets.HINT_H = 28, 16
        widgets.draw_header = lambda d, title, *a, **k: d.text(title, 0, 0)
        widgets.draw_hint = lambda d, text, *a, **k: d.text(text, 0, 230)
        widgets.draw_panel = lambda *a, **k: None
        sys.modules["oreoOS.widgets"] = widgets
        oo.widgets = widgets
        cache = types.ModuleType("oreoOS.cache")
        cache.Refresh = SyncRefresh
        sys.modules["oreoOS.cache"] = cache
        oo.cache = cache
        self.api = importlib.import_module("oreoOS.api")
        oo.api = self.api
        oo.theme = importlib.import_module("oreoOS.theme")
        self.state = importlib.import_module("oreoOS.state")
        self.state.STATE_DIR = str(state_dir)
        oo.state = self.state
        oo.App = importlib.import_module("oreoOS.app").App
        self.audio = importlib.import_module("oreoWare.audio")
        self.audio._native = None
        self.player = importlib.import_module("oreoOS.player")
        oo.player = self.player
        self.mediaui = importlib.import_module("oreoOS.mediaui")
        oo.mediaui = self.mediaui
        apps = types.ModuleType("apps")
        apps.__path__ = []
        sys.modules["apps"] = apps
        FakeI2S.instances = []
        SyncRefresh.log = []

    def make_audio(self, available=True):
        exp = FakeExpander()
        a = self.audio.Audio(expander=exp, i2s_class=FakeI2S, available=available)
        return a, exp

    def load_app(self, folder, app_id):
        """Import <folder>/src/app.py as apps.<app_id>.src.app."""
        pkg = types.ModuleType("apps." + app_id)
        pkg.__path__ = [str(ROOT / folder)]
        sys.modules["apps." + app_id] = pkg
        return importlib.import_module("apps.%s.src.app" % app_id)

    def close(self):
        for k in [k for k in sys.modules if k.split(".")[0] in _KEYS]:
            del sys.modules[k]
        sys.modules.update(self.saved)

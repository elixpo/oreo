"""Speaker output on the PCB badge: MAX98357A I2S amp, mono, 16-bit.

The amp takes BCLK / LRCLK / DIN on pins.I2S_BCLK / I2S_LRCLK / I2S_DOUT
(GPIO 8 / 9 / 10 on the PCB) and its SD_MODE is the AW9523B's P1_4
(pins.EXP_AMP_EN, high = on). The amp is powered only between start() and
the end of stop(), so it draws nothing while the badge is quiet.

    a = os.audio
    if a.available:
        a.start(22050)              # silence first, then the amp
        n = a.write(pcm, 22050)     # bytes taken (int16 mono); never blocks
        a.volume = 60               # 0-100, software gain
        a.stop()                    # fade out, silence, amp off, I2S off

write() copies into a ring buffer (in PSRAM: it is an ordinary bytearray)
and returns how much fitted; it never waits. The ring is drained by
machine.I2S in non-blocking mode: each finished transfer schedules
_on_sent() on the main thread, which hands I2S the next CHUNK bytes. When
the ring runs dry it sends silence, so the I2S DMA never replays stale
samples and the chain of callbacks never stops while started. Sample-rate
changes, the amp and I2S itself are only touched on the main thread (from
start/stop and the callback), never from a player's worker thread, so the
expander's I2C bus is never used by two threads at once.

No pops: start() runs I2S with silence before the amp is switched on and
fades the first samples in; stop() fades the last samples out, sends
silence until the DMA buffers hold nothing else, and only then turns the
amp off and releases I2S.

On the breadboard badge (or with no expander answering) `available` is
False and every method is a harmless no-op.
"""

try:
    import time
    _ticks_ms = time.ticks_ms
except AttributeError:          # CPython host tests
    import time

    def _ticks_ms():
        return int(time.monotonic() * 1000)

try:
    import _oreo_audio as _native        # firmware/usermods/oreo_audio
except ImportError:
    _native = None

from oreoWare import pins

I2S_ID = 0
DEFAULT_RATE = 22050
RING_BYTES = 64 * 1024     # ~1.5 s at 22050 Hz, 0.74 s at 44100 Hz
CHUNK = 2048               # bytes per I2S write: 46 ms at 22050 Hz
IBUF = 12 * 1024           # I2S DMA buffering: the main loop may stall this long
FADE_STEPS = 8
RATES = (8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000)

STOPPED, STARTING, RUNNING, STOPPING = 0, 1, 2, 3


class Ring:
    """Single-producer, single-consumer byte ring.

    One thread writes and one reads; each side moves only its own index,
    after its copy, so the two never need a lock. Indexes run modulo
    2 * size, which tells a full ring from an empty one.
    """

    def __init__(self, size):
        self.size = size
        self.buf = bytearray(size)
        self.mv = memoryview(self.buf)
        self._w = 0
        self._r = 0

    def used(self):
        return (self._w - self._r) % (2 * self.size)

    def free(self):
        return self.size - self.used()

    def clear(self):
        self._r = self._w

    def write(self, data):
        """Copy as much of data as fits; returns the bytes taken."""
        n = min(len(data), self.free())
        if n <= 0:
            return 0
        src = memoryview(data)
        pos = self._w % self.size
        first = min(n, self.size - pos)
        self.mv[pos:pos + first] = src[:first]
        if n > first:
            self.mv[0:n - first] = src[first:n]
        self._w = (self._w + n) % (2 * self.size)
        return n

    def read_into(self, dst, n=None):
        """Move up to n bytes (default len(dst)) into dst; returns how many."""
        want = len(dst) if n is None else n
        n = min(want, self.used())
        if n <= 0:
            return 0
        pos = self._r % self.size
        first = min(n, self.size - pos)
        out = memoryview(dst)
        out[:first] = self.mv[pos:pos + first]
        if n > first:
            out[first:n] = self.mv[0:n - first]
        self._r = (self._r + n) % (2 * self.size)
        return n


def gain_q16(volume):
    """Volume 0-100 as a gain in 1/65536: a square law, so the steps sound
    even (half the volume is a quarter of the amplitude)."""
    v = max(0, min(100, int(volume)))
    return (v * v * 65536) // 10000


def apply_gain(buf, q16, n=None):
    """Scale int16 samples in buf[:n bytes] by q16 / 65536."""
    if q16 >= 65536:
        return
    mv = memoryview(buf)
    if n is not None:
        mv = mv[:n]
    if _native is not None:
        _native.gain(mv, q16)
        return
    import struct                   # slow path: firmware without _oreo_audio
    for i in range(0, len(mv) - 1, 2):
        v = struct.unpack_from("<h", mv, i)[0]
        struct.pack_into("<h", mv, i, (v * q16) >> 16)


def fade(buf, n, start_q16, end_q16):
    """Ramp the gain of buf[:n bytes] from start_q16 to end_q16 in steps."""
    n &= ~1
    if n <= 0:
        return
    step = ((n // 2) // FADE_STEPS) * 2 or n
    mv = memoryview(buf)
    i = 0
    k = 0
    while i < n:
        j = min(n, i + step)
        g = start_q16 + (end_q16 - start_q16) * k // FADE_STEPS
        apply_gain(mv[i:j], max(0, min(65536, g)))
        i = j
        k += 1


class Audio:
    def __init__(self, expander=None, i2s_class=None, available=None):
        if available is None:
            available = getattr(pins, "BOARD", "") == "pcb"
        self._exp = expander
        self._i2s_class = i2s_class
        self.available = bool(available)
        self.rate = DEFAULT_RATE
        self._want_rate = None
        self._volume = 70
        self._gain = gain_q16(70)
        self.state = STOPPED
        self._i2s = None
        self._amp = False
        self._ring = None
        self._chunk = None
        self._silence_left = 0
        self._fade_in = False
        self.underruns = 0
        self._last_data_ms = 0

    # ── setup ───────────────────────────────────────────────────────────
    def _expander(self):
        if self._exp is None:
            try:
                from oreoWare import aw9523
                self._exp = aw9523.get()
            except Exception:
                self._exp = None
        return self._exp

    def _set_amp(self, on):
        if on == self._amp:
            return
        exp = self._expander()
        if exp is not None:
            try:
                exp.set_amp(on)
            except Exception:
                pass
        self._amp = on

    def _buffers(self):
        if self._ring is None:
            self._ring = Ring(RING_BYTES)
            self._chunk = bytearray(CHUNK)

    def _open_i2s(self, rate):
        cls = self._i2s_class
        if cls is None:
            from machine import I2S as cls      # noqa: N813
            from machine import Pin
            sck, ws, sd = Pin(pins.I2S_BCLK), Pin(pins.I2S_LRCLK), Pin(pins.I2S_DOUT)
        else:
            sck, ws, sd = pins.I2S_BCLK, pins.I2S_LRCLK, pins.I2S_DOUT
        i2s = cls(I2S_ID, sck=sck, ws=ws, sd=sd, mode=cls.TX, bits=16,
                  format=cls.MONO, rate=rate, ibuf=IBUF)
        i2s.irq(self._on_sent)
        self._i2s = i2s
        self.rate = rate

    def _close_i2s(self):
        if self._i2s is not None:
            try:
                self._i2s.irq(None)
            except Exception:
                pass
            try:
                self._i2s.deinit()
            except Exception:
                pass
            self._i2s = None

    # ── public ──────────────────────────────────────────────────────────
    @property
    def started(self):
        return self.state in (STARTING, RUNNING)

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, v):
        self._volume = max(0, min(100, int(v)))
        self._gain = gain_q16(self._volume)

    def set_volume(self, v):
        self.volume = v

    def set_rate(self, hz):
        """Use hz from the next sample on. Applied on the main thread once
        the samples already queued at the old rate have played."""
        if hz not in RATES:
            raise ValueError("unsupported sample rate %r" % (hz,))
        if hz != self.rate:
            self._want_rate = hz

    def start(self, rate=None):
        """Open I2S (silence), then switch the amp on. Main thread only."""
        if not self.available:
            return False
        if rate is not None:
            self.set_rate(rate)
        if self.state == STOPPING:
            # Still draining from a stop(): keep I2S, just carry on.
            self.state = RUNNING
            self._set_amp(True)
            return True
        if self.started:
            return True
        self._buffers()
        if self._want_rate:
            self.rate, self._want_rate = self._want_rate, None
        try:
            self._open_i2s(self.rate)
        except Exception:
            self._close_i2s()
            return False
        self.state = STARTING
        # Silence fills the DMA first; the amp comes on in _on_sent once
        # it is clocking zeros, and the first real samples fade in.
        self._silence_left = 2
        self._fade_in = True
        self._send()
        return True

    def stop(self):
        """Fade out and power down. Returns at once; the amp turns off from
        the I2S callback after the DMA has played out its silence."""
        if not self.available or self.state in (STOPPED, STOPPING):
            return
        if self.state == STARTING:
            self._ring.clear()
            self._finish()
            return
        self.state = STOPPING
        # Fade what is about to play, drop the rest, then send silence
        # until everything in the DMA buffers is zeros.
        self._fade_out_head()
        self._silence_left = IBUF // CHUNK + 2

    def write(self, data, rate=None):
        """Queue int16 mono samples; returns the bytes taken (an even
        number), 0 while a different rate waits to be applied. Never
        blocks; safe from a worker thread."""
        if not self.available:
            return 0
        self._buffers()
        if rate is not None and rate != self.rate:
            if self._want_rate != rate:
                self.set_rate(rate)
            if self._ring.used() or self.started:
                return 0                # the callback switches once drained
            self.rate, self._want_rate = rate, None
        n = len(data) & ~1
        n = min(n, self._ring.free() & ~1)
        if n <= 0:
            return 0
        self._last_data_ms = _ticks_ms()
        return self._ring.write(memoryview(data)[:n])

    def free(self):
        """Bytes write() would take now."""
        if not self.available:
            return 0
        self._buffers()
        return self._ring.free() & ~1

    def buffered(self):
        """Bytes queued and not yet handed to I2S."""
        return self._ring.used() if self._ring is not None else 0

    def buffered_ms(self):
        return self.buffered() * 500 // max(1, self.rate)

    def flush(self):
        """Drop queued samples (station change): silence follows."""
        if self._ring is not None:
            self._ring.clear()

    def deinit(self):
        self.flush()
        self._finish()
        self._ring = None
        self._chunk = None

    # ── the I2S side (main thread) ──────────────────────────────────────
    def _fade_out_head(self):
        """Fade the next CHUNK of queued samples to zero, drop the rest."""
        r = self._ring
        if r is None:
            return
        n = r.read_into(self._chunk, CHUNK) & ~1
        r.clear()
        if n:
            fade(self._chunk, n, self._gain, 0)
            for i in range(n, CHUNK):
                self._chunk[i] = 0
            self._pending_tail = True
        else:
            self._pending_tail = False

    def _send(self):
        """Hand I2S the next CHUNK: queued samples, else silence."""
        c = self._chunk
        if getattr(self, "_pending_tail", False):
            self._pending_tail = False          # the faded-out chunk
        elif self.state == RUNNING and self._ring.used():
            n = self._ring.read_into(c, CHUNK) & ~1
            if n < CHUNK:
                self.underruns += 1
                for i in range(n, CHUNK):
                    c[i] = 0
            if self._fade_in:
                fade(c, n, 0, self._gain)
                self._fade_in = False
            else:
                apply_gain(c, self._gain, n)
        else:
            for i in range(CHUNK):
                c[i] = 0
        self._i2s.write(c)

    def _finish(self):
        self._set_amp(False)
        self._close_i2s()
        self.state = STOPPED

    def _on_sent(self, _i2s=None):
        """I2S finished a write (scheduled on the main thread)."""
        if self._i2s is None:
            return
        if self.state == STARTING:
            self._silence_left -= 1
            if self._silence_left <= 0:
                self._set_amp(True)
                self.state = RUNNING
        elif self.state == STOPPING:
            self._silence_left -= 1
            if self._silence_left <= 0:
                self._finish()
                return
        elif self.state == RUNNING and self._want_rate and not self._ring.used():
            # Old-rate samples have all gone out: switch rates with the amp
            # muted so the clock change is not heard.
            rate, self._want_rate = self._want_rate, None
            self._set_amp(False)
            self._close_i2s()
            try:
                self._open_i2s(rate)
            except Exception:
                self.state = STOPPED
                return
            self.state = STARTING
            self._silence_left = 2
            self._fade_in = True
        self._send()


_audio = None


def get():
    """The badge's one Audio object (available only on the PCB badge)."""
    global _audio
    if _audio is None:
        _audio = Audio()
    return _audio

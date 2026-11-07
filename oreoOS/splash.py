"""Boot splash and the OTA "updating" screen, 320x240 landscape.

Boot splash: the logo sits top left, "hello" rolls through languages in
the middle (each word in its own script, anti-aliased), with a small
"OreoOS" under it. The artwork is pre-rendered by tools/build_splash.py
into oreoOS/splash.bin, already blended onto the background, so drawing
is only row copies into the framebuffer and one SPI write per frame.

The roll runs on its own thread, so it keeps moving while boot imports
modules and starts the radios; boot code never has to call into it.

    sp = Splash(os_obj)
    sp.intro()          # first frame, starts the animation thread
    ...boot work...
    sp.finish()         # waits for a minimum show time and a word boundary

Without _thread (or without splash.bin) it degrades to pump() calls or a
static frame. Splash must never break boot: every method swallows errors.
"""

import struct
import time
from oreoOS import api
from oreoOS import theme

SW = api.SCREEN_W
SH = api.SCREEN_H

BIN_PATH     = "oreoOS/splash.bin"
LOGO_X       = 12
LOGO_Y       = 12
TAG_GAP      = 2            # px between the greeting band and "OreoOS"

HOLD_MS      = 850          # a word rests in place
ROLL_MS      = 380          # the roll to the next word
CYCLE_MS     = HOLD_MS + ROLL_MS
FRAME_MS     = 15           # animation thread tick
MIN_TOTAL_MS = 2600         # finish() never returns earlier than this
FINISH_MAX_MS = 1500        # extra wait for a word boundary, at most


def _ms():
    return time.ticks_ms()


def _diff(a, b):
    return time.ticks_diff(a, b)


def ease(p):
    """Ease-in-out cubic, 0..1 -> 0..1."""
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    if p < 0.5:
        return 4.0 * p * p * p
    q = -2.0 * p + 2.0
    return 1.0 - q * q * q / 2.0


def roll_state(t_ms, count, band_h):
    """(word, next_word, offset_px) at t_ms. offset 0 shows `word` at rest;
    during the roll it grows to band_h as `next_word` rises into place."""
    if count <= 0:
        return 0, 0, 0
    cycle = t_ms // CYCLE_MS
    phase = t_ms - cycle * CYCLE_MS
    k = cycle % count
    nxt = (k + 1) % count
    if phase < HOLD_MS:
        return k, nxt, 0
    p = ease((phase - HOLD_MS) / ROLL_MS)
    return k, nxt, min(band_h, int(p * band_h + 0.5))


def compose_band(fb, stride, band_y, band_h, bg_row, cur, cur_w, nxt, nxt_w, off):
    """Write one frame of the roll into framebuffer rows band_y..+band_h.
    cur rows move up by off; nxt rows follow band_h below them."""
    cx = ((SW - cur_w) // 2) * 2
    nx = ((SW - nxt_w) // 2) * 2
    cl = cur_w * 2
    nl = nxt_w * 2
    base = band_y * stride
    for y in range(band_h):
        d = base + y * stride
        fb[d:d + stride] = bg_row
        r = y + off
        if r < band_h:
            if cur is not None:
                s = r * cl
                fb[d + cx:d + cx + cl] = cur[s:s + cl]
        else:
            r -= band_h
            if nxt is not None:
                s = r * nl
                fb[d + nx:d + nx + nl] = nxt[s:s + nl]


class _Art:
    """Reads oreoOS/splash.bin: header, logo, tag and greeting offsets.
    Greetings are loaded on demand into reusable buffers."""

    def __init__(self, path):
        f = open(path, "rb")
        self._f = f
        hdr = f.read(10)
        if hdr[:4] != b"OSP1":
            raise ValueError("bad splash.bin")
        self.count, _, self.band_h, self.bg565 = struct.unpack("<BBHH", hdr[4:])
        self.logo_w, self.logo_h = struct.unpack("<HH", f.read(4))
        self.logo = f.read(self.logo_w * self.logo_h * 2)
        self.tag_w, self.tag_h = struct.unpack("<HH", f.read(4))
        self.tag = f.read(self.tag_w * self.tag_h * 2)
        self.offsets = []
        self.widths = []
        pos = 10 + 4 + len(self.logo) + 4 + len(self.tag)
        max_w = 0
        for _ in range(self.count):
            f.seek(pos)
            w = struct.unpack("<H", f.read(2))[0]
            self.widths.append(w)
            self.offsets.append(pos + 2)
            pos += 2 + w * self.band_h * 2
            if w > max_w:
                max_w = w
        self._size = max_w * self.band_h * 2

    def buffer(self):
        return bytearray(self._size)

    def load(self, k, buf):
        n = self.widths[k] * self.band_h * 2
        self._f.seek(self.offsets[k])
        self._f.readinto(memoryview(buf)[:n])
        return buf

    def close(self):
        try:
            self._f.close()
        except Exception:
            pass


class Splash:
    def __init__(self, os_obj):
        self._os = os_obj
        self._art = None
        self._start = _ms()
        self._stop = False
        self._alive = False
        self._threaded = False
        self._last = None
        self._loaded = (-1, -1)
        try:
            self._art = _Art(BIN_PATH)
            a = self._art
            self._band_y = (SH - a.band_h) // 2 - 8
            self._bufs = [a.buffer(), a.buffer()]
            bg = struct.pack(">H", a.bg565)
            self._bg_row = bg * SW
        except Exception as e:
            print("[splash] art unavailable:", e)
            self._art = None

    # -- public API (all calls are safe to make; errors never escape) -----

    def intro(self):
        try:
            self._start = _ms()
            if self._art is None:
                self._static()
                return
            self._first_frame()
            self._start_thread()
        except Exception as e:
            print("[splash] intro:", e)

    def progress(self, frac):
        pass        # the roll is time-based; kept for boot() compatibility

    def pump(self):
        """Draw one frame when no animation thread is running. Returns False
        (callers pass it as a cancel callback)."""
        if not self._threaded and self._art is not None:
            try:
                self._frame()
            except Exception:
                pass
        return False

    def finish(self):
        try:
            if self._art is not None:
                deadline = None
                while True:
                    t = _diff(_ms(), self._start)
                    if t >= MIN_TOTAL_MS:
                        if deadline is None:
                            deadline = t + FINISH_MAX_MS
                        k, n, off = roll_state(t, self._art.count, self._art.band_h)
                        if off == 0 or t >= deadline:
                            break
                    if not self._threaded:
                        self._frame()
                    time.sleep_ms(FRAME_MS)
            self._stop = True
            waited = 0
            while self._alive and waited < 500:
                time.sleep_ms(5)
                waited += 5
        except Exception as e:
            print("[splash] finish:", e)
        self.release()

    def release(self):
        self._stop = True
        if self._art is not None:
            self._art.close()
        self._art = None
        self._bufs = None

    # -- drawing ----------------------------------------------------------

    def _static(self):
        d = self._os.display
        d.clear(theme.BG)
        d.text("hello", (SW - 5 * 24) // 2, SH // 2 - 20, theme.TEXT_BRIGHT, scale=3)
        d.text("OreoOS", (SW - 6 * 8) // 2, SH // 2 + 12, theme.PRIMARY)
        d.present()

    def _blit_rows(self, data, x, y, w, h):
        fb = self._os.display._buf
        stride = SW * 2
        rl = w * 2
        for r in range(h):
            d = (y + r) * stride + x * 2
            fb[d:d + rl] = data[r * rl:(r + 1) * rl]

    def _first_frame(self):
        a = self._art
        d = self._os.display
        fb = d._buf
        stride = SW * 2
        for y in range(SH):
            fb[y * stride:(y + 1) * stride] = self._bg_row
        self._blit_rows(a.logo, LOGO_X, LOGO_Y, a.logo_w, a.logo_h)
        tag_y = self._band_y + a.band_h + TAG_GAP
        self._blit_rows(a.tag, (SW - a.tag_w) // 2, tag_y, a.tag_w, a.tag_h)
        self._ensure(0, 1)
        compose_band(fb, stride, self._band_y, a.band_h, self._bg_row,
                     self._bufs[0], a.widths[0], self._bufs[1], a.widths[1], 0)
        self._last = (0, 0)
        d._dirty = True
        d.present()

    def _ensure(self, k, n):
        """Have word k in buffer 0 and word n in buffer 1."""
        lk, ln = self._loaded
        a = self._art
        if lk != k:
            if ln == k:
                self._bufs[0], self._bufs[1] = self._bufs[1], self._bufs[0]
                ln = -1
            else:
                a.load(k, self._bufs[0])
        if ln != n:
            a.load(n, self._bufs[1])
        self._loaded = (k, n)

    def _frame(self):
        a = self._art
        t = _diff(_ms(), self._start)
        k, n, off = roll_state(t, a.count, a.band_h)
        self._ensure(k, n)
        if (k, off) == self._last:
            return
        self._last = (k, off)
        d = self._os.display
        compose_band(d._buf, SW * 2, self._band_y, a.band_h, self._bg_row,
                     self._bufs[0], a.widths[k], self._bufs[1], a.widths[n], off)
        d._dirty = True
        d.present_rect(0, self._band_y, SW, a.band_h)

    def _run(self):
        try:
            while not self._stop and self._art is not None:
                self._frame()
                time.sleep_ms(FRAME_MS)
        except Exception as e:
            print("[splash] thread:", e)
        self._alive = False

    def _start_thread(self):
        try:
            import _thread
            try:
                _thread.stack_size(8 * 1024)
            except Exception:
                pass
            self._alive = True
            self._threaded = True
            _thread.start_new_thread(self._run, ())
        except Exception as e:
            print("[splash] no thread, pump() fallback:", e)
            self._alive = False
            self._threaded = False


# -- OTA updating screen ------------------------------------------------------

def show_updating(os_obj, target_version, total_files):
    """Draw a system-update splash while OTA files are being copied.

    Modelled on the app-loader slide: a pink panel fills the screen with a
    vertically centred title, progress bar, target version and safety copy.
    The caller advances the bar via update_progress(). Returns a callable
    `(done_count, current_file) -> None` so the apply step can pump
    progress without re-doing all the panel rendering each call.
    """
    d  = os_obj.display
    SW = api.SCREEN_W
    SH = api.SCREEN_H

    # Build the complete block around the screen centre instead of anchoring
    # individual elements to unrelated offsets. This keeps the title, bar,
    # version, warning and current filename visually balanced as one unit.
    d.rect(0, 0, SW, SH, theme.PRIMARY, fill=True)
    centre_y = SH // 2
    title_y  = centre_y - 54
    bar_y    = centre_y - 20
    bar_h    = 10
    version_y = bar_y + bar_h + 10
    warning_y = version_y + 20
    file_y    = warning_y + 18

    title = "UPDATING OREOOS"
    tw    = len(title) * 16
    d.text(title, (SW - tw) // 2, title_y, api.WHITE, scale=2)

    bar_x = 30
    bar_w = SW - 60
    # Gold outer frame separates the progress track from the pink panel.
    d.rect(bar_x - 2, bar_y - 2, bar_w + 4, bar_h + 4,
           theme.GOLD, fill=True)
    d.rect(bar_x, bar_y, bar_w, bar_h, api.rgb(40, 40, 40), fill=True)

    # The target version belongs to the progress operation, so keep it just
    # below the bar rather than near the title. Scale 2 makes the destination
    # unambiguous from normal status text.
    version = target_version or "unknown"
    vw = len(version) * 16
    d.text(version, (SW - vw) // 2, version_y, theme.GOLD, scale=2)
    d.text("do not unplug", (SW - 13 * 8) // 2, warning_y,
           api.WHITE)
    d.present()

    def _advance(done, current_file=""):
        # Only repaint the bar's filled portion + the file-name strip to
        # keep this cheap (full-screen reflows during an OTA apply would
        # add 30+ ms of GC pressure per file).
        pct = done / float(max(1, total_files))
        fill_w = int(bar_w * pct)
        d.rect(bar_x, bar_y, bar_w, bar_h, api.rgb(40, 40, 40), fill=True)
        if fill_w:
            d.rect(bar_x, bar_y, fill_w, bar_h, theme.GOLD, fill=True)
        # Clear + re-draw the file-name line under the bar.
        d.rect(0, file_y, SW, 14, theme.PRIMARY, fill=True)
        name = (current_file or "")[:38]
        if name:
            d.text(name, (SW - len(name) * 8) // 2, file_y,
                   api.WHITE)
        d.present()

    return _advance

"""Animated boot splash — Oreo OS, 320×240 landscape.

The splash runs alongside the boot work instead of in front of it:

  intro()     ~0.75 s, blocking. Backdrop, the favicon logo drops in,
              "OREO OS" types in.
  pump()      non-blocking, call it between boot steps and hand it to
              wifi.connect_from_config(pump_cb=...). Each call draws at
              most one frame of the "hello" greeting: the word for hello
              cycles through languages with a fade + slide, and the
              loading bar eases toward the real boot progress.
  progress(f) set the loading bar target (0..1) as boot steps finish.
  finish()    hold until a short minimum on-screen time (so a fast boot
              still reads one or two words), fill the bar, free the
              backdrop buffers.

    sp = Splash(os_obj)
    sp.intro()
    ... sp.progress(0.3); wifi.connect_from_config(pump_cb=sp.pump) ...
    sp.finish()

Why draw it instead of playing a pre-rendered RV565 clip: the current
firmware's native RV565 support is only `_oreo_rv565.inflate_frame`; the
player itself (file parsing, PSRAM preload, frame pacing) lives inside the
Gallery app. A clip would need that app module imported at boot, a large
full-frame asset on flash and a full 153 KB SPI push per frame (~47 ms),
which competes with WiFi bring-up. The drawn greeting repaints one 36-px
band through a single native mono blit and flushes only that band
(~7 ms), needs no asset beyond the Pixelify font that the OS already
ships, and works on any firmware.

The backdrop prefers `assets/sprites/optimized/splash_bg.py` (run
`tools/optimize_assets.py splash_bg` after dropping a raw image into
`assets/sprites/raw/`). When that file is absent we paint a procedural
warm confetti-tone gradient so the splash still looks intentional on a
fresh checkout.
"""

import struct
import time
from oreoOS import api
from oreoOS import theme

SW = api.SCREEN_W
SH = api.SCREEN_H

# ── layout (centred vertical stack) ──────────────────────────────────────────
# Transparent favicon logo → title → greeting band → loading bar.

_MW, _MH       = 72, 72
_LOGO_REST_Y   = 26                       # final logo top y
_TITLE_Y       = _LOGO_REST_Y + _MH + 10  # below logo
_BAR_W         = SW - 80
_BAR_X         = (SW - _BAR_W) // 2
_BAR_Y         = SH - 30
_BAR_H         = 5

TITLE          = "OREO OS"
BG_DIM         = 0.30          # fraction of original brightness

# Intro timeline (ms from intro start).
_LOGO_MS       = (0, 380)
_TITLE_MS      = (380, 700)
INTRO_MS       = 760
MIN_TOTAL_MS   = 1700          # finish() never returns earlier than this

# ── greeting ─────────────────────────────────────────────────────────────────
# Romanised: the Pixelify font is ASCII-only, so Devanagari / Bengali /
# kana and accented letters cannot be drawn.
GREETINGS = ("hello", "namaste", "hola", "bonjour", "nomoshkar", "ciao",
             "konnichiwa", "ola", "hallo", "vanakkam", "salaam", "merhaba")

GREET_IN_MS    = 230           # fade + slide up into place
GREET_HOLD_MS  = 560
GREET_OUT_MS   = 200           # fade + slide up and away
GREET_CYCLE_MS = GREET_IN_MS + GREET_HOLD_MS + GREET_OUT_MS
GREET_SLIDE    = 6             # px travelled during each fade
GREET_FRAME_MS = 30            # pump() draws at most this often

_GLYPH_H       = 24            # pixelify_24
_BAND_Y        = _TITLE_Y + 24 + 6 - GREET_SLIDE  # title is scale 3 (24 px)
_BAND_H        = _GLYPH_H + 2 * GREET_SLIDE
_MASK_W        = SW
_MASK_STRIDE   = _MASK_W >> 3

# Centre box the procedural confetti keeps clear (logo, title, greeting).
_CLEAR_X0      = (SW - 200) // 2
_CLEAR_X1      = (SW + 200) // 2
_CLEAR_Y0      = 16
_CLEAR_Y1      = _BAND_Y + _BAND_H + 4

# ── mascot loader (cached) ───────────────────────────────────────────────────

_mascot = None
_splash_logo = None


def _get_splash_logo():
    """Return the transparent favicon sprite, falling back to the mascot."""
    global _splash_logo
    if _splash_logo is not None:
        return _splash_logo if _splash_logo is not False else None
    try:
        import assets.sprites.optimized.favicon_logo as logo
        _splash_logo = (logo.DATA, logo.W, logo.H)
        return _splash_logo
    except (ImportError, AttributeError):
        _splash_logo = _get_mascot()
        return _splash_logo

def _get_mascot():
    """Return (data, w, h) for the mascot sprite. Prefers the chroma-key
    transparent variant so the splash bg shows through around the mascot.

    Resolution order:
      1. assets/sprites/optimized/mascot_transparent.py   (chroma-key, preferred)
      2. assets/sprites/optimized/mascot.py               (cream-bg fallback)
      3. PIL bake at runtime                              (asset rebuild path)
    """
    global _mascot
    if _mascot is not None:
        return _mascot if _mascot is not False else None
    # 1) Transparent (chroma-key magenta) variant — corners blit as
    # transparent so the dimmed splash bg shows through.
    try:
        import assets.sprites.optimized.mascot_transparent as m
        _mascot = (m.DATA, m.W, m.H)
        return _mascot
    except (ImportError, AttributeError):
        pass
    # 2) Cream-bg version (older asset) — still readable, just sits in a
    # square; better than no mascot.
    try:
        import assets.sprites.optimized.mascot as m
        _mascot = (m.DATA, m.W, m.H)
        return _mascot
    except (ImportError, AttributeError):
        pass
    # 3) Build-host fallback: bake from the raw PNG via PIL (never runs
    # on the badge — PIL isn't installed there).
    try:
        from PIL import Image
        img = Image.open("assets/sprites/raw/mascot.png").convert("RGBA").resize(
            (_MW, _MH), Image.LANCZOS)
        bg = Image.new("RGBA", (_MW, _MH), (theme.BG_R, theme.BG_G, theme.BG_B, 255))
        bg.paste(img, mask=img.split()[3])
        rgb = bg.convert("RGB")
        px  = rgb.load()
        words = []
        for y in range(_MH):
            for x in range(_MW):
                r, g, b = px[x, y]
                words.append(((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3))
        data = struct.pack(">%dH" % len(words), *words)
        _mascot = (data, _MW, _MH)
        return _mascot
    except Exception:
        pass
    _mascot = False
    return None


# ── dimmed background (cached) ───────────────────────────────────────────────

_bg = None

def _dim_buf(src, factor):
    """RGB565 big-endian bytes → new bytearray, every pixel × factor."""
    n   = len(src) // 2
    out = bytearray(len(src))
    fac = int(factor * 256)
    for i in range(n):
        v = (src[i*2] << 8) | src[i*2 + 1]
        r = ((v >> 11) & 0x1F) * fac >> 8
        g = ((v >>  5) & 0x3F) * fac >> 8
        b = ( v        & 0x1F) * fac >> 8
        v2 = (r << 11) | (g << 5) | b
        out[i*2]     = v2 >> 8
        out[i*2 + 1] = v2 & 0xFF
    return out


def _upscale(src, sw, sh, dw, dh):
    """Nearest-neighbour upscale of an RGB565 big-endian byte buffer.

    Lets us ship the splash background at a smaller native size (cheap to
    parse, lighter on flash) and inflate to screen dimensions once at boot.
    """
    out      = bytearray(dw * dh * 2)
    sx_step  = (sw << 16) // dw
    sy_step  = (sh << 16) // dh
    sy       = 0
    for dy in range(dh):
        src_row = (sy >> 16) * sw * 2
        sx      = 0
        row_off = dy * dw * 2
        for dx in range(dw):
            s = src_row + (sx >> 16) * 2
            out[row_off + dx * 2]     = src[s]
            out[row_off + dx * 2 + 1] = src[s + 1]
            sx += sx_step
        sy += sy_step
    return out


def _get_bg():
    """Return (data, w, h) for a full-screen dimmed splash backdrop, or None.

    Catches *every* exception type — the splash_bg module is a 150 KB+ bytes
    literal; on a tight-heap boot the parser/_dim_buf can raise MemoryError,
    SyntaxError, or anything in between. If anything goes wrong we fall back
    to the procedural gradient so the splash never crashes the boot path.
    """
    global _bg
    if _bg is not None:
        return _bg if _bg is not False else None
    try:
        # Free as much heap as possible before importing the big asset.
        try:
            import gc
            gc.collect()
        except ImportError:
            pass
        import assets.sprites.optimized.splash_bg as m
        # Dim FIRST (cheap, per-source-pixel), then upscale into a screen-
        # sized buffer. Works for either a native-res 320×240 asset or the
        # half/quarter-res asset we ship to save flash.
        dimmed = _dim_buf(m.DATA, BG_DIM)
        if m.W == SW and m.H == SH:
            _bg = (dimmed, SW, SH)
        else:
            _bg = (_upscale(dimmed, m.W, m.H, SW, SH), SW, SH)
        return _bg
    except Exception:
        pass
    _bg = False
    return None


# ── procedural fallback bg (festive gradient + confetti dots) ────────────────

def _procedural_row(y):
    """RGB565 colour of backdrop row y: pink → cream → gold bands."""
    if y < SH // 3:
        t = y / (SH // 3)
        r = int(theme.PRIMARY_R * (1 - t) + theme.BG_R * t * 0.7)
        g = int(theme.PRIMARY_G * (1 - t) + theme.BG_G * t * 0.7)
        b = int(theme.PRIMARY_B * (1 - t) + theme.BG_B * t * 0.7)
    elif y > (2 * SH) // 3:
        t = (y - 2 * SH // 3) / (SH // 3)
        r = int(theme.BG_R * (1 - t) * 0.7 + theme.GOLD_R * t)
        g = int(theme.BG_G * (1 - t) * 0.7 + theme.GOLD_G * t)
        b = int(theme.BG_B * (1 - t) * 0.7 + theme.GOLD_B * t)
    else:
        r, g, b = int(theme.BG_R * 0.6), int(theme.BG_G * 0.55), int(theme.BG_B * 0.5)
    return api.rgb(r, g, b)


def _draw_procedural_bg(d):
    """Three-band vertical gradient (pink → cream → gold) with a sparse
    deterministic confetti scatter. Theme-on-brand so the splash looks
    intentional even before a real backdrop asset has been baked."""
    for y in range(SH):
        d.rect(0, y, SW, 1, _procedural_row(y), fill=True)
    seed = 0xC0FFEE
    palette = [theme.PRIMARY, theme.GOLD, theme.TEAL]
    for _ in range(60):
        seed = (seed * 1103515245 + 12345) & 0xFFFFFFFF
        x = seed % SW
        seed = (seed * 1103515245 + 12345) & 0xFFFFFFFF
        y = seed % SH
        sz = 2 + (seed >> 4) % 3
        # keep the logo / title / greeting box clear
        if x + sz > _CLEAR_X0 and x < _CLEAR_X1 and \
           y + sz > _CLEAR_Y0 and y < _CLEAR_Y1:
            continue
        col = palette[seed % 3]
        d.rect(x, y, sz, sz, col, fill=True)


# ── helpers ──────────────────────────────────────────────────────────────────

def _ms():       return time.ticks_ms()
def _diff(a, b): return time.ticks_diff(a, b)


def _ease_out(t):
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    u = 1.0 - t
    return 1.0 - u * u * u


def _span(ms, span):
    """0..1 progress of `ms` through the (start, end) window."""
    s, e = span
    if ms <= s:
        return 0.0
    if ms >= e:
        return 1.0
    return (ms - s) / (e - s)


def _draw_text_centered(d, s, y, color, scale=1):
    w = len(s) * 8 * scale
    d.text(s, (SW - w) // 2, y, color, scale=scale)


def lerp565(a, b, t):
    """Blend two RGB565 colours; t=0 → a, t=1 → b."""
    if t <= 0.0:
        return a
    if t >= 1.0:
        return b
    k = int(t * 256)
    ar, ag, ab = (a >> 11) & 0x1F, (a >> 5) & 0x3F, a & 0x1F
    br, bg, bb = (b >> 11) & 0x1F, (b >> 5) & 0x3F, b & 0x1F
    r = ar + (((br - ar) * k) >> 8)
    g = ag + (((bg - ag) * k) >> 8)
    bl = ab + (((bb - ab) * k) >> 8)
    return (r << 11) | (g << 5) | bl


def greet_frame(t_ms):
    """Greeting timeline at `t_ms` since it started.

    Returns (word_index, alpha 0..1, dy px). dy is positive while the word
    rises into place and negative while it drifts up and away.
    """
    if t_ms < 0:
        t_ms = 0
    cyc = t_ms // GREET_CYCLE_MS
    p   = t_ms - cyc * GREET_CYCLE_MS
    idx = cyc % len(GREETINGS)
    if p < GREET_IN_MS:
        e = _ease_out(p / GREET_IN_MS)
        return idx, e, int(GREET_SLIDE * (1.0 - e) + 0.5)
    p -= GREET_IN_MS
    if p < GREET_HOLD_MS:
        return idx, 1.0, 0
    p -= GREET_HOLD_MS
    u = p / GREET_OUT_MS
    e = u * u
    return idx, 1.0 - e, -int(GREET_SLIDE * e + 0.5)


def glyph_extent(bits, gw, gh, bpr):
    """(left_trim, advance) of a row-major MSB-first glyph bitmap."""
    lo, hi = gw, -1
    for row in range(gh):
        off = row * bpr
        for col in range(gw):
            if bits[off + (col >> 3)] & (0x80 >> (col & 7)):
                if col < lo:
                    lo = col
                if col > hi:
                    hi = col
    if hi < 0:
        return 0, max(3, gw // 3)
    return lo, hi - lo + 1


def build_word_mask(word, font, gw, gh, bpr, kern, metrics, mask, stride):
    """Render `word` centred into a MONO_HLSB `mask` (stride bytes/row,
    gh rows), cleared first. `font` maps char → glyph bitmap, `metrics`
    is a dict cache of char → (left_trim, advance) filled on demand.

    Whole glyph rows are shifted into place as integers, so building a
    word is ~one loop iteration per glyph row, not per pixel. Returns the
    word's pixel width.
    """
    for i in range(stride * gh):
        mask[i] = 0
    width = 0
    for ch in word:
        m = metrics.get(ch)
        if m is None:
            bits = font.get(ch)
            m = glyph_extent(bits, gw, gh, bpr) if bits else (0, gw)
            metrics[ch] = m
        width += m[1] + kern
    width = max(0, width - kern)
    x = (stride * 8 - width) // 2
    total = bpr * 8
    for ch in word:
        lo, adv = metrics[ch]
        bits = font.get(ch)
        start = x - lo                 # mask pixel of glyph column 0
        if bits and start >= 0:
            b = start >> 3
            s = start & 7
            nbytes = (s + total + 7) >> 3
            shift = nbytes * 8 - s - total
            for row in range(gh):
                off = row * bpr
                v = 0
                for k in range(bpr):
                    v = (v << 8) | bits[off + k]
                v = (v << shift) if shift >= 0 else (v >> -shift)
                if not v:
                    continue
                dst = row * stride + b
                for i in range(nbytes):
                    byte = (v >> (8 * (nbytes - 1 - i))) & 0xFF
                    if byte and b + i < stride:
                        mask[dst + i] |= byte
        x += adv + kern
    return width


# ── show_splash ──────────────────────────────────────────────────────────────

def show_shake_mascot(os_obj, duration_ms=2400):
    """Quick reaction to a HARD_SHAKE gesture — paints the mascot at
    centre with a 'head spinning' compress/expand animation.

    The chroma-key mascot already exists in assets; here we just
    horizontally squish it (W × scale_x) and bounce the scale_x between
    0.25 and 1.0 a few times to fake rotation around the vertical axis.
    Cheap enough to run as a blocking overlay — duration_ms keeps the
    block bounded so the OS run-loop resumes shortly after.
    """
    d = os_obj.display
    mascot = _get_mascot()
    if not mascot:
        return
    data, mw, mh = mascot
    cx = SW // 2
    y0 = (SH - mh) // 2

    # Pre-paint background once so the mascot is the only thing
    # changing per frame. Cheap painted card instead of bg image so
    # there's no large asset hit at gesture time.
    d.clear(theme.BG)
    d.rect(0, 0, SW, 28, theme.PRIMARY, fill=True)
    label = "WHOA!"
    d.text(label, (SW - len(label) * 16) // 2, 6, api.WHITE, scale=2)
    sub   = "shake detected"
    d.text(sub, (SW - len(sub) * 8) // 2, SH - 24, theme.MUTED, scale=1)
    d.present()

    import math as _math
    start = _ms()
    last_w = -1
    while True:
        t = _diff(_ms(), start)
        if t >= duration_ms:
            break
        # 0..1 ramp through 4 full cycles
        phase = (t / duration_ms) * 4.0
        s     = abs(_math.cos(phase * _math.pi))      # 1 → 0 → 1 cycle
        new_w = max(2, int(mw * (0.25 + 0.75 * s)))   # never zero
        if new_w == last_w:
            try: time.sleep_ms(20)
            except Exception: pass
            continue
        last_w = new_w
        # Repaint the mascot strip — wipe the previous draw with bg.
        d.rect(0, y0, SW, mh, theme.BG, fill=True)
        # Compress the mascot horizontally to new_w.
        data2 = _compress_x(data, mw, mh, new_w)
        if data2 is not None:
            d.blit(data2, cx - new_w // 2, y0, new_w, mh)
        d.present()
        try: time.sleep_ms(20)
        except Exception: pass


def _compress_x(src, sw, sh, dst_w):
    """Horizontally compress an RGB565 BE sprite to width dst_w.

    Mirrors the helper in apps/launcher — kept private here so splash
    doesn't drag a launcher import along for one reaction animation.
    """
    if dst_w >= sw:
        return src
    if dst_w <= 0:
        return None
    src_stride = sw * 2
    out_stride = dst_w * 2
    out = bytearray(out_stride * sh)
    col_map = [c * sw // dst_w for c in range(dst_w)]
    for ry in range(sh):
        sb = ry * src_stride
        ob = ry * out_stride
        for ox in range(dst_w):
            so = sb + col_map[ox] * 2
            do = ob + ox * 2
            out[do]     = src[so]
            out[do + 1] = src[so + 1]
    return out


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



# ── boot splash ──────────────────────────────────────────────────────────────

_GREET_COLORS = (api.WHITE, theme.GOLD, api.rgb(255, 150, 160),
                 api.rgb(120, 230, 215))
_FONT_MOD = "assets.fonts.optimized.pixelify_24"


class Splash:
    """Boot splash that keeps animating while the OS loads. See module
    docstring for the call order. Every method swallows its own errors:
    the splash must never take the boot down."""

    def __init__(self, os_obj):
        self._d        = os_obj.display
        self._start    = _ms()
        self._snap     = None      # full-screen backdrop, RGB565 BE
        self._grad     = None      # fallback band colour per row
        self._greet_t0 = None
        self._last_ms  = 0
        self._last_key = None      # (idx, alpha level, dy) last drawn
        self._word_idx = -1
        self._band_bg  = theme.TEXT_BRIGHT
        self._font     = None      # (glyphs, gw, gh, bpr, kern) or False
        self._metrics  = {}
        self._mask     = bytearray(_MASK_STRIDE * _GLYPH_H)
        self._bar_pos  = 0.0
        self._bar_goal = 0.0
        self._bar_px   = -1
        self._fast     = False     # finish(): close the bar out quickly

    # ── public API ──────────────────────────────────────────────────────
    def intro(self):
        """Backdrop, logo drop and title, then hand over to pump()."""
        try:
            self._intro()
        except Exception as e:
            try:
                print("[splash] intro failed:", e)
            except Exception:
                pass
        self._greet_t0 = _ms()
        self._last_ms  = 0

    def progress(self, frac):
        """Move the loading-bar target; pump() eases the bar toward it."""
        if frac > self._bar_goal:
            self._bar_goal = 1.0 if frac > 1.0 else frac
        self.pump()

    def pump(self):
        """Draw one greeting frame if one is due. Always returns False so
        it can double as a wifi `pump_cb` (True would cancel the connect).
        """
        try:
            now = _ms()
            if self._greet_t0 is None:
                return False
            if self._last_ms and _diff(now, self._last_ms) < GREET_FRAME_MS:
                return False
            dt = _diff(now, self._last_ms) if self._last_ms else 0
            self._last_ms = now
            self._step_bar(dt)
            self._draw_greeting(_diff(now, self._greet_t0))
        except Exception as e:
            try:
                print("[splash] frame failed:", e)
            except Exception:
                pass
            self._greet_t0 = None       # stop animating, keep booting
        return False

    def finish(self):
        """Hold for the minimum on-screen time, fill the bar, free RAM.
        The last frame stays up until Home paints over it."""
        self._bar_goal = 1.0
        self._fast     = True
        try:
            while self._greet_t0 is not None:
                if _diff(_ms(), self._start) >= MIN_TOTAL_MS and \
                        self._bar_pos >= 0.999:
                    break
                self.pump()
                time.sleep_ms(8)
        except Exception:
            pass
        self.release()

    def release(self):
        global _bg
        self._snap = None
        self._grad = None
        self._mask = None
        self._font = None
        self._greet_t0 = None
        _bg = None                    # 150 KB backdrop: boot-only
        try:
            import sys
            from oreoOS import pixelfont
            if "pixelify_24" not in pixelfont._CACHE:
                sys.modules.pop(_FONT_MOD, None)
        except Exception:
            pass
        try:
            import gc
            gc.collect()
        except Exception:
            pass

    # ── intro ───────────────────────────────────────────────────────────
    def _intro(self):
        d  = self._d
        bg = _get_bg()
        if bg:
            data, bw, bh = bg
            d.blit_rows(data, 0, SH)
            self._snap = data
        else:
            _draw_procedural_bg(d)
            try:
                self._snap = d.copy_rows(0, SH)
            except Exception:
                self._snap = None
            if self._snap is None:
                self._grad = True
        self._band_bg = self._sample_band_colour()
        d.present()

        logo = _get_splash_logo()
        t0   = _ms()
        prev_y = None
        typed  = -1
        while True:
            t = _diff(_ms(), t0)
            # Logo: ease-out drop from above the screen to its rest spot.
            p = _ease_out(_span(t, _LOGO_MS))
            y = int(-_MH + (_LOGO_REST_Y + _MH) * p)
            if y != prev_y:
                bot = y + _MH
                if bot > 0:
                    # Repaint the backdrop under the old and new logo
                    # spots first: the logo has transparent edges, so
                    # drawing over the previous frame would smear it.
                    top = max(0, prev_y if prev_y is not None else y)
                    self._restore(top, bot - top)
                    self._draw_logo(logo, y)
                    d.present_rect(0, 0, SW, min(SH, bot))
                prev_y = y
            # Title: types in one letter at a time.
            n = int(_span(t, _TITLE_MS) * len(TITLE) + 0.999)
            if n != typed and n > 0:
                typed = n
                self._restore(_TITLE_Y, 24)      # centring shifts per letter
                _draw_text_centered(d, TITLE[:n], _TITLE_Y, api.WHITE, scale=3)
                d.present_rect(0, _TITLE_Y, SW, 24)
            if t >= INTRO_MS:
                break
            time.sleep_ms(12)
        self._load_font()

    def _draw_logo(self, logo, y):
        d = self._d
        x = (SW - _MW) // 2
        if logo:
            data, mw, mh = logo
            try:
                d.blit(data, (SW - mw) // 2, y, mw, mh)
                return
            except Exception:
                pass
        d.rect(x, y, _MW, _MH, theme.PRIMARY, fill=True)

    def _restore(self, y, h):
        """Repaint backdrop rows y..y+h (clipped)."""
        if y < 0:
            h += y
            y = 0
        if y + h > SH:
            h = SH - y
        if h <= 0:
            return
        if self._snap is not None:
            self._d.blit_rows(self._snap, y, h, y)
        else:
            for row in range(y, y + h):
                self._d.rect(0, row, SW, 1, _procedural_row(row), fill=True)

    def _sample_band_colour(self):
        """Average backdrop colour behind the greeting: the fade starts
        from it so words appear to emerge from the background."""
        snap = self._snap
        if snap is None:
            return _procedural_row(_BAND_Y + _BAND_H // 2)
        r = g = b = n = 0
        stride = SW * 2
        for row in range(_BAND_Y, _BAND_Y + _BAND_H, 4):
            base = row * stride
            for col in range(_CLEAR_X0, _CLEAR_X1, 8):
                i = base + col * 2
                v = (snap[i] << 8) | snap[i + 1]
                r += (v >> 11) & 0x1F
                g += (v >> 5) & 0x3F
                b += v & 0x1F
                n += 1
        if not n:
            return theme.TEXT_BRIGHT
        return ((r // n) << 11) | ((g // n) << 5) | (b // n)

    def _load_font(self):
        try:
            import gc
            gc.collect()
            m = __import__(_FONT_MOD, None, None, ["_FONT"])
            if m.GLYPH_H != _GLYPH_H or (m.GLYPH_W + 7) >> 3 > m.BPR:
                raise ValueError("font geometry")
            self._font = (m._FONT, m.GLYPH_W, m.GLYPH_H, m.BPR, m.KERN)
        except Exception:
            self._font = False

    # ── per-frame ───────────────────────────────────────────────────────
    def _step_bar(self, dt):
        goal = self._bar_goal
        pos  = self._bar_pos
        if pos < goal:
            # Exponential approach: quick at first, soft landing, frame-
            # rate independent. Snap when within half a pixel.
            k = dt / (70.0 if self._fast else 180.0)
            pos += (goal - pos) * (k if k < 1.0 else 1.0)
            if (goal - pos) * _BAR_W < 0.5:
                pos = goal
            self._bar_pos = pos
        px = int(pos * _BAR_W)
        if px == self._bar_px:
            return
        d = self._d
        if self._bar_px < 0:
            d.rect(_BAR_X, _BAR_Y, _BAR_W, _BAR_H, api.rgb(80, 60, 60), fill=True)
            self._bar_px = 0
        if px > self._bar_px:
            d.rect(_BAR_X + self._bar_px, _BAR_Y, px - self._bar_px, _BAR_H,
                   theme.PRIMARY, fill=True)
        self._bar_px = px
        d.present_rect(_BAR_X, _BAR_Y, _BAR_W, _BAR_H)

    def _draw_greeting(self, t):
        idx, alpha, dy = greet_frame(t)
        key = (idx, int(alpha * 16), dy)
        if key == self._last_key:
            return
        self._last_key = key
        d = self._d
        word = GREETINGS[idx]
        self._restore(_BAND_Y, _BAND_H)
        if alpha > 0.0:
            color = lerp565(self._band_bg, _GREET_COLORS[idx % len(_GREET_COLORS)],
                            alpha)
            y = _BAND_Y + GREET_SLIDE + dy
            f = self._font
            if f:
                if idx != self._word_idx:
                    glyphs, gw, gh, bpr, kern = f
                    build_word_mask(word, glyphs, gw, gh, bpr, kern,
                                    self._metrics, self._mask, _MASK_STRIDE)
                    self._word_idx = idx
                d.blit_mono(self._mask, 0, y, _MASK_W, _GLYPH_H, color)
            else:
                _draw_text_centered(d, word, y, color, scale=3)
        d.present_rect(0, _BAND_Y, SW, _BAND_H)


def show_splash(os_obj):
    """Blocking splash (intro + minimum hold). Kept for callers that have
    no boot steps to interleave; boot() drives Splash directly."""
    sp = Splash(os_obj)
    sp.intro()
    sp.finish()
    return sp

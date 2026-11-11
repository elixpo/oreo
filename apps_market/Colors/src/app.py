"""Color Picker - Photoshop-style 2D spectrum + crosshair cursor.

Layout:
  Header (28 px)  : "COLOR" label + small live preview swatch + tiny readout
                    of the current value in the active model (RGB / HSL / CMYK)
  Spectrum field  : full 320 x 196 rainbow, upscaled 4x from a baked
                    80 x 49 source asset (apps/color_picker/assets/optimized/
                    color_splash.py). White at the top -> saturated band in
                    the middle -> black at the bottom. Hue sweeps left -> right.
  Hint bar (16 px): control summary.

Controls:
  arrows  move the crosshair (long-press accelerates ~5x after ~0.4 s held)
  B       cycle display model RGB -> HSL -> CMYK -> RGB
  A       save the current colour (kept in /state/color_picker.json)
  C       show the colour on the badge's RGB LED, or turn it off
          (a double-tap of C opens the notification panel)
  HOME    back to the apps drawer

The current colour is read directly out of the upscaled spectrum buffer at
the cursor position (so what you see is what you get; no resampling
artefacts). The HSL / CMYK readouts are derived on the fly from RGB.
"""

import oreoOS
from oreoOS import api, theme, widgets
try:
    from oreoOS import state
except ImportError:   # OS before the /state helper: keep the old file save
    state = None


SW = api.SCREEN_W                    # 320
SH = api.SCREEN_H                    # 240
PLAY_TOP  = widgets.HEADER_H
PLAY_BOT  = SH - widgets.HINT_H
PLAY_H    = PLAY_BOT - PLAY_TOP      # 196
PLAY_W    = SW                       # full width
LEGACY_STATE_PATH = "apps/color_picker/state.txt"   # pre-/state save

# Movement tuning. Tap = 1 px nudge; hold for ACCEL_AFTER seconds and the
# cursor steps by FAST_PX_PER_FRAME each frame for fast traversal.
TAP_NUDGE_PX        = 2
SLOW_PX_PER_S       = 60.0
FAST_PX_PER_S       = 380.0
ACCEL_AFTER_S       = 0.4

# Channel labels per model (just for the header readout)
_MODELS = ("RGB", "HSL", "CMYK")

LED_SCALE = 0.4      # WS2812 at full power is glaring a hand's width away


# ── the badge's RGB LED (onboard WS2812, oreoWare.pins.LED_STATUS) ──────────

class _Led:
    """The onboard WS2812 showing one colour. Silently absent off-badge."""

    def __init__(self):
        self._np = None
        self._last = None
        try:
            from machine import Pin
            from neopixel import NeoPixel
            from oreoWare import pins
            self._np = NeoPixel(Pin(pins.LED_STATUS, Pin.OUT), 1)
        except Exception:
            self._np = None

    def show(self, rgb):
        if self._np is None:
            return
        c = led_level(rgb)
        if c == self._last:
            return
        self._last = c
        try:
            self._np[0] = c
            self._np.write()
        except Exception:
            pass

    def off(self):
        self.show((0, 0, 0))


def led_level(rgb):
    """The LED drive level for a colour: scaled, but a lit channel never
    rounds down to 0."""
    out = []
    for v in rgb:
        s = int(v * LED_SCALE + 0.5)
        out.append(1 if (v and not s) else s)
    return tuple(out)


# ── conversions ─────────────────────────────────────────────────────────────

def _rgb_to_hsl(r, g, b):
    rf, gf, bf = r / 255.0, g / 255.0, b / 255.0
    mx = max(rf, gf, bf)
    mn = min(rf, gf, bf)
    l  = (mx + mn) / 2
    if mx == mn:
        return 0, 0, int(round(l * 100))
    d  = mx - mn
    s  = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == rf:
        h = ((gf - bf) / d) % 6
    elif mx == gf:
        h = (bf - rf) / d + 2
    else:
        h = (rf - gf) / d + 4
    return int(round(h * 60)) % 360, int(round(s * 100)), int(round(l * 100))


def _rgb_to_cmyk(r, g, b):
    if r == 0 and g == 0 and b == 0:
        return 0, 0, 0, 100
    rf, gf, bf = r / 255.0, g / 255.0, b / 255.0
    k     = 1 - max(rf, gf, bf)
    inv_k = 1 - k if k < 1 else 1.0
    c = (1 - rf - k) / inv_k
    m = (1 - gf - k) / inv_k
    y = (1 - bf - k) / inv_k
    return (int(round(c * 100)), int(round(m * 100)),
            int(round(y * 100)), int(round(k * 100)))


# ── upscale 80x49 -> 320x196 (nearest-neighbour) ───────────────────────────

def _upscale_4x(src, sw, sh, dw, dh):
    """RGB565-big-endian src buffer -> dest buffer, 4x point-sampled."""
    out = bytearray(dw * dh * 2)
    sx_step = (sw << 16) // dw
    sy_step = (sh << 16) // dh
    sy = 0
    for dy in range(dh):
        src_row = (sy >> 16) * sw * 2
        sx = 0
        row_off = dy * dw * 2
        for dx in range(dw):
            s = src_row + (sx >> 16) * 2
            out[row_off + dx * 2]     = src[s]
            out[row_off + dx * 2 + 1] = src[s + 1]
            sx += sx_step
        sy += sy_step
    return out


def _try_load_spectrum():
    try:
        m = __import__("apps.color_picker.assets.optimized.color_splash",
                       None, None, ["DATA", "W", "H"])
        return bytes(m.DATA), m.W, m.H
    except (ImportError, AttributeError):
        return None


# ── persistence ─────────────────────────────────────────────────────────────

def _save_rgb(rgb):
    if state is None:
        try:
            with open(LEGACY_STATE_PATH, "w") as f:
                f.write("%d,%d,%d" % tuple(int(c) for c in rgb))
        except Exception:
            pass
        return
    state.save("color_picker", {"r": int(rgb[0]), "g": int(rgb[1]),
                                "b": int(rgb[2])})


def _load_rgb():
    try:
        if state is None:
            with open(LEGACY_STATE_PATH) as f:
                r, g, b = (int(x) for x in f.read().strip().split(","))
            s = {"r": r, "g": g, "b": b}
        else:
            s = state.load_migrating("color_picker", {"r": 255, "g": 93, "b": 104},
                                     LEGACY_STATE_PATH, ("r", "g", "b"))
        r, g, b = int(s["r"]), int(s["g"]), int(s["b"])
        return (max(0, min(255, r)),
                max(0, min(255, g)),
                max(0, min(255, b)))
    except Exception:
        return (255, 93, 104)


class App(oreoOS.App):
    name         = "Color"
    SHOW_LOADING = True       # ~300 ms upscale at entry — hidden by the panel
    # C toggles the LED here; a double-tap of C opens the notification panel.
    CAPTURES_C   = True

    # ── lifecycle ──────────────────────────────────────────────────────────
    def on_enter(self, os):
        self._os = os
        # Load the 80x49 baked rainbow and upscale to fill the play area.
        # Cached on the instance — no per-frame work.
        spec = _try_load_spectrum()
        if spec:
            src, sw, sh = spec
            self._bg = _upscale_4x(src, sw, sh, PLAY_W, PLAY_H)
            self._bg_w, self._bg_h = PLAY_W, PLAY_H
        else:
            self._bg = None
            self._bg_w = self._bg_h = 0

        # Cursor starts mid-screen (often a nice saturated colour). Stored
        # as floats so long-press acceleration can move in sub-pixel steps.
        self._cx, self._cy = PLAY_W / 2.0, PLAY_H / 2.0
        self._rgb = _load_rgb()       # restored from disk
        self._mode = "RGB"            # header readout model
        self._saved_flash = 0.0
        # Hold-times for direction buttons (seconds held). Reset to 0 the
        # instant a button is released so the next tap restarts the curve.
        self._hold_t = {api.BTN_LEFT: 0.0, api.BTN_RIGHT: 0.0,
                        api.BTN_UP:   0.0, api.BTN_DOWN:  0.0}
        self._sample_color()
        self._led = _Led()
        try:
            self._led_on = bool(os.settings_get("color_picker_led", True))
        except Exception:
            self._led_on = True
        self._update_led()
        self._dirty = True

    def on_exit(self):
        try:
            self._led.off()
        except Exception:
            pass

    def _update_led(self):
        if self._led_on:
            self._led.show(self._rgb)
        else:
            self._led.off()

    # ── input ──────────────────────────────────────────────────────────────
    def on_button_press(self, btn):
        # Single-tap nudge so a quick press always moves at least a couple
        # of pixels (the update() loop only ramps after ACCEL_AFTER_S).
        if   btn == api.BTN_LEFT:   self._cx -= TAP_NUDGE_PX
        elif btn == api.BTN_RIGHT:  self._cx += TAP_NUDGE_PX
        elif btn == api.BTN_UP:     self._cy -= TAP_NUDGE_PX
        elif btn == api.BTN_DOWN:   self._cy += TAP_NUDGE_PX
        elif btn == api.BTN_B:
            i = _MODELS.index(self._mode)
            self._mode = _MODELS[(i + 1) % len(_MODELS)]
        elif btn == api.BTN_A:
            _save_rgb(self._rgb)
            try:
                self._os.settings_set("color_picker_rgb", self._rgb)
            except Exception:
                pass
            self._saved_flash = 1.2
        elif btn == api.BTN_C:
            self._led_on = not self._led_on
            try:
                self._os.settings_set("color_picker_led", self._led_on)
            except Exception:
                pass
        self._clamp_cursor()
        self._sample_color()
        self._update_led()
        self._dirty = True

    def update(self, dt):
        # Long-press: poll which dir buttons are held and accumulate.
        moved = False
        b = self._os.buttons
        for btn, dx, dy in ((api.BTN_LEFT,  -1, 0),
                            (api.BTN_RIGHT, +1, 0),
                            (api.BTN_UP,     0, -1),
                            (api.BTN_DOWN,   0, +1)):
            try:
                held = b.is_pressed(btn)
            except Exception:
                held = False
            if held:
                self._hold_t[btn] += dt
                # Start slow, ramp to fast after ACCEL_AFTER_S held.
                t = self._hold_t[btn]
                if t > ACCEL_AFTER_S:
                    speed = FAST_PX_PER_S
                else:
                    speed = SLOW_PX_PER_S
                self._cx += dx * speed * dt
                self._cy += dy * speed * dt
                moved = True
            else:
                self._hold_t[btn] = 0.0

        if moved:
            self._clamp_cursor()
            self._sample_color()
            self._update_led()
            self._dirty = True

        if self._saved_flash > 0:
            self._saved_flash = max(0.0, self._saved_flash - dt)
            self._dirty = True

    def _clamp_cursor(self):
        if self._cx < 0:           self._cx = 0
        if self._cy < 0:           self._cy = 0
        if self._cx > PLAY_W - 1:  self._cx = PLAY_W - 1
        if self._cy > PLAY_H - 1:  self._cy = PLAY_H - 1

    def _sample_color(self):
        """Read the RGB565 pixel under the cursor out of the upscaled bg."""
        if not self._bg:
            return
        x = int(self._cx); y = int(self._cy)
        i = (y * self._bg_w + x) * 2
        v = (self._bg[i] << 8) | self._bg[i + 1]
        r = ((v >> 11) & 0x1F) << 3
        g = ((v >>  5) & 0x3F) << 2
        b = ( v        & 0x1F) << 3
        # Restore lost low-order bits with a tiny smear so dark colours
        # don't read as pure black just from RGB565 truncation.
        self._rgb = (r | (r >> 5), g | (g >> 6), b | (b >> 5))

    # ── render ────────────────────────────────────────────────────────────
    def draw(self, d):
        if not self._dirty:
            return
        self._dirty = False

        # ── spectrum (or solid fallback) ───────────────────────────────────
        if self._bg:
            d.blit(self._bg, 0, PLAY_TOP, self._bg_w, self._bg_h)
        else:
            d.rect(0, PLAY_TOP, PLAY_W, PLAY_H,
                   api.rgb(*self._rgb), fill=True)

        # ── header bar (pink, compact) ─────────────────────────────────────
        self._draw_header(d)
        widgets.draw_hint(d, "arrows=pick B=mode A=save C=LED")

        # ── crosshair ──────────────────────────────────────────────────────
        self._draw_cursor(d)

        # ── "Saved!" toast ────────────────────────────────────────────────
        if self._saved_flash > 0:
            msg = "Saved!"
            mw = len(msg) * 16
            tx = (SW - mw) // 2
            ty = PLAY_BOT - 32
            d.rect(tx - 8, ty - 4, mw + 16, 22, theme.GREEN, fill=True)
            d.text(msg, tx, ty, api.WHITE, scale=2)

    # ── header pieces ─────────────────────────────────────────────────────
    def _draw_header(self, d):
        H = widgets.HEADER_H
        d.rect(0, 0, SW, H, theme.PRIMARY, fill=True)
        d.rect(0, H - 1, SW, 1, theme.GOLD, fill=True)
        d.text("COLOR", 6, (H - 8) // 2, api.WHITE)
        # Live preview swatch (small square, pink-bordered)
        sw_sz = H - 8
        sw_x  = 50
        sw_y  = (H - sw_sz) // 2
        d.rect(sw_x - 1, sw_y - 1, sw_sz + 2, sw_sz + 2, theme.GOLD, fill=True)
        d.rect(sw_x,     sw_y,     sw_sz,     sw_sz,    api.rgb(*self._rgb),
               fill=True)
        # Tiny readout per the active model
        readout = self._readout_str()
        d.text(readout, sw_x + sw_sz + 8, (H - 8) // 2, api.WHITE)
        if self._led_on:
            d.text("LED", SW - 30, (H - 8) // 2, theme.GOLD)

    def _readout_str(self):
        r, g, b = self._rgb
        if self._mode == "RGB":
            return "RGB %d %d %d" % (r, g, b)
        if self._mode == "HSL":
            h, s, l = _rgb_to_hsl(r, g, b)
            return "HSL %d %d %d" % (h, s, l)
        c, m, y, k = _rgb_to_cmyk(r, g, b)
        return "CMYK %d %d %d %d" % (c, m, y, k)

    # ── crosshair drawing ────────────────────────────────────────────────
    def _draw_cursor(self, d):
        cx = int(self._cx)
        cy = int(self._cy) + PLAY_TOP
        # Outer dark ring + inner white ring + 1-px black dot in the middle.
        # Two colour layers make the cursor visible on ANY background.
        r1, r2 = 7, 5
        d.rect(cx - r1, cy,      2 * r1 + 1, 1, api.BLACK, fill=True)
        d.rect(cx,      cy - r1, 1, 2 * r1 + 1, api.BLACK, fill=True)
        d.rect(cx - r2, cy,      2 * r2 + 1, 1, api.WHITE, fill=True)
        d.rect(cx,      cy - r2, 1, 2 * r2 + 1, api.WHITE, fill=True)
        # Small open square at the centre, dark outline + light interior
        d.rect(cx - 2, cy - 2, 5, 5, api.BLACK, fill=False)
        d.rect(cx - 1, cy - 1, 3, 3, api.WHITE, fill=False)

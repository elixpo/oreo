import oreoOS
from oreoOS import api, theme, widgets


SW = api.SCREEN_W
SH = api.SCREEN_H

# Channel definitions per model. Each entry is (label, max_value).
MODELS = {
    "RGB":  (("R", 255), ("G", 255), ("B", 255)),
    "HSL":  (("H", 359), ("S", 100), ("L", 100)),
    "CMYK": (("C", 100), ("M", 100), ("Y", 100), ("K", 100)),
}
MODEL_ORDER = ("RGB", "HSL", "CMYK")

STATE_PATH = "apps/color_picker/state.txt"


# ── colour-space conversions (RGB↔HSL, RGB↔CMYK) ────────────────────────────

def _rgb_to_hsl(r, g, b):
    rf, gf, bf = r / 255.0, g / 255.0, b / 255.0
    mx, mn = max(rf, gf, bf), min(rf, gf, bf)
    l = (mx + mn) / 2.0
    if mx == mn:
        return 0, 0, int(round(l * 100))
    d = mx - mn
    s = d / (2.0 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == rf:
        h = ((gf - bf) / d) % 6
    elif mx == gf:
        h = ((bf - rf) / d) + 2
    else:
        h = ((rf - gf) / d) + 4
    return int(round(h * 60)) % 360, int(round(s * 100)), int(round(l * 100))


def _hsl_to_rgb(h, s, l):
    s, l = s / 100.0, l / 100.0
    if s == 0:
        v = int(round(l * 255))
        return v, v, v
    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs(((h / 60.0) % 2) - 1))
    m = l - c / 2.0
    seg = int(h // 60) % 6
    rp, gp, bp = ((c, x, 0), (x, c, 0), (0, c, x),
                  (0, x, c), (x, 0, c), (c, 0, x))[seg]
    return (int(round((rp + m) * 255)),
            int(round((gp + m) * 255)),
            int(round((bp + m) * 255)))


def _rgb_to_cmyk(r, g, b):
    if r == 0 and g == 0 and b == 0:
        return 0, 0, 0, 100
    rf, gf, bf = r / 255.0, g / 255.0, b / 255.0
    k = 1 - max(rf, gf, bf)
    inv_k = 1 - k if k < 1 else 1.0
    c = (1 - rf - k) / inv_k
    m = (1 - gf - k) / inv_k
    y = (1 - bf - k) / inv_k
    return (int(round(c * 100)), int(round(m * 100)),
            int(round(y * 100)), int(round(k * 100)))


def _cmyk_to_rgb(c, m, y, k):
    c, m, y, k = c / 100.0, m / 100.0, y / 100.0, k / 100.0
    r = 255 * (1 - c) * (1 - k)
    g = 255 * (1 - m) * (1 - k)
    b = 255 * (1 - y) * (1 - k)
    return int(round(r)), int(round(g)), int(round(b))


def _save_rgb(rgb):
    try:
        with open(STATE_PATH, "w") as f:
            f.write("%d,%d,%d" % rgb)
    except Exception:
        pass


def _load_rgb():
    try:
        with open(STATE_PATH) as f:
            r, g, b = (int(x) for x in f.read().strip().split(","))
        return (max(0, min(255, r)),
                max(0, min(255, g)),
                max(0, min(255, b)))
    except Exception:
        return (255, 93, 104)   # theme.PRIMARY pink as a friendly default


class App(oreoOS.App):
    name = "Color Picker"

    def on_enter(self, os):
        self._os    = os
        self._rgb   = list(_load_rgb())   # source of truth
        self._model = "RGB"
        self._sel   = 0                   # which channel row is highlighted
        self._saved_flash = 0.0           # ms timer for the "saved" toast
        self._dirty = True

    # ── input ────────────────────────────────────────────────────────────
    def on_button_press(self, btn):
        chans = MODELS[self._model]
        n     = len(chans)
        if btn == api.BTN_LEFT:
            self._sel = (self._sel - 1) % n
        elif btn == api.BTN_RIGHT:
            self._sel = (self._sel + 1) % n
        elif btn == api.BTN_UP:
            self._adjust(+1)
        elif btn == api.BTN_DOWN:
            self._adjust(-1)
        elif btn == api.BTN_B:
            # Cycle model. Stay on a valid channel index for the new model.
            idx = MODEL_ORDER.index(self._model)
            self._model = MODEL_ORDER[(idx + 1) % len(MODEL_ORDER)]
            self._sel   = min(self._sel, len(MODELS[self._model]) - 1)
        elif btn == api.BTN_A:
            _save_rgb(tuple(self._rgb))
            try:
                self._os.settings_set("color_picker_rgb", tuple(self._rgb))
            except Exception:
                pass
            self._saved_flash = 1.2       # show "Saved!" for ~1.2 s
        self._dirty = True

    # Step size: 1 per tap for RGB / CMYK / HSL S+L; H steps by 5 since
    # 360 / 1 would be slow.
    def _adjust(self, sign):
        _, max_v = MODELS[self._model][self._sel]
        step = 5 if (self._model == "HSL" and self._sel == 0) else 1
        delta = sign * step
        if self._model == "RGB":
            self._rgb[self._sel] = max(0, min(255, self._rgb[self._sel] + delta))
        elif self._model == "HSL":
            h, s, l = _rgb_to_hsl(*self._rgb)
            vals = [h, s, l]
            vals[self._sel] = (vals[self._sel] + delta) % (max_v + 1)
            if vals[self._sel] < 0:
                vals[self._sel] += (max_v + 1)
            self._rgb = list(_hsl_to_rgb(*vals))
        elif self._model == "CMYK":
            c, m, y, k = _rgb_to_cmyk(*self._rgb)
            vals = [c, m, y, k]
            vals[self._sel] = max(0, min(max_v, vals[self._sel] + delta))
            self._rgb = list(_cmyk_to_rgb(*vals))

    def update(self, dt):
        if self._saved_flash > 0:
            self._saved_flash = max(0.0, self._saved_flash - dt)
            self._dirty = True

    # ── render ───────────────────────────────────────────────────────────
    def draw(self, d):
        if not self._dirty:
            return

        play_top    = widgets.HEADER_H
        play_bot    = SH - widgets.HINT_H
        swatch_rgb  = api.rgb(self._rgb[0], self._rgb[1], self._rgb[2])

        # ── full-screen swatch: the whole play area IS the colour ─────────
        d.rect(0, play_top, SW, play_bot - play_top, swatch_rgb, fill=True)

        # ── header: canonical RGB values + hex on a pink bar ──────────────
        # Render directly (not widgets.draw_header) so we control the layout
        # of the title + values without an extra string concat.
        d.rect(0, 0, SW, widgets.HEADER_H, theme.PRIMARY, fill=True)
        d.rect(0, widgets.HEADER_H - 1, SW, 1, theme.GOLD, fill=True)
        d.text("COLOR", 8, (widgets.HEADER_H - 16) // 2, api.WHITE, scale=2)
        rgb_str = "R%d  G%d  B%d  #%02X%02X%02X" % (
            self._rgb[0], self._rgb[1], self._rgb[2],
            self._rgb[0], self._rgb[1], self._rgb[2])
        # Truncate from the left if needed (rare — fits at 320 px easily).
        rw = len(rgb_str) * 8
        d.text(rgb_str, SW - rw - 8, (widgets.HEADER_H - 8) // 2, api.WHITE)

        widgets.draw_hint(d, "UP/DN=val  L/R=row  B=model  A=save")

        # ── floating overlay card with the active model's channels ────────
        chans   = MODELS[self._model]
        vals    = self._values_for_model()
        row_h   = 20
        pad_y   = 6
        pad_x   = 10
        card_h  = pad_y * 2 + 14 + row_h * len(chans)
        card_w  = 200
        card_x  = (SW - card_w) // 2
        card_y  = play_bot - card_h - 8

        # Drop shadow + cream card so it reads on any swatch colour.
        d.rect(card_x + 2, card_y + 2, card_w, card_h, theme.MUTED2, fill=True)
        d.rect(card_x,     card_y,     card_w, card_h, theme.CARD,   fill=True)
        d.rect(card_x,     card_y,     card_w, 2,      theme.PRIMARY, fill=True)

        # Model label (top of the card)
        d.text("Mode: %s" % self._model,
               card_x + pad_x, card_y + pad_y, theme.PRIMARY, scale=1)

        # Channel rows
        rows_top = card_y + pad_y + 14
        for i, (label, max_v) in enumerate(chans):
            row_y = rows_top + i * row_h
            sel   = (i == self._sel)
            if sel:
                d.rect(card_x + 2, row_y - 2, card_w - 4, row_h - 2,
                       theme.DOCK_SEL, fill=True)
                d.rect(card_x + 2, row_y - 2, 3, row_h - 2,
                       theme.PRIMARY, fill=True)
            d.text(label, card_x + pad_x, row_y + 4,
                   theme.TEXT_BRIGHT, scale=1)
            # Right-aligned numeric value.
            v   = vals[i]
            s   = "%d" % v
            val_w = len(s) * 8
            val_x = card_x + card_w - pad_x - val_w
            d.text(s, val_x, row_y + 4, theme.TEXT_BRIGHT)
            # Bar between label and value.
            bar_x = card_x + pad_x + 16
            bar_w = val_x - bar_x - 8
            if bar_w > 6:
                d.rect(bar_x, row_y + 7, bar_w, 4, theme.MUTED2, fill=True)
                fill_w = int(bar_w * v / max(1, max_v))
                d.rect(bar_x, row_y + 7, fill_w, 4, theme.PRIMARY, fill=True)

        # "Saved!" toast — overlay above the card.
        if self._saved_flash > 0:
            msg = "Saved!"
            mw  = len(msg) * 16
            tx  = (SW - mw) // 2
            ty  = card_y - 28
            d.rect(tx - 8, ty - 4, mw + 16, 22, theme.GREEN, fill=True)
            d.text(msg, tx, ty, api.WHITE, scale=2)

        self._dirty = False

    def _values_for_model(self):
        if self._model == "RGB":
            return tuple(self._rgb)
        if self._model == "HSL":
            return _rgb_to_hsl(*self._rgb)
        return _rgb_to_cmyk(*self._rgb)

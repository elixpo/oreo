"""Gallery — paginate optimised photo bytearrays from apps/gallery/photos/.

Drop user photos in as `.py` modules (W, H, DATA) — generate via
tools/optimize_assets.py --app gallery once they've been added to
apps/gallery/assets/raw/.

Controls: LEFT/RIGHT page through photos; A = refresh; HOME = exit.
"""

import os as _os
import lix
from lix import api
from lix_os import theme, widgets

SW = api.SCREEN_W
SH = api.SCREEN_H


def _list_photos():
    """Return sorted list of photo module names in apps/gallery/assets/optimized."""
    try:
        names = []
        for f in _os.listdir("apps/gallery/assets/optimized"):
            if f.endswith(".py") and not f.startswith("_"):
                names.append(f[:-3])
        names.sort()
        return names
    except OSError:
        return []


def _load_photo(name):
    try:
        mod = __import__("apps.gallery.assets.optimized." + name,
                         None, None, ["DATA", "W", "H"])
        return (bytearray(mod.DATA), mod.W, mod.H)
    except (ImportError, AttributeError):
        return None


class App(lix.App):
    name = "Gallery"

    def on_enter(self, os):
        self._os    = os
        self._names = _list_photos()
        self._idx   = 0
        self._cache = {}
        self._dirty = True

    def _photo(self, idx):
        name = self._names[idx]
        if name not in self._cache:
            self._cache[name] = _load_photo(name)
        return self._cache.get(name)

    def on_button_press(self, btn):
        if not self._names:
            return
        if btn == api.BTN_LEFT:
            self._idx = (self._idx - 1) % len(self._names); self._dirty = True
        elif btn == api.BTN_RIGHT:
            self._idx = (self._idx + 1) % len(self._names); self._dirty = True
        elif btn == api.BTN_A:
            # Refresh listing (e.g., after dropping new photos on the FS)
            self._names = _list_photos()
            self._cache = {}
            self._idx   = 0
            self._dirty = True

    def update(self, dt):
        pass

    def draw(self, d):
        if not self._dirty:
            return
        d.clear(theme.BG)
        widgets.draw_header(d, "GALLERY")
        widgets.draw_hint  (d, "L/R=prev/next  A=refresh")

        if not self._names:
            self._draw_empty_state(d)
            self._dirty = False
            return

        ph = self._photo(self._idx)
        ay = widgets.HEADER_H + 8
        ah = SH - widgets.HEADER_H - widgets.HINT_H - 16
        if ph:
            data, pw, phh = ph
            px = (SW - pw) // 2
            py = ay + (ah - phh) // 2
            d.blit(data, px, py, pw, phh)
        else:
            d.text("broken photo", (SW - 12 * 16) // 2, ay + 40, theme.MUTED, scale=2)

        # Caption + index
        name = self._names[self._idx]
        d.text(name[:18], (SW - len(name[:18]) * 8) // 2, SH - widgets.HINT_H - 14,
               theme.TEXT_BRIGHT)
        idx_str = "%d/%d" % (self._idx + 1, len(self._names))
        d.text(idx_str, SW - len(idx_str) * 8 - 6, ay - 1, theme.PRIMARY)

        self._dirty = False

    # ── empty state ──────────────────────────────────────────────────────
    def _draw_empty_state(self, d):
        """Fancy card prompting the user to drop photos in."""
        # Card geometry
        card_w = SW - 40
        card_h = SH - widgets.HEADER_H - widgets.HINT_H - 40
        card_x = (SW - card_w) // 2
        card_y = widgets.HEADER_H + 20

        # Soft shadow
        d.rect(card_x + 3, card_y + 3, card_w, card_h, theme.MUTED2, fill=True)
        # Card body
        d.rect(card_x,     card_y,     card_w, card_h, theme.CARD, fill=True)
        # Accent stripes (top + side)
        d.rect(card_x,     card_y,     card_w, 4,      theme.PRIMARY, fill=True)
        d.rect(card_x,     card_y + 4, 4,      card_h - 4, theme.TEAL, fill=True)

        # Picture-frame decoration in the upper area
        fx, fy = card_x + 16, card_y + 16
        fw, fh = 56, 44
        d.rect(fx,     fy,     fw, fh, theme.BG, fill=True)
        d.rect(fx,     fy,     fw,  2, theme.PRIMARY, fill=True)
        d.rect(fx,     fy+fh-2, fw, 2, theme.PRIMARY, fill=True)
        d.rect(fx,     fy,      2, fh, theme.PRIMARY, fill=True)
        d.rect(fx+fw-2, fy,     2, fh, theme.PRIMARY, fill=True)
        # tiny "mountain + sun" inside the frame
        d.rect(fx + 38, fy + 8,  6, 6, theme.GOLD,    fill=True)
        d.rect(fx + 8,  fy + 28, 14, 12, theme.TEAL,  fill=True)
        d.rect(fx + 22, fy + 22, 24, 18, theme.GREEN, fill=True)
        d.rect(fx + 14, fy + fh - 6, fw - 28, 2, theme.MUTED, fill=True)

        # Big heading
        title = "Your gallery"
        tx = card_x + 84
        d.text(title, tx, card_y + 14, theme.PRIMARY, scale=2)
        sub = "is empty"
        d.text(sub, tx, card_y + 32, theme.TEXT_BRIGHT, scale=2)

        # Instruction lines (centred)
        msg_y = card_y + 72
        lines = [
            ("Share some moments!",        theme.PRIMARY,     2),
            ("",                           None,              1),
            ("Drop pictures into",         theme.TEXT_BRIGHT, 1),
            ("apps/gallery/assets/raw/",   theme.TEAL,        1),
            ("(.jpg .jpeg .png)",          theme.MUTED,       1),
            ("",                           None,              1),
            ("Then run:",                  theme.TEXT_BRIGHT, 1),
            ("optimize_assets --app",      theme.GOLD,        1),
            ("gallery",                    theme.GOLD,        1),
        ]
        for line, col, sc in lines:
            if line:
                lw = len(line) * 8 * sc
                d.text(line, (SW - lw) // 2, msg_y, col, scale=sc)
            msg_y += (10 * sc) + 2

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
            d.text("No photos.",      (SW - 10 * 16) // 2, 90,  theme.MUTED, scale=2)
            d.text("Drop them in",    (SW - 12 * 8) // 2, 130, theme.TEXT_BRIGHT)
            d.text("apps/gallery/",   (SW - 13 * 8) // 2, 144, theme.TEXT_BRIGHT)
            d.text("assets/raw/*.png",(SW - 17 * 8) // 2, 158, theme.TEXT_BRIGHT)
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

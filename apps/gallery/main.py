"""Gallery — flip through optimised photos, or read upload instructions.

The carousel always has one extra "ADD" tile at the end. Selecting it
opens a scrollable instruction panel that walks the user through dropping
a new picture in and re-flashing the badge.

Controls:
  LEFT / RIGHT   previous / next tile (photos + the ADD tile at the end)
  UP   / DOWN    scroll the instruction panel (when on the ADD tile)
  A              refresh the photo listing
  HOME           apps drawer
"""

import os as _os
import oreoOS
from oreoOS import api
from oreoOS import theme, widgets

SW = api.SCREEN_W
SH = api.SCREEN_H


def _list_photos():
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


# Instruction text laid out as a list of (kind, payload). kind is "h"
# (heading), "b" (bullet), or "code" (monospace command). Centralised
# here so the panel renderer stays simple.
_HELP = [
    ("h",   "Add a new photo"),
    ("b",   "Drop a JPG or PNG into"),
    ("code","apps/gallery/assets/raw/"),
    ("b",   "Square images render best;"),
    ("b",   "max ~240x240 to fit the LCD."),
    ("h",   "Optimise it"),
    ("b",   "From the repo root run:"),
    ("code","python tools/optimize_assets.py"),
    ("code","         --app gallery"),
    ("b",   "This bakes each raw image into"),
    ("b",   "a tiny RGB565 .py module."),
    ("h",   "Flash the badge"),
    ("b",   "Plug in the badge over USB then:"),
    ("code","python tools/deploy.py"),
    ("b",   "The deploy script auto-skips"),
    ("b",   "unchanged files (use --force to"),
    ("b",   "push everything)."),
    ("h",   "On the badge"),
    ("b",   "Open Gallery, press A to refresh"),
    ("b",   "the listing. New photos appear"),
    ("b",   "in alphabetical order."),
]


class App(oreoOS.App):
    name = "Gallery"

    def on_enter(self, os):
        self._os    = os
        self._names = _list_photos()
        self._idx   = 0
        self._scroll = 0
        self._cache = {}
        self._dirty = True

    def _is_add_tile(self):
        return self._idx == len(self._names)

    def _photo(self, idx):
        name = self._names[idx]
        if name not in self._cache:
            self._cache[name] = _load_photo(name)
        return self._cache.get(name)

    def on_button_press(self, btn):
        total = len(self._names) + 1     # photos + ADD tile
        if btn == api.BTN_LEFT:
            self._idx = (self._idx - 1) % total
            self._scroll = 0
            self._dirty = True
        elif btn == api.BTN_RIGHT:
            self._idx = (self._idx + 1) % total
            self._scroll = 0
            self._dirty = True
        elif btn == api.BTN_UP and self._is_add_tile():
            self._scroll = max(0, self._scroll - 1)
            self._dirty = True
        elif btn == api.BTN_DOWN and self._is_add_tile():
            self._scroll = min(self._scroll + 1, max(0, len(_HELP) - 1))
            self._dirty = True
        elif btn == api.BTN_A:
            # Refresh listing (e.g., after dropping new photos on the FS)
            self._names = _list_photos()
            self._cache = {}
            self._idx   = 0
            self._scroll = 0
            self._dirty = True

    def update(self, dt):
        pass

    def draw(self, d):
        if not self._dirty:
            return
        d.clear(theme.BG)
        widgets.draw_header(d, "GALLERY")
        if self._is_add_tile():
            widgets.draw_hint(d, "UP/DOWN=scroll  L/R=back")
        else:
            widgets.draw_hint(d, "L/R=prev/next  A=refresh")

        # Top-right counter — counts the ADD tile too so the user knows
        # there's something after the last photo.
        total = len(self._names) + 1
        idx_str = "%d/%d" % (self._idx + 1, total)
        d.text(idx_str, SW - len(idx_str) * 8 - 6, widgets.HEADER_H + 2,
               theme.PRIMARY)

        if self._is_add_tile():
            self._draw_add_tile(d)
        else:
            self._draw_photo(d)

        self._dirty = False

    # ── photo render ─────────────────────────────────────────────────────
    def _draw_photo(self, d):
        ph = self._photo(self._idx)
        ay = widgets.HEADER_H + 8
        ah = SH - widgets.HEADER_H - widgets.HINT_H - 16
        if ph:
            data, pw, phh = ph
            px = (SW - pw) // 2
            py = ay + (ah - phh) // 2
            d.blit(data, px, py, pw, phh)
        else:
            d.text("broken photo", (SW - 12 * 16) // 2, ay + 40,
                   theme.MUTED, scale=2)

        name = self._names[self._idx]
        d.text(name[:18], (SW - len(name[:18]) * 8) // 2,
               SH - widgets.HINT_H - 14, theme.TEXT_BRIGHT)

    # ── ADD tile: scrollable instructions ────────────────────────────────
    def _draw_add_tile(self, d):
        # Cream card filling the play area.
        card_x = 10
        card_y = widgets.HEADER_H + 4
        card_w = SW - 20
        card_h = SH - widgets.HEADER_H - widgets.HINT_H - 8
        d.rect(card_x + 2, card_y + 2, card_w, card_h, theme.MUTED2, fill=True)
        d.rect(card_x,     card_y,     card_w, card_h, theme.CARD,   fill=True)
        d.rect(card_x,     card_y,     card_w, 3,      theme.PRIMARY, fill=True)

        # Big pink "+" badge on the left
        bx, by, bsz = card_x + 12, card_y + 12, 36
        d.rect(bx, by, bsz, bsz, theme.PRIMARY, fill=True)
        d.rect(bx + bsz // 2 - 2, by + 6,         4, bsz - 12, api.WHITE, fill=True)
        d.rect(bx + 6,            by + bsz // 2 - 2, bsz - 12, 4, api.WHITE, fill=True)

        # Heading next to the badge.
        d.text("Add a photo", bx + bsz + 12, by + 4, theme.PRIMARY, scale=2)
        d.text("scroll UP / DOWN", bx + bsz + 12, by + 24, theme.MUTED)

        # Scrollable instructions list — only render the rows that fit in
        # the panel area below the heading.
        list_y     = card_y + 12 + bsz + 16
        list_bot   = card_y + card_h - 8
        line_h_h   = 18      # heading row height
        line_h_b   = 12      # bullet / code row height
        text_x     = card_x + 16
        max_chars  = (card_w - 24) // 8

        rows = _HELP[self._scroll:]
        cur_y = list_y
        for kind, payload in rows:
            row_h = line_h_h if kind == "h" else line_h_b
            if cur_y + row_h > list_bot:
                break
            if kind == "h":
                # Pink heading with a gold underline.
                d.text(payload, text_x, cur_y, theme.PRIMARY, scale=2)
                d.rect(text_x, cur_y + 17, len(payload) * 16, 1, theme.GOLD, fill=True)
            elif kind == "b":
                # Standard bullet — pink dot + dim text.
                d.rect(text_x, cur_y + 4, 3, 3, theme.PRIMARY, fill=True)
                d.text(payload[:max_chars - 1], text_x + 10, cur_y,
                       theme.TEXT_BRIGHT)
            elif kind == "code":
                # Monospaced command on a tinted strip.
                strip_h = 12
                d.rect(text_x + 8, cur_y - 1, card_w - 32, strip_h,
                       theme.DOCK_SEL, fill=True)
                d.text(payload[:max_chars - 2], text_x + 12, cur_y,
                       theme.TEAL)
            cur_y += row_h

        # Scroll indicators — small arrows on the right edge when more
        # content exists above / below the visible window.
        sx = card_x + card_w - 14
        if self._scroll > 0:
            d.text("^", sx, list_y - 12, theme.PRIMARY, scale=2)
        last_rendered = self._scroll + sum(
            1 for _ in range(min(len(_HELP) - self._scroll,
                                  (list_bot - list_y) // line_h_b)))
        if self._scroll + last_rendered < len(_HELP):
            d.text("v", sx, list_bot - 12, theme.PRIMARY, scale=2)

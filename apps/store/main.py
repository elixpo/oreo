"""App Market — install / uninstall optional apps from /apps_market/.

Lists every catalogue entry as a card. Tap A on an uninstalled card to
copy the tree from apps_market/<name>/ → apps/<name>/ (tile then appears
in the drawer immediately on next launcher entry). Tap A again to
uninstall — the catalogue copy stays put for a clean re-install later.

Controls:
  UP / DOWN  walk the list
  A          install / uninstall the selected app
  HOME       back to the drawer
"""

import oreoOS
from oreoOS import api, theme, widgets
from oreoOS import store


SW = api.SCREEN_W
SH = api.SCREEN_H

CARD_H       = 44
CARD_GAP     = 4
LIST_TOP_Y   = widgets.HEADER_H + 6
ROW_PAD_X    = 10
ICON_BOX     = 32
ACT_W        = 78        # right-edge action chip
ACT_H        = 18

STATE_INSTALLED   = "INSTALLED"
STATE_INSTALL     = "INSTALL"
STATE_BUSY        = "..."


class App(oreoOS.App):
    name         = "App Market"
    author       = "Circuit-Overtime"
    SHOW_LOADING = True

    def on_enter(self, os_):
        super().on_enter(os_)
        self._os    = os_
        self._sel   = 0
        self._top   = 0     # first visible row
        self._busy  = None  # dir name currently mid-install/uninstall
        self._msg   = ""    # transient status line, e.g. "Installed"
        self._items = store.list_market()
        self._dirty = True

    # ── input ──────────────────────────────────────────────────────────
    def on_button_press(self, btn):
        if btn == api.BTN_HOME:
            self._os.quit()
            return
        n = len(self._items)
        if not n:
            return
        if btn == api.BTN_UP:
            self._sel = (self._sel - 1) % n
        elif btn == api.BTN_DOWN:
            self._sel = (self._sel + 1) % n
        elif btn == api.BTN_A:
            self._toggle_selected()
        else:
            return
        self._ensure_visible()
        self._dirty = True

    def _ensure_visible(self):
        vis_rows = max(1, (SH - LIST_TOP_Y - widgets.HINT_H - 4)
                       // (CARD_H + CARD_GAP))
        if self._sel < self._top:
            self._top = self._sel
        elif self._sel >= self._top + vis_rows:
            self._top = self._sel - vis_rows + 1

    def _toggle_selected(self):
        item = self._items[self._sel]
        name = item["dir"]
        self._busy = name
        self._msg  = ""
        self._dirty = True
        # Force a paint of the BUSY state before the (synchronous, slow
        # on flash) install/uninstall fires, so the user sees feedback.
        try:
            self.draw(self._os.display)
            self._os.display.present()
        except Exception:
            pass
        if item["installed"]:
            ok = store.uninstall(name)
            self._msg = "Uninstalled" if ok else "Failed"
        else:
            ok = store.install(name)
            self._msg = "Installed" if ok else "Failed"
        # Refresh the snapshot so the row's "installed" flag flips.
        self._items = store.list_market()
        # Re-seat the selection (list ordering didn't change, but defend
        # against future re-sorts).
        for i, it in enumerate(self._items):
            if it["dir"] == name:
                self._sel = i
                break
        self._busy = None

    # ── render ─────────────────────────────────────────────────────────
    def draw(self, d):
        if not self._dirty:
            return
        self._dirty = False
        d.clear(theme.BG)
        widgets.draw_header(d, "APP MARKET")
        widgets.draw_hint(d, "A=install/uninstall  HOME=back")

        if not self._items:
            msg = "no apps in /apps_market/"
            d.text(msg, (SW - len(msg) * 8) // 2,
                   SH // 2 - 4, theme.MUTED, scale=1)
            d.text("re-deploy with the new layout",
                   (SW - 30 * 8) // 2, SH // 2 + 10,
                   theme.MUTED2, scale=1)
            return

        vis_rows = max(1, (SH - LIST_TOP_Y - widgets.HINT_H - 4)
                       // (CARD_H + CARD_GAP))
        for vi in range(vis_rows):
            i = self._top + vi
            if i >= len(self._items):
                break
            self._draw_card(d, vi, i)

        # Transient status line at the bottom-left of the play area.
        if self._msg:
            d.text(self._msg, ROW_PAD_X, SH - widgets.HINT_H - 12,
                   theme.PRIMARY, scale=1)

    def _draw_card(self, d, vi, i):
        item = self._items[i]
        sel  = (i == self._sel)
        y    = LIST_TOP_Y + vi * (CARD_H + CARD_GAP)

        bg   = theme.DOCK_SEL if sel else theme.CARD
        d.rect(6, y, SW - 12, CARD_H, bg, fill=True)
        if sel:
            d.rect(6, y,              SW - 12, 1, theme.SEL_BORDER, fill=True)
            d.rect(6, y + CARD_H - 1, SW - 12, 1, theme.SEL_BORDER, fill=True)
            d.rect(6, y,              1, CARD_H,  theme.SEL_BORDER, fill=True)
            d.rect(SW - 7, y,         1, CARD_H,  theme.SEL_BORDER, fill=True)

        # Icon thumbnail (32×32 if the optimized module exists).
        icon = self._icon_for(item)
        if icon:
            data, iw, ih = icon
            d.blit(data, ROW_PAD_X, y + (CARD_H - ih) // 2, iw, ih)
        else:
            # First-letter fallback so a missing optimized icon doesn't
            # leave an empty box.
            letter = (item["name"] or "?")[0].upper()
            d.text(letter, ROW_PAD_X + 8, y + 8, theme.PRIMARY, scale=3)

        # Title + author
        tx = ROW_PAD_X + ICON_BOX + 10
        d.text(item["name"][:18], tx, y + 6,  theme.TEXT_BRIGHT, scale=2)
        author = item.get("author") or ""
        if author:
            d.text(("by " + author)[:24], tx, y + 26,
                   theme.MUTED, scale=1)

        # Action chip — right edge. INSTALL pink-fill / INSTALLED outline-only.
        if self._busy == item["dir"]:
            label = STATE_BUSY
            chip_fill   = theme.MUTED2
            chip_text   = theme.TEXT_BRIGHT
        elif item["installed"]:
            label = STATE_INSTALLED
            chip_fill   = theme.CARD if sel else theme.DOCK_SEL
            chip_text   = theme.PRIMARY
        else:
            label = STATE_INSTALL
            chip_fill   = theme.PRIMARY
            chip_text   = api.WHITE

        cx = SW - ROW_PAD_X - ACT_W
        cy = y + (CARD_H - ACT_H) // 2
        d.rect(cx, cy, ACT_W, ACT_H, chip_fill, fill=True)
        # Outline so the INSTALLED state reads as a "tag" not a button.
        if item["installed"] and self._busy != item["dir"]:
            d.rect(cx, cy,                ACT_W, 1, theme.PRIMARY, fill=True)
            d.rect(cx, cy + ACT_H - 1,    ACT_W, 1, theme.PRIMARY, fill=True)
            d.rect(cx, cy,                1, ACT_H, theme.PRIMARY, fill=True)
            d.rect(cx + ACT_W - 1, cy,    1, ACT_H, theme.PRIMARY, fill=True)
        d.text(label, cx + (ACT_W - len(label) * 8) // 2,
               cy + (ACT_H - 8) // 2, chip_text, scale=1)

    def _icon_for(self, item):
        """Best-effort fetch of the app's optimized icon module — works
        whether the app is installed (in /apps/) or still in the market
        (/apps_market/). Returns (bytes, w, h) or None."""
        icon_file = item.get("icon") or ""
        if not icon_file:
            return None
        stem = icon_file.rsplit(".", 1)[0].replace("-", "_")
        # The icon almost always lives under the global assets/icons —
        # check that first since we already ship those compressed.
        try:
            m = __import__("assets.icons.optimized." + stem,
                           None, None, ["DATA", "W", "H"])
            return (m.DATA, m.W, m.H)
        except (ImportError, AttributeError):
            return None

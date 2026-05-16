"""Store — fetch installable apps from the OreoOS GitHub repo.

Catalogue source: github.com/elixpo/oreo `apps_market/`. Each subdir
of that path that ships a manifest.json + main.py is a candidate.
Listing is cached on flash (/store_cache.json) so the page is usable
offline; press A on a card to install / uninstall, press A on the
top header row (or just open the app cold) to force a refresh.

State machine (drives the page header pill):
    LOADING     refreshing from GitHub right now
    OK          cached listing, fresh-ish
    STALE       cached listing, last refresh > 12h ago
    OFFLINE     cache exists but WiFi is down
    EMPTY       no cache and no network — first install needs WiFi
    ERROR       refresh threw something unexpected

Controls:
  UP / DOWN  walk the list (top row = "Refresh from GitHub")
  A          refresh, install, or uninstall depending on focus
  HOME       back to the launcher
"""

import oreoOS
from oreoOS import api, theme, widgets
from oreoOS import store


SW = api.SCREEN_W
SH = api.SCREEN_H

LIST_TOP_Y    = widgets.HEADER_H + 6
HEADER_CARD_H = 36
CARD_H        = 44
CARD_GAP      = 4
ROW_PAD_X     = 10
ICON_BOX      = 32
ACT_W         = 78
ACT_H         = 18

STALE_AFTER_MS = 12 * 60 * 60 * 1000   # 12 h


class App(oreoOS.App):
    name         = "Store"
    author       = "Circuit-Overtime"
    SHOW_LOADING = True

    def on_enter(self, os_):
        super().on_enter(os_)
        self._os    = os_
        self._sel   = 0     # 0 = refresh header, 1+ = catalogue cards
        self._top   = 0     # first visible CARD index (0..len(items))
        self._busy  = None  # dir name currently mid-install/uninstall
        self._state = "LOADING"
        self._msg   = ""
        self._items = []
        self._dirty = True
        # Surface whatever's in the disk cache immediately so the user
        # has something on screen during the GitHub round-trip.
        self._items = store.list_market()
        self._refresh(initial=True)

    # ── input ──────────────────────────────────────────────────────────
    def on_button_press(self, btn):
        if btn == api.BTN_HOME:
            self._os.quit()
            return
        # Row count = header + every catalogue entry.
        total = 1 + len(self._items)
        if btn == api.BTN_UP:
            self._sel = (self._sel - 1) % total
        elif btn == api.BTN_DOWN:
            self._sel = (self._sel + 1) % total
        elif btn == api.BTN_A:
            self._activate()
        else:
            return
        self._scroll_to_sel()
        self._dirty = True

    def _activate(self):
        if self._sel == 0:
            self._refresh(initial=False)
            return
        idx = self._sel - 1
        if not (0 <= idx < len(self._items)):
            return
        item = self._items[idx]
        name = item["dir"]
        self._busy = name
        self._msg  = ""
        self._dirty = True
        try:
            self.draw(self._os.display); self._os.display.present()
        except Exception:
            pass
        if item["installed"]:
            ok = store.uninstall(name)
            self._msg = "Uninstalled" if ok else "Uninstall failed"
        else:
            ok = store.install(name)
            self._msg = "Installed" if ok else "Install failed"
        # Re-tag installed flags on the in-memory list so the chip
        # flips immediately without another full refresh.
        for e in self._items:
            e["installed"] = store.is_installed(e["dir"])
        self._busy = None

    def _scroll_to_sel(self):
        """Keep the focused row inside the visible window."""
        vis = self._visible_card_count()
        if self._sel == 0:
            self._top = 0
            return
        card_idx = self._sel - 1
        if card_idx < self._top:
            self._top = card_idx
        elif card_idx >= self._top + vis:
            self._top = card_idx - vis + 1

    def _visible_card_count(self):
        avail = SH - LIST_TOP_Y - HEADER_CARD_H - 6 - widgets.HINT_H - 6
        return max(1, avail // (CARD_H + CARD_GAP))

    # ── refresh action ─────────────────────────────────────────────────
    def _refresh(self, initial):
        self._state = "LOADING"
        self._dirty = True
        try:
            self.draw(self._os.display); self._os.display.present()
        except Exception:
            pass
        try:
            self._items = store.refresh(force=not initial)
        except Exception:
            self._items = store.list_market()
            self._state = "ERROR"
            self._msg = "refresh failed"
            self._dirty = True
            return
        self._state = self._classify_state()
        self._dirty = True

    def _classify_state(self):
        age = store.cache_age_ms()
        if not self._items:
            # Check whether WiFi is the blocker so the user gets a
            # useful pill rather than a generic empty state.
            try:
                from oreoWare import wifi
                if not wifi.is_connected():
                    return "OFFLINE"
            except Exception:
                pass
            return "EMPTY"
        if age is None:
            return "OK"
        if age > STALE_AFTER_MS:
            return "STALE"
        return "OK"

    # ── render ─────────────────────────────────────────────────────────
    def draw(self, d):
        if not self._dirty:
            return
        self._dirty = False
        d.clear(theme.BG)
        widgets.draw_header(d, "STORE")
        widgets.draw_hint(d, "A=refresh/install  HOME=back")

        self._draw_header_card(d)
        self._draw_catalogue(d)
        if self._msg:
            d.text(self._msg, ROW_PAD_X, SH - widgets.HINT_H - 12,
                   theme.PRIMARY, scale=1)

    def _draw_header_card(self, d):
        y = LIST_TOP_Y
        sel = (self._sel == 0)
        bg = theme.DOCK_SEL if sel else theme.CARD
        d.rect(6, y, SW - 12, HEADER_CARD_H, bg, fill=True)
        if sel:
            d.rect(6,        y,                    SW - 12, 1, theme.SEL_BORDER, fill=True)
            d.rect(6,        y + HEADER_CARD_H - 1, SW - 12, 1, theme.SEL_BORDER, fill=True)
            d.rect(6,        y,                    1, HEADER_CARD_H, theme.SEL_BORDER, fill=True)
            d.rect(SW - 7,   y,                    1, HEADER_CARD_H, theme.SEL_BORDER, fill=True)
        d.text("Apps from GitHub", ROW_PAD_X, y + 4, theme.PRIMARY, scale=2)
        d.text("A = refresh listing", ROW_PAD_X, y + 22,
               theme.MUTED, scale=1)

        # State pill — right edge.
        pill_text, pill_color = self._state_pill()
        if pill_text:
            pw = len(pill_text) * 8 + 12
            d.rect(SW - pw - 10, y + 8, pw, 18, pill_color, fill=True)
            d.text(pill_text, SW - pw - 10 + 6, y + 13, api.WHITE, scale=1)

    def _state_pill(self):
        return {
            "LOADING": ("LOADING",  theme.MUTED),
            "OK":      ("FRESH",    theme.TEAL),
            "STALE":   ("STALE",    theme.GOLD),
            "OFFLINE": ("OFFLINE",  theme.MUTED),
            "EMPTY":   ("NO WIFI",  theme.PRIMARY),
            "ERROR":   ("ERROR",    theme.PRIMARY),
        }.get(self._state, (None, None))

    def _draw_catalogue(self, d):
        if not self._items:
            y = LIST_TOP_Y + HEADER_CARD_H + 8
            if self._state == "LOADING":
                msg = "fetching catalogue..."
            elif self._state in ("OFFLINE", "EMPTY"):
                msg = "connect WiFi to load the catalogue"
            else:
                msg = "no apps available"
            d.text(msg, (SW - len(msg) * 8) // 2, y + 40,
                   theme.MUTED, scale=1)
            return

        vis = self._visible_card_count()
        list_y0 = LIST_TOP_Y + HEADER_CARD_H + 6
        for vi in range(vis):
            i = self._top + vi
            if i >= len(self._items):
                break
            self._draw_card(d, list_y0 + vi * (CARD_H + CARD_GAP), i)

    def _draw_card(self, d, y, i):
        item = self._items[i]
        sel  = (self._sel == i + 1)
        bg   = theme.DOCK_SEL if sel else theme.CARD
        d.rect(6, y, SW - 12, CARD_H, bg, fill=True)
        if sel:
            d.rect(6,         y,              SW - 12, 1,       theme.SEL_BORDER, fill=True)
            d.rect(6,         y + CARD_H - 1, SW - 12, 1,       theme.SEL_BORDER, fill=True)
            d.rect(6,         y,              1, CARD_H,         theme.SEL_BORDER, fill=True)
            d.rect(SW - 7,    y,              1, CARD_H,         theme.SEL_BORDER, fill=True)

        # Icon. We try the global optimized icons first — the catalogue
        # entry's `icon` field is a filename like `pet_icon.png` which
        # we map to assets.icons.optimized.<stem>.
        icon = self._icon_for(item)
        if icon:
            data, iw, ih = icon
            d.blit(data, ROW_PAD_X, y + (CARD_H - ih) // 2, iw, ih)
        else:
            letter = (item["name"] or "?")[0].upper()
            d.text(letter, ROW_PAD_X + 8, y + 8, theme.PRIMARY, scale=3)

        tx = ROW_PAD_X + ICON_BOX + 10
        d.text(item["name"][:18], tx, y + 6, theme.TEXT_BRIGHT, scale=2)
        author = item.get("author") or ""
        if author:
            d.text(("by " + author)[:24], tx, y + 26, theme.MUTED, scale=1)

        # Action chip
        if self._busy == item["dir"]:
            label, chip_fill, chip_text = "...", theme.MUTED2, theme.TEXT_BRIGHT
        elif item["installed"]:
            label, chip_fill, chip_text = "INSTALLED", \
                                          (theme.CARD if sel else theme.DOCK_SEL), \
                                          theme.PRIMARY
        else:
            label, chip_fill, chip_text = "INSTALL", theme.PRIMARY, api.WHITE

        cx = SW - ROW_PAD_X - ACT_W
        cy = y + (CARD_H - ACT_H) // 2
        d.rect(cx, cy, ACT_W, ACT_H, chip_fill, fill=True)
        if item["installed"] and self._busy != item["dir"]:
            d.rect(cx,             cy,             ACT_W, 1, theme.PRIMARY, fill=True)
            d.rect(cx,             cy + ACT_H - 1, ACT_W, 1, theme.PRIMARY, fill=True)
            d.rect(cx,             cy,             1, ACT_H, theme.PRIMARY, fill=True)
            d.rect(cx + ACT_W - 1, cy,             1, ACT_H, theme.PRIMARY, fill=True)
        d.text(label, cx + (ACT_W - len(label) * 8) // 2,
               cy + (ACT_H - 8) // 2, chip_text, scale=1)

    def _icon_for(self, item):
        """Look up the optimized icon module for an app. The catalogue
        entry's `icon` field is the filename from the app's manifest;
        we strip the extension and reach into assets.icons.optimized.

        Cheap and offline-only — no network hit needed to paint a card
        once the catalogue is cached. If the icon isn't shipped in the
        global icon bundle, the card falls back to a letter glyph."""
        icon_file = item.get("icon") or ""
        if not icon_file:
            return None
        stem = icon_file.rsplit(".", 1)[0].replace("-", "_")
        try:
            m = __import__("assets.icons.optimized." + stem,
                           None, None, ["DATA", "W", "H"])
            return (m.DATA, m.W, m.H)
        except (ImportError, AttributeError):
            return None

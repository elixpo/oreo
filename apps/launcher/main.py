"""Apps — first-class app launcher.

Paginated 4×2 grid of icons with labels, scroll between pages with L/R, jump
within a page with UP/DOWN.

Internally this is the same view that used to live as `_AppMenu` inside
lix_os/launcher.py; promoting it to a real app lets us style it consistently
with the rest of the OS and ship a real icon for the dock.

The hosting `run_app` loop already pipes BTN_HOME into os.quit(), so we
inherit "press HOME to return to the clock" for free.
"""

import lix
from lix import api
from lix_os import theme, widgets

SW = api.SCREEN_W
SH = api.SCREEN_H


class App(lix.App):
    name         = "Apps"
    SHOW_LOADING = False     # icon preload is fast (~30 ms for 18 icons)

    COLS         = 4
    ROWS_PER_PG  = 2
    ICON_SZ      = 56
    GAP_X        = 16
    GAP_Y        = 16
    SEL_PAD      = 4
    LABEL_H      = 12

    def on_enter(self, os):
        self._os = os
        # Discover apps via the launcher module (avoids importing the OS
        # internals here — single source of truth)
        from lix_os.launcher import list_apps
        all_apps = [a for a in list_apps() if a["dir"] != "launcher"]

        # Filter out this app itself
        self._apps  = all_apps
        self._sel   = 0
        self._dirty = True

        # Pre-load every icon as a bytearray so per-frame blits are fast.
        self._icons = {}
        from lix_os import icons as _icons
        for a in self._apps:
            result = _icons.load(a["dir"], a.get("icon"))
            if result:
                # convert to bytearray for fast framebuf blit
                data, w, h = result
                self._icons[a["dir"]] = (bytearray(data), w, h)

    def on_button_press(self, btn):
        n = len(self._apps)
        if not n: return
        cols, rows = self.COLS, self.ROWS_PER_PG
        per_pg = cols * rows
        if btn == api.BTN_LEFT:
            self._sel = (self._sel - 1) % n
        elif btn == api.BTN_RIGHT:
            self._sel = (self._sel + 1) % n
        elif btn == api.BTN_UP:
            self._sel = (self._sel - cols) % n
        elif btn == api.BTN_DOWN:
            self._sel = (self._sel + cols) % n
        elif btn == api.BTN_A:
            self._os.launch(self._apps[self._sel]["dir"])
            return
        else:
            return
        self._dirty = True

    def update(self, dt):
        pass

    def draw(self, d):
        if not self._dirty:
            return
        d.clear(theme.BG)
        # Page indicator
        per_pg = self.COLS * self.ROWS_PER_PG
        n_pg   = max(1, (len(self._apps) + per_pg - 1) // per_pg)
        cur_pg = self._sel // per_pg

        widgets.draw_header(d, "APPS")
        widgets.draw_hint  (d, "arrows=nav  A=launch  HOME=back")

        # Page dots in the header
        dots_x = SW - 12 * n_pg - 8
        for i in range(n_pg):
            color = api.WHITE if i == cur_pg else theme.DOCK_BG
            d.rect(dots_x + i * 12, 10, 8, 6, color, fill=True)

        # Visible slice
        first = cur_pg * per_pg
        last  = min(len(self._apps), first + per_pg)

        cell_w = self.ICON_SZ + self.GAP_X
        cell_h = self.ICON_SZ + self.LABEL_H + self.GAP_Y
        grid_w = self.COLS * self.ICON_SZ + (self.COLS - 1) * self.GAP_X
        grid_h = self.ROWS_PER_PG * (self.ICON_SZ + self.LABEL_H) + \
                 (self.ROWS_PER_PG - 1) * self.GAP_Y
        avail_h = SH - widgets.HEADER_H - widgets.HINT_H
        x0 = (SW - grid_w) // 2
        y0 = widgets.HEADER_H + max(8, (avail_h - grid_h) // 2)

        for slot, app_idx in enumerate(range(first, last)):
            app = self._apps[app_idx]
            col = slot % self.COLS
            row = slot // self.COLS
            tx  = x0 + col * cell_w
            ty  = y0 + row * cell_h
            sel = (app_idx == self._sel)

            if sel:
                d.rect(tx - self.SEL_PAD, ty - self.SEL_PAD,
                       self.ICON_SZ + self.SEL_PAD * 2,
                       self.ICON_SZ + self.SEL_PAD * 2,
                       theme.SEL_BORDER, fill=False)

            icon = self._icons.get(app["dir"])
            if icon:
                idata, iw, ih = icon
                d.blit(idata, tx + (self.ICON_SZ - iw) // 2,
                              ty + (self.ICON_SZ - ih) // 2, iw, ih)
            else:
                letter_c = [theme.PRIMARY, theme.TEAL, theme.GOLD,
                            theme.ORANGE, theme.PURPLE, theme.GREEN]
                lc = letter_c[app_idx % len(letter_c)]
                d.text(app["name"][0].upper(),
                       tx + (self.ICON_SZ - 32) // 2,
                       ty + (self.ICON_SZ - 32) // 2, lc, scale=4)

            label = app["name"][:9]
            d.text(label,
                   tx + (self.ICON_SZ - len(label) * 8) // 2,
                   ty + self.ICON_SZ + 3,
                   theme.PRIMARY if sel else theme.TEXT_BRIGHT)

        self._dirty = False

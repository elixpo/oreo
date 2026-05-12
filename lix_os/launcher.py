"""Elixpo OS — app loader, generic run loop, crash screen, boot entry point.

Apps live in apps/<name>/ with a manifest.json and a main.py that exposes
an App class subclassing lix.App.  The OS launcher owns the top-level loop;
individual screens (splash, home, app-menu) live in separate modules.
"""

import gc
import json
import os as _os
import time

from lix import api

VERSION      = "v0.1"
FRAME_MIN_MS = 16        # ≈60 fps cap

_APPS_CANDIDATES = ("/apps", "/remote/apps", "apps")


def _find_apps_dir():
    for d in _APPS_CANDIDATES:
        try:
            _os.stat(d)
            return d
        except OSError:
            continue
    return None


APPS_DIR = _find_apps_dir() or "/apps"


# ── app discovery ─────────────────────────────────────────────────────────────

def list_apps():
    """Return [{'dir':..., 'name':..., 'type':...}, ...]  sorted by dir name."""
    apps = []
    try:
        entries = _os.listdir(APPS_DIR)
    except OSError:
        return apps
    for entry in sorted(entries):
        try:
            with open("%s/%s/manifest.json" % (APPS_DIR, entry)) as f:
                manifest = json.loads(f.read())
            apps.append({
                "dir":   entry,
                "name":  manifest.get("name", entry),
                "type":  manifest.get("type", "app"),
                "color": manifest.get("color", None),
                "icon":  manifest.get("icon", None),
            })
        except (OSError, ValueError):
            continue
    return [a for a in apps if a["type"] == "app"]


def load_app(app_dir):
    module_path = "apps.%s.main" % app_dir
    mod = __import__(module_path, None, None, ["App"])
    return mod.App()


# ── generic app run loop ──────────────────────────────────────────────────────

def run_app(os_obj, app):
    os_obj._quit_requested = False
    os_obj._launch_request = None

    app.on_enter(os_obj)
    last = time.ticks_ms()
    try:
        while not os_obj._quit_requested:
            now = time.ticks_ms()
            dt  = time.ticks_diff(now, last) / 1000.0
            last = now

            os_obj.buttons.update()
            for b in api.BUTTONS:
                if os_obj.buttons.just_pressed(b):
                    if b == api.BTN_HOME:
                        os_obj.quit()
                    else:
                        app.on_button_press(b)
                if os_obj.buttons.just_released(b):
                    app.on_button_release(b)

            app.update(dt)
            app.draw(os_obj.display)
            os_obj.display.present()

            elapsed = time.ticks_diff(time.ticks_ms(), now)
            if elapsed < FRAME_MIN_MS:
                time.sleep_ms(FRAME_MIN_MS - elapsed)
    finally:
        app.on_exit()
        gc.collect()


# ── crash screen ──────────────────────────────────────────────────────────────

def show_crash(os_obj, name, err):
    d = os_obj.display
    d.clear(api.rgb(60, 0, 0))
    d.rect(0, 0, api.SCREEN_W, 30, api.rgb(180, 30, 30), fill=True)
    d.text("APP CRASHED", 50, 11, api.WHITE, scale=2)
    d.text(name[:14], 20, 50, api.rgb(255, 220, 100), scale=2)
    msg = str(err)
    for i, start in enumerate(range(0, min(len(msg), 150), 28)):
        d.text(msg[start:start + 28], 8, 90 + i * 14, api.WHITE)
    d.text("any key to continue", 16, api.SCREEN_H - 22, api.rgb(160, 160, 160))
    d.present()
    while True:
        os_obj.buttons.update()
        if any(os_obj.buttons.just_pressed(b) for b in api.BUTTONS):
            return
        time.sleep_ms(20)


# ── app menu (icon grid) — 320×240 landscape ──────────────────────────────────

class _AppMenu:
    """4-column icon grid. Icons only — no tile boxes. Faint border on select.
    All 4 nav directions wrap around circularly."""

    COLS    = 4
    ICON_SZ = 48    # display size for each icon (px)
    GAP_X   = 20
    GAP_Y   = 18
    HEADER  = 28
    SEL_PAD = 4     # padding around selected icon for the border

    def __init__(self, apps):
        self.apps   = apps
        self.sel    = 0
        self._dirty = True
        self._os    = None

    def on_enter(self, os_obj):
        self._os    = os_obj
        self._dirty = True

    def on_exit(self):
        pass

    def _move(self, delta_col, delta_row):
        n    = len(self.apps)
        if not n: return
        cols = self.COLS
        rows = (n + cols - 1) // cols
        col  = self.sel % cols
        row  = self.sel // cols

        new_col = (col + delta_col) % cols
        new_row = (row + delta_row) % rows
        new_sel = new_row * cols + new_col
        # if last row is partial, clamp to last item
        self.sel = min(new_sel, n - 1)
        self._dirty = True

    def on_button_press(self, btn):
        n = len(self.apps)
        if not n: return
        if   btn == api.BTN_LEFT:  self._move(-1,  0)
        elif btn == api.BTN_RIGHT: self._move( 1,  0)
        elif btn == api.BTN_UP:    self._move( 0, -1)
        elif btn == api.BTN_DOWN:  self._move( 0,  1)
        elif btn == api.BTN_A:
            self._os.launch(self.apps[self.sel]["dir"])

    def on_button_release(self, btn):
        pass

    def update(self, dt):
        pass

    def draw(self, d):
        from lix_os import theme
        if not self._dirty:
            return

        SW = api.SCREEN_W
        SH = api.SCREEN_H

        d.clear(theme.BG)

        # ── header ────────────────────────────────────────────────────────
        d.rect(0, 0, SW, self.HEADER, theme.STATUS_BG, fill=True)
        title = "APPS"
        tx = (SW - len(title) * 8 * 2) // 2
        d.text(title, tx, (self.HEADER - 16) // 2, api.WHITE, scale=2)

        if not self.apps:
            d.text("no apps found", 40, SH // 2, theme.MUTED, scale=2)
            self._dirty = False
            return

        # ── icon grid (centred) ───────────────────────────────────────────
        cols    = self.COLS
        n       = len(self.apps)
        rows    = (n + cols - 1) // cols
        cell_w  = self.ICON_SZ + self.GAP_X
        cell_h  = self.ICON_SZ + self.GAP_Y

        grid_w  = cols * self.ICON_SZ + (cols - 1) * self.GAP_X
        grid_h  = rows * self.ICON_SZ + (rows - 1) * self.GAP_Y
        avail_h = SH - self.HEADER
        x0      = (SW - grid_w) // 2
        y0      = self.HEADER + (avail_h - grid_h) // 2

        for i, app in enumerate(self.apps):
            col = i % cols
            row = i // cols
            tx  = x0 + col * cell_w
            ty  = y0 + row * cell_h
            sel = (i == self.sel)

            # No background tile — icon stands alone
            if sel:
                d.rect(tx - self.SEL_PAD, ty - self.SEL_PAD,
                       self.ICON_SZ + self.SEL_PAD * 2,
                       self.ICON_SZ + self.SEL_PAD * 2,
                       theme.SEL_BORDER, fill=False)

            # Load icon from asset pipeline
            icon_data = None
            if app.get("icon"):
                from lix_os import icons as _icons
                result = _icons.load(app["dir"], app["icon"])
                if result:
                    icon_data = result

            if icon_data:
                idata, iw, ih = icon_data
                bx = tx + (self.ICON_SZ - iw) // 2
                by = ty + (self.ICON_SZ - ih) // 2
                d.blit(idata, bx, by, iw, ih)
            else:
                # Letter fallback (only until icon is generated & optimised)
                letter_c = [theme.PRIMARY, theme.TEAL, theme.GOLD,
                             theme.ORANGE, theme.PURPLE, theme.GREEN]
                lc = letter_c[i % len(letter_c)]
                d.text(app["name"][0].upper(), tx + 8, ty + 8, lc, scale=4)

        self._dirty = False


# ── boot entry point ─────────────────────────────────────────────────────────

def boot():
    from lix_hw.os import OS
    from lix_os.splash import show_splash
    from lix_os.home   import Home

    os_obj = OS()
    show_splash(os_obj)

    while True:
        apps = list_apps()
        home = Home(apps)
        run_app(os_obj, home)

        target = os_obj._launch_request

        if target == "__appmenu__":
            menu = _AppMenu(apps)
            run_app(os_obj, menu)
            target = os_obj._launch_request

        if target and target not in (None, "__appmenu__"):
            try:
                app = load_app(target)
                run_app(os_obj, app)
            except Exception as e:
                show_crash(os_obj, target, e)


if __name__ == "__main__":
    boot()

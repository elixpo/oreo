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
# Target ~33 fps (30 ms cap). At 40 MHz SPI a full framebuf push is 30.7 ms,
# plus ~3 ms render → total ≈ 34 ms. The sleep rarely actually fires during
# gameplay; it caps idle screens so they don't hammer the panel >50 fps.
FRAME_MIN_MS = 30

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


# ── loading transition (used for slow apps) ──────────────────────────────────
# A flag-on-the-App-class opts in:    class App(lix.App): SHOW_LOADING = True
# Cost: ~210 ms slide-in animation BEFORE app.on_enter — the heavy load then
# runs while the loading panel is the only thing on screen.

def _show_loading(display, label):
    """Slide a primary-coloured panel down from the top, covering the screen."""
    from lix_os import theme
    from lix import font
    SW = api.SCREEN_W
    SH = api.SCREEN_H
    steps = 7
    for i in range(steps + 1):
        progress = i / steps
        panel_h  = int(progress * SH)
        # Pink panel from y=0 to y=panel_h
        display.rect(0, 0, SW, panel_h, theme.PRIMARY, fill=True)
        # Below the panel: solid cream (leftover from previous screen is fine
        # since it'll be overwritten — but cream looks tidier on partial slide).
        if panel_h < SH:
            display.rect(0, panel_h, SW, SH - panel_h, theme.BG, fill=True)
        if panel_h > 50:
            cy = panel_h // 2
            font.text_center(display, "LOADING", SW // 2, cy - 14, api.WHITE, scale=2)
            font.text_center(display, label.upper(), SW // 2, cy + 4,  api.WHITE)
        display.present()
        time.sleep_ms(30)


# ── generic app run loop ──────────────────────────────────────────────────────

def run_app(os_obj, app):
    os_obj._quit_requested = False
    os_obj._launch_request = None

    # Optional loading transition for heavy apps. The panel covers the screen
    # while on_enter does its work; the very next frame fully overwrites it.
    if getattr(app, "SHOW_LOADING", False):
        label = getattr(app, "name", app.__class__.__name__)
        _show_loading(os_obj.display, label)

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
    """Grid of app icons with labels underneath.

    Nav:
      LEFT/RIGHT  → linear traversal across rows (wraps at ends)
      UP/DOWN     → row navigation (wraps top↔bottom, clamps on partial row)
      A           → launch
    """

    COLS    = 4
    ICON_SZ = 56          # bigger icons
    LABEL_H = 12          # space for one line of 8x8 text + 4px gap
    GAP_X   = 16
    GAP_Y   = 12
    HEADER  = 26
    SEL_PAD = 4

    def __init__(self, apps):
        self.apps   = apps
        self.sel    = 0
        self._dirty = True
        self._os    = None
        # Preload all icons up-front so first frame draws fast
        self._icons = {}
        if apps:
            from lix_os import icons as _icons
            for a in apps:
                key = a["dir"]
                result = _icons.load(key, a.get("icon"))
                if result:
                    self._icons[key] = result

    def on_enter(self, os_obj):
        self._os    = os_obj
        self._dirty = True

    def on_exit(self):
        pass

    def on_button_press(self, btn):
        n = len(self.apps)
        if not n: return
        cols = self.COLS

        if btn == api.BTN_LEFT:
            self.sel = (self.sel - 1) % n
        elif btn == api.BTN_RIGHT:
            self.sel = (self.sel + 1) % n
        elif btn == api.BTN_UP:
            new = self.sel - cols
            if new < 0:
                # wrap to corresponding column in bottom row
                col = self.sel % cols
                rows = (n + cols - 1) // cols
                new = (rows - 1) * cols + col
                if new >= n:
                    new -= cols
            self.sel = new
        elif btn == api.BTN_DOWN:
            new = self.sel + cols
            if new >= n:
                # wrap to corresponding column in top row
                new = self.sel % cols
            self.sel = new
        elif btn == api.BTN_A:
            self._os.launch(self.apps[self.sel]["dir"])
            return
        else:
            return
        self._dirty = True

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

        # ── icon grid (centred horizontally, snug under header) ──────────
        cols   = self.COLS
        n      = len(self.apps)
        rows   = (n + cols - 1) // cols
        cell_w = self.ICON_SZ + self.GAP_X
        cell_h = self.ICON_SZ + self.LABEL_H + self.GAP_Y

        grid_w = cols * self.ICON_SZ + (cols - 1) * self.GAP_X
        grid_h = rows * (self.ICON_SZ + self.LABEL_H) + (rows - 1) * self.GAP_Y
        avail_h = SH - self.HEADER
        x0     = (SW - grid_w) // 2
        y0     = self.HEADER + max(6, (avail_h - grid_h) // 2)

        for i, app in enumerate(self.apps):
            col = i % cols
            row = i // cols
            tx  = x0 + col * cell_w
            ty  = y0 + row * cell_h
            sel = (i == self.sel)

            if sel:
                d.rect(tx - self.SEL_PAD, ty - self.SEL_PAD,
                       self.ICON_SZ + self.SEL_PAD * 2,
                       self.ICON_SZ + self.SEL_PAD * 2,
                       theme.SEL_BORDER, fill=False)

            icon = self._icons.get(app["dir"])
            if icon:
                idata, iw, ih = icon
                bx = tx + (self.ICON_SZ - iw) // 2
                by = ty + (self.ICON_SZ - ih) // 2
                d.blit(idata, bx, by, iw, ih)
            else:
                letter_c = [theme.PRIMARY, theme.TEAL, theme.GOLD,
                            theme.ORANGE, theme.PURPLE, theme.GREEN]
                lc = letter_c[i % len(letter_c)]
                d.text(app["name"][0].upper(),
                       tx + (self.ICON_SZ - 32) // 2,
                       ty + (self.ICON_SZ - 32) // 2, lc, scale=4)

            # ── label under icon (small font, dark text) ─────────────────
            label = app["name"][:8]   # truncate to fit one cell
            lx = tx + (self.ICON_SZ - len(label) * 8) // 2
            ly = ty + self.ICON_SZ + 3
            text_c = theme.PRIMARY if sel else theme.TEXT_BRIGHT
            d.text(label, lx, ly, text_c)

        self._dirty = False


# ── boot entry point ─────────────────────────────────────────────────────────

def boot():
    from lix_hw.os import OS
    from lix_os.splash import show_splash
    from lix_os.home   import Home

   
    try:
        gc.threshold(8_000)        # auto-GC after every 8 KB of growth
    except AttributeError:
        # CPython simulator has no gc.threshold — ignore.
        pass

    os_obj = OS()
    show_splash(os_obj)

    # Start WiFi and BT after splash (non-blocking for BT, background for WiFi)
    try:
        from lix_hw import wifi, bt
        wifi.connect_from_config()
        bt.init_from_config()
    except Exception:
        pass

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

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


# ── app menu (icon grid) ──────────────────────────────────────────────────────

_ICON_PALETTE = [
    api.rgb(255, 80, 200),
    api.rgb(0, 200, 255),
    api.rgb(255, 160, 0),
    api.rgb(120, 220, 80),
    api.rgb(200, 80, 255),
    api.rgb(255, 120, 60),
    api.rgb(60, 200, 200),
    api.rgb(220, 220, 60),
]


class _AppMenu:
    """Scrollable app selector with coloured icon tiles."""

    COLS    = 2
    TILE_W  = 100
    TILE_H  = 80
    GAP     = 8
    HEADER  = 30

    def __init__(self, apps):
        self.apps    = apps
        self.sel     = 0
        self._dirty  = True
        self._os     = None
        self._scroll = 0   # pixel scroll offset (future: smooth scroll)

    # --- lifecycle -----------------------------------------------------------

    def on_enter(self, os_obj):
        self._os    = os_obj
        self._dirty = True

    def on_exit(self):
        pass

    def on_button_press(self, btn):
        n = len(self.apps)
        if not n:
            return
        if btn == api.BTN_LEFT and self.sel % self.COLS > 0:
            self.sel -= 1;  self._dirty = True
        elif btn == api.BTN_RIGHT and self.sel % self.COLS < self.COLS - 1 and self.sel + 1 < n:
            self.sel += 1;  self._dirty = True
        elif btn == api.BTN_UP and self.sel >= self.COLS:
            self.sel -= self.COLS;  self._dirty = True
        elif btn == api.BTN_DOWN and self.sel + self.COLS < n:
            self.sel += self.COLS;  self._dirty = True
        elif btn == api.BTN_A:
            self._os.launch(self.apps[self.sel]["dir"])

    def on_button_release(self, btn):
        pass

    def update(self, dt):
        pass

    def draw(self, d):
        if not self._dirty:
            return

        BG  = api.rgb(8, 8, 20)
        d.clear(BG)

        # header
        d.rect(0, 0, api.SCREEN_W, self.HEADER, api.rgb(0, 180, 160), fill=True)
        d.text("APPS", 8, 9, api.BLACK, scale=2)
        d.text(VERSION, api.SCREEN_W - 44, 11, api.BLACK)

        if not self.apps:
            d.text("no apps found", 20, 160, api.WHITE, scale=2)
            self._dirty = False
            return

        # icon grid
        x0 = (api.SCREEN_W - (self.COLS * self.TILE_W + (self.COLS - 1) * self.GAP)) // 2

        for i, app in enumerate(self.apps):
            col = i % self.COLS
            row = i // self.COLS
            tx  = x0 + col * (self.TILE_W + self.GAP)
            ty  = self.HEADER + self.GAP + row * (self.TILE_H + self.GAP)

            ic  = _ICON_PALETTE[i % len(_ICON_PALETTE)]
            sel = (i == self.sel)

            tile_bg = api.rgb(25, 25, 45) if not sel else api.rgb(0, 50, 45)
            d.rect(tx, ty, self.TILE_W, self.TILE_H, tile_bg, fill=True)
            border_c = ic if sel else api.rgb(40, 40, 70)
            d.rect(tx, ty, self.TILE_W, self.TILE_H, border_c, fill=False)

            # Icon: try PNG, fall back to letter tile
            icon_data = None
            if app.get("icon"):
                from lix_os import icons as _icons
                result = _icons.load(app["dir"], app["icon"])
                if result:
                    icon_data = result
            if icon_data:
                idata, iw, ih = icon_data
                ix = tx + (self.TILE_W - iw) // 2
                iy = ty + 8
                d.blit(idata, ix, iy, iw, ih)
            else:
                d.rect(tx + 30, ty + 8, 40, 36, ic, fill=True)
                d.text(app["name"][0].upper(), tx + 38, ty + 13, api.BLACK, scale=4)

            # Selection glow on bottom border
            if sel:
                d.rect(tx + 4, ty + self.TILE_H - 3, self.TILE_W - 8, 3, ic, fill=True)

        # footer hint
        foot_y = api.SCREEN_H - 18
        d.rect(0, foot_y, api.SCREEN_W, 18, api.rgb(10, 10, 20), fill=True)
        d.text("arrows  nav     A  open", 8, foot_y + 4, api.rgb(100, 100, 130))

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

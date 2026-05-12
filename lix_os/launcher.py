"""Lix OS — boot splash, app menu, generic app loop.

Apps live in /apps/<name>/ with a manifest.json declaring metadata and a
main.py exposing an `App` class that subclasses `lix.App`.
"""

import gc
import json
import os as _os
import time

from lix import api
from lix_hw.os import OS


VERSION       = "v0.1"
APPS_DIR      = "/apps"
SPLASH_MS     = 1500
FRAME_MIN_MS  = 16   # cap frame rate ~60fps even if hardware can do more


# ----------------------------- splash --------------------------------------

def show_splash(d):
    d.clear(api.rgb(12, 12, 24))
    # logo
    d.text("LIX", 65, 110, api.rgb(255, 200, 0), scale=6)
    d.text("OS",  95, 175, api.WHITE,            scale=4)
    # version
    d.text(VERSION, 100, 235, api.rgb(120, 120, 150), scale=1)
    # subtle accent
    d.rect(40,  100, 160, 2, api.rgb(255, 100, 30), fill=True)
    d.rect(40,  225, 160, 2, api.rgb(255, 100, 30), fill=True)
    d.present()
    time.sleep_ms(SPLASH_MS)


# ----------------------------- app discovery -------------------------------

def list_apps():
    """Return list of dicts: [{'dir': 'hello', 'name': 'Hello', ...}, ...]."""
    apps = []
    try:
        entries = _os.listdir(APPS_DIR)
    except OSError:
        return apps
    for entry in sorted(entries):
        try:
            with open(f"{APPS_DIR}/{entry}/manifest.json") as f:
                manifest = json.loads(f.read())
            apps.append({
                "dir":  entry,
                "name": manifest.get("name", entry),
                "type": manifest.get("type", "app"),
            })
        except (OSError, ValueError):
            continue
    return [a for a in apps if a["type"] == "app"]


def load_app(app_dir):
    module_path = f"apps.{app_dir}.main"
    mod = __import__(module_path, None, None, ["App"])
    return mod.App()


# ----------------------------- generic app loop ----------------------------

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

            # 1. inputs
            os_obj.buttons.update()
            for b in api.BUTTONS:
                if os_obj.buttons.just_pressed(b):
                    if b == api.BTN_HOME:
                        os_obj.quit()       # universal: HOME = back to launcher
                    else:
                        app.on_button_press(b)
                if os_obj.buttons.just_released(b):
                    app.on_button_release(b)

            # 2. tick + render
            app.update(dt)
            app.draw(os_obj.display)
            os_obj.display.present()

            # 3. frame pacing
            elapsed = time.ticks_diff(time.ticks_ms(), now)
            if elapsed < FRAME_MIN_MS:
                time.sleep_ms(FRAME_MIN_MS - elapsed)
    finally:
        app.on_exit()
        gc.collect()


# ----------------------------- crash screen --------------------------------

def show_crash(os_obj, name, err):
    d = os_obj.display
    d.clear(api.rgb(60, 0, 0))
    d.rect(0, 0, api.SCREEN_W, 30, api.rgb(180, 30, 30), fill=True)
    d.text("APP CRASHED", 50, 11, api.WHITE, scale=2)
    d.text(name, 20, 70, api.rgb(255, 220, 100), scale=2)
    # error message wrapped
    msg = str(err)
    for i, line_start in enumerate(range(0, min(len(msg), 120), 30)):
        d.text(msg[line_start:line_start + 30], 10, 110 + i * 12, api.WHITE)
    d.text("press any key", 60, api.SCREEN_H - 30, api.rgb(200, 200, 200), scale=2)
    d.present()
    # block until any press
    while True:
        os_obj.buttons.update()
        if any(os_obj.buttons.just_pressed(b) for b in api.BUTTONS):
            return
        time.sleep_ms(20)


# ----------------------------- menu (internal app) -------------------------

class _Menu:
    """The launcher's app picker. Same lifecycle shape as a regular App so we
    can drive it through run_app() without special-casing."""

    def __init__(self, apps):
        self.apps = apps
        self.sel  = 0
        self._dirty = True
        self._os = None

    def on_enter(self, os_obj):
        self._os = os_obj
        self._dirty = True

    def on_exit(self):
        pass

    def on_button_press(self, btn):
        if not self.apps:
            return
        if   btn == api.BTN_UP   and self.sel > 0:
            self.sel -= 1
            self._dirty = True
        elif btn == api.BTN_DOWN and self.sel < len(self.apps) - 1:
            self.sel += 1
            self._dirty = True
        elif btn == api.BTN_A:
            self._os.launch(self.apps[self.sel]["dir"])

    def on_button_release(self, btn):
        pass

    def update(self, dt):
        pass

    def draw(self, d):
        if not self._dirty:
            return
        d.clear(api.rgb(12, 12, 24))
        # header
        d.rect(0, 0, api.SCREEN_W, 30, api.rgb(255, 100, 30), fill=True)
        d.text("LIX OS", 8, 11, api.BLACK, scale=2)
        d.text(VERSION, api.SCREEN_W - 50, 11, api.BLACK)

        if not self.apps:
            d.text("no apps in", 60, 140, api.WHITE, scale=2)
            d.text(APPS_DIR,      80, 170, api.YELLOW, scale=2)
        else:
            y0 = 50
            for i, app in enumerate(self.apps):
                selected = (i == self.sel)
                bg = api.rgb(80, 80, 160) if selected else api.rgb(30, 30, 40)
                tx = api.WHITE            if selected else api.rgb(180, 180, 200)
                y = y0 + i * 32
                d.rect(10, y, api.SCREEN_W - 20, 28, bg, fill=True)
                if selected:
                    d.text(">", 14, y + 7, api.WHITE, scale=2)
                d.text(app["name"], 36, y + 7, tx, scale=2)

        # footer hint
        d.rect(0, api.SCREEN_H - 20, api.SCREEN_W, 20, api.rgb(10, 10, 20), fill=True)
        d.text("UP/DN  pick     A  open", 20, api.SCREEN_H - 14, api.rgb(140, 140, 160))

        self._dirty = False


# ----------------------------- boot ----------------------------------------

def boot():
    os_obj = OS()
    show_splash(os_obj.display)

    while True:
        apps = list_apps()
        menu = _Menu(apps)
        run_app(os_obj, menu)

        target = os_obj._launch_request
        if target:
            try:
                app = load_app(target)
                run_app(os_obj, app)
            except Exception as e:
                show_crash(os_obj, target, e)


if __name__ == "__main__":
    boot()

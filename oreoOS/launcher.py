"""Oreo OS — app loader, generic run loop, crash screen, boot entry point.

Apps live in apps/<name>/ with a manifest.json and a main.py that exposes
an App class subclassing oreoOS.App.  The OS launcher owns the top-level loop;
individual screens (splash, home, app-menu) live in separate modules.
"""

import gc
import json
import os as _os
import time

from oreoOS import api

VERSION      = "v1.2.19"
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
                "dir":    entry,
                "name":   manifest.get("name", entry),
                "type":   manifest.get("type", "app"),
                "color":  manifest.get("color", None),
                "icon":   manifest.get("icon", None),
                "author": manifest.get("author", None),
            })
        except (OSError, ValueError):
            continue
    return [a for a in apps if a["type"] == "app"]


def load_app(app_dir):
    module_path = "apps.%s.main" % app_dir
    mod = __import__(module_path, None, None, ["App"])
    app = mod.App()
    # Pull the `author` field off the manifest and stamp it onto the app
    # instance so `_show_loading()` can render "By @author" without each
    # app needing to declare the attribute on the class.
    try:
        with open("%s/%s/manifest.json" % (APPS_DIR, app_dir)) as f:
            manifest = json.loads(f.read())
        if manifest.get("author"):
            app.author = manifest["author"]
    except (OSError, ValueError):
        pass
    return app


# ── loading transition (used for slow apps) ──────────────────────────────────
# A flag-on-the-App-class opts in:    class App(oreoOS.App): SHOW_LOADING = True
# Cost: ~210 ms slide-in animation BEFORE app.on_enter — the heavy load then
# runs while the loading panel is the only thing on screen.

def _show_loading(os_obj, label, author=None):
    """Slide a primary-coloured panel down from the top, covering the screen.

    Polls HOME each frame so the user can abort a slow app launch without
    waiting for the on_enter to finish — returns True when interrupted.
    """
    from oreoOS import theme
    display = os_obj.display
    buttons = os_obj.buttons
    SW = api.SCREEN_W
    SH = api.SCREEN_H
    label  = (label  or "")[:16].upper()
    byline = ("By @" + author[:24]) if author else ""

    steps      = 12          # more keyframes = smoother slide
    frame_ms   = 33          # ≈ 30 fps
    label_lbl  = "LOADING"
    label_x_l  = (SW - len(label_lbl) * 16) // 2
    label_x_n  = (SW - len(label)     *  8) // 2
    byline_x   = (SW - len(byline)    *  8) // 2
    hint       = "HOME to cancel"
    hint_x     = (SW - len(hint) * 8) // 2

    for i in range(steps + 1):
        # HOME interrupt — the only escape hatch while the slide plays,
        # since the app's on_enter blocks the main loop once we exit.
        buttons.update()
        if buttons.just_pressed(api.BTN_HOME):
            return True

        t        = i / steps
        eased    = 1.0 - (1.0 - t) ** 3
        panel_h  = int(eased * SH)

        display.rect(0, 0, SW, panel_h, theme.PRIMARY, fill=True)
        if panel_h < SH:
            display.rect(0, panel_h, SW, SH - panel_h, theme.BG, fill=True)

        if panel_h > 60:
            cy = panel_h // 2
            display.text(label_lbl, label_x_l, cy - 16, api.WHITE, scale=2)
            display.text(label,     label_x_n, cy +  6, api.WHITE)
            if byline and panel_h > 100:
                display.text(byline, byline_x, cy + 24, theme.GOLD)
            if panel_h > 140:
                display.text(hint, hint_x, panel_h - 22, api.WHITE)

        display.present()
        time.sleep_ms(frame_ms)
    return False


# ── generic app run loop ──────────────────────────────────────────────────────

def run_app(os_obj, app):
    os_obj._quit_requested = False
    os_obj._launch_request = None

    # Optional loading transition for heavy apps. The panel covers the screen
    # while on_enter does its work; the very next frame fully overwrites it.
    if getattr(app, "SHOW_LOADING", False):
        label  = getattr(app, "name",   app.__class__.__name__)
        author = getattr(app, "author", None)
        _show_loading(os_obj.display, label, author)

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
                        handled = False
                        hook = getattr(app, "on_home_press", None)
                        if hook is not None:
                            try:
                                handled = bool(hook())
                            except Exception:
                                handled = False
                        if not handled:
                            # Default: HOME → apps drawer (not the clock screen).
                            # Skip the redirect when we ARE in a drawer/home — quit
                            # then so boot()'s outer loop reaches the home screen.
                            app_name = getattr(app, "name", "")
                            if app_name in ("Apps", "home"):
                                os_obj.quit()
                            else:
                                os_obj.launch("__appmenu__")
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
    """Centred, themed crash screen — Pixelify Sans title + app name,
    framebuf body text. Press any button to dismiss."""
    d  = os_obj.display
    SW = api.SCREEN_W
    SH = api.SCREEN_H

    BG     = api.rgb( 40,   8,  16)
    HDR    = api.rgb(255,  93, 104)
    ACCENT = api.rgb(255, 230,  80)
    TEXT   = api.rgb(245, 230, 220)
    DIM    = api.rgb(180, 150, 150)

    d.clear(BG)

    # Header bar
    HDR_H = 30
    d.rect(0, 0, SW, HDR_H,    HDR,    fill=True)
    d.rect(0, HDR_H, SW, 1,    ACCENT, fill=True)

    # Pixelify display font for the app name; fall back to framebuf if missing.
    try:
        from oreoOS import pixelfont
        title_font = pixelfont.load("pixelify_24")
    except (ImportError, AttributeError):
        title_font = None

    # ── title "APP CRASHED" centred inside the header (small) ────────────
    short_title = "APP CRASHED"
    tw = len(short_title) * 16
    d.text(short_title, (SW - tw) // 2, (HDR_H - 16) // 2, api.WHITE, scale=2)

    # ── big Pixelify app name below the header ──────────────────────────
    nm = (name or "?")[:14]
    name_y = HDR_H + 14
    if title_font:
        nw = title_font.measure(nm)
        title_font.text(d, nm, (SW - nw) // 2, name_y, ACCENT)
        name_h = title_font.h
    else:
        nw = len(nm) * 16
        d.text(nm, (SW - nw) // 2, name_y, ACCENT, scale=2)
        name_h = 16

    # ── error message panel ─────────────────────────────────────────────
    panel_y = name_y + name_h + 12
    panel_h = SH - panel_y - 26          # leave room for footer hint
    d.rect(8, panel_y - 4, SW - 16, panel_h + 8, api.rgb(56, 16, 24), fill=True)
    d.rect(8, panel_y - 4, SW - 16, 1, HDR, fill=True)

    msg       = str(err)
    max_chars = (SW - 32) // 8
    lines     = _wrap_text(msg, max_chars)
    max_lns   = panel_h // 12
    lines     = lines[:max_lns]
    block_h   = len(lines) * 12
    text_y    = panel_y + max(0, (panel_h - block_h) // 2)
    for i, line in enumerate(lines):
        lw = len(line) * 8
        d.text(line, (SW - lw) // 2, text_y + i * 12, TEXT)

    # ── centred footer hint ──────────────────────────────────────────────
    hint = "press any button to continue"
    hw   = len(hint) * 8
    d.text(hint, (SW - hw) // 2, SH - 18, DIM)

    d.present()

    # Wait for any keypress
    while True:
        os_obj.buttons.update()
        if any(os_obj.buttons.just_pressed(b) for b in api.BUTTONS):
            return
        time.sleep_ms(20)


def _wrap_text(text, max_chars):
    """Greedy word-wrap to ≤ max_chars per line; hard-breaks oversized words."""
    if not text:
        return [""]
    out = []
    cur = ""
    for w in text.split():
        if not cur:
            if len(w) > max_chars:
                while len(w) > max_chars:
                    out.append(w[:max_chars])
                    w = w[max_chars:]
                cur = w
            else:
                cur = w
        else:
            candidate = cur + " " + w
            if len(candidate) <= max_chars:
                cur = candidate
            else:
                out.append(cur)
                cur = w
    if cur:
        out.append(cur)
    return out


# ── boot entry point ─────────────────────────────────────────────────────────

def boot():
    from oreoWare.os import OS
    from oreoOS.splash import show_splash
    from oreoOS.home   import Home

    # gc.threshold() was set aggressively for LDO smoothing but caused
    # frequent GC pauses that murdered fps. Leave it at the MicroPython
    # default — manual gc.collect() runs at app exit in run_app's finally.

    os_obj = OS()
    show_splash(os_obj)

    # Start WiFi and BT after splash (non-blocking for BT, background for WiFi)
    try:
        from oreoWare import wifi, bt
        wifi.connect_from_config()
        bt.init_from_config()
        # Sync the system clock from an NTP server once WiFi is up. The RTC
        # then drives the home-screen clock. ~2 s blocking, only at boot.
        if wifi.is_connected():
            try:
                import ntptime, machine, time as _t
                ntptime.host = "pool.ntp.org"
                ntptime.settime()
                # ntptime always sets the RTC to UTC. Shift by the user's
                # TIMEZONE_OFFSET (hours) so localtime() reads correctly.
                try:
                    from secrets import TIMEZONE_OFFSET as _TZ
                    if _TZ:
                        shifted = _t.localtime(_t.time() + int(_TZ * 3600))
                        machine.RTC().datetime(
                            (shifted[0], shifted[1], shifted[2], shifted[6] + 1,
                             shifted[3], shifted[4], shifted[5], 0))
                except Exception:
                    pass
            except Exception:
                pass
    except Exception:
        pass

    while True:
        apps = list_apps()
        home = Home(apps)
        run_app(os_obj, home)

        target = os_obj._launch_request

        # Home's APPS dock sends "__appmenu__" — route it to the
        # first-class apps/launcher/ implementation.
        if target == "__appmenu__":
            target = "launcher"

        # If the user picked the launcher, run it then CHAIN into whichever
        # app it selected. `run_app` clears _launch_request on entry, so we
        # have to re-read it after the launcher exits — otherwise pressing A
        # on a tile would drop us back to home instead of launching the app.
        if target == "launcher":
            try:
                app = load_app("launcher")
                run_app(os_obj, app)
            except Exception as e:
                show_crash(os_obj, "launcher", e)
            target = os_obj._launch_request   # ← the launcher's selection

        if target and target not in (None, "launcher", "__appmenu__"):
            try:
                app = load_app(target)
                run_app(os_obj, app)
            except Exception as e:
                show_crash(os_obj, target, e)


if __name__ == "__main__":
    boot()

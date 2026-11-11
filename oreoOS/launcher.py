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

from oreoOS.config import VERSION   # single source of truth; deploy bumps PATCH
# Target ~33 fps (30 ms cap). At 40 MHz SPI a full framebuf push is 30.7 ms,
# plus ~3 ms render → total ≈ 34 ms. The sleep rarely actually fires during
# gameplay; it caps idle screens so they don't hammer the panel >50 fps.
FRAME_MIN_MS = 30
LOADING_SLIDE_MS = 240      # app-loading panel slide-in

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


def _invalidate(app):
    """Ask an app for a full repaint after an overlay covered it."""
    try:
        hook = getattr(app, "invalidate", None)
        if hook is not None:
            hook()
        else:
            app._dirty = True
    except Exception:
        pass


# ── loading transition (used for slow apps) ──────────────────────────────────
# A flag-on-the-App-class opts in:    class App(oreoOS.App): SHOW_LOADING = True
# Cost: ~210 ms slide-in animation BEFORE app.on_enter — the heavy load then
# runs while the loading panel is the only thing on screen.

def _show_loading(os_obj, label, author=None):
    """Slide a primary-coloured panel down from the top, covering the screen.

    Time-based ease-out over LOADING_SLIDE_MS, so the slide takes the same
    time whatever a frame costs. Each frame repaints and flushes only the
    panel's own rows; the screen below stays as it was, so the panel reads
    as sliding over the previous view. Polls HOME each frame so the user
    can abort a slow app launch — returns True when interrupted.
    """
    from oreoOS import theme
    display = os_obj.display
    buttons = os_obj.buttons
    SW = api.SCREEN_W
    SH = api.SCREEN_H
    label  = (label  or "")[:16].upper()
    byline = ("By @" + author[:24]) if author else ""

    label_lbl  = "LOADING"
    label_x_l  = (SW - len(label_lbl) * 16) // 2
    label_x_n  = (SW - len(label)     *  8) // 2
    byline_x   = (SW - len(byline)    *  8) // 2
    hint       = "HOME to cancel"
    hint_x     = (SW - len(hint) * 8) // 2

    start = time.ticks_ms()
    shown = 0
    while shown < SH:
        # HOME interrupt — the only escape hatch while the slide plays,
        # since the app's on_enter blocks the main loop once we exit.
        buttons.update()
        if buttons.just_pressed(api.BTN_HOME):
            return True

        t = time.ticks_diff(time.ticks_ms(), start) / LOADING_SLIDE_MS
        if t >= 1.0:
            panel_h = SH
        else:
            u = 1.0 - t
            panel_h = int((1.0 - u * u * u) * SH)
        if panel_h <= shown:
            time.sleep_ms(2)
            continue
        shown = panel_h

        display.rect(0, 0, SW, panel_h, theme.PRIMARY, fill=True)
        if panel_h > 60:
            cy = panel_h // 2
            display.text(label_lbl, label_x_l, cy - 16, api.WHITE, scale=2)
            display.text(label,     label_x_n, cy +  6, api.WHITE)
            if byline and panel_h > 100:
                display.text(byline, byline_x, cy + 24, api.WHITE)
            if panel_h > 140:
                display.text(hint, hint_x, panel_h - 22, api.WHITE)
        display.present_rect(0, 0, SW, panel_h)
    return False


# ── generic app run loop ──────────────────────────────────────────────────────

def run_app(os_obj, app):
    os_obj._quit_requested = False
    os_obj._launch_request = None

    # Optional loading transition for heavy apps. The panel covers the screen
    # while on_enter does its work; the very next frame fully overwrites it.
    # If the user mashes HOME during the slide, abort the launch entirely and
    # route them back to the apps drawer instead of waiting for on_enter.
    if getattr(app, "SHOW_LOADING", False):
        label  = getattr(app, "name",   app.__class__.__name__)
        author = getattr(app, "author", None)
        if _show_loading(os_obj, label, author):
            os_obj._launch_request = "__appmenu__"
            return

    # Power manager — singleton on the OS object; idle timer drives deep sleep.
    pm = getattr(os_obj, "_power", None)
    if pm is None:
        try:
            from oreoOS.power import PowerManager
            pm = PowerManager(os_obj)
            os_obj._power = pm
        except Exception:
            pm = None

    # Notification panel singleton — global C-button hotkey, OS-level
    # overlay. Same instance survives app switches so notifications you
    # push from inside an app are visible the moment the user opens it.
    from oreoOS import notif_panel as _np_mod
    panel = _np_mod.get(os_obj)

    # Pair-confirm overlay — sits above the notif panel and the app.
    # While active it eats all input. Drawn after the panel so a fresh
    # SMP prompt is never visually clobbered by a passing notification.
    from oreoOS import pair_prompt as _pp_mod
    pair_pp = _pp_mod.get(os_obj)

    # Consecutive-frame error counter. A single bad frame (transient
    # I2C glitch, momentary divide-by-zero) shouldn't kill the whole
    # OS — we count, log, and only escalate to a crash screen if the
    # error is sticky. Reset on every successful frame.
    frame_errs = 0
    FRAME_ERR_LIMIT = 8

    # Long-press auto-repeat for navigation buttons. Held UP/DOWN/LEFT/
    # RIGHT will fire on_button_press repeatedly at REPEAT_MS cadence
    # after HOLD_MS of continuous hold. Action buttons (A/B/C/HOME) are
    # NOT included — those are commit-style and one fire per press is
    # the right semantic. Apps inherit this behaviour for free: any
    # scrollable list already handles UP/DOWN, no per-app changes.
    HOLD_MS   = 350
    REPEAT_MS = 80
    AUTOREPEAT_BUTTONS = (api.BTN_UP, api.BTN_DOWN, api.BTN_LEFT, api.BTN_RIGHT)
    next_repeat_ms = {b: 0 for b in AUTOREPEAT_BUTTONS}
    last_c_ms = None    # previous C press, for the double-tap panel gesture

    # Timing (oreoOS.perf, read from the REPL) and the background network
    # service (oreoOS.netsvc). Both are optional: a failed import leaves
    # the loop as it was.
    try:
        from oreoOS import perf as _perf
    except Exception:
        _perf = None
    try:
        from oreoOS import netsvc as _net
    except Exception:
        _net = None
    app_name = getattr(app, "name", "")
    # perf's first-press bound: a press latched at any point of the loop
    # period before this frame is read here, and acts by the end of this
    # frame, so period + this frame's work bounds its delay.
    period_ms = 0

    app.on_enter(os_obj)
    last = time.ticks_ms()
    try:
        while not os_obj._quit_requested:
            now = time.ticks_ms()
            period_ms = time.ticks_diff(now, last)
            dt  = period_ms / 1000.0
            last = now
            press_seen = False

            os_obj.buttons.update()

            # Wake-button swallow. PowerManager sets this when light sleep
            # exits — without it, the press that woke us would also fire
            # as a fresh just_pressed against the pre-sleep frame and the
            # current app would handle it (e.g. HOME → go-home).
            if getattr(os_obj, "_just_woke", False):
                os_obj._just_woke = False
            else:
                for b in api.BUTTONS:
                    if os_obj.buttons.just_pressed(b):
                        if pm: pm.note_event()
                        press_seen = True

                        # Pair-confirm prompt has top priority — when an
                        # SMP numeric comparison is in flight, NOTHING
                        # else gets the button. Eats every key including
                        # C and HOME so the user can't accidentally
                        # accept a stranger's pair attempt by hitting C.
                        if pair_pp.is_active():
                            pair_pp.handle_button(b)
                            continue

                        # Global C hotkey → toggle the notification panel
                        # before anything else gets a look. Works from any
                        # app, except one that sets CAPTURES_C because C is
                        # one of its controls (a game's fire button, Gamepad). An
                        # open panel still takes C so it can always close.
                        if b == api.BTN_C and (panel.is_active() or
                                               _np_mod.hotkey_allowed(app)):
                            last_c_ms = None
                            panel.toggle()
                            continue
                        # Apps that use C: a single C is theirs, a quick
                        # double-tap opens the panel (the first tap has
                        # already reached the app; the second does not).
                        if b == api.BTN_C and _np_mod.double_tap_opens(app):
                            if (last_c_ms is not None and time.ticks_diff(
                                    now, last_c_ms) <= _np_mod.DOUBLE_TAP_MS):
                                last_c_ms = None
                                panel.toggle()
                                continue
                            last_c_ms = now

                        # Panel-open input is routed to the panel and the
                        # underlying app sees nothing.
                        if panel.is_active():
                            panel.handle_button(b)
                            continue

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
                        if not panel.is_active():
                            app.on_button_release(b)

                # ── auto-repeat synthesis for held nav buttons ────────
                # After the initial just_pressed dispatch above, a held
                # UP/DOWN/LEFT/RIGHT keeps firing on_button_press every
                # REPEAT_MS so the user can drag-scroll a list without
                # tapping repeatedly. Routed identically to the initial
                # press so the panel-open / app dispatch / HOME-redirect
                # paths all stay consistent.
                tick_ms = time.ticks_ms()
                for b in AUTOREPEAT_BUTTONS:
                    held = os_obj.buttons.pressed_for_ms(b)
                    if held <= HOLD_MS:
                        next_repeat_ms[b] = 0
                        continue
                    if next_repeat_ms[b] == 0:
                        # First repeat fires HOLD_MS after press.
                        next_repeat_ms[b] = tick_ms + REPEAT_MS
                        fire = True
                    elif time.ticks_diff(tick_ms, next_repeat_ms[b]) >= 0:
                        next_repeat_ms[b] = tick_ms + REPEAT_MS
                        fire = True
                    else:
                        fire = False
                    if not fire:
                        continue
                    if pm: pm.note_event()
                    if b == api.BTN_C:
                        # Defensive — BTN_C isn't in AUTOREPEAT_BUTTONS,
                        # but keep the guard so a future edit can't make
                        # the panel re-toggle on every repeat tick.
                        continue
                    if panel.is_active():
                        panel.handle_button(b)
                    else:
                        app.on_button_press(b)

            # Tick the panel BEFORE the app draws so we can detect the
            # exact frame the close animation finishes and force the app
            # to redraw the area the panel just vacated. Without this the
            # last frame of the panel lingers as visible artifacts because
            # the app's _dirty flag is False and panel.draw bails on _t==0.
            # While the panel slides up it uncovers app pixels it painted
            # over, so the app repaints on each of those frames as well.
            panel.tick(dt)
            if panel.consume_closed() or panel.is_closing():
                _invalidate(app)

            # Refresh the pair-confirm overlay's view of the SMP state
            # every frame. Cheap — just one module-level dict peek.
            pp_was_active = pair_pp.is_active()
            try:
                pair_pp.tick()
            except Exception:
                pass
            if pp_was_active and not pair_pp.is_active():
                # Prompt dismissed — force the underlying app to redraw
                # because the overlay painted over its frame.
                _invalidate(app)
                panel.invalidate()

            try:
                app.update(dt)
                # A fully open panel covers the whole screen: skip the app's
                # paint (it would be overdrawn) and let the panel redraw only
                # when its own content changes.
                if not panel.covers_screen():
                    app.draw(os_obj.display)
                panel.draw(os_obj.display)
                # Pair prompt is the topmost layer — drawn last so the
                # 6-digit code can never be obscured by a panel slide-in.
                if pair_pp.is_active():
                    try:
                        pair_pp.draw(os_obj.display)
                    except Exception:
                        pass
                # Apps that redrew only one band can name it in
                # _present_region; the OS then flushes just that rectangle
                # (a full 153 KB push is the most expensive part of a frame).
                region = getattr(app, "_present_region", None)
                if region is not None:
                    app._present_region = None
                    if panel.is_active() or pair_pp.is_active():
                        region = None
                # First OS frame after boot: swipe in from the splash.
                if getattr(os_obj, "_splash_frame", None) is not None:
                    from oreoOS.splash import swipe_in
                    swipe_in(os_obj)
                    region = None
                present_hook = getattr(app, "after_present", None)
                if present_hook is None:
                    if region is None:
                        os_obj.display.present()
                    else:
                        os_obj.display.present_rect(*region)
                else:
                    present_start_us = time.ticks_us()
                    os_obj.display.present()
                    present_hook(time.ticks_diff(
                        time.ticks_us(), present_start_us))
                if not getattr(os_obj, "_home_marked", False):
                    # The first OS frame is on the panel (after the swipe,
                    # or without one if the splash failed): start the
                    # quiet window (#119).
                    os_obj._home_marked = True
                    _bc("first frame shown")
                    if _perf is not None:
                        _perf.home_shown()
                    if _net is not None:
                        _net.home_shown()
                frame_errs = 0
            except Exception as e:
                # A failed first frame keeps the swipe pending for the next
                # one, but only for a few frames.
                if getattr(os_obj, "_splash_frame", None) is not None:
                    tries = getattr(os_obj, "_swipe_tries", 0) + 1
                    os_obj._swipe_tries = tries
                    print("[splash] first frame failed (%d): %s" % (tries, e))
                    if tries >= 3:
                        os_obj._splash_frame = None
                # Per-frame exception swallow + counter. Logging via
                # print keeps a breadcrumb on the USB serial console for
                # post-mortem; we don't draw anything because the
                # framebuf state mid-failure is unknown. After
                # FRAME_ERR_LIMIT consecutive bad frames we give up and
                # let the outer handler crash-screen this app.
                try:
                    print("frame error in", getattr(app, "name", "?"), ":", e)
                except Exception:
                    pass
                frame_errs += 1
                if frame_errs >= FRAME_ERR_LIMIT:
                    raise

            # A realtime app (currently Gallery RV565 playback) retains the
            # normal input path but defers unbounded network/filesystem work.
            # It also gets a 1 ms scheduler floor while waiting for its next
            # frame; the normal 30 ms floor would quantise a 24 FPS timeline
            # into visibly uneven 30/60 ms intervals.
            try:
                realtime = bool(app.realtime_mode())
            except Exception:
                realtime = False

            # Idle check AFTER the frame so the user sees the result of their
            # last input before the chip dozes off. PowerManager calls
            # machine.deepsleep() internally when the threshold is hit — that
            # call never returns; next reset starts main.py fresh.
            if pm and not realtime:
                if panel.keeps_awake():
                    pm.note_event()      # torch on: never doze mid-use
                pm.tick(app)

            # Gestures are NOT polled in the OS run loop. The IMU is
            # opt-in per app: an app that wants tilt / tap / shake
            # imports oreoOS.gestures itself and ticks the engine on
            # its own update(). Polling here previously cost ~50-100 ms
            # per frame on a breadboard without the IMU wired because
            # i2c.scan ran every iteration — now apps without an IMU
            # need pay nothing.

            # BLE adv watchdog. Internal rate-limit means this is a
            # ticks_diff comparison on the fast path; only every 30 s
            # does it actually re-issue gap_advertise. Fixes the
            # "phone says paired-but-not-connected and won't reconnect"
            # case where adv silently stopped between sessions.
            if not realtime:
                try:
                    from oreoWare import bt as _bt
                    _bt.watchdog_tick()
                except Exception:
                    pass

            # LAN HTTP upload server tick. Non-blocking accept on the
            # listening socket — costs one syscall per frame on the
            # idle path. Handles one request synchronously when a
            # phone POSTs, which briefly stalls the UI for the
            # duration of the upload (fine for sub-second photo
            # transfers; we'll move to a background worker later if
            # uploads ever grow above a few hundred KB).
            #
            # Wi-Fi auto-connect, keep-alive and the on-link-up jobs live
            # in netsvc (#118): it only polls here; the clock sync runs on
            # its worker thread and nothing starts in the quiet window
            # after boot.
            net_ms = 0
            if not realtime:
                net_t0 = time.ticks_ms()
                if _net is not None:
                    try:
                        _net.tick(app_name)
                    except Exception:
                        pass
                try:
                    from oreoOS import http_server as _hs
                    _hs.tick()
                except Exception:
                    pass
                # Background OTA probe: rate-limited inside ota to one
                # check every 6 h, only with Wi-Fi up. The GitHub GET runs
                # on its own thread; this call only starts it and, on a
                # later frame, writes the result to settings (UI thread).
                # Still gated on a ticks-based grace after Home here: ota's
                # own grace compares time.time() against a stamp taken
                # before the clock sync, and the first sync after a cold
                # boot jumps the clock by years and defeats it. Timed with
                # the network tail so perf reports it.
                if _net is None or _net.background_ok():
                    try:
                        from oreoOS import ota as _ota
                        _ota.background_check(os_obj, foreground=app_name)
                    except Exception:
                        pass
                net_ms = time.ticks_diff(time.ticks_ms(), net_t0)

            elapsed = time.ticks_diff(time.ticks_ms(), now)
            if _perf is not None:
                _perf.frame(elapsed, net_ms)
                if press_seen:
                    _perf.press(period_ms + elapsed, now)
            frame_floor = 1 if realtime else FRAME_MIN_MS
            if elapsed < frame_floor:
                time.sleep_ms(frame_floor - elapsed)
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

def _maybe_apply_ota(os_obj=None):
    """Run any staged OTA update BEFORE we import the home screen.

    Drives a progress splash while files are copied so the user knows
    the badge hasn't locked up. apply_pending() is a no-op when
    /_ota/manifest.json is absent (the common case), in which case the
    splash is never shown.
    """
    try:
        from oreoOS import ota
        if not ota.is_pending():
            return None
        # Peek at the staged manifest to learn the target version + file
        # count for the splash. Cheap — just opens one JSON file.
        try:
            import json as _j
            with open(ota.STAGE_DIR + "/" + ota.MANIFEST_NAME) as f:
                m = _j.load(f)
            target = m.get("version", "")
            total  = len(m.get("files", ()))
        except Exception:
            target, total = "", 1
        if os_obj is not None:
            try:
                from oreoOS.splash import show_updating
                advance = show_updating(os_obj, target, total)
            except Exception:
                advance = None
        else:
            advance = None
        if advance is None:
            return ota.apply_pending()
        # Keep promotion and cleanup inside ota.apply_pending().  Its return
        # value remains false on a copy failure, leaving staging intact for a
        # controlled retry rather than rebooting a partially applied system.
        return ota.apply_pending(on_progress=advance)
    except Exception:
        return None


def _bc(tag):
    """Boot breadcrumb — print to USB serial with monotonic timestamp.

    Used to live-diagnose boot freezes over the USB-CDC REPL (host runs
    `mpremote connect /dev/ttyACM0`). Each phase prints a short tag so
    we can tell whether a freeze is in WiFi, NTP, OTA-stage-copy, etc.
    Cheap enough to leave in for v1 — one print per boot phase, nothing
    in the run-loop hot path.
    """
    try:
        t = time.ticks_ms()
        print("[boot %d] %s" % (t, tag))
        from oreoOS import perf
        perf.mark(tag, t)
    except Exception:
        pass


class _NoSplash:
    """Stand-in when the splash module cannot load: boot code calls the
    same methods unconditionally."""

    def progress(self, frac):
        pass

    def pump(self):
        return False

    def finish(self, settled=None, cap_ms=6000):
        # No splash on screen: still give Wi-Fi a moment to start
        # associating, but never hold boot past cap_ms.
        if settled is None:
            return
        t0 = time.ticks_ms()
        try:
            while (not settled() and
                   time.ticks_diff(time.ticks_ms(), t0) < cap_ms):
                time.sleep_ms(20)
        except Exception:
            pass


SAFE_HOLD_MS = 300      # HOME must stay down this long to mean safe mode


def _safe_boot_requested(buttons, hold_ms=SAFE_HOLD_MS):
    """True when HOME is held while the badge boots (safe mode).

    HOME is GPIO9, not a strapping pin, so holding it at power-on does not
    put the ESP32-S3 in download mode. The press is read once, then again
    after hold_ms so a bounce or a stray tap does not count. Reading it
    through update() also consumes the press edge, so Home does not see a
    HOME press on its first frame."""
    try:
        buttons.update()
        if not buttons.is_pressed(api.BTN_HOME):
            return False
        t0 = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < hold_ms:
            time.sleep_ms(20)
            buttons.update()
            if not buttons.is_pressed(api.BTN_HOME):
                return False
        return True
    except Exception:
        return False


def _warm_up(os_obj):
    """Do behind the splash what the first frames would otherwise pay for
    (#119): import the modules the run loop uses, build its singletons,
    and load Home's wallpaper and dock icon into their caches."""
    try:
        from oreoOS import notif_panel, pair_prompt
        notif_panel.get(os_obj)
        pair_prompt.get(os_obj)
    except Exception as e:
        _bc("warm panel FAILED: %s" % e)
    try:
        if getattr(os_obj, "_power", None) is None:
            from oreoOS.power import PowerManager
            os_obj._power = PowerManager(os_obj)
    except Exception:
        pass
    for mod in ("oreoOS.http_server", "oreoOS.ota", "oreoOS.netsvc",
                "oreoOS.perf"):
        try:
            __import__(mod)
        except Exception:
            pass
    try:
        from oreoOS import home as _home
        _home._get_scaled_bg()
        _home._load_apps_icon()
    except Exception:
        pass
    gc.collect()


def boot():
    _bc("entered boot()")
    from oreoWare.os import OS
    from oreoOS.home   import Home
    _bc("imports done")

    # Bring the hardware up first so the OTA splash has a display to draw
    # on. The trade-off: if an OTA swaps oreoWare/display.py we'll have
    # already imported the old version — _maybe_apply_ota does a
    # machine.reset() after apply to guarantee the new drivers boot fresh.
    os_obj = OS()
    _bc("OS() constructed")
    # Safe mode: HOME held while booting skips Wi-Fi and Bluetooth
    # auto-start for this boot (the crash screen in entry.py points here).
    safe = _safe_boot_requested(os_obj.buttons)
    os_obj._safe_mode = safe
    if safe:
        _bc("SAFE MODE (HOME held): Wi-Fi and BT auto-start skipped")
    # Every boot starts at full brightness; the panel and Settings adjust it
    # for the session (both through _last_brightness), and the splash fades
    # back up to it.
    os_obj._last_brightness = 100
    try:
        os_obj.display.set_brightness(100)
    except Exception:
        pass

    # Stamp the boot timestamp on the OS object so OTA can refuse to
    # probe inside the first minutes of uptime — without this the very
    # first run-loop frame fires a synchronous GitHub API GET, freezing
    # whichever transition the user triggers (e.g. "press A on home").
    # This stamp is wall-clock and is taken before the clock sync, so the
    # run loop also gates the probe on netsvc.background_ok() (ticks).
    try:
        os_obj._boot_ts_s = int(time.time())
    except Exception:
        os_obj._boot_ts_s = 0

    # Gestures intentionally NOT seeded at the OS layer — the IMU stack
    # is opt-in per app now. The Gestures settings page (`apps/gestures`)
    # imports oreoOS.gestures itself when the user opens it.

    _bc("checking pending OTA")
    applied = _maybe_apply_ota(os_obj)
    _bc("OTA check done (applied=%s)" % bool(applied))
    if applied:
        # Persist the version for the post-reboot "Updated to vX.Y.Z" toast.
        try:
            os_obj.settings_set("ota_just_applied", applied)
            os_obj.settings_set("ota_status",       "applied")
            os_obj.settings_set("ota_pending_peek_ok", False)
        except Exception:
            pass
        # Clean reboot so every module imports the new code on the next
        # boot. apply_pending already deleted /_ota so the boot path
        # won't re-apply this round.
        try:
            import machine
            machine.reset()
        except Exception:
            pass
    # The splash keeps animating while the rest of boot runs: intro()
    # draws the logo + title, then pump() repaints the "hello" greeting
    # between boot steps and inside the WiFi association wait. Splash
    # must NEVER kill the boot — every Splash method swallows its own
    # errors, and a failed import falls back to a no-op stand-in.
    _bc("splash intro")
    try:
        from oreoOS.splash import Splash
        splash = Splash(os_obj)
        splash.intro()
    except Exception as e:
        _bc("splash FAILED: %s" % e)
        splash = _NoSplash()
    _bc("splash intro done")

    # Start Wi-Fi and BT behind the splash. netsvc.begin() applies the
    # Wi-Fi gates: secrets.WIFI_AUTO_CONNECT, Settings -> WiFi ->
    # Auto-connect, one Wi-Fi-free boot after a brownout reset (a weak
    # supply can still reach Home), and safe mode. Joining is
    # non-blocking: the splash only waits for the association to start.
    splash.progress(0.2)
    try:
        from oreoOS import netsvc
        _bc("wifi: %s" % netsvc.begin(os_obj, safe=safe))
    except Exception as e:
        netsvc = None
        _bc("wifi block FAILED: %s" % e)
    splash.progress(0.7)
    if safe:
        _bc("bt skipped (safe mode)")
    else:
        try:
            from oreoWare import bt
            _bc("bt.init_from_config begin")
            bt.init_from_config()
            _bc("bt.init_from_config done")
        except Exception as e:
            _bc("bt block FAILED: %s" % e)
    splash.progress(0.85)
    # Build the first Home while the greeting is still rolling, so the
    # splash covers that loading too and hands straight over to Home.
    first = None
    try:
        apps = list_apps()
        first = (apps, Home(apps))
    except Exception as e:
        _bc("first home FAILED: %s" % e)
    _warm_up(os_obj)
    _bc("warm-up done")
    if safe:
        try:
            from oreoOS import notifications
            notifications.push("system", "Safe mode",
                               "Wi-Fi and BT not started", target="wifi")
        except Exception:
            pass
    # Keep the splash until boot has settled (Wi-Fi association started,
    # driven from here while we wait), capped at splash.MAX_TOTAL_MS.
    settled = netsvc.boot_settled if netsvc is not None else None
    splash.finish(settled)
    _bc("splash done")
    del splash
    gc.collect()
    _bc("entering main loop")

    while True:
        if first is not None:
            apps, home = first
            first = None
        else:
            apps = list_apps()
            home = Home(apps)
        # Reaching the home screen is the "I'm done" signal — clear any
        # launcher resume context so the next drawer open starts fresh
        # rather than restoring the user to where they last were inside
        # a category. HOME-from-app already chains via __appmenu__ and
        # consumes the context; this just guarantees a clean slate when
        # the user actually lands on home.
        try:
            os_obj._launcher_resume = None
        except Exception:
            pass
        # Home is wrapped just like app launches below — a crash in the
        # home screen used to take the whole OS down silently (the LCD
        # froze on whatever was last drawn, no button polling, requiring
        # a hardware reset). Now we paint a crash screen and loop back
        # so the next iteration rebuilds Home from scratch.
        try:
            run_app(os_obj, home)
        except Exception as e:
            show_crash(os_obj, "home", e)
            continue

        # Chain-launch loop. Each app may call os.launch(...) on the
        # way out (e.g. Settings → Gestures, Settings → WiFi). We keep
        # consuming _launch_request until it's empty — otherwise a
        # sub-launched app would get clobbered by Home's run_app re-
        # initialising _launch_request = None on entry, and the user
        # would briefly see Home flash before having to re-navigate.
        while True:
            target = os_obj._launch_request

            # Home's APPS dock sends "__appmenu__" — route it to the
            # first-class apps/launcher/ implementation.
            if target == "__appmenu__":
                target = "launcher"

            if not target:
                break    # nothing queued; outer loop returns to Home

            try:
                app = load_app(target)
                run_app(os_obj, app)
            except Exception as e:
                show_crash(os_obj, target, e)
                break


if __name__ == "__main__":
    boot()

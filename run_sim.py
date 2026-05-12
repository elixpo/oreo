"""Elixpo OS — pygame simulator.

Run from project root:
    python run_sim.py

Controls:
  Arrow keys   → UP / DOWN / LEFT / RIGHT
  Escape / H   → HOME  (back to home screen)
  Z / Enter    → A (select / confirm)
  X            → B
  C / Tab      → C
"""

import sys
import os
import time
import gc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# MicroPython shims — patch before any lix_os import
if not hasattr(time, "ticks_ms"):
    time.ticks_ms   = lambda: int(time.monotonic() * 1000)
    time.ticks_diff = lambda a, b: a - b
if not hasattr(time, "sleep_ms"):
    time.sleep_ms = lambda ms: time.sleep(ms / 1000.0)

import pygame

from lix_sim.display import SimDisplay, SCALE
from lix_sim.buttons import SimButtons
from lix_sim.os      import SimOS
from lix             import api

from lix_os.splash   import show_splash
from lix_os.home     import Home
from lix_os          import launcher

WINDOW_TITLE = "Elixpo Badge Simulator"
FPS_CAP      = 60
BADGE_W      = api.SCREEN_W * SCALE
BADGE_H      = api.SCREEN_H * SCALE
BORDER       = 20
LEGEND_H     = 110
WIN_W        = BADGE_W + BORDER * 2
WIN_H        = BADGE_H + BORDER * 2 + LEGEND_H

_KEY_LABELS = [
    ("Esc", "HOME"),
    ("Arrows", "D-Pad"),
    ("Z / ↵", "A"),
    ("X", "B"),
    ("C", "C"),
]


def _draw_chrome(win, badge_surf, legend_font, fps):
    win.fill((14, 14, 26))
    # bezel
    pygame.draw.rect(win, (40, 40, 60),
                     (BORDER - 6, BORDER - 6, BADGE_W + 12, BADGE_H + 12),
                     border_radius=8)
    win.blit(badge_surf, (BORDER, BORDER))
    # FPS counter
    fps_s = legend_font.render("%.0f fps" % fps, True, (60, 60, 90))
    win.blit(fps_s, (BORDER, BORDER + BADGE_H + 4))
    # key legend
    lx = BORDER
    ly = BORDER + BADGE_H + 20
    for key, label in _KEY_LABELS:
        pygame.draw.rect(win, (30, 30, 50), (lx, ly, 96, 44), border_radius=6)
        pygame.draw.rect(win, (0, 160, 140), (lx, ly, 96, 44), 1, border_radius=6)
        win.blit(legend_font.render(key,   True, (220, 220, 220)), (lx + 48 - legend_font.size(key)[0]   // 2, ly + 6))
        win.blit(legend_font.render(label, True, (100, 100, 140)), (lx + 48 - legend_font.size(label)[0] // 2, ly + 26))
        lx += 108


def _run_app(os_obj, buttons, app, badge_surf, win, clock, legend_font):
    os_obj._quit_requested = False
    os_obj._launch_request = None

    app.on_enter(os_obj)
    last_ms = pygame.time.get_ticks()

    try:
        while not os_obj._quit_requested:
            now_ms = pygame.time.get_ticks()
            dt     = (now_ms - last_ms) / 1000.0
            last_ms = now_ms

            buttons.update()
            for b in api.BUTTONS:
                if buttons.just_pressed(b):
                    if b == api.BTN_HOME:
                        os_obj.quit()
                    else:
                        app.on_button_press(b)
                if buttons.just_released(b):
                    app.on_button_release(b)

            if os_obj._quit_requested:
                break

            app.update(dt)
            app.draw(os_obj.display)

            fps = clock.get_fps()
            _draw_chrome(win, badge_surf, legend_font, fps)
            pygame.display.flip()
            clock.tick(FPS_CAP)
    finally:
        app.on_exit()
        gc.collect()


def _wait_key(win, badge_surf, clock, legend_font, buttons):
    """Block until any key press — used after crash screen."""
    while True:
        buttons.update()
        if any(buttons.just_pressed(b) for b in api.BUTTONS):
            return
        _draw_chrome(win, badge_surf, legend_font, clock.get_fps())
        pygame.display.flip()
        clock.tick(FPS_CAP)


def main():
    pygame.init()
    pygame.display.set_caption(WINDOW_TITLE)
    win         = pygame.display.set_mode((WIN_W, WIN_H))
    clock       = pygame.time.Clock()
    legend_font = pygame.font.SysFont("DejaVu Sans,Arial,sans-serif", 14)

    badge_surf = pygame.Surface((BADGE_W, BADGE_H))
    display    = SimDisplay(badge_surf)
    buttons    = SimButtons()
    os_obj     = SimOS(display, buttons)

    # ── animated splash ───────────────────────────────────────────────────────
    # Run splash as a tight loop driven by its own timer
    from lix_os.splash import show_splash as _splash
    import threading

    splash_done = [False]

    def _splash_loop():
        # show_splash blocks for ~3s internally; we pump pygame events alongside
        pass

    # We'll run the splash inside the normal frame loop so pygame stays alive
    from lix_os.splash import TOTAL_MS
    splash_start = pygame.time.get_ticks()

    import lix_os.splash as _sp
    _sp_start = time.ticks_ms()

    while True:
        elapsed_sp = pygame.time.get_ticks() - splash_start
        if elapsed_sp >= TOTAL_MS:
            break

        # Drain events to keep window responsive
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_SPACE:
                elapsed_sp = TOTAL_MS; break  # space = skip splash

        # Build one splash frame at the current elapsed time
        _draw_splash_frame(display, elapsed_sp)

        _draw_chrome(win, badge_surf, legend_font, clock.get_fps())
        pygame.display.flip()
        clock.tick(FPS_CAP)

    display.clear(api.BLACK)

    # ── main OS loop ──────────────────────────────────────────────────────────
    while True:
        apps = launcher.list_apps()
        home = Home(apps)
        _run_app(os_obj, buttons, home, badge_surf, win, clock, legend_font)

        target = os_obj._launch_request

        if target == "__appmenu__":
            menu = launcher._AppMenu(apps)
            _run_app(os_obj, buttons, menu, badge_surf, win, clock, legend_font)
            target = os_obj._launch_request

        if target and target not in (None, "__appmenu__"):
            try:
                app = launcher.load_app(target)
                _run_app(os_obj, buttons, app, badge_surf, win, clock, legend_font)
            except Exception as e:
                launcher.show_crash(os_obj, target, e)
                _draw_chrome(win, badge_surf, legend_font, clock.get_fps())
                pygame.display.flip()
                _wait_key(win, badge_surf, clock, legend_font, buttons)


def _draw_splash_frame(display, elapsed_ms):
    """Replicate splash.py animation inline for the sim's frame-pumped loop."""
    from lix_os import panda as _p
    from lix_os.splash import (BG, PRIMARY, ACCENT, MUTED,
                                _PANDA_X, _PANDA_Y, _PS,
                                _TEXT_X, _TEXT_Y, _SUB_Y, _VER_Y,
                                _BAR_X, _BAR_Y, _BAR_W, TOTAL_MS, _lerp)

    def phase(e, s, en):
        t = e / TOTAL_MS
        if t < s:  return 0.0
        if t >= en: return 1.0
        return (t - s) / (en - s)

    d = display
    d.clear(BG)

    p1 = phase(elapsed_ms, 0.0, 0.25)
    if p1 > 0:
        sy = int(p1 * api.SCREEN_H)
        d.rect(0, max(0, sy - 30), api.SCREEN_W, 30, api.rgb(0, 40, 35), fill=True)
        d.rect(0, max(0, sy - 3),  api.SCREEN_W,  3, PRIMARY, fill=True)

    p2 = phase(elapsed_ms, 0.15, 0.72)
    if p2 > 0:
        rows = max(1, int(p2 * _p.PANDA_H))
        _p.draw_panda(d, _PANDA_X, _PANDA_Y, ps=_PS, max_rows=rows)

    p3 = phase(elapsed_ms, 0.60, 1.10)
    if p3 > 0:
        n = max(1, int(p3 * 6))
        d.text("ELIXPO"[:n], _TEXT_X, _TEXT_Y, PRIMARY, scale=4)

    p4 = phase(elapsed_ms, 1.00, 1.45)
    if p4 > 0:
        n_sub = max(1, int(p4 * 8))
        d.text("BADGE OS"[:n_sub], 72, _SUB_Y, api.WHITE, scale=2)
        if p4 > 0.8:
            d.text("v0.1", 100, _VER_Y, MUTED)

    p5 = phase(elapsed_ms, 1.30, 2.00)
    if p5 > 0:
        d.rect(_BAR_X, _BAR_Y, _BAR_W, 5, api.rgb(25, 25, 40), fill=True)
        filled = int(p5 * _BAR_W)
        if filled > 0:
            d.rect(_BAR_X, _BAR_Y, filled, 5, PRIMARY, fill=True)
        d.text("%d%%" % int(p5 * 100), _BAR_X + _BAR_W + 4, _BAR_Y - 2, MUTED)

    p6 = phase(elapsed_ms, 1.90, 2.60)
    if p6 > 0:
        pulse = abs((p6 * 2) % 2 - 1)
        rail_c = api.rgb(int(_lerp(0, 255, pulse)),
                         int(_lerp(220, 80, pulse)),
                         int(_lerp(200, 200, pulse)))
        d.rect(20, _TEXT_Y - 6, api.SCREEN_W - 40, 2, rail_c, fill=True)
        d.rect(20, _BAR_Y + 10, api.SCREEN_W - 40, 2, rail_c, fill=True)

    p7 = phase(elapsed_ms, 2.60, 3.00)
    if p7 > 0 and p7 >= 1.0:
        d.clear(api.BLACK)


if __name__ == "__main__":
    main()

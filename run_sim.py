"""Lix OS pygame simulator entry point.

Run from the project root:
    python run_sim.py

Controls:
  Arrow keys   → UP / DOWN / LEFT / RIGHT
  Escape / H   → HOME  (back to launcher)
  Z / Enter    → A     (select / confirm)
  X            → B
  C / Tab      → C
"""

import sys
import os
import time
import gc

# Make project root importable regardless of cwd
sys.path.insert(0, os.path.dirname(__file__))

import pygame

from lix_sim.display import SimDisplay, SCALE
from lix_sim.buttons import SimButtons
from lix_sim.os import SimOS
from lix import api

# Re-use the launcher logic (app discovery, menu, crash screen, run_app)
import lix_os.launcher as launcher

WINDOW_TITLE  = "Elixpo Badge Simulator"
FPS_CAP       = 60
BADGE_W       = api.SCREEN_W * SCALE   # 720
BADGE_H       = api.SCREEN_H * SCALE   # 960
BORDER        = 24                      # gray bezel around the badge
WIN_W         = BADGE_W + BORDER * 2
WIN_H         = BADGE_H + BORDER * 2 + 120  # extra room for key legend


# ---------- key legend -------------------------------------------------------

def _draw_legend(win, font):
    legends = [
        ("Esc/H", "HOME"),
        ("Arrows", "D-Pad"),
        ("Z/Enter", "A"),
        ("X", "B"),
        ("C/Tab", "C"),
    ]
    x = BORDER
    y = BADGE_H + BORDER * 2 + 6
    win.fill((30, 30, 40), pygame.Rect(0, BADGE_H + BORDER * 2, WIN_W, 120))
    for key, label in legends:
        pygame.draw.rect(win, (60, 60, 80), pygame.Rect(x, y, 100, 44), border_radius=6)
        pygame.draw.rect(win, (100, 220, 200), pygame.Rect(x, y, 100, 44), 2, border_radius=6)
        key_surf = font.render(key, True, (255, 255, 255))
        lbl_surf = font.render(label, True, (150, 150, 180))
        win.blit(key_surf, (x + 50 - key_surf.get_width() // 2, y + 6))
        win.blit(lbl_surf, (x + 50 - lbl_surf.get_width() // 2, y + 26))
        x += 116


# ---------- main -------------------------------------------------------------

def main():
    pygame.init()
    pygame.display.set_caption(WINDOW_TITLE)
    win = pygame.display.set_mode((WIN_W, WIN_H))
    clock = pygame.time.Clock()

    legend_font = pygame.font.SysFont("DejaVu Sans,Arial,sans-serif", 14)

    # Badge surface sits inside the bezel
    badge_surf = pygame.Surface((BADGE_W, BADGE_H))

    display = SimDisplay(badge_surf)
    buttons = SimButtons()
    os_obj  = SimOS(display, buttons)

    # Show splash
    launcher.show_splash(display)
    win.fill((20, 20, 28))
    win.blit(badge_surf, (BORDER, BORDER))
    _draw_legend(win, legend_font)
    pygame.display.flip()
    pygame.time.wait(launcher.SPLASH_MS)

    # Boot loop (mirrors launcher.boot())
    while True:
        apps = launcher.list_apps()
        menu = launcher._Menu(apps)
        _run_app_sim(os_obj, buttons, menu, badge_surf, win, clock, legend_font)

        target = os_obj._launch_request
        if target:
            try:
                app = launcher.load_app(target)
                _run_app_sim(os_obj, buttons, app, badge_surf, win, clock, legend_font)
            except Exception as e:
                launcher.show_crash(os_obj, target, e)
                win.fill((20, 20, 28))
                win.blit(badge_surf, (BORDER, BORDER))
                pygame.display.flip()
                # wait for any key to clear crash screen
                waiting = True
                while waiting:
                    for ev in pygame.event.get():
                        if ev.type == pygame.QUIT:
                            pygame.quit()
                            sys.exit()
                        if ev.type == pygame.KEYDOWN:
                            waiting = False


def _run_app_sim(os_obj, buttons, app, badge_surf, win, clock, legend_font):
    """Drive one app through its full lifecycle inside the pygame window."""
    os_obj._quit_requested = False
    os_obj._launch_request = None

    app.on_enter(os_obj)
    last_ms = pygame.time.get_ticks()

    try:
        while not os_obj._quit_requested:
            now_ms = pygame.time.get_ticks()
            dt = (now_ms - last_ms) / 1000.0
            last_ms = now_ms

            # 1. inputs — SimButtons.update() drains pygame events
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

            # 2. tick + render
            app.update(dt)
            app.draw(os_obj.display)   # draws onto badge_surf

            # 3. composite badge into window
            win.fill((20, 20, 28))
            pygame.draw.rect(win, (50, 50, 60),
                             pygame.Rect(BORDER - 4, BORDER - 4,
                                         BADGE_W + 8, BADGE_H + 8))
            win.blit(badge_surf, (BORDER, BORDER))
            _draw_legend(win, legend_font)
            pygame.display.flip()

            clock.tick(FPS_CAP)
    finally:
        app.on_exit()
        gc.collect()


if __name__ == "__main__":
    main()

"""Visual button tester — shows all 8 buttons on the display, lighting up when pressed.

Only redraws the rows that actually changed since last frame, and only pushes
those rows to the panel via Display.present_rect(). Avoids the full-screen
SPI-wipe that causes flicker on every-frame redraws.
"""

import time

from oreoOS import api
from oreoWare.buttons import Buttons
from oreoWare.display import Display


NAMES = {
    api.BTN_HOME:  "HOME",
    api.BTN_A:     "A",
    api.BTN_B:     "B",
    api.BTN_C:     "C",
    api.BTN_UP:    "UP",
    api.BTN_DOWN:  "DOWN",
    api.BTN_LEFT:  "LEFT",
    api.BTN_RIGHT: "RIGHT",
}

ROW_X      = 10
ROW_W      = api.SCREEN_W - 20
ROW_H      = 26
ROW_Y0     = 44
ROW_PITCH  = 32

GRAY_BG    = api.rgb(30, 30, 40)
GRAY_TX    = api.rgb(120, 120, 130)
GREEN_BG   = api.rgb(40, 140, 40)
GREEN_TX   = api.WHITE
TITLE_CLR  = api.rgb(255, 200, 0)


def draw_row(disp, y, label, pressed):
    bg = GREEN_BG if pressed else GRAY_BG
    tx = GREEN_TX if pressed else GRAY_TX
    disp.rect(ROW_X, y, ROW_W, ROW_H, bg, fill=True)
    disp.text(label, ROW_X + 10, y + 6, tx, scale=2)
    disp.text("ON" if pressed else "off", api.SCREEN_W - 60, y + 6, tx, scale=2)


def main():
    btns = Buttons()
    disp = Display()

    # full initial draw
    disp.clear(api.BLACK)
    disp.text("BUTTONS", 60, 10, TITLE_CLR, scale=2)
    btns.update()
    state = [btns.is_pressed(b) for b in api.BUTTONS]
    for i, pressed in enumerate(state):
        draw_row(disp, ROW_Y0 + i * ROW_PITCH, NAMES[api.BUTTONS[i]], pressed)
    disp.present()

    print("btn_test_all: press buttons; only changed rows redraw. Ctrl-C to stop.")
    while True:
        btns.update()
        for i, b in enumerate(api.BUTTONS):
            now = btns.is_pressed(b)
            if now != state[i]:
                y = ROW_Y0 + i * ROW_PITCH
                draw_row(disp, y, NAMES[b], now)
                disp.present_rect(ROW_X, y, ROW_W, ROW_H)
                state[i] = now
        time.sleep_ms(8)


main()

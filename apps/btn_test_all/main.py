"""Visual button tester — shows all 8 buttons on the display, lighting up when pressed.

Proves the lix Display + Buttons backends work end-to-end through the API.
"""

import time

from lix import api
from lix_hw.buttons import Buttons
from lix_hw.display import Display


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

GRAY_BG     = api.rgb(30, 30, 40)
GRAY_TEXT   = api.rgb(120, 120, 130)
GREEN_BG    = api.rgb(40, 140, 40)
GREEN_TEXT  = api.WHITE
TITLE_COLOR = api.rgb(255, 200, 0)


def draw_row(disp, y, label, pressed):
    bg   = GREEN_BG   if pressed else GRAY_BG
    text = GREEN_TEXT if pressed else GRAY_TEXT
    disp.rect(10, y, api.SCREEN_W - 20, 26, bg, fill=True)
    disp.text(label, 20, y + 6, text, scale=2)
    state = "ON" if pressed else "off"
    disp.text(state, api.SCREEN_W - 60, y + 6, text, scale=2)


def main():
    btns = Buttons()
    disp = Display()
    print("btn_test_all: press any button. Ctrl-C to stop.")
    while True:
        btns.update()
        disp.clear(api.BLACK)
        disp.text("BUTTONS", 60, 10, TITLE_COLOR, scale=2)
        y = 44
        for b in api.BUTTONS:
            draw_row(disp, y, NAMES[b], btns.is_pressed(b))
            y += 32
        disp.present()
        time.sleep_ms(16)


main()

from machine import Pin
from neopixel import NeoPixel
import time

BUTTONS = {
    "HOME":  9,
    "A":    10,
    "B":    13,
    "C":     8,
    "UP":    4,
    "DOWN":  5,
    "LEFT":  6,
    "RIGHT": 7,
}

pins = {name: Pin(gpio, Pin.IN, Pin.PULL_UP) for name, gpio in BUTTONS.items()}
last = {name: pins[name].value() for name in BUTTONS}
np = NeoPixel(Pin(48), 1)

print("watching all 8 buttons (Ctrl-C to stop)")
print("HOME=9  A=10  B=13  C=8  UP=4  DOWN=5  LEFT=6  RIGHT=7")

while True:
    held = []
    changed = False
    for name in BUTTONS:
        v = pins[name].value()
        if v != last[name]:
            edge = "pressed " if v == 0 else "released"
            print(f"{edge} {name:5s}  (GPIO{BUTTONS[name]})")
            last[name] = v
            changed = True
        if v == 0:
            held.append(name)
    if changed:
        np[0] = (0, 32, 0) if held else (0, 0, 0)
        np.write()
    time.sleep_ms(10)

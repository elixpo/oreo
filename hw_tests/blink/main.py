import time
from machine import Pin
from neopixel import NeoPixel

np = NeoPixel(Pin(48), 1)

COLORS = [
    (32,  0,  0),   # red
    (32, 16,  0),   # orange
    (32, 32,  0),   # yellow
    ( 0, 32,  0),   # green
    ( 0, 16, 32),   # cyan-blue
    ( 0,  0, 32),   # blue
    (16,  0, 32),   # purple
]

print("blink: oreoOS says hello")
while True:
    for c in COLORS:
        np[0] = c
        np.write()
        time.sleep(0.25)

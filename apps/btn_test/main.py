from machine import Pin
from neopixel import NeoPixel
import time

BTN_PIN = 9
LED_PIN = 48

btn = Pin(BTN_PIN, Pin.IN, Pin.PULL_UP)
np  = NeoPixel(Pin(LED_PIN), 1)

last = btn.value()
print(f"watching GPIO{BTN_PIN}: press the button (Ctrl-C to stop)")

while True:
    v = btn.value()
    if v != last:
        if v == 0:
            print("PRESSED")
            np[0] = (0, 32, 0)
        else:
            print("released")
            np[0] = (0, 0, 0)
        np.write()
        last = v
    time.sleep_ms(10)

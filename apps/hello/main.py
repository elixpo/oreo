"""First app that uses the lix Display API — no raw SPI, no ST7789 details."""

from lix import api
from lix_hw.display import Display

d = Display()

# background
d.clear(api.rgb(20, 20, 40))

# title bar
d.rect(0, 0, api.SCREEN_W, 30, api.rgb(255, 100, 30), fill=True)
d.text("Lix OS", 8, 11, api.BLACK, scale=2)

# centered card
d.rect(20, 60, 200, 200, api.WHITE, fill=True)
d.rect(20, 60, 200, 200, api.rgb(50, 50, 80))
d.text("hello, world", 36, 130, api.BLACK)
d.text("badge alive", 50, 160, api.rgb(120, 0, 0))

# decoration
for i in range(0, api.SCREEN_W, 8):
    d.pixel(i,                     api.SCREEN_H - 1, api.rgb(255, 200, 0))
    d.pixel(api.SCREEN_W - 1 - i,  api.SCREEN_H - 4, api.rgb(255, 200, 0))

d.present()
print("hello: drawn")

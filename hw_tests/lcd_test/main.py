from machine import Pin, SPI
import time

from oreoWare import pins
from oreoWare._st7789 import ST7789

RED   = 0xF800
GREEN = 0x07E0
BLUE  = 0x001F
WHITE = 0xFFFF
BLACK = 0x0000


def build_lcd():
    spi = SPI(
        1,
        baudrate=pins.DISPLAY_BAUD,
        polarity=0, phase=0,
        sck=Pin(pins.DISPLAY_SCK),
        mosi=Pin(pins.DISPLAY_MOSI),
    )
    return ST7789(
        spi,
        dc =Pin(pins.DISPLAY_DC,    Pin.OUT),
        cs =Pin(pins.DISPLAY_CS,    Pin.OUT, value=1),
        rst=Pin(pins.DISPLAY_RESET, Pin.OUT, value=1),
        bl =Pin(pins.DISPLAY_BL,    Pin.OUT, value=0),
    )


def main():
    print("lcd: init...")
    lcd = build_lcd()
    lcd.init()
    print("lcd: init done. cycling colors (Ctrl-C to stop)")
    while True:
        for color, name in [(RED, "red"), (GREEN, "green"), (BLUE, "blue"),
                             (WHITE, "white"), (BLACK, "black")]:
            print(f"  -> {name}")
            lcd.fill(color)
            time.sleep(1)


main()

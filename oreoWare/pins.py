"""GPIO assignments for the Falera Badge: the breadboard prototype, then the PCB.

Single source of truth. Every hardware module imports from here — never hardcode a
GPIO number anywhere else. When the PCB swaps pins, this is the only file to edit.
"""

# ----- Display: SmartElex 2.0" IPS, ST7789P3, 4-wire SPI -----
# Module silkscreen → our name:  CS=CS, RST=RESET, DC=DC, SDA=MOSI, SCL=SCK, EN=BL
# Power: VCC → DevKit 5V pin (module has onboard 3V3 LDO). TE pin left disconnected.
DISPLAY_CS    = 14
DISPLAY_RESET = 16
DISPLAY_DC    = 15
DISPLAY_MOSI  = 11     # display silkscreen: SDA
DISPLAY_SCK   = 12     # display silkscreen: SCL
DISPLAY_BL    = 17     # display silkscreen: EN. Active-high, PWM-capable for brightness
DISPLAY_BAUD  = 40_000_000  # 40MHz SPI. Each full framebuf transfer is
                            # 320×240×2 = 153,600 bytes → ~30.7 ms on the wire.
                            # 40 MHz is the practical ceiling for GPIO-matrix-
                            # routed pins on ESP32-S3 (MOSI=11, SCK=12 aren't
                            # on the IO_MUX — going higher loses bits at the
                            # GPIO matrix). Combined with the 4-chunk write
                            # and proper 5V power, this is stable.

# ----- Buttons (active-low, internal pull-up) -----
BTN_HOME   = 9
BTN_A      = 10
BTN_B      = 13
BTN_C      = 8
BTN_UP     = 4
BTN_DOWN   = 5
BTN_LEFT   = 6
BTN_RIGHT  = 7

# ----- microSD (SDMMC host, 1-bit, the host's own DMA) -----
# Breadboard: a plain 3.3 V microSD breakout (no level shifter; the blue
# 5 V SPI modules buffer the lines one way and cannot do SDMMC). CMD and D0
# need 10 kΩ pull-ups to 3V3 (most breakouts have them). Its own bus, so the
# card never shares the display's SPI bus. These pins were the corner LEDs,
# which were never wired or driven; they move to the I2C expander or the PCB
# (#102).
SD_CLK = 38
SD_CMD = 39
SD_D0  = 40

# ----- I2S speaker amplifier (MAX98357A) -----
# BCLK/LRCLK/DIN only; the amp's SD pin to VIN (always on, L+R mix), GAIN
# floating (9 dB). VIN from the 5 V rail, not the 3.3 V regulator.
# GPIO46 is a boot-strapping pin: it must read low at reset and while
# flashing. The amp's DIN is a high-impedance input and the pin's internal
# pull-down keeps it low until I2S starts, so add no pull-up on this line.
I2S_BCLK  = 41
I2S_LRCLK = 21
I2S_DOUT  = 46

# ----- Status NeoPixel (onboard WS2812) -----
LED_STATUS = 48

# ----- IR subsystem -----
# Reassigned from BOM's original GPIO48 because that pin is the onboard NeoPixel.
# Picked from the unused pool: 2, 18, 21, 42, 47.
IR_TX = 2     # to 2N2222 base via 4.7kΩ
IR_RX = 18    # TSOP38238 OUT pin

# ----- Analog inputs -----
ADC_VBAT = 1  # ADC1_CH0, fed by the 100kΩ/100kΩ divider stub

# ----- I2C bus (shared by MPU6050; future expanders) -----
# Picked from the unused pool: 42, 47 are general-purpose, non-strapping,
# not on PSRAM lines for N16R8, and not USB-OTG pads.
I2C_SDA   = 42
I2C_SCL   = 47

# ----- MPU6050 -----
# +Y axis of the IMU is wired to "up" on the screen (the way the user holds
# the badge horizontally during the racer game). Mount in-plane with the
# board so pitch = front/back tilt, roll = side-to-side tilt, yaw = twist.
IMU_INT   = 3      # RTC_GPIO3 — wakes from deep sleep on a motion interrupt

# ----- TTP223 touch pads (not fitted) -----
# The planned pads were never wired or read. Their pins went elsewhere:
# GPIO21 is I2S LRCLK, and GPIO33 is not on the DevKit header at all (inside
# the N16R8 module it belongs to the octal PSRAM bus). Pick new pins for
# touch on the expander or the PCB (#102).


# ═════ PCB badge (circuit/elixpo/) ══════════════════════════════════════
# The values above are the breadboard's. On the PCB badge, which
# oreoWare.board detects from its AW9523B expander, the pins below
# replace them. The display (11, 12, 14-17), microSD (38-40), IR (2, 18),
# status LED (48) and battery sense (1) keep the same GPIOs.
try:
    from oreoWare import board as _board
    BOARD = _board.board()
except ImportError:
    BOARD = "breadboard"

DISPLAY_DRIVER = "st7789"
EXPANDER = False            # buttons on GPIOs (breadboard) or the AW9523B

if BOARD == "pcb":
    # 2.8" ILI9341 module (MSP2807 type) with an XPT2046 touch controller
    DISPLAY_DRIVER = "ili9341"
    DISPLAY_MISO   = 13     # the touch controller's data out; the LCD has none
    TOUCH_IRQ      = 21     # XPT2046 PENIRQ, active low; T_CS is EXP_TOUCH_CS
    # The buttons are on the expander, not on GPIOs.
    EXPANDER = True
    BTN_HOME = BTN_A = BTN_B = BTN_C = None
    BTN_UP = BTN_DOWN = BTN_LEFT = BTN_RIGHT = None
    # I2C: AW9523B 0x58 and MPU-6050 0x69 (AD0 high), 2.2 kΩ pull-ups
    I2C_SDA   = 6
    I2C_SCL   = 7
    EXP_ADDR  = 0x58
    EXP_INT   = 3           # AW9523B ~INT, active low, RTC GPIO: wakes the badge
    IMU_INT   = 4
    # MAX98357A; its SD_MODE is EXP_AMP_EN on the expander
    I2S_BCLK  = 8
    I2S_LRCLK = 9
    I2S_DOUT  = 10
    # J6 expansion header: 3V3, GND, then these, in this order
    EXPANSION = (5, 41, 42, 47)

# AW9523B pins (PCB only). Port 0 bit n is the button EXP_BUTTON_ORDER[n]
# names; port 1 holds the rest.
EXP_BUTTON_ORDER = ("UP", "DOWN", "LEFT", "RIGHT", "A", "B", "C", "HOME")
EXP_LED_BITS   = 0x0F       # P1_0-P1_3: corner LEDs TL, TR, BL, BR (LED mode only)
EXP_AMP_EN     = 1 << 4     # P1_4: high turns the speaker amp on
EXP_SD_DET     = 1 << 5     # P1_5: low when a card is in
EXP_AUX_ON_N   = 1 << 6     # P1_6: low powers the IR receiver and status LED
EXP_TOUCH_CS   = 1 << 7     # P1_7: the touch controller's chip select, active low

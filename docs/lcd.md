# LCD — SmartElex 2.0" IPS TFT (ST7789P3)

Canonical reference for the Lix badge display. If anything here disagrees with
`BREADBOARD_BOM.md` or memory, **this file wins** — it reflects the actual module
datasheet we ordered.

## Module specs

| | |
|---|---|
| Driver IC      | ST7789P3 |
| Resolution     | 240 × 320 (portrait, RGB) |
| Color depth    | 262K colors (we'll drive it as RGB565 = 65K) |
| Active area    | 30.6 × 40.8 mm |
| Module size    | 34.6 × 47.8 × 2.05 mm |
| Interface      | 4-wire SPI (write-only — no MISO/SDO) |
| Backlight      | 3 white LEDs, single EN pin (active-high, PWM-capable) |
| Logic level    | 3.3V (panel I/O), 5V tolerant on power input via onboard LDO |
| Max SPI clock  | 62.5 MHz (we use 40 MHz on breadboard for noise margin) |
| Operating temp | -20°C to +70°C |

## Pin map (display ↔ ESP32-S3-DevKitC-1-N16R8)

| Display silkscreen | Function | DevKit pin | Our name in `lix_hw/pins.py` |
|---|---|---|---|
| **VCC** | Power input (3.3–5V) | **5V** | — |
| **GND** | Ground | GND | — |
| **EN**  | Backlight enable (HIGH = on) | **GPIO17** | `DISPLAY_BL` |
| **DC**  | Data/Command select | **GPIO15** | `DISPLAY_DC` |
| **SCL** | SPI clock | **GPIO12** | `DISPLAY_SCK` |
| **SDA** | SPI data MCU→panel | **GPIO11** | `DISPLAY_MOSI` |
| **CS**  | Chip select (LOW = listening) | **GPIO14** | `DISPLAY_CS` |
| **RST** | Reset (LOW pulse on boot) | **GPIO16** | `DISPLAY_RESET` |
| **TE**  | Tearing Effect (vsync) | **— leave open** | unused |

Total: **9 wires from the display**, 7 connected, 2 (TE + the absent MISO) skipped.

## Why VCC is 5V on this module specifically

The board has an onboard **AMS1117-3.3** linear regulator that takes 3.3–5V in
and outputs 3.3V to the ST7789P3. With ~1.1V dropout, feeding 3.3V to VCC
would leave the panel at ~2.2V — marginal/unreliable. Feed 5V and the panel
sees a clean 3.3V. Logic pins from the ESP32 stay at 3.3V — within the panel's
input spec, no level shifting needed.

(The BOM's original "VCC to 3V3 not 5V" line was wrong for this specific
module and has been corrected. Other ST7789 modules without an onboard LDO
*are* 3V3-native; always check before applying advice across boards.)

## Pre-flight checklist before powering on

- [ ] VCC traced from display VCC pin to DevKit 5V pin (not 3V3, not Vin via barrel jack)
- [ ] GND common with everything else on the breadboard
- [ ] All 4 SPI/control wires (CS, DC, SCL/SCK, SDA/MOSI) kept **short and bundled** — long jumpers cause flicker/garbage at 40 MHz
- [ ] RST and EN wires can be routed loosely (they're not clocked)
- [ ] TE pin left floating
- [ ] Multimeter resistance 5V↔GND: should read kΩ+, not a few ohms

## Common failure modes

| Symptom | Likely cause |
|---|---|
| Backlight on but only white screen (no init) | RST or DC miswired, or SPI clock too high |
| Backlight off entirely | EN not wired or stuck low; VCC not getting 5V |
| Random pixel garbage / flicker | SPI wires too long → drop SPI baud, shorten wires |
| Image upside-down or mirrored | `MADCTL` register value — fix in driver init, not wiring |
| Tearing / partial-frame visible | TE pin unused = expected; not actually a bug for our use case |
| Colors swapped (R↔B) | `COLMOD` set to BGR instead of RGB — fix in driver init |

## Open questions

- Whether to wire **EN** to a real GPIO or just to 3V3 (always-on backlight). Currently using GPIO17 so we get PWM brightness control later. If GPIO17 ever gets reclaimed for something else, jumper EN to 3V3 instead.
- PCB phase: replace AMS1117 with a low-Iq LDO (e.g. AP2112) to extend battery life.

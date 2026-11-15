# Oreo badge hardware

The Oreo Badge is certified open source hardware by the Open Source Hardware
Association, UID [IN000107](https://certification.oshwa.org/in000107.html). The design is licensed under
CERN-OHL-P-2.0 (see `LICENSE` in this directory).

This KiCad 10 project is the PCB successor to the ESP32-S3 DevKitC
breadboard: a 4-layer, 88 x 133.5 mm board, fully routed. The root
schematic, `elixpo.kicad_sch`, links five sheets:

1. ESP32-S3-WROOM-1-N16R8 module, reset and boot, debug pads.
2. USB-C, BQ24074 Li-ion power-path charger, battery sense and TPS63031 3.3 V rail.
3. 2.8 inch ILI9341 SPI display module header and the eight buttons.
4. AW9523B I2C expander, the I2C bus, corner and edge LEDs.
5. MAX98357A speaker amp, MPU-6050, RTC, microSD, infrared, status LED and Qwiic.

Run `./circuit/elixpo/build.sh` from any directory to regenerate the design and
produce the ERC report, PDF and KiCad-native BOM under `circuit/elixpo/build/`.

`BOM_PROCUREMENT.csv` is the sourcing-oriented BOM. `BOM_PRELIMINARY.csv` is a
flat engineering export that is regenerated directly from the schematic model.
`BOM_ORDER.csv` is the shopping list (see Assembly below).

## Pin map

| GPIO | Net | GPIO | Net |
|---|---|---|---|
| 0 | BOOT button | 21 | TOUCH_IRQ (display touch) |
| 1 | VBAT_SENSE (ADC) | 38 | SD_CLK |
| 2 | IR_TX | 39 | SD_CMD |
| 3 | EXP_INT (AW9523B, RTC GPIO: wakes the badge) | 40, 41, 42, 47 | SD_D0, D1, D2, D3 |
| 4 | IMU_INT | 43, 44 | UART TX, RX (debug pads) |
| 5 | RTC_INT | 45, 46 | strapping pins, unused |
| 6, 7 | I2C SDA, SCL | 48 | STATUS_LED (WS2812B) |
| 8, 9, 10 | I2S BCLK, LRCLK, DIN | 11, 12, 13 | LCD MOSI, SCK, MISO (touch only) |
| 14, 15, 16, 17 | LCD CS, DC, RESET, backlight | 18 | IR_RX |
| 19, 20 | native USB D-, D+ | 35-37 | in-module octal PSRAM |

On the AW9523B (0x58): P0_0-P0_7 are UP, DOWN, LEFT, RIGHT, A, B, C,
HOME; P1_0-P1_3 sink the corner LEDs (TL, TR, BL, BR); P1_4 AMP_EN,
P1_5 SD_DET, P1_6 spare, P1_7 the touch controller's chip select. Other
I2C devices: RV-3028 0x52, MPU-6050 0x69 (AD0 tied to its VLOGIC pin;
`oreoWare/imu.py` tries 0x68, then 0x69).

This differs from the breadboard's `oreoWare/pins.py` (buttons on GPIOs,
SD on 38-40, the amp on 41/21/46): the expander freed the button pins, so
the PCB regroups them. The OS needs a matching pin map, an ILI9341 driver,
a touch driver and the expander button driver (#154) before it runs on
this board.

## Electrical decisions

- 4 layers, JLCPCB JLC04161H-7628 (1.6 mm): F signal / In1 solid GND /
  In2 signal with a 3.3 V pour / B signal.
- U1 is the ESP32-S3-WROOM-1-N16R8 module (16 MB flash, 8 MB octal PSRAM),
  its PCB antenna over a keep-out on every layer at the top edge.
- Native USB uses GPIO19/GPIO20, 22 ohm series resistors, Type-C 5.1 kohm Rd
  resistors and a dedicated low-capacitance ESD array.
- BQ24074 keeps the system powered while charging. The current design targets
  about 445 mA charge current, about 800 mA input limit, about 50 mA
  termination current, and a 6.3-hour safety timer (all JLCPCB basic resistor
  values). These values must be checked against the selected cell before
  production. The battery level comes from the R17/R18 divider on GPIO1 (ADC).
- The main 3.3 V rail is buck-boost regulated so the badge remains stable over
  the full Li-ion discharge curve. The display module runs from 3.3 V and
  switches its own backlight. The speaker amp runs from VSYS.
- microSD is on its own 4-bit SDMMC bus, so the display keeps the whole SPI
  bus for video.
- GPIO45 and GPIO46 are deliberately unused because they are boot strapping
  pins. GPIO0 has a dedicated BOOT switch and EN has the recommended
  10 kohm/1 uF reset network.

## Before ordering and on the first boards

- Check the display module's header order against J3, and the battery
  lead's polarity against J2.
- Confirm the selected LiPo capacity, protection board and maximum permitted
  charge current (#156).
- Review the ESP32-S3 RF layout against Espressif's current hardware guide;
  tune the antenna network on assembled boards with a VNA.
- Replace the MPU-6050 only if its successor driver is added to OreoOS first.
- Treat this as an engineering prototype, not a production-certified charger
  or RF design, until bring-up and compliance testing complete.

## Display mounting

The display is a 2.8 inch 240x320 ILI9341 SPI module of the LCDwiki MSP2807
type (86 x 50 mm, with XPT2046 resistive touch and its own regulator and
backlight transistor). It sits landscape on the front, under the name card,
with its 14-pin 2.54 mm header in J3 (a hand-soldered socket) on the right
and its four M3 holes on 11 mm standoffs in H1-H4. LED (pin 8) is a logic
input, so GPIO17 drives and dims the backlight directly. Touch shares the
display's SPI bus, with T_CS on the expander's spare pin (EXP_P17) and
T_IRQ on GPIO21.

Before soldering J3, check that the module's header reads VCC, GND, CS,
RESET, DC, SDI, SCK, LED, SDO, T_CLK, T_CS, T_DIN, T_DO, T_IRQ from pin 1:
clones differ.

## Assembly

JLCPCB assembles the basic-library parts (all on the back); everything
else is bought and hand-soldered, as `BOM_ORDER.csv` sets out, including
the through-hole parts: the eight 6 mm buttons, J3, and the IR receiver. The
corner LEDs D1-D4 on the front stay SMD; each has two more on the back's
corner curve (D30-D37), in parallel on the same AW9523B channel.

`python3 export_jlcpcb.py` writes the order files: the Gerber zip, and a
JLCPCB assembly BOM and placement list in `build/jlcpcb/` that hold only
parts from JLCPCB's basic library (no extended-part fees; all on the back,
so assembly is single-sided). `BOM_ORDER.csv` lists everything a badge
needs: what JLCPCB fits, the SMD and through-hole parts to buy and solder
by hand (the exposed-pad chips need a stencil and hot air or a hot plate),
and the off-board parts, with LCSC numbers and prices.

The battery sits on the back in a 3D-printed L-shaped holder: it runs the
cell's 50 mm edge, is as tall as the cell (6 mm) and has a 10-12 mm lip over
it. Its foot is drawn on the back silkscreen under the cell and fixes with
two M2 screws in H5-H6; the dashed line shows how far the lip reaches.

## Motion sensor orientation

U7 (MPU-6050) is on the back, unrotated, so seen from the front its +X
points to the left of the screen, +Y up the screen and +Z into the badge,
the frame oreoWare/imu.py and oreoWare/pins.py assume.

## Contributing

Open work is labelled
[hardware](https://github.com/elixpo/oreo/issues?q=is%3Aopen+label%3Ahardware),
and new ideas go in the
[hardware issue form](https://github.com/elixpo/oreo/issues/new?template=hardware.yml).
In short:

- Change the schematic by changing `generate_badge_schematic.py`, then run
  `build.sh` and commit what it writes. Edits made only in the schematic
  editor are lost on the next run.
- The board is built by scripts, run with `/usr/bin/python3` (KiCad's
  pcbnew): `generate_badge_pcb.py` places the parts, draws the outline and
  the silkscreen; `route_badge_pcb.py` routes with Freerouting;
  `finish_badge_pcb.py` adds ground stitching and closes the last gaps;
  `tighten_regulator.py` packs the 3.3 V regulator. Running
  `generate_badge_pcb.py` again discards the routing, so small changes to a
  routed board go in with a script or by hand in KiCad.
- `wire_side_schematics.py` draws the wired front and back schematics, and
  `export_jlcpcb.py` writes the order files.
- CI (`.github/workflows/hardware.yml`, KiCad 10.0.5) fails if the committed
  schematic differs from the generator, if ERC reports anything, or, once
  the board has footprints, if DRC or schematic parity fails. Its artifact
  holds the schematic PDF, the BOM and the reports.
- A pin change also changes `oreoWare/pins.py`, the drivers and
  `docs/HARDWARE.md` in the same pull request.

The full guide is the
[hardware section of CONTRIBUTING.md](../../CONTRIBUTING.md#work-on-the-hardware).

## Licence

The hardware design files in this directory are Open Hardware, licensed under
the [CERN Open Hardware Licence v2 - Permissive](../../LICENSES/preferred/CERN-OHL-P-2.0)
(CERN-OHL-P-2.0); see [`LICENSE`](LICENSE) for the notice. You may make,
modify and sell boards from them; the Elixpo and Oreo names and mascot are
trademarks, so derived boards need their own names (see
[`TRADEMARKS.md`](../../TRADEMARKS.md)).

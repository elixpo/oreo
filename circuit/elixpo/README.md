# Oreo badge hardware

The Oreo Badge is certified open source hardware by the Open Source Hardware
Association, UID [IN000107](https://certification.oshwa.org/in000107.html). The design is licensed under
CERN-OHL-P-2.0 (see `LICENSE` in this directory).

This KiCad 10 project is the bare-chip successor to the ESP32-S3 DevKitC
breadboard. The root schematic, `elixpo.kicad_sch`, links four detailed sheets:

1. ESP32-S3R8 core, 16 MB external flash, 40 MHz clock and 2.4 GHz RF network.
2. USB-C data/power, BQ24074 Li-ion power-path charger and TPS63031 3.3 V rail.
3. 2.8 inch ILI9341 SPI display module header, buttons, corner and edge LEDs.
4. MPU-6050, exact-capture IR path, WS2812 status LED, microSD and expansion.

Run `./circuit/elixpo/build.sh` from any directory to regenerate the design and
produce the ERC report, PDF and KiCad-native BOM under `circuit/elixpo/build/`.

`BOM_PROCUREMENT.csv` is the sourcing-oriented BOM. `BOM_PRELIMINARY.csv` is a
flat engineering export that is regenerated directly from the schematic model.

## Electrical decisions

- U1 is `ESP32-S3R8`: 8 MB octal PSRAM is inside the package. GPIO33–GPIO37
  are therefore unavailable and are explicitly marked as internal connections.
- U2 is an external 16 MB, 3.3 V quad-SPI flash matching the tested N16R8
  prototype capacity.
- Native USB uses GPIO19/GPIO20, 22 ohm series resistors, Type-C 5.1 kohm Rd
  resistors and a dedicated low-capacitance ESD array.
- BQ24074 keeps the system powered while charging. The current design targets
  about 445 mA charge current, about 800 mA input limit, about 50 mA termination
  current, and a 6.3-hour safety timer (all JLCPCB basic resistor values). These values must be checked against
  the selected cell before production.
- The main 3.3 V rail is buck-boost regulated so the badge remains stable over
  the full Li-ion discharge curve. The display module runs from 3.3 V and
  switches its own backlight.
- microSD shares the LCD clock/MOSI lines and uses GPIO43 as CS and GPIO44 as
  MISO. Firmware must arbitrate the two devices and keep both chip-select lines
  inactive while the other device owns the bus.
- GPIO45 and GPIO46 are deliberately unused because they are boot strapping
  pins. GPIO0 has a dedicated BOOT switch and CHIP_PU has the recommended
  10 kohm/1 uF reset network.

## Before PCB layout

- Bring the schematic in line with the breadboard (#106): microSD on its
  own SDMMC bus (GPIO38/39/40) instead of the LCD's SPI bus, and the
  MAX98357A I2S amplifier (GPIO41/21/46) powered from VSYS. The corner LEDs
  that held GPIO38–41 move to the I2C GPIO expander.
- Add the I2C GPIO expander for the eight buttons, the corner LEDs and the
  touch pad (#102), with its interrupt on a freed GPIO.
- Freeze the exact display module and battery connector orientation.
- Confirm the selected LiPo capacity, protection board, NTC curve and maximum
  permitted charge current.
- Review the ESP32-S3 RF layout against Espressif's current hardware guide;
  tune the antenna network on assembled boards with a VNA.
- Replace the MPU-6050 only if its successor driver is added to OreoOS first.
- Confirm every regulator inductor, capacitor DC-bias curve and thermal margin.
- Treat this as an engineering prototype, not a production-certified charger
  or RF design, until layout review, bring-up and compliance testing complete.

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
- Lay out the PCB by hand in `elixpo.kicad_pcb`.
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

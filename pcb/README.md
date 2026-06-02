# Oreo Badge — PCB

Hardware design for the Oreo Badge v1 prototype. KiCad-native; everything
in this folder is the source-of-truth for the physical board.

```
pcb/
├── README.md             this file
├── BOM.md                full bill of materials with rationale
├── badge.kicad_pro       KiCad project (added once schematic starts)
├── badge.kicad_sch       schematic
├── badge.kicad_pcb       PCB layout
├── badge-cache.lib       project-local symbol cache
├── gerbers/              fab-ready Gerber outputs (gitignored)
└── manufacturing/        BOM CSV + CPL + assembly drawings for JLCPCB
```

---

## 🎯 Design goals

| Goal | Why |
|---|---|
| **2-layer PCB** | Cheapest fab tier ($5/5pcs at JLCPCB); plenty for this design. |
| **Bare ESP32-S3-WROOM-1 module** | Pre-certified RF (no FCC headaches), but skip the breakout board scaffolding. |
| **Native USB on ESP32-S3 PLUS CH340 bridge** | Two paths to flash & debug — survives the inevitable native-USB driver weirdness. |
| **LiPo + USB power-path** | Charge-while-running, no awkward unplug-to-charge UX. |
| **Conference-badge form factor** | ~80×50 mm, lanyard cutout in the corner, screen edge-aligned. |
| **Hand-solderable bring-up + SMT-assemblable final** | 0402 minimum for passives; everything reflowable for production. |

---

## 🔌 Block diagram

```
  ┌─────────┐                               ┌──────────────┐
  │  USB-C  │──┬──── CC1/CC2 pull-down ────│ ESD + polyfuse│
  └─────────┘  │                             └──────┬───────┘
               │                                    │ VBUS
               │   ┌──────────────────────────┐     │
               ├──→│  CH340N USB→UART bridge  │←────┤  5 V
               │   └──────┬─────────┬─────────┘     │
               │          │RX       │TX             │
               │          ▼         ▼               │
   D+/D- ──────┴────→  ESP32-S3 native USB          │
                            │  GPIO 19/20            │
                            │                        │
                            │   ┌──────────────┐    │
                            │   │ TP4056 LiPo  │←───┤
                            │   │   charger    │    │
                            │   └──┬───────────┘    │
                            │      │ VBAT             │
                            │      ▼                 │
                            │   ┌──────────────┐    │
                            │   │ Power-path / │←───┤
                            │   │   ORing      │    │
                            │   └──┬───────────┘    │
                            │      │ V_SYS           │
                            │      ▼                 │
                            │   ┌──────────────┐    │
                            │   │ AP2112 LDO   │    │
                            │   │  3.3 V 600mA │    │
                            │   └──┬───────────┘    │
                            │      │ 3V3             │
                            ▼      ▼                 │
                    ┌────────────────────┐           │
                    │ ESP32-S3-WROOM-1   │           │
                    │   N16R8 module     │           │
                    │  ┌──────────────┐  │           │
                    │  │ SPI: ST7789  │  │           │
                    │  │ I²C: MPU6050 │  │           │
                    │  │ GPIO: 8 btns │  │           │
                    │  │ GPIO: IR T/R │  │           │
                    │  │ GPIO: RGB    │  │           │
                    │  │ ADC: VBAT/2  │  │           │
                    │  └──────────────┘  │           │
                    └────────────────────┘           │
                            ▲                        │
                            │   GND plane            │
                            └────────────────────────┘
```

---

## 📐 Stackup

**2-layer, 1.6 mm FR-4, 1 oz/ft² copper, ENIG finish.**

| Layer | Use |
|---|---|
| **F.Cu** (top) | Signal routing + components |
| **B.Cu** (bottom) | GND pour + signal escape routes + small components if needed |

**Why 2 layers, not 4:** USB-FS (12 Mbps) is comfortably routable on 2 layers
with a ground pour underneath. The WROOM-1 module handles all the RF
internally, so no buried impedance-controlled stripline is needed. The
cost delta to 4 layers (~2.5× at JLCPCB) buys nothing for this design.

**Stitching vias:** ≥ 20 vias around the board perimeter and underneath
the WROOM-1 antenna keep-out zone. These tie F.Cu's GND pour to B.Cu's
GND pour — without them, the ground return path for high-frequency
signals goes the long way around and you get radiated emissions.

---

## 🧠 Critical layout rules

These are the "do them now or pay later in rework" rules. Each one comes
from a real bring-up failure on previous badge projects.

### 1. WROOM-1 antenna keep-out

The module's PCB antenna is at one corner. **No copper (signal or pour),
no components, no vias** within ~14×6 mm of the antenna corner — even on
the back layer. Check the WROOM-1 datasheet for the exact keep-out
rectangle. Violating this kills your WiFi range from ~40 m to ~3 m.

### 2. Decoupling cap layout

Every 100 nF decoupling cap (C1×4) goes **directly under the WROOM-1's VDD
pin on the bottom layer**, with one via to VDD and one via to GND. The
loop area between pin → cap → ground via → ground plane → pin must be
under 10 mm². This is more important than the cap value.

### 3. USB differential pair

USB D+ / D- routed as a **differential pair**, 90 Ω impedance, length-matched
to within 5 mm. Place R_USB_TX / R_USB_RX (22 Ω each) close to the CH340
side, not the USB-C side. Use ESD diodes (U8) close to the connector,
NOT close to the chip — the ESD energy needs somewhere to dump before it
travels.

### 4. Power-path / charge isolation

The TP4056 SHOULD NOT see USB VBUS when it's not actively charging — leakage
through the BAT pin drains the LiPo over months. Either use a real
power-path IC (TPS2113A) or add a Schottky diode in series with VBUS so
charge stops cleanly when USB is unplugged.

### 5. EN pin RC filter

R_EN (10 kΩ to 3V3) + C6 (100 nF to GND) on the EN pin. **Without this**,
the ESP32-S3 enters bootloader mode randomly on power-up. The RC creates
a deterministic reset slope.

### 6. CC pull-downs on USB-C

R_CC1 + R_CC2 (5.1 kΩ to GND, one per CC pin). **Without these, USB-C-only
laptops won't power your board** — they default to no current until a CC
pull-down tells them it's a device. The single most common "why won't it
power on?" issue.

### 7. BAT voltage divider impedance

R_BAT_DIV uses 100 kΩ + 100 kΩ. Higher impedance = less idle current
drain (~21 µA), but too high and the ESP32-S3 ADC sample-and-hold can't
charge fast enough. 100 kΩ is the sweet spot. **Don't go above 200 kΩ.**

### 8. Mounting holes

Four mounting holes — M2 or M2.5, brass standoff. **Connect each to
GND** if you'll ever attach an enclosure with metal screws; otherwise
they're an ESD funnel from the user's hand to your signals.

---

## 🔢 Pin assignments (firmware-locked)

Pins below are already referenced by `oreoWare/pins.py` in the firmware.
**Don't reassign without updating both sides.**

| GPIO | Net | Notes |
|---:|---|---|
| 0 | BOOT strap | Tactile to GND |
| 3 | WS2812B DIN | 4 corner LEDs daisy-chained — 470 Ω series at GPIO side |
| 4 | IR RX | From VS1838B output |
| 5 | IR TX | To 2N7002 gate |
| 6 | LCD CS | ST7789 SPI chip-select |
| 7 | LCD DC | Data/command |
| 8 | LCD RST | Reset |
| 9 | LCD backlight PWM | LCD module BL pin — driven open-drain by ST7789 module's FET |
| 10 | LCD MOSI | SPI MOSI |
| 11 | LCD SCK | SPI clock |
| 12 | I²C SDA | **Shared bus**: MPU-6050 (0x69) + DS3231 (0x68) |
| 13 | I²C SCL | Same bus |
| 14 | VBAT_ADC | Battery monitor (1:1 divider) |
| 15-18 | BTN_UP / DOWN / LEFT / RIGHT | Tactile to GND |
| **16** | **LDR_ADC** | Ambient light sense (GL5528 + 10 kΩ divider) — *replaces BTN_RIGHT if a conflict — confirm against `oreoWare/pins.py`* |
| 21 | BTN_A | |
| 33 | BTN_B | |
| 34 | BTN_C | |
| 35 | BTN_HOME | |
| **36** | **I²S BCLK** | MAX98357A bit-clock |
| **37** | **I²S LRCLK** | Word-select |
| **38** | **I²S DIN** | Audio data |
| 19 | USB D- | Native USB |
| 20 | USB D+ | Native USB |
| EN | Reset | Tactile to GND + RC |

⚠ **Pin 16 conflict check** — GPIOs 15-18 were already labelled as the
D-pad. Reassign LDR to a free pin (38 freed up too, or use 39/40)
before the layout locks. The firmware's `oreoWare/pins.py` is the
arbiter; update it in the same commit as the schematic to keep them in
sync.

Pins 26-32 are reserved on WROOM-1 (octal-SPI flash/PSRAM) — don't use
even if KiCad lets you.

---

## 🛠 KiCad setup

```bash
# Install KiCad 8 (already standard on most distros)
sudo apt install kicad kicad-symbols kicad-footprints kicad-templates

# Open the project once it exists
kicad pcb/badge.kicad_pro
```

**Footprint libraries you'll need beyond stock:**
- `Espressif-ESP32-S3-WROOM-1` — Espressif's official KiCad symbols/footprints
- `WCH-Symbols` — for CH340N
- `JLCPCB-LCSC` — auto-aligns with LCSC C-numbers for assembly

Add via KiCad → Preferences → Manage Symbol Libraries.

---

## 🏭 Fab + assembly

**JLCPCB** is the obvious first stop:

```
Board:
  - 2 layers, 1.6 mm FR-4, 1 oz Cu
  - ENIG finish (gold pads; better for hand-soldering than HASL)
  - Black or white soldermask (matches OS theme)
  - White silkscreen on black mask
  - Gold fingers: no
  - Castellated holes: no

SMT assembly:
  - "Basic" + "Extended" parts as in BOM.md
  - Top side only (cheaper)
  - Confirm tombstoning prevention for 0402s with their reviewer
```

Expected cost: **~$15 for 5 boards bare, ~$40-60 for 5 boards fully
assembled** depending on extended-parts count. Bring-up before ordering
20+.

---

## 📋 Bring-up checklist

When the first board arrives:

1. **Visual inspection** — no solder bridges, no missing parts, no
   tombstoned 0402s. 10× loupe minimum.
2. **Smoke test** — plug USB. **Read 5 V on VBUS, 3.3 V on the LDO output,
   and 0 V everywhere else.** If 3V3 is missing → LDO or input cap
   issue. If 3V3 is droopy → check polyfuse rating.
3. **Idle current** — should be under 100 mA without WiFi. If higher,
   look for short circuits or stuck pull-ups.
4. **Flash bring-up** — hold BOOT, tap RST, release BOOT. Computer should
   enumerate as either a CH340 serial port (via CH340N) or as a USB-CDC
   device (via native USB). If neither, check USB enumeration with
   `lsusb` — see if it's even being detected.
5. **Run a minimal MicroPython REPL** — flash `micropython.bin` via
   `esptool.py`, then connect at 115200 baud. `print("hello")` confirms
   life.
6. **Display test** — wire the ST7789 ribbon, run `oreoWare.display.smoke_test()`.
7. **WiFi test** — `wifi.connect_from_config()`. Range test at 2 m / 5 m / 10 m
   to confirm antenna keep-out wasn't violated.
8. **Battery charge test** — plug LiPo, watch CHRG LED. Pull USB,
   confirm board stays alive on battery. Plug USB again, confirm
   transition is glitchless.

---

## 📚 Reference

- [ESP32-S3-WROOM-1 datasheet](https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf)
- [ESP32-S3 hardware design guidelines](https://www.espressif.com/sites/default/files/documentation/esp32-s3_hardware_design_guidelines_en.pdf) — **read sections 2 + 3 before laying out**
- [CH340N datasheet](http://www.wch-ic.com/downloads/CH340DS1_PDF.html)
- [AP2112 datasheet](https://www.diodes.com/datasheet/download/AP2112.pdf)
- [TP4056 datasheet](https://dlnmh9ip6v2uc.cloudfront.net/datasheets/Prototyping/TP4056.pdf)
- [JLCPCB capabilities](https://jlcpcb.com/capabilities/Capabilities)
- KiCad pad-to-pad rules: stock 6 mil clearance is fine for everything here.

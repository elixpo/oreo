# Oreo Badge — PCB Bill of Materials

**Revision:** v1 prototype
**Stackup:** 2-layer, 1.6 mm FR-4, ENIG or HASL finish
**Target fab:** JLCPCB / PCBWay (LCSC sourcing in part numbers below)
**Module:** ESP32-S3-WROOM-1-N16R8 (16 MB flash, 8 MB octal-PSRAM, pre-certified)

All passive values assume an ESP32-S3 module with **2.4 GHz WiFi + BLE active**,
**LCD backlit at full brightness**, and **LiPo charge-while-running**. Cap
counts are the *minimum* — don't substitute smaller bulks unless you've
measured your supply with a scope.

---

## 🔌 U — Active components (ICs / modules)

| Ref | Part | Package | Qty | Function | Notes |
|---|---|---|---:|---|---|
| **U1** | ESP32-S3-WROOM-1-N16R8 | Module 18×25.5 mm | 1 | MCU + WiFi + BLE + flash + PSRAM | Use the **N16R8** variant — matches firmware memory layout. Pre-certified module; no antenna/matching needed. |
| **U2** | CH340N | SOP-8 (auto-3V3/5V) | 1 | USB → UART bridge for serial console | Auto-detects logic level. Avoids the ESP32-S3 native-USB quirks during bring-up. |
| **U3** | AP2112K-3.3 | SOT-23-5 | 1 | 3.3 V LDO, 600 mA, low dropout | Low-noise — important so WiFi TX bursts don't visibly modulate the display. Output cap MUST be ≥ 1 µF ceramic. |
| **U4** | TP4056 | SOP-8 | 1 | LiPo charge controller, 1A | Standard hobby part. Use a programming resistor to set the charge current (see R section). |
| **U5** | DW01A + FS8205A | SOT-23-6 / SOT-23-6 | 1 ea | LiPo over-discharge / overcurrent / short-circuit protection | Skip ONLY if your battery already has an integrated protection PCM (most do). Confirm on the cell datasheet. |
| **U6** | MPU-6050 (or MPU-6500) | QFN-24 4×4 mm | 1 | 6-axis IMU (accel + gyro) | Matches firmware memory. **AD0 pin tied to 3V3** → I²C addr **0x69** to avoid conflict with the DS3231 RTC (which is hard-wired to 0x68). Decoupling caps mandatory. |
| **U9** | DS3231SN | SOIC-16 | 1 | High-accuracy I²C RTC with integrated TCXO (±2 ppm) | Keeps time across reboots and during sleep. Fixed I²C addr **0x68** — that's why U6's AD0 is pulled high. Backup powered from coin cell (BAT2 below). |
| **U10** | GL5528 photoresistor (LDR) | Radial 5 mm | 1 | Ambient light sense → auto backlight + corner-LED dimming | 8-20 kΩ bright / 1 MΩ dark. Forms a divider with R_LDR (10 kΩ) feeding an ADC pin. |
| **U7** | ST7789V LCD module | 2.0" / 2.4" IPS, 320×240 | 1 | Display | Buy as a bare module with FFC ribbon — far easier than spinning a separate panel design. Tape-down to the rear cutout. |
| **U8** | PESD5V0S1UL | SOD-323 | 2 | USB-C ESD protection (D+ / D-) | One per data line. Mandatory if conference attendees will touch the port. |
| **D1** | SS14 or 1N5819 | SMA | 1 | USB-VBUS reverse-polarity / power-path diode | Optional if using TPS2113A power-path; required for the cheap P-MOSFET path. |

---

## 🔋 BAT — Battery + connector

| Ref | Part | Spec | Qty | Notes |
|---|---|---|---:|---|
| **J_BAT** | JST-PH 2.0 mm 2-pin | Right-angle or SMT | 1 | Standard hobby-LiPo connector. Wire colour: red = +, black = − (verify before plug). |
| **BAT1** | LiPo 503450 (or similar) | 500–800 mAh, 3.7 V nominal | 1 | Sweet spot for ~4-6h active / weeks standby on a badge. Prefer cells with **built-in protection PCM** so you can skip U5. |
| **BAT2** | CR1220 coin cell + holder | SMT through-hole holder, ~12 mm | 1 | RTC backup — keeps DS3231 ticking when the main LiPo dies. ~5 year shelf life. CR1220 chosen over CR2032 to save weight (1 g vs 3 g on the lanyard). |

---

## 🔌 J — Connectors + switches

| Ref | Part | Footprint | Qty | Notes |
|---|---|---|---:|---|
| **J1** | USB Type-C receptacle, 16-pin | Mid-mount SMT | 1 | 16-pin variant (no Alt Mode) is fine for USB-FS. Add the 5.1 kΩ pull-downs on CC1/CC2 below. |
| **J2** | FFC connector | 8-pin or 14-pin matching LCD ribbon | 1 | Match to the U7 module's ribbon spec. |
| **J3** | Tag-Connect TC2030 footprint (no connector) | Hand-pads | (1 footprint) | For one-shot JTAG flash if USB ever bricks. Cost: 6 pads on the PCB. |
| **SW_BOOT** | Tactile 6×6 mm SMT | SMT | 1 | GPIO 0 strap — held LOW at reset enters download mode. |
| **SW_RST** | Tactile 6×6 mm SMT | SMT | 1 | Pulls EN to GND. |
| **SW1…SW8** | Tactile 6×6 mm SMT | SMT | 8 | UP / DOWN / LEFT / RIGHT / A / B / C / HOME — matches the firmware button matrix. |

---

## 🔊 Audio (wired headphones + on-board click)

Wireless A2DP isn't possible on ESP32-S3 (LE only — no BT Classic /
A2DP source). Going with **a wired 3.5 mm jack + I²S DAC** for proper
audio, plus a tiny piezo for system clicks that don't need headphones.

| Ref | Part | Footprint | Qty | Notes |
|---|---|---|---:|---|
| **U11** | MAX98357A or PCM5102A | SOIC-8 / TSSOP-14 | 1 | I²S DAC with built-in Class-D amp (MAX98357A is the simpler one — drives a small speaker or headphones at low impedance). Three GPIO: BCLK, LRCLK, DIN. |
| **J_AUDIO** | TRRS 3.5 mm jack, switched | SMT, side-entry | 1 | "Switched" means inserting a plug disconnects the on-board piezo automatically — saves a GPIO + no clicks in your ear when plugging in. |
| **SPK1** | Piezo buzzer 12 mm | SMT | 1 | Drives system sounds (boot chime, button clicks, IR-quest hits) when no headphones are plugged in. ~$0.20. Wire across the TRRS jack's normally-closed switch contacts. |

**Why no Bluetooth audio in v1:**
- ESP32-S3 has BT 5 LE only. A2DP requires BT Classic.
- BLE Audio (LE Audio + LC3 codec) is in the BT5 spec but virtually no
  headphones in the wild support it yet (only flagship 2023+ buds).
- An external BT Classic module (BM83 / KCX_BT_EMITTER) would work but
  adds $5-8, a chip, and a separate pairing UX. Deferred to v2.

---

## 💡 LED / IR

| Ref | Part | Footprint | Qty | Notes |
|---|---|---|---:|---|
| **LED_PWR** | Green SMD 0603 | 0603 | 1 | Power-on indicator. Series ~2.2 kΩ to keep < 1 mA idle. |
| **LED_CHRG** | Red SMD 0603 | 0603 | 1 | TP4056 charge indicator. |
| **LED_RGB1…4** | WS2812B-2020 addressable RGB | 2020 micro | **4** | The four corner "glow" LEDs — daisy-chained on a single data line from GPIO 3. **Brightness is software-modulated by the LDR reading** so the badge dims itself in a dark room. Place one in each PCB corner; the data line snakes around the perimeter. |
| **D_IR_TX** | IR LED 940 nm | 5 mm radial or SMD 0805 | 1 | IR Quest transmit. Drive via a 2N7002 N-MOSFET + 150 Ω series for ~30 mA pulses. |
| **U_IR_RX** | VS1838B or TSOP38238 | TO-92 / SMD | 1 | 38 kHz IR receiver. Add 100 nF decoupling + 100 Ω series on VCC per datasheet. |
| **Q1** | 2N7002 | SOT-23 | 1 | IR LED low-side switch. |

---

## ⚡ C — Capacitors

> **The single most important rule:** every 100 nF decoupling cap must be
> within **5 mm of the pin it's protecting**, with the shortest possible
> loop to GND. The number of caps matters less than the layout.

| Ref | Value | Package | Qty | Where it goes | Notes |
|---|---|---|---:|---|---|
| C1 | 100 nF X7R | 0402 / 0603 | 4 | One per WROOM-1 VDD pin (pins 2, 11, 24…) | Local decoupling. **Place under the module on the bottom layer, via straight up to VDD.** |
| C2 | 10 µF X7R | 0805 | 1 | 3V3 rail, near WROOM-1 | Mid-frequency bulk. |
| C3 | 22 µF X5R (or 47 µF polymer / tantalum) | 0805 / SMD-A | 1 | 3V3 rail, near WROOM-1 VDD pins | WiFi TX-burst reservoir. Low-ESR tantalum/polymer is better than ceramic here. |
| C4 | 10 µF X7R | 0805 | 1 | LDO **input** (U3 Vin) | Stops USB rail droop during WiFi peaks. |
| C5 | 1 µF X7R | 0603 | 1 | LDO **output** (U3 Vout) | AP2112 requires ≥ 1 µF for stability. |
| C6 | 100 nF | 0402 | 1 | EN pin (WROOM-1 pin 3) | Pairs with R_EN below for clean power-on reset. |
| C7 | 100 nF | 0603 | 1 | CH340N pin 5 (VCC) | Decoupling. |
| C8 | 4.7 µF | 0805 | 1 | CH340N VCC | Bulk. |
| C9 | 100 nF + 10 µF | 0603 / 0805 | 1 each | USB-C VBUS | Standard USB recommendation. |
| C10 | 10 µF | 0805 | 1 | TP4056 input (VCC) | Smooths USB during charge. |
| C11 | 10 µF | 0805 | 1 | TP4056 output (BAT) | Battery-side bulk. |
| C12 | 100 nF | 0603 | 1 | MPU-6050 VDD | Per datasheet. |
| C13 | 10 nF | 0402 | 1 | MPU-6050 VLOGIC | Per datasheet. |
| C14 | 100 nF | 0402 | 1 | DS3231 VCC | Per datasheet. |
| C15 | 100 nF | 0402 | 1 | DS3231 VBAT (coin-cell side) | Per datasheet. |
| C16 | 100 nF + 10 µF | 0402 / 0805 | 1 each | MAX98357A VDD | Class-D amp current spikes — bulk cap matters. |
| C17 | 1 µF | 0603 | 1 | Across the WS2812B chain VDD (close to chain start) | Stabilises the LED-string supply during all-bright frames. |
| C18 | 100 nF | 0402 | 1 | LDR voltage divider tap → GND | Filters fast flicker (camera flashes, fluorescent lights) before the ADC reads it. |

**Total caps: ~16-20 pieces.** Buy in 100-piece reels of 0402 100 nF and 0603 10 µF — cheap and you'll burn through them across prototype revisions.

---

## ⚙ R — Resistors

| Ref | Value | Package | Qty | Where | Why |
|---|---|---|---:|---|---|
| R_EN | 10 kΩ | 0402 | 1 | EN pin → 3V3 | Pull-up for proper reset behaviour. |
| R_BOOT | 10 kΩ | 0402 | 1 | GPIO 0 → 3V3 | Strap pin pull-up. |
| R_CC1, R_CC2 | 5.1 kΩ | 0402 | 2 | USB-C CC1, CC2 → GND | Identify the board as a USB device to USB-C hosts. **Without these, your USB-C-only laptop won't power the board.** |
| R_USB_TX, R_USB_RX | 22 Ω | 0402 | 2 | In series with USB D+ / D- (between CH340 and connector) | USB-FS termination. |
| R_TP4056_PROG | 1.2 kΩ | 0603 | 1 | TP4056 PROG pin | Sets charge current to **1 A**. For 500 mA charge, use 2.4 kΩ. **Match to battery capacity (rule of thumb: charge ≤ 1C).** |
| R_TP4056_LED | 1 kΩ | 0603 | 2 | TP4056 CHRG / STDBY LEDs | Current limit. |
| R_BAT_DIV | 100 kΩ × 2 | 0402 | 2 | Battery voltage divider → ESP32-S3 ADC pin | Brings 4.2 V max down to ~2.1 V into the ADC. Two equal resistors → 0.5× scale. |
| R_IR_TX | 150 Ω | 0805 (heat) | 1 | In series with IR LED | Limits current to ~30 mA peak. |
| R_IR_RX | 100 Ω | 0603 | 1 | In series with IR RX VCC | Per datasheet — isolates noise. |
| R_LED_PWR | 2.2 kΩ | 0603 | 1 | Power LED current limit | ~1 mA — visible, low idle. |
| R_LED_CHRG | 1 kΩ | 0603 | 1 | Charge LED current limit | |
| R_btns | 10 kΩ × 8 | 0402 | (optional) | One per button to 3V3 if you use external pull-ups | ESP32-S3 has internal pull-ups; you can skip these and save 8 parts. **Recommended: skip unless you have ESD concerns.** |
| R_AD0 | 10 kΩ | 0402 | 1 | MPU-6050 AD0 → 3V3 | Moves MPU to addr **0x69** so it doesn't collide with DS3231 at 0x68. |
| R_I2C_SDA, R_I2C_SCL | 4.7 kΩ | 0402 | 2 | I²C bus pull-ups | One pair shared by MPU-6050 + DS3231. Skip if the LCD ribbon already has them. |
| R_RTC_VBAT | 1 kΩ | 0402 | 1 | Coin-cell series resistor on DS3231 VBAT | Protects against an inserted-backwards coin cell. Optional but cheap. |
| R_LDR | 10 kΩ | 0402 | 1 | Lower half of GL5528 / 3V3 voltage divider | Brings the divider's tap-point into the ESP32-S3 ADC range across the LDR's full resistance swing. |
| R_WS2812B | 470 Ω | 0402 | 1 | Series resistor on the WS2812B data line | Damps reflections on the daisy-chain DIN net so the LEDs don't randomly glitch. **Place close to GPIO 3, not close to the first LED.** |
| R_I2S | 100 kΩ | 0402 | 1 | MAX98357A GAIN pin pulldown | Sets the amp gain to 12 dB. Different value = different gain step (see datasheet). |

---

## 🛡 F — Protection

| Ref | Part | Footprint | Qty | Notes |
|---|---|---|---:|---|
| F1 | Polyfuse 500 mA hold / 1 A trip | 1206 | 1 | On USB VBUS, before TP4056 + LDO. Resettable. **Protects against bad USB cables / shorts.** |
| TVS1, TVS2 | PESD5V0S1UL | SOD-323 | 2 | One per USB data line — see U8. |
| TVS3 | SMAJ5.0CA | SMA | 1 | Optional — across VBUS for surge protection. Skip if you trust the polyfuse + TP4056's internal protection. |

---

## 📡 Antenna (already inside WROOM-1)

**Nothing to add.** The ESP32-S3-WROOM-1 has an integrated PCB antenna and
matching network on the module. Your only job is to **keep the area near
the antenna corner of the module clear of ground pour and components** —
specifically the keep-out zone in the WROOM-1 datasheet (typically a
14×6 mm rectangle at one corner).

---

## 📐 Total parts count

| Category | Count |
|---|---:|
| ICs / modules | 11 (added DS3231, GL5528, MAX98357A) |
| Battery + connectors | 5 (added CR1220 holder, TRRS jack) |
| Switches | 10 |
| LEDs + IR | 8 (4 corner WS2812Bs + status + charge + IR TX/RX) |
| Audio | 2 (piezo, TRRS jack already counted above) |
| Capacitors | ~24-28 |
| Resistors | ~22-30 |
| Protection (fuses + TVS) | 3-4 |
| **Total** | **~85-100 unique placements** |

Still a reasonable count for a prototype badge. The RTC + corner LEDs +
audio added roughly 20 parts. Most are still 0402/0603 — manageable to
hand-solder but a stencil + reflow oven keeps you sane.

---

## 🛒 Quick BOM CSV (paste into JLCPCB / LCSC)

For the first prototype-order pass, the LCSC C-numbers below are
JLCPCB-stocked (so they assemble for free with their basic-parts SMT
service). Saves you from hand-placing the 60+ passives.

```csv
designator,quantity,manufacturer,part_number,lcsc_code,description
U1,1,Espressif,ESP32-S3-WROOM-1-N16R8,C2913201,SMD module
U2,1,WCH,CH340N,C506813,USB→UART bridge
U3,1,Diodes,AP2112K-3.3TRG1,C51118,3.3V LDO
U4,1,TPower,TP4056,C16581,LiPo charger
U6,1,InvenSense,MPU-6050,C19102,6-axis IMU
U8,2,Nexperia,PESD5V0S1UL,C8801,USB ESD
F1,1,Eaton,500mA polyfuse,C7888,polyfuse
SW_BOOT/RST/1-8,10,Generic,6x6mm tactile,C318884,buttons
J1,1,Generic,USB-C 16-pin,C165948,USB-C
J_BAT,1,JST,PH2.0 2-pin SMT,C273126,LiPo connector
```

(Resistors and caps: bulk from any 0402/0603 grab-bag. JLCPCB's basic
library has all standard values.)

---

## 🔬 Test points worth adding

Cheap insurance for bring-up debugging. Just bare 1 mm round pads with
silkscreen labels — costs nothing:

- **3V3** (power rail)
- **5V** (post-fuse VBUS)
- **VBAT** (battery raw)
- **GND** × 2 (one near each rail TP for short scope-probe loops)
- **GPIO 0 / EN** (strap pins, for debugging stuck-in-bootloader issues)

---

## ✅ Decisions locked for v1

- ✅ **RTC** — DS3231 (U9) + CR1220 coin cell (BAT2). MPU AD0 pulled high to free up addr 0x68.
- ✅ **Ambient light** — GL5528 LDR (U10) on GPIO 16 ADC. Modulates LCD backlight + corner-LED brightness in software.
- ✅ **Corner glow LEDs** — 4× WS2812B-2020, daisy-chained on GPIO 3. PCB-corner placement.
- ✅ **Audio out** — MAX98357A I²S DAC + TRRS jack + piezo buzzer (no wireless).
- ❌ **No haptic motor** — weight on the lanyard. Stays out.
- ❌ **No touch panel** — deferred. SPI pins reserved on the LCD bus if added later.
- ❌ **No wireless audio in v1** — ESP32-S3 lacks BT Classic; BLE Audio adoption too low. Revisit for v2 with external BT module.

## 🤔 Decisions still deferred (revisit before tape-out)

- [ ] **Touch pads etched into PCB silkscreen?** ESP32-S3 has native cap-touch. Could replace the C button or HOME button. Zero extra BOM.
- [ ] **External BT Classic module for v2 audio?** BM83, KCX_BT_EMITTER, or similar. ~$5-8.
- [ ] **APDS-9930 instead of LDR?** Proper lux readings + IR proximity, ~$1.50, I²C. Overkill unless you want gesture-wave-to-mute.
- [ ] **Coin-cell hot-swap?** If you want to be able to swap CR1220 without losing time, add a 1 µF buffer cap across the RTC VBAT pin big enough to hold for ~30 s.
- [ ] **Lanyard hole reinforcement** — a brass eyelet press-fit through a mech-cutout vs just a plain PCB hole. Affects mech-cad, not BOM, but easy to forget.

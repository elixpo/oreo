# Elixpo Badge — Breadboard Phase Purchase Checklist

Final reconciled list of what's already on hand vs what needs to be ordered for breadboard prototyping.

---

## ✅ Already have (no need to buy)

| Item | Required for |
|---|---|
| 6mm tactile push buttons (×8 minimum) | HOME, A, B, C, UP, DOWN, LEFT, RIGHT |
| Resistor kit (covers 100Ω, 470Ω, 4.7kΩ, 10kΩ, 100kΩ) | IR driver, LED current limit, button pull-ups, VBAT divider |
| Capacitor kit (100nF, 10µF, 100µF electrolytic) | TSOP decoupling, ADC filter, general decoupling |
| Breadboards (full-size 830-tie) | Main prototyping surface |
| Jumper wires — M-M, M-F, F-F bundles | Breadboard wiring |
| Solid-core 22AWG hookup wire | Power rails |
| Multimeter | Continuity, voltage, short-checking |
| Soldering iron + solder | Soldering DevKit headers, IR LED prep |
| 5mm white LEDs (×4 minimum) | Corner backlight LEDs |
| 5mm IR LED (940nm) | IR transmitter |
| TSOP IR receiver (TSOP1738 or TSOP38238) | IR receiver |

---

## 🛒 To purchase

### From Amazon.in

| Item | Qty | Link | Notes |
|---|---:|---|---|
| **ESP32-S3-DevKitC-1-N16R8** (OceanLabz) | 1 | [Amazon link](https://www.amazon.in/OceanLabz-ESP32-S3-DevKit-N16R8-MicroPython-Unsoldered/dp/B0F9XB91XG) | N16R8 only (16MB flash + 8MB PSRAM), dual USB-C, PCB antenna, headers unsoldered |

### From Robu.in

| Item | Qty | Link | Notes |
|---|---:|---|---|
| **SmartElex 2.0" IPS TFT LCD (LHS200KP-IF05)** | 1 | [Robu link](https://robu.in/product/smartelex-2-inch-ips-tft-lcd-module) | ST7789P3 driver, 240×320, 4-wire SPI, no touch |
| **10kΩ trimmer potentiometer** | 2 | Search "10K trimpot" on Robu | For fake VBAT sweep + spare |
| **2N2222 NPN transistor** (or BC547) | 5 | Search "2N2222" or "BC547" on Robu | IR LED driver — get spares, easy to fry |

---

## 🧩 Optional / verify before ordering

| Item | Notes |
|---|---|
| USB-C data cable | If your existing cable is charge-only, flashing won't work. Test before assuming you have one. |
| Extra IR LED + TSOP receiver | If you only have one of each, buy spares — cheap insurance |

---

## 📦 Order strategy

1. **Place Amazon order first** (ESP32 takes longer to ship in India — typically 2–4 days)
2. **Robu order in parallel** (LCD + transistors + trimpot — usually 3–5 days)
3. While waiting: solder DevKit headers, set up MicroPython toolchain, scaffold the project repo

---

## ✅ Pre-power-on checklist (when parts arrive)

Copied from [BREADBOARD_BOM.md §11](BREADBOARD_BOM.md):

- [ ] DevKit headers soldered straight (seat board in breadboard while soldering)
- [ ] Confirmed UART USB-C port (not native USB) for first flash
- [ ] All 8 buttons tested with multimeter continuity
- [ ] Display VCC to **3V3, NOT 5V**
- [ ] Common ground between DevKit and display
- [ ] IR LED orientation correct (long lead = anode = toward 3V3 side)
- [ ] TSOP1738 orientation correct (pin 1 = OUT, pin 2 = GND, pin 3 = VS)
- [ ] White LED polarity correct (long lead = anode)
- [ ] 100µF cap across TSOP VS–GND (the easy-to-forget one)
- [ ] No 3V3↔GND shorts (multimeter resistance check before USB plug-in)
- [ ] DevKit BOOT/EN buttons accessible (don't bury under wires)

---

## Reference

Full BOM with rationale: [BREADBOARD_BOM.md](BREADBOARD_BOM.md)

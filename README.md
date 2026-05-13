# Oreo Badge OS

A conference badge running a custom MicroPython OS on an **ESP32-S3-DevKitC-1-N16R8**.  
Develop and preview apps on your laptop with the built-in pygame simulator, then deploy to hardware.

![Badge](docs/BADGE_LAYOUT.md)

---

## Hardware

| Component | Part |
|---|---|
| MCU | ESP32-S3-DevKitC-1-N16R8 (16MB flash, 8MB octal PSRAM) |
| Display | SmartElex 2.0" IPS TFT (ST7789P3, 240×320, 4-wire SPI) |
| Buttons | 8× tactile (HOME, A, B, C, UP, DOWN, LEFT, RIGHT) |
| IR | TSOP1738 receiver + 940nm LED (NEC protocol) |
| LEDs | 4× corner white LEDs + onboard NeoPixel (GPIO48) |
| Runtime | MicroPython v1.28.0 SPIRAM_OCT |

Full wiring reference: [`docs/`](docs/)

---

## Repo layout

```
oreoOS/            Core API — Display, Buttons, OS ABCs shared by all backends
oreoWare/         Hardware backend (MicroPython, runs on badge)
lix_sim/        Simulator backend (CPython + pygame, runs on laptop)
oreoOS/         OS launcher — splash, app menu, run loop, crash screen
apps/           User apps (each has manifest.json + main.py)
templates/      Copy-paste starter for new apps
hw_tests/       One-off hardware validation scripts (MicroPython)
docs/           Wiring guides, layout reference, BOM
run_sim.py      Launch the simulator
```

---

## Quick start — simulator (laptop)

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r oreoOS/requirements.txt

python run_sim.py
```

**Controls:**

| Key | Button |
|---|---|
| Arrow keys | UP / DOWN / LEFT / RIGHT |
| Escape or H | HOME (back to launcher) |
| Z or Enter | A (select / confirm) |
| X | B |
| C or Tab | C |

---

## Quick start — hardware (badge)

Flash MicroPython once, then use `mpremote mount .` for live development:

```bash
# Flash firmware (one-time)
esptool.py --chip esp32s3 --port /dev/ttyUSB0 erase_flash
esptool.py --chip esp32s3 --port /dev/ttyUSB0 write_flash 0 \
    firmware/ESP32_GENERIC_S3-SPIRAM_OCT-*.bin

# Live dev (no reflash needed — badge imports from your laptop)
mpremote connect /dev/ttyUSB0 mount . exec "import oreoOS.launcher; oreoOS.launcher.boot()"
```

---

## Writing an app

Copy [`templates/app_template/`](templates/app_template/) into `apps/<your_app>/`.

```python
# apps/my_app/main.py
import oreoOS
from oreoOS import api

class App(oreoOS.App):
    name = "My App"

    def on_enter(self, os):
        super().on_enter(os)

    def update(self, dt):
        pass   # dt = seconds since last frame

    def draw(self, d):
        d.clear(api.rgb(8, 8, 20))
        d.text("Hello!", 80, 150, api.WHITE, scale=2)

    def on_button_press(self, btn):
        if btn == api.BTN_A:
            pass
```

`manifest.json` — required fields:

```json
{ "name": "My App", "type": "app", "version": "0.1" }
```

---

## Architecture

```
Apps ──────────────────────────────────────────────────┐
                                                       │  oreoOS.App   oreoOS.api
OS Launcher (oreoOS/launcher.py)  ─────────────────────┤  (shared interface)
                                                       │
        ┌──────────────────────────────────────────────┘
        │
        ▼
  oreoWare/   (MicroPython, badge)    lix_sim/   (CPython, laptop)
  display.py   → ST7789P3 SPI       display.py  → pygame Surface
  buttons.py   → GPIO PULL_UP       buttons.py  → pygame keyboard
  os.py        → hardware OS        os.py       → sim OS
```

The `oreoOS/api.py` ABCs are the only contract apps depend on — they run identically on both backends.

---

## License

MIT — see [LICENSE](LICENSE).

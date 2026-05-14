<div align="center">

# 🐼 Oreo Badge

**A conference badge that's also a tiny console, a hacker's notebook, and a panda.**

Built by humans who think hardware should feel as warm as software does.

[![License](https://img.shields.io/badge/license-Oreo--PCL-FF5D68)](LICENSE)
[![Made with MicroPython](https://img.shields.io/badge/micropython-1.28-00B4A5)](https://micropython.org)
[![Updates over the air](https://img.shields.io/badge/OTA-yes-FFBE1E)](#updates)

</div>

---

## What is it?

The Oreo Badge is a wearable, programmable conference accessory. Hang it
on your lanyard, hand it to a stranger, swap quests over IR, watch your
GitHub commit graph scroll across its tiny screen.

It runs **OreoOS**, a friendly little operating system that boots into a
warm cream home screen, runs a handful of curated apps, and quietly
updates itself when we ship new things.

Inside the badge: an **ESP32-S3** microcontroller, a **2-inch IPS LCD**,
eight tactile buttons, a touch pad, an IR transmitter + receiver, and a
6-axis motion sensor so a few of the games respond to tilt.

---

## Why a badge?

Because conferences should feel like meeting people, not exchanging
business cards. Because handing someone an *object* you made changes
the conversation. Because tinkerers learn faster when there's a screen
that lights up.

We wanted:

- **Something kids can solder** — through-hole-friendly, forgiving
  components, a power rail that survives mistakes
- **Something adults can hack** — proper OS, real apps, an SDK that's
  three lines of `class App(oreoOS.App):` away from a working game
- **Something that looks alive** — pink, gold, teal, an actual panda
  mascot, animations that feel cared for

The result is a badge that ships a custom OS, a games library, a tilt-
controlled racing game, an IR quest tracker, a weather app, and the
ability to send a software update to every badge in a room with one
`git tag`.

---

## What's on it

A growing handful of apps live in [`apps/`](apps/), all written in the
same `class App(oreoOS.App)` shape. Each app declares a name, an icon,
and three lifecycle methods: `on_enter / update / draw`. That's the
whole API. The OS handles loading, rendering, navigation, and updates.

Highlights:

- **Home** — clock, date, WiFi/BT/battery status
- **Apps** — grid or category view (configurable in settings)
- **Badge / Identity** — your GitHub profile + a conference name card
- **Commits** — your contribution graph, scrolled live
- **Weather** — local conditions over a dimmed panda sky
- **Pet** — a panda you take care of across days
- **Racer** — top-down kart, tilt or D-pad to drive
- **Flappy, Snake** — the classics
- **Gallery** — photos you flash with the rest of the OS
- **Color Picker** — RGB / HSL / CMYK with a 2D spectrum
- **IR Quest** — receive beacons, send back, decode protocols
- **Settings / About** — themed, scrollable, complete with OTA

Anyone can write a new one in an afternoon — see
[`templates/example_app/`](templates/example_app/) for a hello-world.

---

## Updates

The badge talks to its own GitHub release channel. When we cut a new
version:

1. The badge runs a **fast SHA check** against the latest manifest —
   no big downloads to find out if anything actually changed.
2. **Small patches** (≤ 80 KB) auto-download in the background and pop a
   gentle "ready to install, reboot anytime" notice.
3. **Big updates** (new apps, asset packs, major version bumps) wait
   for the user's explicit yes.
4. Files are staged in a `/_ota` directory, validated by SHA-256, and
   atomically swapped in on the next boot. If anything goes wrong
   mid-download, the badge keeps running its old version.

You can also tap **Check Update** in Settings or About at any time.

---

## Hardware

The reference design is built around an **ESP32-S3-DevKitC-1-N16R8**
(16 MB flash, 8 MB PSRAM). The schematic + breadboard BOM live in
[`docs/`](docs/). Headline components:

| Part | What it does |
|---|---|
| ESP32-S3 | brain, WiFi, BLE |
| ST7789 320×240 IPS | display |
| 8 tactile buttons | HOME, A, B, C, dpad |
| TTP223 | capacitive touch wake |
| MPU-6050 | tilt input for games |
| TSOP38238 + IR LED | conference quests + signal play |
| MAX17048 + 18650 | battery + fuel gauge |

The full pin map is in [`oreoWare/pins.py`](oreoWare/pins.py) — one
file is the source of truth, so when the PCB changes you only edit one
line.

---

## Getting started

```bash
# Clone, set up a venv, install host-side tooling
git clone https://github.com/elixpo/oreo-badge
cd oreo-badge
python -m venv .venv && source .venv/bin/activate
pip install -r oreoOS/requirements.txt

# Flash MicroPython firmware (one-time)
# (see docs/FIRMWARE.md)

# Push the OS to a connected board
python tools/deploy.py /dev/ttyACM0
```

That's it. The badge will splash, boot to home, and start running.

To add your own app, copy the template:

```bash
cp -r templates/example_app apps/my_thing
# edit apps/my_thing/main.py
python tools/deploy.py /dev/ttyACM0
```

Your app shows up in the launcher.

---

## Project layout

```
oreoOS/      the Python OS — boot, launcher, splash, theme, widgets,
             OTA client, cache, power management, app base class
oreoWare/    hardware drivers — display, buttons, wifi, BT, IMU, IR,
             battery, touch, pin map
apps/        the user-facing apps, each in its own folder
assets/      icons, sprites, fonts, status glyphs (raw + optimized)
prompts/     image-generation prompts used to bake the assets
tools/       deploy, asset pipelines, release builder, helpers
docs/        hardware notes, BOM, schematic, design rationale
templates/   starting point for new apps
```

---

## Contributing

Building this with us? See [CONTRIBUTING.md](CONTRIBUTING.md) for the
release process, app conventions, and how to get a PR landed.

We expect everyone in the project to follow the
[Code of Conduct](CODE_OF_CONDUCT.md). It's short, plain-English, and
basically asks you to be the kind of person you'd want to swap badges
with at a conference.

---

## Made by

The Oreo Badge is a side project from the
[**Elixpo**](https://elixpo.com) team. The mascot, OS, and most of the
apps are by [@Circuit-Overtime](https://github.com/Circuit-Overtime).
Want to help, ship an app, sponsor a build, or just say hi?

✉️  **hello@elixpo.com**

</div>

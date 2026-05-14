<div align="center">


<img src="assets/sprites/raw/mascot.png" alt="Oreo, the panda mascot" width="180">

### A conference badge that's also a tiny console, a hacker's notebook, and a panda. 🐼

<br>

[![License: Oreo-PCL](https://img.shields.io/badge/license-Oreo--PCL-FF5D68?style=for-the-badge)](LICENSE)
[![MicroPython 1.28](https://img.shields.io/badge/MicroPython-1.28-00B4A5?style=for-the-badge&logo=python&logoColor=white)](https://micropython.org)
[![ESP32-S3](https://img.shields.io/badge/ESP32--S3-N16R8-2E2E2E?style=for-the-badge&logo=espressif&logoColor=white)](https://www.espressif.com/en/products/socs/esp32-s3)
[![OTA Updates](https://img.shields.io/badge/OTA-yes-FFBE1E?style=for-the-badge)](#-updates)

[![Made by Elixpo](https://img.shields.io/badge/made_by-Elixpo-FF5D68?style=flat-square)](https://elixpo.com)
[![Issues welcome](https://img.shields.io/badge/issues-welcome-00B4A5?style=flat-square)](https://github.com/elixpo/oreo/issues)
[![Stars](https://img.shields.io/github/stars/elixpo/oreo?style=flat-square&color=FFBE1E)](https://github.com/elixpo/oreo/stargazers)
[![Sponsor](https://img.shields.io/badge/sponsor-%E2%9D%A4-FF5D68?style=flat-square)](https://github.com/sponsors/Circuit-Overtime)

</div>

<img src="docs/images/banner.png" alt="OreoOS — the Oreo Badge" width="100%">

---

## ✨ What is it

A wearable, programmable badge that runs **OreoOS** — a small,
friendly operating system with a curated app drawer, themed UI, OTA
updates, and a panda mascot.

Hang it on your lanyard. Hand it to a stranger. Swap quests over IR.
Watch your GitHub commit graph scroll across its tiny screen.

---

## 🎮 Apps

Every tile in the drawer is its own folder under [`apps/`](apps/),
written as a small `class App(oreoOS.App)` with three lifecycle methods.

<div align="center">

| | | | | |
|:-:|:-:|:-:|:-:|:-:|
| <img src="assets/icons/raw/apps_icon.png" width="64"><br>**Apps** | <img src="assets/icons/raw/badge_icon.png" width="64"><br>**Badge** | <img src="assets/icons/raw/identity_icon.png" width="64"><br>**Identity** | <img src="assets/icons/raw/commits_icon.png" width="64"><br>**Commits** | <img src="assets/icons/raw/wifi_icon.png" width="64"><br>**Weather** |
| <img src="assets/icons/raw/elixpo_pet_icon.png" width="64"><br>**Pet** | <img src="assets/icons/raw/racer_icon.png" width="64"><br>**Racer** | <img src="assets/icons/raw/flappy_icon.png" width="64"><br>**Flappy** | <img src="assets/icons/raw/snake_icon.png" width="64"><br>**Snake** | <img src="assets/icons/raw/gamepad_icon.png" width="64"><br>**Gamepad** |
| <img src="assets/icons/raw/gallery_icon.png" width="64"><br>**Gallery** | <img src="assets/icons/raw/color_icon.png" width="64"><br>**Color** | <img src="assets/icons/raw/IR_Quest_icon.png" width="64"><br>**IR Quest** | <img src="assets/icons/raw/settings_icon.png" width="64"><br>**Settings** | <img src="assets/icons/raw/about_icon.png" width="64"><br>**About** |

</div>

Want to add yours? Copy [`templates/example_app/`](templates/example_app/)
into `apps/your_name/` and ship.

---

## 🚀 Get going

```bash
git clone https://github.com/elixpo/oreo
cd oreo
python -m venv .venv && source .venv/bin/activate
pip install -r oreoOS/requirements.txt
python tools/deploy.py /dev/ttyACM0      # flash to a connected board
```

For step-by-step app-writing + OS internals, see
[`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## 🛠 Hardware

ESP32-S3 + 320×240 IPS LCD + 8 buttons + capacitive touch pad + IMU + IR.

Full pinout, schematic, BOM, soldering tips, and breadboard photos
live in **[`docs/HARDWARE.md`](docs/HARDWARE.md)**. The single source
of truth for GPIO assignments is
[`oreoWare/pins.py`](oreoWare/pins.py) — one file, one line per pin.

---

## 🔄 Updates

The badge pulls itself forward. A fast SHA-vs-version check runs in
the background against the project's GitHub release channel, auto-stages
small patches, and asks before downloading big ones. Files are validated
by SHA-256 and atomically swapped on the next boot.

Releases are cut manually with `python tools/release.py vX.Y.Z` —
details in [`CONTRIBUTING.md → Releasing`](CONTRIBUTING.md#releasing).

---

## 🙌 Contributing

We love new contributors. The bar is low; the welcome is warm.

- 🐛 Bugs / ideas: open an [issue](https://github.com/elixpo/oreo/issues/new/choose)
- 🔧 Code: read [`CONTRIBUTING.md`](CONTRIBUTING.md)
- 🧑‍🤝‍🧑 Community: read the [`Code of Conduct`](CODE_OF_CONDUCT.md)
- 🔐 Security disclosures: read [`SECURITY.md`](SECURITY.md)

---

## ⭐ Star history

<a href="https://www.star-history.com/#elixpo/oreo&Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=elixpo/oreo&type=Date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=elixpo/oreo&type=Date" />
    <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=elixpo/oreo&type=Date" width="640" />
  </picture>
</a>

---
<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=12,14,20,24&height=120&section=footer&fontSize=0" width="100%" />

### Made with ❤️ by [Elixpo](https://elixpo.com) | [GitHub](https://github.com/elixpo/sketch.elixpo)

</div>

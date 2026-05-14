<!-- Top wave -->
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://capsule-render.vercel.app/api?type=waving&color=0:FF5D68,50:FFBE1E,100:00B4A5&height=180&section=header&text=Oreo%20Badge&fontColor=FFFFFF&fontSize=48&animation=fadeIn">
  <img alt="Oreo Badge" src="https://capsule-render.vercel.app/api?type=waving&color=0:FF5D68,50:FFBE1E,100:00B4A5&height=180&section=header&text=Oreo%20Badge&fontColor=FFFFFF&fontSize=48&animation=fadeIn">
</picture>

<div align="center">

<!-- TODO: drop a hero shot at docs/images/hero.png -->
<img src="docs/images/hero.png" alt="Oreo Badge on a desk" width="520">

### A conference badge that's also a tiny console, a hacker's notebook, and a panda. 🐼

<br>

[![License: Oreo-PCL](https://img.shields.io/badge/license-Oreo--PCL-FF5D68?style=for-the-badge)](LICENSE)
[![MicroPython 1.28](https://img.shields.io/badge/MicroPython-1.28-00B4A5?style=for-the-badge&logo=python&logoColor=white)](https://micropython.org)
[![ESP32-S3](https://img.shields.io/badge/ESP32--S3-N16R8-2E2E2E?style=for-the-badge&logo=espressif&logoColor=white)](https://www.espressif.com/en/products/socs/esp32-s3)
[![OTA Updates](https://img.shields.io/badge/OTA-yes-FFBE1E?style=for-the-badge)](#updates)

[![Made by Elixpo](https://img.shields.io/badge/made_by-Elixpo-FF5D68?style=flat-square)](https://elixpo.com)
[![Issues welcome](https://img.shields.io/badge/issues-welcome-00B4A5?style=flat-square)](https://github.com/elixpo/oreo-badge/issues)
[![Stars](https://img.shields.io/github/stars/elixpo/oreo-badge?style=flat-square&color=FFBE1E)](https://github.com/elixpo/oreo-badge/stargazers)
[![Sponsor](https://img.shields.io/badge/sponsor-%E2%9D%A4-FF5D68?style=flat-square)](https://github.com/sponsors/Circuit-Overtime)

</div>

---

## ✨ What is it

A wearable, programmable badge that runs **OreoOS** — a small,
friendly operating system with a curated app drawer, themed UI, OTA
updates, and a panda mascot.

Hang it on your lanyard. Hand it to a stranger. Swap quests over IR.
Watch your GitHub commit graph scroll across its tiny screen.

<br>

<div align="center">

| | | |
|:-:|:-:|:-:|
| <img src="docs/images/app_home.png" width="160"><br>**Home** | <img src="docs/images/app_apps.png" width="160"><br>**Apps** | <img src="docs/images/app_racer.png" width="160"><br>**Racer** |
| <img src="docs/images/app_commits.png" width="160"><br>**Commits** | <img src="docs/images/app_pet.png" width="160"><br>**Pet** | <img src="docs/images/app_color.png" width="160"><br>**Color Picker** |

<sub>(Drop real screenshots into <code>docs/images/</code> — they show up here automatically.)</sub>

</div>

---

## 🚀 Get going

```bash
git clone https://github.com/elixpo/oreo-badge
cd oreo-badge
python -m venv .venv && source .venv/bin/activate
pip install -r oreoOS/requirements.txt
python tools/deploy.py /dev/ttyACM0      # flash to a connected board
```

Want to write your own app? Copy
[`templates/example_app/`](templates/example_app/) into `apps/your_name/`
and edit — see [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full walk-through.

---

## 🛠 Hardware

ESP32-S3 + 320×240 IPS LCD + 8 buttons + touch pad + IMU + IR.

The full pinout, schematic, BOM, soldering tips, and breadboard photos
live in **[`docs/HARDWARE.md`](docs/HARDWARE.md)**.

The single source of truth for GPIO assignments is
[`oreoWare/pins.py`](oreoWare/pins.py) — one file, one line per pin.

---

## 🔄 Updates

The badge pulls itself forward. It does a fast SHA-vs-version check
against its own GitHub release channel, auto-stages small patches, and
asks before downloading big ones. Files are validated by SHA-256 and
atomically swapped on the next boot.

Full design + release flow: see [`CONTRIBUTING.md → Releasing`](CONTRIBUTING.md#releasing).

---

## 📂 Repo layout

```
oreoOS/      the Python OS — boot, splash, theme, OTA, power, app base
oreoWare/    hardware drivers — display, buttons, wifi, BT, IMU, IR
apps/        the user-facing apps (each in its own folder)
assets/      icons, sprites, fonts (raw + optimized RGB565 modules)
tools/       deploy, asset pipeline, release builder
docs/        HARDWARE.md + design notes + images
templates/   starting point for new apps
```

---

## 🙌 Contributing

We love new contributors. The bar is low; the welcome is warm.

- 🐛 Bugs / ideas: open an [issue](https://github.com/elixpo/oreo-badge/issues/new/choose)
- 🔧 Code: read [`CONTRIBUTING.md`](CONTRIBUTING.md)
- 🧑‍🤝‍🧑 Community: read the [`Code of Conduct`](CODE_OF_CONDUCT.md)
- 🔐 Security disclosures: read [`SECURITY.md`](SECURITY.md)

---

## ⭐ Star history

<a href="https://www.star-history.com/#elixpo/oreo-badge&Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=elixpo/oreo-badge&type=Date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=elixpo/oreo-badge&type=Date" />
    <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=elixpo/oreo-badge&type=Date" width="640" />
  </picture>
</a>

---

## 📫 Made by

The Oreo Badge is a project from the [**Elixpo**](https://elixpo.com) team.
Mascot, OS, and most of the apps by
[@Circuit-Overtime](https://github.com/Circuit-Overtime).

Want to help, ship an app, sponsor a build, or just say hi?

<div align="center">

✉️  **hello@elixpo.com**

</div>

<!-- Bottom wave -->
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://capsule-render.vercel.app/api?type=waving&color=0:00B4A5,50:FFBE1E,100:FF5D68&height=120&section=footer">
  <img alt="" src="https://capsule-render.vercel.app/api?type=waving&color=0:00B4A5,50:FFBE1E,100:FF5D68&height=120&section=footer">
</picture>

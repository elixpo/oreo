<div align="center">



<img src="assets/sprites/raw/mascot.png" alt="Oreo, the panda mascot" width="60">

# Oreo Badge

**A handheld panda-themed conference badge that runs a real operating system.**

[![License: Oreo-PCL](https://img.shields.io/badge/license-Oreo--PCL-FF5D68?style=for-the-badge)](LICENSE)
[![MicroPython 1.28](https://img.shields.io/badge/MicroPython-1.28-00B4A5?style=for-the-badge&logo=python&logoColor=white)](https://micropython.org)
[![ESP32-S3](https://img.shields.io/badge/ESP32--S3-N16R8-2E2E2E?style=for-the-badge&logo=espressif&logoColor=white)](https://www.espressif.com/en/products/socs/esp32-s3)
[![OTA Updates](https://img.shields.io/badge/OTA-yes-FFBE1E?style=for-the-badge)](#-updates)

[![Made by Elixpo](https://img.shields.io/badge/made_by-Elixpo-FF5D68?style=flat-square)](https://elixpo.com)
[![Issues welcome](https://img.shields.io/badge/issues-welcome-00B4A5?style=flat-square)](https://github.com/elixpo/oreo/issues)
[![Stars](https://img.shields.io/github/stars/elixpo/oreo?style=flat-square&color=FFBE1E)](https://github.com/elixpo/oreo/stargazers)
[![Sponsor](https://img.shields.io/badge/sponsor-%E2%9D%A4-FF5D68?style=flat-square)](https://github.com/sponsors/Circuit-Overtime)

</div>

---

<div align="center">

> *Hang it on your lanyard. Hand it to a stranger.*
> *Swap quests over IR. Watch your commits scroll past.*
> *Oreo is what happens when a conference name-tag grows up.*

</div>

<img src="docs/images/banner.png" alt="OreoOS — the Oreo Badge" width="100%">


---

## 🌟 At a glance

<table>
<tr>
<td width="33%" valign="top">

### 🖥 320 × 240 IPS display
A 2-inch full-colour LCD running at 33 fps with PWM-dimmed backlight. Every app you write gets the same framebuffer + theme palette.

</td>
<td width="33%" valign="top">

### 🐼 Built-in app SDK
`class App(oreoOS.App):` with three methods is all it takes. Copy `templates/example_app/`, edit, deploy. Your icon shows up in the launcher.

</td>
<td width="33%" valign="top">

### 📡 Real WiFi + Bluetooth
Weather, GitHub commits, OTA updates — all live. WiFi power-capped at 11 dBm so a bench supply can run it. BLE for badge-to-badge swaps.

</td>
</tr>
<tr>
<td valign="top">

### 🎮 14 default apps + an App Market
Games, GitHub tools, IR quests, a markdown reader, storage breakdown, gesture controls. More optional apps (colour picker, the Elixpo Pet panda) install on-device from the App Market tile.

</td>
<td valign="top">

### 🔄 Over-the-air updates
The badge SHA-checks GitHub Releases in the background. Small patches install themselves. Big updates wait for your confirmation.

</td>
<td valign="top">

### 🤝 Talks to other badges
IR beacons, BLE advertise + scan, a quest system. Hand someone your badge — they hand you back a new app, a new puzzle, a new high score.

</td>
</tr>
</table>

---

## 🎮 The apps

Every tile in the drawer is its own folder under [`apps/`](apps/),
written as a small `class App(oreoOS.App)` with three lifecycle methods.
Two trees ship to the badge: [`apps/`](apps/) is what's pre-installed,
[`apps_market/`](apps_market/) is the catalogue of opt-in extras the
user can install on-device from the **App Market** tile.

<div align="center">

| | | | |
|:-:|:-:|:-:|:-:|
| <img src="assets/icons/raw/badge_icon.png" width="64"><br>**Badge** | <img src="assets/icons/raw/identity_icon.png" width="64"><br>**Identity** | <img src="assets/icons/raw/commits_icon.png" width="64"><br>**Commits** | <img src="assets/icons/raw/wallpaper_icon.png" width="64"><br>**Weather** |
| <img src="assets/icons/raw/racer_icon.png" width="64"><br>**Racer** | <img src="assets/icons/raw/flappy_icon.png" width="64"><br>**Flappy** | <img src="assets/icons/raw/snake_icon.png" width="64"><br>**Snake** | <img src="assets/icons/raw/gamepad_icon.png" width="64"><br>**Gamepad** |
| <img src="assets/icons/raw/gallery_icon.png" width="64"><br>**Gallery** | <img src="assets/icons/raw/IR_Quest_icon.png" width="64"><br>**IR Quest** | <img src="assets/icons/raw/reader_icon.png" width="64"><br>**Reader** | <img src="assets/icons/raw/storage_icon.png" width="64"><br>**Storage** |
| <img src="assets/icons/raw/apps_icon.png" width="64"><br>**Market** | <img src="assets/icons/raw/settings_icon.png" width="64"><br>**Settings** | <img src="assets/icons/raw/about_icon.png" width="64"><br>**About** | |

</div>

Bluetooth and WiFi don't get their own drawer tiles — they live inside **Settings**, alongside brightness, sleep, gestures and OTA. The notification panel (press **C** from anywhere) puts both radios + a brightness slider + manual time-sync one tap away.

### 📦 App Market — install / uninstall extras on-device

Apps that ship under [`apps_market/`](apps_market/) are **optional**. They aren't in the launcher drawer until you install them. The default catalogue today: **Color Picker** and **Elixpo Pet** — both are good demos but don't pull their weight as always-on tiles.

Open the **App Market** tile, scroll to the app you want, press **A**:
- **INSTALL** → copies the tree from `/apps_market/<name>/` to `/apps/<name>/`. Next time you open the drawer the tile is there.
- **INSTALLED** → press **A** again to uninstall. The catalogue copy stays put so re-install is one tap.

```python
# Programmatic API (handy from REPL or another app):
from oreoOS import store
store.list_market()      # [{name, dir, icon, author, installed}, …]
store.install("pet")     # → bool
store.uninstall("pet")
```

The Market is the right home for: games, themed sketches, hardware demos, hackathon entries. **Contribute one** by dropping a folder into `apps_market/<your_app>/` with the usual `main.py + manifest.json + __init__.py + assets/` shape; the deploy script picks it up automatically and the market tile lists it on next boot. Anything in `apps_market/` is **opt-in by default** — that's how you keep flash + drawer real estate tight for everyone else.

Want yours to be **always-installed**? Drop it in `apps/` instead. Copy [`templates/example_app/`](templates/example_app/) as a starting point.

---

## 🚀 Get going

```bash
git clone https://github.com/elixpo/oreo
cd oreo
python -m venv .venv && source .venv/bin/activate
pip install -r oreoOS/requirements.txt
python tools/deploy.py /dev/ttyACM0      # flash to a connected board
```

For step-by-step app-writing + OS internals, see [`CONTRIBUTING.md`](CONTRIBUTING.md).

---

## 🔔 The notification panel

Press **C** from any app. A pink panel slides down with everything you'd otherwise dig through menus for:

| Row | What it does |
|---|---|
| WiFi · BT · Settings | three pills — A toggles the radio, or jumps straight to the Settings app |
| Brightness slider | LEFT / RIGHT nudges the LCD backlight by 10 %, no preset cycling |
| Sync time | A re-runs the NTP sync — useful when WiFi just came up or you crossed a timezone |
| Notification cards | newest-first list of OTA / BT / file events; A opens, B clears all |

Press **C** (or **HOME**) again to dismiss — the underlying app keeps its state and resumes mid-frame.

---

## 🧰 Built-in libraries

OreoOS ships a small batteries-included SDK that every app imports
from `oreoOS`. Three of those are worth a quick tour:

### Drawing — `d.rect`, `d.pixel`, `d.text`, `d.blit`, `d.clear`

```python
from oreoOS import api, theme

def draw(self, d):
    d.clear(theme.BG)                            # fill cream background
    d.rect(10, 10, 100, 40, theme.PRIMARY, fill=True)
    d.rect(10, 10, 100, 40, theme.GOLD)          # outline (fill=False default)
    d.pixel(60, 30, api.WHITE)                   # single pixel
    d.text("hello!", 14, 20, api.WHITE, scale=2) # framebuf 8×8, scaled
    d.text(api.rgb(160, 50, 220), 14, 60, ...)   # arbitrary RGB
```

The framebuffer is RGB565 big-endian. Build colours with `api.rgb(r, g, b)`
instead of constructing the integer by hand. Theme colours
(`theme.PRIMARY` / `theme.GOLD` / `theme.TEAL` / `theme.MUTED` / …)
exist for visual consistency across apps.

### Sprites + images — `d.blit`

```python
def _try_sprite(name):
    try:
        m = __import__("apps.my_app.assets.optimized." + name, None, None,
                       ["DATA", "W", "H"])
        return (bytearray(m.DATA), m.W, m.H)
    except (ImportError, AttributeError):
        return None

def draw(self, d):
    if (s := self._sprite):
        data, w, h = s
        d.blit(data, x, y, w, h)
```

Sprites are produced by `tools/optimize_assets.py` from raw PNG / JPG
files under `apps/my_app/assets/raw/`. Pixels equal to chroma-key
magenta (`0xF81F` RGB565) are skipped by `blit()` — that's how the
panda mascot ends up with a transparent backdrop on the splash.

### Higher-level text — `oreoOS.pixelfont`

```python
from oreoOS import pixelfont
font = pixelfont.load("pixelify_16")  # also pixelify_8, _12, _24
font.text(d, "Score: 42", 8, 6, theme.PRIMARY)
w = font.measure("Score: 42")          # for centring
```

The framebuf's 8×8 font is fine for HUDs; the Pixelify Sans bitmaps
look better for titles and menus.

### Caching network data — `oreoOS.cache`

```python
from oreoOS import cache
profile, age = cache.load("apps/my_app/cache.txt", ttl_s=3600)
if not profile or age > 3600:
    profile = my_fetch_function()
    cache.save("apps/my_app/cache.txt", profile)
```

Used by Badge + Commits to render instantly from disk and refresh in
the background. Auto-includes a `__ts=<epoch>` header so callers know
the cache age.

### Time + NTP sync — `oreoOS.timeutil`

```python
from oreoOS import timeutil
hour, minute, sec, weekday, day, month, year = timeutil.now()

ok, msg = timeutil.sync_from_ntp()        # ~2 s blocking, gated on WiFi
print(timeutil.last_sync_status())        # "ok" | "no-wifi" | "failed" | "never"
```

Same call drives the boot-time auto-sync, the **Sync Time** row in
Settings, and the **C-panel** time-sync action — all three surfaces
agree on the last result via the shared `last_sync_status()`.

### Storage breakdown — `oreoOS.storage`

```python
from oreoOS import storage
snap = storage.usage()
# {'stats': {'total': …, 'used': …, 'free': …},
#  'buckets': {'system': {...}, 'apps': {...}, 'gallery': {...},
#              'documents': {...}, 'misc': {...}}}
```

A full `os.listdir + os.stat` walk takes a few hundred ms on a
populated 16 MB flash, so the Storage app declares
`SHOW_LOADING = True` to mask the blocking call behind the slide
splash. Use it from any app that wants a "how full am I?" readout.

### Markdown rendering — the Reader app

The Reader app (`apps/reader/`) renders **`.md`** and **`.txt`** files
landed in `documents/` (BT inbox) or `apps/reader/assets/` (flashed).
Supports `# / ## / ###` headings, `**bold**`, `*italic*`, `` `code` ``,
bullets, numbered lists, fenced ``` ``` ``` blocks, and `---` rules —
small enough to ship to flash, big enough for README-style notes
someone sideloaded over BT. New files appear in the picker within
200 ms (5 Hz poll) — no restart.

### Wireless networking and Bluetooth

OreoOS leans on MicroPython's stock networking stack; the OreoOS
wrappers (`oreoWare.wifi`, `oreoWare.bt`) add config handling and
power capping on top.

- **WiFi** — [`network.WLAN`](https://docs.micropython.org/en/latest/library/network.WLAN.html).
  Credentials come from `.env` (`WIFI_SSID`, `WIFI_PASSWORD`); the OS
  applies `wlan.config(txpower=…)` and `pm=PM_POWERSAVE` from
  `oreoOS/config.py` so a sealed badge doesn't melt its LDO.
- **Bluetooth** — [`bluetooth`](https://docs.micropython.org/en/latest/library/bluetooth.html).
  The badge advertises as **Oreo** and exposes a tiny GATT "transfer"
  service so a paired device can push **one image (max 250 KB)** or
  **one text document (deflate-compressed)** at a time. Images land in
  `apps/gallery/assets/raw/`, text in `documents/`. BLE adv interval is
  capped by `BT_ADV_INTERVAL_MS` to keep average current draw down.

```python
# WiFi via the OreoOS wrapper — auto-applies power caps from config
from oreoWare import wifi
wifi.connect_from_config()
print(wifi.ip())

# Or drop straight to stock MicroPython:
import network
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect("SSID", "password")
```

```python
# BLE advertise (raw stdlib path)
import bluetooth
ble = bluetooth.BLE()
ble.active(True)
ble.gap_advertise(500_000, b"\x02\x01\x06\x05\x09Oreo")
```

**Pushing files to the badge.** Connect to "Oreo", then write to the
RX characteristic in chunks. Frame format:

```
+------+-------------------+-----------+-------------+
| type | length (4B BE)    | payload   | crc32 (4B)  |
+------+-------------------+-----------+-------------+
  'I'  =  image,    raw bytes, length ≤ 250 KB
  'T'  =  text,     deflate-compressed UTF-8 → documents/*.txt
  'M'  =  markdown, deflate-compressed UTF-8 → documents/*.md
```

The TX characteristic notifies a single-byte status (`0x02` = done,
`0xE1` = too large, `0xE2` = bad CRC, …). See [`oreoWare/bt.py`](oreoWare/bt.py)
for the full UUID + status table.

### Built-in modules

Every stock MicroPython module is available to apps — no extra install
step. The ones you'll actually reach for on badge work:

`array`, `binascii`, `builtins`, `cmath`, `collections`, `errno`, `gc`,
`hashlib`, `heapq`, `io`, `json`, `machine`, `math`, `micropython`,
`network`, `os`, `platform`, `random`, `re`, `select`, `socket`, `ssl`,
`struct`, `sys`, `time`, `uctypes`, `bluetooth`, `cryptolib`, `deflate`,
`framebuf`, `vfs`, `ntptime`, `requests`, `urequests`, `asyncio`,
`aioble`, `websocket`, `umqtt`, `webrepl`.

On top of those, OreoOS ships its own helper packages: `oreoOS.*`
(font, sprite, cache, theme, widgets, ota, power…) and `oreoWare.*`
(display, buttons, wifi, bt, imu, ir, battery, pins). Import them from
any app — they're on the device boot path.

---

## 🖼 Gallery — flashing your own photos

The Gallery app cycles through pictures you ship with the badge.
Workflow:

```bash
# 1. Drop pictures into apps/gallery/assets/raw/
cp ~/Pictures/team-offsite.jpg apps/gallery/assets/raw/

# 2. Bake them to RGB565 (preserves aspect ratio, fits 320×196 play area)
python tools/optimize_assets.py --app gallery

# 3. Push to the badge — the deploy step also prunes any stale photos
#    the user deleted from raw/ so the device stays in sync.
python tools/deploy.py /dev/ttyACM0
```

The optimizer accepts `.png`, `.jpg`, and `.jpeg`. Photos are
aspect-preserved (no forced square crop). On the badge, **L/R cycles
photos**, and the last tile is a **+ help screen** that walks any
user through this exact workflow.

---

## 🛠 Hardware

| | |
|---|---|
| **MCU** | ESP32-S3-DevKitC-1-N16R8 (16 MB flash, 8 MB PSRAM) |
| **Display** | ST7789 IPS, 2.0", 320×240, 4-wire SPI @ 40 MHz |
| **Input** | 8 tactile buttons — also the wake-from-sleep source (TTP223 capacitive pads planned for v2) |
| **Sensors** | MPU-6050 (6-DoF IMU), TSOP38238 (IR RX) |
| **Output** | 4 corner LEDs, WS2812 status NeoPixel, IR LED (940 nm) + 2N2222 driver |
| **Comms** | WiFi 802.11 b/g/n, BLE 5.0, IR, USB-C |
| **Power** | 18650 cell + MAX17048 fuel gauge, USB-C charging, AMS1117-3.3 LDO |
| **Clock** | RTC backed by NTP — boot sync + manual re-sync from Settings / C-panel |

📄 **Full electrical / mechanical specs:** see [`docs/DATASHEET.md`](docs/DATASHEET.md)
🔧 **Build guide + pinout + soldering tips:** see [`docs/HARDWARE.md`](docs/HARDWARE.md)

The single source of truth for every GPIO assignment is
[`oreoWare/pins.py`](oreoWare/pins.py) — one file, one line per pin.

---

## 🔄 Updates

The badge pulls itself forward. A fast SHA-vs-version check runs in the background against the project's GitHub release channel. **Small patches** (≤ 80 KB) install themselves; **big updates** wait for your explicit yes. Files are validated by SHA-256 and atomically swapped on the next boot — if anything goes wrong mid-download, the badge keeps running its old version.

Wall-clock time follows the same pattern: NTP runs once at boot when WiFi is up, and the **Sync Time** action (Settings or the C-panel) lets you re-pull if you crossed a timezone or the clock drifted.

Cutting a release takes one command: `python tools/release.py`. Details in [`CONTRIBUTING.md → Releasing`](CONTRIBUTING.md#releasing).

---

## 📚 Reading order

| | |
|---|---|
| 👋 **Just want to use it?** | this README + [`docs/HARDWARE.md`](docs/HARDWARE.md) |
| 🧑‍💻 **Want to write an app?** | [`CONTRIBUTING.md`](CONTRIBUTING.md) + [`templates/example_app/`](templates/example_app/) |
| 🔌 **Building your own PCB?** | [`docs/DATASHEET.md`](docs/DATASHEET.md) + [`oreoWare/pins.py`](oreoWare/pins.py) |
| 🤝 **Joining the community?** | [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) + [`SUPPORT.md`](SUPPORT.md) |
| 🛡 **Found a vulnerability?** | [`SECURITY.md`](SECURITY.md) |
| 📖 **Citing OreoOS?** | [`CITATION.cff`](CITATION.cff) |

A docs index lives at [`docs/README.md`](docs/README.md).

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


With 💖 by [**Ayushman Bhattacharya**](https://github.com/Circuit-Overtime).

Want to help, ship an app, sponsor a build, or just say hi - ✉️ **hello@elixpo.com**

</div>


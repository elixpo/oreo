# Using the badge from a computer

Plug the badge into a computer with a USB-C cable and you get the MicroPython
REPL that runs OreoOS. Through it you can look at files, copy them, run code
and reinstall the OS. Large media is faster over Wi-Fi with **Send Files**
(see [below](#large-files-send-files-over-wi-fi)).

The badge is built on an ESP32-S3-DevKitC-1 N16R8 (see
[`BREADBOARD_BOM.md`](BREADBOARD_BOM.md)). The PCB version keeps the same
native USB port.

## Quick start

```bash
git clone https://github.com/elixpo/oreo && cd oreo
python3 -m venv .venv && source .venv/bin/activate
pip install -r oreoOS/requirements.txt     # mpremote, esptool and the host tools

mpremote devs                               # find the badge (see below)
mpremote connect /dev/ttyACM0 repl          # REPL; Ctrl-] to leave
```

## Which USB-C port

The DevKit has two USB-C ports. Use the one labelled **USB**.

| Silkscreen | Connects to | Shows up as | Use it for |
|---|---|---|---|
| **USB** | the ESP32-S3's own USB (GPIO19/20) | `303a:83ec` **Elixpo Oreo Badge** | REPL, `mpremote`, `./deploy`, firmware flashing |
| **UART** | a USB-to-serial bridge (CH343, `1a86:55d3`, on the tested board) on UART0 | the bridge's name, not the badge's | boot logs and recovery when the native port is not responding |

`0x303A` is Espressif's USB vendor ID and `0x83EC` is the product ID
Espressif allocated to this badge
([espressif/usb-pids#425](https://github.com/espressif/usb-pids/pull/425)).
The Oreo Badge firmware reports it, so the badge appears by name:

```text
$ lsusb | grep 303a
… ID 303a:83ec … Elixpo Oreo Badge
```

Some DevKitC-1 boards use a CP2102N bridge instead of the CH343; on Linux that
one appears as `/dev/ttyUSB*` rather than `/dev/ttyACM*`.

## Finding the port

The port name is assigned by the computer and can change when you reconnect
or plug in another board. Look it up each time:

```bash
mpremote devs
ls -l /dev/serial/by-id/        # Linux: names that include "Elixpo_Oreo_Badge"
```

| System | Typical name |
|---|---|
| Linux | `/dev/ttyACM0` |
| macOS | `/dev/cu.usbmodem…` |
| Windows | `COM3`, `COM4`, … |

With both USB-C ports connected, Linux names both `ttyACM*`, so pick the
entry with **Elixpo_Oreo_Badge** in `/dev/serial/by-id/`. The examples below
use `/dev/ttyACM0`; replace it with yours.

**Linux permissions:** if you get "permission denied", add yourself to the
group that owns the port (`dialout` on Debian/Ubuntu, `uucp` on Arch), then
log out and back in:

```bash
sudo usermod -aG dialout "$USER"
```

## The REPL

```bash
mpremote connect /dev/ttyACM0 repl
```

| Keys | Effect |
|---|---|
| **Ctrl-C** | Stops OreoOS (the badge's `main.py`) and gives you the `>>>` prompt |
| **Ctrl-D** | Soft reset: restarts OreoOS from `main.py` |
| **Ctrl-]** | Leaves `mpremote`; the badge stays where it was |

While you are at the prompt, OreoOS is stopped and the screen and buttons do
not respond. Press **Ctrl-D**, or the board's **RST** button, to start it again.

Some things to try at the prompt:

```python
from oreoOS import config, storage
config.VERSION                  # OreoOS version
storage.usage()                 # free space, and what system, apps, gallery and documents use

from oreoOS import store        # the App Store, from code
store.refresh()
store.install("racer")          # returns (ok, message)
```

`mpremote` also stops OreoOS when it runs a command, and most commands (`fs`,
`run`, `exec`) leave the badge at the prompt. Run `mpremote connect
/dev/ttyACM0 reset` afterwards to restart OreoOS.

## Files on the badge

| Path | What it holds |
|---|---|
| `/main.py` | Boot entry point: starts the launcher and reboots after a crash |
| `/oreoOS/` | The OS: launcher, home screen, App Store, OTA, HTTP server |
| `/oreoWare/` | Hardware drivers: display, buttons, IMU, Wi-Fi, Bluetooth, IR |
| `/apps/<name>/` | Installed apps, built-in and from the App Store |
| `/apps/gallery/assets/optimized/` | Photos (`.rz565`) and videos (`.rv565`) shown in Gallery |
| `/documents/` | Markdown and text for the Reader app |

`./deploy --board` keeps this layout in sync with the repository. Photos,
documents and Store apps that were added on the badge are kept unless you pass
`--override`.

## Copying files

```bash
mpremote connect /dev/ttyACM0 fs ls :                 # list the root
mpremote connect /dev/ttyACM0 fs ls :apps
mpremote connect /dev/ttyACM0 fs cp notes.md :documents/notes.md
mpremote connect /dev/ttyACM0 fs cp :apps/racer/main.py .     # badge → computer
mpremote connect /dev/ttyACM0 fs rm :documents/notes.md
mpremote connect /dev/ttyACM0 fs cp -r my_app :apps/          # a whole app folder
mpremote connect /dev/ttyACM0 reset                           # restart OreoOS
```

`mpremote` sends files through the REPL in small chunks, which takes minutes
for a few megabytes. That's fine for code. For media, use one of these two:

**Convert, check and copy, over USB:** `tools/media_ingest.py` converts the
file to the badge's format, checks it fits in the free space, and copies it
into Gallery or Reader:

```bash
python3 tools/media_ingest.py photo.jpg --to-board --port /dev/ttyACM0
python3 tools/media_ingest.py clip.mp4 --seconds 6 --to-board --port /dev/ttyACM0
```

Video defaults to 180×135 at 24 FPS. See [`MEDIA_INGESTION.md`](MEDIA_INGESTION.md).

### Large files: Send Files over Wi-Fi

This is faster than USB for photos and videos, and needs no tools on the
computer:

1. On the badge, open **Settings → WiFi** and press **A** for **Send files**.
   The badge must be on Wi-Fi; it shows a six-character code.
2. On a computer or phone on the **same Wi-Fi network**, open
   [oreo.elixpo.com/upload](https://oreo.elixpo.com/upload) and enter the code.
3. The sender appears on the badge: select it and press **A** to approve.
4. Pick the files. The browser converts photos and videos to the badge's
   formats before uploading, and they appear in Gallery or Reader.

The same page can send the badge a Wi-Fi password ("Share a WiFi network"),
since the badge has no keyboard.

## Running code without installing it

```bash
mpremote connect /dev/ttyACM0 run hello.py               # run a file from the computer
mpremote connect /dev/ttyACM0 exec "import os; print(os.listdir('apps'))"
mpremote connect /dev/ttyACM0 mount .                    # the computer's folder appears as /remote
```

`mount` is the quickest way to try an app while you write it: the badge reads
your files straight from the computer, so there is nothing to copy after each
edit.

## Installing an app

- **On the badge:** open the **App Store** tile, pick an app and install it.
- **From the REPL:** `store.install("<name>")`, as above.
- **Your own app:** copy its folder (`main.py`, `manifest.json`, `__init__.py`,
  `src/`, `assets/`) to `:apps/<name>/` with `fs cp -r`, then reset. To start
  one, copy [`app_templates/`](../app_templates/); writing apps is covered in
  [`CONTRIBUTING.md`](../CONTRIBUTING.md).

## Updating and reinstalling OreoOS

| Command | What it does |
|---|---|
| `./deploy --board` | Uploads changed OS files only (it remembers what it sent) |
| `./deploy --board --clean` | Wipes the badge's filesystem and reinstalls OreoOS |
| `./deploy --full` | Reflashes the MicroPython firmware, then installs OreoOS clean |
| `./build-firmware --flash` | Rebuilds the firmware from source, then runs `./deploy --full` |

`./deploy --board` raises OreoOS's patch version (`oreoOS/config.py`) on every
run. Add `--no-bump` when you are only testing. Pass `--port <device>` if the
badge is not `/dev/ttyACM0`.

Without a computer, the badge updates itself from GitHub releases: small
patches install automatically, and larger ones ask first (the **Updates** page).

`--full` and `./build-firmware --flash` erase everything on the badge,
including photos, documents and Store apps.

## Troubleshooting

| Problem | Fix |
|---|---|
| No `303a:83ec` in `lsusb` | Use the port labelled **USB**, not **UART**, and a data cable (some are charge-only) |
| "failed to access … (it may be in use)" | Another program has the port open: close other `mpremote` sessions, serial monitors and the Arduino IDE |
| "permission denied" on Linux | Add yourself to `dialout` (see [Finding the port](#finding-the-port)) |
| Screen frozen after using `mpremote` | OreoOS is stopped at the prompt: `mpremote connect <port> reset`, or press **RST** |
| Badge keeps showing **OREO CRASHED** and rebooting | Connect and press **Ctrl-C** during the restart to reach the prompt; read the error printed above the prompt, then reinstall with `./deploy --board --clean --no-bump` |
| `esptool` cannot connect when flashing | Hold **BOOT**, tap **RST**, release **BOOT**, then run the command again. The badge then waits in download mode until you reset it |
| The port name changed | Normal after a reset or reconnect: run `mpremote devs` again |

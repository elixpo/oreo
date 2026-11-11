# AGENTS.md

Guide for coding agents (and people) working in this repository.

OreoOS is a MicroPython 1.28 operating system for the Oreo badge, an
ESP32-S3 board with a 320x240 ST7789 screen, eight buttons, an IMU, IR,
Wi-Fi and Bluetooth. Apps are Python packages the OS loads at runtime.

## Map

| Path | What |
|---|---|
| `oreoOS/` | The OS: launcher and run loop, home screen, App Store, OTA, network service, shared helpers (`api`, `theme`, `widgets`, `state`, `profile`, `crashlog`, `cache`, `github`, `timeutil`). |
| `oreoWare/` | Hardware drivers (display, buttons, Wi-Fi, BT, IMU, IR) and `os.py`, the object passed to apps. |
| `apps/` | Built-in apps, installed on every badge. |
| `apps_market/` | Optional apps the on-device App Store installs; `index.json` is the catalogue. |
| `app_templates/` | The starting point for a new app. |
| `cli/` | The `oreo` command-line tool that talks to the badge over USB. |
| `tools/` | Host scripts: deploy, release, asset conversion, `validate_app.py`, `app_icon.py`, `build_store_index.py`. |
| `tests/` | Hardware-free unit tests (standard library only). |
| `firmware/` | The MicroPython firmware build (native modules, partition table). |
| `docs/` | Guides: [APPS.md](docs/APPS.md), [PROFILE.md](docs/PROFILE.md), [CLI.md](docs/CLI.md), [HARDWARE.md](docs/HARDWARE.md). |

## Building an app

Read [docs/APPS.md](docs/APPS.md). In short:

```bash
cp -r app_templates apps_market/my_app
# edit manifest.json and src/app.py
python3 tools/app_icon.py apps_market/my_app      # icon.png -> icon module
python3 tools/validate_app.py apps_market/my_app
python3 tools/build_store_index.py                # App Store apps only
```

Rules that matter on the badge:

- Subclass `oreoOS.App`; implement `on_enter`, `update(dt)`, `draw(d)`,
  `on_button_press(btn)`, `on_exit`. Never call `d.present()`.
- Nothing in `update`/`draw` may block. Network calls go through
  `oreoOS._http` with a timeout, on a worker (`oreoOS.cache.Refresh`).
- Use `api.BTN_SELECT` (A) to confirm, `api.BTN_BACK` (B) to go back;
  HOME belongs to the OS; C opens the panel unless `CAPTURES_C = True`.
- Persist with `oreoOS.state.load/save`, not files in the app folder.
- Read the owner's details with `oreoOS.profile.get`, not `secrets`.
- Prefer the `os` object over importing `oreoWare` or `machine` (#67).
- MicroPython 1.28: no `abc`, `typing`, `dataclasses`, `pathlib`; small
  heap, so avoid large lists and module-level buffers.

## Checks

```bash
python3 -m unittest discover -s tests          # OS and app tests
python3 -m unittest discover -s cli/tests      # the oreo CLI
python3 tools/validate_app.py                  # every app
```

If you have MicroPython's `mpy-cross` (v1.28), compile-check badge files
with it too. Add a host test in `tests/` for logic you change; load
modules by path (see `tests/test_app_platform.py`) so the hardware
imports in `oreoOS/__init__.py` are not needed.

## Do not

- Commit secrets. `.env` is SOPS-encrypted; personal values go in the
  git-ignored `.env.local` or on the badge in `/profile.json`. Do not
  read or print `.env`, `.env.local` or `secrets.py`.
- Hardcode a person's GitHub user, name, location or timezone.
- Use Wi-Fi for anything but the internet. File transfer and Wi-Fi setup
  go over USB with the `oreo` CLI. Bluetooth features come last (#124).
- Run the deploy or flashing tools against a badge unless the user asked.

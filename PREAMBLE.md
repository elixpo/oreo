# OreoOS: a preamble

This is the first document to read about OreoOS. It says what the system is,
the rules it is built by, how it is put together, and where the rest of the
documentation lives. It is meant to be read once, top to bottom, before
reading code.

## What OreoOS is

OreoOS is the operating system of the Oreo Badge, an open conference badge.
It is written in MicroPython (version 1.28) and runs on an ESP32-S3 with
16 MiB of flash and 8 MiB of PSRAM, a 2.0" 320x240 ST7789 screen, eight
buttons, an IMU, an infrared transceiver, Wi-Fi and Bluetooth.

It is an operating system in the sense that matters on a device this size:
it owns the screen, the buttons, the network, storage and power, and it runs
applications that it loads at runtime. Applications are ordinary Python
packages that subclass `oreoOS.App`, draw through the OS, and never touch the
hardware directly when the OS offers a way to do it. About 39,000 lines of
Python make up the OS, its drivers and the apps that ship with it; the rest of
the badge's software is the firmware build (MicroPython with native modules),
the `oreo` command-line tool, and the RV565 video library.

The hardware is certified open source hardware by OSHWA (UID IN000107). The
code is MIT, the hardware CERN-OHL-P-2.0, the artwork CC-BY-4.0.

## The rules it is built by

These rules decide most design questions before they come up. They are
restated in [`AGENTS.md`](AGENTS.md), which every change is checked
against.

1. **The badge works on its own.** Nothing on the badge waits on the network
   or blocks the screen. Slow work runs on a worker, and the user sees a
   loading state.
2. **Wi-Fi is for the internet only:** the App Store, OTA updates, GitHub
   data, weather and time. Nothing listens on the local network.
3. **A computer reaches the badge over USB,** through the `oreo` CLI. Files go
   through the Transfer app, guarded by a code shown on the badge.
4. **Bluetooth comes last,** together with the mobile app.
5. **The OS and the CLI ship together and must agree.** A change on one side
   of a contract changes the other side, its tests and its docs at once.
6. **No personal data in the code.** The owner's name, GitHub user and
   location come from the owner's profile, never from the source.
7. **Every change is tested without hardware.** Host tests stand in for the
   badge; whatever only a badge can show is written down as a test step.

## How it is put together

From the bottom up:

| Layer | Where | What it does |
| --- | --- | --- |
| Firmware | [`firmware/`](firmware/) | MicroPython 1.28 for the `OREO_BADGE` board, with native modules for infrared and RV565 video |
| Drivers | [`oreoWare/`](oreoWare/) | Display, buttons, Wi-Fi, Bluetooth, IMU, infrared, and `os.py`, the object handed to apps |
| OS | [`oreoOS/`](oreoOS/) | Launcher and run loop, home screen, notification panel, App Store, OTA updates, network service, and the shared helpers apps use (`theme`, `widgets`, `state`, `profile`, `cache`, `busy`) |
| Apps | [`apps/`](apps/), [`apps_market/`](apps_market/) | The apps every badge has, and the optional ones the App Store installs |
| Host tools | [`cli/`](cli/), [`tools/`](tools/) | The `oreo` CLI, deploy and release tools, the app validator |

**The run loop.** The launcher owns the frame. Each tick it delivers button
events to the foreground app, calls its `update(dt)`, then its `draw(d)`, and
presents the frame itself; apps never call `present()`. HOME belongs to the
OS. Nothing inside `update` or `draw` may block: network requests go through
the OS's HTTP layer on a worker, with a timeout, and long work shows a busy
state.

**State and profile.** Apps persist through `oreoOS.state`, not files in their
own folder, so updates can replace an app without losing its data. The
owner's details come from `oreoOS.profile`.

**Updates.** OTA updates come from GitHub Releases on the `stable/` and
`beta/` channels, over TLS with certificate verification.

**Video.** The Gallery plays RV565, a video format designed for this badge:
frames are stored in the panel's own pixel format, so the device only
inflates and transfers, and partial deltas send only the rows that changed.
It is published as its own library and described in a paper
(arXiv:2610.35935).

## The contracts with the CLI

The badge and the `oreo` CLI agree on profile keys, the list of built-in
apps, the app checks, the app template, the Transfer protocol, the
"connected to computer" screen and the USB identity (`303a:83ec`). Each
contract has a guard test on both sides; the table is in
[`AGENTS.md`](AGENTS.md). A newer CLI must keep working with the previous
OS release.

## Where to go next

- Writing an app: [`APPS.md`](docs/APPS.md).
- Using the badge from a computer: [`USB.md`](docs/USB.md), [`CLI.md`](docs/CLI.md),
  [`TRANSFER.md`](docs/TRANSFER.md).
- The hardware: [`HARDWARE.md`](docs/HARDWARE.md), [`DATASHEET.md`](docs/DATASHEET.md).
- A guided tour of the code: [`LEARN.md`](docs/LEARN.md).
- How the project is run: [`GOVERNANCE.md`](docs/GOVERNANCE.md),
  [`SECURITY.md`](docs/SECURITY.md), [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Dedication

Every system has a reason it was finished. This one is dedicated to A., for
its full runtime: the second author of the video format the Gallery plays,
who read every frame of it before anyone else did. Her name is in the poem
below, one letter at the start of each line.

> At power-on the panel's dark, the clock is still unset;<br>
> No Wi-Fi and no promises: the badge boots up, and yet,<br>
> When every frame is written, only what has changed goes through;<br>
> Each band we never touched stays still, a format made by two.<br>
> So every deadline that we keep is measured, line by line, and true;<br>
> Heap and stack and every task this kernel spawns belong to you,<br>
> And when the watchdog bites at last, it's you I'm booting to.

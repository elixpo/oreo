# OreoOS status roadmap

Goal: OreoOS is recognised as *the* operating system of the Oreo Badge, by
the computers it is plugged into and by the places the ESP32 and MicroPython
communities trust, not only on our own site.

What "official" can mean for a microcontroller OS:

- **Identity:** what a computer shows when the badge is plugged in (USB
  manufacturer and product names, serial-port names, the boot banner).
- **Installation:** installable in one click from trusted tools.
- **Listing:** present in the registries and indexes people search.
- **Adoption:** shipped on badges at events, used and cited by others.

Legend: 🤖 Claude prepares it (code, PR, draft) · 🙋 needs Ayushman (account,
hardware, build/flash, or a decision).

---

## Level 1: identity and installation

### 1.1 The badge introduces itself as "Oreo Badge"

- [x] 🤖 MicroPython board definition `firmware/boards/OREO_BADGE`: the exact
      ESP32_GENERIC_S3 + SPIRAM_OCT configuration (flash layout and behaviour
      unchanged) plus USB manufacturer "Elixpo", product "Oreo Badge", board
      name "Oreo Badge" (boot banner, `os.uname()`) and hostname `oreo`.
- [x] 🤖 `./build-firmware` builds it and checks the identity is in the image;
      the deployable image is now `oreoWare/firmware/OREO_BADGE-v1.28.0.bin`.
- [ ] 🙋 Build (`./build-firmware --clean`), flash (`./deploy --full`), and
      confirm: `ls /dev/serial/by-id/` shows `usb-Elixpo_Oreo_Badge_…`, and the
      REPL banner ends `Oreo Badge with ESP32S3`. Commit the new image.

### 1.2 One-click install from the browser

- [ ] 🤖 "Install OreoOS" button on oreo.elixpo.com using ESP Web Tools (Chrome
      and Edge, Web Serial): flashes the firmware, then the OS files.
- [ ] 🤖 Decide the image: a full flash image with the filesystem included, or
      firmware plus first-boot download of the OS through the existing OTA path.
- [ ] 🙋 Test on a wiped badge.

### 1.3 Release assets people and tools can trust

- [ ] 🤖 Each GitHub release carries the firmware image, the full flash image
      and SHA-256 checksums, built by CI from the tagged commit.
- [ ] 🤖 Release notes generated from the changelog.

---

## Level 2: listed where people look

- [ ] 🤖 **awesome-esp**, *Firmware* section, and **awesome-micropython**
      (one-line PRs, disclosed as our own).
- [ ] 🤖 **Wikidata** item "OreoOS": instance of operating system, based on
      MicroPython, platform ESP32-S3, citing arXiv:2610.35935.
- [ ] 🙋 **Hackaday.io** project page with photos, the badge video, and links.
- [ ] 🤖 **MicroPython upstream board** (`micropython/micropython`,
      `ports/esp32/boards/ELIXPO_OREO_BADGE`), so the badge appears on
      micropython.org/download with automatically built firmware. Maintainers
      mostly accept boards other people can obtain, so send it once badges or
      the open design are in other people's hands; the definition above is
      written to be submitted as is.
- [ ] 🤖 **Own USB PID** under Espressif's VID (`espressif/usb-pids`). Only
      worth requesting when OreoOS adds its own USB function (for example
      mass storage for the Gallery, or WebUSB file transfer): Espressif grants
      PIDs for custom USB classes, and standard serial already works under the
      default PID. With a PID, the badge can then be named in the Linux USB ID
      database (`usb.ids`), so `lsusb` shows "Elixpo Oreo Badge" everywhere.

## Level 3: adoption

- [ ] 🙋 Ship OreoOS on badges at an event (the way EMF Camp's Tildagon and
      the Hackaday Supercon badges became known).
- [ ] 🤖 Systems paper on OreoOS (app model, OTA, on-badge security, RV565
      integration), cross-cited with the RV565 paper.
- [ ] 🙋 Talks: MicroPython meetups, Hackaday Supercon, PyCon.

---

## What does not apply

- **A Linux kernel or "OS registry" PR.** OreoOS runs on MicroPython over
  ESP-IDF/FreeRTOS on the ESP32-S3, not on Linux, and there is no central
  list of operating systems for microcontrollers. The upstream that matters
  is MicroPython (board definition) and Espressif's programmes (USB PID).
- **Espressif's ESP-IDF repository.** It does not list third-party operating
  systems; the Espressif routes are the Developer Portal (articles) and the
  ESP Component Registry (libraries, where RV565 already is).

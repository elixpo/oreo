# Changelog

Each release of OreoOS gets its own section here. The CI release
workflow lifts the **top section** verbatim into the GitHub release's
`body` field — that's exactly what the Updates app surfaces as the
in-device changelog when an upgrade is available.

Format for a new entry (add to the top, push, CI does the rest):

```
## vX.Y.Z — YYYY-MM-DD
- Short bullets, present tense (e.g. "Fix Store hang at LOADING").
- Group bullets loosely by surface: OS, Apps, Drivers, Tooling, Docs.
- Keep technical, no marketing language.
```

---

## v2.0.0 — 2026-11-07

Diwali release: the App Store, a smoother shell, Wi-Fi handoff and Patakha.

- **App Store** (was Store): Discover page with a featured card, icons, taglines, categories, sizes and Install / Open / Update; app pages; B opens Installed, where apps uninstall after a confirm step and reinstall from Discover. The catalogue is one file (apps_market/index.json), cached on the badge and refreshed in the background. Installs stream into a staging folder and swap in only when complete; updates keep an app's saved files.
- **Smaller default image**: About, Badge, Commits, Gallery, Gamepad, Identity, Reader, Settings, App Store and Storage (plus Launcher, Updates and Wi-Fi). Bluetooth, Doom, Flappy, Gestures, IR Quest, Racer, Snake, Weather, Pet and Colors install from the App Store.
- **Doom from the App Store**: the engine stays in firmware; the App Store downloads the Freedoom data into the doom partition, checking size and SHA-256 before it activates.
- **Patakha** (new, App Store): Diwali firecracker shooter with firework bursts, speed-ups every 100 points, rocket barrages at 250/500/1000 and a UFO power-up (#97).
- **Shell**: new splash with the logo top left and "hello" rolling through 16 languages in their own scripts (anti-aliased Inter / Noto Sans, pre-rendered), on its own thread so it never freezes while the OS loads; eased scrolling and partial redraws in the apps grid, home and lists; full-height notification panel with Torch (white screen, Home returns) and Update tiles.
- **Wi-Fi**: boot connects in the background and never blocks the splash; the Wi-Fi page scans live with progress, signal bars and lock icons, shows connect progress with clear failure reasons, and lists Saved networks to join or forget. A paired phone or laptop can send the badge a new network's password from the Send Files page.
- **Faster transfers**: larger buffers and fewer flash writes for LAN uploads; OTA patches stream to flash over a reused connection; deploys batch flash writes.
- **Bluetooth**: status page and stalled-transfer reset; docs/BLUETOOTH.md documents what works today and the next steps.
- **Notification panel over apps that use C** (Wi-Fi's nearby rescan, Pet, Bluetooth): single C goes to the app, double-tap C opens the panel.
- **Fixes**: App Store apps show their own icon in the launcher after install; Patakha has a dimmer sky, a bigger launcher, tilt steering by default and a harder curve; Racer traffic can spawn kerb to kerb, so hugging the edge no longer avoids crashes; IR Quest arms RMT RX on the ESP32-S3 (glitch filter within the S3 limit, #48), every tab shares one receive lifecycle, errors show in full, new DIAG tab (needs the new firmware); Gamepad's C no longer opens the notification panel; About and Badge open instantly from cache and refresh in the background.
- **Tooling**: OTA releases now ship apps' src/ code; tools/build_store_index.py builds and checks the catalogue.

## v1.4.19 — 2026-05-16

- **Fix**: Updates page no longer hangs forever — OTA's `check`,
  `peek`, and `download` now use the raw-socket helper instead of
  `urequests`, with `settimeout` correctly applied after the SSL
  wrap and a hard wallclock backstop.
- **Fix**: Time-sync no longer freezes the device for 15+ seconds —
  `timeutil.sync_from_ntp()` is now a 30-line raw UDP exchange with a
  2.5 s socket timeout (replaces `ntptime.settime()`).
- **Refactor**: Pulled the HTTP helper into `oreoOS/_http.py` so OTA
  + Store share one implementation (single place to fix bugs).
- **Updates UX**: New layout — `OREO OS <version>` header, animated
  "CHECKING …" loader, two side-by-side buttons (`INSTALL` +
  `CHANGELOG`) when an update is found, "Up to date — LTS YYYY-MM-DD"
  card otherwise. The changelog button opens a scrollable sub-page
  showing the GitHub release's body verbatim.

## v1.4.x — earlier patches

See the git log; this CHANGELOG was started at v1.4.19.

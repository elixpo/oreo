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

## Unreleased

- **Every press answers at once; opening an app no longer looks frozen**: the frame of the press draws an "Opening <name>" chip, and an open that is not done within 120 ms shows the LOADING panel (name, author, spinner) until the app's first frame, covering the import (MicroPython compiles the app's source on every open) as well as on_enter. Quick opens show no panel; an app that took over 250 ms last time gets it at once; HOME on the panel cancels; a failing import or on_enter shows the crash screen. The old blocking 240 ms slide is gone, so SHOW_LOADING apps open faster too. New module `oreoOS/opening.py`.
- **Faster first drawer open and return to Home**: the apps drawer is imported and its icons built behind the boot splash, and going back to Home no longer re-reads every manifest.json. Each open logs `[open] <app>: N ms (import, on_enter, first frame)` on the USB console.
- **Apps**: Reader shows a card while a long document is read and laid out; Storage shows one while A recounts the files; Gallery no longer runs a full garbage collection on every photo step.
- **Tooling**: `oreo run tools/app_open_probe.py` times, per app, the import (and how much is compiling), on_enter, the first frame and the heap it uses.

- **A bigger avatar on the Badge app**: the owner's GitHub avatar now fills the 72 px disc edge to edge (it was 56 px with a margin), inside a 2 px ring instead of 3. Run `oreo setup --avatar` with the updated CLI to fetch the larger picture; a 56 px avatar from before still shows, smaller.
- **tools/release.py publishes to the repository badges update from** (#134): the repository comes from `OTA_REPO` in oreoOS/ota.py, or `--repo owner/name`, and is used for the manifest's download URLs and every `gh release` command; `--dry-run` shows it. A fork no longer edits release.py. A release stops when `origin`, where the tag is pushed, is another repository.
- **Badge shows its owner's avatar, not the maintainer's** (#133): no avatar ships with OreoOS any more. `oreo setup` fetches the avatar of the profile's GITHUB_USER on the computer and copies it over USB to /avatar.bin (outside the app folders, so updates keep it), and Badge shows it only while that user is GITHUB_USER; otherwise it draws the owner's initials. Badge deletes the old shipped avatar module, deploys remove it, and deploy and release builds never include it. tools/fetch_avatar.py now writes the same /avatar.bin file, sharing the CLI's code.
- **Verified HTTPS** (#110): every TLS connection (OTA, App Store, GitHub data, location, weather, speed test) now checks the server's certificate chain, host name and dates against 10 bundled root CAs (`oreoOS/tls_roots.py`, loaded on the first secure request). The clock is synced over NTP first; a connection whose certificate or clock can't be checked is refused, never retried unverified. Updates, App Store, Commits and Weather show the reason (`TLS: untrusted certificate`, `TLS: clock not set`, ...). Docs: docs/TLS.md; badge check: `oreo run tools/tls_probe.py`.
- **Tooling**: `tools/gen_ca_bundle.py` regenerates the root bundle and `--check-hosts` verifies every host against it.

## v2.0.0 — 2026-11-07

Diwali release: the App Store, a smoother shell, Wi-Fi handoff and Patakha.

- **App Store** (was Store): Discover page with a featured card, icons, taglines, categories, sizes and Install / Open / Update; app pages; B opens Installed, where apps uninstall after a confirm step and reinstall from Discover. The catalogue is one file (apps_market/index.json), cached on the badge and refreshed in the background. Installs stream into a staging folder and swap in only when complete; updates keep an app's saved files.
- **Smaller default image**: About, Badge, Commits, Gallery, Gamepad, Identity, Reader, Settings, App Store and Storage (plus Launcher, Updates and Wi-Fi). Bluetooth, Flappy, Gestures, IR Quest, Racer, Snake, Weather, Pet and Colors install from the App Store.
- **Doom removed**: the engine is gone from the firmware and the game from the App Store, and its 7 MB flash partition now belongs to the filesystem (about 13.7 MB, was 6.7 MB). This takes effect after a full flash: `./deploy --full` erases the badge, while OTA updates keep the old partition table.
- **Patakha** (new, App Store): Diwali firecracker shooter with firework bursts, speed-ups every 100 points, rocket barrages at 250/500/1000 and a UFO power-up (#97).
- **New look**: dark wallpaper on the splash and a light liquid-glass wallpaper on Home (full 320x240). The splash shows the logo top left, "hello" rolling through 16 languages three times a second in their own scripts (anti-aliased Inter / Noto Sans) and a loader, runs on its own thread so it never freezes while the OS loads, and hands over to Home with a swipe of big chevrons in the light wallpaper's colours.
- **Shell**: eased scrolling and partial redraws in the apps grid, home and lists; full-height notification panel with Torch (white screen, Home returns) and Update tiles.
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

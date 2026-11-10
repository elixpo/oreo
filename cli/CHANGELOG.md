# Changelog

All notable changes to the `oreo` CLI (`oreo-cli`, in `cli/`) are recorded
here. OreoOS itself is versioned and released separately (`stable/v*` tags).

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the CLI uses [semantic versioning](https://semver.org/). Releases are
tagged `cli-v<version>`; the release workflow takes the notes for a release
from its `## [<version>]` section below, so every release needs one.

## [Unreleased]

## [0.1.0] - 2026-11-10

First release (#117). Not yet tested against a real badge; please report
problems with `oreo doctor` output attached.

### Added

- `oreo` finds the badge by its USB ID `303a:83ec` and picks it when exactly
  one is connected; `--port` or `$OREO_PORT` overrides this.
- `oreo devs [--all]` lists badges (and other USB serial devices) without
  opening a port.
- `oreo info`: OreoOS and MicroPython versions, board, space by category,
  Wi-Fi, Bluetooth boot setting, battery and free RAM.
- Files: `oreo ls`, `push` (folders with `-r`), `pull` and `rm`. Pushes go
  to a temporary `.part` file, are renamed into place and checked by size
  and SHA-256; free space is checked first. `rm` refuses OreoOS's own files
  and anything inside its folders (`/oreoOS`, `/oreoWare`, `/assets`, the
  built-in apps) without `--force`, and `rm -r` asks first.
- `oreo add`: photos and videos into the Gallery (`.rz565` / `.rv565`),
  `.md` / `.txt` into the Reader (`.mdz` / `.txtz`), after a space check.
  Videos need `ffmpeg`.
- `oreo apps [list|refresh|install|update|remove]` through the badge's App
  Store, over the badge's Wi-Fi.
- `oreo wifi [scan|connect|saved|forget]`. Passwords are read without echo
  (or with `--password-stdin`), sent to the badge once, and never printed,
  logged or stored on the computer.
- `oreo shell`, `oreo run <file>`, `oreo dev <folder> [--run FILE]` and
  `oreo logs [--restart]`.
- `oreo doctor`: pyserial and mpremote versions, the badge's USB ID, other
  known IDs (stock ESP32-S3 JTAG port, download mode, CP210x / CH340),
  Linux `dialout` / `uucp` membership and the firmware banner.
- `oreo update --repo <checkout>` and `oreo flash --repo <checkout>` run the
  checkout's `./deploy`; erasing always asks first.
- The interactive view (`oreo` with no command): status, files, apps,
  Wi-Fi, media and shell.
- OreoOS is restarted after every command (`--reset soft|hard|none`),
  also when the command is stopped with Ctrl-C.
- Output falls back to ASCII marks on a console or pipe that is not UTF-8
  (for example a redirect on Windows) instead of crashing.
- Release packaging: wheel and sdist on GitHub Releases with SHA-256
  checksums and build-provenance attestations, and `install.sh` /
  `install.ps1`, which verify the checksum and install with pipx or uv.

### Known limitations

- `oreo update` and `oreo flash` need an OreoOS checkout (`--repo`);
  updating from GitHub releases is future work.
- No Bluetooth transfers yet (#103).

[Unreleased]: https://github.com/elixpo/oreo/compare/cli-v0.1.0...HEAD
[0.1.0]: https://github.com/elixpo/oreo/releases/tag/cli-v0.1.0

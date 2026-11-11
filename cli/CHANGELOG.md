# Changelog

All notable changes to the `oreo` CLI (`oreo-cli`, in `cli/`) are recorded
here. OreoOS itself is versioned and released separately (`stable/v*` tags).

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the CLI uses [semantic versioning](https://semver.org/). Releases are
tagged `cli-v<version>`; the release workflow takes the notes for a release
from its `## [<version>]` section below, so every release needs one.

## [Unreleased]

### Added

- A full-screen view: `oreo` with no command (and the new `oreo ui`)
  switches the terminal to an Oreo app on the alternate screen, built with
  Textual. A header shows the badge, port, OreoOS version and whether
  OreoOS is paused; a sidebar has Status, Files (browse, upload, download,
  add media, delete), Apps (App Store fetch, install, update, remove),
  Wi-Fi (scan, connect, forget), Transfer (with the code the badge shows),
  Profile (`oreo setup`, also from an `.env`-style file), Install app (from
  a folder) and Update OreoOS, and **s** opens the REPL and comes back.
  Every badge operation runs in the background with a spinner or progress
  bar, one command on the serial port at a time; Esc cancels copies,
  downloads, installs and Transfer between two chunks (removing a half
  copy), and interrupts scans on the badge. It waits for a badge to be
  plugged in and asks which one when there are several. OreoOS stays paused
  while the view is open and restarts when it closes, also on Ctrl-C and on
  errors. It reuses the commands' own code, so behaviour matches them.
- `oreo menu`: the numbered menu. `oreo` falls back to it where the
  full-screen view cannot run (no terminal, `TERM=dumb`, Textual missing)
  or when `OREO_UI=menu` is set; `oreo ui` explains instead.
- The badge's screen shows long operations: `push`, `pull`, `add`,
  `app install`, `apps install`/`update` and `update` (and the same in the
  view) call `oreoOS/hostui.py` (`show(title, detail, progress)`, `clear()`)
  on OreoOS versions that have it. The calls ride along with execs the CLI
  sends anyway, so a push costs no extra round trips; an OreoOS without it,
  or a failure inside it, changes nothing.
- Dependency: `textual >= 8.2, < 9` (imported only when the view opens).
- `oreo setup --from-file FILE` takes the profile keys from an `.env`-style
  file such as `.env.local` (other keys are left alone and only named), and
  `--set KEY=VALUE` sets one key at a time by its `.env` name.
- The title is `DISPLAY_DESIGNATION`, as in `.env.local`; `DESIGNATION` is
  still accepted.
- `oreo setup`: the owner profile (GitHub user, name, title, timezone,
  weather place and OpenWeatherMap key) in `/profile.json` on the badge, the
  file `oreoOS/profile.py` reads (docs/PROFILE.md). It shows the current
  values and where they come from, prompts for each one (or takes them as
  options), checks the ranges before touching the badge, never echoes or
  prints the key (the badge only reports whether one is set), merges and
  writes atomically through `/profile.json.tmp` (the backup the badge falls
  back to), and restarts OreoOS.
  `oreo setup --show` prints the profile with the key hidden;
  `--owm-key-stdin` reads the key from standard input.
- `oreo new <name>`: a new app folder from the app template, which now ships
  inside oreo-cli, with the id, display name, author and icon module filled
  in.
- `oreo app install <folder>`: checks an app folder with the same rules as
  `tools/validate_app.py` (vendored; a test keeps them identical), refuses
  built-in apps without `--force`, copies only the files that belong on the
  badge to `/apps/<id>/` with the verified push, removes files left from an
  earlier install and restarts OreoOS. `oreo app list` and
  `oreo app remove <id>` too.
- Interactive view: **t** sends files to the Transfer app (the
  `oreo transfer send` flow), **p** edits the owner profile, **i** installs
  an app from a folder.

### Changed

- `oreo dev` explains how live editing relates to OreoOS: the REPL imports
  from `/remote`, modules are imported once, OreoOS does not run meanwhile,
  and its drawer lists apps from `/apps`, so apps are tried with
  `oreo app install`.

## [1.0.0] - 2026-11-11

First stable release. Commands, options, output and exit codes are now
stable: later 1.x releases add to them but do not change them. Like 0.1.0,
it is tested against a simulated badge; the on-badge checks are listed in
docs/CLI.md ("Testing on a badge").

### Added

- `oreo transfer send <files>` (alias `oreo send`), `oreo transfer list` and
  `oreo transfer rm`: send files to the badge's new Transfer app over USB,
  authorised by the six-character code the badge shows. OreoOS keeps
  running; files are converted like `oreo add` and checked on the badge
  with SHA-256 before they are saved.
- `oreo update` works without a checkout. The badge downloads the newest
  OreoOS release from GitHub over its own Wi-Fi, through its own updater
  (`oreoOS.ota`, the same code as its Updates page). The CLI shows the
  installed and new versions and the download size, asks, checks the free
  space, shows download progress, installs, restarts the badge, waits for
  it to come back on USB (also under a new port name) and reports the
  version it booted. `--check` only reports; `--channel beta` follows the
  beta channel. An update the badge already downloaded is offered for
  installing. Ctrl-C is held while files are moved into place.
  `--repo <checkout>` remains for developers.
- Exit status 4 (the badge could not be reached: port busy or missing, no
  answer, connection lost) and 5 (OreoOS missing on the badge, or too old
  for the command); usage errors such as a missing app or network name now
  exit with 2. All codes are listed in `oreo --help` and docs/CLI.md.
- The interactive view: **u** updates OreoOS; the file view uploads a file
  into the folder shown (`u <path>`) and asks before overwriting a local
  file on download; Ctrl-C stops the current action and returns to the menu.
- `oreo doctor` ends with numbered next steps (failures first), checks for
  ffmpeg, and says when the badge answers but has no OreoOS.
- `oreo logs` keeps following across a badge restart or replug, and decodes
  the console as UTF-8 for any terminal.
- `oreo-cli` is installed as a second name for the `oreo` command.

### Changed

- Pushes are verified before they replace anything: the badge checks the
  size and SHA-256 of the `.part` file and only then renames it into place,
  so a damaged copy leaves the old file untouched (0.1.0 checked after the
  rename).
- Pushes need fewer round trips: the first chunk rides with the open and
  the last with the check-and-rename, folders are created once per session
  and free space is checked once per command. A small file now costs 2
  execs instead of 6; 40 small files go from 240 execs to 81. Chunks are
  8 KiB instead of 4 KiB. Measurements and the model are in docs/CLI.md
  ("Transfer speed").
- `oreo wifi connect` checks the network name (1 to 32 bytes) and the
  password (8 to 63 characters, or 64 hex digits) before touching the badge,
  and refuses an empty `--password-stdin`.

### Fixed

- Unplugging the badge (or it rebooting) during a command printed a Python
  traceback; it is now "lost the connection to the badge" with a hint and
  exit status 4. Any other unexpected error is one line plus a link to
  report it (the traceback with `-v`).
- A badge busy with something that delays Ctrl-C is retried once before it
  is reported, with a hint, and mpremote's raw debugging output no longer
  leaks into ours.
- Blocking reads while sending code are bounded, so a badge that stops
  answering in the middle of a command cannot hang `oreo` forever.
- `oreo logs` could not be stopped with Ctrl-C on Windows while the badge
  was quiet.
- `oreo shell` and `oreo dev` without a terminal crashed inside mpremote;
  they now say they need one, before touching the badge.
- Port names: `com5` works on Windows, `/dev/tty.usbmodem*` is replaced by
  its `/dev/cu.*` twin on macOS (the tty one can hang on open), and a bare
  `ttyACM0` means `/dev/ttyACM0`.
- Badge paths rewritten by Git Bash (`/documents` becoming
  `C:/Program Files/Git/documents`) are refused with a hint to write
  `:documents` instead.
- `oreo pull <file> newdir/` created a file called `newdir`; it now creates
  the folder.
- The Wi-Fi signal bars and header separator fall back to ASCII on a
  terminal that is not UTF-8.
- A second Ctrl-C while OreoOS is being restarted no longer leaves the
  badge at the MicroPython prompt: the restart starts over and the port is
  closed only after the reboot request has been sent.
- `oreo logs` on a port that is busy in another program, or that you have
  no permission to open, says so (exit status 4) instead of waiting for
  the badge to "come back" forever.
- A file on this computer that cannot be read or written (`oreo push` of an
  unreadable file, `oreo pull` into a folder that cannot be created) is
  reported as "<path>: <reason>" with exit status 1, not as a lost badge
  connection.

### Known limitations

- `oreo flash` still needs an OreoOS checkout (`--repo`).
- File transfer over Bluetooth is not available yet (#103); Bluetooth comes
  last, with the mobile app.

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

[Unreleased]: https://github.com/elixpo/oreo/compare/cli-v1.0.0...HEAD
[1.0.0]: https://github.com/elixpo/oreo/releases/tag/cli-v1.0.0
[0.1.0]: https://github.com/elixpo/oreo/releases/tag/cli-v0.1.0

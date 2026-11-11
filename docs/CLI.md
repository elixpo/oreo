# The `oreo` command-line tool

`oreo` controls the Elixpo Oreo Badge from a computer over USB: status,
files, photos, videos and documents, apps, Wi-Fi, logs, a MicroPython shell,
OreoOS updates and firmware. It finds the badge by its USB ID (`303a:83ec`),
so you never have to guess `/dev/ttyACM0` or `COM5`.

The code lives in [`cli/`](../cli) (Python package `oreo-cli`, command
`oreo`). It is released separately from OreoOS, with tags `cli-v<version>`;
see [cli/CHANGELOG.md](../cli/CHANGELOG.md).

> **Status: 1.0.0, stable.** Commands, options, output and exit codes are
> stable: later 1.x releases add to them but do not change them. Every
> command is covered by host tests against a simulated badge, and the
> on-badge checks are listed in [Testing on a badge](#testing-on-a-badge).
> If something misbehaves, run `oreo doctor` and attach its output to an
> issue.

Contents: [Install](#install) · [First run](#first-run) ·
[Commands](#commands) · [Wi-Fi setup](#wi-fi-setup) ·
[Exit status](#exit-status) · [Transfer speed](#transfer-speed) ·
[Troubleshooting](#troubleshooting) · [Testing on a badge](#testing-on-a-badge) ·
[Releasing](#releasing)

## Install

You need Python 3.9 or newer and either [uv](https://docs.astral.sh/uv/) or
[pipx](https://pipx.pypa.io/). The installer picks one of them (pipx first),
downloads the release wheel and its `.sha256`, checks the SHA-256, and
installs `oreo` as an isolated tool. If neither is installed it tells you how
to get one and stops.

**Linux and macOS**

```sh
curl --proto '=https' --tlsv1.2 -LsSf \
  https://raw.githubusercontent.com/elixpo/oreo/main/cli/install.sh | sh
```

**Windows (PowerShell)**

```powershell
irm https://raw.githubusercontent.com/elixpo/oreo/main/cli/install.ps1 | iex
```

Run the same command again to upgrade: it replaces the installed version.

### Installer options

| Variable | Meaning |
|---|---|
| `OREO_CLI_VERSION` | Release to install: `latest` (default), or `cli-v1.0.0`, `v1.0.0`, `1.0.0` |
| `OREO_CLI_INSTALLER` | `pipx` or `uv` (default: pipx if present, else uv) |
| `OREO_CLI_REPOSITORY` | GitHub repository to install from (default `elixpo/oreo`) |
| `OREO_CLI_DOWNLOAD_BASE` | Fetch the wheel from this URL instead of the release (testing; needs a pinned version) |

Pin a version:

```sh
curl --proto '=https' --tlsv1.2 -LsSf \
  https://raw.githubusercontent.com/elixpo/oreo/main/cli/install.sh |
  OREO_CLI_VERSION=cli-v1.0.0 sh
```

```powershell
$env:OREO_CLI_VERSION = "cli-v1.0.0"
irm https://raw.githubusercontent.com/elixpo/oreo/main/cli/install.ps1 | iex
```

The repository's "latest" GitHub release is always OreoOS itself, so for
`latest` the installers look up the newest `cli-vX.Y.Z` tag through the
GitHub API (unauthenticated, 60 requests an hour). Pre-releases such as
`0.2.0rc1` are installed only when you name them. Pinning a version skips
the API call.

### Manual install and verification

Every release has fixed asset names:

| Asset | What it is |
|---|---|
| `oreo_cli-<version>-py3-none-any.whl` (+ `.sha256`) | The package |
| `oreo_cli-<version>.tar.gz` (+ `.sha256`) | Source distribution, with the tests |
| `SHA256SUMS` | Both checksums in one file |

```sh
V=1.0.0
curl -LO https://github.com/elixpo/oreo/releases/download/cli-v$V/oreo_cli-$V-py3-none-any.whl
curl -LO https://github.com/elixpo/oreo/releases/download/cli-v$V/SHA256SUMS
sha256sum --check --ignore-missing SHA256SUMS      # macOS: shasum -a 256 -c --ignore-missing
gh attestation verify oreo_cli-$V-py3-none-any.whl -R elixpo/oreo
pipx install oreo_cli-$V-py3-none-any.whl          # or: uv tool install oreo_cli-$V-py3-none-any.whl
```

`gh attestation verify` checks the GitHub build-provenance attestation: that
the file was built by this repository's `cli-release` workflow from the
tagged commit.

### From a checkout

```sh
pipx install ./cli          # or, for development: pip install -e cli/
```

### Dependencies

`rich`, `pyserial`, `mpremote` 1.28.x (it must match the badge's
MicroPython 1.28) and `Pillow` are installed with the CLI. `oreo add` needs
[ffmpeg](https://ffmpeg.org/) on your PATH for videos only:

| System | Command |
|---|---|
| Debian / Ubuntu | `sudo apt install ffmpeg` |
| macOS | `brew install ffmpeg` |
| Windows | `winget install ffmpeg` |

### Linux serial permissions

Opening the badge's port needs the `dialout` group (`uucp` on Arch):

```sh
sudo usermod -aG dialout "$USER"     # then log out and back in
```

`oreo doctor` checks this.

### Uninstall

```sh
pipx uninstall oreo-cli      # or: uv tool uninstall oreo-cli
```

The package is `oreo-cli`; it installs the command as both `oreo` and
`oreo-cli`.

Nothing else is stored on the computer.

## First run

1. Plug the badge into a USB port with a data cable. On the breadboard build
   (ESP32-S3-DevKitC-1), use the port labelled **USB**, not **UART**.
2. Run:

   ```sh
   oreo devs        # is the badge there? (never opens the port)
   oreo             # status, then an interactive menu
   ```

   `oreo` with no command shows the badge's status and a menu: **1** status,
   **2** files, **3** apps, **4** Wi-Fi, **5** add a photo, video or
   document, **u** update OreoOS, **s** shell, **q** quit. In the file
   view, `u <path>` uploads a file from the computer into the folder shown.
   Ctrl-C stops the current action and returns to the menu. OreoOS stays paused while the menu is
   open and starts again when you quit. Without a terminal (for example in a
   script), `oreo` prints the status and exits.
3. If no badge is found, run `oreo doctor`.

### How `oreo` uses the badge

- **The badge is only touched when a command needs it.** `--help`,
  `oreo help`, `oreo devs`, mistyped arguments and "no badge found" never
  open the serial port.
- **One badge is picked automatically.** With several connected, choose one
  with `--port` or `$OREO_PORT` (see `oreo devs`).
- **OreoOS keeps running.** A command pauses OreoOS, does its work and then
  soft-resets the badge so OreoOS starts again. `--reset hard` does a
  hardware reset instead, `--reset none` leaves the MicroPython prompt.
- **Destructive actions ask first** (`rm -r`, `apps remove`,
  `update --clean`, `flash`). Without a terminal the answer is "no" unless
  you pass `--yes`.

### Global options

Put these before the command, e.g. `oreo --port /dev/ttyACM1 info`.

| Option | Meaning |
|---|---|
| `-p`, `--port PORT` | Serial port to use (default: the one badge found; also `$OREO_PORT`) |
| `--reset soft\|hard\|none` | How OreoOS is restarted after a command (default `soft`) |
| `-y`, `--yes` | Answer yes to confirmations |
| `--no-color` | Plain output |
| `-v`, `--verbose` | Show the badge's log lines and full tracebacks |
| `--version` | Print the CLI version |

Exit status: see [Exit status](#exit-status).

## Commands

`oreo help <command>` (or `oreo <command> --help`) shows each command's
options and examples.

### `oreo devs` — list badges

```sh
oreo devs           # badges, by USB ID 303a:83ec
oreo devs --all     # also other USB serial devices, with what they probably are
```

Never opens a port. Exits with status 3 when no badge is connected.

### `oreo info` — status

```sh
oreo info
```

OreoOS version and date, MicroPython version, board, port, space used by
system, apps, gallery, documents and other files, Wi-Fi, the Bluetooth boot
setting, battery and free RAM.

### `oreo ls` / `push` / `pull` / `rm` — files

```sh
oreo ls                              # the badge's root folder
oreo ls /apps
oreo push notes.txt /documents/
oreo push -r myapp /apps/myapp       # a whole folder
oreo pull /wifi_seen.json            # into the current folder
oreo pull -r /apps/pet ./pet-backup
oreo rm /documents/old.mdz
oreo rm -r /apps/myapp               # asks first
```

- `push` checks free space before writing anything. Each file is written to
  a temporary `.part` file, renamed into place, then checked by size and
  SHA-256 (`--no-verify` skips the hash).
- `rm` refuses OreoOS's own files (`/oreoOS`, `/oreoWare`, `/assets`, the
  built-in apps, `/main.py`, `/secrets.py`, `/wifi.json`, ...) and anything
  inside those folders unless you add `--force`; removing them can stop the
  badge booting.

### `oreo add` — photos, videos and documents

```sh
oreo add holiday.jpg                  # Gallery
oreo add clip.mp4 --seconds 8         # Gallery (needs ffmpeg)
oreo add talk-notes.md reading.txt    # Reader
```

Converts each file to a format OreoOS reads and copies it:

| Input | Stored as | Folder on the badge |
|---|---|---|
| Photos (`.jpg`, `.png`, ...) | `.rz565` | `/apps/gallery/assets/optimized` |
| Videos (`.mp4`, `.mov`, ...) | `.rv565` | `/apps/gallery/assets/optimized` |
| `.md` / `.txt` | `.mdz` / `.txtz` | `/documents` |

The converted size is what is checked, against both the media budget
(5 MiB for photos and videos) and the badge's free space, before anything
is copied. Options: `--kind image|video|document` overrides detection,
`--seconds` (default 10), `--fps` (24), `--width` (180) and `--height`
(135) shape videos, `--photo-max` (240) caps a photo's longest side, and
`--save DIR` also keeps the converted files on the computer.

### `oreo apps` — the App Store

```sh
oreo apps                    # installed apps and the catalogue
oreo apps refresh            # fetch the latest catalogue
oreo apps install snake
oreo apps update             # every app with a newer version
oreo apps update snake
oreo apps remove snake       # asks first
```

The badge downloads apps itself, over its own Wi-Fi, so set up Wi-Fi first
(see [Wi-Fi setup](#wi-fi-setup)). `oreo` brings Wi-Fi up from the badge's
saved networks before `refresh`, `install` and `update`, and shows the
download progress.

### `oreo wifi` — Wi-Fi

```sh
oreo wifi scan
oreo wifi connect "Home Net"
oreo wifi saved
oreo wifi forget "Old Net"
```

See [Wi-Fi setup](#wi-fi-setup).

### `oreo shell` — MicroPython REPL

```sh
oreo shell
```

Pauses OreoOS and opens the badge's MicroPython prompt. Leave with
**Ctrl-]** or **Ctrl-X**; OreoOS starts again.

### `oreo run` — run a script

```sh
oreo run blink.py
```

Runs a file from the computer on the badge and streams its output.
**Ctrl-C** stops the script on the badge.

### `oreo dev` — live editing

```sh
oreo dev ./myapp                 # mount ./myapp at /remote, open the REPL
oreo dev ./myapp --run main.py   # and run main.py from it
```

The folder on the computer appears on the badge at `/remote`: edit files
locally and `import` them on the badge without copying. Leave with Ctrl-]
or Ctrl-X.

### `oreo logs` — console output

```sh
oreo logs              # follow what OreoOS prints; Ctrl-C to stop
oreo logs --restart    # restart OreoOS first, to see the boot log
```

`logs` does not stop OreoOS. It keeps following when the badge restarts or
is unplugged and plugged back in (even under a new port name).

### `oreo update` — update OreoOS

```sh
oreo update                    # newest stable release
oreo update --check            # only say whether there is a newer one
oreo update --channel beta     # newest beta release
```

The badge updates itself, the same way its **Settings > Updates** page
does (`oreoOS/ota.py`), and `oreo` steers it and shows what happens:

1. reads the OreoOS version on the badge;
2. brings up the badge's Wi-Fi from its saved networks (set one up first,
   see [Wi-Fi setup](#wi-fi-setup));
3. asks GitHub, from the badge, for the newest release on the channel;
4. compares the badge's files with the release and shows how many change
   and how much will be downloaded;
5. asks, checks the free space, and has the badge download the changed
   files into `/_ota`, checking each one's SHA-256;
6. moves them into place, as the badge does when it boots with an update
   waiting;
7. restarts the badge, waits for it to come back on USB (it may come back
   under another port name) and reports the version it booted.

Apps, photos, documents and saved Wi-Fi are kept. Ctrl-C works until step
6; during step 6 it is held until the files are in place. If the badge
loses power during step 6, it finishes the update when it next starts. If
the badge has already downloaded an update by itself, `oreo update` offers
to install that one.

Without a terminal, `oreo update` answers "no" unless you pass `--yes`.
The badge asks GitHub without a token, which allows 60 requests an hour per
network.

**Developers:** `--repo` deploys from an OreoOS checkout instead of a
release:

```sh
oreo update --repo ~/src/oreo            # ./deploy --board from that checkout
oreo update --repo ~/src/oreo --clean    # wipe the badge's files first (asks)
```

With `--repo`, `update` also takes `--force` (upload every file),
`--no-bump` (keep the OreoOS version) and `--override APPS` (replace these
app folders).

### `oreo flash` — firmware

```sh
oreo flash  --repo ~/src/oreo            # erase, write firmware, install OreoOS (asks)
oreo flash  --repo ~/src/oreo --build    # run ./build-firmware first
```

Needs an OreoOS checkout. Erasing always asks first.

### `oreo doctor` — diagnose the connection

```sh
oreo doctor
```

Checks the computer first (Python, pyserial, mpremote, ffmpeg), then looks
for the badge's USB ID and explains other IDs it finds, checks Linux
`dialout` / `uucp` membership, and only then opens the port to read the
firmware and OreoOS versions. It ends with numbered **next steps**,
failures first. Exit status `0` when nothing failed (warnings are fine),
`1` otherwise.

### `oreo help`

```sh
oreo help            # list commands
oreo help add        # one command, with examples
```

## Wi-Fi setup

The badge uses Wi-Fi only for the internet: the App Store, OreoOS updates,
GitHub, weather and the clock. It joins 2.4 GHz networks only.

```sh
oreo wifi scan                     # networks the badge can see, with signal and security
oreo wifi connect "Home Net"       # asks for the password without echo
oreo wifi saved                    # names of saved networks
oreo wifi forget "Old Net"
```

`connect` joins the network and saves it, so OreoOS joins it by itself from
then on. Options:

| Option | Meaning |
|---|---|
| `--open` | The network has no password |
| `--no-save` | Join now, but do not save it |
| `--save-only` | Save it without trying it now (e.g. a network that is not in range) |
| `--password-stdin` | Read the password from standard input, for scripts |
| `--timeout SECONDS` | How long to wait for the network (default 15) |

```sh
# In a script: the password never appears on the command line.
printf '%s\n' "$WIFI_PASSWORD" | oreo wifi connect "Home Net" --password-stdin
```

**The password stays private.** It is read before the badge is touched,
sent to the badge once, and never printed, logged, returned or stored on the
computer; it is removed from error messages. `oreo wifi saved` lists names
only.

Results are reported plainly: **wrong password**, **not in range** (the
badge sees only 2.4 GHz networks; check `oreo wifi scan`) or **did not
answer in time** (move closer, or try `--timeout 30`).

Networks written into the deploy-time `.env` file come back at the next
boot even after `forget`; `oreo` warns about that. Remove them from `.env`
and deploy again to forget them for good.

## Exit status

Stable across 1.x, for scripts:

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | The command failed; the message says why |
| `2` | Usage error: a missing or invalid argument (checked before the badge is touched) |
| `3` | No badge found, or several and no `--port` |
| `4` | The badge could not be reached: port missing or busy, no answer, connection lost |
| `5` | The badge answers but has no OreoOS (or one too old for the command) |
| `130` | Cancelled: Ctrl-C, or "no" at a confirmation |

`oreo devs` exits `3` when no badge is connected; `oreo doctor` exits `1`
when a check failed.

## Transfer speed

`push`, `add` and the interactive upload send files as base64 inside short
MicroPython snippets over the raw REPL ("raw paste" mode). Each file goes
to a `.part` file in 8 KiB chunks; the first chunk rides along with the
open, and the last with a step on the badge that checks the size and
SHA-256 and only then renames the file into place. Free space is checked
once per command and each folder is created once per session.

Measured on the simulated badge (execs and bytes of code; `python3
cli/tests/test_push_speed.py`) and turned into time with a model of the USB
link (1.5 ms round trip, MicroPython's 256-byte raw-paste window, 150 KB/s
flash), so the times are estimates until measured on a badge:

| Case | Execs | Code per file byte | Estimate |
|---|---|---|---|
| 1 MiB file, 4 KiB chunks (0.1.0) | 257 | 1.34 | ~43 KiB/s |
| 1 MiB file, 8 KiB chunks (1.0.0) | 129 | 1.34 | ~44 KiB/s |
| 40 files of 1.5 KiB, 0.1.0 | 240 | | |
| 40 files of 1.5 KiB, 1.0.0 | 81 | 1.99 | ~32 KiB/s |

What this shows: for big files the chunk size hardly matters; the time
goes to raw-paste flow control (one round trip per 256 bytes of code) and
to flash writes. For many small files, the fewer execs per file (2 instead
of 6) are what count. A binary transfer that streams raw bytes to a
receiver on the badge would remove both the base64 overhead and the
flow-control round trips (about a third of the estimate above), but it
needs measuring on a badge before it replaces the current, simple path.

## Troubleshooting

Start with `oreo doctor`. Common cases:

| Symptom | What to do |
|---|---|
| `no Oreo Badge found (USB 303a:83ec)` | Use a data cable (some are charge-only) and, on the DevKitC-1, the **USB** port. `oreo devs --all` shows what is connected. |
| A `303a:1001` device | Stock ESP32-S3 USB-Serial/JTAG: the board has no OreoOS firmware yet, or it is in the bootloader. Flash it with `oreo flash --repo <checkout>`. |
| A `303a:0002` device | Download mode (BOOT was held at reset). Press RESET without BOOT. |
| A `303a:4001` device | Generic MicroPython, not the Oreo Badge build. Flash the badge firmware. |
| A CP210x, CH340 or CH9102 device | That is the devkit's UART bridge; plug into the native **USB** port instead. |
| `2 badges connected` | Pick one: `oreo --port /dev/ttyACM1 info` or `export OREO_PORT=/dev/ttyACM1`. |
| `Permission denied` on Linux | Join `dialout` (`uucp` on Arch), then log out and back in. |
| Port busy | Close other programs using it: another `oreo`, `mpremote`, Thonny, a serial monitor, the Arduino IDE. |
| `the badge did not answer` (exit 4) | OreoOS is busy with something that delays Ctrl-C (a download, an app). Wait a few seconds and retry; if it stays stuck, press RESET or replug. |
| `lost the connection to the badge` (exit 4) | It was unplugged or restarted. Plug it back in, `oreo devs`, run the command again. |
| `this needs OreoOS` (exit 5) | The badge has MicroPython but no OreoOS: `oreo flash --repo <checkout>`. |
| Git Bash: `looks like a path on this computer` | Git Bash rewrote `/documents` into a Windows path. Write `:documents/`, or set `MSYS_NO_PATHCONV=1`. |
| `oreo update`: `could not get online` | Set up Wi-Fi first: `oreo wifi scan`, `oreo wifi connect <name>`. |
| `oreo update`: `could not reach GitHub` | Check the network; GitHub allows 60 requests an hour per network without a token. |
| `oreo update`: `did not come back on USB` | It may still be installing; wait and run `oreo info`. If the screen stays dark, press RESET. |
| `oreo update`: `too old to be updated from the CLI` | Update once from the badge (Settings > Updates) or with `oreo update --repo`. |
| `not enough space on the badge` | See what uses it with `oreo info`; free some with `oreo rm` or `oreo apps remove`. |
| `ffmpeg was not found` | Install ffmpeg (see [Dependencies](#dependencies)); only videos need it. |
| `checksum mismatch after copy` | Run it again; if it repeats, try another cable or USB port. |
| Wi-Fi: not in range | The badge sees 2.4 GHz only. Check `oreo wifi scan`. |
| `apps install` fails | Check Wi-Fi first: `oreo wifi saved`, `oreo wifi connect <name>`. |
| The badge stays at the `>>>` prompt | A command ran with `--reset none`, or OreoOS failed to start. Try `oreo --reset hard info`, then `oreo logs --restart`. |
| An installer says `pipx or uv ... neither was found` | Install one of them (the message has the command), then run it again. |
| Something else | Re-run with `-v` and include `oreo doctor` output in an issue. |

## Testing on a badge

CI has no badge; these are the checks to run by hand on a badge (and the
output to attach when reporting a problem):

1. `oreo doctor`: all checks pass, ending in "all good".
2. `oreo info`, then `oreo` (menu): status, files (open a folder, `u` an
   upload, `p` a download), apps list, Wi-Fi saved, **q** restarts OreoOS.
3. `oreo push` a 1 MiB file and a folder of small files; note the time
   and speed shown, `oreo pull` them back and compare (`sha256sum`).
4. Pull the cable during a large `oreo push`: the error is "lost the
   connection" (exit 4), no traceback; after replugging, the old file at
   the destination is intact and there is no `.part` left after the next
   push.
5. `oreo wifi scan`, `oreo wifi connect <name>`, `oreo apps install <app>`.
6. `oreo update --check`, then `oreo update` on a badge one release behind:
   versions shown, progress, restart, "installed and running". Also with
   the badge offline (expect the Wi-Fi hint) and when up to date.
7. `oreo logs`, press RESET on the badge: logging carries on after the
   restart. Ctrl-C stops it (also on Windows).
8. `oreo shell` and `oreo run` a script that prints; Ctrl-C stops it and
   OreoOS restarts.
9. On Windows (PowerShell and Git Bash) and macOS: `oreo devs`, `oreo info`,
   `oreo push notes.txt :documents/`, `oreo --port com5 info` /
   `oreo --port /dev/tty.usbmodem* info`.

## Releasing

Maintainers only. CLI releases are independent of OreoOS releases and do not
touch them: the `cli-release` workflow runs only for `cli-v*` tags (and
builds and tests, without releasing, on pull requests that change `cli/`),
its tags do not match the badge's OTA prefixes (`stable/`, `beta/`), and the
release is created with `--latest=false` so the repository's "Latest"
release stays OreoOS.

1. In a pull request: set `__version__` in `cli/oreo_cli/__init__.py`, move
   the `Unreleased` notes in `cli/CHANGELOG.md` under a new
   `## [<version>] - <date>` heading, and merge it.
2. Tag the merge commit and push the tag:

   ```sh
   git tag cli-v1.0.0 <commit-on-main>
   git push origin cli-v1.0.0
   ```

3. The workflow then:
   - runs the CLI tests on Linux (Python 3.9 and 3.13) and macOS;
   - checks the tag matches `__version__` and that `CHANGELOG.md` has a
     section for it;
   - builds the wheel and sdist from `cli/` (timestamps from the commit),
     writes `.sha256` files and `SHA256SUMS`, and smoke-tests the wheel and
     both installers on Linux and Windows;
   - adds a build-provenance attestation for both packages;
   - waits for the `cli-release` environment (add required reviewers to it
     in the repository settings to make releases need an approval), then
     publishes the GitHub release with the changelog section as its notes.
     Versions with `a`, `b` or `rc` are marked as pre-releases.

If a release run fails after the tag was pushed, fix the problem, delete the
tag (`git push origin :refs/tags/cli-v1.0.0`), and tag again. The installers
skip a tag that has no published release.

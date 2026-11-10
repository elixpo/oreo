# The `oreo` command-line tool

`oreo` controls the Elixpo Oreo Badge from a computer over USB: status,
files, photos, videos and documents, apps, Wi-Fi, logs, a MicroPython shell,
OreoOS updates and firmware. It finds the badge by its USB ID (`303a:83ec`),
so you never have to guess `/dev/ttyACM0` or `COM5`.

The code lives in [`cli/`](../cli) (Python package `oreo-cli`, command
`oreo`). It is released separately from OreoOS, with tags `cli-v<version>`;
see [cli/CHANGELOG.md](../cli/CHANGELOG.md).

> **Status: 0.1.0, first release.** Every command is covered by host tests
> against a simulated badge, but the CLI has not yet been run against a real
> badge. If something misbehaves, run `oreo doctor` and attach its output to
> an issue.

Contents: [Install](#install) · [First run](#first-run) ·
[Commands](#commands) · [Wi-Fi setup](#wi-fi-setup) ·
[Troubleshooting](#troubleshooting) · [Releasing](#releasing)

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
| `OREO_CLI_VERSION` | Release to install: `latest` (default), or `cli-v0.1.0`, `v0.1.0`, `0.1.0` |
| `OREO_CLI_INSTALLER` | `pipx` or `uv` (default: pipx if present, else uv) |
| `OREO_CLI_REPOSITORY` | GitHub repository to install from (default `elixpo/oreo`) |
| `OREO_CLI_DOWNLOAD_BASE` | Fetch the wheel from this URL instead of the release (testing; needs a pinned version) |

Pin a version:

```sh
curl --proto '=https' --tlsv1.2 -LsSf \
  https://raw.githubusercontent.com/elixpo/oreo/main/cli/install.sh |
  OREO_CLI_VERSION=cli-v0.1.0 sh
```

```powershell
$env:OREO_CLI_VERSION = "cli-v0.1.0"
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
V=0.1.0
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
   document, **s** shell, **q** quit. OreoOS stays paused while the menu is
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

Exit status: `0` success, `1` error, `2` usage error, `3` no badge (or more
than one) found, `130` cancelled.

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
- `rm` refuses OreoOS's own files (`/oreoOS`, `/oreoWare`, `/main.py`, the
  built-in apps, ...) unless you add `--force`; removing them can stop the
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

`logs` does not stop OreoOS.

### `oreo update` / `oreo flash` — OreoOS and firmware

```sh
oreo update --repo ~/src/oreo            # ./deploy --board from that checkout
oreo update --repo ~/src/oreo --clean    # wipe the badge's files first (asks)
oreo flash  --repo ~/src/oreo            # erase, write firmware, install OreoOS (asks)
oreo flash  --repo ~/src/oreo --build    # run ./build-firmware first
```

Both need an OreoOS checkout for now. `update` also takes `--force` (upload
every file), `--no-bump` (keep the OreoOS version) and `--override APPS`
(replace these app folders). Updating from GitHub releases without a
checkout is planned; the badge itself can also update over Wi-Fi from its
Updates page.

### `oreo doctor` — diagnose the connection

```sh
oreo doctor
```

Checks pyserial and mpremote, looks for the badge's USB ID and explains
other IDs it finds, checks Linux `dialout` / `uucp` membership, and reads
the firmware banner and the OreoOS version. Each problem comes with a hint.

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
| `not enough space on the badge` | See what uses it with `oreo info`; free some with `oreo rm` or `oreo apps remove`. |
| `ffmpeg was not found` | Install ffmpeg (see [Dependencies](#dependencies)); only videos need it. |
| `checksum mismatch after copy` | Run it again; if it repeats, try another cable or USB port. |
| Wi-Fi: not in range | The badge sees 2.4 GHz only. Check `oreo wifi scan`. |
| `apps install` fails | Check Wi-Fi first: `oreo wifi saved`, `oreo wifi connect <name>`. |
| The badge stays at the `>>>` prompt | A command ran with `--reset none`, or OreoOS failed to start. Try `oreo --reset hard info`, then `oreo logs --restart`. |
| An installer says `pipx or uv ... neither was found` | Install one of them (the message has the command), then run it again. |
| Something else | Re-run with `-v` and include `oreo doctor` output in an issue. |

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
   git tag cli-v0.1.0 <commit-on-main>
   git push origin cli-v0.1.0
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
tag (`git push origin :refs/tags/cli-v0.1.0`), and tag again. The installers
skip a tag that has no published release.

# oreo-cli: the Oreo Badge command-line tool

**oreo-cli** controls the Elixpo Oreo Badge from a computer over USB. The
command it installs is `oreo`. With it you can:

- see the badge's status
- send photos, videos and documents to the **Transfer** app
- work with files and apps
- set up Wi-Fi
- follow the badge's logs
- open a MicroPython shell
- update OreoOS

It finds the badge by its USB ID (`303a:83ec`), so you never have to guess
`/dev/ttyACM0` or `COM5`.

The code lives in [`cli/`](../cli). The Python package is `oreo-cli` and the
command is `oreo`; the package also installs `oreo-cli` as a second name for
the same command. The CLI is released separately from OreoOS, with tags
`cli-v<version>`. See [cli/CHANGELOG.md](../cli/CHANGELOG.md) for what each
release changed.

> **Status: 1.0.0, stable.** Commands, options, output and exit codes are
> stable. Later 1.x releases may add to them but will not change them. Every
> command is tested against a simulated badge, and the checks to run by hand
> are listed in [Testing on a badge](#testing-on-a-badge). If something goes
> wrong, run `oreo doctor` and attach its output to an
> [issue](https://github.com/elixpo/oreo/issues).

Related guides:

- [USB.md](USB.md): using the badge from a computer (ports, drivers,
  permissions, and raw `mpremote` for advanced use).
- [TRANSFER.md](TRANSFER.md): how the Transfer app and its code exchange
  work.

Contents: [Install](#install) · [First run](#first-run) ·
[Commands](#commands) · [Sending files: `oreo transfer`](#oreo-transfer-send-files-to-the-transfer-app) ·
[Wi-Fi setup](#wi-fi-setup) · [Updating OreoOS](#oreo-update-update-oreoos) ·
[Exit status](#exit-status) · [Troubleshooting](#troubleshooting) ·
[FAQ](#faq) · [Transfer speed](#transfer-speed) ·
[Testing on a badge](#testing-on-a-badge) · [Releasing](#releasing)

## Install

You need Python 3.9 or newer and either [pipx](https://pipx.pypa.io/) or
[uv](https://docs.astral.sh/uv/). The installer:

1. picks pipx if you have it, and uv otherwise;
2. downloads the release wheel and its `.sha256` file;
3. checks the SHA-256;
4. installs `oreo` as an isolated tool.

If you have neither pipx nor uv, it tells you how to get one and stops.

**Linux and macOS**

```sh
curl --proto '=https' --tlsv1.2 -LsSf \
  https://raw.githubusercontent.com/elixpo/oreo/main/cli/install.sh | sh
```

**Windows (PowerShell)**

```powershell
irm https://raw.githubusercontent.com/elixpo/oreo/main/cli/install.ps1 | iex
```

To upgrade, run the same command again. It replaces the installed version.
Check what you have with `oreo --version`.

### Installer options

| Variable | Meaning |
|---|---|
| `OREO_CLI_VERSION` | Release to install: `latest` (the default), or a version written as `cli-v1.0.0`, `v1.0.0` or `1.0.0` |
| `OREO_CLI_INSTALLER` | `pipx` or `uv` (default: pipx if present, otherwise uv) |
| `OREO_CLI_REPOSITORY` | GitHub repository to install from (default `elixpo/oreo`) |
| `OREO_CLI_DOWNLOAD_BASE` | Download the wheel from this URL instead of the release. For testing; needs a pinned version |

To install a specific version:

```sh
curl --proto '=https' --tlsv1.2 -LsSf \
  https://raw.githubusercontent.com/elixpo/oreo/main/cli/install.sh |
  OREO_CLI_VERSION=cli-v1.0.0 sh
```

```powershell
$env:OREO_CLI_VERSION = "cli-v1.0.0"
irm https://raw.githubusercontent.com/elixpo/oreo/main/cli/install.ps1 | iex
```

The repository's "Latest" GitHub release is always OreoOS, not the CLI. So
for `latest`, the installers ask the GitHub API for the newest `cli-vX.Y.Z`
tag. The API allows 60 requests an hour without a token. Pre-releases such as
`1.1.0rc1` are installed only when you name them. Pinning a version skips the
API call.

### Install with pipx or uv directly

Every release has assets with fixed names:

| Asset | What it is |
|---|---|
| `oreo_cli-<version>-py3-none-any.whl` (+ `.sha256`) | The package |
| `oreo_cli-<version>.tar.gz` (+ `.sha256`) | Source distribution, with the tests |
| `SHA256SUMS` | Both checksums in one file |

pipx and uv can install the wheel straight from its release URL:

```sh
pipx install https://github.com/elixpo/oreo/releases/download/cli-v1.0.0/oreo_cli-1.0.0-py3-none-any.whl
# or
uv tool install https://github.com/elixpo/oreo/releases/download/cli-v1.0.0/oreo_cli-1.0.0-py3-none-any.whl
```

To check the file before you install it:

```sh
V=1.0.0
curl -LO https://github.com/elixpo/oreo/releases/download/cli-v$V/oreo_cli-$V-py3-none-any.whl
curl -LO https://github.com/elixpo/oreo/releases/download/cli-v$V/SHA256SUMS
sha256sum --check --ignore-missing SHA256SUMS      # macOS: shasum -a 256 -c --ignore-missing SHA256SUMS
gh attestation verify oreo_cli-$V-py3-none-any.whl -R elixpo/oreo
pipx install oreo_cli-$V-py3-none-any.whl          # or: uv tool install oreo_cli-$V-py3-none-any.whl
```

`gh attestation verify` checks the GitHub build-provenance attestation. It
confirms that the file was built by this repository's `cli-release` workflow
from the tagged commit.

oreo-cli is not on PyPI; install it from the GitHub release.

### From a checkout

```sh
pipx install ./cli          # or, for development: pip install -e cli/
```

### Dependencies

These are installed with the CLI:

- `rich`
- `pyserial`
- `mpremote` 1.28.x, which must match the badge's MicroPython 1.28
- `Pillow`

Converting **videos** also needs [ffmpeg](https://ffmpeg.org/) on your PATH
(for `oreo transfer send` and `oreo add`). Photos and documents do not.

| System | Command |
|---|---|
| Debian / Ubuntu | `sudo apt install ffmpeg` |
| macOS | `brew install ffmpeg` |
| Windows | `winget install ffmpeg` |

### Linux serial permissions

To open the badge's port you need to be in the `dialout` group (`uucp` on
Arch):

```sh
sudo usermod -aG dialout "$USER"     # then log out and back in
```

`oreo doctor` checks this. macOS and Windows need no setup.

### Uninstall

```sh
pipx uninstall oreo-cli      # or: uv tool uninstall oreo-cli
```

The CLI stores nothing else on the computer.

## First run

1. Plug the badge into a USB port with a data cable. On the breadboard build
   (ESP32-S3-DevKitC-1), use the port labelled **USB**, not **UART** (see
   [USB.md](USB.md#which-usb-c-port)).
2. Run:

   ```sh
   oreo devs        # is the badge there? (never opens the port)
   oreo             # status, then an interactive menu
   ```

3. If no badge is found, run `oreo doctor`.

`oreo` with no command shows the badge's status and then a menu:

| Key | Action |
|---|---|
| **1** | status |
| **2** | files |
| **3** | apps |
| **4** | Wi-Fi |
| **5** | add a photo, video or document |
| **t** | send files to Transfer (the same flow as `oreo transfer send`) |
| **p** | owner profile (the same flow as `oreo setup`) |
| **i** | install an app from a folder (the same checks as `oreo app install`) |
| **u** | update OreoOS |
| **s** | shell |
| **q** | quit |

In the file view, `u <path>` uploads a file from the computer into the folder
shown, and `p` downloads one. Ctrl-C stops the current action and goes back
to the menu. OreoOS stays paused while the menu is open and starts again when
you quit. Without a terminal (in a script, for example), `oreo` prints the
status and exits.

**t** is the one entry that needs OreoOS running: it checks and converts the
files first, then restarts OreoOS and asks for the code the Transfer app shows
(apps drawer -> Tools -> Transfer). OreoOS keeps running afterwards; the next
entry that needs the badge pauses it again. A profile saved with **p** and an
app installed with **i** take effect when OreoOS restarts, which happens when
you quit the menu.

To send photos and documents while OreoOS keeps running, use the Transfer app
instead (see [`oreo transfer`](#oreo-transfer-send-files-to-the-transfer-app)).

### How `oreo` uses the badge

- **The badge is only touched when a command needs it.** `--help`,
  `oreo help`, `oreo devs`, mistyped arguments and "no badge found" never
  open the serial port.
- **One badge is picked automatically.** If several are connected, choose
  one with `--port` or `$OREO_PORT` (see `oreo devs`).
- **Most commands pause OreoOS and then restart it.** Such a command stops
  OreoOS, does its work and then soft-resets the badge so OreoOS starts
  again. `--reset hard` does a hardware reset instead, and `--reset none`
  leaves the badge at the MicroPython prompt.
- **Some commands do not stop OreoOS.** `oreo transfer` talks to the Transfer
  app while it runs, and `oreo logs` only listens.
- **Destructive actions ask first.** These are `rm -r`, `apps remove`, `app remove`,
  `transfer rm`, `update`, `update --clean` and `flash`. Without a terminal,
  the answer is "no" unless you pass `--yes`.

### Global options

Put these before the command, for example `oreo --port /dev/ttyACM1 info`.

| Option | Meaning |
|---|---|
| `-p`, `--port PORT` | Serial port to use (default: the one badge found; also `$OREO_PORT`) |
| `--reset soft\|hard\|none` | How OreoOS is restarted after a command (default `soft`) |
| `-y`, `--yes` | Answer yes to confirmations |
| `--no-color` | Plain output |
| `-v`, `--verbose` | Show the badge's log lines and full tracebacks |
| `--version` | Print the CLI version |

## Commands

| Command | What it does | Stops OreoOS? |
|---|---|---|
| [`oreo`](#first-run) | Status and the interactive menu | while the menu is open |
| [`oreo devs`](#oreo-devs-list-badges) | List badges | no (never opens a port) |
| [`oreo info`](#oreo-info-status) | Versions, storage, Wi-Fi, battery | briefly |
| [`oreo transfer`](#oreo-transfer-send-files-to-the-transfer-app) / `oreo send` | Send files to the Transfer app, using the code on the badge | **no** |
| [`oreo add`](#oreo-add-photos-videos-and-documents-without-the-transfer-app) | Send photos, videos and documents without opening an app | briefly |
| [`oreo ls` / `push` / `pull` / `rm`](#oreo-ls--push--pull--rm-files) | Any file on the badge | briefly |
| [`oreo apps`](#oreo-apps-the-app-store) | App Store: list, install, update, remove | briefly |
| [`oreo setup`](#oreo-setup-owner-profile) | Owner profile: GitHub user, name, timezone, weather | briefly, then restarts |
| [`oreo new`](#oreo-new-start-an-app) | Make a new app folder from the app template | no (never opens a port) |
| [`oreo app`](#oreo-app-install-an-app-from-a-folder) | Install, list or remove an app from a folder on this computer | briefly, then restarts |
| [`oreo wifi`](#wi-fi-setup) | Scan, connect, list and forget networks | briefly |
| [`oreo update`](#oreo-update-update-oreoos) | Update OreoOS (downloaded by the badge) | yes, then restarts |
| [`oreo logs`](#oreo-logs-console-output) | Follow the console | no |
| [`oreo shell`](#oreo-shell-micropython-repl) / [`run`](#oreo-run-run-a-script) / [`dev`](#oreo-dev-live-editing) | MicroPython prompt, scripts, live editing | while it runs |
| [`oreo flash`](#oreo-flash-firmware) | Reflash the firmware (developers) | yes |
| [`oreo doctor`](#oreo-doctor-diagnose-the-connection) | Diagnose cable, port, permissions, firmware | briefly |

`oreo help <command>` (or `oreo <command> --help`) shows each command's
options and examples.

### `oreo devs`: list badges

```sh
oreo devs           # badges, by USB ID 303a:83ec
oreo devs --all     # also other USB serial devices, with what they probably are
```

This never opens a port. It exits with status 3 when no badge is connected.

### `oreo info`: status

```sh
oreo info
```

Shows:

- the OreoOS version and date, and the MicroPython version;
- the board and port;
- space used by the system, apps, gallery, documents and other files;
- Wi-Fi status and the Bluetooth boot setting;
- battery and free RAM.

### `oreo transfer`: send files to the Transfer app

The easiest way to put photos, videos and documents on the badge. OreoOS keeps
running the whole time, and you prove you are at the right badge by typing
the code it shows. How it works inside is in [TRANSFER.md](TRANSFER.md).

1. On the badge, open the apps drawer, go to **Tools** and open
   **Transfer**. It shows a six-character code, for example `K7M2QX`.
2. On the computer, run:

   ```sh
   oreo transfer send holiday.jpg clip.mp4 talk-notes.md
   ```

3. When asked, type the code from the badge. Case does not matter, and you
   can include spaces or dashes (`k7m-2qx` is fine).
4. Each file is converted, sent, checked on the badge and saved. Photos and
   videos appear in the **Gallery**, documents in the **Reader**, and the
   badge shows a notification for each file.

```text
$ oreo transfer send holiday.jpg talk-notes.md
holiday.jpg -> holiday.rz565  41.2 KB (6% of the original)
talk-notes.md -> talk-notes.mdz  2.1 KB (38% of the original)
✓ Transfer is open on the badge (OreoOS 2.x.y), 9.8 MB free
Code shown on the badge: K7M2QX
✓ code accepted
✓ holiday.rz565 is in the Gallery (/apps/gallery/assets/optimized/holiday.rz565, SHA-256 checked)
✓ talk-notes.mdz is in the Reader (/documents/talk-notes.mdz, SHA-256 checked)
✓ 2 file(s) sent
```

(The output above is an illustration; the exact wording and sizes vary.)

Other actions, in the same session style (open Transfer, type the code):

```sh
oreo transfer list                    # photos, videos and documents on the badge, and free space
oreo transfer rm holiday.rz565        # remove one (asks first; names from `transfer list`)
oreo send holiday.jpg                 # short for `oreo transfer send`
```

`oreo transfer` with no action means `send`.

| Option | Meaning |
|---|---|
| `--code CODE` | The code shown on the badge. Without it, `oreo` asks. A script with no terminal must pass it |
| `--wait SECONDS` | How long to wait for the Transfer app to be open (default 60) |
| `--kind image\|video\|document` | Override the file type detection |
| `--seconds N` | Video length to keep (default 10) |
| `--photo-max N` | Longest side of a photo in pixels (default 240) |

What gets sent:

| Input | Sent as | Lands in |
|---|---|---|
| Photos (`.jpg`, `.png`, ...) | `.rz565` | Gallery (`/apps/gallery/assets/optimized`) |
| Videos (`.mp4`, `.mov`, ...; needs ffmpeg) | `.rv565`, 180×135 at 24 fps | Gallery |
| `.md` / `.txt` | `.mdz` / `.txtz` | Reader (`/documents`) |
| Files already in a badge format (`.rz565`, `.r565`, `.rv565`, `.mdz`, `.txtz`) | as they are | Gallery or Reader |

Anything else is refused before the badge is touched. Every file is converted
and checked before the badge is contacted, so a bad file never leaves a
session half done.

Things to know:

- **The code changes.** Every session gets a new code: when the CLI says
  goodbye, when the session is cancelled, and after a lockout. **RIGHT** on
  the badge draws a new one while no computer is connected.
- **Wrong codes.** In a terminal, `oreo` tells you how many tries are left
  and asks again. After 5 wrong codes, the badge locks for 60 seconds and
  then shows a new code. With `--code`, or without a terminal, one wrong
  code ends the command.
- **Waiting for the app.** If Transfer is not open, `oreo` waits. After a
  couple of seconds it tells you to open it, and it gives up after `--wait`
  seconds. It sends nothing to the badge until the app has announced
  itself, so a closed app is never sent bytes it cannot read.
- **Cancelling.** **B** on the badge cancels the session and Ctrl-C on the
  computer stops it. A half-sent file is always thrown away; the old file
  with the same name, if any, is kept.
- **Same name.** A file with the same name replaces the old one, and `oreo`
  says "replaced the old one".
- **Limits.** One file can be up to 8 MiB, and the badge keeps 256 KiB free
  for OreoOS. A file that does not fit fails on its own and the others still
  go through. The command then exits with status 1 and lists what was not
  sent.
- **Timeouts.** The badge drops a computer that stays silent: after 5 minutes
  while waiting for the code, after 2 minutes once the code is accepted, and
  after 20 seconds in the middle of a file.
- **While Transfer is open, close it before using other `oreo` commands.**
  The app turns off Ctrl-C on the USB console so that no byte can interrupt
  OreoOS. Commands that pause OreoOS (`info`, `add`, `push`, `shell`,
  `update`, ...) therefore cannot stop it, and they fail with "the badge did
  not answer" (exit 4). Press **HOME** or **B** on the badge to leave
  Transfer, then run the command again.
- **Only one program can have the port open.** Stop `oreo logs`, `mpremote`
  or a serial monitor before running `oreo transfer`.

### `oreo add`: photos, videos and documents without the Transfer app

```sh
oreo add holiday.jpg                  # Gallery
oreo add clip.mp4 --seconds 8         # Gallery (needs ffmpeg)
oreo add talk-notes.md reading.txt    # Reader
```

Same conversion and destinations as `oreo transfer send`. The difference is
that `add` needs no app and no code: it pauses OreoOS and copies the files
over the MicroPython REPL, then restarts OreoOS. Use it in scripts, or when
you have the badge to yourself; use `oreo transfer` when you want OreoOS to
stay up, or want the person holding the badge to approve the transfer.

Before anything is copied, the converted size is checked against the media
budget (5 MiB for photos and videos) and the badge's free space.

| Option | Meaning |
|---|---|
| `--kind image\|video\|document` | Override detection |
| `--seconds N` | Video length (default 10) |
| `--fps N` | Video frame rate (default 24) |
| `--width N`, `--height N` | Video size (default 180×135) |
| `--photo-max N` | Longest side of a photo (default 240) |
| `--save DIR` | Also keep the converted files on the computer |

### `oreo ls` / `push` / `pull` / `rm`: files

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
  a temporary `.part` file. The badge checks its size and SHA-256 and only
  then renames it into place, so a damaged copy leaves the old file
  untouched. `--no-verify` skips the hash.
- `push` copies files as they are. To make a photo or video viewable, use
  `oreo transfer send` or `oreo add`, which convert it first.
- `rm` refuses OreoOS's own files (`/oreoOS`, `/oreoWare`, `/assets`, the
  built-in apps, `/main.py`, `/secrets.py`, `/wifi.json`, ...) and anything
  inside those folders unless you add `--force`. Removing them can stop the
  badge from booting.
- A badge path can be written with a leading `:` (`:documents/`). In Git Bash
  on Windows you need it (see [Troubleshooting](#troubleshooting)).

### `oreo apps`: the App Store

```sh
oreo apps                    # installed apps and the catalogue
oreo apps refresh            # fetch the latest catalogue
oreo apps install snake
oreo apps update             # every app with a newer version
oreo apps update snake
oreo apps remove snake       # asks first
```

The badge downloads apps itself, over its own Wi-Fi, so set up Wi-Fi first
(see [Wi-Fi setup](#wi-fi-setup)). Before `refresh`, `install` and `update`,
`oreo` brings Wi-Fi up from the badge's saved networks and then shows the
download progress. Built-in apps (including Transfer) cannot be removed.

### `oreo setup`: owner profile

```sh
oreo setup                                     # show the profile, ask for each value
oreo setup --show                              # only print it (the key is hidden)
oreo setup --github-user octocat --name "Mona Lisa" --timezone 5.5
oreo setup --lat 12.97 --lon 77.59 --weather-name Bengaluru
oreo setup --owm-key-stdin < owm-key.txt       # the OpenWeatherMap key, kept out of history
oreo setup --designation ""                    # remove a value
oreo setup --from-file .env.local              # the profile keys from an .env-style file
oreo setup --set DISPLAY_NAME="Mona Lisa" --set TIMEZONE_OFFSET=5.5   # one key at a time
```

Keys use the `.env.local` names: `GITHUB_USER`, `DISPLAY_NAME`,
`DISPLAY_DESIGNATION` (or the older `DESIGNATION`), `TIMEZONE_OFFSET`,
`OWM_API_KEY`, and optionally `WEATHER_LAT`, `WEATHER_LON`, `WEATHER_NAME`.
Without a pinned latitude and longitude, Weather finds the badge's own
location from its network ([PROFILE.md](PROFILE.md#weathers-location)).

- `--from-file FILE` reads an `.env`-style file (comments, `export` and
  quotes are fine). It takes only the profile keys, skips empty ones, and
  leaves everything else in the file alone: it prints which keys it took
  and the names of the others, never a value.
- `--set KEY=VALUE` sets one key (repeatable); `KEY=` removes it.
- When several are given, later ones win: the file, then `--set`, then the
  named options such as `--name`.

Writes `/profile.json` on the badge, which Badge, Identity, Commits, Weather
and the clock read through `oreoOS/profile.py` (see [PROFILE.md](PROFILE.md)).
No checkout or `.env.local` is needed.

- It first shows what the badge has now and where each value comes from
  (`profile.json` or `secrets.py`, which `tools/deploy.py` writes).
- Asked interactively, **Enter** keeps the value shown and `-` removes it, so
  the `secrets.py` value (if any) shows through again. Values given as options
  are saved without prompting; an empty option value removes the key.
- Values are checked before the badge is touched: the timezone is hours from
  UTC between -12 and +14 in quarter hours (`5.5`, `-4`, `+05:30`,
  `UTC+5:45`), latitude -90 to 90, longitude -180 to 180, GitHub user names
  as GitHub allows them, and short plain-ASCII names that fit the screen
  (the badge font has no other characters).
- The OpenWeatherMap key is read without echo and never printed. The badge
  only reports whether one is set, so the key never comes back to the
  computer. `--owm-key KEY` works but warns that the key may land in your
  shell history; prefer the prompt or `--owm-key-stdin`.
- The new file is merged on the badge, written to `/profile.json.tmp`, read
  back and then renamed over `/profile.json`, so a cut-off save never leaves
  a half-written profile. If the power goes between removing the old file
  and the rename, OreoOS reads the `.tmp` copy, and the next save repairs it.
- OreoOS restarts afterwards so the apps read the new profile (`--reset none`
  leaves it at the MicroPython prompt). A new timezone applies at the next
  time sync, which happens as OreoOS starts.

### `oreo new`: start an app

```sh
oreo new my_game                               # ./my_game, shown as "My Game"
oreo new "My Game" --author octocat --dir ~/oreo-apps
```

Copies the app template (a counter: **A** adds, **B** takes one away; the same
files as `app_templates/` in the OreoOS repo, shipped inside oreo-cli) into a
new folder, and fills in the app id, the name shown on the badge, the author
(from `--author`, else `git config github.user` or `user.name`) and the icon
module. The id comes from the name: `My Game` -> `my_game`. Edit
`src/app.py`, then `oreo app install ./my_game`. The app guide is
[APPS.md](APPS.md).

### `oreo app`: install an app from a folder

```sh
oreo app install ./my_game      # check, copy to /apps/my_game/, restart OreoOS
oreo app install ./badge --force   # over a built-in app (working on OreoOS itself)
oreo app list                   # installed apps
oreo app remove my_game         # asks first
```

`install`:

1. checks the folder with the same rules as `tools/validate_app.py` (a copy
   ships in oreo-cli, and a test keeps them the same). Errors stop it before
   the badge is touched; warnings are shown;
2. refuses to replace a built-in app unless you add `--force`;
3. checks free space, then copies only the files that belong on the badge
   (`manifest.json`, `main.py`, `__init__.py`, `src/`, `assets/optimized/`)
   to `/apps/<id>/`, each one through a `.part` file checked with SHA-256
   (`--no-verify` skips the hash);
4. removes files an earlier install left that are no longer in the folder.
   Saved data in `/state/<id>.json` stays;
5. restarts OreoOS, so the app is in the Apps drawer.

OreoOS imports an app once per boot, so to try a change run
`oreo app install` again: OreoOS restarts and loads the new code.

`list` and `remove` are the same as `oreo apps list` and `oreo apps remove`.

### `oreo wifi`: Wi-Fi

```sh
oreo wifi scan
oreo wifi connect "Home Net"
oreo wifi saved
oreo wifi forget "Old Net"
```

See [Wi-Fi setup](#wi-fi-setup).

### `oreo update`: update OreoOS

```sh
oreo update                    # newest stable release
oreo update --check            # only say whether there is a newer one
oreo update --channel beta     # newest beta release
```

The badge updates itself with the same code its **Settings > Updates** page
uses (`oreoOS/ota.py`). `oreo` steers it and shows each step:

1. Reads the OreoOS version on the badge.
2. Brings up the badge's Wi-Fi from its saved networks. Set up a network
   first (see [Wi-Fi setup](#wi-fi-setup)).
3. Asks GitHub, from the badge, for the newest release on the channel.
4. Compares the badge's files with the release and shows how many change
   and how much will be downloaded.
5. Asks you, checks the free space, and has the badge download the changed
   files into `/_ota`, checking each file's SHA-256.
6. Moves the files into place, as the badge does when it boots with an
   update waiting.
7. Restarts the badge, waits for it to come back on USB (it may come back
   under another port name) and reports the version it booted.

Apps, photos, documents, saved Wi-Fi and your profile are kept.

- **Ctrl-C** works until step 6. During step 6 it is held until the files
  are in place.
- **Power loss** during step 6 is safe: the badge finishes the update the
  next time it starts.
- **An update the badge already downloaded** by itself is offered for
  installing.
- **Without a terminal**, `oreo update` answers "no" unless you pass
  `--yes`.
- **GitHub limit:** the badge asks GitHub without a token, which allows 60
  requests an hour per network.

**Developers:** `--repo` deploys from an OreoOS checkout instead of a
release:

```sh
oreo update --repo ~/src/oreo            # ./deploy --board from that checkout
oreo update --repo ~/src/oreo --clean    # wipe the badge's files first (asks)
```

With `--repo`, `update` also takes:

- `--force`: upload every file;
- `--no-bump`: keep the OreoOS version;
- `--override APPS`: replace these app folders.

### `oreo logs`: console output

```sh
oreo logs              # follow what OreoOS prints; Ctrl-C to stop
oreo logs --restart    # restart OreoOS first, to see the boot log
```

`logs` does not stop OreoOS. It keeps following when the badge restarts, or
is unplugged and plugged back in, even under a new port name. While the
Transfer app is open you will see its `@OTB ...` protocol lines in the log;
that is normal.

### `oreo shell`: MicroPython REPL

```sh
oreo shell
```

Pauses OreoOS and opens the badge's MicroPython prompt. Leave with
**Ctrl-]** or **Ctrl-X**, and OreoOS starts again.

### `oreo run`: run a script

```sh
oreo run blink.py
```

Runs a file from the computer on the badge and streams its output.
**Ctrl-C** stops the script on the badge.

### `oreo dev`: live editing

```sh
oreo dev ./scripts                 # mount ./scripts at /remote, open the REPL
oreo dev ./scripts --run blink.py  # and run blink.py from it
```

OreoOS stops, the folder on the computer appears on the badge at `/remote`,
and the REPL opens there. `import mymodule` loads your local copy, so edits
need no copying. MicroPython imports a module once: after an edit, run
`import sys; del sys.modules['mymodule']` and import it again. To reach
OreoOS's own modules, `import sys; sys.path.append('/')`.

OreoOS does not run while you are in the REPL. To edit an app live, mount a
folder that contains `apps/<id>/` and start OreoOS from the REPL:

```sh
oreo dev ~/work                    # ~/work/apps/my_app/{manifest.json,main.py,...}
```

```python
>>> import os; os.chdir("/"); exec(open("/main.py").read())
```

Apps under `/remote/apps` load from the computer instead of `/apps` (the
console prints `[dev] my_app from /remote/apps`), and OreoOS re-reads an
app's files every time it opens, so save on the computer, press HOME and
reopen the app. Leaving `oreo dev` resets the badge and the installed apps
are used again. To copy an app onto the badge instead, use
[`oreo app install`](#oreo-app-install-an-app-from-a-folder). Details:
[docs/APPS.md](APPS.md#live-editing-with-oreo-dev).

Leave with Ctrl-] or Ctrl-X. Ctrl-D soft-resets the badge, which starts
OreoOS and ends live editing.

### `oreo flash`: firmware

```sh
oreo flash --repo ~/src/oreo            # erase, write firmware, install OreoOS (asks)
oreo flash --repo ~/src/oreo --build    # run ./build-firmware first
```

Needs an OreoOS checkout. Erasing always asks first, and it removes
everything on the badge, including photos, documents and Store apps.

### `oreo doctor`: diagnose the connection

```sh
oreo doctor
```

Checks, in this order:

1. the computer: Python, pyserial, mpremote, ffmpeg;
2. the badge's USB ID, and what any other USB IDs it finds probably are;
3. on Linux, membership of `dialout` / `uucp`;
4. only then, it opens the port to read the firmware and OreoOS versions.

It ends with numbered **next steps**, failures first. It exits with `0` when
nothing failed (warnings are fine) and `1` otherwise.

### `oreo help`

```sh
oreo help            # list commands
oreo help transfer   # one command, with examples
```

## Wi-Fi setup

The badge uses Wi-Fi **only for the internet**: the App Store, OreoOS
updates, GitHub data (Badge, Commits), weather and the clock. Files never go
over Wi-Fi; they go over USB with `oreo transfer`. The badge joins 2.4 GHz
networks only.

The badge has no keyboard, so networks with a password are added from the
computer:

```sh
oreo wifi scan                     # networks the badge can see, with signal and security
oreo wifi connect "Home Net"       # asks for the password without echo
oreo wifi saved                    # names of saved networks
oreo wifi forget "Old Net"
```

`connect` joins the network and saves it, so OreoOS joins it by itself from
then on. Open networks can also be joined on the badge, from
**Settings > WiFi**.

| Option | Meaning |
|---|---|
| `--open` | The network has no password |
| `--no-save` | Join now, but do not save it |
| `--save-only` | Save it without trying it now (for a network that is not in range) |
| `--password-stdin` | Read the password from standard input, for scripts |
| `--timeout SECONDS` | How long to wait for the network (default 15) |

```sh
# In a script, so the password never appears on the command line:
printf '%s\n' "$WIFI_PASSWORD" | oreo wifi connect "Home Net" --password-stdin
```

Before touching the badge, `connect` checks that the network name is 1 to 32
bytes and that the password is 8 to 63 characters (or 64 hex digits).

**The password stays private.** It is read before the badge is touched and
sent to the badge once. It is never printed, logged, returned or stored on
the computer, and it is removed from error messages. `oreo wifi saved` lists
names only.

Results are reported plainly:

- **wrong password**;
- **not in range**: the badge sees only 2.4 GHz networks; check
  `oreo wifi scan`;
- **did not answer in time**: move closer, or try `--timeout 30`.

Networks written into the deploy-time `.env` file come back at the next boot
even after `forget`, and `oreo` warns about that. To forget them for good,
remove them from `.env` and deploy again.

## Exit status

These are stable across 1.x, so scripts can rely on them:

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | The command failed; the message says why |
| `2` | Usage error: a missing or invalid argument (checked before the badge is touched) |
| `3` | No badge found, or several and no `--port` |
| `4` | The badge could not be reached: port missing or busy, no answer, connection lost |
| `5` | The badge answers but has no OreoOS, or one too old for the command |
| `130` | Cancelled: Ctrl-C, or "no" at a confirmation |

Special cases:

- `oreo devs` exits `3` when no badge is connected.
- `oreo doctor` exits `1` when a check failed.
- `oreo transfer` exits `1` when the Transfer app is not open, the code is
  wrong, the badge is locked, or a file was refused. A failure to open the
  port is `4`, as for other commands. With no code typed, it exits `130`.

## Troubleshooting

Start with `oreo doctor`. [USB.md](USB.md#troubleshooting) has more on
cables, ports and drivers.

**Connection**

| Symptom | What to do |
|---|---|
| `no Oreo Badge found (USB 303a:83ec)` | Use a data cable (some are charge-only) and, on the DevKitC-1, the **USB** port. `oreo devs --all` shows what is connected. |
| A `303a:1001` device | Stock ESP32-S3 USB-Serial/JTAG: the board has no OreoOS firmware yet, or it is in the bootloader. Flash it with `oreo flash --repo <checkout>`. |
| A `303a:0002` device | Download mode (BOOT was held at reset). Press RESET without BOOT. |
| A `303a:4001` device | Generic MicroPython, not the Oreo Badge build. Flash the badge firmware. |
| A CP210x, CH340, CH343 or CH9102 device | That is the devkit's UART bridge. Plug into the native **USB** port instead. |
| `2 badges connected` | Pick one: `oreo --port /dev/ttyACM1 info` or `export OREO_PORT=/dev/ttyACM1`. |
| `Permission denied` on Linux | Join `dialout` (`uucp` on Arch), then log out and back in. |
| Port busy | Close other programs using it: another `oreo`, `oreo logs`, `mpremote`, Thonny, a serial monitor, the Arduino IDE. |
| `the badge did not answer` (exit 4) | Is the **Transfer** app open? Leave it (HOME) and try again. Otherwise OreoOS is busy with something that delays Ctrl-C (a download, an app): wait a few seconds and retry. If it stays stuck, press RESET or replug. |
| `lost the connection to the badge` (exit 4) | It was unplugged or restarted. Plug it back in, check with `oreo devs`, and run the command again. |
| `this needs OreoOS` (exit 5) | The badge has MicroPython but no OreoOS: `oreo flash --repo <checkout>`. |
| The badge stays at the `>>>` prompt | A command ran with `--reset none`, or OreoOS failed to start. Try `oreo --reset hard info`, then `oreo logs --restart`. |
| Git Bash: `looks like a path on this computer` | Git Bash rewrote `/documents` into a Windows path. Write `:documents/`, or set `MSYS_NO_PATHCONV=1`. |

**Transfer**

| Symptom | What to do |
|---|---|
| `open Transfer on the badge`, then `the Transfer app is not open on the badge` | Open the apps drawer, then **Tools > Transfer**, and run the command again. Give a slow start more time with `--wait 120`. |
| `wrong code` | Type the code exactly as the badge shows it. The characters 0, O, 1, I and L are never used, so what looks like `0` is not one. |
| `too many wrong codes` / `wait 60s` | The badge locked after 5 wrong codes. Wait for the countdown; it then shows a new code. |
| `the session was cancelled on the badge` | Someone pressed **B** on the badge. Run the command again. |
| `the Transfer app was closed` | The app was left in the middle of a session. Open it and run the command again. |
| `the badge waited too long` | The session timed out (5 min without the code, 2 min idle, 20 s mid-file). Run the command again. |
| `not enough free space` | Free space with `oreo transfer list` and `oreo transfer rm`, or `oreo info` / `oreo rm`. |
| `larger than 8192 KB` | Shorten the video with `--seconds`. To make it smaller still, use `oreo add` with `--width` / `--height`. |
| `the badge only takes ...` | Send photos, videos, `.md` or `.txt`; other files cannot be shown on the badge. |
| `SHA-256 mismatch` / `damaged chunk` | The copy was damaged on the way and dropped. Run it again; if it repeats, try another cable or USB port. |
| `speaks Transfer protocol v...` | The CLI and OreoOS are from different generations. Update both: rerun the installer, then `oreo update`. |
| `no code given` | No terminal to ask in. Pass `--code ABC123`. |

**Updates, apps and media**

| Symptom | What to do |
|---|---|
| `oreo update`: `could not get online` | Set up Wi-Fi first: `oreo wifi scan`, `oreo wifi connect <name>`. |
| `oreo update`: `could not reach GitHub` | Check the network. GitHub allows 60 requests an hour per network without a token. |
| `oreo update`: `did not come back on USB` | It may still be installing. Wait, then run `oreo info`. If the screen stays dark, press RESET. |
| `oreo update`: `too old to be updated from the CLI` | Update once from the badge (Settings > Updates) or with `oreo update --repo`. |
| `apps install` fails | Check Wi-Fi first: `oreo wifi saved`, `oreo wifi connect <name>`. |
| Wi-Fi: not in range | The badge sees 2.4 GHz only. Check `oreo wifi scan`. |
| `not enough space on the badge` | See what uses it with `oreo info`; free some with `oreo rm` or `oreo apps remove`. |
| `ffmpeg was not found` | Install ffmpeg (see [Dependencies](#dependencies)). Only videos need it. |
| `checksum mismatch after copy` | Run it again. If it repeats, try another cable or USB port. |
| An installer says `pipx or uv ... neither was found` | Install one of them (the message has the command), then run the installer again. |
| Something else | Re-run with `-v`, and include the `oreo doctor` output in an issue. |

## FAQ

**Is it `oreo` or `oreo-cli`?**
The package is **oreo-cli**. The command is **oreo**; `oreo-cli` also works
and runs the same thing.

**Do I need to clone the OreoOS repository?**
No. Everything except `oreo flash` and the `--repo` developer options works
from the installed CLI alone.

**Can I send files over Wi-Fi?**
No. The old Send Files page and the upload web page are gone. Wi-Fi on the
badge is for the internet only; files go over USB with `oreo transfer` or
`oreo add`.

**Why do I have to type a code?**
The code is shown only on the badge's screen, so typing it proves you can see
the badge you are sending to. Nothing is written until the code is accepted.
See [TRANSFER.md](TRANSFER.md).

**`oreo transfer` or `oreo add`?**
Both convert files the same way and put them in the same places.
`oreo transfer` keeps OreoOS running and needs the Transfer app open and the
code. `oreo add` needs neither, but pauses OreoOS while it copies. It also
has the video size options (`--fps`, `--width`, `--height`) and `--save`.

**Can I send any file with `oreo transfer`?**
Only things the badge can show: photos, videos and Markdown or text
documents. For anything else (app files, your `profile.json`), use
`oreo push`.

**Does the CLI need the internet?**
Only to install it. `oreo update`, `oreo apps install` and `oreo apps refresh`
need the *badge* to be online, because the badge does the downloading.

**Does `oreo update` touch my photos, apps or Wi-Fi?**
No. Only OreoOS's own files change.

**What about Bluetooth?**
Bluetooth file sharing is not available yet. It is planned last, together
with the mobile app (issues #101, #103, #124).

**Several badges on one computer?**
`oreo devs` lists them. Pick one with `--port` or `$OREO_PORT`.

**Windows and macOS?**
Both are supported. On Windows the port is a `COM` name (`--port com5` works).
On macOS, `oreo` uses the `/dev/cu.*` name even if you give the
`/dev/tty.*` one.

**Where are my settings stored on the computer?**
Nowhere. The CLI keeps no configuration and no history.

## Transfer speed

`oreo push`, `oreo add` and the interactive upload send files as base64
inside short MicroPython snippets over the raw REPL ("raw paste" mode):

- Each file goes to a `.part` file in 8 KiB chunks.
- The first chunk rides along with the command that opens the file. The last
  rides with the step that checks the size and SHA-256 on the badge and
  only then renames the file into place.
- Free space is checked once per command, and each folder is created once
  per session.

The numbers below were measured on the simulated badge (execs and bytes of
code; `python3 cli/tests/test_push_speed.py`). They were turned into time
with a model of the USB link: a 1.5 ms round trip, MicroPython's 256-byte
raw-paste window, and 150 KB/s flash writes. So the times are estimates until
they are measured on a badge.

| Case | Execs | Code per file byte | Estimate |
|---|---|---|---|
| 1 MiB file, 4 KiB chunks (0.1.0) | 257 | 1.34 | ~43 KiB/s |
| 1 MiB file, 8 KiB chunks (1.0.0) | 129 | 1.34 | ~44 KiB/s |
| 40 files of 1.5 KiB, 0.1.0 | 240 | | |
| 40 files of 1.5 KiB, 1.0.0 | 81 | 1.99 | ~32 KiB/s |

For big files, the chunk size hardly matters. The time goes to raw-paste flow
control (one round trip per 256 bytes of code) and to flash writes. For many
small files, what counts is fewer execs per file (2 instead of 6).

`oreo transfer` uses a different path: a line protocol to the Transfer app,
with 3 KiB chunks and up to 4 chunks in flight before it waits for an
acknowledgement (see [TRANSFER.md](TRANSFER.md#the-protocol)). Its speed has
not been measured on a badge yet.

## Testing on a badge

CI has no badge. These are the checks to run by hand on one; please attach
the output when you report a problem.

1. `oreo doctor`: all checks pass, ending in "all good".
2. `oreo info`, then `oreo` (the menu): status, files (open a folder, `u` an
   upload, `p` a download), the apps list, saved Wi-Fi, and **q** restarts
   OreoOS.
3. `oreo push` a 1 MiB file and a folder of small files. Note the time and
   speed shown, `oreo pull` them back and compare them (`sha256sum`).
4. Pull the cable during a large `oreo push`. Expect "lost the connection"
   (exit 4) and no traceback. After replugging, the old file at the
   destination is intact, and no `.part` file is left after the next push.
5. `oreo wifi scan`, `oreo wifi connect <name>`, `oreo apps install <app>`.
6. `oreo update --check`, then `oreo update` on a badge one release behind:
   versions shown, progress, restart, "installed and running". Also try it
   with the badge offline (expect the Wi-Fi hint) and when it is up to date.
7. `oreo logs`, then press RESET on the badge: logging carries on after the
   restart. Ctrl-C stops it (also on Windows).
8. `oreo shell`, and `oreo run` a script that prints. Ctrl-C stops it and
   OreoOS restarts.
9. Transfer: open **Tools > Transfer**, then `oreo transfer send` a photo, a
   10-second video and a `.md` file. Each appears in the Gallery or Reader,
   with a notification. Also check:
   - a wrong code: the tries left are shown;
   - five wrong codes: a 60 s lockout, then a new code;
   - **B** on the badge mid-file: no half file is left;
   - Ctrl-C mid-file;
   - `oreo transfer list` and `oreo transfer rm`;
   - running the command with Transfer closed, then opening it while
     `oreo` waits;
   - afterwards, with Transfer closed, `oreo info` still works;
   - with Transfer open, `oreo info` fails with exit 4 and the hint.
10. On Windows (PowerShell and Git Bash) and macOS: `oreo devs`, `oreo info`,
    `oreo push notes.txt :documents/`, `oreo transfer send photo.jpg`, and
    `oreo --port com5 info` / `oreo --port /dev/tty.usbmodem* info`.

## Releasing

Maintainers only. CLI releases are independent of OreoOS releases and do not
touch them:

- the `cli-release` workflow runs only for `cli-v*` tags (on pull requests
  that change `cli/`, it builds and tests without releasing);
- its tags do not match the badge's OTA prefixes (`stable/`, `beta/`);
- the release is created with `--latest=false`, so the repository's "Latest"
  release stays OreoOS.

Steps:

1. In a pull request, set `__version__` in `cli/oreo_cli/__init__.py`, move
   the `Unreleased` notes in `cli/CHANGELOG.md` under a new
   `## [<version>] - <date>` heading, and merge it.
2. Tag the merge commit and push the tag:

   ```sh
   git tag cli-v1.0.0 <commit-on-main>
   git push origin cli-v1.0.0
   ```

3. The workflow then:
   - runs the CLI tests on Linux (Python 3.9 and 3.13) and macOS;
   - checks that the tag matches `__version__` and that `CHANGELOG.md` has a
     section for it;
   - builds the wheel and sdist from `cli/` (with timestamps from the
     commit), writes the `.sha256` files and `SHA256SUMS`, and smoke-tests
     the wheel and both installers on Linux and Windows;
   - adds a build-provenance attestation for both packages;
   - waits for the `cli-release` environment, then publishes the GitHub
     release with the changelog section as its notes. To make releases
     need an approval, add required reviewers to that environment in the
     repository settings. Versions with `a`, `b` or `rc` are marked as
     pre-releases.

If a release run fails after the tag was pushed, fix the problem, delete the
tag (`git push origin :refs/tags/cli-v1.0.0`), and tag again. The installers
skip a tag that has no published release.

# oreo: the Elixpo Oreo Badge CLI

`oreo` finds the badge on USB (ID `303a:83ec`) and controls it: status, files,
apps, photos and videos, Wi-Fi, logs, updates and firmware. It talks to
OreoOS through MicroPython's raw REPL, using `mpremote`'s serial transport
as a library (issue #117).

```sh
oreo                       # find the badge, show its status, open the menu
oreo info
oreo wifi scan
oreo wifi connect "Home Net"     # password asked without echo
oreo add holiday.jpg talk.md
oreo apps install snake
oreo help <command>
```

## Install

Needs Python 3.9+ and [uv](https://docs.astral.sh/uv/) or
[pipx](https://pipx.pypa.io/). The installers download the wheel from the
latest `cli-v*` GitHub release, check its SHA-256 and install it with
whichever of the two is present.

```sh
# Linux, macOS
curl --proto '=https' --tlsv1.2 -LsSf \
  https://raw.githubusercontent.com/elixpo/oreo/main/cli/install.sh | sh
```

```powershell
# Windows
irm https://raw.githubusercontent.com/elixpo/oreo/main/cli/install.ps1 | iex
```

Pin a release with `OREO_CLI_VERSION=cli-v0.1.0`. Or download
`oreo_cli-<version>-py3-none-any.whl` and `SHA256SUMS` from the
[releases](https://github.com/elixpo/oreo/releases), check them, and run
`pipx install oreo_cli-<version>-py3-none-any.whl`; each release also has a
build-provenance attestation (`gh attestation verify <file> -R elixpo/oreo`).

From a checkout: `pipx install ./cli` (or `pip install -e cli/`).

Dependencies: `rich`, `pyserial`, `mpremote` 1.28.x (matching the badge's
MicroPython 1.28), `Pillow`. Videos also need `ffmpeg` on your PATH.

Full guide (every command, Wi-Fi setup, troubleshooting):
[docs/CLI.md](https://github.com/elixpo/oreo/blob/main/docs/CLI.md).
Changes: [CHANGELOG.md](https://github.com/elixpo/oreo/blob/main/cli/CHANGELOG.md).

On Linux, opening the port needs the `dialout` group (`uucp` on Arch):
`sudo usermod -aG dialout $USER`, then log out and back in. `oreo doctor`
checks this.

## Commands

| Command | Does |
|---|---|
| `oreo` | Finds the badge and opens the interactive view (status, files, apps, Wi-Fi, media, shell) |
| `oreo devs [--all]` | Lists badges by USB ID; never opens a port |
| `oreo info` | OreoOS and firmware version, space by category, Wi-Fi, Bluetooth, battery |
| `oreo shell` | MicroPython REPL; OreoOS restarts when you leave (Ctrl-] / Ctrl-X) |
| `oreo ls / push / pull / rm` | Files, with progress bars; pushes are atomic and SHA-256 checked |
| `oreo add <file>...` | Photo/video into the Gallery, `.md`/`.txt` into the Reader, after a space check |
| `oreo apps [list\|refresh\|install\|update\|remove]` | The badge's App Store, over the badge's Wi-Fi |
| `oreo run <file>` | Runs a script and streams its output |
| `oreo dev <folder>` | Mounts a folder at `/remote` for live editing |
| `oreo logs [--restart]` | Follows the console without stopping OreoOS |
| `oreo wifi [scan\|connect\|saved\|forget]` | Wi-Fi setup; Wi-Fi is for the internet only (#120) |
| `oreo update --repo <checkout>` | Runs the checkout's `./deploy --board` |
| `oreo flash --repo <checkout>` | Runs `./deploy --full` (erases the badge; asks first) |
| `oreo doctor` | Cable, port, permissions (Linux `dialout`), firmware banner |

Global options: `--port` (or `$OREO_PORT`), `--reset soft|hard|none` (how
OreoOS is restarted after a command; default `soft`), `--yes`, `--no-color`,
`-v` (show the badge's log lines).

## Behaviour

- **The badge is touched only when a command needs it.** `--help`,
  `oreo help`, `oreo devs`, argument errors and "no badge found" never open
  the port.
- **OreoOS keeps running.** A command stops OreoOS (Ctrl-C, raw REPL, soft
  reset), does its work, then soft-resets so `main.py` starts OreoOS again.
  The interactive view keeps OreoOS paused until you quit.
- **Wi-Fi passwords** are read with `getpass` (or `--password-stdin`), sent
  to the badge once and never printed, logged, returned or stored on the
  computer. `oreo wifi saved` only lists names.
- **Space** is checked before copying; converted media is validated before
  it is sent, and its stored size (not the source size) is what counts.
- **Erasing** (`rm -r`, `apps remove`, `update --clean`, `flash`) asks
  first; without a terminal it answers no unless `--yes` is given.

`oreo update` / `oreo flash` need an OreoOS checkout for now. Updating
from GitHub releases without one is future work.

## Development

```sh
python3 -m unittest discover -s cli/tests -v
```

The tests need no badge: `tests/fake.py` has a `FakeTransport` that runs
the CLI's MicroPython snippets in CPython against a fake filesystem and
fake OreoOS modules. Inside the OreoOS repository, `test_contract.py` also
runs them against the real `oreoWare/wifi.py` and `oreoOS/storage.py`.

The media converters in `oreo_cli/media.py` are copied from
`tools/media_ingest.py` and `tools/encode_video_benchmark.py`; keep the
formats in step.

`tests/test_release.py` runs `install.sh` against a local folder with a
stub installer, and checks that the release workflow, both installers and
this changelog agree on asset names and the version.

## Releasing

Set `__version__` in `oreo_cli/__init__.py`, add a `## [<version>]` section
to `CHANGELOG.md`, merge, then push a `cli-v<version>` tag. The
`cli-release` workflow tests, builds, checksums, attests and publishes the
release; it never touches the OreoOS (`stable/`, `beta/`) releases. Details
in [docs/CLI.md](https://github.com/elixpo/oreo/blob/main/docs/CLI.md#releasing).

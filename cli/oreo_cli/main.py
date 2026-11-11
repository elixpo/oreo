"""`oreo` entry point: argument parsing, help, and dispatch.

Nothing here opens a serial port. A command reaches the badge only through
Ctx.session(), after discovery has picked a port, so `--help`, `oreo help`
and commands run with no badge plugged in never touch the hardware.
"""

import argparse
import contextlib
import sys
import time

from . import __version__, commands, discovery
from . import transfer  # noqa: F401  registers `transfer` and `send`
from . import devtools, owner  # noqa: F401  register `new`, `app` and `setup`
from .badge import Badge
from .errors import (EXIT_CANCELLED, EXIT_ERROR, EXIT_LINK, Cancelled, OreoError,
                     is_serial_error, local_error_message)
from .ui import UI, adapt_stdio, esc

HOME = "https://oreo.elixpo.com/docs"

# name -> (one-line summary, long description with examples)
HELP = {
    "devs": ("List connected badges",
             "Lists badges found by their USB ID 303a:83ec, so nobody has to\n"
             "guess /dev/ttyACM* or COM ports. Never opens a port.\n\n"
             "  oreo devs\n  oreo devs --all      also show other USB serial devices"),
    "info": ("OreoOS and firmware version, storage, Wi-Fi, battery",
             "Shows the OreoOS and MicroPython versions, free space by category\n"
             "(system, apps, gallery, documents, misc), Wi-Fi, Bluetooth and battery.\n\n"
             "  oreo info"),
    "shell": ("MicroPython REPL; OreoOS restarts when you leave",
              "Stops OreoOS and opens the badge's MicroPython REPL. Leave with\n"
              "Ctrl-] or Ctrl-X; OreoOS starts again (unless --reset none).\n\n"
              "  oreo shell"),
    "ls": ("List files on the badge",
           "  oreo ls\n  oreo ls /apps\n  oreo ls :documents"),
    "push": ("Copy files to the badge",
             "Copies files (or folders with -r) to the badge with a progress bar.\n"
             "Each file is written to a temporary name, renamed into place and\n"
             "checked with SHA-256. Free space is checked first.\n\n"
             "  oreo push notes.txt /documents/\n"
             "  oreo push -r myapp /apps/myapp"),
    "pull": ("Copy files from the badge",
             "  oreo pull /wifi_seen.json\n"
             "  oreo pull -r /apps/pet ./pet-backup"),
    "rm": ("Remove files from the badge",
           "Folders need -r. OreoOS's own files and anything inside them\n"
           "(/oreoOS, /oreoWare, /assets, built-in apps, /main.py, /secrets.py,\n"
           "/wifi.json, ...) also need --force.\n\n"
           "  oreo rm /documents/old.mdz\n  oreo rm -r /apps/myapp"),
    "add": ("Add a photo, video or document (Gallery / Reader)",
            "Converts the file to the format OreoOS reads, checks it fits, and\n"
            "copies it: photos and videos to the Gallery, .md/.txt to the Reader.\n"
            "Videos need ffmpeg on your PATH.\n\n"
            "  oreo add holiday.jpg\n"
            "  oreo add clip.mp4 --seconds 8\n"
            "  oreo add talk-notes.md"),
    "transfer": ("Send files to the badge's Transfer app (code shown on the badge)",
                 "Open Transfer on the badge, run this, and type the code the badge\n"
                 "shows. Files are converted like `oreo add`, sent over USB, checked\n"
                 "with SHA-256 and land in the Gallery or Reader. OreoOS keeps running.\n\n"
                 "  oreo transfer send holiday.jpg clip.mp4 notes.md\n"
                 "  oreo transfer list\n"
                 "  oreo transfer rm holiday.rz565"),
    "send": ("Same as `oreo transfer send`",
             "  oreo send holiday.jpg notes.md"),
    "apps": ("List, install, update and remove apps",
             "Uses the badge's App Store (oreoOS.store). Installing and updating\n"
             "download over the badge's Wi-Fi, so set that up first (`oreo wifi`).\n\n"
             "  oreo apps                 installed apps and the catalogue\n"
             "  oreo apps refresh         fetch the latest catalogue\n"
             "  oreo apps install snake\n"
             "  oreo apps update          update every app with a newer version\n"
             "  oreo apps remove snake"),
    "run": ("Run a script on the badge",
            "Stops OreoOS, runs the file and streams its output. Ctrl-C stops it.\n\n"
            "  oreo run blink.py"),
    "dev": ("Mount a folder for live editing in the REPL",
            "Stops OreoOS, mounts a folder from your computer at /remote on the\n"
            "badge and opens the REPL there: `import mymodule` loads your local\n"
            "copy, so edits need no copying. A module is imported once; after an\n"
            "edit, `del sys.modules['mymodule']` and import it again. OreoOS does\n"
            "not run meanwhile, and its drawer lists apps from /apps only, so to\n"
            "try an app in OreoOS use `oreo app install`. Leave with Ctrl-] or\n"
            "Ctrl-X (Ctrl-D starts OreoOS and ends live editing).\n\n"
            "  oreo dev ./scripts\n"
            "  oreo dev ./scripts --run blink.py"),
    "logs": ("Follow the badge's console output",
             "Prints what OreoOS writes to the console without stopping it.\n"
             "Ctrl-C to stop.\n\n"
             "  oreo logs\n  oreo logs --restart     restart OreoOS to see boot logs"),
    "wifi": ("Scan, join, list and forget Wi-Fi networks",
             "Wi-Fi on the badge is only for the internet (App Store, updates,\n"
             "GitHub, weather, time). The password is asked for without echo,\n"
             "sent to the badge once, and never printed, logged or kept here.\n\n"
             "  oreo wifi scan\n"
             "  oreo wifi connect \"Home Net\"\n"
             "  oreo wifi saved\n"
             "  oreo wifi forget \"Old Net\""),
    "update": ("Update OreoOS to the newest release",
               "Has the badge download the newest OreoOS release from GitHub over\n"
               "its own Wi-Fi (the same update its Updates page does), shows the\n"
               "versions and the download size, asks, installs it, restarts the\n"
               "badge and checks the new version. Apps, photos, documents and\n"
               "saved Wi-Fi stay. Set up Wi-Fi first (`oreo wifi`).\n\n"
               "  oreo update                  newest stable release\n"
               "  oreo update --check          only say whether there is one\n"
               "  oreo update --channel beta   newest beta release\n\n"
               "Developers: --repo deploys from an OreoOS checkout (./deploy --board)\n"
               "instead; --clean wipes the badge's files first and asks.\n\n"
               "  oreo update --repo ~/src/oreo\n"
               "  oreo update --repo ~/src/oreo --clean"),
    "flash": ("Reflash the firmware from a checkout",
              "Erases the badge, writes the MicroPython firmware and installs\n"
              "OreoOS (./deploy --full). Asks before erasing. --build runs\n"
              "./build-firmware first (which never touches the badge).\n\n"
              "  oreo flash --repo ~/src/oreo"),
    "doctor": ("Check cable, port, permissions and firmware",
               "Looks for the badge and explains what is wrong: wrong cable or\n"
               "port, missing serial permissions (Linux dialout), port busy, wrong\n"
               "firmware, OreoOS missing. Ends with numbered next steps.\n"
               "Exit status 0 when nothing failed, 1 otherwise.\n\n"
               "  oreo doctor"),
    "setup": ("Set the owner profile: GitHub user, name, timezone, weather",
              "Shows what the badge has now, asks for each value (Enter keeps it,\n"
              "- removes it) and writes /profile.json on the badge, which Badge,\n"
              "Identity, Commits, Weather and the clock read (docs/PROFILE.md).\n"
              "No .env.local or checkout needed. Values given as options are saved\n"
              "without prompting. The OpenWeatherMap key is asked without echo and\n"
              "never shown; an empty value removes a key. OreoOS restarts after.\n\n"
              "  oreo setup\n"
              "  oreo setup --show\n"
              "  oreo setup --github-user octocat --name \"Mona Lisa\" --timezone 5.5\n"
              "  oreo setup --lat 12.97 --lon 77.59 --weather-name Bengaluru\n"
              "  oreo setup --owm-key-stdin < owm-key.txt\n"
              "  oreo setup --designation \"\"     remove the title"),
    "new": ("Make a new app folder from the app template",
            "Copies the OreoOS app template (a counter: A adds, B subtracts) into\n"
            "./<id>, with your app's name, id, author and icon module filled in.\n"
            "The id comes from the name: \"My Game\" -> my_game.\n\n"
            "  oreo new my_game\n"
            "  oreo new \"My Game\" --author octocat --dir ~/oreo-apps\n"
            "  oreo app install ./my_game      then try it on the badge"),
    "app": ("Install an app from a folder on this computer",
            "install checks the folder with the same rules as the repo's\n"
            "tools/validate_app.py, copies the files that belong on the badge\n"
            "to /apps/<id>/ (each one checked with SHA-256), removes files an\n"
            "earlier install left behind, and restarts OreoOS so the Apps drawer\n"
            "lists it. Built-in apps are not replaced without --force.\n"
            "Saved data (/state/<id>.json) stays. Store apps: `oreo apps`.\n\n"
            "  oreo app install ./my_game\n"
            "  oreo app list\n"
            "  oreo app remove my_game"),
    "help": ("Help for a command", "  oreo help wifi"),
}


class Formatter(argparse.RawDescriptionHelpFormatter):
    def __init__(self, prog):
        super().__init__(prog, max_help_position=30)


def _sub(subs, name, **kw):
    summary, desc = HELP[name]
    return subs.add_parser(name, help=summary, description=summary + "\n\n" + desc,
                           formatter_class=Formatter, **kw)


def build_parser():
    p = argparse.ArgumentParser(
        prog="oreo", formatter_class=Formatter,
        description="oreo %s: control the Elixpo Oreo Badge over USB.\n\n"
                    "Run `oreo` with no command to find the badge and open the\n"
                    "interactive view. Docs: %s" % (__version__, HOME),
        epilog="`oreo help <command>` shows details and examples.\n"
               "Exit status: 0 ok, 1 error, 2 usage, 3 no badge (or several),\n"
               "4 badge unreachable or busy, 5 OreoOS missing, 130 cancelled.")
    p.add_argument("--version", action="version", version="oreo-cli " + __version__)
    p.add_argument("-p", "--port", help="serial port (default: the one badge found; $OREO_PORT)")
    p.add_argument("--reset", choices=("soft", "hard", "none"), default="soft",
                   help="how to restart OreoOS after a command (default: soft)")
    p.add_argument("-y", "--yes", action="store_true", help="answer yes to confirmations")
    p.add_argument("--no-color", action="store_true", help="plain output")
    p.add_argument("-v", "--verbose", action="store_true", help="show the badge's log lines")

    subs = p.add_subparsers(dest="cmd", metavar="<command>")

    s = _sub(subs, "devs")
    s.add_argument("--all", action="store_true", help="show every USB serial device")

    _sub(subs, "info")
    _sub(subs, "shell")

    s = _sub(subs, "ls")
    s.add_argument("path", nargs="?", default="/")

    s = _sub(subs, "push")
    s.add_argument("sources", nargs="+", metavar="local")
    s.add_argument("dest", metavar="badge-path")
    s.add_argument("-r", "--recursive", action="store_true", help="copy folders")
    s.add_argument("--no-verify", action="store_true", help="skip the SHA-256 check")

    s = _sub(subs, "pull")
    s.add_argument("source", metavar="badge-path")
    s.add_argument("dest", nargs="?", default=".", metavar="local")
    s.add_argument("-r", "--recursive", action="store_true", help="copy folders")

    s = _sub(subs, "rm")
    s.add_argument("paths", nargs="+", metavar="badge-path")
    s.add_argument("-r", "--recursive", action="store_true", help="remove folders")
    s.add_argument("--force", action="store_true", help="allow removing OreoOS files")

    s = _sub(subs, "add")
    s.add_argument("files", nargs="+", metavar="file")
    s.add_argument("--kind", choices=("image", "video", "document"), help="override detection")
    s.add_argument("--seconds", type=float, default=10.0, help="video length (default 10)")
    s.add_argument("--fps", type=int, default=24, help="video frame rate (default 24)")
    s.add_argument("--width", type=int, default=180, help="video width (default 180)")
    s.add_argument("--height", type=int, default=135, help="video height (default 135)")
    s.add_argument("--photo-max", type=int, default=240, help="longest photo side (default 240)")
    s.add_argument("--save", metavar="DIR", help="also keep the converted files here")

    transfer.add_arguments(_sub(subs, "transfer"))
    transfer.add_send_arguments(_sub(subs, "send"))

    s = _sub(subs, "apps")
    s.add_argument("action", nargs="?", default="list",
                   choices=("list", "refresh", "install", "update", "remove"))
    s.add_argument("app", nargs="?", help="app id (see `oreo apps`)")

    s = _sub(subs, "setup")
    s.add_argument("--show", action="store_true", help="only print the profile (key hidden)")
    s.add_argument("--github-user", metavar="LOGIN", help="GitHub user for Badge and Commits")
    s.add_argument("--name", metavar="TEXT", help="name on the Identity card")
    s.add_argument("--designation", metavar="TEXT", help="title under the name")
    s.add_argument("--timezone", metavar="HOURS",
                   help="hours from UTC, -12 to +14: 5.5, -4, +05:30")
    s.add_argument("--lat", metavar="DEG", help="weather latitude, -90 to 90")
    s.add_argument("--lon", metavar="DEG", help="weather longitude, -180 to 180")
    s.add_argument("--weather-name", metavar="TEXT", help="place name shown by Weather")
    s.add_argument("--owm-key", metavar="KEY", help="OpenWeatherMap API key (prefer the prompt)")
    s.add_argument("--owm-key-stdin", action="store_true",
                   help="read the OpenWeatherMap key from standard input")

    s = _sub(subs, "new")
    s.add_argument("name", help="app name or id, e.g. my_game or \"My Game\"")
    s.add_argument("--name", dest="display_name", metavar="TEXT",
                   help="name shown on the badge (default: from the id)")
    s.add_argument("--author", help="your GitHub handle (default: from git config)")
    s.add_argument("--dir", metavar="PATH", help="where to create it (default: here)")

    s = _sub(subs, "app")
    s.add_argument("action", choices=("install", "list", "remove"))
    s.add_argument("target", nargs="?", metavar="folder|id",
                   help="install: the app folder; remove: the app id")
    s.add_argument("--force", action="store_true", help="install over a built-in app")
    s.add_argument("--no-verify", action="store_true", help="skip the SHA-256 check")

    s = _sub(subs, "run")
    s.add_argument("file")

    s = _sub(subs, "dev")
    s.add_argument("folder")
    s.add_argument("--run", metavar="FILE", help="run this file from the folder after mounting")

    s = _sub(subs, "logs")
    s.add_argument("--restart", action="store_true", help="restart OreoOS to show boot logs")

    s = _sub(subs, "wifi")
    s.add_argument("action", nargs="?", default="saved",
                   choices=("scan", "connect", "saved", "forget"))
    s.add_argument("ssid", nargs="?")
    s.add_argument("--no-save", action="store_true", help="connect without saving the network")
    s.add_argument("--save-only", action="store_true",
                   help="save the network without trying it now")
    s.add_argument("--open", action="store_true", help="the network has no password")
    s.add_argument("--password-stdin", action="store_true",
                   help="read the password from standard input (for scripts)")
    s.add_argument("--timeout", type=float, default=15.0, help="seconds to wait (default 15)")

    s = _sub(subs, "update")
    s.add_argument("--check", action="store_true", help="only check for a newer release")
    s.add_argument("--channel", choices=("stable", "beta"), default="stable",
                   help="release channel (default: stable)")
    s.add_argument("--repo", help="developers: deploy from this OreoOS checkout instead")
    s.add_argument("--clean", action="store_true", help="with --repo: wipe the badge's files first")
    s.add_argument("--force", action="store_true", help="with --repo: upload every file")
    s.add_argument("--no-bump", action="store_true", help="with --repo: keep the OreoOS version")
    s.add_argument("--override", metavar="APPS", help="with --repo: replace these app folders")

    s = _sub(subs, "flash")
    s.add_argument("--repo", help="path to an OreoOS checkout (required)")
    s.add_argument("--build", action="store_true", help="build the firmware first")

    _sub(subs, "doctor")

    s = _sub(subs, "help")
    s.add_argument("topic", nargs="?")
    return p


class Ctx:
    """What a command needs: options, UI, and a lazily opened badge."""

    def __init__(self, args, ui, comports=None, link_factory=None, runner=None,
                 sleep=None, monotonic=None):
        self.args = args
        self.ui = ui
        self.comports = comports
        self._link_factory = link_factory
        self.runner = runner
        self.sleep = sleep or time.sleep          # injectable for tests
        self.monotonic = monotonic or time.monotonic

    def port(self):
        return discovery.pick(self.args.port, self.comports)

    def link(self, port):
        if self._link_factory:
            return self._link_factory(port)
        from .transport import SerialLink
        return SerialLink(port)

    def badge(self, port=None):
        on_text = (lambda s: self.ui.note("badge: " + esc(s))) if self.args.verbose else None
        return Badge(self.link(port or self.port()), on_text=on_text)

    @contextlib.contextmanager
    def session(self, reset=None):
        """A connected badge; OreoOS is restarted on the way out."""
        port = self.port()
        b = self.badge(port)
        b.port = port
        try:
            yield b
        finally:
            finish_shielded(b, reset or self.args.reset)


def finish_shielded(b, mode):
    """Restart OreoOS; a second Ctrl-C must not cut that short and leave
    the badge at the MicroPython prompt."""
    try:
        b.finish(mode)
    except KeyboardInterrupt:
        b.finish(mode)


def _transport_error(e):
    """mpremote's TransportError, without importing mpremote eagerly."""
    return type(e).__name__ == "TransportError"


def main(argv=None, ui=None, comports=None, link_factory=None, runner=None,
         sleep=None, monotonic=None):
    if ui is None:
        adapt_stdio()   # a non-UTF-8 pipe (Windows) must not crash on the marks
    parser = build_parser()
    argv = sys.argv[1:] if argv is None else list(argv)
    args = parser.parse_args(argv)
    if ui is None:
        ui = UI(color=not args.no_color, assume_yes=args.yes)
    else:
        ui.assume_yes = ui.assume_yes or args.yes
    if args.cmd == "help":
        topic = args.topic
        if not topic:
            parser.print_help()
            return 0
        if topic not in HELP:
            ui.error("no command called %r" % topic, hint="commands: " + ", ".join(sorted(HELP)))
            return 2
        build_parser().parse_args([topic, "--help"])  # prints and exits 0
    ctx = Ctx(args, ui, comports=comports, link_factory=link_factory, runner=runner,
              sleep=sleep, monotonic=monotonic)
    handler = commands.HANDLERS.get(args.cmd or "")
    try:
        if handler is None:
            from .interactive import run as interactive
            return interactive(ctx) or 0
        return handler(ctx) or 0
    except Cancelled as e:
        ui.warn(e.message)
        return e.code
    except KeyboardInterrupt:
        ui.warn("stopped")
        return EXIT_CANCELLED
    except OreoError as e:
        ui.error(e.message, hint=e.hint, detail=getattr(e, "detail", None) if args.verbose else None)
        return e.code
    except BrokenPipeError:
        # stdout closed early (`oreo cat ... | head`): nothing left to tell.
        return EXIT_ERROR
    except OSError as e:
        if is_serial_error(e):
            # a port that vanished outside the places that already explain it
            ui.error("lost the connection to the badge (%s)" % esc(e),
                     hint="plug it back in, check with `oreo devs`, then run the command again")
            return EXIT_LINK
        # anything else is a file or folder on this computer
        ui.error(esc(local_error_message(e)))
        return EXIT_ERROR
    except Exception as e:   # never a bare traceback for the person
        if _transport_error(e):
            ui.error("the badge did not answer (%s)" % esc(e),
                     hint="unplug and replug the badge, then run `oreo doctor`")
            return EXIT_LINK
        import traceback
        ui.error("unexpected error: %s: %s" % (type(e).__name__, esc(e)),
                 hint="this is a bug in oreo; please report it with `oreo -v ...` output "
                      "at https://github.com/elixpo/oreo/issues",
                 detail=traceback.format_exc() if args.verbose else None)
        return EXIT_ERROR

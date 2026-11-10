"""`oreo` with no command: find the badge, show its status, then a menu.

A simple menu-driven view (status, file browser, apps, Wi-Fi, media). The
badge stays in the raw REPL while the view is open, so OreoOS is paused;
it restarts when you quit.
"""

import posixpath
from pathlib import Path

from . import commands
from .badge import norm
from .errors import Cancelled, OreoError
from .ui import esc, human

MENU = [("1", "status"), ("2", "files"), ("3", "apps"), ("4", "Wi-Fi"),
        ("5", "add a photo, video or document"), ("s", "shell"), ("q", "quit")]


def _menu(ui, items):
    ui.print("  ".join("[accent]%s[/] %s" % (k, esc(label)) for k, label in items))


def _guard(ui, fn, *a):
    """Run one menu action; report errors and stay in the view."""
    try:
        return fn(*a)
    except Cancelled as e:
        ui.warn(e.message)
    except OreoError as e:
        ui.error(e.message, hint=e.hint)
    return None


def files_view(ui, b):
    cwd = "/"
    while True:
        entries = b.ls(cwd)
        ui.header("files", cwd)
        ui.table(["#", "Name", ">Size"],
                 [[str(i + 1), ("[accent]%s/[/]" % esc(e["name"])) if e["dir"] else esc(e["name"]),
                   "" if e["dir"] else human(e["size"])] for i, e in enumerate(entries)],
                 empty="empty folder")
        ui.note("number: open folder · ..: up · p <n>: download · d <n>: delete · q: back")
        cmd = ui.ask("files", default="q").strip()
        if cmd in ("q", ""):
            return
        if cmd == "..":
            cwd = posixpath.dirname(cwd.rstrip("/")) or "/"
            continue
        verb, _, num = cmd.partition(" ")
        if verb.isdigit():
            verb, num = "o", verb
        if not num.strip().isdigit() or not 1 <= int(num) <= len(entries):
            ui.warn("pick a number from the list")
            continue
        e = entries[int(num) - 1]
        path = norm(posixpath.join(cwd, e["name"]))
        if verb == "o":
            if e["dir"]:
                cwd = path
            else:
                ui.note("%s: %s (p %s to download)" % (esc(path), human(e["size"]), num))
        elif verb == "p" and not e["dir"]:
            def _pull():
                with ui.progress(esc(e["name"]), total=e["size"]) as update:
                    data = b.read_file(path, progress=update)
                Path(e["name"]).write_bytes(data)
                ui.ok("saved %s" % esc(Path(e["name"]).resolve()))
            _guard(ui, _pull)
        elif verb == "d":
            if commands.is_protected(path):
                ui.error("%s belongs to OreoOS" % esc(path), hint="use `oreo rm --force` outside the view")
            elif ui.confirm("Delete %s%s?" % (esc(path), " and everything inside" if e["dir"] else "")):
                _guard(ui, b.rm, path, e["dir"])
        else:
            ui.warn("unknown action")


def apps_view(ui, b):
    commands.apps_action(ui, b, "list")
    while True:
        ui.note("i <id>: install · u: update all · r <id>: remove · f: refresh catalogue · q: back")
        cmd = ui.ask("apps", default="q").strip()
        verb, _, app = cmd.partition(" ")
        app = app.strip() or None
        if verb in ("q", ""):
            return
        action = {"i": "install", "u": "update", "r": "remove", "f": "refresh",
                  "l": "list"}.get(verb)
        if not action:
            ui.warn("unknown action")
            continue
        _guard(ui, commands.apps_action, ui, b, action, app)


def wifi_view(ui, b):
    _guard(ui, commands.wifi_saved, ui, b)
    while True:
        ui.note("s: scan · c <name>: connect · f <name>: forget · l: saved · q: back")
        cmd = ui.ask("wifi", default="q").strip()
        verb, _, ssid = cmd.partition(" ")
        ssid = ssid.strip()
        if verb in ("q", ""):
            return
        if verb == "s":
            _guard(ui, commands.wifi_scan, ui, b)
        elif verb == "l":
            _guard(ui, commands.wifi_saved, ui, b)
        elif verb == "c" and ssid:
            password = ui.secret("Password for %s (empty for an open network)" % ssid)
            _guard(ui, commands.wifi_connect, ui, b, ssid, password)
            password = None
        elif verb == "f" and ssid:
            if ui.confirm("Forget %s?" % esc(ssid)):
                _guard(ui, commands.wifi_forget, ui, b, ssid)
        else:
            ui.warn("unknown action (names with spaces are fine: c Home Net)")


def media_view(ui, b):
    path = ui.ask("file to add (photo, video, .md/.txt)", default="").strip().strip("'\"")
    if not path:
        return
    prepared = commands.prepare_media(ui, [path], commands.MediaOptions())
    commands.send_media(ui, b, prepared)


def run(ctx):
    ui = ctx.ui
    ui.header("Oreo Badge", "looking for a badge on USB")
    with ctx.session() as b:
        with ui.status("reading the badge"):
            info = b.info()
        commands.show_info(ui, info, b.port)
        if not ui.interactive:
            ui.note("no terminal: showing status only. `oreo help` lists the commands.")
            return 0
        ui.note("OreoOS is paused while this view is open and restarts when you quit.")
        while True:
            ui.print("")
            _menu(ui, MENU)
            choice = ui.ask("choose", default="q").strip().lower()
            if choice in ("q", "quit", "exit", ""):
                break
            if choice == "1":
                _guard(ui, lambda: commands.show_info(ui, b.info(), b.port))
            elif choice == "2":
                _guard(ui, files_view, ui, b)
            elif choice == "3":
                _guard(ui, apps_view, ui, b)
            elif choice == "4":
                _guard(ui, wifi_view, ui, b)
            elif choice == "5":
                _guard(ui, media_view, ui, b)
            elif choice == "s":
                b.link.friendly()
                ui.header("shell", "Ctrl-] or Ctrl-X to go back to the menu")
                commands._repl(b.link, ui)
                ui.print("")
                b.link.enter(soft_reset=False)
            else:
                ui.warn("choose one of: " + ", ".join(k for k, _ in MENU))
    ui.ok("OreoOS is starting again" if ctx.args.reset != "none" else "done")
    return 0

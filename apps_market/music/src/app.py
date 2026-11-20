"""Music: the owner's own MP3s, from the badge's microSD card.

Home: microSD card (browse folders), Play whole card, Shuffle, Repeat.
In a folder, the first row plays the whole folder; A on a song plays the
folder from that song. On the player: LEFT/RIGHT previous / next, UP/DOWN
volume, A play/stop, B back. The title, artist and album come from the
file's ID3 tags. Touch on every screen.

The card is mounted at /sd from a worker; on the PCB badge its card-detect
switch tells when one is in. Copy music onto the card with a computer (any
folders; MP3 files). Volume, shuffle and repeat are kept with oreoOS.state.
"""

import oreoOS
from oreoOS import api, theme, widgets

try:
    from oreoOS import state, mediaui
except ImportError:         # an OS from before the audio apps
    state = mediaui = None

from . import id3, library

APP_ID = "music"

BUTTONS = (("prev", "|<"), ("play", ">/||"), ("next", ">|"),
           ("vol-", "VOL-"), ("vol+", "VOL+"))

PLAY_FOLDER = "> Play this folder"


class App(oreoOS.App):
    name = "Music"
    SHOW_LOADING = False

    def on_enter(self, os):
        super().on_enter(os)
        self.player = None
        self._dirty = True
        if mediaui is None:
            self.view = "oldos"
            return
        self.saved = state.load(APP_ID, {"volume": 60, "shuffle": False, "repeat": 0})
        self.volume = int(self.saved.get("volume", 60))
        self.shuffle = bool(self.saved.get("shuffle", False))
        self.repeat = int(self.saved.get("repeat", 0)) % 3
        self.view = "list"
        self.kind = "home"
        self.title = "MUSIC"
        self.stack = []
        self.list = mediaui.ListView()
        self.folder = None
        self.jobs = {}
        self.message = None
        self.queue = None
        self.tags = {}
        self.sd = getattr(os, "sdcard", None)
        self.card = None            # None unknown, False no card, True mounted
        self._card_t = 0.0
        self._seq = -1
        self._clock_t = 0.0
        self._home()
        if not mediaui.has_speaker(os):
            self.view = "nospeaker"
            return
        try:
            from oreoOS import player
        except ImportError:
            player = None
        if player is None:
            self.view = "oldos"
            return
        os.audio.volume = self.volume
        self.player = player.Player(os.audio)
        self._mount()

    def on_exit(self):
        if self.player is not None:
            self.player.stop()
        if mediaui is not None:
            self._save()

    def _save(self):
        self.saved.update({"volume": self.volume, "shuffle": self.shuffle,
                           "repeat": self.repeat})
        state.save(APP_ID, self.saved)

    def realtime_mode(self):
        return self.player is not None and self.player.state in ("playing", "buffering")

    # ── background work ─────────────────────────────────────────────────
    def _job(self, name, fn, label=None):
        j = self.jobs.get(name)
        if j is not None and j.busy():
            return
        from oreoOS import cache
        j = cache.Refresh(fn)
        self.jobs[name] = j
        if label:
            self.message = label
        j.start()
        self._dirty = True

    def _mount(self):
        sd = self.sd
        if sd is None:
            self.card = False
            return
        if sd.present() is False:
            self.card = False
            return
        self._job("mount", sd.mount, "Reading the card...")

    # ── menus ───────────────────────────────────────────────────────────
    def _home_items(self):
        items = [("card", "microSD card"), ("all", "Play whole card"),
                 ("shuffle", "Shuffle: " + ("on" if self.shuffle else "off")),
                 ("repeat", "Repeat: " + library.REPEAT_NAMES[self.repeat])]
        if self.queue is not None:
            items.insert(0, ("now", "Now playing"))
        return items

    def _home(self):
        self.kind, self.title = "home", "MUSIC"
        self.list.set(self._home_items(), keep=True)

    def _push(self, kind, title, items):
        self.stack.append((self.kind, self.title, self.list.items, self.list.sel,
                           self.list.top, self.folder))
        self.kind, self.title = kind, title
        self.list.set(items)
        self.view = "list"
        self._dirty = True

    def _back(self):
        if self.view in ("player", "nocard"):
            self.view = "list"
        elif self.stack:
            self.kind, self.title, items, sel, top, self.folder = self.stack.pop()
            if self.kind == "home":
                items = self._home_items()
            self.list.set(items)
            self.list.sel, self.list.top = sel, top
        else:
            self.os.quit()
        self.message = None
        self._dirty = True

    def _open_folder(self, path):
        self.folder = path
        self._job("list", lambda: (path, library.list_dir(path)), "Reading...")

    def _select(self):
        it = self.list.current()
        if it is None:
            return
        if self.kind == "home":
            k = it[0]
            if k == "now":
                self.view = "player"
            elif k in ("card", "all"):
                if not self.card:
                    self.view = "nocard"
                    if self.card is None or (self.sd and self.sd.present() is not False):
                        self._mount()
                elif k == "card":
                    self._open_folder(self.sd.path)
                else:
                    root = self.sd.path
                    self._job("scan", lambda: library.scan(root), "Scanning the card...")
            elif k == "shuffle":
                self.shuffle = not self.shuffle
                if self.queue is not None:
                    self.queue.set_shuffle(self.shuffle)
                self.list.set(self._home_items(), keep=True)
            elif k == "repeat":
                self.repeat = (self.repeat + 1) % 3
                if self.queue is not None:
                    self.queue.repeat = self.repeat
                self.list.set(self._home_items(), keep=True)
            self._dirty = True
        elif self.kind == "folder":
            if it == PLAY_FOLDER:
                self._play_files(self._folder_files(), 0)
            elif it.endswith("/"):
                path = self.folder.rstrip("/") + "/" + it[:-1]
                self._open_folder(path)
            else:
                files = self._folder_files()
                self._play_files(files, files.index(self.folder.rstrip("/") + "/" + it))
        self._dirty = True

    def _folder_files(self):
        base = self.folder.rstrip("/") + "/"
        return [base + n for n in self.list.items if n != PLAY_FOLDER and not n.endswith("/")]

    # ── playing ─────────────────────────────────────────────────────────
    def _play_files(self, paths, start):
        if not paths:
            return
        self.queue = library.Queue(paths, start, self.shuffle, self.repeat)
        self._start()

    def _start(self):
        it = self.queue.current() if self.queue else None
        if it is None:
            return
        self.tags = {"title": library.display_name(it)}
        self.player.play(it, name="")
        self._job("tags", lambda p=it: (p, id3.read_tags(p)))
        self.player.title = self.tags.get("title", "")
        self.view = "player"
        self._dirty = True

    def _volume(self, delta):
        self.volume = max(0, min(100, self.volume + delta))
        self.os.audio.volume = self.volume
        self._dirty = True

    def _player_action(self, act):
        p = self.player
        q = self.queue
        if act == "play":
            if p.state in ("playing", "buffering", "connecting"):
                p.stop()
            elif q is not None:
                self._start()
        elif act == "next" and q is not None:
            if q.next() is not None:
                self._start()
        elif act == "prev" and q is not None:
            if p.position_s() > 5:
                self._start()           # restart this one first
            elif q.prev() is not None:
                self._start()
        elif act == "vol-":
            self._volume(-10)
        elif act == "vol+":
            self._volume(10)
        self._dirty = True

    # ── input ───────────────────────────────────────────────────────────
    def on_button_press(self, btn):
        if self.view in ("oldos", "nospeaker"):
            if btn == api.BTN_B:
                self.os.quit()
            return
        if self.view == "nocard":
            if btn in (api.BTN_B, api.BTN_A):
                self._back()
            return
        if self.view == "player":
            act = {api.BTN_A: "play", api.BTN_LEFT: "prev", api.BTN_RIGHT: "next",
                   api.BTN_UP: "vol+", api.BTN_DOWN: "vol-"}.get(btn)
            if act:
                self._player_action(act)
            elif btn == api.BTN_B:
                self._back()
            return
        if btn == api.BTN_A:
            self._select()
        elif btn == api.BTN_B:
            self._back()
        elif self.list.key(btn):
            self._dirty = True

    def on_touch(self, event, x, y):
        if event != "down" or self.view in ("oldos", "nospeaker"):
            return
        if self.view == "nocard":
            self._back()
        elif self.view == "player":
            act = mediaui.player_hit(x, y, BUTTONS)
            if act:
                self._player_action(act)
        else:
            if y < widgets.HEADER_H and x < 60:
                self._back()
                return
            i = self.list.hit(x, y)
            if i is not None:
                if i == self.list.sel:
                    self._select()
                else:
                    self.list.sel = i
                self._dirty = True

    # ── frame ───────────────────────────────────────────────────────────
    def _job_done(self, name, job):
        if job.result is None:
            if name == "mount":
                self.card = False
                self.message = "Card: " + ((self.sd.error if self.sd else None) or job.error or "unreadable")
            elif name != "tags":
                self.message = mediaui.clean(job.error or "failed", 36)
            return
        self.message = None
        r = job.result
        if name == "mount":
            self.card = True
            if self.view == "nocard":
                self.view = "list"
        elif name == "list":
            path, (dirs, files) = r
            title = "CARD" if path == (self.sd.path if self.sd else "/sd") else \
                mediaui.clean(path.rsplit("/", 1)[-1], 20).upper()
            items = ([PLAY_FOLDER] if files else []) + [d + "/" for d in dirs] + files
            self._push("folder", title, items)
            self.folder = path
        elif name == "scan":
            if not r:
                self.message = "No MP3 files on the card"
            else:
                self._play_files(r, 0)
        elif name == "tags":
            path, tags = r
            q = self.queue
            if q is not None and q.current() == path:
                self.tags = {"title": tags.get("title") or library.display_name(path),
                             "artist": tags.get("artist", ""), "album": tags.get("album", "")}
                self.player.title = self.tags["title"]
                self.player.station_name = self.tags["artist"]

    def update(self, dt):
        if self.view == "oldos":
            return
        for name in list(self.jobs):
            j = self.jobs[name]
            if j.poll():
                del self.jobs[name]
                self._job_done(name, j)
                self._dirty = True
        p = self.player
        if p is None:
            return
        p.update()
        if p.title_seq != self._seq:
            self._seq = p.title_seq
            self._dirty = True
            if p.state == "ended" and self.queue is not None:
                if self.queue.next(auto=True) is not None:
                    self._start()
        if p.state == "playing" and self.view == "player":
            self._clock_t += dt
            if self._clock_t >= 1:
                self._clock_t = 0
                self._dirty = True
        # card pulled out or put in (PCB card detect), once a second
        self._card_t += dt
        if self._card_t >= 1 and self.sd is not None:
            self._card_t = 0
            present = self.sd.present()
            if present is False and self.card:
                if self.queue is not None:
                    p.stop()
                self.sd.unmount()
                self.card = False
                self.message = "Card removed"
                self._dirty = True
            elif present and self.card is False and "mount" not in self.jobs:
                self._mount()

    def draw(self, d):
        if not self._dirty:
            return
        self._dirty = False
        d.clear(theme.BG)
        if self.view == "oldos":
            widgets.draw_header(d, "MUSIC")
            d.text("Update FaleraOS to use Music.", 16, 100, theme.TEXT_BRIGHT)
            widgets.draw_hint(d, "B back")
            return
        if self.view == "nospeaker":
            widgets.draw_header(d, "MUSIC")
            mediaui.draw_message(d, "Needs the PCB badge (speaker)", mediaui.NEEDS_SPEAKER)
            widgets.draw_hint(d, "B back")
            return
        if self.view == "nocard":
            widgets.draw_header(d, "MUSIC")
            lines = ("Put MP3 files on a microSD card", "with a computer (any folders),",
                     "then insert it in the badge.")
            if "mount" in self.jobs:
                lines = ("Reading the card...",)
            mediaui.draw_message(d, "No microSD card", lines)
            widgets.draw_hint(d, "B back")
            return
        if self.view == "player":
            widgets.draw_header(d, "MUSIC")
            p = self.player
            q = self.queue
            t = self.tags
            detail = p.error if p.error and p.state in ("error", "connecting") else ""
            mode = []
            if q is not None and q.shuffle:
                mode.append("shuffle")
            if q is not None and q.repeat:
                mode.append("repeat " + library.REPEAT_NAMES[q.repeat])
            extra = t.get("album", "")
            if q is not None:
                extra = (extra + "  %d/%d" % (q.pos + 1, len(q))).strip()
            if not detail:
                detail = ", ".join(mode)
            mediaui.draw_player(d, t.get("artist", ""), t.get("title", ""), p.state, detail,
                                self.volume, position=p.position_s(), duration=p.duration_s(),
                                buttons=BUTTONS, extra=extra)
            widgets.draw_hint(d, "LEFT/RIGHT track  A play/stop")
            return
        widgets.draw_header(d, self.title)
        if self.kind == "home":
            self.list.draw(d, lambda it: it[1])
        else:
            self.list.draw(d, lambda it: it if it.endswith("/") or it == PLAY_FOLDER
                           else library.display_name(it))
        if self.message:
            d.rect(0, mediaui.BOTTOM - 16, api.SCREEN_W, 16, theme.CARD, fill=True)
            d.text(mediaui.clean(self.message, 39), 4, mediaui.BOTTOM - 12, theme.TEXT_DIM)
        widgets.draw_hint(d, "A select  B back")

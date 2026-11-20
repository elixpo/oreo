"""Jamendo: Creative Commons music from jamendo.com.

Menu: Featured, Popular this week, Genres, Albums, Search tracks, Search
albums. A track list plays from the chosen track on, one after another; an
album plays in album order. The player shows the track, the artist, the
album and the track's CC licence (Jamendo's licences require the
attribution, so it is always on screen).

Buttons: UP/DOWN move or change the volume on the player, A select /
play-stop, LEFT/RIGHT previous / next track on the player, B back. Touch on
every screen.

The app needs a Jamendo client id, a public app id (src/config.py, or a
"client_id" saved in /state/jamendo.json); with none it shows "Jamendo not
set up" and the steps.
"""

import oreoOS
from oreoOS import api, theme, widgets

try:
    from oreoOS import state, mediaui
except ImportError:         # an OS from before the audio apps
    state = mediaui = None

from . import config, jam

APP_ID = "jamendo"

MENU = (
    ("featured", "Featured"),
    ("popular", "Popular this week"),
    ("genres", "Genres"),
    ("albums", "Albums"),
    ("search", "Search tracks"),
    ("asearch", "Search albums"),
)

BUTTONS = (("prev", "|<"), ("play", ">/||"), ("next", ">|"),
           ("vol-", "VOL-"), ("vol+", "VOL+"))

NOT_SET_UP = (
    "This app needs a Jamendo client id",
    "(a public app id, not a password).",
    "1. Create an app on",
    "   devportal.jamendo.com",
    "2. Put its client id in",
    "   /state/jamendo.json as",
    "   {\"client_id\": \"...\"}",
)


def client_id(saved):
    cid = (saved.get("client_id") or "").strip() if isinstance(saved, dict) else ""
    return cid or config.DEFAULT_CLIENT_ID


class App(oreoOS.App):
    name = "Jamendo"
    SHOW_LOADING = False

    def on_enter(self, os):
        super().on_enter(os)
        self.player = None
        self._dirty = True
        if mediaui is None:
            self.view = "oldos"
            return
        self.saved = state.load(APP_ID, {"volume": 60})
        self.volume = int(self.saved.get("volume", 60))
        self.cid = client_id(self.saved)
        self.view = "list" if self.cid else "setup"
        self.kind = "menu"
        self.title = "JAMENDO"
        self.stack = []
        self.list = mediaui.ListView()
        self.list.set(list(MENU))
        self.kb = None
        self.kb_for = None
        self.job = None
        self.job_what = None
        self.message = None
        self.queue = []
        self.index = 0
        self._seq = -1
        self._clock_t = 0.0
        if not mediaui.has_speaker(os):
            if self.view == "list":
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

    def on_exit(self):
        if self.player is not None:
            self.player.stop()
        if mediaui is not None:
            self.saved["volume"] = self.volume
            state.save(APP_ID, self.saved)

    def realtime_mode(self):
        return self.player is not None and self.player.state in ("playing", "buffering")

    # ── navigation ──────────────────────────────────────────────────────
    def _push(self, kind, title, items):
        self.stack.append((self.kind, self.title, self.list.items, self.list.sel, self.list.top))
        self.kind, self.title = kind, title
        self.list.set(items)
        self.view = "list"
        self._dirty = True

    def _back(self):
        if self.view in ("player", "search"):
            self.view = "list"
            self.kb = None
        elif self.stack:
            self.kind, self.title, items, sel, top = self.stack.pop()
            self.list.set(items)
            self.list.sel, self.list.top = sel, top
        else:
            self.os.quit()
        self.message = None
        self._dirty = True

    def _fetch(self, kind, title, url):
        if self.job is not None and self.job.busy():
            return
        from oreoOS import cache
        self.job = cache.Refresh(lambda: jam.fetch(url))
        self.job_what = (kind, title)
        self.message = "Loading..."
        self.job.start()
        self._dirty = True

    def _select(self):
        it = self.list.current()
        if it is None:
            return
        cid = self.cid
        if self.kind == "menu":
            k = it[0]
            if k == "featured":
                self._fetch("tracks", "FEATURED", jam.tracks_featured(cid))
            elif k == "popular":
                self._fetch("tracks", "POPULAR", jam.tracks_popular(cid))
            elif k == "genres":
                self._push("genres", "GENRES", list(jam.GENRES))
            elif k == "albums":
                self._fetch("albums", "ALBUMS", jam.albums_popular(cid))
            else:
                self.kb = mediaui.Keyboard("Search tracks" if k == "search" else "Search albums")
                self.kb_for = k
                self.view = "search"
                self._dirty = True
        elif self.kind == "genres":
            self._fetch("tracks", it.upper(), jam.tracks_tag(cid, it))
        elif self.kind == "albums":
            self._fetch("album", mediaui.clean(it["name"], 20).upper(), jam.tracks_album(cid, it["id"]))
        else:
            self.queue = list(self.list.items)
            self._play(self.list.sel)

    def _play(self, i):
        if not self.queue:
            return
        self.index = i % len(self.queue)
        t = self.queue[self.index]
        self.player.play(t["url"], name=t["artist"])
        self.player.title = t["name"]
        self.view = "player"
        self._dirty = True

    def _volume(self, delta):
        self.volume = max(0, min(100, self.volume + delta))
        self.os.audio.volume = self.volume
        self._dirty = True

    def _player_action(self, act):
        p = self.player
        if act == "play":
            if p.state in ("playing", "buffering", "connecting"):
                p.stop()
            else:
                self._play(self.index)
        elif act == "next":
            self._play(self.index + 1)
        elif act == "prev":
            self._play(self.index - 1)
        elif act == "vol-":
            self._volume(-10)
        elif act == "vol+":
            self._volume(10)
        self._dirty = True

    # ── input ───────────────────────────────────────────────────────────
    def on_button_press(self, btn):
        if self.view in ("oldos", "setup", "nospeaker"):
            if btn == api.BTN_B:
                self.os.quit()
            return
        if self.view == "search":
            self._kb(self.kb.key(btn))
            self._dirty = True
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

    def _kb(self, r):
        if r == "ok":
            q = self.kb.text.strip()
            self.view = "list"
            self.kb = None
            if q:
                title = ("\"" + q + "\"")[:20].upper()
                if self.kb_for == "search":
                    self._fetch("tracks", title, jam.tracks_search(self.cid, q))
                else:
                    self._fetch("albums", title, jam.albums_search(self.cid, q))
        elif r == "cancel":
            self.view = "list"
            self.kb = None

    def on_touch(self, event, x, y):
        if event != "down" or self.view in ("oldos", "setup", "nospeaker"):
            return
        if self.view == "search":
            self._kb(self.kb.hit(x, y))
            self._dirty = True
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
    def update(self, dt):
        if self.view in ("oldos", "setup"):
            return
        p = self.player
        if p is not None:
            p.update()
            if p.title_seq != self._seq:
                self._seq = p.title_seq
                self._dirty = True
                if p.state == "ended" and self.queue:
                    if self.index + 1 < len(self.queue):
                        self._play(self.index + 1)
            if p.state == "playing" and self.view == "player":
                self._clock_t += dt
                if self._clock_t >= 1:
                    self._clock_t = 0
                    self._dirty = True
        if self.job is not None and self.job.poll():
            job, self.job = self.job, None
            kind, title = self.job_what
            self.message = None
            if job.result is None:
                self.message = mediaui.clean(job.error or "no answer", 36)
            else:
                try:
                    if kind == "albums":
                        items = jam.parse_albums(job.result)
                    else:
                        items = jam.parse_tracks(job.result)
                        if kind == "album":
                            items = jam.album_order(items)
                    self._push("albums" if kind == "albums" else "tracks", title, items)
                except jam.ApiError as e:
                    self.message = "Jamendo: " + str(e)
            self._dirty = True

    def draw(self, d):
        if not self._dirty:
            return
        self._dirty = False
        d.clear(theme.BG)
        widgets.draw_header(d, "JAMENDO" if self.view != "list" else self.title)
        if self.view == "oldos":
            d.text("Update FaleraOS to use Jamendo.", 16, 100, theme.TEXT_BRIGHT)
            widgets.draw_hint(d, "B back")
            return
        if self.view == "setup":
            mediaui.draw_message(d, "Jamendo not set up", NOT_SET_UP)
            widgets.draw_hint(d, "B back")
            return
        if self.view == "nospeaker":
            mediaui.draw_message(d, "Needs the PCB badge (speaker)", mediaui.NEEDS_SPEAKER)
            widgets.draw_hint(d, "B back")
            return
        if self.view == "search":
            self.kb.draw(d)
            widgets.draw_hint(d, "A key  B delete  OK search")
            return
        if self.view == "player":
            p = self.player
            t = self.queue[self.index] if self.queue else {}
            detail = p.error if p.error and p.state in ("error", "connecting") else t.get("licence", "")
            extra = (t.get("album", "") + "  %d/%d" % (self.index + 1, len(self.queue))).strip()
            mediaui.draw_player(d, t.get("artist", ""), t.get("name", ""), p.state, detail,
                                self.volume, position=p.position_s(),
                                duration=t.get("duration") or p.duration_s(),
                                buttons=BUTTONS, extra=extra)
            widgets.draw_hint(d, "LEFT/RIGHT track  A play/stop")
            return
        if self.kind == "menu":
            self.list.draw(d, lambda it: it[1])
        elif self.kind == "genres":
            self.list.draw(d, lambda it: it)
        elif self.kind == "albums":
            self.list.draw(d, lambda it: it["name"] + " - " + it["artist"])
        else:
            self.list.draw(d, lambda it: it["name"] + " - " + it["artist"],
                           right=lambda it: mediaui.mmss(it["duration"]) if it.get("duration") else "")
        if self.message:
            d.rect(0, mediaui.BOTTOM - 16, api.SCREEN_W, 16, theme.CARD, fill=True)
            d.text(mediaui.clean(self.message, 39), 4, mediaui.BOTTOM - 12, theme.TEXT_DIM)
        widgets.draw_hint(d, "A play  B back" if self.kind == "tracks" else "A open  B back")

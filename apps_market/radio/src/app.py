"""Radio: internet radio from the open Radio Browser directory.

Menu: Top stations, Favourites, By country, By genre, Search. A station
list plays the station with A; RIGHT on a row (or the star on the player)
keeps it in Favourites. The player shows the station, the song the station
announces (ICY StreamTitle), the state and the volume.

Buttons: UP/DOWN move, A select / play-stop, B back, LEFT/RIGHT page (in
lists) or volume down/up (on the player), C is the OS panel. Touch: tap a
row, the keyboard keys and the player's buttons.

Lists come from Radio Browser on a worker (oreoOS.cache.Refresh), and the
stream plays on oreoOS.player's worker, so nothing here waits on the
network. Favourites and the volume are kept with oreoOS.state. Leaving the
app stops the radio.
"""

import oreoOS
from oreoOS import api, theme, widgets

try:
    # The Store serves this app to every badge; an OS from before the audio
    # apps has no player or mediaui, and the app says so instead.
    from oreoOS import state, mediaui
except ImportError:
    state = mediaui = None

from . import rb

APP_ID = "radio"
MAX_FAVS = 30

MENU = (
    ("top", "Top stations"),
    ("favs", "Favourites"),
    ("countries", "By country"),
    ("tags", "By genre"),
    ("search", "Search"),
)

RADIO_BUTTONS = (("play", ">/||"), ("vol-", "VOL-"), ("vol+", "VOL+"), ("fav", "FAV"),
                 ("back", "BACK"))


class App(oreoOS.App):
    name = "Radio"
    SHOW_LOADING = False

    def on_enter(self, os):
        super().on_enter(os)
        self.player = None
        if mediaui is None:
            self.view = "oldos"
            self._dirty = True
            return
        saved = state.load(APP_ID, {"favs": [], "volume": 60})
        self.favs = [f for f in saved.get("favs", []) if isinstance(f, dict) and f.get("url")]
        self.volume = int(saved.get("volume", 60))
        self.speaker = mediaui.has_speaker(os)
        self.view = "menu" if self.speaker else "nospeaker"
        self.stack = []
        self.list = mediaui.ListView()
        self.list.set(list(MENU))
        self.kind = "menu"
        self.title = "RADIO"
        self.kb = None
        self.job = None
        self.job_kind = None
        self.click_job = None
        self.message = None
        self.station = None
        self.player = None
        self._seq = -1
        self._dirty = True
        if self.speaker:
            try:
                from oreoOS import player
            except ImportError:         # mediaui without player: not shipped
                player = None
            if player is not None:
                os.audio.volume = self.volume
                self.player = player.Player(os.audio)
            else:
                self.view = "oldos"

    def on_exit(self):
        if self.player is not None:
            self.player.stop()
        if mediaui is not None:
            self._save()

    def _save(self):
        state.save(APP_ID, {"favs": self.favs[:MAX_FAVS], "volume": self.volume})

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
        if self.view == "player":
            self.view = "list"
        elif self.view == "search":
            self.view = "list"
            self.kb = None
        elif self.stack:
            self.kind, self.title, items, sel, top = self.stack.pop()
            self.list.set(items)
            self.list.sel, self.list.top = sel, top
            self.message = None
        else:
            self.os.quit()
        self._dirty = True

    def _fetch(self, kind, title, path):
        if self.job is not None and self.job.busy():
            return
        from oreoOS import cache
        self.job = cache.Refresh(lambda: rb.fetch(path))
        self.job_kind = (kind, title)
        self.message = "Loading " + title.lower() + "..."
        self.job.start()
        self._dirty = True

    def _select_menu(self, key):
        if key == "top":
            self._fetch("stations", "TOP", rb.path_top())
        elif key == "favs":
            self._push("stations", "FAVOURITES", list(self.favs))
        elif key == "countries":
            self._fetch("countries", "COUNTRIES", rb.path_countries())
        elif key == "tags":
            self._fetch("tags", "GENRES", rb.path_tags())
        elif key == "search":
            self.kb = mediaui.Keyboard("Station name")
            self.view = "search"
            self._dirty = True

    def _select(self):
        it = self.list.current()
        if it is None:
            return
        if self.kind == "menu":
            self._select_menu(it[0])
        elif self.kind == "countries":
            self._fetch("stations", it[1].upper()[:20], rb.path_country(it[0]))
        elif self.kind == "tags":
            self._fetch("stations", it[0].upper()[:20], rb.path_tag(it[0]))
        elif self.kind == "stations":
            self._play(it)

    def _play(self, st):
        self.station = st
        self.player.play(st["url"], name=st["name"])
        self.view = "player"
        self._dirty = True
        # Radio Browser counts plays: tell it, off the UI loop, ignore failures.
        if st.get("id") and "://" not in st["id"]:
            from oreoOS import cache
            self.click_job = cache.Refresh(lambda: rb.fetch(rb.path_click(st["id"])))
            self.click_job.start()

    def _is_fav(self, st):
        return any(f.get("url") == st.get("url") for f in self.favs)

    def _toggle_fav(self, st):
        if st is None or not isinstance(st, dict):
            return
        if self._is_fav(st):
            self.favs = [f for f in self.favs if f.get("url") != st.get("url")]
        elif len(self.favs) < MAX_FAVS:
            self.favs.append(rb.station_to_fav(st))
        self._save()
        if self.title == "FAVOURITES" and self.view == "list":
            self.list.set(list(self.favs), keep=True)
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
            elif self.station is not None:
                self._play(self.station)
        elif act == "vol-":
            self._volume(-10)
        elif act == "vol+":
            self._volume(10)
        elif act == "fav":
            self._toggle_fav(self.station)
        elif act == "back":
            self._back()
        self._dirty = True

    # ── input ───────────────────────────────────────────────────────────
    def on_button_press(self, btn):
        if self.view in ("nospeaker", "oldos"):
            if btn == api.BTN_B:
                self.os.quit()
            return
        if self.view == "search":
            r = self.kb.key(btn)
            self._kb_result(r)
            self._dirty = True
            return
        if self.view == "player":
            if btn == api.BTN_A:
                self._player_action("play")
            elif btn == api.BTN_B:
                self._back()
            elif btn in (api.BTN_UP, api.BTN_RIGHT):
                self._volume(10 if btn == api.BTN_UP else 5)
            elif btn in (api.BTN_DOWN, api.BTN_LEFT):
                self._volume(-10 if btn == api.BTN_DOWN else -5)
            return
        if btn == api.BTN_A:
            self._select()
        elif btn == api.BTN_B:
            self._back()
        elif btn == api.BTN_RIGHT and self.kind == "stations":
            self._toggle_fav(self.list.current())
        elif self.list.key(btn):
            self._dirty = True

    def _kb_result(self, r):
        if r == "ok":
            q = self.kb.text.strip()
            self.view = "list"
            self.kb = None
            if q:
                self._fetch("stations", ("\"" + q + "\"")[:20].upper(), rb.path_search(q))
        elif r == "cancel":
            self.view = "list"
            self.kb = None

    def on_touch(self, event, x, y):
        if event != "down" or self.view == "oldos":
            return
        if self.view == "search":
            self._kb_result(self.kb.hit(x, y))
            self._dirty = True
        elif self.view == "player":
            act = mediaui.player_hit(x, y, RADIO_BUTTONS)
            if act:
                self._player_action(act)
        elif self.view == "list":
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
        if self.view == "oldos":
            return
        if self.player is not None:
            self.player.update()
            if self.player.title_seq != self._seq:
                self._seq = self.player.title_seq
                if self.view == "player":
                    self._dirty = True
        if self.click_job is not None and self.click_job.poll():
            self.click_job = None
        if self.job is not None and self.job.poll():
            job, self.job = self.job, None
            kind, title = self.job_kind
            if job.result is None:
                self.message = "Radio Browser: " + (job.error or "no answer")
            else:
                self.message = None
                if kind == "stations":
                    items = rb.parse_stations(job.result)
                elif kind == "countries":
                    items = rb.parse_countries(job.result)
                else:
                    items = rb.parse_tags(job.result)
                self._push(kind, title, items)
            self._dirty = True

    def draw(self, d):
        if not self._dirty:
            return
        self._dirty = False
        if self.view == "oldos":
            d.clear(theme.BG)
            widgets.draw_header(d, "RADIO")
            d.text("Update FaleraOS to use Radio.", 16, 100, theme.TEXT_BRIGHT)
            widgets.draw_hint(d, "B back")
            return
        if self.view == "nospeaker":
            d.clear(theme.BG)
            widgets.draw_header(d, "RADIO")
            mediaui.draw_message(d, "Needs the PCB badge (speaker)", mediaui.NEEDS_SPEAKER)
            widgets.draw_hint(d, "B back")
            return
        if self.view == "search":
            d.clear(theme.BG)
            widgets.draw_header(d, "SEARCH")
            self.kb.draw(d)
            widgets.draw_hint(d, "A key  B delete  OK search")
            return
        if self.view == "player":
            d.clear(theme.BG)
            widgets.draw_header(d, "RADIO")
            p = self.player
            st = self.station or {}
            detail = p.error if p.state == "error" or (p.error and p.state == "connecting") else ""
            if not detail and st.get("bitrate"):
                detail = "%d kb/s" % st["bitrate"]
            mediaui.draw_player(d, st.get("name", ""), p.title or p.station_name or "",
                                p.state, detail, self.volume, fav=self._is_fav(st),
                                buttons=RADIO_BUTTONS)
            widgets.draw_hint(d, "A play/stop  UP/DOWN volume  B back")
            return
        d.clear(theme.BG)
        widgets.draw_header(d, self.title)
        if self.kind == "menu":
            self.list.draw(d, lambda it: it[1])
        elif self.kind == "countries":
            self.list.draw(d, lambda it: it[1], right=lambda it: str(it[2]))
        elif self.kind == "tags":
            self.list.draw(d, lambda it: it[0], right=lambda it: str(it[1]))
        else:
            self.list.draw(d, lambda it: it["name"], mark=self._is_fav,
                           right=lambda it: ("%dk" % it["bitrate"]) if it.get("bitrate") else "")
        if self.message:
            d.rect(0, mediaui.BOTTOM - 16, api.SCREEN_W, 16, theme.CARD, fill=True)
            d.text(mediaui.clean(self.message, 39), 4, mediaui.BOTTOM - 12, theme.TEXT_DIM)
        hint = "A play  RIGHT fav  B back" if self.kind == "stations" else "A open  B back"
        widgets.draw_hint(d, hint)

"""Podcasts: search shows (iTunes Search API), subscribe, list episodes from
the show's RSS feed and play their MP3s, resuming where you stopped.

Menu: Subscriptions, Search. A show (from either) opens its episodes; RIGHT
on a show subscribes or unsubscribes. A plays an episode. On the player:
LEFT jumps back 15 s, RIGHT forward 30 s, UP/DOWN volume, A play/stop, B
back. Seeking needs a server that honours HTTP Range (most podcast hosts
do); when it doesn't, the player says "can't seek on this server".

The feed is parsed while it downloads (src/rss.py) and only the first
MAX_EPISODES episodes are kept, so a huge feed never sits in memory.
Subscriptions and each episode's position are kept with oreoOS.state.
Everything slow runs on a worker; leaving the app stops playback and saves
the position.
"""

import oreoOS
from oreoOS import api, theme, widgets

try:
    from oreoOS import state, mediaui
except ImportError:         # an OS from before the audio apps
    state = mediaui = None

from . import itunes, rss

APP_ID = "podcasts"
MAX_SUBS = 20
MAX_EPISODES = 40
MAX_POSITIONS = 60
SAVE_EVERY_S = 15
BACK_S = 15
FORWARD_S = 30


def pos_key(url):
    """A short, stable key for an episode URL (djb2, hex)."""
    h = 5381
    for ch in url:
        h = ((h * 33) ^ ord(ch)) & 0xFFFFFFFF
    return "%08x" % h


def fetch_feed(url, get_stream=None, max_items=MAX_EPISODES):
    """Run on a worker: (title, episodes) from the feed at url."""
    if get_stream is None:
        try:
            from oreoOS import player
        except ImportError:
            raise OSError("update FaleraOS")
        get_stream = player.get_stream
    p = rss.RssParser(max_items)
    get_stream(url, p.feed, user_agent=itunes.USER_AGENT)
    return p.title, p.items, p.skipped


class App(oreoOS.App):
    name = "Podcasts"
    SHOW_LOADING = False

    def on_enter(self, os):
        super().on_enter(os)
        self.player = None
        self._dirty = True
        if mediaui is None:
            self.view = "oldos"
            return
        saved = state.load(APP_ID, {"subs": [], "pos": [], "volume": 60})
        self.subs = [s for s in saved.get("subs", []) if isinstance(s, dict) and s.get("feed")]
        self.positions = [p for p in saved.get("pos", []) if isinstance(p, list) and len(p) >= 3]
        self.volume = int(saved.get("volume", 60))
        self.view = "list"
        self.kind = "menu"
        self.title = "PODCASTS"
        self.stack = []
        self.list = mediaui.ListView()
        self.list.set([("subs", "Subscriptions"), ("search", "Search")])
        self.kb = None
        self.job = None
        self.job_what = None
        self.message = None
        self.show = None
        self.episode = None
        self.pending_seek = 0
        self._seq = -1
        self._save_t = 0.0
        self._clock_t = 0.0
        self.speaker = mediaui.has_speaker(os)
        if self.speaker:
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
        if mediaui is None:
            return
        self._remember()
        if self.player is not None:
            self.player.stop()
        self._save()

    def _save(self):
        state.save(APP_ID, {"subs": self.subs[:MAX_SUBS],
                            "pos": self.positions[-MAX_POSITIONS:],
                            "volume": self.volume})

    def realtime_mode(self):
        return self.player is not None and self.player.state in ("playing", "buffering")

    # ── positions ───────────────────────────────────────────────────────
    def resume_of(self, url):
        """(seconds, bitrate_kbps) saved for an episode, or (0, 0)."""
        k = pos_key(url)
        for p in self.positions:
            if p[0] == k:
                return p[1], p[2]
        return 0, 0

    def _remember(self):
        """Save where the current episode is (finished ones restart)."""
        p, ep = self.player, self.episode
        if p is None or ep is None or p.state not in ("playing", "buffering", "ended", "idle"):
            return
        k = pos_key(ep["url"])
        self.positions = [q for q in self.positions if q[0] != k]
        pos = p.position_s()
        dur = p.duration_s() or ep.get("duration", 0)
        if p.state == "ended" or (dur and pos > dur - 20):
            pos = 0                 # finished: start over next time
        if pos >= 5:
            self.positions.append([k, int(pos), p.bitrate])
        self.positions = self.positions[-MAX_POSITIONS:]

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

    def _run(self, what, fn, label):
        if self.job is not None and self.job.busy():
            return
        from oreoOS import cache
        self.job = cache.Refresh(fn)
        self.job_what = what
        self.message = label
        self.job.start()
        self._dirty = True

    def _open_show(self, show):
        self.show = show
        self._run(("feed", show), lambda: fetch_feed(show["feed"]), "Loading episodes...")

    def _select(self):
        it = self.list.current()
        if it is None:
            return
        if self.kind == "menu":
            if it[0] == "subs":
                self._push("shows", "SUBSCRIPTIONS", list(self.subs))
            else:
                self.kb = mediaui.Keyboard("Search podcasts")
                self.view = "search"
                self._dirty = True
        elif self.kind == "shows":
            self._open_show(it)
        elif self.kind == "episodes":
            self._play(it)

    def _is_sub(self, show):
        return show is not None and any(s.get("feed") == show.get("feed") for s in self.subs)

    def _toggle_sub(self, show):
        if not isinstance(show, dict) or not show.get("feed"):
            return
        if self._is_sub(show):
            self.subs = [s for s in self.subs if s.get("feed") != show.get("feed")]
        elif len(self.subs) < MAX_SUBS:
            self.subs.append({"name": show.get("name", "")[:60], "author": show.get("author", "")[:40],
                              "feed": show["feed"]})
        self._save()
        if self.title == "SUBSCRIPTIONS" and self.view == "list":
            self.list.set(list(self.subs), keep=True)
        self._dirty = True

    def _play(self, ep):
        if self.player is None:
            self.view = "nospeaker"
            self._dirty = True
            return
        self._remember()
        self.episode = ep
        start, br = self.resume_of(ep["url"])
        name = (self.show or {}).get("name", "")
        self.pending_seek = 0
        if start and br:
            self.player.play(ep["url"], name=name, start_s=start, bitrate_kbps=br)
        else:
            self.player.play(ep["url"], name=name)
            self.pending_seek = start      # seek once the bit rate is known
        self.player.title = ep["title"]
        self.view = "player"
        self.message = None
        self._dirty = True

    def _volume(self, delta):
        self.volume = max(0, min(100, self.volume + delta))
        self.os.audio.volume = self.volume
        self._dirty = True

    def _seek(self, delta):
        p = self.player
        if p is None:
            return
        title = p.title
        if p.seek(delta):
            p.title = title
            self.message = None
        else:
            self.message = "Can't seek on this server" if p.state == "playing" else None
        self._dirty = True

    def _player_action(self, act):
        p = self.player
        if act == "play":
            if p.state in ("playing", "buffering", "connecting"):
                self._remember()
                self._save()
                p.stop()
            elif self.episode is not None:
                self._play(self.episode)
        elif act == "back15":
            self._seek(-BACK_S)
        elif act == "fwd30":
            self._seek(FORWARD_S)
        elif act == "vol-":
            self._volume(-10)
        elif act == "vol+":
            self._volume(10)
        elif act == "fav":
            self._toggle_sub(self.show)
        self._dirty = True

    # ── input ───────────────────────────────────────────────────────────
    def on_button_press(self, btn):
        if self.view in ("oldos", "nospeaker"):
            if btn == api.BTN_B:
                if self.view == "nospeaker":
                    self.view = "list"
                    self._dirty = True
                else:
                    self.os.quit()
            return
        if self.view == "search":
            self._kb(self.kb.key(btn))
            self._dirty = True
            return
        if self.view == "player":
            if btn == api.BTN_A:
                self._player_action("play")
            elif btn == api.BTN_B:
                self._back()
            elif btn == api.BTN_LEFT:
                self._player_action("back15")
            elif btn == api.BTN_RIGHT:
                self._player_action("fwd30")
            elif btn == api.BTN_UP:
                self._volume(10)
            elif btn == api.BTN_DOWN:
                self._volume(-10)
            return
        if btn == api.BTN_A:
            self._select()
        elif btn == api.BTN_B:
            self._back()
        elif btn == api.BTN_RIGHT and self.kind == "shows":
            self._toggle_sub(self.list.current())
        elif self.list.key(btn):
            self._dirty = True

    def _kb(self, r):
        if r == "ok":
            q = self.kb.text.strip()
            self.view = "list"
            self.kb = None
            if q:
                self._run(("search", q), lambda: itunes.search(q), "Searching...")
        elif r == "cancel":
            self.view = "list"
            self.kb = None

    def on_touch(self, event, x, y):
        if event != "down" or self.view in ("oldos", "nospeaker"):
            return
        if self.view == "search":
            self._kb(self.kb.hit(x, y))
            self._dirty = True
        elif self.view == "player":
            act = mediaui.player_hit(x, y)
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
        if self.view == "oldos":
            return
        p = self.player
        if p is not None:
            p.update()
            if p.title_seq != self._seq:
                self._seq = p.title_seq
                self._dirty = True
            if self.pending_seek and p.state == "playing" and p.bitrate:
                s, self.pending_seek = self.pending_seek, 0
                title = p.title
                if p.seekable:
                    p.seek(s - p.position_s())
                    p.title = title
            if p.state == "playing" and self.view == "player":
                self._clock_t += dt
                if self._clock_t >= 1:
                    self._clock_t = 0
                    self._dirty = True
                self._save_t += dt
                if self._save_t >= SAVE_EVERY_S:
                    self._save_t = 0
                    self._remember()
            if p.state == "ended" and self.episode is not None:
                self._remember()
        if self.job is not None and self.job.poll():
            job, self.job = self.job, None
            what = self.job_what
            self.message = None
            if job.result is None:
                self.message = mediaui.clean(job.error or "no answer", 36)
            elif what[0] == "search":
                self._push("shows", ("\"" + what[1] + "\"")[:20].upper(), job.result)
            else:
                title, items, skipped = job.result
                show = what[1]
                if title and not show.get("name"):
                    show["name"] = title
                self._push("episodes", mediaui.clean(show.get("name") or title, 22).upper(), items)
                if not items:
                    self.message = ("No MP3 episodes" if skipped else "No episodes")
            self._dirty = True

    def draw(self, d):
        if not self._dirty:
            return
        self._dirty = False
        d.clear(theme.BG)
        if self.view == "oldos":
            widgets.draw_header(d, "PODCASTS")
            d.text("Update FaleraOS to use Podcasts.", 16, 100, theme.TEXT_BRIGHT)
            widgets.draw_hint(d, "B back")
            return
        if self.view == "nospeaker":
            widgets.draw_header(d, "PODCASTS")
            mediaui.draw_message(d, "Needs the PCB badge (speaker)", mediaui.NEEDS_SPEAKER)
            widgets.draw_hint(d, "B back")
            return
        if self.view == "search":
            widgets.draw_header(d, "SEARCH")
            self.kb.draw(d)
            widgets.draw_hint(d, "A key  B delete  OK search")
            return
        if self.view == "player":
            widgets.draw_header(d, "PODCASTS")
            p = self.player
            ep = self.episode or {}
            detail = p.error if p.error and p.state in ("error", "connecting") else (self.message or "")
            dur = p.duration_s() or ep.get("duration", 0)
            mediaui.draw_player(d, (self.show or {}).get("name", ""), ep.get("title", ""),
                                p.state, detail, self.volume, fav=self._is_sub(self.show),
                                position=p.position_s(), duration=dur,
                                extra=ep.get("date", ""))
            widgets.draw_hint(d, "LEFT -15s  RIGHT +30s  A play/stop")
            return
        widgets.draw_header(d, self.title)
        if self.kind == "menu":
            self.list.draw(d, lambda it: it[1])
        elif self.kind == "shows":
            self.list.draw(d, lambda it: it.get("name", ""), mark=self._is_sub)
        else:
            def right(ep):
                s, _ = self.resume_of(ep["url"])
                if s:
                    return "@" + mediaui.mmss(s)
                return mediaui.mmss(ep["duration"]) if ep.get("duration") else ""
            self.list.draw(d, lambda it: it["title"], right=right)
        if self.message:
            d.rect(0, mediaui.BOTTOM - 16, api.SCREEN_W, 16, theme.CARD, fill=True)
            d.text(mediaui.clean(self.message, 39), 4, mediaui.BOTTOM - 12, theme.TEXT_DIM)
        hint = {"shows": "A open  RIGHT subscribe  B back",
                "episodes": "A play  B back"}.get(self.kind, "A open  B back")
        widgets.draw_hint(d, hint)

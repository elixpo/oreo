"""Spotify: see and control what your Spotify account is playing.

The badge does not play audio; it is a remote for Spotify Connect (a
phone, computer or speaker signed in to the same account).

Screens and buttons:

  LINK      shown until the badge is linked. A QR code and a PIN for
            {relay}/spotify; sign in there on a phone or computer.
            C  new code
  PLAYER    A  play / pause      LEFT / RIGHT  previous / next
            UP / DOWN  volume    B  library    C  unlink (asks first)
  LIBRARY   Liked songs, Recently played, Top tracks, Playlists.
            UP / DOWN  move      A  open / play    B or LEFT  back
            RIGHT on a playlist plays all of it.

Network: every request runs on one worker (oreoOS.cache.Refresh), one at
a time, through net.request (the OS's verified TLS with a deadline).
update() only starts jobs and collects their results, and draw() only
draws. Playback is polled every few seconds while the app is open and
Wi-Fi is up; button presses update the screen at once and the next poll
corrects it. Tokens are saved with oreoOS.state (/state/spotify.json).
"""

import oreoOS
from oreoOS import api, widgets

try:
    from oreoOS import state
except ImportError:         # FaleraOS before oreoOS.state: not supported
    state = None

from . import auth, client

APP_ID = state.app_id(__name__, "spotify") if state else "spotify"

SW = api.SCREEN_W
SH = api.SCREEN_H
TOP = widgets.HEADER_H
BOTTOM = SH - widgets.HINT_H

GREEN = api.rgb(30, 215, 96)
HEADER = api.rgb(16, 110, 56)
BG = api.rgb(18, 18, 20)
CARD = api.rgb(34, 34, 40)
LINE = api.rgb(64, 64, 72)
SEL = api.rgb(48, 60, 54)
MUTED = api.rgb(160, 160, 170)
WARN = api.rgb(245, 170, 60)
WHITE = api.WHITE
BLACK = api.BLACK

T_REQ = 8               # seconds per request (connect + TLS + answer)
POLL_PLAYING_S = 4
POLL_IDLE_S = 12
SETTLE_S = 1.2          # wait after a command before asking what plays
VOL_STEP = 5
VOL_SETTLE_S = 0.4      # send the volume once the presses stop
LIB_TTL_S = 300
ROWS = 5
ROW_H = 34
TOAST_S = 2.5

ROOT = (("liked", "Liked songs"), ("recent", "Recently played"),
        ("top", "Top tracks"), ("playlists", "Playlists"))

_TOASTS = {
    client.NO_DEVICE: "Open Spotify on a device",
    client.PREMIUM: "Needs Spotify Premium",
    client.LIMITED: "Spotify says slow down",
    client.OFFLINE: "No connection",
    client.FAILED: "Spotify said no",
}


def _wall():
    import time
    try:
        return time.time()
    except Exception:
        return 0


def _online():
    try:
        from oreoWare import wifi
        return bool(wifi.is_connected())
    except Exception:
        return False


def _auto_ok():
    """True when an automatic poll may start: threads available (else
    the job would run on the UI loop), past netsvc's boot quiet window,
    and no other background fetch running."""
    try:
        from oreoOS import netsvc
    except Exception:
        return True
    try:
        if not netsvc.has_threads() or netsvc.in_quiet() or netsvc.fetch_busy():
            return False
    except Exception:
        pass
    return True


def _platform_ok():
    """FaleraOS with oreoOS.state, verified TLS and background jobs (the
    app's only OS requirements beyond the App API)."""
    if state is None:
        return False
    try:
        from oreoOS import cache
        from oreoOS import _http
        return hasattr(cache, "Refresh") and hasattr(_http, "tls_wrap")
    except Exception:
        return False


def _send(method, url, headers, body):
    from . import net
    return net.request(method, url, headers, body, T_REQ)


def _post_json(url, payload):
    import json
    status, _h, raw = _send("POST", url, {"Content-Type": "application/json"},
                            json.dumps(payload))
    data = None
    if raw:
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            data = None
    return status, data


def _clock(s):
    s = int(max(0, s))
    return "%d:%02d" % (s // 60, s % 60)


def _fit(text, px, scale=1):
    n = max(1, px // (8 * scale))
    if len(text) <= n:
        return text
    return text[:max(1, n - 2)] + ".."


class App(oreoOS.App):
    name = "Spotify"
    SHOW_LOADING = False
    CAPTURES_C = True       # C is "new code" / "unlink"; double-tap opens the panel

    # ── lifecycle ──────────────────────────────────────────────────

    def on_enter(self, os):
        super().on_enter(os)
        self._ok = _platform_ok()
        self._saved = state.load(APP_ID, {}) if self._ok else {}
        self._relay = auth.relay_base(self._saved)
        self._client = client.Client(self._saved, _send, _wall, self._relay)
        self._pair = auth.Pairing()
        self._t = 0.0
        self._job = None
        self._job_op = None
        self._ops = []
        self._np = None             # now playing (client.parse_player dict)
        self._np_t = 0.0            # self._t when _np was fetched
        self._np_known = False      # a poll has answered since entering
        self._next_poll = 0.0
        self._vol = None            # volume shown while the user adjusts
        self._vol_due = None
        self._vol_hold = 0.0        # ignore polled volume until then
        self._lib = []              # stack of list frames
        self._lib_cache = {}        # kind -> (t, rows)
        self._view = "player" if auth.has_tokens(self._saved) else "link"
        self._confirm = False
        self._qr = None             # (mask, side) of the sign-in URL
        self._toast = ""
        self._toast_until = 0.0
        self._online = _online()
        self._wifi_t = 0.0
        self._shown_s = -1
        if self._view == "link" and self._ok:
            self._start_pairing()
        self._dirty = True

    def on_exit(self):
        # A running request finishes on its worker; its result is dropped.
        self._job = None
        self._ops = []
        self._lib = []
        self._lib_cache = {}
        self._qr = None
        if self._client.changed and self._ok:
            self._save_tokens()

    # ── state helpers ──────────────────────────────────────────────

    def _start_pairing(self):
        self._qr = None
        if self._relay is None:
            self._pair.reset()
            self._pair.state = auth.FAILED
            self._pair.error = auth.ERR_BAD_RELAY
        else:
            self._pair.start()
        self._dirty = True

    def _save_tokens(self):
        keep = dict(self._saved)
        keep.update(self._client.tokens)
        self._saved = keep
        self._client.changed = False
        state.save(APP_ID, keep)

    def _unlink(self, note=""):
        self._saved = auth.clear_tokens(self._saved)
        state.save(APP_ID, self._saved)
        self._client = client.Client(self._saved, _send, _wall, self._relay)
        self._ops = []
        self._np = None
        self._np_known = False
        self._lib = []
        self._lib_cache = {}
        self._view = "link"
        self._confirm = False
        self._start_pairing()
        if note:
            self._say(note)

    def _say(self, msg):
        self._toast = msg
        self._toast_until = self._t + TOAST_S
        self._dirty = True

    def _queue(self, op):
        if op[0] == "control" and op[1] == "volume":
            self._ops = [o for o in self._ops
                         if not (o[0] == "control" and o[1] == "volume")]
        self._ops.append(op)

    def _poll_soon(self, delay=SETTLE_S):
        self._next_poll = self._t + delay

    def _progress(self):
        np = self._np
        if not np:
            return 0
        p = np["progress"]
        if np["playing"]:
            p += self._t - self._np_t
        if np["dur"]:
            p = min(p, np["dur"])
        return p

    # ── worker ─────────────────────────────────────────────────────
    # _work runs on the Refresh thread: network and parsing only, no
    # drawing and no changes to what draw() reads.

    def _work(self, op):
        kind = op[0]
        if kind == "session":
            status, data = _post_json(self._relay + "/api/spotify/session", {})
            qr = None
            if status == 200 and isinstance(data, dict) and data.get("url"):
                try:
                    from . import qr as qrmod
                    size, rows = qrmod.encode(data["url"])
                    qr = qrmod.mono_mask(size, rows, scale=3, quiet=2)
                except Exception:
                    qr = None
            return status, data, qr
        if kind == "pair_poll":
            return _post_json(self._relay + "/api/spotify/poll",
                              {"pin": op[1], "secret": op[2]})
        if kind == "playback":
            return self._client.playback()
        if kind == "control":
            return self._client.control(op[1], op[2])
        if kind == "library":
            return self._client.library(op[1], op[2])
        return None

    def _next_op(self):
        p = self._pair
        if self._view == "link":
            want = p.want(self._t)
            if want and self._online:
                if want == "session":
                    return ("session",)
                return ("pair_poll", p.pin, p.secret)
            return None
        if self._ops:
            return self._ops.pop(0)
        if (self._online and self._t >= self._next_poll and self._view != "link"
                and auth.has_tokens(self._saved) and _auto_ok()):
            return ("playback",)
        return None

    def _start(self, op):
        try:
            from oreoOS import cache
        except Exception:
            return
        if op[0] == "playback":
            # Reschedule now so a slow answer does not stack polls.
            playing = bool(self._np and self._np["playing"])
            self._next_poll = self._t + (POLL_PLAYING_S if playing else POLL_IDLE_S)
        self._job_op = op
        self._job = cache.Refresh(lambda: self._work(op))
        if op[0] in ("session", "pair_poll"):
            self._pair.busy = True
        self._job.start()

    def _finish(self, op, result):
        kind = op[0]
        p = self._pair
        if kind == "session":
            status, data, qr = result if result else (0, None, None)
            p.on_session(status, data, self._t)
            self._qr = qr if p.state == auth.WAITING else None
        elif kind == "pair_poll":
            status, data = result if result else (0, None)
            p.on_poll(status, data, self._t)
            if p.state == auth.LINKED:
                new = auth.apply_token_response(self._saved, p.tokens, _wall())
                p.tokens = None
                if new is not None:
                    self._saved = new
                    state.save(APP_ID, new)
                    self._client = client.Client(new, _send, _wall, self._relay)
                    self._view = "player"
                    self._qr = None
                    self._next_poll = 0.0
                    self._say("Spotify linked")
        elif kind == "playback":
            r, st = result if result else (client.OFFLINE, None)
            if r == client.OK:
                self._np_known = True
                if self._t >= self._vol_hold and self._vol_due is None:
                    self._vol = None        # the server's volume wins again
                elif st and self._vol is not None:
                    st["volume"] = self._vol
                self._np = st
                self._np_t = self._t
            elif r == client.LIMITED:
                self._next_poll = self._t + max(5, self._client.retry_after)
        elif kind == "control":
            r = result or client.FAILED
            if r != client.OK and r in _TOASTS:
                self._say(_TOASTS[r])
            if op[1] != "volume":
                self._poll_soon()
        elif kind == "library":
            r, rows = result if result else (client.OFFLINE, [])
            for fr in self._lib:
                if fr["kind"] == op[1] and fr.get("ref") is op[2]:
                    fr["rows"] = rows
                    fr["loading"] = False
                    fr["error"] = None if r == client.OK else r
            if r == client.OK and op[1] != "playlist":
                self._lib_cache[op[1]] = (self._t, rows)
        if self._client.changed:
            self._save_tokens()
        if self._client.unlinked and self._view != "link":
            self._unlink("Sign-in expired: link again")
        self._dirty = True

    # ── per frame ──────────────────────────────────────────────────

    def update(self, dt):
        self._t += dt
        t = self._t
        if t - self._wifi_t >= 2:
            self._wifi_t = t
            on = _online()
            if on != self._online:
                self._online = on
                self._dirty = True
                if on:
                    self._next_poll = t
        if self._toast and t >= self._toast_until:
            self._toast = ""
            self._dirty = True
        if self._vol_due is not None and t >= self._vol_due:
            self._vol_due = None
            self._vol_hold = t + 3
            self._queue(("control", "volume", self._vol))
        if not self._ok:
            return
        job = self._job
        if job is not None and job.poll():
            op = self._job_op
            self._job = self._job_op = None
            self._finish(op, job.result)
        if self._job is None:
            op = self._next_op()
            if op is not None:
                self._start(op)
        # Redraw when a visible second changes (progress, PIN countdown).
        if self._view == "player":
            s = int(self._progress())
        else:
            s = self._pair.remaining(t)
        if s != self._shown_s:
            self._shown_s = s
            self._dirty = True

    # ── buttons ────────────────────────────────────────────────────

    def on_button_press(self, btn):
        if not self._ok:
            return
        if self._confirm:
            if btn == api.BTN_A:
                self._unlink("Spotify unlinked")
            elif btn in (api.BTN_B, api.BTN_C):
                self._confirm = False
            self._dirty = True
            return
        if self._view == "link":
            if btn == api.BTN_C:
                self._start_pairing()
            return
        if btn == api.BTN_C:
            self._confirm = True
            self._dirty = True
            return
        if self._view == "library":
            self._library_button(btn)
        else:
            self._player_button(btn)
        self._dirty = True

    def _player_button(self, btn):
        np = self._np
        if btn == api.BTN_A:
            if np and np["playing"]:
                np["progress"] = int(self._progress())
                np["playing"] = False
                self._queue(("control", "pause", None))
            else:
                if np:
                    np["playing"] = True
                self._np_t = self._t
                self._queue(("control", "play", None))
        elif btn == api.BTN_RIGHT:
            self._queue(("control", "next", None))
        elif btn == api.BTN_LEFT:
            self._queue(("control", "prev", None))
        elif btn in (api.BTN_UP, api.BTN_DOWN):
            base = self._vol
            if base is None:
                base = (np or {}).get("volume")
            if base is None:
                base = 50
            step = VOL_STEP if btn == api.BTN_UP else -VOL_STEP
            self._vol = max(0, min(100, int(base) + step))
            self._vol_due = self._t + VOL_SETTLE_S
            self._vol_hold = self._t + 3
        elif btn == api.BTN_B:
            self._view = "library"
            if not self._lib:
                self._lib = [{"kind": "root", "title": "LIBRARY", "ref": None,
                              "rows": [{"title": lbl, "kind": k} for k, lbl in ROOT],
                              "sel": 0, "top": 0, "loading": False, "error": None}]

    def _open(self, kind, title, ref=None):
        fr = {"kind": kind, "title": title, "ref": ref, "rows": [],
              "sel": 0, "top": 0, "loading": True, "error": None}
        hit = self._lib_cache.get(kind) if kind != "playlist" else None
        if hit and self._t - hit[0] < LIB_TTL_S:
            fr["rows"] = hit[1]
            fr["loading"] = False
        else:
            self._queue(("library", kind, ref))
        self._lib.append(fr)

    def _library_button(self, btn):
        fr = self._lib[-1]
        rows = fr["rows"]
        if btn in (api.BTN_B, api.BTN_LEFT):
            if len(self._lib) > 1:
                self._lib.pop()
            else:
                self._view = "player"
            return
        if btn in (api.BTN_UP, api.BTN_DOWN) and rows:
            fr["sel"] = (fr["sel"] + (1 if btn == api.BTN_DOWN else -1)) % len(rows)
            if fr["sel"] < fr["top"]:
                fr["top"] = fr["sel"]
            elif fr["sel"] >= fr["top"] + ROWS:
                fr["top"] = fr["sel"] - ROWS + 1
            return
        if not rows:
            return
        row = rows[fr["sel"]]
        kind = fr["kind"]
        if kind == "root" and btn in (api.BTN_A, api.BTN_RIGHT):
            self._open(row["kind"], row["title"].upper())
        elif kind == "playlists":
            if btn == api.BTN_A:
                self._open("playlist", row["name"].upper(), row)
            elif btn == api.BTN_RIGHT:
                self._play_now(row["name"], row["owner"], ("play_context", row["uri"]))
        elif btn == api.BTN_A:
            self._play_now(row["title"], row["artist"], ("play_track", row))

    def _play_now(self, title, artist, cmd):
        self._np = {"playing": True, "progress": 0, "device": (self._np or {}).get("device", ""),
                    "device_id": None, "volume": (self._np or {}).get("volume"),
                    "shuffle": False, "repeat": "off", "title": title,
                    "artist": artist, "album": "", "dur": 0, "uri": ""}
        self._np_t = self._t
        self._queue(("control", cmd[0], cmd[1]))
        self._view = "player"

    # ── drawing ────────────────────────────────────────────────────

    def draw(self, d):
        if not self._dirty:
            return
        self._dirty = False
        d.rect(0, TOP, SW, BOTTOM - TOP, BG, fill=True)
        if not self._ok:
            self._header(d, "SPOTIFY")
            self._lines(d, ("This app needs a newer", "FaleraOS. Update the badge",
                            "in Settings > Updates."), WARN)
            widgets.draw_hint(d, "HOME:exit")
            return
        if self._view == "link":
            self._draw_link(d)
        elif self._view == "library":
            self._draw_library(d)
        else:
            self._draw_player(d)
        if self._confirm:
            self._draw_confirm(d)
        if self._toast:
            w = len(self._toast) * 8 + 20
            x = (SW - w) // 2
            y = BOTTOM - 26
            d.rect(x, y, w, 20, CARD, fill=True)
            d.rect(x, y, w, 20, GREEN)
            d.text(self._toast, x + 10, y + 6, WHITE)

    def _header(self, d, title):
        widgets.draw_header(d, title, color=HEADER, accent=GREEN)

    def _lines(self, d, lines, color=WHITE, y=None):
        y = TOP + 40 if y is None else y
        for i, ln in enumerate(lines):
            c = color if i == 0 else MUTED
            d.text(ln, (SW - len(ln) * 8) // 2, y + i * 16, c)

    def _draw_link(self, d):
        self._header(d, "LINK SPOTIFY")
        p = self._pair
        hint = "C:new code  HOME:exit"
        if not self._online:
            self._lines(d, ("Wi-Fi is not connected", "Connect in Settings > Wi-Fi;",
                            "the code appears by itself."), WARN)
        elif p.state == auth.WAITING:
            self._draw_code(d, p)
        elif p.state == auth.EXPIRED:
            self._lines(d, ("The code expired", "Press C for a new one."), WARN)
        elif p.state == auth.FAILED:
            if p.error == auth.ERR_NOT_CONFIGURED:
                lines = ("Sign-in relay not set up", "The site has no Spotify",
                         "client id or storage yet.", "See the app's README.")
            elif p.error == auth.ERR_BAD_RELAY:
                lines = ("Bad relay URL", "The \"relay\" in",
                         "/state/spotify.json must", "start with https://")
            elif p.error == auth.ERR_UNREACHABLE:
                lines = ("Can't reach the relay", _fit(self._host(), 300),
                         "Press C to try again.")
            else:
                lines = ("The relay said no", _fit(p.detail or "", 300),
                         "Press C to try again.")
            self._lines(d, lines, WARN)
        else:
            self._lines(d, ("Getting a code...", _fit(self._host(), 300)), GREEN)
        widgets.draw_hint(d, hint)

    def _host(self):
        r = self._relay or ""
        return r[8:] if r.startswith("https://") else r

    def _draw_code(self, d, p):
        x0 = 10
        y0 = TOP + 10
        qr = self._qr
        if qr:
            mask, side = qr
            d.rect(x0, y0, side, side, WHITE, fill=True)
            d.blit_mono(mask, x0, y0, side, side, BLACK)
            tx = x0 + side + 12
        else:
            tx = 16
        w = SW - tx - 6
        d.text("Scan, or open", tx, y0 + 2, WHITE)
        d.text(_fit(self._host(), w), tx, y0 + 18, GREEN)
        d.text("/spotify", tx, y0 + 30, GREEN)
        d.text("and enter:", tx, y0 + 48, MUTED)
        pin = p.pin or ""
        bw = len(pin) * 16 + 16
        d.rect(tx, y0 + 62, bw, 28, CARD, fill=True)
        d.rect(tx, y0 + 62, bw, 28, GREEN)
        d.text(pin, tx + 8, y0 + 68, WHITE, scale=2)
        d.text("expires " + _clock(p.remaining(self._t)), tx, y0 + 98, MUTED)
        d.text("Waiting for sign-in", 16, BOTTOM - 40, MUTED)
        d.text("(Spotify Premium for control)", 16, BOTTOM - 24, MUTED)

    def _draw_player(self, d):
        self._header(d, "SPOTIFY")
        np = self._np
        # Cover placeholder (the badge has no JPEG decoder for album art).
        cx, cy, cs = 12, TOP + 10, 84
        d.rect(cx, cy, cs, cs, CARD, fill=True)
        d.rect(cx, cy, cs, cs, GREEN if np and np["playing"] else LINE)
        for r, c in ((30, LINE), (20, LINE), (8, GREEN)):
            d.rect(cx + cs // 2 - r, cy + cs // 2 - r, 2 * r, 2 * r, c, fill=(r == 8))
        d.rect(cx + cs // 2 - 2, cy + cs // 2 - 2, 4, 4, BLACK, fill=True)

        tx = cx + cs + 10
        tw = SW - tx - 8
        if not self._online:
            title, artist, album = "Wi-Fi is not connected", "Connect in Settings", ""
        elif not self._np_known:
            title, artist, album = "Asking Spotify...", "", ""
        elif np is None:
            title, artist, album = "Nothing playing", "Start Spotify on a phone,", "computer or speaker"
        else:
            title, artist, album = np["title"], np["artist"], np["album"]
        d.text(_fit(title, tw), tx, cy + 4, WHITE)
        d.text(_fit(artist, tw), tx, cy + 22, GREEN)
        d.text(_fit(album, tw), tx, cy + 38, MUTED)
        if np and np["device"]:
            dev = _fit(np["device"], tw - 18)
            pw = len(dev) * 8 + 18
            d.rect(tx, cy + 60, pw, 16, CARD, fill=True)
            d.rect(tx, cy + 60, pw, 16, GREEN)
            d.rect(tx + 6, cy + 66, 4, 4, GREEN, fill=True)
            d.text(dev, tx + 14, cy + 64, WHITE)

        # Progress
        py = cy + cs + 14
        pos = self._progress()
        dur = np["dur"] if np else 0
        d.text(_clock(pos), 12, py, WHITE)
        tot = _clock(dur) if dur else "-:--"
        d.text(tot, SW - 12 - len(tot) * 8, py, WHITE)
        bx, bw = 12, SW - 24
        d.rect(bx, py + 14, bw, 4, LINE, fill=True)
        if dur:
            fw = int(bw * min(1, pos / dur))
            if fw:
                d.rect(bx, py + 14, fw, 4, GREEN, fill=True)

        # Controls and volume
        ky = py + 30
        self._icon_prev(d, 22, ky + 6)
        d.rect(50, ky, 36, 24, GREEN, fill=True)
        if np and np["playing"]:
            d.rect(61, ky + 6, 4, 12, BLACK, fill=True)
            d.rect(70, ky + 6, 4, 12, BLACK, fill=True)
        else:
            for i in range(6):
                d.rect(62 + i * 2, ky + 6 + i, 2, 12 - 2 * i, BLACK, fill=True)
        self._icon_next(d, 98, ky + 6)
        vol = self._vol
        if vol is None and np:
            vol = np["volume"]
        if vol is not None:
            d.text("VOL", 140, ky + 8, MUTED)
            vx, vw = 170, 100
            d.rect(vx, ky + 10, vw, 4, LINE, fill=True)
            fw = vw * int(vol) // 100
            if fw:
                d.rect(vx, ky + 10, fw, 4, GREEN, fill=True)
            d.text("%d" % int(vol), vx + vw + 8, ky + 8, WHITE)
        widgets.draw_hint(d, "A:play <>:skip ^v:vol B:lib C:unlink")

    def _icon_prev(self, d, x, y):
        d.rect(x, y, 2, 12, WHITE, fill=True)
        for i in range(6):
            d.rect(x + 3 + i * 2, y + 5 - i, 2, 2 + 2 * i, WHITE, fill=True)

    def _icon_next(self, d, x, y):
        for i in range(6):
            d.rect(x + i * 2, y + i, 2, 12 - 2 * i, WHITE, fill=True)
        d.rect(x + 13, y, 2, 12, WHITE, fill=True)

    def _draw_library(self, d):
        fr = self._lib[-1]
        self._header(d, _fit(fr["title"], 200, 2))
        rows = fr["rows"]
        kind = fr["kind"]
        if fr["loading"] and not rows:
            self._lines(d, ("Loading...",), GREEN)
        elif fr["error"] and not rows:
            self._lines(d, (_TOASTS.get(fr["error"], "Could not load"),
                            "B: back"), WARN)
        elif not rows:
            self._lines(d, ("Nothing here yet",), MUTED)
        y = TOP + 6
        end = min(len(rows), fr["top"] + ROWS)
        for i in range(fr["top"], end):
            row = rows[i]
            sel = i == fr["sel"]
            ry = y + (i - fr["top"]) * (ROW_H + 2)
            d.rect(6, ry, SW - 16, ROW_H, SEL if sel else CARD, fill=True)
            if sel:
                d.rect(6, ry, 3, ROW_H, GREEN, fill=True)
            if kind == "root":
                main, sub = row["title"], ""
                hit = self._lib_cache.get(row["kind"])
                if hit:
                    sub = "%d items" % len(hit[1])
            elif kind == "playlists":
                main = row["name"]
                sub = "%d tracks" % row["count"]
                if row["owner"]:
                    sub += "  " + row["owner"]
            else:
                main, sub = row["title"], row["artist"]
                dur = _clock(row["dur"])
                d.text(dur, SW - 16 - len(dur) * 8, ry + 6, MUTED)
            d.text(_fit(main, SW - 80), 16, ry + 6, WHITE if sel else MUTED)
            d.text(_fit(sub, SW - 40), 16, ry + 20, GREEN if sel else LINE)
        if len(rows) > ROWS:
            h = BOTTOM - TOP - 12
            th = max(10, h * ROWS // len(rows))
            ty = TOP + 6 + (h - th) * fr["top"] // max(1, len(rows) - ROWS)
            d.rect(SW - 6, TOP + 6, 2, h, LINE, fill=True)
            d.rect(SW - 6, ty, 2, th, GREEN, fill=True)
        if kind == "root":
            hint = "A:open  B:player  C:unlink"
        elif kind == "playlists":
            hint = "A:open  >:play all  B:back"
        else:
            hint = "A:play  B:back  C:unlink"
        widgets.draw_hint(d, hint)

    def _draw_confirm(self, d):
        w, h = 240, 80
        x, y = (SW - w) // 2, (SH - h) // 2
        d.rect(x, y, w, h, CARD, fill=True)
        d.rect(x, y, w, h, WARN)
        d.text("Unlink Spotify?", x + (w - 15 * 8) // 2, y + 14, WHITE)
        d.text("Forgets this sign-in", x + (w - 20 * 8) // 2, y + 32, MUTED)
        d.text("A:unlink   B:cancel", x + (w - 19 * 8) // 2, y + 56, GREEN)

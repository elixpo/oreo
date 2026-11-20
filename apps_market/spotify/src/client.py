"""Spotify Web API calls and response parsing for the badge.

Client methods do network I/O and run only on the app's worker. They get
the transport as `send(method, url, headers, body) -> (status, headers,
body_bytes)` (net.request on the badge, a fake in tests) and a wall-clock
`now()` for token expiry. The parse_* functions turn Spotify JSON into
the small dicts the screen draws, keeping only what it shows so a
library page does not sit in RAM as a full API object.

Endpoints add market=from_token, which makes Spotify drop the long
available_markets lists from track objects (most of a response's size).
"""

try:
    import json
except ImportError:  # pragma: no cover
    import ujson as json

from . import auth

API = "https://api.spotify.com/v1"
TITLE_MAX = 40          # characters kept per title / artist / name
LIST_LIMIT = 20         # items per library list

# Control results
OK = "ok"
NO_DEVICE = "no_device"     # nothing to play on: open Spotify somewhere
PREMIUM = "premium"         # playback control needs Spotify Premium
LIMITED = "limited"         # 429, wait a little
OFFLINE = "offline"
UNLINKED = "unlinked"       # refresh token revoked: link again
FAILED = "failed"

# Latin letters with marks -> plain ASCII, for the badge's ASCII font.
_FOLD = {}
for _plain, _marked in (
        ("A", "ÀÁÂÃÄÅ"),
        ("a", "àáâãäå"),
        ("C", "Ç"), ("c", "ç"),
        ("E", "ÈÉÊË"), ("e", "èéêë"),
        ("I", "ÌÍÎÏ"), ("i", "ìíîï"),
        ("N", "Ñ"), ("n", "ñ"),
        ("O", "ÒÓÔÕÖØ"),
        ("o", "òóôõöø"),
        ("U", "ÙÚÛÜ"), ("u", "ùúûü"),
        ("Y", "Ý"), ("y", "ýÿ"),
        ("ss", "ß"),
        ("'", "‘’"), ('"', "“”"), ("-", "–—"),
        ("...", "…")):
    for _ch in _marked:
        _FOLD[_ch] = _plain


def ascii_text(s, limit=TITLE_MAX):
    """`s` folded to printable ASCII (accents dropped, other characters
    become '?', runs of them collapse), cut to `limit` characters."""
    if not s:
        return ""
    out = []
    last_q = False
    for ch in str(s):
        o = ord(ch)
        if 32 <= o < 127:
            out.append(ch)
            last_q = False
        elif ch in _FOLD:
            out.append(_FOLD[ch])
            last_q = False
        elif ch in "\t\n\r":
            out.append(" ")
            last_q = False
        elif not last_q:
            out.append("?")
            last_q = True
    text = "".join(out).strip()
    if len(text) > limit:
        text = text[:limit - 2].rstrip() + ".."
    return text


def _artists(obj):
    names = []
    for a in obj.get("artists") or ():
        if isinstance(a, dict) and a.get("name"):
            names.append(a["name"])
    return ", ".join(names)


def _track(obj, context=None):
    """One list row from a track object, or None."""
    if not isinstance(obj, dict) or not obj.get("name"):
        return None
    uri = obj.get("uri") or ""
    if obj.get("is_local") or not uri.startswith("spotify:"):
        return None
    row = {
        "title": ascii_text(obj.get("name")),
        "artist": ascii_text(_artists(obj)) or "Unknown artist",
        "dur": int((obj.get("duration_ms") or 0) // 1000),
        "uri": uri,
    }
    if context:
        row["ctx"] = context
    return row


def parse_tracks(data, context=None, limit=LIST_LIMIT):
    """Rows from a paging object of tracks: /me/tracks, /me/top/tracks,
    /me/player/recently-played and playlist items. Items may be bare
    tracks or wrap them under "track" (or "item", the newer name for
    playlist entries). Duplicates (by URI) are dropped."""
    rows = []
    seen = set()
    if not isinstance(data, dict):
        return rows
    for entry in data.get("items") or ():
        if not isinstance(entry, dict):
            continue
        obj = entry
        if "track" in entry and isinstance(entry.get("track"), dict):
            obj = entry["track"]
        elif "item" in entry and isinstance(entry.get("item"), dict):
            obj = entry["item"]
        row = _track(obj, context)
        if row is None or row["uri"] in seen:
            continue
        seen.add(row["uri"])
        rows.append(row)
        if len(rows) >= limit:
            break
    return rows


def parse_playlists(data, limit=LIST_LIMIT):
    rows = []
    if not isinstance(data, dict):
        return rows
    for pl in data.get("items") or ():
        if not isinstance(pl, dict) or not pl.get("id") or not pl.get("name"):
            continue
        count = 0
        for key in ("items", "tracks"):
            info = pl.get(key)
            if isinstance(info, dict) and "total" in info:
                count = info.get("total") or 0
                break
        owner = pl.get("owner") or {}
        rows.append({
            "name": ascii_text(pl.get("name")),
            "id": pl["id"],
            "uri": pl.get("uri") or "spotify:playlist:" + pl["id"],
            "count": int(count),
            "owner": ascii_text(owner.get("display_name") if isinstance(owner, dict) else "", 20),
        })
        if len(rows) >= limit:
            break
    return rows


def parse_devices(data):
    out = []
    if not isinstance(data, dict):
        return out
    for d in data.get("devices") or ():
        if isinstance(d, dict) and d.get("id") and not d.get("is_restricted"):
            out.append({"id": d["id"], "name": ascii_text(d.get("name"), 24),
                        "active": bool(d.get("is_active")),
                        "volume": d.get("volume_percent")})
    return out


def parse_player(data):
    """Now-playing state from /me/player, or None when nothing plays.
    Handles tracks and podcast episodes; an item Spotify hides (an ad,
    private session) shows as an untitled entry."""
    if not isinstance(data, dict):
        return None
    dev = data.get("device") or {}
    item = data.get("item")
    st = {
        "playing": bool(data.get("is_playing")),
        "progress": int((data.get("progress_ms") or 0) // 1000),
        "device": ascii_text(dev.get("name"), 24) if isinstance(dev, dict) else "",
        "device_id": dev.get("id") if isinstance(dev, dict) else None,
        "volume": dev.get("volume_percent") if isinstance(dev, dict) else None,
        "shuffle": bool(data.get("shuffle_state")),
        "repeat": data.get("repeat_state") or "off",
        "title": "",
        "artist": "",
        "album": "",
        "dur": 0,
        "uri": "",
    }
    if isinstance(item, dict):
        st["title"] = ascii_text(item.get("name"))
        st["dur"] = int((item.get("duration_ms") or 0) // 1000)
        st["uri"] = item.get("uri") or ""
        if item.get("type") == "episode":
            show = item.get("show") or {}
            st["artist"] = ascii_text(show.get("name") if isinstance(show, dict) else "")
            st["album"] = "Podcast"
        else:
            st["artist"] = ascii_text(_artists(item))
            album = item.get("album") or {}
            st["album"] = ascii_text(album.get("name") if isinstance(album, dict) else "")
    elif data.get("currently_playing_type") == "ad":
        st["title"] = "Advertisement"
    if not st["title"]:
        st["title"] = "Playing" if st["playing"] else "Paused"
    if st["dur"] and st["progress"] > st["dur"]:
        st["progress"] = st["dur"]
    return st


def _json(body):
    if not body:
        return None
    try:
        if isinstance(body, (bytes, bytearray)):
            body = body.decode("utf-8")
        return json.loads(body)
    except Exception:
        return None


def _error_reason(data):
    err = (data or {}).get("error") if isinstance(data, dict) else None
    if isinstance(err, dict):
        return err.get("reason") or err.get("message") or ""
    return ""


class Client:
    """Spotify Web API on the worker. `tokens` is the app's saved dict;
    tokens are refreshed through `relay` (see auth.refresh_request).
    After a refresh `changed` is True and the app saves `tokens` on the
    UI thread. `unlinked` is set when the refresh token was revoked."""

    def __init__(self, tokens, send, now, relay=None):
        self.tokens = dict(tokens or {})
        self.send = send
        self.now = now
        self.relay = relay
        self.changed = False
        self.unlinked = False
        self.retry_after = 0

    def refresh(self):
        if not self.tokens.get("refresh_token"):
            self.unlinked = True
            return False
        req = auth.refresh_request(self.tokens, self.relay)
        if req is None:
            return False
        url, headers, body = req
        status, _h, raw = self.send("POST", url, headers, body)
        data = _json(raw)
        if status == 200:
            new = auth.apply_token_response(self.tokens, data, self.now())
            if new is not None:
                self.tokens = new
                self.changed = True
                return True
            return False
        if auth.refresh_revoked(status, data):
            self.unlinked = True
        return False

    def call(self, method, path, body=None):
        """(status, json_or_None, headers). Refreshes the token first when
        it is about to expire, and once more on a 401."""
        if self.unlinked:
            return 401, None, {}
        if auth.needs_refresh(self.tokens, self.now()) and not self.refresh():
            return (401 if self.unlinked else 0), None, {}
        status = 0
        data = None
        hdrs = {}
        for attempt in (0, 1):
            headers = {"Authorization": "Bearer " + self.tokens["access_token"]}
            payload = None
            if body is not None:
                headers["Content-Type"] = "application/json"
                payload = json.dumps(body)
            status, hdrs, raw = self.send(method, API + path, headers, payload)
            data = _json(raw)
            if status == 401 and attempt == 0 and self.refresh():
                continue
            break
        if status == 429:
            try:
                self.retry_after = int(hdrs.get("retry-after") or 5)
            except (TypeError, ValueError):
                self.retry_after = 5
        return status, data, hdrs

    # ── reads ───────────────────────────────────────────────────────

    def playback(self):
        """(result, state): result OK with state (None = nothing playing),
        or an error code with None."""
        status, data, _ = self.call(
            "GET", "/me/player?market=from_token&additional_types=track,episode")
        if status == 204 or (status == 200 and not data):
            return OK, None
        if status == 200:
            return OK, parse_player(data)
        return self._fail(status, data), None

    def devices(self):
        status, data, _ = self.call("GET", "/me/player/devices")
        return parse_devices(data) if status == 200 else []

    def library(self, kind, ref=None):
        """(result, rows) for a library list: "liked", "top", "recent",
        "playlists" or "playlist" (ref = playlist dict)."""
        n = LIST_LIMIT
        ctx = None
        if kind == "liked":
            path = "/me/tracks?limit=%d&market=from_token" % n
        elif kind == "top":
            path = "/me/top/tracks?limit=%d&time_range=short_term" % n
        elif kind == "recent":
            path = "/me/player/recently-played?limit=%d" % n
        elif kind == "playlists":
            path = "/me/playlists?limit=%d" % n
        elif kind == "playlist" and ref:
            ctx = ref.get("uri")
            path = "/playlists/%s/tracks?limit=%d&market=from_token" % (ref["id"], n)
        else:
            return FAILED, []
        status, data, _ = self.call("GET", path)
        if status != 200:
            return self._fail(status, data), []
        if kind == "playlists":
            return OK, parse_playlists(data)
        return OK, parse_tracks(data, ctx)

    # ── controls ────────────────────────────────────────────────────

    def _fail(self, status, data):
        if self.unlinked:
            return UNLINKED
        if status == 0:
            return OFFLINE
        if status == 429:
            return LIMITED
        if status == 403 or _error_reason(data) == "PREMIUM_REQUIRED":
            return PREMIUM
        if status == 404 or _error_reason(data) == "NO_ACTIVE_DEVICE":
            return NO_DEVICE
        return FAILED

    def _control(self, method, path, body=None):
        status, data, _ = self.call(method, path, body)
        if 200 <= status < 300:
            return OK
        return self._fail(status, data)

    def _wake_device(self):
        """Transfer playback to the first available device (Spotify keeps
        a phone or desktop app listed for a while after it goes idle).
        Returns its id or None."""
        devs = self.devices()
        if not devs:
            return None
        pick = devs[0]
        for d in devs:
            if d["active"]:
                pick = d
                break
        r = self._control("PUT", "/me/player", {"device_ids": [pick["id"]], "play": False})
        return pick["id"] if r == OK else None

    def control(self, action, arg=None):
        """Run one playback command. action: play, pause, next, prev,
        volume (arg 0-100), play_track (arg row dict), play_context
        (arg context URI). Returns OK or an error code."""
        if action == "pause":
            return self._control("PUT", "/me/player/pause")
        if action == "next":
            return self._control("POST", "/me/player/next")
        if action == "prev":
            return self._control("POST", "/me/player/previous")
        if action == "volume":
            pct = max(0, min(100, int(arg or 0)))
            return self._control("PUT", "/me/player/volume?volume_percent=%d" % pct)
        body = None
        if action == "play_track" and arg:
            if arg.get("ctx"):
                body = {"context_uri": arg["ctx"], "offset": {"uri": arg["uri"]}}
            else:
                body = {"uris": [arg["uri"]]}
        elif action == "play_context" and arg:
            body = {"context_uri": arg}
        elif action != "play":
            return FAILED
        r = self._control("PUT", "/me/player/play", body)
        if r == NO_DEVICE:
            dev = self._wake_device()
            if dev:
                r = self._control("PUT", "/me/player/play?device_id=" + auth.quote(dev), body)
        return r

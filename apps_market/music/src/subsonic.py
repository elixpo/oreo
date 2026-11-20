"""A Subsonic API client (Navidrome, Jellyfin's Subsonic plugin, Airsonic,
Gonic...), for the owner's own music server.

Token authentication: each request carries u (user), s (a random salt) and
t = md5(password + salt) in hex, never the password. The badge keeps only
the server URL, the user, one salt and its token (oreoOS.state), not the
password. Streams ask the server to transcode to MP3 at 128 kb/s at most
(stream.view?format=mp3&maxBitRate=128), so any library format plays.
"""

try:
    import json
except ImportError:  # pragma: no cover
    import ujson as json

API_VERSION = "1.16.1"
CLIENT = "FaleraOS"
MAX_BITRATE = 128


def _md5_hex(data):
    import hashlib
    h = hashlib.md5(data)
    d = h.digest()
    return "".join("%02x" % b for b in d)


def new_salt(n=12):
    """A random hex salt."""
    try:
        import os
        raw = os.urandom(n // 2 + 1)
    except Exception:
        import random
        raw = bytes(random.getrandbits(8) for _ in range(n // 2 + 1))
    return "".join("%02x" % b for b in raw)[:n]


def token(password, salt):
    """t for token auth: md5(password + salt), lower-case hex."""
    return _md5_hex((password + salt).encode("utf-8"))


def credentials(url, user, password, salt=None):
    """What the badge stores: {url, user, salt, token} (no password)."""
    salt = salt or new_salt()
    url = url.strip().rstrip("/")
    if url and "://" not in url:
        url = "https://" + url
    return {"url": url, "user": user.strip(), "salt": salt, "token": token(password, salt)}


def _q(s):
    out = []
    for ch in str(s):
        if ("a" <= ch <= "z") or ("A" <= ch <= "Z") or ("0" <= ch <= "9") or ch in "-_.~":
            out.append(ch)
        else:
            for b in ch.encode("utf-8"):
                out.append("%%%02X" % b)
    return "".join(out)


def build_url(cred, method, **params):
    """Full URL of a Subsonic REST call with token auth."""
    q = [("u", cred["user"]), ("t", cred["token"]), ("s", cred["salt"]),
         ("v", API_VERSION), ("c", CLIENT), ("f", "json")]
    for k in sorted(params):
        q.append((k, str(params[k])))
    return "%s/rest/%s.view?%s" % (cred["url"], method,
                                   "&".join("%s=%s" % (k, _q(v)) for k, v in q))


def ping_url(cred):
    return build_url(cred, "ping")


def albums_url(cred, kind="newest", size=40):
    return build_url(cred, "getAlbumList2", type=kind, size=size)


def album_url(cred, album_id):
    return build_url(cred, "getAlbum", id=album_id)


def search_url(cred, text):
    return build_url(cred, "search3", query=text, songCount=40, albumCount=20, artistCount=0)


def random_url(cred, size=50):
    return build_url(cred, "getRandomSongs", size=size)


def stream_url(cred, song_id):
    return build_url(cred, "stream", id=song_id, format="mp3", maxBitRate=MAX_BITRATE)


class SubsonicError(Exception):
    pass


def _body(data):
    if isinstance(data, (bytes, bytearray)):
        data = bytes(data).decode("utf-8", "ignore")
    try:
        raw = json.loads(data)
    except Exception:
        raise SubsonicError("not a Subsonic server")
    r = raw.get("subsonic-response") if isinstance(raw, dict) else None
    if not isinstance(r, dict):
        raise SubsonicError("not a Subsonic server")
    if r.get("status") != "ok":
        err = r.get("error") or {}
        code = err.get("code")
        if code in (40, 41):
            raise SubsonicError("wrong user or password")
        raise SubsonicError(err.get("message") or "server error")
    return r


def parse_ping(data):
    _body(data)
    return True


def _song(s, cred):
    return {
        "id": str(s.get("id", "")),
        "title": (s.get("title") or "Untitled").strip(),
        "artist": (s.get("artist") or "").strip(),
        "album": (s.get("album") or "").strip(),
        "track": s.get("track") or 0,
        "duration": int(s.get("duration") or 0),
        "url": stream_url(cred, s.get("id", "")),
    }


def parse_albums(data):
    r = _body(data)
    lst = (r.get("albumList2") or {}).get("album") or []
    return [{"id": str(a.get("id", "")), "name": (a.get("name") or "Album").strip(),
             "artist": (a.get("artist") or "").strip()} for a in lst if isinstance(a, dict)]


def parse_album(data, cred):
    r = _body(data)
    songs = (r.get("album") or {}).get("song") or []
    out = [_song(s, cred) for s in songs if isinstance(s, dict) and not s.get("isVideo")]
    return sorted(out, key=lambda s: (s.get("track") or 999))


def parse_songs(data, cred, key="searchResult3"):
    r = _body(data)
    node = r.get(key) or {}
    songs = node.get("song") or []
    return [_song(s, cred) for s in songs if isinstance(s, dict) and not s.get("isVideo")]


def parse_random(data, cred):
    return parse_songs(data, cred, "randomSongs")


def fetch(url, get=None):
    """Run on a worker: the body of a Subsonic call (http or https)."""
    if get is None:
        get = _get
    body = get(url)
    if body is None:
        raise OSError("server not answering")
    return body


def _get(url):
    if url.startswith("https://"):
        from oreoOS import _http
        return _http.get_url(url, accept="application/json", timeout_s=12)
    # plain http (a server without TLS): the player's HTTP client
    try:
        from oreoOS import player
    except ImportError:
        raise OSError("update FaleraOS")
    out = bytearray()

    def sink(mv):
        out.extend(mv)
        return len(out) < 512 * 1024
    player.get_stream(url, sink)
    return bytes(out)

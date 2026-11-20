"""Jamendo API v3 (developer.jamendo.com/v3.0): Creative Commons
music. Tracks are asked for as MP3 streams (audioformat=mp32, about 96 to
128 kb/s); each comes with its artist, album and CC licence.

URL building and parsing are pure (tested on the host); fetch() runs on a
worker.
"""

try:
    import json
except ImportError:  # pragma: no cover
    import ujson as json

BASE = "https://api.jamendo.com/v3.0"
USER_AGENT = "FaleraOS-Jamendo/1.0"
LIMIT = 30

GENRES = ("pop", "rock", "electronic", "hiphop", "jazz", "classical", "ambient",
          "lounge", "chillout", "acoustic", "folk", "world", "metal", "reggae",
          "soundtrack", "piano")


def _q(s):
    out = []
    for ch in str(s):
        if ("a" <= ch <= "z") or ("A" <= ch <= "Z") or ("0" <= ch <= "9") or ch in "-_.~":
            out.append(ch)
        else:
            for b in ch.encode("utf-8"):
                out.append("%%%02X" % b)
    return "".join(out)


def _url(path, client_id, **params):
    q = [("client_id", client_id), ("format", "json"), ("limit", str(LIMIT))]
    for k in sorted(params):
        q.append((k, str(params[k])))
    return BASE + path + "?" + "&".join("%s=%s" % (k, _q(v)) for k, v in q)


def tracks_featured(cid):
    return _url("/tracks/", cid, audioformat="mp32", featured="true")


def tracks_popular(cid):
    return _url("/tracks/", cid, audioformat="mp32", boost="popularity_week")


def tracks_tag(cid, tag):
    return _url("/tracks/", cid, audioformat="mp32", tags=tag, boost="popularity_month")


def tracks_search(cid, text):
    return _url("/tracks/", cid, audioformat="mp32", search=text)


def tracks_album(cid, album_id):
    return _url("/tracks/", cid, audioformat="mp32", album_id=album_id)


def albums_popular(cid):
    return _url("/albums/", cid, order="popularity_week")


def albums_search(cid, text):
    return _url("/albums/", cid, namesearch=text)


def licence_name(url):
    """'http://creativecommons.org/licenses/by-nc-sa/3.0/' -> 'CC BY-NC-SA 3.0'."""
    if not url:
        return "CC licence"
    parts = [p for p in url.split("/") if p]
    if "licenses" in parts:
        i = parts.index("licenses")
        kind = parts[i + 1] if len(parts) > i + 1 else ""
        ver = parts[i + 2] if len(parts) > i + 2 else ""
        return ("CC " + kind.upper() + (" " + ver if ver else "")).strip()
    if "publicdomain" in parts:
        return "CC0 / public domain"
    return "CC licence"


class ApiError(Exception):
    pass


def _load(data):
    if isinstance(data, (bytes, bytearray)):
        data = bytes(data).decode("utf-8", "ignore")
    try:
        raw = json.loads(data)
    except Exception:
        raise ApiError("bad answer from Jamendo")
    h = raw.get("headers", {}) if isinstance(raw, dict) else {}
    if h.get("status") != "success":
        msg = h.get("error_message") or "Jamendo refused the request"
        if h.get("code") == 5:
            msg = "client id not accepted"
        raise ApiError(msg)
    return raw.get("results") or []


def parse_tracks(data):
    """[{id, name, artist, album, album_id, duration, url, licence, pos}]
    with an MP3 stream; raises ApiError when Jamendo reports one."""
    out = []
    for r in _load(data):
        if not isinstance(r, dict):
            continue
        url = r.get("audio") or ""
        if not url.startswith("http"):
            continue
        try:
            dur = int(r.get("duration") or 0)
        except (TypeError, ValueError):
            dur = 0
        try:
            pos = int(r.get("position") or 0)
        except (TypeError, ValueError):
            pos = 0
        out.append({
            "id": str(r.get("id", "")),
            "name": (r.get("name") or "Untitled").strip(),
            "artist": (r.get("artist_name") or "").strip(),
            "album": (r.get("album_name") or "").strip(),
            "album_id": str(r.get("album_id") or ""),
            "duration": dur,
            "url": url,
            "licence": licence_name(r.get("license_ccurl")),
            "pos": pos,
        })
    return out


def parse_albums(data):
    """[{id, name, artist}]"""
    out = []
    for r in _load(data):
        if isinstance(r, dict) and r.get("id"):
            out.append({"id": str(r["id"]), "name": (r.get("name") or "Album").strip(),
                        "artist": (r.get("artist_name") or "").strip()})
    return out


def album_order(tracks):
    """An album's tracks in their album order."""
    return sorted(tracks, key=lambda t: (t.get("pos") or 999, t["name"]))


def fetch(url, get=None):
    """Run on a worker: the body of url, or OSError."""
    if get is None:
        from oreoOS import _http

        def get(u):
            return _http.get_url(u, accept="application/json", timeout_s=12,
                                 user_agent=USER_AGENT)
    body = get(url)
    if body is None:
        raise OSError("Jamendo is not answering")
    return body

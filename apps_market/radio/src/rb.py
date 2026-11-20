"""Radio Browser (https://www.radio-browser.info): the community-run, open
directory of internet radio stations. No key; the API asks clients to send
a descriptive User-Agent and to report a click when a station is played.

Only MP3 stations are asked for (the badge decodes MP3 only), working ones
(hidebroken), most clicked first, and lower bit rates are preferred: they
need less Wi-Fi and fit the speaker.

URL building and parsing are pure functions (tested on the host); fetch()
runs on a worker thread.
"""

try:
    import json
except ImportError:  # pragma: no cover
    import ujson as json

USER_AGENT = "FaleraOS-Radio/1.0"
SERVERS = ("de1.api.radio-browser.info", "de2.api.radio-browser.info")
LIMIT = 40
MAX_BITRATE = 128


def _q(s):
    """Percent-encode a query value."""
    out = []
    for ch in str(s):
        o = ord(ch)
        if ("a" <= ch <= "z") or ("A" <= ch <= "Z") or ("0" <= ch <= "9") or ch in "-_.~":
            out.append(ch)
        else:
            for b in ch.encode("utf-8"):
                out.append("%%%02X" % b)
    return "".join(out)


def _stations(**params):
    q = {
        "codec": "MP3",
        "hidebroken": "true",
        "order": "clickcount",
        "reverse": "true",
        "limit": str(LIMIT),
        "bitrateMax": str(MAX_BITRATE),
    }
    q.update(params)
    keys = sorted(q)
    return "/json/stations/search?" + "&".join("%s=%s" % (k, _q(q[k])) for k in keys)


def path_top():
    return _stations()


def path_country(code):
    return _stations(countrycode=code)


def path_tag(tag):
    return _stations(tag=tag, tagExact="true")


def path_search(name):
    return _stations(name=name)


def path_countries():
    return "/json/countries?order=stationcount&reverse=true&hidebroken=true&limit=60"


def path_tags():
    return "/json/tags?order=stationcount&reverse=true&hidebroken=true&limit=60"


def path_click(uuid):
    return "/json/url/" + _q(uuid)


def _rank(st):
    br = st["bitrate"]
    if 0 < br <= 96:
        return 0
    if 0 < br <= 128:
        return 1
    if br == 0:
        return 2            # unknown
    return 3


def parse_stations(data):
    """Station dicts {id, name, url, bitrate, country, cc, tags, clicks}
    from a /json/stations response (bytes or str). MP3 only, HLS and
    entries without a URL dropped, low bit rates first, then by clicks."""
    if isinstance(data, (bytes, bytearray)):
        data = bytes(data).decode("utf-8", "ignore")
    try:
        raw = json.loads(data)
    except Exception:
        return []
    out = []
    seen = set()
    for s in raw if isinstance(raw, list) else ():
        if not isinstance(s, dict):
            continue
        if (s.get("codec") or "").upper() != "MP3" or s.get("hls"):
            continue
        url = s.get("url_resolved") or s.get("url") or ""
        if not (url.startswith("http://") or url.startswith("https://")):
            continue
        sid = s.get("stationuuid") or url
        if sid in seen:
            continue
        seen.add(sid)
        try:
            br = int(s.get("bitrate") or 0)
        except (TypeError, ValueError):
            br = 0
        tags = (s.get("tags") or "").split(",")
        out.append({
            "id": sid,
            "name": (s.get("name") or "").strip() or "Unnamed station",
            "url": url,
            "bitrate": br,
            "country": s.get("country") or "",
            "cc": (s.get("countrycode") or "").upper(),
            "tags": ", ".join(t.strip() for t in tags[:3] if t.strip()),
            "clicks": int(s.get("clickcount") or 0),
        })
    # Stable: keeps the server's popularity order inside each bit-rate group.
    order = sorted(range(len(out)), key=lambda i: (_rank(out[i]), i))
    return [out[i] for i in order]


def parse_countries(data):
    """[(code, name, count)] with at least one station, biggest first."""
    if isinstance(data, (bytes, bytearray)):
        data = bytes(data).decode("utf-8", "ignore")
    try:
        raw = json.loads(data)
    except Exception:
        return []
    out = []
    for c in raw if isinstance(raw, list) else ():
        if not isinstance(c, dict):
            continue
        code = (c.get("iso_3166_1") or "").upper()
        n = int(c.get("stationcount") or 0)
        if len(code) == 2 and n > 0:
            out.append((code, c.get("name") or code, n))
    return out


def parse_tags(data):
    """[(tag, count)] for non-empty tags."""
    if isinstance(data, (bytes, bytearray)):
        data = bytes(data).decode("utf-8", "ignore")
    try:
        raw = json.loads(data)
    except Exception:
        return []
    out = []
    for t in raw if isinstance(raw, list) else ():
        if isinstance(t, dict) and (t.get("name") or "").strip():
            out.append((t["name"].strip(), int(t.get("stationcount") or 0)))
    return out


def fetch(path, get=None, servers=SERVERS):
    """GET path from the first Radio Browser server that answers (on a
    worker). Returns the body bytes; raises OSError when none answers."""
    if get is None:
        from oreoOS import _http

        def get(url):
            return _http.get_url(url, accept="application/json", timeout_s=10,
                                 user_agent=USER_AGENT)
    for host in servers:
        body = get("https://" + host + path)
        if body is not None:
            return body
    raise OSError("Radio Browser is not answering")


def station_to_fav(st):
    """The part of a station worth saving in /state (keep it small)."""
    return {"id": st["id"], "name": st["name"][:48], "url": st["url"],
            "bitrate": st.get("bitrate", 0), "cc": st.get("cc", "")}

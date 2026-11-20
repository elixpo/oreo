"""Podcast search through the iTunes Search API (no key):
https://itunes.apple.com/search?media=podcast&entity=podcast&term=...

URL building and parsing are pure; fetching runs on a worker.
"""

try:
    import json
except ImportError:  # pragma: no cover
    import ujson as json

HOST = "https://itunes.apple.com"
LIMIT = 25
USER_AGENT = "FaleraOS-Podcasts/1.0"


def _q(s):
    out = []
    for ch in str(s).strip():
        if ("a" <= ch <= "z") or ("A" <= ch <= "Z") or ("0" <= ch <= "9") or ch in "-_.~":
            out.append(ch)
        elif ch == " ":
            out.append("+")
        else:
            for b in ch.encode("utf-8"):
                out.append("%%%02X" % b)
    return "".join(out)


def search_url(term):
    return "%s/search?media=podcast&entity=podcast&limit=%d&term=%s" % (HOST, LIMIT, _q(term))


def parse_results(data):
    """[{id, name, author, feed}] for results that have an RSS feed."""
    if isinstance(data, (bytes, bytearray)):
        data = bytes(data).decode("utf-8", "ignore")
    try:
        raw = json.loads(data)
    except Exception:
        return []
    out = []
    for r in raw.get("results", ()) if isinstance(raw, dict) else ():
        if not isinstance(r, dict):
            continue
        feed = r.get("feedUrl") or ""
        if not (feed.startswith("http://") or feed.startswith("https://")):
            continue
        out.append({
            "id": r.get("collectionId") or feed,
            "name": (r.get("collectionName") or r.get("trackName") or "Podcast").strip(),
            "author": (r.get("artistName") or "").strip(),
            "feed": feed,
        })
    return out


def search(term, get=None):
    """Run on a worker: the shows matching term."""
    if get is None:
        from oreoOS import _http

        def get(url):
            return _http.get_url(url, accept="application/json", timeout_s=12,
                                 user_agent=USER_AGENT)
    body = get(search_url(term))
    if body is None:
        raise OSError("iTunes search is not answering")
    return parse_results(body)

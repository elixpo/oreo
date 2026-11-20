"""Host tests for the Spotify app (apps_market/spotify).

Pure modules (qr, auth, client, net) are loaded by path as a package; the
app itself runs on stub oreoOS modules, the real oreoOS/state.py in a temp
dir, a synchronous Refresh and a fake HTTPS transport standing in for
Spotify and the falera.elixpo relay.

    python3 -m unittest tests.test_spotify_app -v
"""

import importlib
import importlib.util
import json
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "apps_market" / "spotify" / "src"
PKG = "spotify_src_under_test"


def _load_pkg():
    if PKG not in sys.modules:
        pkg = types.ModuleType(PKG)
        pkg.__path__ = [str(SRC)]
        sys.modules[PKG] = pkg
    return (importlib.import_module(PKG + ".qr"), importlib.import_module(PKG + ".auth"),
            importlib.import_module(PKG + ".client"), importlib.import_module(PKG + ".net"))


qr, auth, client, net = _load_pkg()


# ── QR ──────────────────────────────────────────────────────────────────

def _read_codewords(size, rows, n_codewords):
    """Undo the mask and read codewords in placement order (a small
    decoder, so placement and masking are checked end to end)."""
    version = (size - 17) // 4
    grid = qr._Grid(version)
    fmt = 0
    for i in range(6):
        fmt |= rows[i][8] << i
    fmt |= rows[7][8] << 6
    fmt |= rows[8][8] << 7
    fmt |= rows[8][7] << 8
    for i in range(9, 15):
        fmt |= rows[8][14 - i] << i
    mask = [m for m in range(8) if qr._format_bits(m) == fmt]
    assert len(mask) == 1, "format bits do not decode"
    mask = mask[0]
    bits = []
    right = size - 1
    while right >= 1:
        if right == 6:
            right = 5
        upward = ((right + 1) & 2) == 0
        for vert in range(size):
            y = size - 1 - vert if upward else vert
            for j in range(2):
                x = right - j
                if not grid.fn[y][x]:
                    bits.append(rows[y][x] ^ (1 if qr._mask_bit(mask, x, y) else 0))
        right -= 2
    out = bytearray()
    for k in range(n_codewords):
        v = 0
        for b in bits[k * 8:(k + 1) * 8]:
            v = (v << 1) | b
        out.append(v)
    return mask, bytes(out)


class QRTest(unittest.TestCase):
    URL = "https://falera.elixpo.com/spotify/?pin=ABC234"

    def test_version_choice(self):
        self.assertEqual(qr.pick_version(17), 1)
        self.assertEqual(qr.pick_version(18), 2)
        self.assertEqual(qr.pick_version(len(self.URL)), 3)
        self.assertEqual(qr.pick_version(134), 6)
        self.assertIsNone(qr.pick_version(135))
        with self.assertRaises(ValueError):
            qr.encode("x" * 200)

    def test_reed_solomon_reference(self):
        # Checked against an independent GF(256) long division and segno.
        cw = qr._codewords(b"x", 1)
        self.assertEqual(list(cw[:4]), [0x40, 0x17, 0x80, 0xEC])
        self.assertEqual(list(cw[-7:]), [39, 55, 68, 36, 118, 171, 122])

    def test_round_trip_every_mask_and_version(self):
        for text in ("x", self.URL, "y" * 60, "z" * 100, "w" * 134):
            data = text.encode()
            v = qr.pick_version(len(data))
            want = qr._codewords(data, v)
            for m in range(8):
                size, rows = qr.encode(text, mask=m)
                self.assertEqual(size, 17 + 4 * v)
                got_mask, got = _read_codewords(size, rows, len(want))
                self.assertEqual(got_mask, m)
                self.assertEqual(got, bytes(want), (text[:10], m))

    def test_finders_timing_and_dark_module(self):
        size, rows = qr.encode(self.URL)
        finder = ("1111111", "1000001", "1011101", "1011101", "1011101", "1000001", "1111111")
        for (x0, y0) in ((0, 0), (size - 7, 0), (0, size - 7)):
            for dy in range(7):
                self.assertEqual("".join(str(rows[y0 + dy][x0 + dx]) for dx in range(7)),
                                 finder[dy])
        for i in range(8, size - 8):
            self.assertEqual(rows[6][i], 1 - i % 2)
            self.assertEqual(rows[i][6], 1 - i % 2)
        self.assertEqual(rows[size - 8][8], 1)

    def test_mono_mask(self):
        size, rows = qr.encode(self.URL)
        mask, side = qr.mono_mask(size, rows, scale=3, quiet=2)
        self.assertEqual(side, (size + 4) * 3)
        stride = (side + 7) // 8
        self.assertEqual(len(mask), stride * side)

        def px(x, y):
            return bool(mask[y * stride + (x >> 3)] & (0x80 >> (x & 7)))
        self.assertFalse(px(0, 0))              # quiet zone
        self.assertTrue(px(6, 6))               # top-left finder corner
        self.assertTrue(px(8, 8))
        self.assertFalse(px(6 + 3, 6 + 3))      # finder's light ring


# ── auth ────────────────────────────────────────────────────────────────

class AuthTest(unittest.TestCase):
    def test_relay_base(self):
        self.assertEqual(auth.relay_base({}), "https://falera.elixpo.com")
        self.assertEqual(auth.relay_base({"relay": "https://my.site/"}), "https://my.site")
        self.assertIsNone(auth.relay_base({"relay": "http://lan.local"}))
        self.assertIsNone(auth.relay_base({"relay": 5}))

    def test_refresh_timing(self):
        tok = {"access_token": "a", "expires_at": 10000}
        self.assertFalse(auth.needs_refresh(tok, 9000))
        self.assertTrue(auth.needs_refresh(tok, 10000 - auth.REFRESH_MARGIN_S))
        self.assertTrue(auth.needs_refresh(tok, 11000))
        self.assertTrue(auth.needs_refresh({"expires_at": 99999}, 0))
        self.assertTrue(auth.needs_refresh({"access_token": "a", "expires_at": "x"}, 0))

    def test_token_response(self):
        old = {"access_token": "a", "refresh_token": "r1", "client_id": "c", "relay": "https://x.y"}
        new = auth.apply_token_response(old, {"access_token": "b", "expires_in": 3600}, 1000)
        self.assertEqual(new["access_token"], "b")
        self.assertEqual(new["refresh_token"], "r1")      # not rotated: kept
        self.assertEqual(new["expires_at"], 4600)
        self.assertEqual(new["relay"], "https://x.y")
        rot = auth.apply_token_response(old, {"access_token": "b", "refresh_token": "r2"}, 0)
        self.assertEqual(rot["refresh_token"], "r2")
        self.assertIsNone(auth.apply_token_response(old, {"error": "x"}, 0))
        self.assertIsNone(auth.apply_token_response(old, None, 0))
        self.assertEqual(old["access_token"], "a")       # input untouched

    def test_refresh_goes_through_the_relay(self):
        self.assertIsNone(auth.refresh_request({}, "https://f"))
        self.assertIsNone(auth.refresh_request({"refresh_token": "r"}, None))
        url, headers, body = auth.refresh_request({"refresh_token": "r/+ x", "client_id": "c"},
                                                  "https://f")
        self.assertEqual(url, "https://f/api/spotify/refresh")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(json.loads(body), {"refresh_token": "r/+ x"})
        self.assertTrue(auth.refresh_revoked(400, {"error": "invalid_grant"}))
        self.assertFalse(auth.refresh_revoked(500, {"error": "invalid_grant"}))
        self.assertFalse(auth.refresh_revoked(400, None))

    def test_quote_and_form(self):
        self.assertEqual(auth.quote("a b/+=\u00e9"), "a%20b%2F%2B%3D%C3%A9")
        self.assertEqual(auth.form((("k", "v 1"), ("x", "&"))), "k=v%201&x=%26")

    def test_clear_tokens_keeps_relay(self):
        s = {"access_token": "a", "refresh_token": "r", "client_id": "c",
             "expires_at": 1, "relay": "https://x.y"}
        self.assertEqual(auth.clear_tokens(s), {"relay": "https://x.y"})
        self.assertFalse(auth.has_tokens(auth.clear_tokens(s)))
        self.assertTrue(auth.has_tokens(s))

    def _waiting(self):
        p = auth.Pairing()
        p.start()
        self.assertEqual(p.want(0), "session")
        p.busy = True
        self.assertIsNone(p.want(0))
        p.on_session(200, {"status": "ok", "pin": "ABC234", "secret": "s3",
                           "url": "https://f/spotify/?pin=ABC234",
                           "expires_in": 600, "interval": 3}, 0)
        self.assertEqual(p.state, auth.WAITING)
        return p

    def test_pairing_happy_path(self):
        p = self._waiting()
        self.assertIsNone(p.want(1))
        self.assertEqual(p.want(3), "poll")
        p.on_poll(200, {"status": "pending"}, 3)
        self.assertIsNone(p.want(5))
        self.assertEqual(p.want(6), "poll")
        tok = {"status": "authorized", "access_token": "a", "refresh_token": "r", "client_id": "c"}
        p.on_poll(200, tok, 6)
        self.assertEqual(p.state, auth.LINKED)
        self.assertIs(p.tokens, tok)
        self.assertIsNone(p.secret)
        self.assertEqual(p.remaining(6), 0)

    def test_pairing_expiry_and_errors(self):
        p = self._waiting()
        self.assertEqual(p.remaining(100), 500)
        self.assertIsNone(p.want(600))
        self.assertEqual(p.state, auth.EXPIRED)

        p = self._waiting()
        p.on_poll(200, {"status": "expired"}, 3)
        self.assertEqual(p.state, auth.EXPIRED)

        p = self._waiting()
        p.on_poll(429, None, 3)
        self.assertEqual(p.state, auth.WAITING)
        self.assertEqual(p.next_poll, 3 + 12)
        p.on_poll(0, None, 15)
        self.assertEqual(p.next_poll, 15 + 6)
        p.on_poll(403, {"status": "error"}, 21)
        self.assertEqual(p.state, auth.FAILED)

        p = self._waiting()
        p.on_poll(200, {"status": "authorized", "access_token": "a"}, 3)
        self.assertEqual((p.state, p.error), (auth.FAILED, auth.ERR_RELAY))

    def test_session_failures(self):
        for status, data, err in (
                (0, None, auth.ERR_UNREACHABLE),
                (503, {"status": "error", "error": "not_configured", "message": "set X"},
                 auth.ERR_NOT_CONFIGURED),
                (500, None, auth.ERR_RELAY),
                (200, {"status": "ok"}, auth.ERR_RELAY)):
            p = auth.Pairing()
            p.start()
            p.on_session(status, data, 0)
            self.assertEqual((p.state, p.error), (auth.FAILED, err))


# ── client ──────────────────────────────────────────────────────────────

def _track(name, uri, artists=("A",), dur=200000, **kw):
    t = {"name": name, "uri": uri, "duration_ms": dur,
         "artists": [{"name": a} for a in artists],
         "album": {"name": "Alb", "available_markets": ["IN"] * 3}}
    t.update(kw)
    return t


class ParseTest(unittest.TestCase):
    def test_ascii(self):
        self.assertEqual(client.ascii_text("Beyoncé – Halo"), "Beyonce - Halo")
        self.assertEqual(client.ascii_text("日本語 ok"), "? ok")
        self.assertEqual(client.ascii_text("x" * 50, 10), "xxxxxxxx..")
        self.assertEqual(client.ascii_text(None), "")

    def test_player_track(self):
        st = client.parse_player({
            "is_playing": True, "progress_ms": 61500, "shuffle_state": True,
            "repeat_state": "context",
            "device": {"id": "d1", "name": "Kitchen", "volume_percent": 40},
            "item": _track("Song", "spotify:track:1", ("A", "B"), 180000)})
        self.assertEqual(st["title"], "Song")
        self.assertEqual(st["artist"], "A, B")
        self.assertEqual(st["album"], "Alb")
        self.assertEqual((st["progress"], st["dur"]), (61, 180))
        self.assertEqual((st["device"], st["device_id"], st["volume"]), ("Kitchen", "d1", 40))
        self.assertTrue(st["playing"] and st["shuffle"])

    def test_player_episode_ad_and_empty(self):
        st = client.parse_player({"is_playing": False, "item": {
            "type": "episode", "name": "Ep 1", "duration_ms": 1000, "uri": "spotify:episode:1",
            "show": {"name": "Pod"}}})
        self.assertEqual((st["title"], st["artist"], st["album"]), ("Ep 1", "Pod", "Podcast"))
        ad = client.parse_player({"is_playing": True, "item": None,
                                  "currently_playing_type": "ad"})
        self.assertEqual(ad["title"], "Advertisement")
        self.assertIsNone(client.parse_player(None))
        hidden = client.parse_player({"is_playing": False, "item": None})
        self.assertEqual(hidden["title"], "Paused")

    def test_tracks_wrapped_bare_dupes_local(self):
        wrapped = {"items": [
            {"track": _track("One", "spotify:track:1")},
            {"track": _track("One again", "spotify:track:1")},
            {"track": _track("Local", "spotify:local:x", is_local=True)},
            {"item": _track("Two", "spotify:track:2")},
            {"track": None},
            "junk"]}
        rows = client.parse_tracks(wrapped, "spotify:playlist:p")
        self.assertEqual([r["title"] for r in rows], ["One", "Two"])
        self.assertEqual(rows[0], {"title": "One", "artist": "A", "dur": 200,
                                   "uri": "spotify:track:1", "ctx": "spotify:playlist:p"})
        bare = {"items": [_track("T%d" % i, "spotify:track:%d" % i) for i in range(30)]}
        self.assertEqual(len(client.parse_tracks(bare)), client.LIST_LIMIT)
        self.assertNotIn("ctx", client.parse_tracks(bare)[0])
        self.assertEqual(client.parse_tracks(None), [])

    def test_playlists(self):
        rows = client.parse_playlists({"items": [
            {"id": "p1", "name": "Mix", "uri": "spotify:playlist:p1",
             "tracks": {"total": 12}, "owner": {"display_name": "me"}},
            {"id": "p2", "name": "New", "items": {"total": 3}},
            {"name": "no id"}]})
        self.assertEqual(rows[0], {"name": "Mix", "id": "p1", "uri": "spotify:playlist:p1",
                                   "count": 12, "owner": "me"})
        self.assertEqual((rows[1]["count"], rows[1]["uri"]), (3, "spotify:playlist:p2"))
        self.assertEqual(len(rows), 2)

    def test_devices(self):
        devs = client.parse_devices({"devices": [
            {"id": "a", "name": "Phone", "is_active": True, "volume_percent": 30},
            {"id": "b", "name": "TV", "is_restricted": True},
            {"name": "no id"}]})
        self.assertEqual(devs, [{"id": "a", "name": "Phone", "active": True, "volume": 30}])


class FakeSpotify:
    """Records requests; answers from a list of (match, status, body)."""

    def __init__(self, routes):
        self.routes = list(routes)
        self.sent = []

    def __call__(self, method, url, headers, body):
        self.sent.append((method, url, dict(headers or {}), body))
        for i, (m, frag, status, payload) in enumerate(self.routes):
            if m == method and frag in url:
                self.routes.pop(i)
                raw = b"" if payload is None else json.dumps(payload).encode()
                hdrs = {"retry-after": "7"} if status == 429 else {}
                return status, hdrs, raw
        return 0, {}, b""


def _fresh(now=1000):
    return {"access_token": "AT", "refresh_token": "RT", "client_id": "CID",
            "expires_at": now + 3600}


class ClientTest(unittest.TestCase):
    def test_refreshes_before_expiry(self):
        fake = FakeSpotify([
            ("POST", "https://relay.test/api/spotify/refresh", 200,
             {"access_token": "AT2", "expires_in": 3600}),
            ("GET", "/me/player", 204, None)])
        c = client.Client({"access_token": "AT", "refresh_token": "RT", "client_id": "CID",
                           "expires_at": 1030}, fake, lambda: 1000, "https://relay.test")
        self.assertEqual(c.playback(), (client.OK, None))
        self.assertTrue(c.changed)
        self.assertEqual(c.tokens["access_token"], "AT2")
        self.assertEqual(c.tokens["refresh_token"], "RT")
        self.assertEqual(json.loads(fake.sent[0][3]), {"refresh_token": "RT"})
        self.assertFalse(any("accounts.spotify.com" in x[1] for x in fake.sent))
        self.assertEqual(fake.sent[1][2]["Authorization"], "Bearer AT2")
        self.assertIn("market=from_token", fake.sent[1][1])

    def test_401_refreshes_once_and_retries(self):
        fake = FakeSpotify([
            ("GET", "/me/player", 401, {"error": {"status": 401}}),
            ("POST", "/api/spotify/refresh", 200, {"access_token": "AT2", "refresh_token": "RT2"}),
            ("GET", "/me/player", 200, {"is_playing": True, "item": _track("S", "spotify:track:9")})])
        c = client.Client(_fresh(), fake, lambda: 1000, "https://relay.test")
        r, st = c.playback()
        self.assertEqual((r, st["title"]), (client.OK, "S"))
        self.assertEqual(c.tokens["refresh_token"], "RT2")
        self.assertEqual(len(fake.sent), 3)

    def test_revoked_refresh_unlinks(self):
        fake = FakeSpotify([("POST", "/api/spotify/refresh", 400, {"error": "invalid_grant"})])
        c = client.Client(dict(_fresh(), expires_at=0), fake, lambda: 1000, "https://relay.test")
        self.assertEqual(c.playback(), (client.UNLINKED, None))
        self.assertTrue(c.unlinked)
        self.assertEqual(len(fake.sent), 1)

    def test_relay_down_keeps_the_link(self):
        c = client.Client(dict(_fresh(), expires_at=0), FakeSpotify([]), lambda: 1000,
                          "https://relay.test")
        self.assertEqual(c.playback(), (client.OFFLINE, None))
        self.assertFalse(c.unlinked)

    def test_offline(self):
        c = client.Client(_fresh(), FakeSpotify([]), lambda: 1000)
        self.assertEqual(c.playback(), (client.OFFLINE, None))
        self.assertEqual(c.control("next"), client.OFFLINE)

    def test_controls(self):
        fake = FakeSpotify([
            ("PUT", "/me/player/pause", 204, None),
            ("POST", "/me/player/next", 204, None),
            ("PUT", "/me/player/volume?volume_percent=100", 204, None),
            ("PUT", "/me/player/play", 403, {"error": {"reason": "PREMIUM_REQUIRED"}}),
            ("POST", "/me/player/previous", 429, None)])
        c = client.Client(_fresh(), fake, lambda: 1000)
        self.assertEqual(c.control("pause"), client.OK)
        self.assertEqual(c.control("next"), client.OK)
        self.assertEqual(c.control("volume", 140), client.OK)
        self.assertEqual(c.control("play"), client.PREMIUM)
        self.assertEqual(c.control("prev"), client.LIMITED)
        self.assertEqual(c.retry_after, 7)
        self.assertEqual(c.control("dance"), client.FAILED)

    def test_play_track_wakes_a_device(self):
        row = {"title": "T", "artist": "A", "dur": 1, "uri": "spotify:track:5",
               "ctx": "spotify:playlist:p"}
        fake = FakeSpotify([
            ("PUT", "/me/player/play", 404, {"error": {"reason": "NO_ACTIVE_DEVICE"}}),
            ("GET", "/me/player/devices", 200, {"devices": [{"id": "dev 1", "name": "Phone"}]}),
            ("PUT", "/me/player", 204, None),
            ("PUT", "/me/player/play?device_id=dev%201", 204, None)])
        c = client.Client(_fresh(), fake, lambda: 1000)
        self.assertEqual(c.control("play_track", row), client.OK)
        body = json.loads(fake.sent[0][3])
        self.assertEqual(body, {"context_uri": "spotify:playlist:p",
                                "offset": {"uri": "spotify:track:5"}})
        self.assertEqual(json.loads(fake.sent[2][3]),
                         {"device_ids": ["dev 1"], "play": False})
        self.assertEqual(fake.sent[2][2]["Content-Type"], "application/json")

    def test_no_device_anywhere(self):
        fake = FakeSpotify([
            ("PUT", "/me/player/play", 404, {"error": {"reason": "NO_ACTIVE_DEVICE"}}),
            ("GET", "/me/player/devices", 200, {"devices": []})])
        c = client.Client(_fresh(), fake, lambda: 1000)
        self.assertEqual(c.control("play_context", "spotify:playlist:x"), client.NO_DEVICE)

    def test_library_paths(self):
        pl = {"id": "PL", "uri": "spotify:playlist:PL"}
        fake = FakeSpotify([
            ("GET", "/me/tracks?limit=20&market=from_token", 200,
             {"items": [{"track": _track("L", "spotify:track:1")}]}),
            ("GET", "/me/playlists", 200, {"items": [{"id": "PL", "name": "P"}]}),
            ("GET", "/playlists/PL/tracks", 200, {"items": [{"track": _track("X", "spotify:track:2")}]}),
            ("GET", "/me/top/tracks", 500, None)])
        c = client.Client(_fresh(), fake, lambda: 1000)
        self.assertEqual(c.library("liked")[1][0]["title"], "L")
        self.assertEqual(c.library("playlists")[1][0]["name"], "P")
        r, rows = c.library("playlist", pl)
        self.assertEqual(rows[0]["ctx"], "spotify:playlist:PL")
        self.assertEqual(c.library("top"), (client.FAILED, []))
        self.assertEqual(c.library("nope"), (client.FAILED, []))


# ── net ─────────────────────────────────────────────────────────────────

class NetTest(unittest.TestCase):
    def test_split_url(self):
        self.assertEqual(net.split_url("https://api.spotify.com/v1/me?x=1"),
                         ("api.spotify.com", 443, "/v1/me?x=1"))
        self.assertEqual(net.split_url("https://h:8443"), ("h", 8443, "/"))
        self.assertIsNone(net.split_url("http://h/"))

    def test_build_request(self):
        req = net.build_request("PUT", "h", "/p", {"Authorization": "Bearer t"})
        self.assertTrue(req.startswith(b"PUT /p HTTP/1.1\r\nHost: h\r\n"))
        self.assertIn(b"Authorization: Bearer t\r\n", req)
        self.assertIn(b"Content-Length: 0\r\n", req)    # Spotify wants it on empty PUTs
        self.assertTrue(req.endswith(b"\r\n\r\n"))
        get = net.build_request("GET", "h", "/")
        self.assertNotIn(b"Content-Length", get)
        post = net.build_request("POST", "h", "/", None, '{"a":1}')
        self.assertTrue(post.endswith(b'\r\n\r\n{"a":1}'))
        self.assertIn(b"Content-Length: 7\r\n", post)

    def test_parse_response(self):
        st, h, body = net.parse_response(
            b"HTTP/1.1 200 OK\r\nContent-Type: x\r\nTransfer-Encoding: chunked\r\n\r\n"
            b"3\r\nabc\r\n2\r\nde\r\n0\r\n\r\n")
        self.assertEqual((st, h["content-type"], body), (200, "x", b"abcde"))
        self.assertEqual(net.parse_response(b"HTTP/1.1 204 No Content\r\n\r\n")[0], 204)
        self.assertEqual(net.parse_response(b"HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\nabc"),
                         (0, {"content-length": "10"}, b""))
        self.assertEqual(net.parse_response(b"garbage")[0], 0)

    def test_complete(self):
        self.assertTrue(net._complete(bytearray(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")))
        self.assertFalse(net._complete(bytearray(b"HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\nok")))
        self.assertFalse(net._complete(bytearray(b"HTTP/1.1 200 OK\r\n\r\nok")))

    def test_request_rejects_plain_http(self):
        self.assertEqual(net.request("GET", "http://x/"), (0, {}, b""))


# ── the app on stub oreoOS ──────────────────────────────────────────────

class FakeDisplay:
    def __init__(self):
        self.texts = []
        self.monos = 0

    def clear(self, c=0):
        self.texts = []

    def rect(self, *a, **k):
        pass

    def text(self, s, x, y, color=0, scale=1):
        self.texts.append(s)

    def blit_mono(self, mask, x, y, w, h, color):
        self.monos += 1


class SyncRefresh:
    def __init__(self, fn):
        self.fn = fn
        self.result = None
        self.error = None
        self._done = False
        self._busy = False

    def busy(self):
        return self._busy

    def start(self, use_thread=True):
        self._busy = True
        self.result = self.fn()
        self._busy = False
        self._done = True
        return True

    def poll(self):
        if self._done:
            self._done = False
            return True
        return False


class FakeNet:
    """The relay and Spotify, as seen by the app's _send."""

    def __init__(self):
        self.relay_configured = True
        self.signed_in = False
        self.sent = []
        self.player = {"is_playing": True, "progress_ms": 10000,
                       "device": {"id": "d", "name": "Phone", "volume_percent": 50},
                       "item": _track("Song", "spotify:track:1")}

    def __call__(self, method, url, headers, body):
        self.sent.append((method, url, body))
        if url.endswith("/api/spotify/session"):
            if not self.relay_configured:
                return 503, {}, json.dumps({"status": "error", "error": "not_configured",
                                            "message": "set SPOTIFY_KV"}).encode()
            return 200, {}, json.dumps({
                "status": "ok", "pin": "ABC234", "secret": "sec",
                "url": "https://falera.elixpo.com/spotify/?pin=ABC234",
                "expires_in": 600, "interval": 3}).encode()
        if url.endswith("/api/spotify/poll"):
            assert json.loads(body) == {"pin": "ABC234", "secret": "sec"}
            if not self.signed_in:
                return 200, {}, b'{"status": "pending"}'
            return 200, {}, json.dumps({
                "status": "authorized", "access_token": "AT", "refresh_token": "RT",
                "client_id": "CID", "expires_in": 3600}).encode()
        if "/me/player?" in url:
            return 200, {}, json.dumps(self.player).encode()
        if "/me/player/" in url:
            return 204, {}, b""
        if "/me/tracks" in url:
            return 200, {}, json.dumps({"items": [{"track": _track("Liked", "spotify:track:7")}]}).encode()
        return 0, {}, b""


def load_app(state_dir, fake_net, online=True):
    api = types.ModuleType("oreoOS.api")
    api.SCREEN_W, api.SCREEN_H = 320, 240
    names = ("BTN_A", "BTN_B", "BTN_C", "BTN_UP", "BTN_DOWN", "BTN_LEFT",
             "BTN_RIGHT", "BTN_HOME")
    for i, n in enumerate(names):
        setattr(api, n, i + 1)
    api.rgb = lambda r, g, b: (r, g, b)
    api.WHITE, api.BLACK = (255, 255, 255), (0, 0, 0)
    widgets = types.ModuleType("oreoOS.widgets")
    widgets.HEADER_H, widgets.HINT_H = 28, 16
    widgets.draw_header = widgets.draw_hint = lambda *a, **k: None
    spec = importlib.util.spec_from_file_location("oreoOS.state", ROOT / "oreoOS" / "state.py")
    state = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(state)
    state.STATE_DIR = state_dir
    cache = types.ModuleType("oreoOS.cache")
    cache.Refresh = SyncRefresh
    http = types.ModuleType("oreoOS._http")
    http.tls_wrap = lambda raw, host: raw

    class App:
        def on_enter(self, os_):
            self.os = os_

    package = types.ModuleType("oreoOS")
    package.App = App
    package.api, package.widgets, package.state = api, widgets, state
    package.cache, package._http = cache, http
    ware = types.ModuleType("oreoWare")
    wifi = types.ModuleType("oreoWare.wifi")
    wifi.is_connected = lambda: online
    ware.wifi = wifi
    mods = {"oreoOS": package, "oreoOS.api": api, "oreoOS.widgets": widgets,
            "oreoOS.state": state, "oreoOS.cache": cache, "oreoOS._http": http,
            "oreoWare": ware, "oreoWare.wifi": wifi}
    saved = {k: sys.modules.get(k) for k in mods}

    def restore():
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    # The app imports oreoOS.cache and friends lazily, so the stubs stay
    # installed until the test's cleanup calls restore().
    sys.modules.update(mods)
    sys.modules.pop(PKG + ".app", None)
    app_mod = importlib.import_module(PKG + ".app")
    app_mod._restore = restore
    app_mod._send = fake_net
    app_mod._wall = lambda: 1000
    app_mod.APP_ID = "spotify"
    return app_mod, api, state


class AppFlowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.state_dir = self.tmp + "/state"
        self.net = FakeNet()

    def _app(self, online=True):
        mod, api, state = load_app(self.state_dir, self.net, online)
        self.addCleanup(mod._restore)
        self.api, self.state = api, state
        app = mod.App()
        app.on_enter(types.SimpleNamespace(display=FakeDisplay()))
        return app

    def _tick(self, app):
        """Start the next job and collect it (the sync worker hands the
        result back on the following update, as Refresh.poll does)."""
        app.update(0.05)
        app.update(0.05)

    def _save(self, data):
        spec = importlib.util.spec_from_file_location("st_tmp", ROOT / "oreoOS" / "state.py")
        st = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(st)
        st.STATE_DIR = self.state_dir
        st.save("spotify", data)

    def _frames(self, app, seconds, dt=0.5):
        for _ in range(int(seconds / dt)):
            app.update(dt)

    def _draw(self, app):
        d = FakeDisplay()
        app._dirty = True
        app.draw(d)
        return d

    def test_link_then_play_then_unlink(self):
        app = self._app()
        self.assertEqual(app._view, "link")
        self._tick(app)                                     # session request
        self.assertEqual(app._pair.state, auth.WAITING)
        d = self._draw(app)
        self.assertIn("ABC234", d.texts)
        self.assertEqual(d.monos, 1)                        # the QR code
        self._frames(app, 4)
        self.assertTrue(any(u.endswith("/api/spotify/poll") for _, u, _ in self.net.sent))
        self.assertEqual(app._view, "link")
        self.net.signed_in = True
        self._frames(app, 4)
        self.assertEqual(app._view, "player")
        saved = self.state.load("spotify")
        self.assertEqual((saved["access_token"], saved["refresh_token"], saved["client_id"]),
                         ("AT", "RT", "CID"))
        self.assertEqual(saved["expires_at"], 1000 + 3600)

        self._frames(app, 1)                                # first playback poll
        self.assertEqual(app._np["title"], "Song")
        d = self._draw(app)
        self.assertIn("Song", d.texts)
        self.assertIn("Phone", d.texts)

        app.on_button_press(self.api.BTN_A)                 # pause at once
        self.assertFalse(app._np["playing"])
        self._tick(app)
        self.assertEqual(self.net.sent[-1][:2],
                         ("PUT", "https://api.spotify.com/v1/me/player/pause"))

        for _ in range(3):
            app.on_button_press(self.api.BTN_UP)
        self.assertEqual(app._vol, 65)
        n = len(self.net.sent)
        app.update(0.1)
        self.assertFalse([u for _, u, _ in self.net.sent[n:] if "volume" in u])  # debounced
        self._frames(app, 1, 0.25)
        vols = [u for _, u, _ in self.net.sent if "volume_percent" in u]
        self.assertEqual(vols, ["https://api.spotify.com/v1/me/player/volume?volume_percent=65"])

        app.on_button_press(self.api.BTN_C)                 # asks first
        self.assertTrue(app._confirm)
        self.assertIn("Unlink Spotify?", self._draw(app).texts)
        app.on_button_press(self.api.BTN_B)
        self.assertFalse(app._confirm)
        self.assertTrue(auth.has_tokens(self.state.load("spotify")))
        app.on_button_press(self.api.BTN_C)
        app.on_button_press(self.api.BTN_A)
        self.assertEqual(app._view, "link")
        self.assertFalse(auth.has_tokens(self.state.load("spotify")))

    def test_library_and_play(self):
        self._save({"access_token": "AT", "refresh_token": "RT", "client_id": "CID",
                    "expires_at": 99999})
        app = self._app()
        self.assertEqual(app._view, "player")
        app.on_button_press(self.api.BTN_B)
        self.assertEqual(app._view, "library")
        self.assertIn("Liked songs", self._draw(app).texts)
        app.on_button_press(self.api.BTN_A)                 # open Liked songs
        self.assertIn("Loading...", self._draw(app).texts)
        self._tick(app)
        self.assertEqual(app._lib[-1]["rows"][0]["title"], "Liked")
        app.on_button_press(self.api.BTN_A)                 # play it
        self.assertEqual(app._view, "player")
        self.assertEqual(app._np["title"], "Liked")
        self._tick(app)
        put = [x for x in self.net.sent if x[1].endswith("/me/player/play")][-1]
        self.assertEqual(json.loads(put[2]), {"uris": ["spotify:track:7"]})
        app.on_button_press(self.api.BTN_B)                 # library remembers its place
        self.assertEqual(app._lib[-1]["title"], "LIKED SONGS")
        app.on_button_press(self.api.BTN_LEFT)
        self.assertEqual(app._lib[-1]["kind"], "root")
        app.on_button_press(self.api.BTN_B)
        self.assertEqual(app._view, "player")

    def test_relay_not_configured(self):
        self.net.relay_configured = False
        app = self._app()
        self._tick(app)
        self.assertEqual((app._pair.state, app._pair.error),
                         (auth.FAILED, auth.ERR_NOT_CONFIGURED))
        self.assertIn("Sign-in relay not set up", self._draw(app).texts)

    def test_offline_waits(self):
        app = self._app(online=False)
        self._frames(app, 5)
        self.assertEqual(self.net.sent, [])
        self.assertIn("Wi-Fi is not connected", self._draw(app).texts)

    def test_bad_relay_override(self):
        self._save({"relay": "http://lan.local"})
        app = self._app()
        self._tick(app)
        self.assertEqual(self.net.sent, [])
        self.assertIn("Bad relay URL", self._draw(app).texts)

    def test_draws_every_view(self):
        self._save({"access_token": "AT", "refresh_token": "RT", "client_id": "CID",
                    "expires_at": 99999})
        app = self._app()
        self.assertIn("Asking Spotify...", self._draw(app).texts)
        self._frames(app, 1)
        self.net.player = None
        app._np = None
        self.assertIn("Nothing playing", self._draw(app).texts)
        app.on_button_press(self.api.BTN_B)
        self._draw(app)
        app._confirm = True
        self._draw(app)
        app._view = "link"
        app._start_pairing()
        self.assertIn("Getting a code...", self._draw(app).texts)


if __name__ == "__main__":
    unittest.main()

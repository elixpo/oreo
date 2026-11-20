"""Host tests for the Jamendo app (apps_market/jamendo): URL building,
response and licence parsing, the client id (default and saved override),
and the app on stub modules.

    python3 -m unittest tests.test_jamendo_app -v
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import audio_env as E  # noqa: E402


def tracks_json(n=3, status="success"):
    res = [{"id": str(100 + i), "name": "Song %d" % i, "artist_name": "Artist %d" % i,
            "album_name": "Album", "album_id": "77", "duration": 180 + i, "position": 3 - i,
            "audio": "https://prod-1.storage.jamendo.com/?trackid=%d&format=mp32" % (100 + i),
            "license_ccurl": "http://creativecommons.org/licenses/by-nc-sa/3.0/"}
           for i in range(n)]
    res.append({"id": "9", "name": "No audio", "audio": ""})
    return json.dumps({"headers": {"status": status, "code": 0, "error_message": "",
                                   "results_count": n}, "results": res}).encode()


class JamApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = E.Env(self.tmp.name)
        self.mod = self.env.load_app("apps_market/jamendo", "jamendo")
        self.jam = self.mod.jam

    def tearDown(self):
        self.env.close()
        self.tmp.cleanup()

    def test_urls(self):
        j = self.jam
        u = j.tracks_featured("abc")
        self.assertTrue(u.startswith("https://api.jamendo.com/v3.0/tracks/?client_id=abc&format=json"))
        self.assertIn("audioformat=mp32", u)
        self.assertIn("featured=true", u)
        self.assertIn("tags=hip%20hop", j.tracks_tag("abc", "hip hop"))
        self.assertIn("search=caf%C3%A9", j.tracks_search("abc", "café"))
        self.assertIn("album_id=77", j.tracks_album("abc", "77"))
        self.assertIn("namesearch=x", j.albums_search("abc", "x"))
        self.assertTrue(j.albums_popular("abc").startswith("https://api.jamendo.com/v3.0/albums/?"))

    def test_parse_tracks_and_licence(self):
        t = self.jam.parse_tracks(tracks_json())
        self.assertEqual(len(t), 3)
        self.assertEqual(t[0]["artist"], "Artist 0")
        self.assertEqual(t[0]["licence"], "CC BY-NC-SA 3.0")
        self.assertEqual(t[0]["duration"], 180)
        self.assertEqual([x["name"] for x in self.jam.album_order(t)],
                         ["Song 2", "Song 1", "Song 0"])
        self.assertEqual(self.jam.licence_name(""), "CC licence")
        self.assertEqual(self.jam.licence_name("https://creativecommons.org/licenses/by/4.0/"),
                         "CC BY 4.0")
        self.assertEqual(self.jam.licence_name("http://creativecommons.org/publicdomain/zero/1.0/"),
                         "CC0 / public domain")

    def test_errors(self):
        bad = json.dumps({"headers": {"status": "failed", "code": 5,
                                      "error_message": "Invalid Client Id"}, "results": []})
        with self.assertRaises(self.jam.ApiError) as cm:
            self.jam.parse_tracks(bad)
        self.assertEqual(str(cm.exception), "client id not accepted")
        with self.assertRaises(self.jam.ApiError):
            self.jam.parse_albums(b"<html>")
        with self.assertRaises(OSError):
            self.jam.fetch("u", get=lambda u: None)

    def test_parse_albums(self):
        a = self.jam.parse_albums(json.dumps({"headers": {"status": "success"}, "results": [
            {"id": "5", "name": "LP", "artist_name": "X"}, {"name": "no id"}]}))
        self.assertEqual(a, [{"id": "5", "name": "LP", "artist": "X"}])

    def test_client_id(self):
        self.assertEqual(self.mod.config.DEFAULT_CLIENT_ID, "c4a5c1db")
        self.assertEqual(self.mod.client_id({}), "c4a5c1db")
        self.assertEqual(self.mod.client_id({"client_id": " mine "}), "mine")
        self.mod.config.DEFAULT_CLIENT_ID = ""
        self.assertEqual(self.mod.client_id({}), "")


class JamendoAppTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = E.Env(self.tmp.name)
        self.mod = self.env.load_app("apps_market/jamendo", "jamendo")
        self.api = self.env.api
        self.urls = []

        def fetch(url, get=None):
            self.urls.append(url)
            if "/albums/" in url:
                return json.dumps({"headers": {"status": "success"}, "results": [
                    {"id": "77", "name": "Album", "artist_name": "A"}]}).encode()
            return tracks_json()
        self.mod.jam.fetch = fetch
        self.audio, self.exp = self.env.make_audio()
        self.os = E.FakeOS(self.audio)
        self.hosts = []

        def connect(host, port, tls, timeout):
            self.hosts.append(host)
            return E.FakeSock(E.http_reply(b"\x01\x00" * 6000, "200 OK", [
                ("Content-Type", "audio/mpeg"), ("Content-Length", "12000")]))
        P = self.env.player
        orig = P.Player.__init__

        def init(p, audio, connect_=None, decoder=None, threaded=True):
            orig(p, audio, connect=connect, decoder=lambda: E.FakeDecoder(), threaded=False)
        P.Player.__init__ = init

    def tearDown(self):
        self.env.close()
        self.tmp.cleanup()

    def start(self):
        self.app = self.mod.App()
        self.app.on_enter(self.os)
        self.app.draw(self.os.display)

    def frame(self, n=1):
        for _ in range(n):
            self.app.update(0.05)
            if E.FakeI2S.instances and not E.FakeI2S.instances[-1].closed:
                E.FakeI2S.instances[-1].fire()
            self.app.draw(self.os.display)

    def press(self, *btns):
        for b in btns:
            self.app.on_button_press(b)
            self.frame()

    def test_featured_plays_with_licence_then_next(self):
        self.start()
        self.press(self.api.BTN_A)
        self.assertIn("client_id=c4a5c1db", self.urls[-1])
        self.assertIn("Song 0 - Artist 0", self.os.display.joined())
        self.press(self.api.BTN_A)
        self.assertEqual(self.app.view, "player")
        self.frame(5)
        txt = self.os.display.joined()
        self.assertIn("Artist 0", txt)
        self.assertIn("Song 0", txt)
        self.assertIn("CC BY-NC-SA 3.0", txt)
        self.assertEqual(self.hosts[0], "prod-1.storage.jamendo.com")
        # the 12 KB "track" ends and the next one starts by itself
        for _ in range(400):
            self.frame()
            if self.app.index == 1:
                break
        self.assertEqual(self.app.index, 1)
        self.press(self.api.BTN_LEFT)
        self.assertEqual(self.app.index, 0)

    def test_saved_client_id_wins(self):
        self.env.state.save("jamendo", {"client_id": "override1"})
        self.start()
        self.press(self.api.BTN_A)
        self.assertIn("client_id=override1", self.urls[-1])

    def test_not_set_up(self):
        self.mod.config.DEFAULT_CLIENT_ID = ""
        self.start()
        self.assertIn("Jamendo not set up", self.os.display.joined())
        self.assertIn("devportal.jamendo.com", self.os.display.joined())
        self.app.on_button_press(self.api.BTN_A)
        self.assertEqual(self.urls, [])
        self.app.on_button_press(self.api.BTN_B)
        self.assertTrue(self.os.quit_called)

    def test_album_in_order(self):
        self.start()
        self.press(self.api.BTN_DOWN, self.api.BTN_DOWN, self.api.BTN_DOWN, self.api.BTN_A)
        self.assertIn("Album - A", self.os.display.joined())
        self.press(self.api.BTN_A)
        self.assertIn("album_id=77", self.urls[-1])
        self.assertEqual(self.app.list.items[0]["name"], "Song 2")

    def test_api_error_shown(self):
        self.mod.jam.fetch = lambda url, get=None: json.dumps(
            {"headers": {"status": "failed", "code": 5}, "results": []}).encode()
        self.start()
        self.press(self.api.BTN_A)
        self.assertIn("client id not accepted", self.os.display.joined())


if __name__ == "__main__":
    unittest.main()

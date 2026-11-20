"""Host tests for the Radio app (apps_market/radio): Radio Browser URL
building and response parsing, and the app on stub modules (fake audio,
synchronous workers, a fake Radio Browser and a fake stream).

    python3 -m unittest tests.test_radio_app -v
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import audio_env as E  # noqa: E402

STATIONS = [
    {"stationuuid": "u-hi", "name": "Big FM", "url": "http://big/x", "url_resolved": "http://big/live",
     "codec": "MP3", "bitrate": 128, "countrycode": "de", "country": "Germany",
     "tags": "pop,rock,news,talk", "clickcount": 900, "hls": 0},
    {"stationuuid": "u-lo", "name": "Small FM", "url": "http://small/live", "url_resolved": "",
     "codec": "MP3", "bitrate": 64, "countrycode": "IN", "tags": "", "clickcount": 10, "hls": 0},
    {"stationuuid": "u-aac", "name": "AAC FM", "url_resolved": "http://aac/", "codec": "AAC",
     "bitrate": 48},
    {"stationuuid": "u-hls", "name": "HLS FM", "url_resolved": "http://hls/", "codec": "MP3",
     "hls": 1},
    {"stationuuid": "u-unk", "name": "  ", "url_resolved": "https://unk/", "codec": "mp3",
     "bitrate": 0, "clickcount": 500},
    {"stationuuid": "u-lo", "name": "dup", "url_resolved": "http://small/live", "codec": "MP3"},
]


class RadioBrowserTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = E.Env(self.tmp.name)
        self.rb = self.env.load_app("apps_market/radio", "radio").rb

    def tearDown(self):
        self.env.close()
        self.tmp.cleanup()

    def test_paths(self):
        p = self.rb.path_top()
        self.assertTrue(p.startswith("/json/stations/search?"))
        for part in ("codec=MP3", "hidebroken=true", "order=clickcount", "reverse=true",
                     "bitrateMax=128", "limit=40"):
            self.assertIn(part, p)
        self.assertIn("countrycode=IN", self.rb.path_country("IN"))
        self.assertIn("tag=drum%20%26%20bass", self.rb.path_tag("drum & bass"))
        self.assertIn("name=caf%C3%A9", self.rb.path_search("café"))
        self.assertEqual(self.rb.path_click("ab-12"), "/json/url/ab-12")

    def test_parse_stations(self):
        out = self.rb.parse_stations(json.dumps(STATIONS).encode())
        self.assertEqual([s["id"] for s in out], ["u-lo", "u-hi", "u-unk"])  # low bitrate first
        big = out[1]
        self.assertEqual(big["url"], "http://big/live")          # url_resolved wins
        self.assertEqual(big["cc"], "DE")
        self.assertEqual(big["tags"], "pop, rock, news")
        self.assertEqual(out[0]["url"], "http://small/live")      # falls back to url
        self.assertEqual(out[2]["name"], "Unnamed station")
        self.assertEqual(self.rb.parse_stations(b"not json"), [])
        self.assertEqual(self.rb.parse_stations(b"{}"), [])

    def test_parse_countries_and_tags(self):
        c = self.rb.parse_countries(json.dumps([
            {"name": "India", "iso_3166_1": "IN", "stationcount": 500},
            {"name": "Nowhere", "iso_3166_1": "", "stationcount": 3},
            {"name": "Empty", "iso_3166_1": "EM", "stationcount": 0}]))
        self.assertEqual(c, [("IN", "India", 500)])
        t = self.rb.parse_tags(json.dumps([{"name": "jazz", "stationcount": 40}, {"name": " "}]))
        self.assertEqual(t, [("jazz", 40)])

    def test_fetch_falls_over_to_next_server(self):
        seen = []

        def get(url):
            seen.append(url)
            return None if "de1" in url else b"[]"
        self.assertEqual(self.rb.fetch("/json/x", get), b"[]")
        self.assertEqual(seen, ["https://de1.api.radio-browser.info/json/x",
                                "https://de2.api.radio-browser.info/json/x"])
        with self.assertRaises(OSError):
            self.rb.fetch("/json/x", lambda u: None)


class RadioAppTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = E.Env(self.tmp.name)
        self.mod = self.env.load_app("apps_market/radio", "radio")
        self.api = self.env.api
        self.fetched = []
        stations = json.dumps(STATIONS).encode()

        def fetch(path, get=None, servers=None):
            self.fetched.append(path)
            if path.startswith("/json/url/"):
                return b"{}"
            if path.startswith("/json/countries"):
                return json.dumps([{"name": "India", "iso_3166_1": "IN",
                                    "stationcount": 5}]).encode()
            return stations
        self.mod.rb.fetch = fetch
        audio, self.exp = self.env.make_audio()
        self.audio = audio
        self.os = E.FakeOS(audio)
        self.streams = []

        def connect(host, port, tls, timeout):
            s = E.FakeSock(E.http_reply(b"\x01\x00" * 20000, "200 OK",
                                        [("Content-Type", "audio/mpeg"), ("icy-metaint", "0"),
                                         ("icy-name", "x")]), hang=True)
            self.streams.append((host, s))
            return s
        P = self.env.player
        orig = P.Player.__init__

        def init(p, audio, connect_=None, decoder=None, threaded=True):
            orig(p, audio, connect=connect, decoder=lambda: E.FakeDecoder(), threaded=False)
        P.Player.__init__ = init
        self.app = self.mod.App()
        self.app.on_enter(self.os)

    def tearDown(self):
        self.env.close()
        self.tmp.cleanup()

    def frame(self, n=1):
        for _ in range(n):
            self.app.update(0.03)
            if E.FakeI2S.instances and not E.FakeI2S.instances[-1].closed:
                E.FakeI2S.instances[-1].fire()
            self.app.draw(self.os.display)

    def press(self, *btns):
        for b in btns:
            self.app.on_button_press(b)
            self.frame()

    def test_top_list_play_and_click(self):
        self.frame()
        self.assertIn("Top stations", self.os.display.joined())
        self.press(self.api.BTN_A)                 # Top stations
        self.assertIn("Small FM", self.os.display.joined())
        self.press(self.api.BTN_A)                 # play the first
        self.assertEqual(self.app.view, "player")
        self.assertEqual(self.streams[0][0], "small")
        self.assertTrue(any(p == "/json/url/u-lo" for p in self.fetched))
        self.frame(35)
        self.assertEqual(self.app.player.state, "playing")
        self.assertTrue(self.exp.amp)
        self.assertIn("Playing", self.os.display.joined())
        self.press(self.api.BTN_DOWN)              # volume down
        self.assertEqual(self.app.volume, 50)
        self.assertEqual(self.audio.volume, 50)
        self.press(self.api.BTN_A)                 # stop
        self.assertEqual(self.app.player.state, "idle")
        self.app.on_exit()
        self.assertEqual(self.env.state.load("radio")["volume"], 50)

    def test_favourites_persist(self):
        self.press(self.api.BTN_A)                 # Top
        self.press(self.api.BTN_RIGHT)             # star Small FM
        self.assertEqual(len(self.app.favs), 1)
        self.app.on_exit()
        app2 = self.mod.App()
        app2.on_enter(self.os)
        self.assertEqual(app2.favs[0]["url"], "http://small/live")
        app2.on_button_press(self.api.BTN_DOWN)    # Favourites
        app2.on_button_press(self.api.BTN_A)
        app2.draw(self.os.display)
        self.assertIn("Small FM", self.os.display.joined())

    def test_countries_then_back(self):
        self.press(self.api.BTN_DOWN, self.api.BTN_DOWN, self.api.BTN_A)
        self.assertIn("India", self.os.display.joined())
        self.press(self.api.BTN_A)
        self.assertIn("countrycode=IN", self.fetched[-1])
        self.press(self.api.BTN_B, self.api.BTN_B)
        self.assertEqual(self.app.kind, "menu")
        self.press(self.api.BTN_B)
        self.assertTrue(self.os.quit_called)

    def test_search_with_touch(self):
        for _ in range(4):
            self.press(self.api.BTN_DOWN)          # Search
        self.press(self.api.BTN_A)
        self.assertEqual(self.app.view, "search")
        mu = self.env.mediaui
        # tap "j", "a", "z" then OK
        for ch in "jaz":
            r = [i for i, row in enumerate(mu.KB_ROWS) if ch in row][0]
            c = mu.KB_ROWS[r].index(ch)
            self.app.on_touch("down", mu.KB_X + c * mu.KB_W + 5, mu.KB_Y + r * mu.KB_H + 5)
        self.assertEqual(self.app.kb.text, "jaz")
        self.app.on_touch("down", mu.KB_X + 4 * mu.KB_ACT_W + 5, mu.KB_Y + 4 * mu.KB_H + 5)
        self.frame()
        self.assertIn("name=jaz", self.fetched[-1])
        self.assertEqual(self.app.view, "list")
        # tap the second row twice: select, then play
        y = mu.TOP + mu.ROW_H + 5
        self.app.on_touch("down", 50, y)
        self.app.on_touch("down", 50, y)
        self.assertEqual(self.app.view, "player")
        self.assertEqual(self.app.station["id"], "u-hi")

    def test_no_speaker(self):
        a, _ = self.env.make_audio(available=False)
        os_ = E.FakeOS(a)
        app = self.mod.App()
        app.on_enter(os_)
        app.draw(os_.display)
        self.assertIn("Needs the PCB badge (speaker)", os_.display.joined())
        app.on_button_press(self.api.BTN_B)
        self.assertTrue(os_.quit_called)
        app.on_exit()


if __name__ == "__main__":
    unittest.main()

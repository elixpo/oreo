"""Host tests for the Podcasts app (apps_market/podcasts): the streaming RSS
parser, iTunes search parsing, and the app on stub modules (subscriptions,
resume positions, 15/30 s skips).

    python3 -m unittest tests.test_podcasts_app -v
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import audio_env as E  # noqa: E402

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
<channel>
  <title>Badge &amp; Friends</title>
  <image><title>Not the show title</title><url>http://x/i.png</url></image>
  <itunes:owner><itunes:name>Owner</itunes:name></itunes:owner>
  <description><![CDATA[<p>A show with <b>markup</b> & a ]] tricky bit</p>]]></description>
  <!-- a comment with <item> inside -->
  <item>
    <title><![CDATA[Ep 3: Café <live>]]></title>
    <pubDate>Tue, 03 Nov 2026 10:00:00 GMT</pubDate>
    <itunes:duration>1:02:03</itunes:duration>
    <guid isPermaLink="false">ep-3</guid>
    <description>&lt;p&gt;Long &amp; escaped html&lt;/p&gt;</description>
    <enclosure url="https://cdn.example/ep3.mp3?a=1&amp;b=2" length="123456" type="audio/mpeg"/>
  </item>
  <item>
    <title>Ep 2 (video)</title>
    <enclosure url="https://cdn.example/ep2.m4v" type="video/x-m4v" length="1"/>
  </item>
  <item>
    <title>Ep 1 &#8211; start</title>
    <itunes:duration>1800</itunes:duration>
    <enclosure type='audio/mp3' url='https://cdn.example/ep1.mp3' length='9'></enclosure>
  </item>
</channel>
</rss>
"""


class EnvCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = E.Env(self.tmp.name)
        self.mod = self.env.load_app("apps_market/podcasts", "podcasts")
        self.rss = self.mod.rss

    def tearDown(self):
        self.env.close()
        self.tmp.cleanup()


class RssTest(EnvCase):
    def parse(self, text, piece, max_items=40):
        p = self.rss.RssParser(max_items)
        data = text.encode("utf-8")
        for i in range(0, len(data), piece):
            if not p.feed(data[i:i + piece]):
                break
        return p

    def test_any_chunking(self):
        for piece in (1, 2, 3, 7, 64, 1000, 100000):
            p = self.parse(FEED, piece)
            self.assertEqual(p.title, "Badge & Friends", piece)
            self.assertEqual(len(p.items), 2, piece)
            self.assertEqual(p.skipped, 1)
            e3, e1 = p.items
            self.assertEqual(e3["title"], "Ep 3: Café <live>")
            self.assertEqual(e3["url"], "https://cdn.example/ep3.mp3?a=1&b=2")
            self.assertEqual(e3["length"], 123456)
            self.assertEqual(e3["duration"], 3723)
            self.assertEqual(e3["date"], "03 Nov 2026")
            self.assertEqual(e3["guid"], "ep-3")
            self.assertEqual(e1["title"], "Ep 1 – start")
            self.assertEqual(e1["duration"], 1800)
            self.assertEqual(e1["guid"], e1["url"])

    def test_stops_after_max_items(self):
        p = self.parse(FEED, 50, max_items=1)
        self.assertTrue(p.done)
        self.assertEqual(len(p.items), 1)
        self.assertFalse(p.feed(b"<item>"))

    def test_memory_stays_bounded(self):
        """A 2 MB description never sits in the parser's buffer."""
        p = self.rss.RssParser()
        p.feed(b"<rss><channel><title>T</title><item><title>x</title><description><![CDATA[")
        big = b"<p>" + b"y" * 4000 + b"</p>"
        top = 0
        for _ in range(500):
            p.feed(big)
            top = max(top, len(p._buf))
        p.feed(b"]]></description><description>")
        for _ in range(500):
            p.feed(b"&lt;b&gt;" + b"z" * 4000)
            top = max(top, len(p._buf))
        p.feed(b"</description><enclosure url=\"http://a/b.mp3\" type=\"audio/mpeg\"/></item>")
        self.assertLess(top, 9000)
        self.assertEqual(p.items[0]["url"], "http://a/b.mp3")

    def test_helpers(self):
        self.assertEqual(self.rss.duration_s("62:03"), 3723)
        self.assertEqual(self.rss.duration_s("bad"), 0)
        self.assertTrue(self.rss.is_mp3("http://a/x.MP3?y", ""))
        self.assertFalse(self.rss.is_mp3("http://a/x.mp3", "audio/x-m4a"))
        self.assertEqual(self.rss.unescape("a &amp; b &#x41; &bogus; &"), "a & b A &bogus; &")
        self.assertEqual(self.rss.attrs('enclosure url="u" length=5 type=\'t\''),
                         {"url": "u", "length": "5", "type": "t"})


class ItunesTest(EnvCase):
    def test_url_and_parse(self):
        it = self.mod.itunes
        u = it.search_url("café talk")
        self.assertTrue(u.startswith("https://itunes.apple.com/search?media=podcast&entity=podcast"))
        self.assertIn("term=caf%C3%A9+talk", u)
        data = json.dumps({"resultCount": 3, "results": [
            {"collectionId": 1, "collectionName": "Show A", "artistName": "A",
             "feedUrl": "https://a.example/feed"},
            {"collectionId": 2, "collectionName": "No feed"},
            {"collectionId": 3, "trackName": "Show C", "feedUrl": "http://c/rss"}]})
        r = it.parse_results(data.encode())
        self.assertEqual([x["name"] for x in r], ["Show A", "Show C"])
        self.assertEqual(it.parse_results(b"oops"), [])
        with self.assertRaises(OSError):
            it.search("x", get=lambda u: None)


class FetchFeedTest(EnvCase):
    def test_streams_through_get_stream(self):
        pieces = []

        def get_stream(url, sink, user_agent=None):
            self.assertEqual(user_agent, "FaleraOS-Podcasts/1.0")
            data = FEED.encode()
            for i in range(0, len(data), 100):
                pieces.append(1)
                if sink(memoryview(data[i:i + 100])) is False:
                    return
        title, items, skipped = self.mod.fetch_feed("https://f/rss", get_stream, max_items=1)
        self.assertEqual((title, len(items)), ("Badge & Friends", 1))
        self.assertLess(len(pieces), len(FEED) // 100)     # stopped early

    def test_player_get_stream_redirect(self):
        P = self.env.player
        net = E.FakeNet({"a.example": [
            E.FakeSock(E.http_reply(b"", "301 Moved", [("Location", "https://b.example/rss")]))],
            "b.example": [E.FakeSock(E.http_reply(FEED.encode(), "200 OK", []), piece=333)]})
        p = self.rss.RssParser()
        P.get_stream("http://a.example/rss", p.feed, connect=net)
        self.assertEqual(len(p.items), 2)
        self.assertEqual(net.calls[1], ("b.example", 443, True))
        self.assertNotIn(b"Icy-MetaData", bytes(net.socks[0].sent))


class PodcastsAppTest(EnvCase):
    def setUp(self):
        super().setUp()
        self.api = self.env.api
        self.audio, self.exp = self.env.make_audio()
        self.os = E.FakeOS(self.audio)
        self.mod.itunes.search = lambda q: [{"id": 1, "name": "Badge & Friends", "author": "A",
                                             "feed": "https://f.example/rss"}]
        self.mod.fetch_feed = lambda url: ("Badge & Friends",
                                           self.parse_items(), 0)
        total = 600 * 64 * 125                  # a 10-minute 64 kb/s episode
        self.total = total
        self.socks = []

        def connect(host, port, tls, timeout):
            req_range = None
            s = E.FakeSock(b"", hang=True)

            # reply depends on the request, so build it on first read
            orig_read = s.readinto

            def readinto(mv, s=s):
                if not s.data and not getattr(s, "replied", False):
                    s.replied = True
                    sent = bytes(s.sent)
                    if b"Range: bytes=" in sent:
                        start = int(sent.split(b"Range: bytes=")[1].split(b"-")[0])
                        s.data = bytearray(E.http_reply(b"\x01\x00" * 15000, "206 Partial Content", [
                            ("Content-Type", "audio/mpeg"),
                            ("Content-Range", "bytes %d-%d/%d" % (start, total - 1, total))]))
                    else:
                        s.data = bytearray(E.http_reply(b"\x01\x00" * 15000, "200 OK", [
                            ("Content-Type", "audio/mpeg"), ("Content-Length", str(total)),
                            ("Accept-Ranges", "bytes")]))
                return orig_read(mv)
            s.readinto = readinto
            self.socks.append(s)
            return s
        P = self.env.player
        orig = P.Player.__init__

        def init(p, audio, connect_=None, decoder=None, threaded=True):
            orig(p, audio, connect=connect, decoder=lambda: E.FakeDecoder(), threaded=False)
        P.Player.__init__ = init
        self.app = self.mod.App()
        self.app.on_enter(self.os)

    def parse_items(self):
        p = self.rss.RssParser()
        p.feed(FEED.encode())
        return p.items

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

    def search_and_open(self):
        self.press(self.api.BTN_DOWN, self.api.BTN_A)       # Search
        self.app.kb.text = "badge"
        self.press(self.api.BTN_DOWN, self.api.BTN_DOWN, self.api.BTN_DOWN, self.api.BTN_DOWN)
        for _ in range(4):
            self.press(self.api.BTN_RIGHT)                  # to OK
        self.press(self.api.BTN_A)
        self.assertIn("Badge & Friends", self.os.display.joined())

    def test_search_subscribe_play_seek_resume(self):
        self.search_and_open()
        self.press(self.api.BTN_RIGHT)                      # subscribe
        self.assertEqual(self.app.subs[0]["feed"], "https://f.example/rss")
        self.press(self.api.BTN_A)                          # episodes
        self.assertIn("Ep 3", self.os.display.joined())
        self.press(self.api.BTN_A)                          # play Ep 3
        self.frame(30)
        p = self.app.player
        self.assertEqual(p.state, "playing")
        self.assertTrue(p.can_seek())
        p._start_s += 100.0                                 # pretend 100 s in
        at = p.position_s()
        self.press(self.api.BTN_RIGHT)                      # +30 s
        self.assertIn(b"Range: bytes=%d-" % int((at + 30) * 64 * 125), bytes(self.socks[-1].sent))
        self.frame(30)
        self.assertEqual(p.state, "playing")
        self.assertAlmostEqual(p.position_s(), at + 30, delta=2)
        at = p.position_s()
        self.press(self.api.BTN_LEFT)                       # -15 s
        self.assertIn(b"Range: bytes=%d-" % int((at - 15) * 64 * 125), bytes(self.socks[-1].sent))
        self.frame(30)
        self.app.on_exit()                                  # saves the position
        saved = self.env.state.load("podcasts")
        self.assertEqual(saved["subs"][0]["name"], "Badge & Friends")
        key = self.mod.pos_key("https://cdn.example/ep3.mp3?a=1&b=2")
        pos = [q for q in saved["pos"] if q[0] == key][0]
        self.assertAlmostEqual(pos[1], at - 15, delta=3)
        self.assertEqual(pos[2], 64)
        # a new session resumes with a Range request straight away
        app2 = self.mod.App()
        app2.on_enter(self.os)
        app2.show = {"name": "Badge & Friends", "feed": "https://f.example/rss"}
        app2._play(self.parse_items()[0])
        app2.update(0.05)
        self.assertIn(b"Range: bytes=%d-" % (pos[1] * 64 * 125), bytes(self.socks[-1].sent))
        app2.on_exit()

    def test_cant_seek_message(self):
        self.search_and_open()
        self.press(self.api.BTN_A, self.api.BTN_A)
        self.frame(30)
        self.app.player.seekable = False
        self.press(self.api.BTN_RIGHT)
        self.assertIn("Can't seek on this server", self.os.display.joined())

    def test_subscriptions_list(self):
        self.app.subs = [{"name": "Kept", "author": "", "feed": "https://k/rss"}]
        self.press(self.api.BTN_A)
        self.assertIn("Kept", self.os.display.joined())
        self.press(self.api.BTN_RIGHT)                      # unsubscribe
        self.assertEqual(self.app.subs, [])

    def test_no_speaker(self):
        a, _ = self.env.make_audio(available=False)
        os_ = E.FakeOS(a)
        app = self.mod.App()
        app.on_enter(os_)
        app.subs = [{"name": "S", "feed": "https://k/rss"}]
        app._play({"title": "t", "url": "https://x/y.mp3"})
        app.draw(os_.display)
        self.assertIn("Needs the PCB badge (speaker)", os_.display.joined())
        app.on_exit()


if __name__ == "__main__":
    unittest.main()

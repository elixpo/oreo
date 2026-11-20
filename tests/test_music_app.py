"""Host tests for the Music app (apps_market/music): ID3v2/v1 parsing,
Subsonic token auth and URLs, the folder scan and play queue, the microSD
driver (oreoWare/sdcard.py), and the app on stub modules with a temporary
folder as the card.

    python3 -m unittest tests.test_music_app -v
"""

import io
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import audio_env as E  # noqa: E402


def syncsafe(n):
    return bytes([(n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F])


def frame(ver, fid, payload):
    if ver == 2:
        return fid + len(payload).to_bytes(3, "big") + payload
    size = syncsafe(len(payload)) if ver == 4 else struct.pack(">I", len(payload))
    return fid + size + b"\0\0" + payload


def tag(ver, frames, pad=50):
    body = b"".join(frames) + b"\0" * pad
    return b"ID3" + bytes([ver, 0, 0]) + syncsafe(len(body)) + body


def v1(title, artist, album, track=0):
    def f(s, n):
        return s.encode("latin-1")[:n].ljust(n, b"\0")
    return b"TAG" + f(title, 30) + f(artist, 30) + f(album, 30) + b"2026" + \
        b"\0" * 28 + bytes([0, track, 0])


AUDIO = b"\xff\xfb\x90\x00" + b"\0" * 400


class Id3Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = E.Env(self.tmp.name)
        self.mod = self.env.load_app("apps_market/music", "music")
        self.id3 = self.mod.id3

    def tearDown(self):
        self.env.close()
        self.tmp.cleanup()

    def read(self, data):
        return self.id3.read_tags(io.BytesIO(data))

    def test_v23_with_big_cover_skipped(self):
        apic = frame(3, b"APIC", b"\0image/jpeg\0\3\0" + b"\x88" * 300000)
        t = tag(3, [frame(3, b"TIT2", b"\0Song"), apic, frame(3, b"TPE1", b"\0Band"),
                    frame(3, b"TALB", b"\3Alb\xc3\xbcm"), frame(3, b"TRCK", b"\x003/12")])
        f = io.BytesIO(t + AUDIO)
        reads = []
        orig = f.read
        f.read = lambda n=-1: (reads.append(n), orig(n))[1]
        out = self.id3.read_tags(f)
        self.assertEqual(out, {"title": "Song", "artist": "Band", "album": "Albüm",
                               "track": "3/12"})
        self.assertLess(sum(n for n in reads if n > 0), 2000)    # cover never read

    def test_v24_utf16(self):
        t = tag(4, [frame(4, b"TIT2", b"\1\xff\xfe" + "Café".encode("utf-16-le") + b"\0\0"),
                    frame(4, b"TPE1", b"\2" + "Åsa".encode("utf-16-be")),
                    frame(4, b"TALB", b"\3LP")])
        self.assertEqual(self.read(t + AUDIO), {"title": "Café", "artist": "Åsa",
                                                "album": "LP"})

    def test_v22(self):
        t = tag(2, [frame(2, b"TT2", b"\0Old"), frame(2, b"TP1", b"\0Timer"),
                    frame(2, b"TAL", b"\0Tape")])
        self.assertEqual(self.read(t + AUDIO), {"title": "Old", "artist": "Timer", "album": "Tape"})

    def test_v1_fallback_and_merge(self):
        self.assertEqual(self.read(AUDIO + v1("T1", "A1", "B1", 7)),
                         {"title": "T1", "artist": "A1", "album": "B1", "track": "7"})
        t = tag(3, [frame(3, b"TIT2", b"\0From v2")])
        out = self.read(t + AUDIO + v1("T1", "A1", "B1"))
        self.assertEqual(out["title"], "From v2")
        self.assertEqual(out["artist"], "A1")

    def test_no_tags_and_garbage(self):
        self.assertEqual(self.read(AUDIO), {})
        self.assertEqual(self.read(b"ID3\x03\0\0\x7f\x7f\x7f\x7f" + b"\xff" * 30), {})
        self.assertEqual(self.read(b""), {})

    def test_from_path(self):
        p = Path(self.tmp.name) / "a.mp3"
        p.write_bytes(tag(3, [frame(3, b"TIT2", b"\0P")]) + AUDIO)
        self.assertEqual(self.id3.read_tags(str(p)), {"title": "P"})


class SubsonicTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = E.Env(self.tmp.name)
        self.ss = self.env.load_app("apps_market/music", "music").subsonic

    def tearDown(self):
        self.env.close()
        self.tmp.cleanup()

    def test_token_matches_the_spec_example(self):
        # subsonic.org/pages/api.jsp: password "sesame", salt "c19b2d"
        self.assertEqual(self.ss.token("sesame", "c19b2d"), "26719a1196d2a940705a59634eb18eab")

    def test_credentials_keep_no_password(self):
        c = self.ss.credentials("music.example.org/", "me", "sesame", salt="c19b2d")
        self.assertEqual(c, {"url": "https://music.example.org", "user": "me", "salt": "c19b2d",
                             "token": "26719a1196d2a940705a59634eb18eab"})
        self.assertNotIn("sesame", json.dumps(c))
        s1, s2 = self.ss.new_salt(), self.ss.new_salt()
        self.assertEqual(len(s1), 12)
        self.assertNotEqual(s1, s2)

    def test_urls(self):
        c = self.ss.credentials("http://nas:4533", "me", "sesame", salt="c19b2d")
        u = self.ss.stream_url(c, "so ng/1")
        self.assertTrue(u.startswith("http://nas:4533/rest/stream.view?u=me&t=26719a"))
        for part in ("s=c19b2d", "v=1.16.1", "c=FaleraOS", "f=json", "format=mp3",
                     "maxBitRate=128", "id=so%20ng%2F1"):
            self.assertIn(part, u)
        self.assertNotIn("p=", u)
        self.assertIn("/rest/ping.view?", self.ss.ping_url(c))
        self.assertIn("type=newest", self.ss.albums_url(c))
        self.assertIn("query=a%26b", self.ss.search_url(c, "a&b"))

    def test_parsing(self):
        c = self.ss.credentials("https://s", "me", "x", salt="aa")
        ok = lambda body: json.dumps({"subsonic-response": dict(status="ok", version="1.16.1", **body)})
        self.assertTrue(self.ss.parse_ping(ok({})))
        albums = self.ss.parse_albums(ok({"albumList2": {"album": [
            {"id": "a1", "name": "One", "artist": "X"}]}}))
        self.assertEqual(albums, [{"id": "a1", "name": "One", "artist": "X"}])
        songs = self.ss.parse_album(ok({"album": {"song": [
            {"id": "2", "title": "B", "track": 2, "duration": 100},
            {"id": "1", "title": "A", "track": 1, "artist": "X"},
            {"id": "v", "title": "Clip", "isVideo": True}]}}), c)
        self.assertEqual([s["title"] for s in songs], ["A", "B"])
        self.assertIn("/rest/stream.view?", songs[0]["url"])
        self.assertEqual(len(self.ss.parse_songs(ok({"searchResult3": {"song": [{"id": "3"}]}}), c)), 1)
        self.assertEqual(self.ss.parse_random(ok({"randomSongs": {}}), c), [])
        bad = json.dumps({"subsonic-response": {"status": "failed",
                                                "error": {"code": 40, "message": "Wrong"}}})
        with self.assertRaises(self.ss.SubsonicError) as cm:
            self.ss.parse_ping(bad)
        self.assertEqual(str(cm.exception), "wrong user or password")
        with self.assertRaises(self.ss.SubsonicError):
            self.ss.parse_ping(b"<html>")


class LibraryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = E.Env(self.tmp.name)
        self.lib = self.env.load_app("apps_market/music", "music").library
        root = Path(self.tmp.name) / "sd"
        for p in ("b/2.mp3", "b/1.MP3", "a/x/deep.mp3", "top.mp3", "notes.txt",
                  ".hidden/h.mp3", "a/._junk.mp3"):
            f = root / p
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(b"x")
        self.root = str(root)

    def tearDown(self):
        self.env.close()
        self.tmp.cleanup()

    def test_list_and_scan(self):
        self.assertEqual(self.lib.list_dir(self.root), (["a", "b"], ["top.mp3"]))
        self.assertEqual(self.lib.list_dir(self.root + "/b"), ([], ["1.MP3", "2.mp3"]))
        files = [p[len(self.root):] for p in self.lib.scan(self.root)]
        self.assertEqual(files, ["/top.mp3", "/a/x/deep.mp3", "/b/1.MP3", "/b/2.mp3"])
        self.assertEqual(len(self.lib.scan(self.root, limit=2)), 2)
        self.assertEqual(self.lib.display_name("/sd/x/01 - Song.mp3"), "01 - Song")

    def test_queue_order_repeat_shuffle(self):
        Q = self.lib.Queue
        q = Q(["a", "b", "c"], start=1)
        self.assertEqual(q.current(), "b")
        self.assertEqual(q.next(auto=True), "c")
        self.assertIsNone(q.next(auto=True))            # repeat off: stop at the end
        self.assertEqual(q.next(), "a")                 # a press wraps
        q.repeat = self.lib.REPEAT_ALL
        q.pos = 2
        self.assertEqual(q.next(auto=True), "a")
        q.repeat = self.lib.REPEAT_ONE
        self.assertEqual(q.next(auto=True), "a")
        self.assertEqual(q.next(), "b")                 # a press still moves
        self.assertEqual(q.prev(), "a")
        items = list(range(20))
        q = Q(items, start=5, shuffle=True)
        self.assertEqual(q.current(), 5)                # shuffling keeps the current song
        self.assertEqual(sorted(q.order), items)
        self.assertNotEqual(q.order, items)
        seen = [q.current()] + [q.next(auto=True) for _ in range(19)]
        self.assertEqual(sorted(seen), items)           # every song once
        cur = q.current()
        q.set_shuffle(False)
        self.assertEqual(q.current(), cur)
        self.assertEqual(q.order, items)


class SDCardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = E.Env(self.tmp.name)
        sys.modules["oreoWare.pins"].SD_CLK = 38
        sys.modules["oreoWare.pins"].SD_CMD = 39
        sys.modules["oreoWare.pins"].SD_D0 = 40
        import importlib
        self.sd = importlib.import_module("oreoWare.sdcard")

    def tearDown(self):
        self.env.close()
        self.tmp.cleanup()

    def test_mount_with_card_detect(self):
        made = []

        class Card:
            def __init__(self, **kw):
                made.append(kw)

            def deinit(self):
                made.append("deinit")

        class Vfs:
            mounts = []

            def mount(self, card, path):
                self.mounts.append(path)

            def umount(self, path):
                self.mounts.remove(path)

        class Exp:
            card = False

            def card_present(self):
                return self.card
        exp, vfs = Exp(), Vfs()
        sd = self.sd.SDCard(expander=exp, sdcard_class=Card, vfs_module=vfs)
        self.assertFalse(sd.present())
        self.assertIsNone(sd.mount())
        self.assertEqual(sd.error, "no card")
        self.assertEqual(made, [])
        exp.card = True
        self.assertEqual(sd.mount(), "/sd")
        self.assertEqual(made[0], {"slot": 1, "width": 1, "sck": 38, "cmd": 39, "data": (40,),
                                   "freq": 20_000_000})
        self.assertEqual(vfs.mounts, ["/sd"])
        sd.unmount()
        self.assertEqual(vfs.mounts, [])
        self.assertIn("deinit", made)

    def test_breadboard_unknown_presence(self):
        class Vfs:
            def mount(self, card, path):
                raise OSError("no SD card")
        sd = self.sd.SDCard(sdcard_class=lambda **kw: object(), vfs_module=Vfs())
        self.assertIsNone(sd.present())
        self.assertIsNone(sd.mount())
        self.assertIn("no SD card", sd.error)


class FakeSD:
    def __init__(self, root, present=True):
        self.root = root
        self.card = present
        self.path = None
        self.error = None
        self.mounts = 0

    def present(self):
        return self.card

    def mount(self):
        if not self.card:
            self.error = "no card"
            return None
        self.mounts += 1
        self.path = self.root
        return self.root

    def unmount(self):
        self.path = None


class MusicAppTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = E.Env(self.tmp.name)
        self.mod = self.env.load_app("apps_market/music", "music")
        self.api = self.env.api
        root = Path(self.tmp.name) / "card"
        (root / "Album").mkdir(parents=True)
        pcm = b"\x01\x00" * 3000
        (root / "Album" / "01 first.mp3").write_bytes(
            tag(3, [frame(3, b"TIT2", b"\0First"), frame(3, b"TPE1", b"\0Band"),
                    frame(3, b"TALB", b"\0Record")]) + pcm)
        (root / "Album" / "02 second.mp3").write_bytes(pcm)
        (root / "loose.mp3").write_bytes(pcm)
        self.root = str(root)
        self.audio, self.exp = self.env.make_audio()
        self.os = E.FakeOS(self.audio)
        self.os.sdcard = FakeSD(self.root)
        self.connects = []

        def connect(host, port, tls, timeout):
            self.connects.append((host, port, tls))
            return E.FakeSock(E.http_reply(b"\x01\x00" * 3000, "200 OK", [
                ("Content-Type", "audio/mpeg"), ("Content-Length", "6000")]))
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
        self.frame()

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

    def test_browse_play_folder_with_tags_then_next(self):
        self.start()
        self.assertTrue(self.app.card)
        self.press(self.api.BTN_A)                          # microSD card
        self.assertIn("Album/", self.os.display.joined())
        self.assertEqual(self.app.list.items, ["> Play this folder", "Album/", "loose.mp3"])
        self.press(self.api.BTN_DOWN, self.api.BTN_A)       # into Album
        self.assertEqual(self.app.list.items[1:], ["01 first.mp3", "02 second.mp3"])
        self.press(self.api.BTN_A)                          # play this folder
        self.frame(3)
        txt = self.os.display.joined()
        self.assertIn("First", txt)
        self.assertIn("Band", txt)
        self.assertIn("Record", txt)
        for _ in range(400):
            self.frame()
            if self.app.queue.pos == 1:
                break
        self.assertEqual(self.app.queue.pos, 1)
        self.frame(3)
        self.assertIn("02 second", self.os.display.joined())   # no tags: file name
        self.assertEqual(self.connects, [])
        self.press(self.api.BTN_B, self.api.BTN_B, self.api.BTN_B)
        self.assertEqual(self.app.kind, "home")

    def test_whole_card_shuffle_saved(self):
        self.start()
        self.press(self.api.BTN_DOWN, self.api.BTN_DOWN, self.api.BTN_A)   # Shuffle: on
        self.assertTrue(self.app.shuffle)
        self.press(self.api.BTN_DOWN, self.api.BTN_A)       # Repeat: all
        self.assertEqual(self.app.repeat, 1)
        self.press(self.api.BTN_UP, self.api.BTN_UP, self.api.BTN_A)  # whole card
        self.assertEqual(len(self.app.queue), 3)
        self.assertTrue(self.app.queue.shuffle)
        self.app.on_exit()
        saved = self.env.state.load("music")
        self.assertEqual((saved["shuffle"], saved["repeat"]), (True, 1))

    def test_no_card(self):
        self.os.sdcard = FakeSD(self.root, present=False)
        self.start()
        self.press(self.api.BTN_A)
        self.assertIn("No microSD card", self.os.display.joined())
        self.os.sdcard.card = True
        self.frame(25)                                      # card detect notices
        self.assertTrue(self.app.card)

    def test_card_removed_while_playing(self):
        self.start()
        self.app._play_files([self.root + "/loose.mp3"], 0)
        self.frame(3)
        self.os.sdcard.card = False
        self.frame(25)
        self.assertFalse(self.app.card)
        self.assertEqual(self.app.player.state, "idle")

    def test_subsonic_settings_and_play(self):
        ss = self.mod.subsonic
        calls = []

        def fetch(url, get=None):
            calls.append(url)
            base = {"status": "ok", "version": "1.16.1"}
            if "/rest/ping.view" in url:
                return json.dumps({"subsonic-response": base}).encode()
            if "getAlbumList2" in url:
                base["albumList2"] = {"album": [{"id": "al", "name": "Disc", "artist": "S"}]}
            else:
                base["album"] = {"song": [{"id": "s1", "title": "Tune", "artist": "S",
                                           "album": "Disc", "track": 1}]}
            return json.dumps({"subsonic-response": base}).encode()
        ss.fetch = fetch
        self.start()
        # Server settings is the last home row
        self.app.list.sel = len(self.app.list.items) - 1
        self.press(self.api.BTN_A)
        self.assertEqual(self.app.view, "keyboard")
        for value in ("http://nas.example:4533", "me", "sesame"):
            self.app.kb.text = value
            self.app._kb("ok")
            self.frame()
        self.assertEqual(self.app.cred["user"], "me")
        self.assertNotIn("sesame", json.dumps(self.env.state.load("music")))
        self.assertEqual(self.app.cred["token"], ss.token("sesame", self.app.cred["salt"]))
        self.assertIn("Server OK", self.os.display.joined())
        self.app.list.sel = [k for k, _ in self.app.list.items].index("server")
        self.press(self.api.BTN_A, self.api.BTN_A)          # My server > Newest albums
        self.assertIn("Disc - S", self.os.display.joined())
        self.press(self.api.BTN_A, self.api.BTN_A)          # album > first song
        self.frame(3)
        self.assertEqual(self.connects[0], ("nas.example", 4533, False))
        self.assertIn("Tune", self.os.display.joined())

    def test_no_speaker(self):
        a, _ = self.env.make_audio(available=False)
        os_ = E.FakeOS(a)
        app = self.mod.App()
        app.on_enter(os_)
        app.draw(os_.display)
        self.assertIn("Needs the PCB badge (speaker)", os_.display.joined())
        app.on_exit()


if __name__ == "__main__":
    unittest.main()

"""Host tests for the audio stack: the ring buffer and I2S driver
(oreoWare/audio.py), and the streaming player (oreoOS/player.py): ICY
metadata, playlists, redirects, buffering, stalls and seeking, against
fake streams and a fake decoder (tests/audio_env.py).

    python3 -m unittest tests.test_audio_player -v
"""

import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import audio_env as E  # noqa: E402


class EnvCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = E.Env(self.tmp.name)
        self.A = self.env.audio
        self.P = self.env.player

    def tearDown(self):
        self.env.close()
        self.tmp.cleanup()


class RingTest(EnvCase):
    def test_wraps_and_keeps_order(self):
        r = self.A.Ring(10)
        self.assertEqual(r.write(b"abcdefgh"), 8)
        out = bytearray(5)
        self.assertEqual(r.read_into(out), 5)
        self.assertEqual(bytes(out), b"abcde")
        self.assertEqual(r.write(b"123456789"), 7)      # only 7 free
        self.assertEqual(r.free(), 0)
        out = bytearray(10)
        self.assertEqual(r.read_into(out), 10)
        self.assertEqual(bytes(out), b"fgh1234567")
        self.assertEqual(r.used(), 0)

    def test_full_and_empty_differ(self):
        r = self.A.Ring(4)
        r.write(b"wxyz")
        self.assertEqual((r.used(), r.free()), (4, 0))
        r.clear()
        self.assertEqual((r.used(), r.free()), (0, 4))

    def test_many_cycles(self):
        r = self.A.Ring(7)
        got = bytearray()
        src = bytes(range(256)) * 4
        i = 0
        buf = bytearray(3)
        while len(got) < len(src):
            i += r.write(src[i:i + 5])
            n = r.read_into(buf)
            got.extend(buf[:n])
        self.assertEqual(bytes(got), src)


def _pcm(*samples):
    return struct.pack("<%dh" % len(samples), *samples)


class AudioDriverTest(EnvCase):
    def test_breadboard_is_a_no_op(self):
        a, exp = self.env.make_audio(available=False)
        self.assertFalse(a.start(22050))
        self.assertEqual(a.write(b"\0\0" * 10), 0)
        a.stop()
        self.assertEqual(exp.log, [])
        self.assertEqual(E.FakeI2S.instances, [])

    def test_available_follows_board(self):
        self.assertTrue(self.A.Audio(expander=E.FakeExpander()).available)
        self.env.close()
        self.env = E.Env(self.tmp.name, board="breadboard")
        self.assertFalse(self.env.audio.Audio().available)

    def test_start_sends_silence_before_amp(self):
        a, exp = self.env.make_audio()
        a.start(22050)
        i2s = E.FakeI2S.instances[-1]
        self.assertEqual(i2s.args["rate"], 22050)
        self.assertEqual(i2s.args["bits"], 16)
        self.assertEqual(i2s.args["format"], E.FakeI2S.MONO)
        self.assertEqual((i2s.args["sck"], i2s.args["ws"], i2s.args["sd"]), (8, 9, 10))
        self.assertFalse(exp.amp)                       # silence first
        self.assertEqual(set(i2s.writes[0]), {0})
        i2s.fire(2)
        self.assertTrue(exp.amp)
        self.assertEqual(a.state, self.A.RUNNING)

    def test_write_is_non_blocking_and_plays_in_order(self):
        a, exp = self.env.make_audio()
        a.volume = 100
        a.start(22050)
        i2s = E.FakeI2S.instances[-1]
        i2s.fire(2)
        data = _pcm(*range(1, 2049)) * 1
        self.assertEqual(a.write(data), len(data))
        full = bytes(self.A.RING_BYTES)
        self.assertLess(a.write(full), len(full))       # takes what fits, returns
        self.assertEqual(a.free(), 0)
        i2s.writes.clear()
        i2s.fire(2)
        # first chunk is faded in, second is untouched
        second = struct.unpack("<1024h", i2s.writes[1])
        self.assertEqual(second[0], 1025)
        first = struct.unpack("<1024h", i2s.writes[0])
        self.assertEqual(first[0], 0)                   # fade starts at zero
        self.assertEqual(first[-1], 1024 * 7 // 8)      # last fade step

    def test_underrun_sends_silence(self):
        a, _ = self.env.make_audio()
        a.start(22050)
        i2s = E.FakeI2S.instances[-1]
        i2s.fire(2)
        a.write(_pcm(5000) * 10)
        i2s.writes.clear()
        i2s.fire(2)
        self.assertEqual(a.underruns, 1)
        self.assertEqual(set(i2s.writes[1]), {0})       # nothing queued: zeros

    def test_volume_scales_samples(self):
        a, _ = self.env.make_audio()
        a.volume = 50
        self.assertEqual(self.A.gain_q16(50), 16384)
        self.assertEqual(self.A.gain_q16(100), 65536)
        self.assertEqual(self.A.gain_q16(0), 0)
        a.start(22050)
        i2s = E.FakeI2S.instances[-1]
        i2s.fire(2)
        a.write(_pcm(*([8000] * 1024)) * 2)
        i2s.writes.clear()
        i2s.fire(2)
        self.assertEqual(struct.unpack("<1024h", i2s.writes[1])[0], 2000)

    def test_stop_fades_drains_then_amp_off(self):
        a, exp = self.env.make_audio()
        a.volume = 100
        a.start(22050)
        i2s = E.FakeI2S.instances[-1]
        i2s.fire(2)
        a.write(_pcm(*([10000] * 1024)) * 4)
        i2s.fire(1)
        a.stop()
        self.assertEqual(a.buffered(), 0)
        self.assertTrue(exp.amp)                        # still draining
        i2s.writes.clear()
        n = 0
        while a.state != self.A.STOPPED and n < 50:
            i2s.fire()
            n += 1
        self.assertFalse(exp.amp)
        self.assertTrue(i2s.closed)
        faded = struct.unpack("<1024h", i2s.writes[0])
        self.assertEqual(faded[0], 10000)
        self.assertLess(abs(faded[-1]), 10000 // 8 + 1)
        for w in i2s.writes[1:]:
            self.assertEqual(set(w), {0})
        # enough silence to flush the DMA buffers before the amp went off
        self.assertGreaterEqual(len(i2s.writes) - 1, self.A.IBUF // self.A.CHUNK)

    def test_rate_change_waits_for_queue(self):
        a, exp = self.env.make_audio()
        a.start(22050)
        i2s = E.FakeI2S.instances[-1]
        i2s.fire(2)
        a.write(_pcm(1) * 100, 22050)
        self.assertEqual(a.write(_pcm(2) * 100, 44100), 0)   # old samples first
        i2s.fire()                                      # plays them
        i2s.fire()                                      # queue empty: switch
        new = E.FakeI2S.instances[-1]
        self.assertIsNot(new, i2s)
        self.assertTrue(i2s.closed)
        self.assertEqual(new.args["rate"], 44100)
        self.assertEqual(a.write(_pcm(2) * 100, 44100), 200)
        with self.assertRaises(ValueError):
            a.set_rate(12345)

    def test_rate_before_start_applies_at_once(self):
        a, _ = self.env.make_audio()
        self.assertEqual(a.write(_pcm(3) * 10, 44100), 20)
        a.start()
        self.assertEqual(E.FakeI2S.instances[-1].args["rate"], 44100)


class IcyTest(EnvCase):
    def test_title_parsing(self):
        t = self.P.parse_stream_title
        self.assertEqual(t(b"StreamTitle='Artist - Song';StreamUrl='';\0\0\0"), "Artist - Song")
        self.assertEqual(t(b"StreamTitle='Rock 'n' Roll';"), "Rock 'n' Roll")
        self.assertEqual(t(b"StreamTitle='';"), "")
        self.assertIsNone(t(b"StreamUrl='x';"))
        self.assertEqual(t("StreamTitle='Café'".encode("utf-8")), "Café")

    def _icy_stream(self, metaint, audio, titles):
        out = bytearray()
        i = 0
        k = 0
        while i < len(audio):
            out += audio[i:i + metaint]
            i += metaint
            if i <= len(audio):
                if k < len(titles):
                    m = ("StreamTitle='%s';" % titles[k]).encode()
                    m += b"\0" * (-len(m) % 16)
                    out.append(len(m) // 16)
                    out += m
                else:
                    out.append(0)
                k += 1
        return bytes(out)

    def test_demux_any_chunking(self):
        audio = bytes((i * 7) & 0xFF for i in range(5000))
        stream = self._icy_stream(1000, audio, ["One", "Two", "Three"])
        for piece in (1, 7, 999, 1000, 1001, 4096):
            seen = []
            d = self.P.IcyDemux(1000, seen.append)
            got = bytearray()
            for i in range(0, len(stream), piece):
                chunk = stream[i:i + piece]
                for a, b in d.feed(chunk, len(chunk)):
                    got += chunk[a:b]
            self.assertEqual(bytes(got), audio, piece)
            self.assertEqual(seen, ["One", "Two", "Three"], piece)

    def test_no_metaint_passes_through(self):
        d = self.P.IcyDemux(0)
        self.assertEqual(d.feed(b"abc", 3), [(0, 3)])


class Id3SkipTest(EnvCase):
    def tag(self, body_len, footer=False):
        n = body_len
        size = bytes([(n >> 21) & 0x7F, (n >> 14) & 0x7F, (n >> 7) & 0x7F, n & 0x7F])
        return b"ID3\x04\x00" + bytes([0x10 if footer else 0]) + size + b"T" * n + \
            (b"3DI" + b"\0" * 7 if footer else b"")

    def test_size(self):
        self.assertEqual(self.P.id3_size(self.tag(300)[:10]), 310)
        self.assertEqual(self.P.id3_size(self.tag(300, True)[:10]), 320)
        self.assertEqual(self.P.id3_size(b"\xff\xfb\x90\x00" + b"\0" * 6), 0)

    def test_tag_never_reaches_the_decoder(self):
        audio = bytes(range(200)) * 10
        for footer in (False, True):
            for piece in (1, 3, 10, 11, 500, 5000):
                data = self.tag(3000, footer) + audio
                s = self.P.Session(self.P.Player(None, threaded=False), "x")
                s.demux = self.P.IcyDemux(0)
                for i in range(0, len(data), piece):
                    c = data[i:i + piece]
                    s._push(c, len(c))
                out = bytearray(s.ring.used())
                s.ring.read_into(out)
                self.assertEqual(bytes(out), audio, (footer, piece))

    def test_untagged_data_unchanged(self):
        audio = b"\xff\xfb" + bytes(range(250)) * 4
        for piece in (1, 4, 9, 1000):
            s = self.P.Session(self.P.Player(None, threaded=False), "x")
            s.demux = self.P.IcyDemux(0)
            for i in range(0, len(audio), piece):
                c = audio[i:i + piece]
                s._push(c, len(c))
            out = bytearray(s.ring.used())
            s.ring.read_into(out)
            self.assertEqual(bytes(out), audio, piece)


class UrlPlaylistTest(EnvCase):
    def test_split_and_join(self):
        s = self.P.split_url
        self.assertEqual(s("http://a.b/x.mp3"), (False, "a.b", 80, "/x.mp3"))
        self.assertEqual(s("https://a.b:8443"), (True, "a.b", 8443, "/"))
        with self.assertRaises(self.P.StreamError):
            s("ftp://x")
        j = self.P.join_url
        self.assertEqual(j("http://a.b/x/y.pls", "/z"), "http://a.b/z")
        self.assertEqual(j("http://a.b:81/x/y.pls", "z.mp3"), "http://a.b:81/x/z.mp3")
        self.assertEqual(j("http://a.b/x", "https://c.d/e"), "https://c.d/e")
        self.assertEqual(j("https://a.b/x", "//c.d/e"), "https://c.d/e")

    def test_pls_and_m3u(self):
        pls = b"[playlist]\nNumberOfEntries=2\nFile1=http://s1.example/live\nTitle1=One\nFile2=http://s2.example/\n"
        self.assertEqual(self.P.parse_playlist(pls), "http://s1.example/live")
        m3u = "#EXTM3U\n#EXTINF:-1,Station\nhttps://s.example/stream.mp3\nhttp://other/\n"
        self.assertEqual(self.P.parse_playlist(m3u), "https://s.example/stream.mp3")
        self.assertIsNone(self.P.parse_playlist(b"#EXTM3U\n"))
        with self.assertRaises(self.P.StreamError):
            self.P.parse_playlist("#EXTM3U\n#EXT-X-TARGETDURATION:10\nseg1.ts\n")

    def test_is_playlist(self):
        self.assertTrue(self.P.is_playlist("http://a/b.pls", ""))
        self.assertTrue(self.P.is_playlist("http://a/b", "audio/x-mpegurl"))
        self.assertFalse(self.P.is_playlist("http://a/b.m3u", "audio/mpeg"))

    def test_head_parsing_icy(self):
        st, h = self.P.parse_head(b"ICY 200 OK\r\nicy-metaint: 8192\r\nicy-name: X")
        self.assertEqual(st, 200)
        self.assertEqual(h["icy-metaint"], "8192")


class PlayerTest(EnvCase):
    def make(self, replies, hz=22050):
        self.audio, self.exp = self.env.make_audio()
        self.net = E.FakeNet(replies)
        self.decs = []

        def dec():
            d = E.FakeDecoder(hz)
            self.decs.append(d)
            return d
        p = self.P.Player(self.audio, connect=self.net, decoder=dec, threaded=False)
        return p

    def run_until(self, p, cond, limit=500, fire=True):
        for _ in range(limit):
            p.update()
            if fire and E.FakeI2S.instances and not E.FakeI2S.instances[-1].closed:
                E.FakeI2S.instances[-1].fire()
            if cond():
                return True
        return False

    def test_icy_stream_plays_with_title(self):
        audio = _pcm(*([1234] * 20000))
        body = IcyTest._icy_stream(None, 4000, audio, ["Band - Tune"])
        sock = E.FakeSock(E.http_reply(body, "200 OK", [("Content-Type", "audio/mpeg"),
                                                        ("icy-metaint", "4000"),
                                                        ("icy-name", "Test FM")]), hang=True)
        p = self.make({"radio.example": [sock]})
        p.play("http://radio.example/live")
        self.assertEqual(p.state, "connecting")
        self.assertTrue(self.run_until(p, lambda: p.state == "playing"))
        self.assertTrue(self.run_until(p, lambda: p.title == "Band - Tune"))
        self.assertTrue(self.audio.started)
        self.assertTrue(self.run_until(p, lambda: self.exp.amp))
        req = bytes(sock.sent)
        self.assertIn(b"Icy-MetaData: 1\r\n", req)
        self.assertIn(b"GET /live HTTP/1.0", req)
        self.assertIn(b"User-Agent: FaleraOS", req)
        self.assertEqual(p.station_name, "Test FM")
        # samples reached I2S unchanged (volume 70: gain applied)
        i2s = E.FakeI2S.instances[-1]
        played = [w for w in i2s.writes if any(w)]
        self.assertTrue(played)
        p.stop()
        self.assertEqual(p.state, "idle")
        self.assertTrue(sock.closed)

    def test_redirect_then_playlist(self):
        pls = b"[playlist]\nFile1=https://cdn.example/stream\n"
        r1 = E.FakeSock(E.http_reply(b"", "302 Found", [("Location", "/list.pls")]))
        r2 = E.FakeSock(E.http_reply(pls, "200 OK", [("Content-Type", "audio/x-scpls")]))
        r3 = E.FakeSock(E.http_reply(_pcm(*([7] * 30000)), "200 OK",
                                     [("Content-Type", "audio/mpeg"), ("icy-br", "64")]),
                        hang=True)
        p = self.make({"a.example": [r1, r2], "cdn.example": [r3]})
        p.play("http://a.example/start")
        self.assertTrue(self.run_until(p, lambda: p.state == "playing"))
        self.assertEqual(self.net.calls, [("a.example", 80, False), ("a.example", 80, False),
                                          ("cdn.example", 443, True)])
        self.assertIn(b"GET /list.pls ", bytes(r2.sent))

    def test_errors_are_reported(self):
        html = E.FakeSock(E.http_reply(b"<html>", "200 OK", [("Content-Type", "text/html")]))
        p = self.make({"x.example": [html]})
        p.play("http://x.example/")
        self.assertTrue(self.run_until(p, lambda: p.state == "error"))
        self.assertEqual(p.error, "not an audio stream")
        aac = E.FakeSock(E.http_reply(b"", "200 OK", [("Content-Type", "audio/aac")]))
        p = self.make({"x.example": [aac]})
        p.play("http://x.example/")
        self.assertTrue(self.run_until(p, lambda: p.state == "error", limit=5000))
        self.assertIn("MP3 only", p.error)

    def test_stall_reconnects_live_stream(self):
        clock = [0]
        self.P._ticks_ms = lambda: clock[0]
        self.P._sleep_ms = lambda ms: None
        first = E.FakeSock(E.http_reply(_pcm(*([9] * 12000)), "200 OK",
                                        [("Content-Type", "audio/mpeg"), ("icy-metaint", "0"),
                                         ("icy-name", "S")]), hang=True)
        second = E.FakeSock(E.http_reply(_pcm(*([9] * 12000)), "200 OK",
                                         [("Content-Type", "audio/mpeg"), ("icy-name", "S")]),
                            hang=True)
        p = self.make({"s.example": [first, second]})
        p.play("http://s.example/")
        self.assertTrue(self.run_until(p, lambda: p.state == "playing"))
        # the server goes quiet: after STALL_MS the player reconnects
        self.assertTrue(self.run_until(p, lambda: not first.data))
        clock[0] += self.P.STALL_MS + 1
        self.assertTrue(self.run_until(p, lambda: first.closed, limit=50))
        self.assertEqual(p.state, "connecting")
        self.assertEqual(p.error, "stream stalled")
        clock[0] += 5000                                # past the retry delay
        self.assertTrue(self.run_until(p, lambda: len(self.net.calls) == 2, limit=50))
        self.assertTrue(self.run_until(p, lambda: p.state in ("buffering", "playing")))

    def test_gives_up_after_retries(self):
        self.P._sleep_ms = lambda ms: None
        clock = [0]
        self.P._ticks_ms = lambda: clock[0]
        p = self.make({"down.example": [OSError(113)] * 10})
        p.play("http://down.example/")
        for _ in range(200):
            clock[0] += 1000
            p.update()
            if p.state == "error":
                break
        self.assertEqual(p.state, "error")
        self.assertEqual(len(self.net.calls), self.P.MAX_RETRIES + 1)

    def test_file_like_stream_ends(self):
        data = _pcm(*([3] * 5000))
        sock = E.FakeSock(E.http_reply(data, "200 OK", [("Content-Type", "audio/mpeg"),
                                                        ("Content-Length", str(len(data))),
                                                        ("Accept-Ranges", "bytes")]))
        p = self.make({"pod.example": [sock]})
        p.play("https://pod.example/ep.mp3")
        self.assertTrue(self.run_until(p, lambda: p.state == "ended", limit=3000))
        self.assertTrue(p.seekable)
        self.assertEqual(p.length, len(data))
        self.assertTrue(self.run_until(p, lambda: self.audio.state == self.A.STOPPED,
                                       limit=100))
        self.assertFalse(self.exp.amp)

    def test_seek_uses_range(self):
        data = _pcm(*([3] * 40000))
        total = 10 * 64 * 125            # 10 s at 64 kb/s
        s1 = E.FakeSock(E.http_reply(data, "200 OK", [("Content-Type", "audio/mpeg"),
                                                      ("Content-Length", str(total)),
                                                      ("Accept-Ranges", "bytes")]), hang=True)
        s2 = E.FakeSock(E.http_reply(data, "206 Partial Content",
                                     [("Content-Type", "audio/mpeg"),
                                      ("Content-Range", "bytes 48000-79999/%d" % total)]),
                        hang=True)
        p = self.make({"pod.example": [s1, s2]})
        p.play("https://pod.example/ep.mp3")
        self.assertTrue(self.run_until(p, lambda: p.state == "playing"))
        self.assertEqual(p.bitrate, 64)
        self.assertTrue(p.can_seek())
        p._start_s, p._played = 0.0, 0        # pretend we are at 0 s
        self.assertTrue(p.seek(6))
        self.assertTrue(self.run_until(p, lambda: p.state == "playing"))
        self.assertIn(b"Range: bytes=48000-\r\n", bytes(s2.sent))
        self.assertTrue(p.seekable)
        self.assertAlmostEqual(p.duration_s(), 10.0)

    def test_server_without_range_cannot_seek(self):
        s1 = E.FakeSock(E.http_reply(_pcm(*([1] * 20000)), "200 OK",
                                     [("Content-Type", "audio/mpeg"),
                                      ("Content-Length", "999999")]), hang=True)
        p = self.make({"pod.example": [s1]})
        p.play("https://pod.example/ep.mp3")
        self.assertTrue(self.run_until(p, lambda: p.state == "playing"))
        self.assertFalse(p.can_seek())
        self.assertFalse(p.seek(30))

    def test_plays_a_file(self):
        path = Path(self.tmp.name) / "song.mp3"
        path.write_bytes(_pcm(*([4] * 6000)))
        p = self.make({})
        p.play(str(path))
        self.assertTrue(self.run_until(p, lambda: p.state == "ended", limit=3000))
        self.assertTrue(p.seekable)
        self.assertEqual(self.net.calls, [])

    def test_needs_speaker(self):
        a, _ = self.env.make_audio(available=False)
        p = self.P.Player(a, threaded=False)
        self.assertFalse(p.play("http://x/"))
        self.assertEqual(p.state, "error")
        self.assertIn("PCB", p.error)


if __name__ == "__main__":
    unittest.main()

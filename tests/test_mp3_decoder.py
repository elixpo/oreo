"""Host test for the firmware's MP3 decoder (firmware/usermods/oreo_audio).

Builds mp3_core.c (minimp3 plus the streaming wrapper the firmware module
calls) with the host's C compiler, makes short MP3s with ffmpeg, decodes
them in random-sized chunks and compares the result with ffmpeg's own
decode. Skipped when cc or ffmpeg (with libmp3lame) is missing.
"""

import array
import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOD = ROOT / "firmware" / "usermods" / "oreo_audio"
HARNESS = ROOT / "tests" / "mp3_harness.c"

CC = shutil.which(os.environ.get("CC", "cc")) or shutil.which("gcc")
FFMPEG = shutil.which("ffmpeg")


def _has_lame():
    if not FFMPEG:
        return False
    out = subprocess.run([FFMPEG, "-hide_banner", "-encoders"],
                         capture_output=True, text=True).stdout
    return "libmp3lame" in out


def _pcm(path):
    a = array.array("h")
    with open(path, "rb") as f:
        a.frombytes(f.read())
    if sys.byteorder == "big":
        a.byteswap()
    return a


def _onset(x, level=2000):
    for i, v in enumerate(x):
        if abs(v) >= level:
            return i
    return -1


def _align(ours, ref):
    """Offset d with ours[i + d] ~ ref[i]: the onsets give a first guess
    (minimp3 also outputs the encoder delay and the LAME info frame, which
    ffmpeg skips), refined by the smallest squared error nearby."""
    guess = _onset(ours) - _onset(ref)
    best, best_err = guess, None
    start = _onset(ref) + 200
    n = 2000
    for d in range(guess - 64, guess + 65):
        if start + d < 0 or start + d + n > len(ours) or start + n > len(ref):
            continue
        err = 0
        for i in range(start, start + n, 2):
            e = ours[i + d] - ref[i]
            err += e * e
        if best_err is None or err < best_err:
            best, best_err = d, err
    return best


def _snr_db(ours, ref, d, skip=300, tail=1200):
    sig = noise = 0
    end = min(len(ref), len(ours) - d) - tail
    for i in range(_onset(ref) + skip, end):
        r = ref[i]
        e = ours[i + d] - r
        sig += r * r
        noise += e * e
    if noise == 0:
        return 200.0, end
    return 10 * math.log10(sig / noise), end


@unittest.skipUnless(CC and _has_lame(), "needs cc and ffmpeg with libmp3lame")
class Mp3DecoderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        cls.exe = cls.dir / "mp3_harness"
        subprocess.run(
            [CC, "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
             "-I", str(MOD), str(HARNESS), str(MOD / "mp3_core.c"),
             "-o", str(cls.exe), "-lm"],
            check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _ffmpeg(self, *args):
        subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y"]
                       + list(args), check=True)

    def _decode(self, mp3, seed):
        out = self.dir / ("ours_%d.pcm" % seed)
        res = subprocess.run([str(self.exe), str(mp3), str(out), str(seed)],
                             capture_output=True, text=True, check=True)
        hz, ch, samples, frames, skipped = (int(v) for v in res.stdout.split())
        return _pcm(out), hz, ch, samples, frames, skipped

    def test_mono_22050_64k_matches_ffmpeg(self):
        mp3 = self.dir / "sine22.mp3"
        self._ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:sample_rate=22050:duration=1",
                     "-ac", "1", "-c:a", "libmp3lame", "-b:a", "64k", str(mp3))
        ref_path = self.dir / "ref22.pcm"
        self._ffmpeg("-i", str(mp3), "-f", "s16le", "-ac", "1", str(ref_path))
        ref = _pcm(ref_path)
        for seed in (1, 7, 1234):
            ours, hz, ch, samples, frames, _ = self._decode(mp3, seed)
            self.assertEqual((hz, ch), (22050, 1))
            self.assertEqual(samples, len(ours))
            self.assertGreater(frames, 30)          # 576 samples per MPEG-2 frame
            d = _align(ours, ref)
            self.assertGreaterEqual(d, 0)
            self.assertLess(d, 3000)
            snr, _ = _snr_db(ours, ref, d)
            self.assertGreater(snr, 40.0, "seed %d: SNR %.1f dB" % (seed, snr))
            if seed == 1:
                first = ours
            else:
                self.assertEqual(ours, first)       # chunking never changes output

    def test_stereo_44100_downmixed(self):
        mp3 = self.dir / "st44.mp3"
        self._ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=1",
                     "-f", "lavfi", "-i", "sine=frequency=660:sample_rate=44100:duration=1",
                     "-filter_complex", "[0:a][1:a]amerge=inputs=2[a]", "-map", "[a]",
                     "-c:a", "libmp3lame", "-b:a", "128k", str(mp3))
        st_path = self.dir / "ref44.pcm"
        self._ffmpeg("-i", str(mp3), "-f", "s16le", "-ac", "2", str(st_path))
        st = _pcm(st_path)
        ref = array.array("h", ((st[i] + st[i + 1]) >> 1 for i in range(0, len(st) - 1, 2)))
        ours, hz, ch, samples, frames, _ = self._decode(mp3, 99)
        self.assertEqual((hz, ch), (44100, 2))
        d = _align(ours, ref)
        snr, _ = _snr_db(ours, ref, d)
        self.assertGreater(snr, 40.0, "SNR %.1f dB" % snr)

    def test_garbage_before_and_inside_stream(self):
        """A stream joined mid-frame, and a dropped chunk, resync."""
        mp3 = self.dir / "sine22b.mp3"
        self._ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:sample_rate=22050:duration=2",
                     "-ac", "1", "-c:a", "libmp3lame", "-b:a", "64k", str(mp3))
        data = mp3.read_bytes()
        cut = self.dir / "cut.mp3"
        # Start 1000 bytes in (mid-frame) and lose 700 bytes in the middle.
        mid = len(data) // 2
        cut.write_bytes(data[1000:mid] + data[mid + 700:])
        ours, hz, ch, samples, frames, skipped = self._decode(cut, 5)
        self.assertEqual(hz, 22050)
        self.assertGreater(skipped, 0)
        # Nearly all of the 2 s survive: only the damaged frames are lost.
        self.assertGreater(samples, int(22050 * 1.6))

    def test_benchmark_runs(self):
        mp3 = self.dir / "bench.mp3"
        self._ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=2",
                     "-ac", "2", "-c:a", "libmp3lame", "-b:a", "128k", str(mp3))
        res = subprocess.run([str(self.exe), "--bench", str(mp3), "3"],
                             capture_output=True, text=True, check=True)
        audio_s, cpu_s = (float(v) for v in res.stdout.split())
        self.assertGreater(audio_s, 5.0)
        self.assertLess(cpu_s, audio_s)          # faster than real time on any host


if __name__ == "__main__":
    unittest.main()

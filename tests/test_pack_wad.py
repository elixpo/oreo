"""Tests for tools/pack_wad.py: WAD -> OWZ round trip."""

import importlib.util
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_packer():
    spec = importlib.util.spec_from_file_location("oreo_pack_wad_under_test", ROOT / "tools/pack_wad.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_wad(lumps, ident=b"IWAD"):
    """Build a minimal WAD: header, lump data, directory."""
    body = bytearray()
    entries = []
    for name, content in lumps:
        entries.append((12 + len(body), len(content), name))
        body += content
    directory = b"".join(struct.pack("<ii8s", off, size, name.encode().ljust(8, b"\0"))
                         for off, size, name in entries)
    return struct.pack("<4sii", ident, len(lumps), 12 + len(body)) + bytes(body) + directory


LUMPS = [
    ("PLAYPAL", bytes(range(256)) * 3),
    ("E1M1", b""),                           # map marker: zero size, position matters
    ("THINGS", b"\x01\x02" * 400),
    ("DSPISTOL", b"\x80" * 500),             # sound effect: dropped by default
    ("D_E1M1", b"MUS\x1a" + b"\x00" * 200),  # music: dropped by default
    ("GENMIDI", b"#OPL_II#" + b"\x00" * 50),
    ("TITLEPIC", bytes(i % 7 for i in range(4000))),
    ("TINY", b"x"),                          # does not compress: stored as is
]


class PackWadTest(unittest.TestCase):
    def setUp(self):
        self.packer = load_packer()

    def test_round_trip_keeps_order_and_content(self):
        ident, lumps = self.packer.read_wad(make_wad(LUMPS))
        owz = self.packer.pack(ident, lumps)
        self.assertEqual(self.packer.unpack(owz), (b"IWAD", LUMPS))

    def test_audio_is_detected(self):
        names = [n for n, _ in LUMPS if self.packer.is_audio(n)]
        self.assertEqual(names, ["DSPISTOL", "D_E1M1", "GENMIDI"])

    def test_audio_is_emptied_but_names_and_order_survive(self):
        _, lumps = self.packer.read_wad(make_wad(LUMPS))
        _, back = self.packer.unpack(self.packer.pack(b"IWAD", self.packer.strip_audio(lumps)))
        self.assertEqual([n for n, _ in back], [n for n, _ in LUMPS])
        self.assertEqual(dict(back)["D_E1M1"], b"")       # music is looked up by name
        self.assertEqual(dict(back)["DSPISTOL"], b"")
        self.assertEqual(dict(back)["THINGS"], dict(LUMPS)["THINGS"])
        self.assertEqual(back[1], ("E1M1", b""))

    def test_compresses_and_stores_incompressible_lumps(self):
        owz = self.packer.pack(b"IWAD", LUMPS)
        self.assertLess(len(owz), len(make_wad(LUMPS)))
        _, count, dir_offset = struct.unpack_from("<4sII", owz, 4)
        entries = [struct.unpack_from("<8sIII", owz, dir_offset + 20 * i) for i in range(count)]
        tiny = [e for e in entries if e[0].rstrip(b"\0") == b"TINY"][0]
        self.assertEqual(tiny[1], tiny[3])   # stored size == raw size: not compressed

    def test_keep_episodes_drops_maps_and_retargets_demos(self):
        demo = lambda e, m: bytes([109, 2, e, m]) + b"\x00" * 20
        lumps = [
            ("E1M1", b""), ("THINGS", b"a"), ("SECTORS", b"b"),
            ("E2M1", b""), ("THINGS", b"c"), ("SECTORS", b"d"),
            ("DEMO1", demo(1, 6)), ("DEMO2", demo(2, 4)),
            ("TITLEPIC", b"t"),
        ]
        kept = self.packer.keep_episodes(lumps, {1})
        self.assertEqual([n for n, _ in kept],
                         ["E1M1", "THINGS", "SECTORS", "DEMO1", "DEMO2", "TITLEPIC"])
        self.assertEqual(dict(kept)["THINGS"], b"a")
        self.assertEqual(dict(kept)["DEMO2"], demo(1, 6))
        with self.assertRaises(self.packer.PackError):
            self.packer.keep_episodes([("DEMO1", demo(2, 1))], {1})

    def test_rejects_bad_input(self):
        with self.assertRaises(self.packer.PackError):
            self.packer.read_wad(b"PWAX" + b"\0" * 8)
        with self.assertRaises(self.packer.PackError):
            self.packer.unpack(b"OWZ0" + b"\0" * 12)
        owz = bytearray(self.packer.pack(b"IWAD", LUMPS))
        owz[-1] ^= 0xFF   # corrupt the directory
        with self.assertRaises(Exception):
            self.packer.unpack(bytes(owz))


if __name__ == "__main__":
    unittest.main()

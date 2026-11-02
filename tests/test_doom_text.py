"""Tests for tools/doom_text.py: Doom patch codec and text restyling."""

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))


def load():
    spec = importlib.util.spec_from_file_location("oreo_doom_text_under_test", ROOT / "tools/doom_text.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Greys 0..255 in steps of 1, so luminance(i) == i.
PALETTE = bytes(v for i in range(256) for v in (i, i, i))


class DoomTextTest(unittest.TestCase):
    def setUp(self):
        self.t = load()

    def test_font_covers_the_heads_up_range(self):
        self.assertEqual(sorted(self.t.FONT), [chr(c) for c in range(33, 96)])
        for ch, glyph in self.t.FONT.items():
            rows = glyph.split()
            self.assertEqual(len(rows), 7, ch)
            self.assertEqual(len({len(r) for r in rows}), 1, ch)

    def test_patch_round_trip_with_gaps(self):
        rows = [[None, 5, None], [7, None, None], [None, 9, 200]]
        left, top, back = self.t.decode_patch(self.t.encode_patch(-2, 3, rows))
        self.assertEqual((left, top, back), (-2, 3, rows))

    def test_strip_outline_keeps_bright_core(self):
        # A bright 3x3 block framed by a dark ring.
        rows = [[40] * 5] + [[40, 250, 250, 250, 40] for _ in range(3)] + [[40] * 5]
        out = self.t.strip_outline(rows, PALETTE)
        self.assertEqual(out[0], [None] * 5)
        self.assertEqual(out[2], [None, 250, 250, 250, None])

    def test_font_patch_adds_shadow(self):
        _, _, rows = self.t.decode_patch(self.t.font_patch("#", 200, 1))
        self.assertEqual(rows, [[200, None], [None, 1]])

    def test_restyle_replaces_font_and_leaves_other_lumps(self):
        glyph = self.t.encode_patch(0, 0, [[40, 250, 40]])
        lumps = [("PLAYPAL", PALETTE), ("STCFN065", glyph), ("M_NGAME", glyph),
                 ("M_SKULL1", glyph), ("WALL", b"data")]
        out = dict(self.t.restyle(lumps))
        self.assertNotEqual(out["STCFN065"], glyph)
        self.assertEqual(self.t.decode_patch(out["M_NGAME"])[2], [[None, 250, None]])
        self.assertEqual(out["M_SKULL1"], glyph)
        self.assertEqual(out["WALL"], b"data")


if __name__ == "__main__":
    unittest.main()

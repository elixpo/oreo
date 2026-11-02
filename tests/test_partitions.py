"""Tests for the Oreo Badge flash layout and tools/fetch_freedoom.py."""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLASH_SIZE = 16 * 1024 * 1024
MMAP_PAGE = 0x10000


def load_fetcher():
    spec = importlib.util.spec_from_file_location("fetch_freedoom", ROOT / "tools" / "fetch_freedoom.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def partitions():
    csv = ROOT / "firmware" / "boards" / "OREO_BADGE" / "partitions-oreo-badge.csv"
    rows = []
    for line in csv.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            name, kind, subtype, offset, size = [f.strip() for f in line.split(",")][:5]
            rows.append((name, kind, subtype, int(offset, 0), int(size, 0)))
    return rows


class PartitionTest(unittest.TestCase):
    def test_layout_is_contiguous_and_fills_flash(self):
        rows = partitions()
        for (_, _, _, off, size), (_, _, _, nxt, _) in zip(rows, rows[1:]):
            self.assertEqual(off + size, nxt)
        _, _, _, off, size = rows[-1]
        self.assertEqual(off + size, FLASH_SIZE)

    def test_firmware_and_doom_are_mmap_aligned(self):
        # Apps and memory-mapped data must start on a 64 KiB MMU page.
        for name, _, _, off, size in partitions():
            if name in ("factory", "doom"):
                self.assertEqual(off % MMAP_PAGE, 0, name)
                self.assertEqual(size % MMAP_PAGE, 0, name)

    def test_filesystem_partition_is_named_vfs(self):
        # MicroPython finds its filesystem by this label.
        self.assertIn("vfs", [row[0] for row in partitions()])

    def test_fetcher_reads_doom_partition(self):
        fetcher = load_fetcher()
        doom = [(off, size) for name, _, _, off, size in partitions() if name == "doom"]
        self.assertEqual([fetcher.doom_partition()], doom)


if __name__ == "__main__":
    unittest.main()

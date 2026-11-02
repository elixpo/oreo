#!/usr/bin/env python3
"""Fetch Freedoom and pack it into the game data the badge's Doom app loads.

Freedoom (https://freedoom.github.io, BSD-3-Clause) is a free replacement for
Doom's game data. This downloads the pinned release, verifies its SHA-256,
packs Episode 1 of Phase 1 (freedoom1.wad) into OWZ with tools/pack_wad.py
and checks the result fits the badge's "doom" partition. ./deploy --full
writes it there. One episode (nine levels) is what fits beside OreoOS in
16 MiB of flash; the engine then runs in single-episode mode.

    python3 tools/fetch_freedoom.py            # -> oreoWare/doom/freedoom1.owz
    python3 tools/fetch_freedoom.py --print-offset

The game data is downloaded, never committed; the download is cached in
~/.cache/oreo/freedoom.
"""

import argparse
import hashlib
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pack_wad  # noqa: E402

VERSION = "0.13.0"
URL = ("https://github.com/freedoom/freedoom/releases/download/"
       "v%s/freedoom-%s.zip" % (VERSION, VERSION))
SHA256 = "3f9b264f3e3ce503b4fb7f6bdcb1f419d93c7b546f4df3e874dd878db9688f59"
WAD = "freedoom-%s/freedoom1.wad" % VERSION
LICENSE = "freedoom-%s/COPYING.txt" % VERSION
EPISODES = {1}

REPO = Path(__file__).resolve().parent.parent
CACHE = Path.home() / ".cache" / "oreo" / "freedoom"
OUTPUT = REPO / "oreoWare" / "doom" / "freedoom1.owz"
PARTITIONS = REPO / "firmware" / "boards" / "OREO_BADGE" / "partitions-oreo-badge.csv"


def doom_partition(csv=PARTITIONS):
    """Return (offset, size) of the "doom" partition in the board's table."""
    for line in csv.read_text().splitlines():
        fields = [f.strip() for f in line.split(",")]
        if fields and fields[0] == "doom":
            return int(fields[3], 0), int(fields[4], 0)
    raise SystemExit("fetch_freedoom: no doom partition in %s" % csv)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(path):
    if path.exists() and sha256(path) == SHA256:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    print("Downloading Freedoom %s..." % VERSION)
    partial = path.with_suffix(".part")
    with urllib.request.urlopen(URL, timeout=60) as response, open(partial, "wb") as out:
        while chunk := response.read(1 << 20):
            out.write(chunk)
    if sha256(partial) != SHA256:
        partial.unlink()
        raise SystemExit("fetch_freedoom: checksum mismatch for %s" % URL)
    partial.replace(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--print-offset", action="store_true",
                        help="print the doom partition's flash offset and exit")
    args = parser.parse_args(argv)

    offset, size = doom_partition()
    if args.print_offset:
        print("0x%x" % offset)
        return 0

    archive = CACHE / ("freedoom-%s.zip" % VERSION)
    download(archive)
    with zipfile.ZipFile(archive) as z:
        wad = z.read(WAD)
        notice = z.read(LICENSE)

    ident, lumps = pack_wad.read_wad(wad)
    owz = pack_wad.pack(ident, pack_wad.prepare(lumps, episodes=EPISODES))
    if len(owz) > size:
        raise SystemExit("fetch_freedoom: %.2f MiB of game data does not fit the "
                         "%.2f MiB doom partition" % (len(owz) / 2**20, size / 2**20))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(owz)
    # Freedoom's licence travels with its data.
    (args.output.parent / "FREEDOOM-COPYING.txt").write_bytes(notice)
    print("Freedoom %s episode %s: %.2f MiB WAD -> %s %.2f MiB (partition 0x%x, %.2f MiB)" % (
        VERSION, ",".join(map(str, sorted(EPISODES))), len(wad) / 2**20, args.output.relative_to(REPO) if args.output.is_relative_to(REPO)
        else args.output, len(owz) / 2**20, offset, size / 2**20))
    return 0


if __name__ == "__main__":
    sys.exit(main())

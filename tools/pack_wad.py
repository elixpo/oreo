#!/usr/bin/env python3
"""Pack a Doom WAD into OWZ, the compressed form the Oreo Badge loads.

Doom reads its data as named "lumps" in random order, so the WAD cannot be
compressed as one stream. OWZ compresses every lump on its own with zlib
(the same idea as RV565 video frames): the badge inflates a lump into PSRAM
the first time the engine asks for it, using the ESP32-S3's ROM inflater.

The badge has no speaker, so sound effects, music and music-driver lumps are
emptied by default (--keep-audio keeps them): each keeps its name with zero
bytes of data, because the engine still looks lumps such as the title music
up by name and treats a missing one as fatal.

    python3 tools/pack_wad.py freedoom1.wad freedoom1.owz
    python3 tools/pack_wad.py --check freedoom1.owz freedoom1.wad

OWZ v1 layout, all integers little-endian:

    offset  size  field
    0       4     magic "OWZ1"
    4       4     identification of the source WAD ("IWAD" or "PWAD")
    8       4     lump count n
    12      4     offset of the lump directory
    16      ...   compressed lump data
    dir     n*20  per lump: name (8 bytes, NUL padded), uncompressed size (u32),
                  data offset (u32), stored size (u32)

A lump whose stored size equals its uncompressed size is stored as is;
otherwise it is a zlib stream that inflates to exactly the uncompressed size.
Zero-size lumps (map and section markers) keep their place in the directory,
because the engine finds levels and resources by their position.
"""

import argparse
import re
import struct
import sys
import zlib
from pathlib import Path

MAGIC = b"OWZ1"
HEADER = struct.Struct("<4s4sII")
ENTRY = struct.Struct("<8sIII")
WAD_HEADER = struct.Struct("<4sii")
WAD_ENTRY = struct.Struct("<ii8s")

# Sound effects (PC speaker and digital), music, and the music drivers' data.
AUDIO = re.compile(r"^(DS|DP|D_)")
AUDIO_NAMES = {"GENMIDI", "DMXGUS", "DMXGUSC"}


class PackError(ValueError):
    pass


def read_wad(data):
    """Return (identification, [(name, bytes)]) for a WAD file's contents."""
    if len(data) < WAD_HEADER.size:
        raise PackError("file too short to be a WAD")
    ident, count, dir_offset = WAD_HEADER.unpack_from(data, 0)
    if ident not in (b"IWAD", b"PWAD"):
        raise PackError("not a WAD file")
    if count < 0 or dir_offset < 0 or dir_offset + count * WAD_ENTRY.size > len(data):
        raise PackError("WAD directory is out of range")
    lumps = []
    for i in range(count):
        offset, size, raw_name = WAD_ENTRY.unpack_from(data, dir_offset + i * WAD_ENTRY.size)
        if size < 0 or (size and (offset < 0 or offset + size > len(data))):
            raise PackError("lump %d is out of range" % i)
        name = raw_name.split(b"\0", 1)[0].decode("latin-1")
        lumps.append((name, data[offset:offset + size]))
    return ident, lumps


def is_audio(name):
    return bool(AUDIO.match(name)) or name in AUDIO_NAMES


def pack(ident, lumps, level=9):
    """Return OWZ bytes for the given lumps."""
    body = bytearray()
    entries = []
    for name, content in lumps:
        offset = HEADER.size + len(body)
        stored = content
        if content:
            packed = zlib.compress(content, level)
            if len(packed) < len(content):
                stored = packed
        body += stored
        entries.append(ENTRY.pack(name.encode("latin-1")[:8].ljust(8, b"\0"),
                                  len(content), offset, len(stored)))
    dir_offset = HEADER.size + len(body)
    return HEADER.pack(MAGIC, ident, len(lumps), dir_offset) + bytes(body) + b"".join(entries)


def unpack(owz):
    """Return (identification, [(name, bytes)]) from OWZ bytes, validating it."""
    if len(owz) < HEADER.size:
        raise PackError("file too short to be OWZ")
    magic, ident, count, dir_offset = HEADER.unpack_from(owz, 0)
    if magic != MAGIC:
        raise PackError("not an OWZ file")
    if dir_offset + count * ENTRY.size != len(owz):
        raise PackError("OWZ directory does not end the file")
    lumps = []
    for i in range(count):
        raw_name, size, offset, stored = ENTRY.unpack_from(owz, dir_offset + i * ENTRY.size)
        if offset + stored > dir_offset:
            raise PackError("lump %d is out of range" % i)
        chunk = owz[offset:offset + stored]
        content = chunk if stored == size else zlib.decompress(chunk)
        if len(content) != size:
            raise PackError("lump %d does not inflate to its size" % i)
        lumps.append((raw_name.split(b"\0", 1)[0].decode("latin-1"), content))
    return ident, lumps


def strip_audio(lumps):
    """Empty the audio lumps, keeping their names and positions."""
    return [(n, b"" if is_audio(n) else c) for n, c in lumps]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path, help="WAD to pack (or OWZ with --check)")
    parser.add_argument("output", type=Path, help="OWZ to write (or the original WAD with --check)")
    parser.add_argument("--keep-audio", action="store_true", help="keep sound and music lumps")
    parser.add_argument("--level", type=int, default=9, choices=range(1, 10), metavar="1-9")
    parser.add_argument("--check", action="store_true",
                        help="verify an OWZ against the WAD it was made from")
    args = parser.parse_args(argv)

    try:
        if args.check:
            _, packed = unpack(args.source.read_bytes())
            ident, original = read_wad(args.output.read_bytes())
            if packed != original and packed != strip_audio(original):
                raise PackError("OWZ does not match the WAD")
            print("ok: %d lumps identical to %s" % (len(packed), args.output.name))
            return 0

        data = args.source.read_bytes()
        ident, lumps = read_wad(data)
        kept = lumps if args.keep_audio else strip_audio(lumps)
        owz = pack(ident, kept, args.level)
        args.output.write_bytes(owz)
        emptied = sum(1 for (n, c), (_, k) in zip(lumps, kept) if c and not k)
        print("%s: %d lumps (%d audio emptied), %.2f MiB -> %s %.2f MiB" % (
            args.source.name, len(kept), emptied, len(data) / 2**20,
            args.output.name, len(owz) / 2**20))
        return 0
    except PackError as exc:
        raise SystemExit("pack_wad: %s" % exc)


if __name__ == "__main__":
    sys.exit(main())

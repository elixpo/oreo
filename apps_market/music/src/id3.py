"""Title, artist, album and track number from an MP3's ID3 tags.

ID3v2 (2.2, 2.3, 2.4) at the start of the file, falling back to ID3v1 in
its last 128 bytes. read_tags() reads only the frame headers and the four
text frames it wants, seeking over everything else (cover art can be
hundreds of KB), so it costs a few small reads per file.
"""

WANT = {
    b"TIT2": "title", b"TPE1": "artist", b"TALB": "album", b"TRCK": "track",
    b"TT2": "title", b"TP1": "artist", b"TAL": "album", b"TRK": "track",
}
MAX_FRAME_TEXT = 512


def _syncsafe(b):
    return (b[0] << 21) | (b[1] << 14) | (b[2] << 7) | b[3]


def _latin1(b):
    return "".join(chr(c) for c in b)


def _utf16(b, big):
    out = []
    for i in range(0, len(b) - 1, 2):
        c = (b[i] << 8 | b[i + 1]) if big else (b[i + 1] << 8 | b[i])
        if 0xD800 <= c < 0xE000:
            out.append("?")
            continue
        out.append(chr(c))
    return "".join(out)


def decode_text(data):
    """An ID3v2 text frame's value (encoding byte, then text)."""
    if not data:
        return ""
    enc = data[0]
    b = bytes(data[1:])
    if enc == 0:
        s = _latin1(b.split(b"\0", 1)[0])
    elif enc == 3:
        s = b.split(b"\0", 1)[0].decode("utf-8", "ignore") if hasattr(b, "decode") else ""
    else:
        big = enc == 2
        if enc == 1 and len(b) >= 2:
            if b[:2] == b"\xff\xfe":
                big, b = False, b[2:]
            elif b[:2] == b"\xfe\xff":
                big, b = True, b[2:]
        # stop at a 16-bit NUL
        end = len(b)
        for i in range(0, len(b) - 1, 2):
            if b[i] == 0 and b[i + 1] == 0:
                end = i
                break
        s = _utf16(b[:end], big)
    return s.strip()


def parse_v1(tail):
    """Tags from the last 128 bytes of a file, or {}."""
    if len(tail) < 128 or tail[-128:-125] != b"TAG":
        return {}
    t = tail[-128:]

    def field(a, b):
        return _latin1(bytes(t[a:b]).split(b"\0", 1)[0]).strip()
    out = {}
    for k, a, b in (("title", 3, 33), ("artist", 33, 63), ("album", 63, 93)):
        v = field(a, b)
        if v:
            out[k] = v
    if t[125] == 0 and t[126]:
        out["track"] = str(t[126])
    return out


def header_size(head):
    """(version, tag size including the 10-byte header and any footer)
    from a file's first 10 bytes, or (0, 0)."""
    if len(head) < 10 or head[:3] != b"ID3" or head[3] in (0xFF, 0) or head[3] > 4:
        return 0, 0
    if any(c & 0x80 for c in head[6:10]):
        return 0, 0
    size = 10 + _syncsafe(head[6:10]) + (10 if head[5] & 0x10 else 0)
    return head[3], size


def read_v2(f):
    """ID3v2 tags from the start of an open binary file, or {}."""
    f.seek(0)
    head = f.read(10)
    ver, size = header_size(head)
    if not ver:
        return {}
    flags = head[5]
    end = 10 + _syncsafe(head[6:10])
    pos = 10
    if flags & 0x40 and ver >= 3:         # extended header: skip it
        ext = f.read(4)
        if len(ext) < 4:
            return {}
        n = _syncsafe(ext) if ver == 4 else (int.from_bytes(ext, "big") + 4)
        pos += n
        f.seek(pos)
    hlen = 6 if ver == 2 else 10
    out = {}
    while pos + hlen <= end and len(out) < 4:
        fh = f.read(hlen)
        if len(fh) < hlen or fh[0] == 0:
            break
        if ver == 2:
            fid = bytes(fh[:3])
            n = (fh[3] << 16) | (fh[4] << 8) | fh[5]
        else:
            fid = bytes(fh[:4])
            n = _syncsafe(fh[4:8]) if ver == 4 else int.from_bytes(fh[4:8], "big")
        pos += hlen
        if n <= 0 or pos + n > end:
            break
        key = WANT.get(fid)
        if key and key not in out:
            data = f.read(min(n, MAX_FRAME_TEXT))
            v = decode_text(data)
            if v:
                out[key] = v
        pos += n
        f.seek(pos)
    return out


def read_tags(path_or_file):
    """{title, artist, album, track} (whichever the file has)."""
    own = isinstance(path_or_file, str)
    f = open(path_or_file, "rb") if own else path_or_file
    try:
        out = {}
        try:
            out = read_v2(f)
        except Exception:
            out = {}
        if len(out) < 3:
            try:
                f.seek(-128, 2)
                for k, v in parse_v1(f.read(128)).items():
                    out.setdefault(k, v)
            except Exception:
                pass
        return out
    finally:
        if own:
            f.close()

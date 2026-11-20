"""A small QR code encoder for the Spotify pairing screen.

Byte mode, error correction level L, versions 1-6 (up to 134 bytes,
plenty for a sign-in URL with a PIN). Versions 7 and up need version
information blocks and are not supported.

    size, rows = encode("https://falera.elixpo.com/spotify/?pin=ABC234")
    mask = mono_mask(size, rows, scale=3, quiet=2)   # for d.blit_mono

`rows` is a list of `size` bytearrays, 1 = dark module. Encoding takes a
moment on the badge (eight mask candidates are scored), so the app runs
it on its network worker, never in update() or draw().
"""

# (data codewords per block, number of blocks, EC codewords per block)
_L_BLOCKS = {
    1: (19, 1, 7),
    2: (34, 1, 10),
    3: (55, 1, 15),
    4: (80, 1, 20),
    5: (108, 1, 26),
    6: (68, 2, 18),
}
_ALIGN = {1: (), 2: (6, 18), 3: (6, 22), 4: (6, 26), 5: (6, 30), 6: (6, 34)}
_ECL_L = 1          # format bits for level L

_EXP = bytearray(512)
_LOG = bytearray(256)


def _init_gf():
    x = 1
    for i in range(255):
        _EXP[i] = x
        _LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    for i in range(255, 512):
        _EXP[i] = _EXP[i - 255]


_init_gf()


def _gf_mul(a, b):
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _rs_divisor(degree):
    # Coefficients of prod (x - a^i), i < degree, highest power dropped.
    res = bytearray(degree)
    res[degree - 1] = 1
    root = 1
    for _ in range(degree):
        for j in range(degree):
            res[j] = _gf_mul(res[j], root)
            if j + 1 < degree:
                res[j] ^= res[j + 1]
        root = _gf_mul(root, 2)
    return res


def _rs_remainder(data, divisor):
    res = bytearray(len(divisor))
    for b in data:
        factor = b ^ res[0]
        res[:-1] = res[1:]
        res[-1] = 0
        for i in range(len(divisor)):
            res[i] ^= _gf_mul(divisor[i], factor)
    return res


def pick_version(n_bytes):
    """Smallest supported version that holds n_bytes, or None."""
    for v in range(1, 7):
        dcw, nblk, _ = _L_BLOCKS[v]
        if 4 + 8 + n_bytes * 8 <= dcw * nblk * 8:
            return v
    return None


def _codewords(data, version):
    dcw, nblk, ecw = _L_BLOCKS[version]
    cap = dcw * nblk
    bits = []

    def put(val, n):
        for i in range(n - 1, -1, -1):
            bits.append((val >> i) & 1)

    put(4, 4)                   # byte mode
    put(len(data), 8)
    for b in data:
        put(b, 8)
    put(0, min(4, cap * 8 - len(bits)))
    put(0, (-len(bits)) % 8)
    out = bytearray()
    for i in range(0, len(bits), 8):
        v = 0
        for b in bits[i:i + 8]:
            v = (v << 1) | b
        out.append(v)
    pad = 0xEC
    while len(out) < cap:
        out.append(pad)
        pad ^= 0xEC ^ 0x11
    # Split into blocks, add error correction, interleave.
    div = _rs_divisor(ecw)
    blocks = []
    ecs = []
    for k in range(nblk):
        blk = out[k * dcw:(k + 1) * dcw]
        blocks.append(blk)
        ecs.append(_rs_remainder(blk, div))
    res = bytearray()
    for i in range(dcw):
        for blk in blocks:
            res.append(blk[i])
    for i in range(ecw):
        for e in ecs:
            res.append(e[i])
    return res


def _format_bits(mask):
    data = (_ECL_L << 3) | mask
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    return ((data << 10) | rem) ^ 0x5412


def _mask_bit(mask, x, y):
    if mask == 0:
        return (x + y) % 2 == 0
    if mask == 1:
        return y % 2 == 0
    if mask == 2:
        return x % 3 == 0
    if mask == 3:
        return (x + y) % 3 == 0
    if mask == 4:
        return (x // 3 + y // 2) % 2 == 0
    if mask == 5:
        return x * y % 2 + x * y % 3 == 0
    if mask == 6:
        return (x * y % 2 + x * y % 3) % 2 == 0
    return ((x + y) % 2 + x * y % 3) % 2 == 0


class _Grid:
    def __init__(self, version):
        self.size = n = version * 4 + 17
        self.m = [bytearray(n) for _ in range(n)]
        self.fn = [bytearray(n) for _ in range(n)]
        self._function_patterns(version)

    def set_fn(self, x, y, dark):
        self.m[y][x] = 1 if dark else 0
        self.fn[y][x] = 1

    def _finder(self, cx, cy):
        n = self.size
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < n and 0 <= y < n:
                    d = max(abs(dx), abs(dy))
                    self.set_fn(x, y, d != 2 and d != 4)

    def _align(self, cx, cy):
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                self.set_fn(cx + dx, cy + dy, max(abs(dx), abs(dy)) != 1)

    def _function_patterns(self, version):
        n = self.size
        for i in range(n):
            self.set_fn(6, i, i % 2 == 0)
            self.set_fn(i, 6, i % 2 == 0)
        self._finder(3, 3)
        self._finder(n - 4, 3)
        self._finder(3, n - 4)
        pos = _ALIGN[version]
        last = len(pos) - 1
        for i in range(len(pos)):
            for j in range(len(pos)):
                if ((i == 0 and j == 0) or (i == 0 and j == last)
                        or (i == last and j == 0)):
                    continue
                self._align(pos[i], pos[j])
        self.draw_format(0)     # reserve the format areas

    def draw_format(self, mask):
        n = self.size
        bits = _format_bits(mask)

        def bit(i):
            return (bits >> i) & 1

        for i in range(6):
            self.set_fn(8, i, bit(i))
        self.set_fn(8, 7, bit(6))
        self.set_fn(8, 8, bit(7))
        self.set_fn(7, 8, bit(8))
        for i in range(9, 15):
            self.set_fn(14 - i, 8, bit(i))
        for i in range(8):
            self.set_fn(n - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self.set_fn(8, n - 15 + i, bit(i))
        self.set_fn(8, n - 8, True)     # the dark module

    def place(self, data):
        n = self.size
        total = len(data) * 8
        i = 0
        right = n - 1
        while right >= 1:
            if right == 6:
                right = 5
            upward = ((right + 1) & 2) == 0
            for vert in range(n):
                y = n - 1 - vert if upward else vert
                for j in range(2):
                    x = right - j
                    if not self.fn[y][x] and i < total:
                        self.m[y][x] = (data[i >> 3] >> (7 - (i & 7))) & 1
                        i += 1
            right -= 2

    def apply_mask(self, mask):
        n = self.size
        for y in range(n):
            row = self.m[y]
            fr = self.fn[y]
            for x in range(n):
                if not fr[x] and _mask_bit(mask, x, y):
                    row[x] ^= 1


def _penalty(m, n):
    """Mask score from the ISO rules 1, 2 and 4 (rule 3, finder-like
    runs, is left out: any mask decodes, this only picks a good one)."""
    score = 0
    for y in range(n):
        run = 1
        row = m[y]
        for x in range(1, n):
            if row[x] == row[x - 1]:
                run += 1
            else:
                if run >= 5:
                    score += run - 2
                run = 1
        if run >= 5:
            score += run - 2
    for x in range(n):
        run = 1
        for y in range(1, n):
            if m[y][x] == m[y - 1][x]:
                run += 1
            else:
                if run >= 5:
                    score += run - 2
                run = 1
        if run >= 5:
            score += run - 2
    dark = 0
    for y in range(n):
        row = m[y]
        dark += sum(row)
        if y + 1 < n:
            nxt = m[y + 1]
            for x in range(n - 1):
                c = row[x]
                if c == row[x + 1] == nxt[x] == nxt[x + 1]:
                    score += 3
    total = n * n
    k = (abs(dark * 20 - total * 10) + total - 1) // total - 1
    if k > 0:
        score += k * 10
    return score


def encode(text, mask=None):
    """(size, rows) for `text` (str or bytes). Raises ValueError when it
    does not fit version 6. `mask` forces a mask pattern (tests)."""
    data = text.encode("utf-8") if isinstance(text, str) else bytes(text)
    version = pick_version(len(data))
    if version is None:
        raise ValueError("text too long for a QR code here")
    cw = _codewords(data, version)
    masks = range(8) if mask is None else (mask,)
    best = None
    for k in masks:
        g = _Grid(version)
        g.place(cw)
        g.apply_mask(k)
        g.draw_format(k)
        if mask is not None:
            return g.size, g.m
        p = _penalty(g.m, g.size)
        if best is None or p < best[0]:
            best = (p, g)
    g = best[1]
    return g.size, g.m


def mono_mask(size, rows, scale=3, quiet=2):
    """A MONO_HLSB bit mask (set bit = dark module) of the code scaled
    by `scale`, with `quiet` light modules of margin on every side.
    Returns (mask_bytes, width_px); the mask is square."""
    side = (size + 2 * quiet) * scale
    stride = (side + 7) >> 3
    out = bytearray(stride * side)
    for y in range(size):
        row = rows[y]
        for x in range(size):
            if not row[x]:
                continue
            px0 = (x + quiet) * scale
            py0 = (y + quiet) * scale
            for py in range(py0, py0 + scale):
                base = py * stride
                for px in range(px0, px0 + scale):
                    out[base + (px >> 3)] |= 0x80 >> (px & 7)
    return out, side

"""Streaming downloads for the App Store: app files and partition data.

`oreoOS._http.get_url` buffers a whole response in RAM, which is fine for
a catalogue or an icon but not for a 7 MiB game-data image. This module
streams a response body in fixed 4 KiB pieces into a sink, so memory use
stays flat whatever the download size:

    stream(url, sink, on_progress=None) -> bytes received, or None
    download_file(url, path, size, on_progress=None) -> True / False
    install_partition(name, url, size, sha256, on_progress=None) -> (ok, msg)
    partition_matches(name, size, sha256) -> True / False

Partition writes go through esp32.Partition and are limited to the labels
in ALLOWED_PARTITIONS, so no catalogue entry can reach the firmware, NVS
or the filesystem. Block 0 (which holds the data's magic, e.g. "OWZ1" for
Doom) is erased first and written last, only after the whole image has
been received and verified by size and SHA-256 against what is now on
flash, so an interrupted install never leaves data the engine would try
to load.
"""

import gc

try:
    import socket as _socket
    import ssl as _ssl
    _NET = True
except ImportError:
    _NET = False

try:
    import hashlib as _hashlib
except ImportError:
    _hashlib = None

try:
    from binascii import hexlify as _hexlify
except ImportError:
    _hexlify = None


USER_AGENT = "OreoBadge-AppStore"
MAX_REDIRECTS = 4
CHUNK = 4096
BLOCK = 4096
# Partitions the Store may write. Anything else is refused outright.
ALLOWED_PARTITIONS = ("doom",)

# Block-device ioctl numbers (MicroPython's MP_BLOCKDEV_IOCTL_*).
_IOCTL_BLOCK_COUNT = 4
_IOCTL_BLOCK_SIZE  = 5
_IOCTL_BLOCK_ERASE = 6


def _bc(msg):
    try:
        print("[store_io] " + msg)
    except Exception:
        pass


def _split(url):
    if not url.startswith("https://"):
        return None
    rest = url[8:]
    slash = rest.find("/")
    if slash < 0:
        host, path = rest, "/"
    else:
        host, path = rest[:slash], rest[slash:]
    port = 443
    if ":" in host:
        host, p = host.split(":", 1)
        try:
            port = int(p)
        except ValueError:
            return None
    if not host:
        return None
    return host, port, path


def _token_for(host):
    if not (host == "api.github.com" or host == "raw.githubusercontent.com"):
        return ""
    try:
        from oreoOS.config import GH_TOKEN as _TOK
        if _TOK:
            return "Authorization: Bearer " + _TOK + "\r\n"
    except Exception:
        pass
    return ""


def _open(host, port, path, timeout_s, auth):
    addr = _socket.getaddrinfo(host, port)[0][-1]
    raw = _socket.socket()
    try:
        raw.settimeout(timeout_s)
        raw.connect(addr)
        s = _ssl.wrap_socket(raw, server_hostname=host)
    except Exception:
        try:
            raw.close()
        except Exception:
            pass
        raise
    try:
        s.settimeout(timeout_s)
    except Exception:
        pass
    s.write(((
        "GET %s HTTP/1.1\r\n"
        "Host: %s\r\n"
        "User-Agent: %s\r\n"
        "Accept: */*\r\n"
        "Accept-Encoding: identity\r\n"
        "%s"
        "Connection: close\r\n\r\n"
    ) % (path, host, USER_AGENT, auth)).encode())
    return s, raw


def read_head(s):
    """Read the status line and headers. Returns (status, length, chunked,
    location) with length -1 when no Content-Length was sent."""
    line = s.readline()
    if not line:
        return 0, -1, False, None
    parts = line.split(None, 2)
    try:
        status = int(parts[1])
    except Exception:
        status = 0
    length = -1
    chunked = False
    location = None
    while True:
        line = s.readline()
        if not line or line in (b"\r\n", b"\n"):
            break
        colon = line.find(b":")
        if colon < 0:
            continue
        key = line[:colon].strip().lower()
        val = line[colon + 1:].strip()
        if key == b"content-length":
            try:
                length = int(val)
            except ValueError:
                length = -1
        elif key == b"transfer-encoding":
            chunked = b"chunked" in val.lower()
        elif key == b"location":
            try:
                location = val.decode()
            except Exception:
                location = None
    return status, length, chunked, location


def _read_exact(s, mv, n, sink, state, on_progress):
    """Read exactly n body bytes through the shared buffer into sink."""
    while n > 0:
        want = n if n < len(mv) else len(mv)
        got = s.readinto(mv[:want])
        if not got:
            return False
        if sink(mv[:got]) is False:
            return False
        n -= got
        state[0] += got
        if on_progress is not None:
            try:
                on_progress(state[0], state[1])
            except Exception:
                pass
    return True


def read_body(s, length, chunked, sink, on_progress=None, buf=None):
    """Stream a response body into sink(memoryview). Returns the byte count
    or None if the body was cut short or sink returned False."""
    mv = memoryview(buf if buf is not None else bytearray(CHUNK))
    state = [0, length if length >= 0 else 0]
    if chunked:
        while True:
            line = s.readline()
            if not line:
                return None
            try:
                n = int(line.split(b";")[0].strip(), 16)
            except ValueError:
                return None
            if n == 0:
                break
            if not _read_exact(s, mv, n, sink, state, on_progress):
                return None
            s.readline()
        return state[0]
    if length >= 0:
        if not _read_exact(s, mv, length, sink, state, on_progress):
            return None
        return state[0]
    # No length and not chunked: read until the server closes.
    while True:
        got = s.readinto(mv)
        if not got:
            break
        if sink(mv[:got]) is False:
            return None
        state[0] += got
    return state[0]


def stream(url, sink, on_progress=None, timeout_s=15, buf=None):
    """GET url (following HTTPS redirects) and stream the body to sink.

    on_progress(received, total) is called as bytes arrive. Returns the
    number of body bytes, or None on any failure."""
    if not _NET:
        return None
    current = url
    auth_allowed = True
    for _ in range(MAX_REDIRECTS + 1):
        parsed = _split(current)
        if parsed is None:
            return None
        host, port, path = parsed
        auth = _token_for(host) if auth_allowed else ""
        s = raw = None
        try:
            s, raw = _open(host, port, path, timeout_s, auth)
            status, length, chunked, location = read_head(s)
            if status == 200:
                return read_body(s, length, chunked, sink, on_progress, buf)
            if status in (301, 302, 303, 307, 308) and location:
                if location.startswith("/"):
                    location = "https://" + host + location
                nxt = _split(location)
                if nxt is None:
                    return None
                if nxt[0] != host:
                    # Never forward a token to a CDN or another host.
                    auth_allowed = False
                current = location
                continue
            _bc("HTTP %d %s" % (status, host))
            return None
        except Exception as e:
            _bc("fail %s: %s" % (host, e))
            return None
        finally:
            for h in (s, raw):
                try:
                    if h is not None:
                        h.close()
                except Exception:
                    pass
            gc.collect()
    return None


def download_file(url, path, size, on_progress=None, buf=None):
    """Stream url into path. True only when exactly `size` bytes landed
    (size < 0 skips the check). A failed download removes the file."""
    try:
        f = open(path, "wb")
    except OSError:
        return False
    try:
        n = stream(url, f.write, on_progress, buf=buf)
    finally:
        f.close()
    if n is None or (size >= 0 and n != size):
        _bc("download %s: got %s of %d bytes" % (path, n, size))
        try:
            import os
            os.remove(path)
        except Exception:
            pass
        return False
    return True


# ── partition data ──────────────────────────────────────────────────────

def _hex(digest):
    if _hexlify is not None:
        return _hexlify(digest).decode()
    return "".join("%02x" % b for b in digest)


def find_partition(name):
    """esp32.Partition for an allowed data partition label, or None."""
    if name not in ALLOWED_PARTITIONS:
        return None
    try:
        import esp32
        found = esp32.Partition.find(esp32.Partition.TYPE_DATA, label=name)
    except Exception:
        return None
    return found[0] if found else None


class PartitionWriter:
    """Stream an image into a partition, block 0 last.

    feed() takes body bytes in any piece sizes; finish() pads the last
    block, verifies size + SHA-256 (of the received stream and of a
    read-back of what is on flash), and only then writes block 0."""

    def __init__(self, part, size, sha256):
        self.part = part
        self.size = int(size)
        self.sha = (sha256 or "").lower()
        bs = part.ioctl(_IOCTL_BLOCK_SIZE, 0)
        self.blocks = part.ioctl(_IOCTL_BLOCK_COUNT, 0)
        if bs != BLOCK:
            raise ValueError("block size %d" % bs)
        if self.size <= 0 or self.size > self.blocks * BLOCK:
            raise ValueError("image does not fit the partition")
        if _hashlib is None or len(self.sha) != 64:
            raise ValueError("no sha256")
        self.head = bytearray(BLOCK)
        self.buf = bytearray(BLOCK)
        self.fill = 0
        self.blk = 0
        self.received = 0
        self.hash = _hashlib.sha256()
        # Invalidate whatever is there before any other block changes.
        part.ioctl(_IOCTL_BLOCK_ERASE, 0)

    def _flush(self):
        if self.blk >= self.blocks:
            raise ValueError("write past partition end")
        if self.blk == 0:
            self.head[:] = self.buf
        else:
            self.part.writeblocks(self.blk, self.buf)
        self.blk += 1
        self.fill = 0

    def feed(self, mv):
        n = len(mv)
        if self.received + n > self.size:
            return False
        self.hash.update(mv)
        self.received += n
        i = 0
        while i < n:
            take = BLOCK - self.fill
            if take > n - i:
                take = n - i
            self.buf[self.fill:self.fill + take] = mv[i:i + take]
            self.fill += take
            i += take
            if self.fill == BLOCK:
                self._flush()
        return True

    def finish(self):
        """Verify and commit. Returns (ok, message)."""
        if self.received != self.size:
            return False, "incomplete download"
        if self.fill:
            for i in range(self.fill, BLOCK):
                self.buf[i] = 0xFF
            self._flush()
        if _hex(self.hash.digest()) != self.sha:
            return False, "checksum mismatch"
        # Read back what flash now holds and hash it again.
        h = _hashlib.sha256()
        left = self.size
        blk = 0
        rb = self.buf
        while left > 0:
            if blk == 0:
                src = self.head
            else:
                self.part.readblocks(blk, rb)
                src = rb
            take = BLOCK if left > BLOCK else left
            h.update(memoryview(src)[:take])
            left -= take
            blk += 1
        if _hex(h.digest()) != self.sha:
            return False, "flash verify failed"
        self.part.writeblocks(0, self.head)
        return True, "ok"


def partition_matches(name, size, sha256, part=None, on_progress=None):
    """True when the partition already starts with exactly this image."""
    part = part or find_partition(name)
    if part is None or _hashlib is None:
        return False
    try:
        blocks = part.ioctl(_IOCTL_BLOCK_COUNT, 0)
        if size <= 0 or size > blocks * BLOCK:
            return False
        buf = bytearray(BLOCK)
        h = _hashlib.sha256()
        left = size
        blk = 0
        while left > 0:
            part.readblocks(blk, buf)
            if blk == 0 and buf[0] == 0xFF and buf[1] == 0xFF:
                return False            # erased: nothing there
            take = BLOCK if left > BLOCK else left
            h.update(memoryview(buf)[:take])
            left -= take
            blk += 1
            if on_progress is not None and (blk & 63) == 0:
                try:
                    on_progress(size - left, size)
                except Exception:
                    pass
        return _hex(h.digest()) == (sha256 or "").lower()
    except Exception:
        return False


def _engine_busy(name):
    """The Doom engine maps its partition; never rewrite it under a game."""
    if name != "doom":
        return False
    try:
        import _oreo_doom
        return bool(_oreo_doom.running())
    except Exception:
        return False


def install_partition(name, url, size, sha256, on_progress=None,
                      stream_fn=None, part=None):
    """Download url into the named data partition. Returns (ok, message)."""
    if name not in ALLOWED_PARTITIONS:
        return False, "partition not allowed"
    part = part or find_partition(name)
    if part is None:
        return False, "no %s partition" % name
    if _engine_busy(name):
        return False, "restart the badge first"
    try:
        writer = PartitionWriter(part, size, sha256)
    except Exception as e:
        return False, str(e)
    gc.collect()
    n = (stream_fn or stream)(url, writer.feed, on_progress, 20)
    if n is None:
        return False, "download failed"
    try:
        return writer.finish()
    except Exception as e:
        return False, "write failed: " + str(e)

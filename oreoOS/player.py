"""Streaming MP3 player: HTTP(S) streams and files, decoded on a worker.

    from oreoOS import player
    p = player.Player(os.audio)
    p.play("http://example.com/stream.mp3", name="Example FM")
    ...
    p.update()          # every frame, on the main thread (in App.update)
    p.state, p.title    # CONNECTING / BUFFERING / PLAYING / ERROR / ...
    p.stop()

The worker thread (16 KB stack, for TLS) connects, follows redirects and
.pls/.m3u playlists, strips ICY metadata (Icy-MetaData: 1, icy-metaint,
StreamTitle), keeps the compressed stream in a 64 KB ring (PSRAM), decodes
it with the firmware's MP3 decoder (_oreo_audio, firmware/usermods/
oreo_audio) and queues mono PCM in the audio driver (oreoWare.audio). A
stalled or dropped live stream is reconnected; a file or podcast episode
ends when its data does. Nothing here draws, and nothing on the main thread
waits on the network: update() only switches the amp on and off as the
state changes, because the speaker and the expander belong to the main
thread.

Files (a path starting with "/", e.g. on the microSD card) take the same
path minus the network. Seeking: play(url, start_s=...) on a source that
honours HTTP Range (or a file) starts there, and seek(delta_s) restarts the
stream at the estimated byte offset (exact for constant bit rate MP3s).

Wi-Fi is used for the internet only: the player opens outgoing connections
to the stream's server and never listens.
"""

import time

try:
    _ticks_ms = time.ticks_ms
    _ticks_diff = time.ticks_diff
    _ticks_add = time.ticks_add
    _sleep_ms = time.sleep_ms
except AttributeError:          # CPython host tests
    def _ticks_add(a, b):
        return a + b

    def _ticks_ms():
        return int(time.monotonic() * 1000)

    def _ticks_diff(a, b):
        return a - b

    def _sleep_ms(ms):
        time.sleep(ms / 1000)

from oreoWare.audio import Ring

USER_AGENT = "FaleraOS-Player/1.0"

IDLE, CONNECTING, BUFFERING, PLAYING, ERROR, ENDED = (
    "idle", "connecting", "buffering", "playing", "error", "ended")

STREAM_RING = 64 * 1024     # compressed stream: 8 s at 64 kb/s, 4 s at 128 kb/s
PREBUFFER = 16 * 1024       # bytes before playback starts (2 s at 64 kb/s)
REBUFFER = 8 * 1024         # after a stall
READ_BYTES = 2048
DECODE_IN = 4096
PCM_SAMPLES = 2304          # two MPEG-1 frames per decode call
CONNECT_TIMEOUT_S = 8
READ_TIMEOUT_S = 0.25
STALL_MS = 10000            # no data this long: reconnect
MAX_RETRIES = 4
RETRY_MS = (1000, 2000, 4000, 8000)
MAX_REDIRECTS = 5
MAX_HEAD = 8192
MAX_PLAYLIST = 16 * 1024
THREAD_STACK = 16 * 1024

_TIMEOUT_ERRNO = (11, 110, 116)     # EAGAIN, ETIMEDOUT (lwIP and Linux)


class StreamError(Exception):
    """A reason to show the user. fatal: retrying cannot help (the
    stream is not something the badge can play)."""

    def __init__(self, msg, fatal=False):
        Exception.__init__(self, msg)
        self.fatal = fatal


# ── URLs, playlists, ICY ───────────────────────────────────────────────────

def split_url(url):
    """(tls, host, port, path) for an http(s) URL; raises StreamError."""
    if url.startswith("https://"):
        tls, rest, port = True, url[8:], 443
    elif url.startswith("http://"):
        tls, rest, port = False, url[7:], 80
    else:
        raise StreamError("not an http(s) URL", True)
    slash = rest.find("/")
    host, path = (rest, "/") if slash < 0 else (rest[:slash], rest[slash:])
    if "@" in host:
        host = host.split("@", 1)[1]
    if host.startswith("["):
        raise StreamError("IPv6 addresses are not supported")
    if ":" in host:
        host, p = host.rsplit(":", 1)
        try:
            port = int(p)
        except ValueError:
            raise StreamError("bad port")
    if "#" in path:
        path = path.split("#", 1)[0]
    if not host:
        raise StreamError("no host")
    return tls, host, port, path


def join_url(base, location):
    """Resolve a redirect Location against the URL that sent it."""
    location = location.strip()
    if location.startswith("http://") or location.startswith("https://"):
        return location
    tls, host, port, path = split_url(base)
    scheme = "https://" if tls else "http://"
    default = 443 if tls else 80
    origin = scheme + host + ("" if port == default else ":%d" % port)
    if location.startswith("//"):
        return scheme[:-2] + location
    if location.startswith("/"):
        return origin + location
    d = path.split("?", 1)[0]
    return origin + d[:d.rfind("/") + 1] + location


def parse_playlist(text):
    """The first stream URL in a .pls or .m3u playlist, or None.
    Raises StreamError for an HLS playlist (segments, not one stream)."""
    if isinstance(text, (bytes, bytearray)):
        text = bytes(text).decode("utf-8", "ignore")
    if "#EXT-X-" in text:
        raise StreamError("HLS streams are not supported", True)
    first = None
    for line in text.splitlines():
        line = line.strip().lstrip("﻿")
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if "=" in line and line[:4].lower() == "file":
            # .pls: File1=http://...
            k, _, v = line.partition("=")
            v = v.strip()
            if v.startswith("http://") or v.startswith("https://"):
                n = k[4:]
                if n in ("1", ""):
                    return v
                if first is None:
                    first = v
            continue
        if line.startswith("http://") or line.startswith("https://"):
            return line if first is None else first
    return first


def is_playlist(url, ctype):
    ctype = (ctype or "").lower()
    if "scpls" in ctype or "mpegurl" in ctype or "x-pls" in ctype:
        return True
    if "audio/mpeg" in ctype or ctype.startswith("audio/mp3"):
        return False
    path = url.split("?", 1)[0].lower()
    return path.endswith(".pls") or path.endswith(".m3u") or path.endswith(".m3u8")


def id3_size(head):
    """Total size of an ID3v2 tag (header, frames, footer) from its first
    10 bytes, or 0 when they are not an ID3v2 header."""
    if len(head) < 10 or head[0:3] != b"ID3" or head[3] == 0xFF:
        return 0
    sz = 0
    for b in head[6:10]:
        if b & 0x80:
            return 0
        sz = (sz << 7) | b
    return 10 + sz + (10 if head[5] & 0x10 else 0)


def parse_stream_title(meta):
    """The StreamTitle of an ICY metadata block (bytes), or None."""
    if isinstance(meta, (bytes, bytearray, memoryview)):
        meta = bytes(meta).rstrip(b"\0")
        try:
            meta = meta.decode("utf-8")
        except Exception:
            meta = meta.decode("latin-1") if hasattr(meta, "decode") else str(meta)
    key = "StreamTitle='"
    i = meta.find(key)
    if i < 0:
        return None
    i += len(key)
    j = meta.find("';", i)
    if j < 0:
        j = meta.rfind("'")
        if j < i:
            j = len(meta)
    return meta[i:j].strip()


class IcyDemux:
    """Separates audio from ICY metadata: every `metaint` audio bytes come
    a length byte (x16) and that many bytes of metadata.

        demux = IcyDemux(metaint, on_title)
        for a, b in demux.feed(buf, n):   # audio is buf[a:b] for each pair
    """

    def __init__(self, metaint, on_title=None):
        self.metaint = metaint
        self.on_title = on_title
        self._left = metaint        # audio bytes until the next length byte
        self._meta = None           # bytearray while collecting metadata
        self._meta_want = 0

    def feed(self, buf, n):
        out = []
        if not self.metaint:
            if n:
                out.append((0, n))
            return out
        i = 0
        while i < n:
            if self._meta is not None:
                take = min(self._meta_want - len(self._meta), n - i)
                self._meta.extend(buf[i:i + take])
                i += take
                if len(self._meta) >= self._meta_want:
                    self._emit(self._meta)
                    self._meta = None
                    self._left = self.metaint
            elif self._left == 0:
                size = buf[i] * 16
                i += 1
                if size:
                    self._meta = bytearray()
                    self._meta_want = size
                else:
                    self._left = self.metaint
            else:
                take = min(self._left, n - i)
                out.append((i, i + take))
                self._left -= take
                i += take
        return out

    def _emit(self, meta):
        title = parse_stream_title(meta)
        if title is not None and self.on_title is not None:
            self.on_title(title)


# ── HTTP ───────────────────────────────────────────────────────────────────

def _connect(host, port, tls, timeout_s):
    """A connected (TLS-verified for https) socket; the badge's own
    connector, with its DNS fallback and certificate checks."""
    from oreoOS import _http
    raw = _http._connect(host, port, timeout_s)
    if not tls:
        return raw
    try:
        s = _http.tls_wrap(raw, host)
    except Exception:
        try:
            raw.close()
        except Exception:
            pass
        raise
    return s


def _send(s, data):
    w = getattr(s, "write", None)
    if w is None:
        s.sendall(data)
        return
    mv = memoryview(data)
    while mv:
        n = w(mv)
        if n is None:
            n = len(mv)
        if n <= 0:
            raise OSError("write failed")
        mv = mv[n:]


def _recv_into(s, mv):
    r = getattr(s, "readinto", None)
    if r is not None:
        n = r(mv)
    else:
        n = s.recv_into(mv)
    return 0 if n is None else n


def _settimeout(s, t):
    try:
        s.settimeout(t)
    except Exception:
        pass


def _close(s):
    try:
        if s is not None:
            s.close()
    except Exception:
        pass


def parse_head(head):
    """(status, {lower-case name: value}) from response-head bytes. Handles
    SHOUTcast's "ICY 200 OK" status line."""
    lines = bytes(head).split(b"\r\n")
    parts = lines[0].split(b" ", 2)
    status = 0
    if len(parts) >= 2:
        try:
            status = int(parts[1])
        except ValueError:
            status = 0
    hdrs = {}
    for ln in lines[1:]:
        k, sep, v = ln.partition(b":")
        if sep:
            try:
                hdrs[k.strip().lower().decode()] = v.strip().decode("utf-8", "ignore")
            except Exception:
                pass
    return status, hdrs


class Response:
    def __init__(self, sock, url, status, headers, leftover):
        self.sock = sock
        self.url = url
        self.status = status
        self.headers = headers
        self.leftover = leftover        # body bytes read with the head

    def close(self):
        _close(self.sock)
        self.sock = None


def request(url, connect=None, range_start=None, icy=True, timeout_s=CONNECT_TIMEOUT_S,
            user_agent=None):
    """GET url and read the response head. Returns a Response (the socket
    positioned at the body). HTTP/1.0, so bodies are never chunked."""
    connect = connect or _connect
    tls, host, port, path = split_url(url)
    s = connect(host, port, tls, timeout_s)
    try:
        _settimeout(s, timeout_s)
        default = 443 if tls else 80
        hosthdr = host if port == default else "%s:%d" % (host, port)
        req = ("GET %s HTTP/1.0\r\nHost: %s\r\nUser-Agent: %s\r\nAccept: */*\r\n"
               % (path, hosthdr, user_agent or USER_AGENT))
        if icy:
            req += "Icy-MetaData: 1\r\n"
        if range_start:
            req += "Range: bytes=%d-\r\n" % range_start
        req += "Connection: close\r\n\r\n"
        _send(s, req.encode())
        buf = bytearray(1024)
        mv = memoryview(buf)
        got = bytearray()
        deadline = _ticks_add(_ticks_ms(), int(timeout_s * 1000))
        while True:
            end = got.find(b"\r\n\r\n")
            if end >= 0:
                break
            if len(got) > MAX_HEAD:
                raise StreamError("response header too long")
            if _ticks_diff(deadline, _ticks_ms()) <= 0:
                raise StreamError("no response")
            try:
                n = _recv_into(s, mv)
            except OSError as e:
                if _errno(e) in _TIMEOUT_ERRNO:
                    continue
                raise
            if not n:
                raise StreamError("connection closed")
            got.extend(mv[:n])
        status, hdrs = parse_head(got[:end])
        return Response(s, url, status, hdrs, bytes(got[end + 4:]))
    except Exception:
        _close(s)
        raise


def _errno(e):
    try:
        return e.errno if e.errno is not None else e.args[0]
    except Exception:
        try:
            return e.args[0]
        except Exception:
            return None


def _read_body(resp, limit):
    body = bytearray(resp.leftover)
    buf = bytearray(1024)
    mv = memoryview(buf)
    while len(body) < limit:
        try:
            n = _recv_into(resp.sock, mv)
        except OSError:
            break
        if not n:
            break
        body.extend(mv[:n])
    return bytes(body[:limit])


def open_stream(url, connect=None, range_start=None, icy=True):
    """Connect to an MP3 stream, following redirects and playlists.
    Returns the Response; raises StreamError with a short reason."""
    for _ in range(MAX_REDIRECTS + 1):
        resp = request(url, connect, range_start, icy)
        st = resp.status
        if st in (301, 302, 303, 307, 308):
            loc = resp.headers.get("location")
            resp.close()
            if not loc:
                raise StreamError("redirect without a location")
            url = join_url(url, loc)
            continue
        if st == 416:
            resp.close()
            raise StreamError("position past the end", True)
        if st not in (200, 206):
            resp.close()
            raise StreamError("HTTP %d" % st if st else "not an HTTP server",
                              400 <= st < 500)
        ctype = resp.headers.get("content-type", "").lower()
        if is_playlist(url, ctype):
            body = _read_body(resp, MAX_PLAYLIST)
            resp.close()
            nxt = parse_playlist(body)
            if not nxt:
                raise StreamError("empty playlist", True)
            url = nxt
            continue
        if "text/html" in ctype:
            resp.close()
            raise StreamError("not an audio stream", True)
        if "aac" in ctype or "ogg" in ctype or "opus" in ctype or "flac" in ctype:
            resp.close()
            raise StreamError("%s: MP3 only" % ctype.split(";")[0], True)
        return resp
    raise StreamError("too many redirects")


def get_stream(url, sink, connect=None, user_agent=None, timeout_s=CONNECT_TIMEOUT_S):
    """GET url (following redirects) and hand the body to sink(memoryview)
    piece by piece, never holding it whole; stop early when sink returns
    False. For feeds and other documents too big to buffer (podcast RSS).
    Raises StreamError on an HTTP error. Run it on a worker."""
    for _ in range(MAX_REDIRECTS + 1):
        resp = request(url, connect, None, False, timeout_s, user_agent)
        st = resp.status
        if st in (301, 302, 303, 307, 308):
            loc = resp.headers.get("location")
            resp.close()
            if not loc:
                raise StreamError("redirect without a location")
            url = join_url(url, loc)
            continue
        if st != 200:
            resp.close()
            raise StreamError("HTTP %d" % st)
        try:
            if resp.leftover and sink(memoryview(resp.leftover)) is False:
                return
            buf = bytearray(2048)
            mv = memoryview(buf)
            while True:
                n = _recv_into(resp.sock, mv)
                if not n:
                    return
                if sink(mv[:n]) is False:
                    return
        finally:
            resp.close()
    raise StreamError("too many redirects")


# ── the player ─────────────────────────────────────────────────────────────

def _decoder():
    try:
        import _oreo_audio
    except ImportError:
        raise StreamError("firmware has no MP3 decoder", True)
    return _oreo_audio.MP3Decoder()


class _FileSource:
    def __init__(self, path, start):
        self.f = open(path, "rb")
        try:
            self.f.seek(0, 2)
            self.length = self.f.tell()
            self.f.seek(start)
        except Exception:
            self.length = 0
        self.seekable = True

    def readinto(self, mv):
        return self.f.readinto(mv) or 0

    def close(self):
        _close(self.f)


class Session:
    """One play of one URL: the worker runs step() until it returns False.
    Separate from Player so a new play() never shares state with a worker
    that is still winding down."""

    def __init__(self, player, url, start_s=0.0, start_byte=None):
        self.p = player
        self.url = url
        self.live = True
        self.start_s = start_s
        self.start_byte = start_byte
        self.alive = True
        self.src = None
        self.demux = None
        self.dec = None
        self.retries = 0
        self.retry_at = 0
        self.last_data = _ticks_ms()
        self.eof = False
        self.ring = Ring(STREAM_RING)
        self.rbuf = bytearray(READ_BYTES)
        self.dbuf = bytearray(DECODE_IN)
        self.d_a = self.d_b = 0
        self.pcm = bytearray(PCM_SAMPLES * 2)
        self.pcm_a = self.pcm_b = 0
        self.pcm_hz = 0
        self.bytes_in = 0           # stream (audio) bytes from the start offset
        # ID3v2 skipping at the start of the data (files and episodes)
        self.head = bytearray() if not start_byte else None
        self.skip = 0

    # state is the player's, guarded by the generation check in _set
    def _set(self, state, error=None):
        if self.alive:
            self.p._set_state(self, state, error)

    def close(self):
        if self.src is not None:
            _close(self.src)
            self.src = None
        if self.dec is not None:
            try:
                self.dec.deinit()
            except Exception:
                pass
            self.dec = None

    def _open(self):
        self._set(CONNECTING)
        p = self.p
        rng = self.start_byte or 0
        if self.url.startswith("/"):
            self.src = _FileSource(self.url, rng)
            self.live = False
            p.seekable = True
            p.length = self.src.length
            self.demux = IcyDemux(0)
        else:
            resp = open_stream(self.url, p._connect, rng or None)
            h = resp.headers
            sock = resp.sock
            _settimeout(sock, READ_TIMEOUT_S)
            p.station_name = p.station_name or h.get("icy-name", "")
            try:
                metaint = int(h.get("icy-metaint", "0") or 0)
            except ValueError:
                metaint = 0
            # An icy server or no length: a live stream. Otherwise a file
            # (a podcast episode) that ends.
            clen = h.get("content-length")
            self.live = bool(metaint or h.get("icy-br") or h.get("icy-name")) or clen is None
            ranged = resp.status == 206
            if rng and not ranged:
                self.start_s = 0.0          # the server ignored the Range
            p.seekable = ranged or h.get("accept-ranges", "").lower() == "bytes"
            total = 0
            if ranged:
                cr = h.get("content-range", "")     # bytes a-b/total
                try:
                    total = int(cr.rsplit("/", 1)[1])
                except Exception:
                    total = 0
            elif clen:
                try:
                    total = int(clen)
                except ValueError:
                    total = 0
            p.length = total
            p.offset = rng if ranged else 0
            self.demux = IcyDemux(metaint, self._title)
            self.src = sock
            if resp.leftover:
                self._push(resp.leftover, len(resp.leftover))
        if self.dec is None:
            self.dec = p._decoder()
        else:
            self.dec.reset()
        self.last_data = _ticks_ms()
        self._set(BUFFERING)

    def _title(self, title):
        if self.alive:
            self.p._on_title(title)

    def _push(self, buf, n):
        for a, b in self.demux.feed(buf, n):
            mv = memoryview(buf)[a:b]
            if self.head is not None:
                mv = self._skip_tag(mv)
            if len(mv):
                self.ring.write(mv)
        self.last_data = _ticks_ms()

    def _skip_tag(self, mv):
        """Drop an ID3v2 tag at the start of a file or episode (cover art
        can make it hundreds of KB) instead of feeding it to the decoder."""
        if self.skip:
            k = min(self.skip, len(mv))
            self.skip -= k
            if not self.skip:
                self.head = None
            return mv[k:]
        need = 10 - len(self.head)
        self.head.extend(mv[:need])
        mv = mv[need:]
        if len(self.head) < 10:
            return mv[:0]
        h = self.head
        self.head = None
        size = id3_size(h)
        if size:
            self.skip = size - 10
            if self.skip:
                self.head = bytearray(10)       # keeps _skip_tag active
                return self._skip_tag(mv)
            return mv
        out = bytearray(h)
        out.extend(mv)
        return memoryview(out)

    def _read(self):
        """Read once from the source into the stream ring. False on EOF."""
        room = min(self.ring.free(), READ_BYTES)
        if room <= 0:
            return True
        mv = memoryview(self.rbuf)[:room]
        try:
            n = _recv_into(self.src, mv)
        except OSError as e:
            if _errno(e) in _TIMEOUT_ERRNO:
                return True
            raise
        if not n:
            return False
        self._push(self.rbuf, n)
        return True

    def _decode(self):
        """Move decoded audio into the driver. True if anything moved."""
        audio = self.p.audio
        moved = False
        while self.alive:
            if self.pcm_a < self.pcm_b:
                k = audio.write(memoryview(self.pcm)[self.pcm_a:self.pcm_b], self.pcm_hz)
                if k <= 0:
                    return moved
                self.pcm_a += k
                self.p._played_bytes(k, self.pcm_hz)
                moved = True
                continue
            if self.d_a == self.d_b:
                n = self.ring.read_into(self.dbuf)
                self.d_a, self.d_b = 0, n
            flush = self.eof and self.d_a == self.d_b and not self.ring.used()
            if self.d_a == self.d_b and not flush:
                return moved
            consumed, samples, hz, _ch = self.dec.decode(
                memoryview(self.dbuf)[self.d_a:self.d_b], self.pcm, flush)
            self.d_a += consumed
            self.bytes_in += consumed
            if samples:
                self.pcm_a, self.pcm_b, self.pcm_hz = 0, samples * 2, hz
                if self.p.bitrate == 0:
                    try:
                        self.p.bitrate = self.dec.info()[2]
                    except Exception:
                        pass
            elif consumed == 0:
                return moved            # the decoder wants more than we have
            if flush and not samples:
                return moved
        return moved

    def step(self):
        """One unit of work. Returns False when the session is over."""
        p = self.p
        if not self.alive:
            return False
        try:
            if self.src is None:
                if self.retry_at and _ticks_diff(self.retry_at, _ticks_ms()) > 0:
                    _sleep_ms(50)
                    return True
                self._open()
                return True
            state = p.state
            if not self.eof:
                if not self._read():
                    if self.live:
                        raise StreamError("stream ended")
                    self.eof = True
            if state == BUFFERING:
                want = PREBUFFER if p._first_buffer else REBUFFER
                if self.ring.used() >= min(want, self.ring.size - READ_BYTES) or self.eof:
                    p._first_buffer = False
                    self._set(PLAYING)
            if p.state == PLAYING:
                self._decode()
                if self.eof and not self.ring.used() and self.d_a == self.d_b \
                        and self.pcm_a >= self.pcm_b:
                    if p.audio.buffered() == 0:
                        self._set(ENDED)
                        return False
                    _sleep_ms(20)
                elif not self.eof and not self.ring.used() and self.d_a == self.d_b \
                        and p.audio.buffered() == 0:
                    p.stalls += 1
                    self._set(BUFFERING)
            if self.live and _ticks_diff(_ticks_ms(), self.last_data) > STALL_MS:
                raise StreamError("stream stalled")
            if p.audio.free() < PCM_SAMPLES * 2 and (self.ring.free() == 0 or self.eof):
                _sleep_ms(20)           # everything is full: let the UI run
            return True
        except Exception as e:
            return self._failed(e)

    def _failed(self, e):
        _close(self.src)
        self.src = None
        msg = str(e) if isinstance(e, StreamError) else _reason(e)
        if getattr(e, "fatal", False):
            self._set(ERROR, msg)
            return False
        self.retries += 1
        if self.retries > MAX_RETRIES or not self.live and self.p.state == CONNECTING \
                and self.retries > 1:
            self._set(ERROR, msg)
            return False
        self.p.error = msg
        self.retry_at = _ticks_add(_ticks_ms(), RETRY_MS[min(self.retries, len(RETRY_MS)) - 1])
        # A live stream picks up where it is now: keep what is buffered.
        self.eof = False
        self._set(CONNECTING)
        return True


def _reason(e):
    try:
        from oreoOS import _http
        return _http._reason(e)
    except Exception:
        return str(e) or e.__class__.__name__


class Player:
    def __init__(self, audio, connect=None, decoder=None, threaded=True):
        self.audio = audio
        self._connect = connect or _connect
        self._decoder = decoder or _decoder
        self._threaded = threaded
        self._session = None
        self.state = IDLE
        self.error = None
        self.title = ""
        self.title_seq = 0          # bumps when title or state changes
        self.station_name = ""
        self.url = None
        self.bitrate = 0
        self.seekable = False
        self.length = 0
        self.offset = 0
        self.stalls = 0
        self._start_s = 0.0
        self._played = 0            # bytes handed to the driver this session
        self._rate = 0
        self._first_buffer = True

    # ── controls (main thread) ──────────────────────────────────────────
    def available(self):
        return bool(self.audio is not None and getattr(self.audio, "available", False))

    def play(self, url, name="", start_s=0.0, bitrate_kbps=0):
        """Start url (an http(s) stream or a file path). start_s > 0 asks
        the server for that position with an HTTP Range (needs the bit rate:
        bitrate_kbps, or the one of the stream being replaced)."""
        self.stop(keep_audio=True)
        if not self.available():
            self._set_state(None, ERROR, "needs the PCB badge (speaker)")
            return False
        self.url = url
        self.station_name = name
        self.title = ""
        self.error = None
        self.length = 0
        self.offset = 0
        self.stalls = 0
        self._played = 0
        self._first_buffer = True
        if bitrate_kbps:
            self.bitrate = bitrate_kbps
        elif not start_s:
            self.bitrate = 0
        start_byte = None
        if start_s > 0 and self.bitrate:
            start_byte = int(start_s * self.bitrate * 125)
        elif start_s > 0 and url.startswith("/"):
            start_byte = None
        self._start_s = start_s if start_byte else 0.0
        self.audio.flush()
        s = Session(self, url, self._start_s, start_byte)
        self._session = s
        self.state = CONNECTING
        self.title_seq += 1
        if self._threaded and not self._spawn(s):
            self._threaded = False
        return True

    def stop(self, keep_audio=False):
        s = self._session
        self._session = None
        if s is not None:
            s.alive = False
            if not self._threaded:
                s.close()
        if self.audio is not None and not keep_audio:
            try:
                self.audio.flush()
                self.audio.stop()
            except Exception:
                pass
        if self.state not in (IDLE, ERROR):
            self.state = IDLE
            self.title_seq += 1

    def position_s(self):
        """Seconds into the track (or since a live stream started)."""
        rate = self._rate or 1
        queued = self.audio.buffered() if self.audio is not None else 0
        return max(0.0, self._start_s + (self._played - queued) / (2.0 * rate))

    def duration_s(self):
        if self.length and self.bitrate:
            return self.length / (self.bitrate * 125.0)
        return 0.0

    def can_seek(self):
        return bool(self.seekable and self.bitrate and self.url and
                    self.state in (PLAYING, BUFFERING))

    def seek(self, delta_s):
        """Jump delta_s seconds (negative = back). False when the source
        can't seek (a live stream, or a server without HTTP Range)."""
        if not self.can_seek():
            return False
        pos = max(0.0, self.position_s() + delta_s)
        dur = self.duration_s()
        if dur and pos > dur - 1:
            pos = max(0.0, dur - 1)
        url, name, title = self.url, self.station_name, self.title
        self.play(url, name, start_s=pos, bitrate_kbps=self.bitrate)
        self.title = title
        return True

    def update(self):
        """Call every frame from the app (main thread)."""
        s = self._session
        if s is not None and not self._threaded and s.alive:
            if not s.step():
                s.close()
        a = self.audio
        if a is None or not getattr(a, "available", False):
            return
        if self.state in (PLAYING, BUFFERING) and not a.started and \
                (self.state == PLAYING or a.buffered()):
            a.start()
        elif self.state in (ERROR, ENDED, IDLE) and a.started and not a.buffered():
            a.stop()

    # ── called from the worker ──────────────────────────────────────────
    def _spawn(self, s):
        try:
            import _thread
        except ImportError:
            return False
        old = None
        try:
            old = _thread.stack_size(THREAD_STACK)
        except Exception:
            pass
        try:
            _thread.start_new_thread(self._worker, (s,))
            return True
        except Exception:
            return False
        finally:
            if old is not None:
                try:
                    _thread.stack_size(old)
                except Exception:
                    pass

    def _worker(self, s):
        try:
            while s.alive and s.step():
                pass
        finally:
            s.close()

    def _set_state(self, session, state, error=None):
        if session is not None and session is not self._session:
            return                      # an old session winding down
        if error is not None:
            self.error = error
        elif state in (PLAYING, BUFFERING):
            self.error = None
        if state != self.state:
            self.state = state
            self.title_seq += 1

    def _on_title(self, title):
        if title != self.title:
            self.title = title
            self.title_seq += 1

    def _played_bytes(self, n, rate):
        self._played += n
        self._rate = rate

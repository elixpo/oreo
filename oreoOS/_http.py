"""Raw-socket HTTP GET with a timeout that's actually honoured.

Both `oreoOS.ota` and `oreoOS.store` use this instead of `urequests`
because `urequests`'s `timeout=` flag on the MicroPython 1.28 build we
ship only covers the connect step — body read can hang forever on a
slow / mis-behaving server, wedging the OS run loop for minutes.

Public surface:
    get_url(url, accept=None, timeout_s=4, auth=None,
            on_progress=None) -> bytes | None

`accept` overrides the Accept header (GitHub Contents API needs
`application/vnd.github.raw` for raw file bodies, otherwise we get the
base64-wrapped JSON envelope).

`auth` is an optional ("Bearer <token>") header value.

Follows a small, bounded number of HTTPS redirects. This is required for
GitHub Release assets: their public download URL responds with HTTP 302 and
points at a short-lived release-assets.githubusercontent.com URL.

Returns the response body as bytes on HTTP 200, or None on any unsupported
status / timeout / DNS failure / SSL error. Caller logs / surfaces.
"""

import time

try:
    import socket as _socket
    import ssl    as _ssl
    _OK = True
except ImportError:
    _OK = False


USER_AGENT = "OreoBadge"


def tls_wrap(raw, host):
    """Wrap a connected socket in TLS 1.2+ as a client, with SNI.

    One place for every HTTPS connection on the badge (OTA, App Store,
    GitHub data, the WiFi speed test). The protocol is explicit
    (PROTOCOL_TLS_CLIENT) rather than the deprecated wrap_socket() default.

    Certificates are not verified yet: the badge carries no CA bundle, and
    verification also needs a correct clock before the first request. This
    matches the previous wrap_socket() behaviour (CERT_NONE); verifying
    GitHub's chain is tracked separately. A fresh context per connection
    keeps concurrent fetches (background refresh threads) independent.
    """
    ctx = _ssl.SSLContext(_ssl.PROTOCOL_TLS_CLIENT)
    # TLS 1.2 is the floor. MicroPython's mbedTLS 3.x has no TLS 1.0/1.1 at
    # all and no minimum_version attribute, so this only takes effect where
    # the attribute exists (CPython, host tests).
    try:
        ctx.minimum_version = _ssl.TLSVersion.TLSv1_2
    except Exception:
        pass
    ctx.verify_mode = _ssl.CERT_NONE
    return ctx.wrap_socket(raw, server_hostname=host)
MAX_REDIRECTS = 3
# The largest current OTA asset is ~490 KiB. Keep a hard ceiling so a bad or
# hostile endpoint cannot consume the whole heap, while leaving useful room
# for future generated assets on the 8 MiB-PSRAM target.
MAX_RESPONSE_BYTES = 1024 * 1024


def _bc(msg):
    try:
        print("[http] " + msg)
    except Exception:
        pass


def _progress(callback, phase, received=0):
    """Best-effort network progress pulse for synchronous UI callers."""
    if callback is None:
        return
    try:
        callback(phase, received)
    except Exception:
        pass


def _split_https_url(url):
    """Return (host, port, path) for an HTTPS URL, or None."""
    if not url.startswith("https://"):
        return None
    rest = url[len("https://"):]
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


def _header_value(head, name):
    """Case-insensitive header lookup on the raw response-header bytes."""
    prefix = name.lower().encode() + b":"
    for line in head.split(b"\r\n")[1:]:
        if line.lower().startswith(prefix):
            try:
                return line[len(prefix):].strip().decode()
            except Exception:
                return None
    return None


def _redirect_url(current_url, location):
    """Resolve the HTTPS absolute/root-relative redirects GitHub emits."""
    if not location:
        return None
    if location.startswith("https://"):
        return location
    if location.startswith("/"):
        parsed = _split_https_url(current_url)
        if parsed is not None:
            return "https://" + parsed[0] + location
    return None


def get_url(url, accept=None, timeout_s=4, auth=None, on_progress=None):
    """GET a URL and follow at most MAX_REDIRECTS HTTPS redirects.

    Authorization is deliberately dropped after a cross-host redirect. GitHub
    Release assets use signed CDN URLs and do not need the API token; keeping
    the token on the original host prevents credentials from being forwarded
    to an unrelated redirect target.
    """
    current = url
    request_auth = auth
    allow_auto_auth = True
    for redirect_count in range(MAX_REDIRECTS + 1):
        result = _get_once(current, accept, timeout_s,
                           request_auth, allow_auto_auth, on_progress)
        if result is None:
            return None
        status, head, body = result
        if status == 200:
            if b"\r\ntransfer-encoding: chunked" in (b"\r\n" + head.lower()):
                body = _dechunk(body)
            return body
        if status not in (301, 302, 303, 307, 308):
            parsed = _split_https_url(current)
            _bc("HTTP %d %s" % (status, parsed[0] if parsed else "?"))
            return None
        if redirect_count >= MAX_REDIRECTS:
            _bc("too many redirects")
            return None
        location = _header_value(head, "location")
        next_url = _redirect_url(current, location)
        if next_url is None:
            _bc("invalid redirect")
            return None
        current_host = _split_https_url(current)
        next_host = _split_https_url(next_url)
        if current_host is None or next_host is None:
            return None
        if current_host[0] != next_host[0]:
            request_auth = None
            allow_auto_auth = False
        _bc("redirect " + next_host[0])
        _progress(on_progress, "redirect")
        current = next_url
    return None


def _get_once(url, accept, timeout_s, auth, allow_auto_auth=True,
              on_progress=None):
    if not _OK:
        return None
    parsed = _split_https_url(url)
    if parsed is None:
        return None
    host, port, path = parsed

    accept_hdr = accept or "*/*"

    # Auto-inject a GitHub token for *.github.com calls if one is
    # present in oreoOS.config. Bumps anonymous limit (60 / hr / IP)
    # to 5000 / hr — relevant only for sustained Store / OTA polling.
    # `auth` arg overrides if the caller wants something custom.
    github_host = (host == "github.com" or host == "api.github.com" or
                   host == "raw.githubusercontent.com" or
                   host.endswith(".githubusercontent.com"))
    if allow_auto_auth and auth is None and github_host:
        try:
            from oreoOS.config import GH_TOKEN as _TOK
            if _TOK:
                auth = "Bearer " + _TOK
        except Exception:
            pass
    auth_hdr = ("Authorization: " + auth + "\r\n") if auth else ""

    deadline = time.ticks_add(time.ticks_ms(), int(timeout_s * 1000) + 500)
    s = None
    raw = None
    try:
        _bc("dns " + host)
        _progress(on_progress, "dns")
        addr = _socket.getaddrinfo(host, port)[0][-1]
        _bc("connect " + host + ":" + str(port))
        _progress(on_progress, "connect")
        raw = _socket.socket()
        raw.settimeout(timeout_s)
        raw.connect(addr)
        _bc("ssl")
        _progress(on_progress, "tls")
        s = tls_wrap(raw, host)
        # SSLSocket wraps raw — settimeout on raw doesn't always
        # propagate. Set it again on the wrapper so .read() honours it.
        try:
            s.settimeout(timeout_s)
        except Exception:
            pass

        req = (
            "GET %s HTTP/1.1\r\n"
            "Host: %s\r\n"
            "User-Agent: %s\r\n"
            "Accept: %s\r\n"
            "Accept-Encoding: identity\r\n"
            "%s"
            "Connection: close\r\n\r\n"
        ) % (path, host, USER_AGENT, accept_hdr, auth_hdr)
        _progress(on_progress, "request")
        s.write(req.encode())

        _bc("read")
        buf = bytearray()
        while True:
            # Hard wallclock guard — even if settimeout misfires we
            # bail when the budget is blown.
            if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
                _bc("deadline blown after %d bytes" % len(buf))
                break
            try:
                chunk = s.read(2048)
            except Exception as e:
                _bc("read err: " + str(e))
                break
            if not chunk:
                break
            buf.extend(chunk)
            _progress(on_progress, "read", len(buf))
            if len(buf) > MAX_RESPONSE_BYTES:
                _bc("response too large")
                return None
    except Exception as e:
        _bc("FAIL " + host + ": " + str(e))
        return None
    finally:
        for h in (s, raw):
            try:
                if h is not None:
                    h.close()
            except Exception:
                pass

    # Slice headers / body. Status handling (including redirects) belongs to
    # get_url(), which may need to issue another request.
    head_end = buf.find(b"\r\n\r\n")
    if head_end < 0:
        return None
    head = bytes(buf[:head_end])
    body = bytes(buf[head_end + 4:])

    status = 0
    line0  = head.split(b"\r\n", 1)[0]
    parts  = line0.split(b" ", 2)
    if len(parts) >= 2:
        try: status = int(parts[1])
        except ValueError: status = 0
    return status, head, body


def _dechunk(body):
    out = bytearray()
    i = 0
    while i < len(body):
        nl = body.find(b"\r\n", i)
        if nl < 0:
            break
        try:
            n = int(body[i:nl].split(b";")[0], 16)
        except Exception:
            break
        i = nl + 2
        if n == 0:
            break
        out.extend(body[i:i + n])
        i += n + 2
    return bytes(out)


# ═════════════════════════════════════════════════════════════════════════
# Streaming downloads with connection reuse (OTA)
# ═════════════════════════════════════════════════════════════════════════
#
# get_url() buffers a whole response in a growing bytearray, then copies it
# twice (head/body slices) before the caller writes it out: ~3x the file
# size in RAM and a fresh TLS handshake per request. An OTA patch touches
# many files, and every release asset is a github.com 302 followed by a
# GET on release-assets.githubusercontent.com, so that was two handshakes
# (each hundreds of ms of ECDHE on the ESP32-S3) per file.
#
# download_to_file() instead:
#   * keeps one HTTP/1.1 keep-alive connection per host open across calls
#     (close_pool() when the batch is done), retrying once on a stale one;
#   * reads into one preallocated buffer and writes straight to flash,
#     hashing on the fly, so RAM use is flat regardless of file size;
#   * understands Content-Length and chunked bodies (and drains redirect
#     bodies so the connection stays reusable).

DL_BUF_BYTES = 16 * 1024
_REDIRECTS = (301, 302, 303, 307, 308)

_pool = {}          # (host, port) -> (raw_socket, tls_socket)
_dl_buf = None


def _buf():
    global _dl_buf
    if _dl_buf is None:
        _dl_buf = bytearray(DL_BUF_BYTES)
    return _dl_buf


def _sock_readinto(s, mv):
    try:
        return s.readinto(mv)
    except AttributeError:          # CPython socket (host tests)
        return s.recv_into(mv)


def _sock_write(s, data):
    try:
        w = s.write
    except AttributeError:
        s.sendall(data)
        return
    view = memoryview(data)
    while view:
        n = w(view)
        if n is None:
            n = len(view)
        if n <= 0:
            raise OSError("write failed")
        view = view[n:]


def _close_conn(conn):
    for h in (conn[1], conn[0]):
        try:
            if h is not None:
                h.close()
        except Exception:
            pass


def close_pool():
    """Close every kept-alive connection. Call after a download batch."""
    for k in list(_pool):
        _close_conn(_pool.pop(k))


def _open_conn(host, port, timeout_s):
    addr = _socket.getaddrinfo(host, port)[0][-1]
    raw = _socket.socket()
    try:
        raw.settimeout(timeout_s)
        raw.connect(addr)
        s = tls_wrap(raw, host)
        try:
            s.settimeout(timeout_s)
        except Exception:
            pass
    except Exception:
        try:
            raw.close()
        except Exception:
            pass
        raise
    return (raw, s)


class _Reader:
    """Minimal buffered reader for one HTTP response on a socket."""

    def __init__(self, sock, buf, deadline):
        self.s = sock
        self.buf = buf
        self.mv = memoryview(buf)
        self.a = 0          # first unread byte
        self.b = 0          # end of valid data
        self.deadline = deadline

    def fill(self):
        if time.ticks_diff(self.deadline, time.ticks_ms()) <= 0:
            raise OSError("deadline")
        if self.a == self.b:
            self.a = self.b = 0
        elif self.b == len(self.buf):
            n = self.b - self.a
            self.buf[:n] = self.mv[self.a:self.b]
            self.a, self.b = 0, n
            if n == len(self.buf):
                raise OSError("line too long")
        n = _sock_readinto(self.s, self.mv[self.b:])
        if not n:
            raise OSError("eof")
        self.b += n

    def until(self, sep, limit):
        """Bytes before `sep` (consumed together with it)."""
        while True:
            i = self.buf.find(sep, self.a, self.b)
            if i >= 0:
                out = bytes(self.mv[self.a:i])
                self.a = i + len(sep)
                return out
            if self.b - self.a > limit:
                raise OSError("header too long")
            self.fill()

    def chunk(self, n):
        """A memoryview of 1..n buffered bytes (fills when empty)."""
        if self.a == self.b:
            self.fill()
        k = min(n, self.b - self.a)
        out = self.mv[self.a:self.a + k]
        self.a += k
        return out

    def leftover(self):
        return self.b - self.a


def _parse_head(head):
    """(status, {lower-case header: value}) from raw response-head bytes."""
    lines = head.split(b"\r\n")
    status = 0
    parts = lines[0].split(b" ", 2)
    if len(parts) >= 2:
        try:
            status = int(parts[1])
        except ValueError:
            status = 0
    hdrs = {}
    for ln in lines[1:]:
        k, sep, v = ln.partition(b":")
        if sep:
            hdrs[k.strip().lower().decode()] = v.strip().decode()
    return status, hdrs


def _stream_body(rd, hdrs, sink):
    """Feed the body to sink(memoryview). Returns True if the connection
    is still positioned at a message boundary (reusable)."""
    if "chunked" in hdrs.get("transfer-encoding", "").lower():
        while True:
            line = rd.until(b"\r\n", 1024)
            try:
                size = int(line.split(b";")[0].strip(), 16)
            except ValueError:
                raise OSError("bad chunk size")
            if size == 0:
                while rd.until(b"\r\n", 4096):   # trailers, if any
                    pass
                return True
            while size:
                mv = rd.chunk(size)
                sink(mv)
                size -= len(mv)
            if rd.until(b"\r\n", 2):
                raise OSError("bad chunk end")
    cl = hdrs.get("content-length")
    if cl is not None:
        left = int(cl)
        while left > 0:
            mv = rd.chunk(left)
            sink(mv)
            left -= len(mv)
        return True
    # Neither: body runs to EOF and the connection cannot be reused.
    try:
        while True:
            sink(rd.chunk(len(rd.buf)))
    except OSError:
        pass
    return False


def _hexdigest(h):
    import binascii
    return binascii.hexlify(h.digest()).decode()


def download_to_file(url, dest, expected_sha=None, timeout_s=25,
                     max_bytes=4 * 1024 * 1024, keep_alive=True):
    """GET `url` (following HTTPS redirects) straight into file `dest`.

    Returns True only on HTTP 200 with a complete body whose SHA-256
    matches `expected_sha` (hex) when one is given; otherwise removes any
    partial file and returns False. Connections are kept for reuse by the
    next call unless keep_alive is False; call close_pool() when done.
    """
    if not _OK:
        return False
    try:
        import hashlib
    except ImportError:
        hashlib = None
    current = url
    auth = None
    allow_auto_auth = True
    buf = _buf()
    for _hop in range(MAX_REDIRECTS + 1):
        parsed = _split_https_url(current)
        if parsed is None:
            return False
        host, port, path = parsed
        req_auth = auth
        if allow_auto_auth and req_auth is None and (
                host in ("github.com", "api.github.com")
                or host.endswith(".githubusercontent.com")):
            try:
                from oreoOS.config import GH_TOKEN as _TOK
                if _TOK:
                    req_auth = "Bearer " + _TOK
            except Exception:
                pass
        req = ("GET %s HTTP/1.1\r\nHost: %s\r\nUser-Agent: %s\r\n"
               "Accept: */*\r\nAccept-Encoding: identity\r\n%s"
               "Connection: %s\r\n\r\n") % (
                   path, host, USER_AGENT,
                   ("Authorization: " + req_auth + "\r\n") if req_auth else "",
                   "keep-alive" if keep_alive else "close")
        deadline = time.ticks_add(time.ticks_ms(), int(timeout_s * 1000))
        key = (host, port)
        conn = rd = None
        status = 0
        hdrs = {}
        for attempt in (0, 1):
            conn = _pool.pop(key, None)
            reused = conn is not None
            try:
                if conn is None:
                    _bc("connect " + host)
                    conn = _open_conn(host, port, timeout_s)
                _sock_write(conn[1], req.encode())
                rd = _Reader(conn[1], buf, deadline)
                status, hdrs = _parse_head(rd.until(b"\r\n\r\n", 8192))
                break
            except Exception as e:
                if conn is not None:
                    _close_conn(conn)
                conn = None
                if reused and attempt == 0:
                    continue        # server dropped the idle connection
                _bc("FAIL " + host + ": " + str(e))
                return False
        reusable = False
        try:
            if status in _REDIRECTS:
                reusable = _stream_body(rd, hdrs, lambda mv: None)
                location = hdrs.get("location")
            elif status == 200:
                h = hashlib.sha256() if (hashlib and expected_sha) else None
                total = [0]
                f = open(dest, "wb")
                try:
                    def sink(mv):
                        total[0] += len(mv)
                        if total[0] > max_bytes:
                            raise OSError("too large")
                        f.write(mv)
                        if h is not None:
                            h.update(mv)
                    reusable = _stream_body(rd, hdrs, sink)
                finally:
                    f.close()
                if h is not None and _hexdigest(h) != expected_sha:
                    raise OSError("sha256 mismatch")
            else:
                _bc("HTTP %d %s" % (status, host))
                return False
        except Exception as e:
            _bc("download failed: " + str(e))
            reusable = False
            if status == 200:
                try:
                    import os as _o
                    _o.remove(dest)
                except Exception:
                    pass
            return False
        finally:
            if (keep_alive and reusable and rd is not None
                    and rd.leftover() == 0 and
                    hdrs.get("connection", "").lower() != "close"):
                old = _pool.pop(key, None)
                if old is not None:
                    _close_conn(old)
                _pool[key] = conn
            elif conn is not None:
                _close_conn(conn)
        if status == 200:
            return True
        nxt = _redirect_url(current, location)
        if nxt is None:
            return False
        nh = _split_https_url(nxt)
        if nh is None:
            return False
        if nh[0] != host:
            auth = None
            allow_auto_auth = False
        current = nxt
    return False

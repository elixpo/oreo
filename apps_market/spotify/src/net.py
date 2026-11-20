"""HTTPS requests with any method, for the Spotify app.

oreoOS._http.get_url() only sends GET and hides the status code. The
Spotify Web API needs PUT and POST, and the app has to tell 204 (nothing
playing), 401 (token expired), 404 (no active device) and 429 (slow
down) apart. This module sends one request over the OS's verified TLS
(oreoOS._http.tls_wrap, docs/TLS.md), using the OS's multi-address
connect when it has one, with a hard deadline on the whole exchange:

    status, headers, body = request("PUT", url, {"Authorization": ...}, b"")

status is 0 when the request never got an HTTP answer (offline, DNS,
TLS, timeout). Call it only from the app's worker (oreoOS.cache.Refresh),
never from update() or draw().
"""

import time

USER_AGENT = "FaleraBadge-Spotify"
MAX_BODY = 128 * 1024       # a 20-track library page is ~40 KB


def split_url(url):
    """(host, port, path) for an https:// URL, else None."""
    if not isinstance(url, str) or not url.startswith("https://"):
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


def build_request(method, host, path, headers=None, body=None):
    """The request bytes (head and body) for one HTTP/1.1 exchange."""
    if body is None:
        body = b""
    elif isinstance(body, str):
        body = body.encode("utf-8")
    lines = ["%s %s HTTP/1.1" % (method, path),
             "Host: " + host,
             "User-Agent: " + USER_AGENT,
             "Accept: application/json",
             "Accept-Encoding: identity",
             "Connection: close"]
    for k, v in (headers or {}).items():
        lines.append("%s: %s" % (k, v))
    if body or method in ("POST", "PUT"):
        lines.append("Content-Length: %d" % len(body))
    return ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8") + body


def _dechunk(body):
    out = bytearray()
    i = 0
    while i < len(body):
        nl = body.find(b"\r\n", i)
        if nl < 0:
            break
        try:
            n = int(body[i:nl].split(b";")[0], 16)
        except ValueError:
            break
        i = nl + 2
        if n == 0:
            break
        out.extend(body[i:i + n])
        i += n + 2
    return bytes(out)


def parse_response(buf):
    """(status, {lower-case header: value}, body) from a raw response.
    status 0 when there is no complete header block."""
    end = buf.find(b"\r\n\r\n")
    if end < 0:
        return 0, {}, b""
    head = bytes(buf[:end])
    body = bytes(buf[end + 4:])
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
            try:
                hdrs[k.strip().lower().decode()] = v.strip().decode()
            except Exception:
                pass
    if "chunked" in hdrs.get("transfer-encoding", "").lower():
        body = _dechunk(body)
    else:
        cl = hdrs.get("content-length")
        if cl is not None:
            try:
                want = int(cl)
            except ValueError:
                want = -1
            if 0 <= want < len(body):
                body = body[:want]
            elif want > len(body):
                return 0, hdrs, b""         # cut short: not a result
    return status, hdrs, body


def _complete(buf):
    """True once buf holds a whole Content-Length response (lets us stop
    reading without waiting for the server to close)."""
    end = buf.find(b"\r\n\r\n")
    if end < 0:
        return False
    head = bytes(buf[:end]).lower()
    i = head.find(b"\r\ncontent-length:")
    if i < 0:
        return False
    j = head.find(b"\r\n", i + 2)
    try:
        want = int(head[i + 17:j if j > 0 else len(head)].strip())
    except ValueError:
        return False
    return len(buf) - end - 4 >= want


def _open(host, port, timeout_s):
    from oreoOS import _http
    connect = getattr(_http, "_connect", None)
    if connect is not None:
        raw = connect(host, port, timeout_s)
    else:
        import socket
        addr = socket.getaddrinfo(host, port)[0][-1]
        raw = socket.socket()
        raw.settimeout(timeout_s)
        raw.connect(addr)
    try:
        s = _http.tls_wrap(raw, host)
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
    return raw, s


def _deadline(ms):
    try:
        return time.ticks_add(time.ticks_ms(), ms)
    except AttributeError:
        return int(time.monotonic() * 1000) + ms


def _left(deadline):
    try:
        return time.ticks_diff(deadline, time.ticks_ms())
    except AttributeError:
        return deadline - int(time.monotonic() * 1000)


def request(method, url, headers=None, body=None, timeout_s=8):
    """Send one request. Returns (status, headers, body); (0, {}, b"")
    when no HTTP answer arrived in time."""
    parsed = split_url(url)
    if parsed is None:
        return 0, {}, b""
    host, port, path = parsed
    raw = s = None
    buf = bytearray()
    try:
        raw, s = _open(host, port, timeout_s)
        deadline = _deadline(int(timeout_s * 1000) + 500)
        s.write(build_request(method, host, path, headers, body))
        while True:
            if _left(deadline) <= 0:
                return 0, {}, b""
            try:
                chunk = s.read(2048)
            except Exception:
                break           # EOF reported as an error by some stacks
            if not chunk:
                break
            buf.extend(chunk)
            if len(buf) > MAX_BODY:
                return 0, {}, b""
            if _complete(buf):
                break
    except Exception:
        return 0, {}, b""
    finally:
        for h in (s, raw):
            try:
                if h is not None:
                    h.close()
            except Exception:
                pass
    return parse_response(buf)

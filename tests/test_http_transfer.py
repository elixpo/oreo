"""Host tests for the LAN transfer server (oreoOS/http_server.py).

Covers the streaming multipart writer, the WiFi credential handoff
(authentication, validation, no password in logs) and a full upload over
a real local socket pair.

    python3 -m unittest tests.test_http_transfer -v
"""

import contextlib
import importlib.util
import io
import json
import os
import socket
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class FakeWifi:
    def __init__(self):
        self.saved = {}

    def get_saved(self, ssid):
        n = self.saved.get(ssid)
        return dict(n) if n else None

    def add_saved(self, ssid, password, priority=10, metered=False):
        self.saved[ssid] = {"ssid": ssid, "password": password,
                            "priority": priority, "metered": metered}
        return True

    def saved_ssids(self):
        return {k: True for k in self.saved}

    def nearby(self):
        return [{"ssid": "Cafe", "rssi": -60, "secure": False},
                {"ssid": "Home", "rssi": -50, "secure": True}]

    def ssid(self):
        return "Home"


def load_server():
    wifi = FakeWifi()
    ow = types.ModuleType("oreoWare")
    ow.wifi = wifi
    sys.modules["oreoWare"] = ow
    sys.modules["oreoWare.wifi"] = wifi
    pushes = []
    notif = types.ModuleType("oreoOS.notifications")
    notif.push = lambda *a, **k: pushes.append(a)
    pkg = types.ModuleType("oreoOS")
    pkg.__path__ = []
    pkg.notifications = notif
    sys.modules["oreoOS"] = pkg
    sys.modules["oreoOS.notifications"] = notif
    spec = importlib.util.spec_from_file_location(
        "oreo_http_under_test", ROOT / "oreoOS/http_server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, wifi, pushes


class ChunkSock:
    """recv_into() returns at most `step` bytes per call."""

    def __init__(self, data, step):
        self.data = memoryview(data)
        self.pos = 0
        self.step = step

    def recv_into(self, mv, n):
        k = min(n, self.step, len(self.data) - self.pos)
        mv[:k] = self.data[self.pos:self.pos + k]
        self.pos += k
        return k


class StreamPartTest(unittest.TestCase):
    def setUp(self):
        self.hs, _, _ = load_server()

    def run_stream(self, payload, step, prefix_len):
        closing = b"\r\n--XyZboundary"
        wire = payload + closing + b"--\r\n"
        rest, tail = wire[:prefix_len], wire[prefix_len:]
        out = io.BytesIO()
        n = self.hs._stream_part(ChunkSock(tail, step), out, rest,
                                 len(tail), closing)
        return n, out.getvalue()

    def test_payload_round_trips_across_chunkings(self):
        payload = os.urandom(70_000) + b"\r\n--XyZboundar" + os.urandom(5000)
        for step in (1, 7, 1460, 4096, 65536):
            for prefix in (0, 5, 3000):
                n, got = self.run_stream(payload, step, prefix)
                self.assertEqual(got, payload, (step, prefix))
                self.assertEqual(n, len(payload))

    def test_delimiter_straddling_every_flush_offset(self):
        for size in range(12_250, 12_300):
            payload = b"a" * size
            n, got = self.run_stream(payload, 4096, 0)
            self.assertEqual(got, payload, size)

    def test_writes_are_batched(self):
        class Counting(io.BytesIO):
            writes = 0

            def write(self, b):
                Counting.writes += 1
                return super().write(b)

        closing = b"\r\n--b"
        data = os.urandom(512 * 1024)
        wire = data + closing + b"--\r\n"
        out = Counting()
        self.hs._stream_part(ChunkSock(wire, 1460), out, b"", len(wire), closing)
        self.assertEqual(out.getvalue(), data)
        # ~12 KB per write: 512 KB lands in < 50 writes (old code: 256+).
        self.assertLess(Counting.writes, 50)


class CredentialRulesTest(unittest.TestCase):
    def setUp(self):
        self.hs, _, _ = load_server()

    def test_rules(self):
        e = self.hs.wifi_credentials_error
        self.assertIsNone(e("Home", "longenough"))
        self.assertIsNone(e("Cafe", ""))
        self.assertIsNone(e("Café ☕", "x" * 63))
        self.assertIsNone(e("Raw", "ab" * 32))
        self.assertTrue(e("", "password1"))
        self.assertTrue(e("x" * 33, "password1"))
        self.assertTrue(e("a\nb", "password1"))
        self.assertTrue(e("Home", "short"))
        self.assertTrue(e("Home", "x" * 65))
        self.assertTrue(e("Home", "zz" * 32))
        self.assertTrue(e("Home", "passéword"))
        self.assertTrue(e(5, "password1"))


def request(hs, raw):
    """Run one request through hs._handle over a real socket pair."""
    srv, cli = socket.socketpair()
    try:
        cli.sendall(raw)
        cli.shutdown(socket.SHUT_WR)
        hs._handle(srv)
        srv.close()
        resp = b""
        while True:
            chunk = cli.recv(65536)
            if not chunk:
                break
            resp += chunk
    finally:
        cli.close()
    head, _, body = resp.partition(b"\r\n\r\n")
    return int(head.split(b" ")[1]), body


class WifiHandoffTest(unittest.TestCase):
    def setUp(self):
        self.hs, self.wifi, self.pushes = load_server()
        self.hs._sessions["ABC234"] = {"state": "approved", "last_ms": 0,
                                       "authed_at": 0}
        self.hs._sessions["PEND22"] = {"state": "authed", "last_ms": 0,
                                       "authed_at": 0}

    def post(self, token, obj):
        body = json.dumps(obj).encode()
        raw = (b"POST /wifi?token=" + token.encode() + b" HTTP/1.1\r\n"
               b"Content-Type: application/json\r\n"
               b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
        log = io.StringIO()
        with contextlib.redirect_stdout(log):
            code, resp = request(self.hs, raw)
        return code, resp, log.getvalue()

    def test_requires_approved_session(self):
        for tok in ("", "NOPE99", "PEND22"):
            code, _, _ = self.post(tok, {"ssid": "Evil", "password": "password1"})
            self.assertEqual(code, 403)
        self.assertEqual(self.wifi.saved, {})

    def test_saves_without_logging_password(self):
        secret = "hunter2-very-secret"
        code, resp, log = self.post("ABC234", {"ssid": "Office", "password": secret})
        self.assertEqual(code, 200)
        self.assertEqual(self.wifi.saved["Office"]["password"], secret)
        self.assertNotIn(secret, log)
        self.assertNotIn(secret.encode(), resp)
        self.assertNotIn(secret, repr(self.pushes))
        self.assertFalse(json.loads(resp)["updated"])
        code, resp, _ = self.post("ABC234", {"ssid": "Office", "password": "another-pw"})
        self.assertTrue(json.loads(resp)["updated"])

    def test_rejects_invalid(self):
        code, resp, _ = self.post("ABC234", {"ssid": "Office", "password": "short"})
        self.assertEqual(code, 422)
        self.assertEqual(self.wifi.saved, {})

    def test_rejects_oversized_body(self):
        code, _, _ = self.post("ABC234", {"ssid": "O", "password": "p" * 600})
        self.assertEqual(code, 413)

    def test_nearby_requires_approval_and_has_no_secrets(self):
        self.wifi.add_saved("Home", "topsecret1")
        code, _ = request(self.hs, b"GET /wifi/nearby?token=PEND22 HTTP/1.1\r\n\r\n")
        self.assertEqual(code, 403)
        code, body = request(self.hs, b"GET /wifi/nearby?token=ABC234 HTTP/1.1\r\n\r\n")
        self.assertEqual(code, 200)
        self.assertNotIn(b"topsecret1", body)
        nets = json.loads(body)["networks"]
        self.assertEqual([n["saved"] for n in nets], [False, True])


class UploadEndToEndTest(unittest.TestCase):
    def setUp(self):
        self.hs, _, _ = load_server()
        self.hs._sessions["ABC234"] = {"state": "approved", "last_ms": 0,
                                       "authed_at": 0}
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)

    def tearDown(self):
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def test_upload_over_socket(self):
        data = (b"# notes\n" + os.urandom(200_000).hex().encode())[:300_000]
        b = b"----oreoTestBoundary"
        part = (b"--" + b + b"\r\nContent-Disposition: form-data; name=\"f\"; "
                b"filename=\"notes.txt\"\r\nContent-Type: text/plain\r\n\r\n"
                + data + b"\r\n--" + b + b"--\r\n")
        head = (b"POST /upload?token=ABC234 HTTP/1.1\r\n"
                b"Content-Type: multipart/form-data; boundary=" + b + b"\r\n"
                b"Content-Length: " + str(len(part)).encode() + b"\r\n\r\n")
        srv, cli = socket.socketpair()
        t = threading.Thread(target=lambda: (cli.sendall(head + part)))
        t.start()
        with contextlib.redirect_stdout(io.StringIO()):
            self.hs._handle(srv)
        t.join()
        srv.close()
        resp = cli.recv(4096)
        cli.close()
        self.assertTrue(resp.startswith(b"HTTP/1.1 200"), resp[:80])
        self.assertEqual(Path("documents/notes.txt").read_bytes(), data)


if __name__ == "__main__":
    unittest.main()

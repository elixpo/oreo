"""Badge codes and session ids must come from the secure RNG."""

import importlib.util
import os
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent


def load_http_server():
    spec = importlib.util.spec_from_file_location("oreo_http_server_under_test",
                                                  ROOT / "oreoOS/http_server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BadgeCodeTest(unittest.TestCase):
    def setUp(self):
        self.server = load_http_server()

    def test_codes_use_only_the_unambiguous_charset(self):
        for _ in range(200):
            code = self.server._gen_code()
            self.assertEqual(len(code), 6)
            self.assertTrue(set(code) <= set(self.server.SESSION_CHARSET))
            sid = self.server._new_session_id()
            self.assertEqual(len(sid), 6)
            self.assertTrue(set(sid) <= set(self.server.SESSION_CHARSET))

    def test_codes_come_from_os_urandom(self):
        with mock.patch.object(os, "urandom", side_effect=lambda n: bytes(range(n))):
            self.assertEqual(self.server._gen_code(), self.server.SESSION_CHARSET[:6])

    def test_no_fallback_without_a_secure_rng(self):
        with mock.patch.object(os, "urandom", side_effect=NotImplementedError):
            with self.assertRaises(NotImplementedError):
                self.server._new_session_id()

    def test_characters_are_roughly_uniform(self):
        counts = Counter("".join(self.server._gen_code() for _ in range(4000)))
        expected = 4000 * 6 / len(self.server.SESSION_CHARSET)
        self.assertTrue(all(0.7 * expected < c < 1.3 * expected for c in counts.values()))


if __name__ == "__main__":
    unittest.main()

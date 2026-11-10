"""SerialLink's raw-REPL framing, against a scripted serial port (no hardware)."""

import unittest

import fake  # noqa: F401  (puts the package on sys.path)

from oreo_cli.errors import BadgeError, OreoError, redact
from oreo_cli.transport import SerialLink, explain_open_failure


class ScriptedSerial:
    """Device side of a serial port: replies are queued per write."""

    def __init__(self, replies):
        self.replies = list(replies)   # one reply per host write, in order
        self.rx = bytearray(b">")      # prompt left by entering the raw REPL
        self.written = []

    def write(self, data):
        self.written.append(bytes(data))
        if self.replies:
            self.rx += self.replies.pop(0)

    def inWaiting(self):
        return len(self.rx)

    def read(self, n=1):
        out = bytes(self.rx[:n])
        del self.rx[:n]
        return out


class FakeMpTransport:
    """Just enough of mpremote's SerialTransport for SerialLink."""

    def __init__(self, serial):
        self.serial = serial
        self.in_raw_repl = True
        self.use_raw_paste = True
        self.pasted = []

    def read_until(self, min_num_bytes, ending, timeout=10, data_consumer=None,
                   timeout_overall=None):
        data = b""
        while not data.endswith(ending) and self.serial.inWaiting():
            data += self.serial.read(1)
        return data

    def raw_paste_write(self, code):
        self.pasted.append(code)
        self.serial.write(b"\x04")


def link_with(serial):
    link = SerialLink("/dev/fake")
    link.t = FakeMpTransport(serial)
    return link


class FramingTest(unittest.TestCase):
    def test_exec_streams_stdout_and_keeps_prompt(self):
        ser = ScriptedSerial([b"R\x01", b"hello\r\n@OREO:{}\r\n\x04\x04>"])
        link = link_with(ser)
        got = []
        out = link.exec("print('hello')", consumer=got.append)
        self.assertEqual(out, b"hello\r\n@OREO:{}\r\n")
        self.assertEqual(b"".join(got), out)
        self.assertTrue(link._have_prompt)       # '>' already consumed
        self.assertEqual(link.t.pasted, [b"print('hello')"])

        # Second exec must not wait for a '>' it already read.
        ser.replies = [b"R\x01", b"\x04\x04>"]
        self.assertEqual(link.exec("pass"), b"")

    def test_exec_raises_badge_traceback(self):
        ser = ScriptedSerial([b"R\x01", b"\x04Traceback\r\nOSError: 28\r\n\x04>"])
        link = link_with(ser)
        with self.assertRaises(BadgeError) as cm:
            link.exec("x")
        self.assertIn("OSError: 28", cm.exception.message)

    def test_timeout(self):
        ser = ScriptedSerial([b"R\x01"])
        link = link_with(ser)
        with self.assertRaises(OreoError) as cm:
            link.exec("while 1: pass", timeout=0.05)
        self.assertIn("stopped answering", cm.exception.message)

    def test_unopened_link_is_inert(self):
        link = SerialLink("/dev/does-not-exist")
        link.restart("soft")       # nothing open: nothing happens
        link.close()
        self.assertIsNone(link.t)


class HelpersTest(unittest.TestCase):
    def test_redact(self):
        self.assertEqual(redact("pw='s3cr\\'et' and s3cr'et", ["s3cr'et"]), "pw='***' and ***")
        self.assertEqual(redact("nothing", ["", None]), "nothing")

    def test_missing_port_explained(self):
        msg, hint = explain_open_failure("/dev/oreo-does-not-exist")
        if msg.endswith("does not exist"):
            self.assertIn("oreo devs", hint)


if __name__ == "__main__":
    unittest.main()

"""The CLI never touches the board on --help, help, devs, or when no badge
is reachable, and argument errors are reported before connecting."""

import contextlib
import io
import unittest

from fake import FakePort, FakeTransport, badge_port
from helpers import run_cli

from oreo_cli import discovery
from oreo_cli.errors import ManyBadges, NoBadge


class DiscoveryTest(unittest.TestCase):
    def test_single_badge_is_picked(self):
        self.assertEqual(discovery.pick(comports=[badge_port("/dev/ttyACM3")], env={}),
                         "/dev/ttyACM3")

    def test_other_devices_are_ignored(self):
        ports = [FakePort("/dev/ttyUSB0", 0x10C4, 0xEA60), FakePort("/dev/ttyS0"),
                 badge_port("COM7")]
        self.assertEqual(discovery.pick(comports=ports, env={}), "COM7")

    def test_no_badge_explains_known_devices(self):
        ports = [FakePort("/dev/ttyACM0", 0x303A, 0x1001)]
        with self.assertRaises(NoBadge) as cm:
            discovery.pick(comports=ports, env={})
        self.assertIn("303a:1001", cm.exception.hint)

    def test_several_badges_need_a_port(self):
        with self.assertRaises(ManyBadges) as cm:
            discovery.pick(comports=[badge_port("/dev/ttyACM0"), badge_port("/dev/ttyACM1")],
                           env={})
        self.assertIn("--port", cm.exception.hint)

    def test_port_and_env_override_without_enumerating(self):
        def boom():
            raise AssertionError("enumerated ports")
        self.assertEqual(discovery.pick("/dev/x", comports=boom, env={}), "/dev/x")
        self.assertEqual(discovery.pick(comports=boom, env={"OREO_PORT": "COM3"}), "COM3")


class NoTouchTest(unittest.TestCase):
    def _exit(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as cm:
            run_cli(argv)
        return cm.exception.code, out.getvalue()

    def test_help_does_not_touch(self):
        code, out = self._exit(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("oreo help <command>", out)

    def test_every_command_has_help(self):
        from oreo_cli.main import HELP
        for name in HELP:
            if name == "help":
                continue
            code, out = self._exit(["help", name])
            self.assertEqual(code, 0, name)
            self.assertIn(HELP[name][0], out)

    def test_help_for_unknown_command(self):
        r = run_cli(["help", "nope"])
        self.assertEqual(r.rc, 2)
        self.assertIn("no command called", r.out)

    def test_no_badge_means_no_connection(self):
        for argv in (["info"], ["ls"], ["wifi", "scan"], ["apps"], ["doctor"]):
            r = run_cli(argv, ports=[])
            self.assertEqual(r.links, [], argv)
            self.assertNotEqual(r.rc, 0, argv)
        r = run_cli(["info"], ports=[])
        self.assertIn("no Oreo Badge found", r.out)

    def test_devs_lists_without_opening(self):
        r = run_cli(["devs", "--all"], ports=[badge_port("/dev/ttyACM0", "SN42"),
                                              FakePort("/dev/ttyUSB0", 0x1A86, 0x7523)])
        self.assertEqual(r.rc, 0)
        self.assertEqual(r.links, [])
        self.assertIn("/dev/ttyACM0", r.out)
        self.assertIn("SN42", r.out)
        self.assertIn("CH340", r.out)

    def test_devs_without_badge(self):
        r = run_cli(["devs"], ports=[])
        self.assertEqual(r.rc, 3)
        self.assertIn("no badge connected", r.out)

    def test_argument_errors_come_before_connecting(self):
        fake = FakeTransport()
        self.addCleanup(fake.cleanup)
        for argv in (["apps", "install"], ["apps", "remove"], ["wifi", "connect"],
                     ["wifi", "forget"], ["push", "/no/such/file", "/"],
                     ["add", "notes.pdf"], ["run", "/no/such.py"]):
            r = run_cli(argv, fake=fake)
            self.assertNotEqual(r.rc, 0, argv)
            self.assertEqual(fake.enters, 0, argv)
            self.assertEqual(fake.sent, [], argv)

    def test_wifi_connect_without_terminal_does_not_touch(self):
        fake = FakeTransport()
        self.addCleanup(fake.cleanup)
        r = run_cli(["wifi", "connect", "Home"], fake=fake)
        self.assertEqual(r.rc, 1)
        self.assertIn("--password-stdin", r.out)
        self.assertEqual(fake.sent, [])


class RestartTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeTransport()
        self.addCleanup(self.fake.cleanup)

    def test_oreoos_restarts_after_a_command(self):
        r = run_cli(["ls"], fake=self.fake)
        self.assertEqual(r.rc, 0)
        self.assertEqual(self.fake.restarts, ["soft"])

    def test_restart_mode_is_selectable(self):
        run_cli(["--reset", "none", "ls"], fake=self.fake)
        run_cli(["--reset", "hard", "ls"], fake=self.fake)
        self.assertEqual(self.fake.restarts, ["none", "hard"])

    def test_restarts_even_when_the_command_fails(self):
        r = run_cli(["ls", "/missing"], fake=self.fake)
        self.assertEqual(r.rc, 1)
        self.assertIn("not found", r.out)
        self.assertEqual(self.fake.restarts, ["soft"])


if __name__ == "__main__":
    unittest.main()

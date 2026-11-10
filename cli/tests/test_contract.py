"""Contract tests: the CLI's badge snippets against the real OreoOS modules.

When the CLI runs inside an OreoOS checkout, load the real oreoWare/wifi.py
(with a fake `network` driver, as tests/test_wifi_logic.py does) and the
real oreoOS/storage.py into the FakeTransport, so a renamed or changed
badge API breaks these tests instead of the badge. Skipped when the CLI is
tested on its own.
"""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

from fake import FakeTransport

from oreo_cli.badge import Badge

REPO = Path(__file__).resolve().parents[2]
WIFI = REPO / "oreoWare" / "wifi.py"
STORAGE = REPO / "oreoOS" / "storage.py"


class FakeWLAN:
    def __init__(self, air):
        self.air = air                 # ssid -> (password, rssi)
        self._active = False
        self.connected = False
        self.status_code = 1001        # STAT_CONNECTING
        self.target = None

    def active(self, on=None):
        if on is None:
            return self._active
        self._active = bool(on)

    def disconnect(self):
        self.connected = False

    def connect(self, ssid, pw):
        self.target = ssid
        if ssid not in self.air:
            self.status_code = 201     # NO_AP_FOUND
        elif self.air[ssid][0] != pw:
            self.status_code = 202     # AUTH_FAIL
        else:
            self.connected = True
            self.status_code = 1010    # GOT_IP

    def isconnected(self):
        return self.connected

    def status(self, *a):
        if a == ("rssi",):
            return -50
        return self.status_code

    def config(self, *a, **k):
        if a == ("essid",):
            return self.target or ""
        return None

    def ifconfig(self):
        return ("10.0.0.7", "255.255.255.0", "10.0.0.1", "10.0.0.1")

    def scan(self):
        return [(s.encode(), b"\x00" * 6, 6, rssi, 3 if pw else 0, False)
                for s, (pw, rssi) in self.air.items()]


def load_module(path, name, **patch):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for k, v in patch.items():
        setattr(mod, k, v)
    return mod


@unittest.skipUnless(WIFI.exists(), "not inside an OreoOS checkout")
class RealWifiContractTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeTransport()
        self.addCleanup(self.fake.cleanup)
        self.wlan = FakeWLAN({"Home": ("hunter2", -48), "Cafe": ("", -71)})
        net = types.ModuleType("network")
        net.STA_IF = 0
        net.WLAN = lambda _if: self.wlan
        net.hostname = lambda *_: None
        patcher = mock.patch.dict(sys.modules, {"network": net, "_thread": None})
        patcher.start()
        self.addCleanup(patcher.stop)
        root = Path(self.fake.root)
        wifi = load_module(WIFI, "oreo_wifi_contract",
                           time=self.fake.clock,
                           _SAVED_PATH=str(root / "wifi.json"),
                           _SEEN_PATH=str(root / "wifi_seen.json"),
                           print=lambda *a, **k: None)
        wifi._secrets_networks = lambda: []
        self.wifi = wifi
        self.fake.wifi = wifi
        self.badge = Badge(self.fake)

    def test_scan(self):
        nets = self.badge.wifi_scan()
        self.assertEqual([n["ssid"] for n in nets], ["Home", "Cafe"])
        self.assertTrue(nets[0]["secure"])
        self.assertFalse(nets[1]["secure"])
        self.assertFalse(nets[0]["saved"])

    def test_connect_save_list_forget(self):
        r = self.badge.wifi_connect("Home", "hunter2")
        self.assertEqual(r["result"], "ok")
        self.assertEqual(r["ip"], "10.0.0.7")
        self.assertTrue(r["saved"])
        saved = self.badge.wifi_saved()
        self.assertEqual([n["ssid"] for n in saved], ["Home"])
        self.assertNotIn("password", saved[0])
        self.assertTrue(saved[0]["last"])
        for out in self.fake.outputs:
            self.assertNotIn(b"hunter2", out)
        self.assertEqual(self.badge.wifi_forget("Home"), (True, False))
        self.assertEqual(self.badge.wifi_forget("Home"), (False, False))

    def test_wrong_password_and_missing_network(self):
        self.assertEqual(self.badge.wifi_connect("Home", "nope")["result"], "bad_password")
        self.assertEqual(self.badge.wifi_connect("Gone", "x")["result"], "not_found")
        self.assertEqual(self.wifi.list_saved(), [])

    def test_save_only_and_online(self):
        self.assertTrue(self.badge.wifi_save("Cafe", ""))
        r = self.badge.wifi_online()
        self.assertTrue(r["online"])
        self.assertEqual(r["ip"], "10.0.0.7")

    def test_forgetting_a_deploy_network_is_flagged(self):
        # Networks from the deploy-time .env are merged back into the saved
        # list by the badge, so `oreo wifi forget` warns about them.
        self.wifi._secrets_networks = lambda: [{"ssid": "Office", "password": "pw"}]
        self.assertTrue(self.badge.wifi_save("Cafe", ""))
        self.assertEqual(self.badge.wifi_forget("Office"), (True, True))
        self.assertEqual(self.badge.wifi_forget("Cafe"), (True, False))


@unittest.skipUnless(STORAGE.exists(), "not inside an OreoOS checkout")
class RealStorageContractTest(unittest.TestCase):
    def test_info_uses_storage_usage(self):
        fake = FakeTransport()
        self.addCleanup(fake.cleanup)
        fake.put("/apps/gallery/assets/optimized/a.rz565", b"x" * 1000)
        fake.put("/documents/b.mdz", b"y" * 300)
        storage = load_module(STORAGE, "oreo_storage_contract", os=fake.os)
        fake.storage = storage
        info = Badge(fake).info()
        buckets = info["storage"]["buckets"]
        self.assertEqual(buckets["gallery"]["bytes"], 1000)
        self.assertEqual(buckets["documents"]["bytes"], 300)
        self.assertGreater(info["storage"]["stats"]["free"], 0)


if __name__ == "__main__":
    unittest.main()

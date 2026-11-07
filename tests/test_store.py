"""Hardware-free tests for the App Store: catalogue, install, partition data.

    python3 -m unittest discover -s tests -v
"""

import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(relative_path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


store = load("oreoOS/store.py", "oreo_store_under_test")
store_io = load("oreoOS/store_io.py", "oreo_store_io_under_test")
indexer = load("tools/build_store_index.py", "oreo_store_index_under_test")
INDEX = json.loads((ROOT / "apps_market" / "index.json").read_text())


def partitions():
    csv = ROOT / "firmware" / "boards" / "OREO_BADGE" / "partitions-oreo-badge.csv"
    out = {}
    for line in csv.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            f = [x.strip() for x in line.split(",")]
            out[f[0]] = (int(f[3], 0), int(f[4], 0))
    return out


class CatalogueTest(unittest.TestCase):
    def test_index_is_fresh(self):
        # Regenerate with: python3 tools/build_store_index.py
        self.assertEqual(indexer.main(["--check"]), 0)

    def test_every_entry_parses_with_metadata(self):
        apps, featured = store.parse_index(json.dumps(INDEX))
        self.assertEqual(len(apps), len(INDEX["apps"]))
        self.assertTrue(featured)
        for e in apps:
            for field in ("name", "tagline", "description", "category",
                          "author", "version", "icon"):
                self.assertTrue(e[field], "%s has no %s" % (e["id"], field))
            self.assertIn(e["category"], indexer.CATEGORIES)
            self.assertLessEqual(len(e["tagline"]), 24, e["id"])

    def test_market_folders_are_listed(self):
        listed = {e["path"] for e in INDEX["apps"]}
        for p in (ROOT / "apps_market").iterdir():
            if (p / "manifest.json").exists():
                self.assertIn("apps_market/" + p.name, listed)

    def test_default_image_is_the_default_app_list(self):
        shipped = {p.name for p in (ROOT / "apps").iterdir()
                   if (p / "manifest.json").exists()}
        self.assertEqual(shipped, set(store.DEFAULT_APPS))
        for e in INDEX["apps"]:
            self.assertNotIn(e["id"], store.DEFAULT_APPS)

    def test_device_file_rule_matches_the_indexer(self):
        for p in (ROOT / "apps_market").rglob("*"):
            if p.is_file():
                rel = "/".join(p.relative_to(ROOT / "apps_market").parts[1:])
                self.assertEqual(store.device_file(rel),
                                 indexer.device_file(rel), rel)

    def test_doom_data_fits_its_partition(self):
        doom = [e for e in INDEX["apps"] if e["id"] == "doom"][0]
        data = doom["data"]
        self.assertEqual(data["partition"], "doom")
        self.assertIn("doom", store_io.ALLOWED_PARTITIONS)
        self.assertTrue(data["url"].startswith(
            "https://github.com/elixpo/oreo/releases/download/"))
        self.assertEqual(len(data["sha256"]), 64)
        self.assertLessEqual(data["size"], partitions()["doom"][1])

    def test_unsafe_entries_are_dropped(self):
        good = {"id": "racer", "path": "apps_market/racer",
                "files": [["main.py", 1], ["../boot.py", 1],
                          ["/main.py", 1], ["assets/raw/x.png", 1],
                          ["src/app.py", 2]]}
        e = store.normalise_entry(good)
        self.assertEqual(e["files"], [("main.py", 1), ("src/app.py", 2)])
        self.assertIsNone(store.normalise_entry(dict(good, id="../x")))
        self.assertIsNone(store.normalise_entry(dict(good, id="a b")))
        self.assertIsNone(store.normalise_entry(
            dict(good, path="oreoOS/../apps")))
        bad_data = dict(good, data={"partition": "doom", "url": "http://x",
                                    "size": 1, "sha256": "0" * 64})
        self.assertIsNone(store.normalise_entry(bad_data)["data"])

    def test_versions(self):
        self.assertTrue(store.is_newer("0.2", "0.1"))
        self.assertTrue(store.is_newer("1.10", "1.9"))
        self.assertFalse(store.is_newer("1.0", "1"))
        self.assertFalse(store.is_newer("0.1", "0.1.0"))
        self.assertTrue(store.is_newer("2.0b", "1.9"))


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.tmp)
        os.mkdir("apps")
        self.saved = {k: getattr(store, k) for k in
                      ("TMP_DIR", "DATA_DIR", "wifi_up", "_io", "_apps",
                       "_featured", "_invalidate_launcher")}
        store.TMP_DIR = self.tmp + "/stage"
        store.DATA_DIR = self.tmp + "/data"
        store.wifi_up = lambda: True
        store._invalidate_launcher = lambda: None
        self.remote = {
            "main.py": b"from .src.app import App\n",
            "manifest.json": b'{"name": "Racer", "type": "app", "version": "0.2"}',
            "src/app.py": b"class App: pass\n",
        }
        self.fail = set()
        test = self

        class FakeIO:
            CHUNK = 64

            @staticmethod
            def download_file(url, path, size, cb=None, buf=None):
                rel = url.split("/apps_market/racer/", 1)[1]
                if rel in test.fail:
                    return False
                body = test.remote[rel]
                if size >= 0 and size != len(body):
                    return False
                with open(path, "wb") as f:
                    f.write(body)
                if cb:
                    cb(len(body), len(body))
                return True

        store._io = lambda: FakeIO
        files = [[k, len(v)] for k, v in self.remote.items()]
        store._apps = [store.normalise_entry({
            "id": "racer", "path": "apps_market/racer", "version": "0.2",
            "files": files, "size": sum(f[1] for f in files)})]
        store._featured = []
        store.forget_installed()

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(store, k, v)
        store.forget_installed()
        os.chdir(self.cwd)
        shutil.rmtree(self.tmp)

    def test_install_update_uninstall(self):
        entry = store.find("racer")
        self.assertEqual(store.app_state(entry), store.INSTALL)
        seen = []
        ok, msg = store.install("racer", lambda r, t, l: seen.append((r, t)))
        self.assertTrue(ok, msg)
        self.assertEqual(seen[-1][0], seen[-1][1])
        self.assertTrue(os.path.exists("apps/racer/src/app.py"))
        self.assertEqual(store.app_state(entry), store.OPEN)

        entry["version"] = "0.3"
        self.assertEqual(store.app_state(entry), store.UPDATE)
        # A failed update keeps the installed version intact.
        self.fail.add("src/app.py")
        ok, _ = store.install("racer")
        self.assertFalse(ok)
        self.assertTrue(os.path.exists("apps/racer/main.py"))
        self.assertFalse(os.path.exists(store.TMP_DIR + "/racer"))

        ok, _ = store.uninstall("racer")
        self.assertTrue(ok)
        self.assertFalse(os.path.exists("apps/racer"))
        self.assertEqual(store.app_state(entry), store.INSTALL)

    def test_failed_install_leaves_nothing(self):
        self.fail.add("manifest.json")
        ok, _ = store.install("racer")
        self.assertFalse(ok)
        self.assertFalse(os.path.exists("apps/racer"))

    def test_default_apps_cannot_be_uninstalled(self):
        os.makedirs("apps/settings")
        for app_id in store.DEFAULT_APPS:
            ok, _ = store.uninstall(app_id)
            self.assertFalse(ok)
        self.assertTrue(os.path.exists("apps/settings"))


class FakePartition:
    def __init__(self, blocks):
        self.blocks = blocks
        self.data = bytearray(b"\xAA" * (blocks * 4096))
        self.writes = []

    def ioctl(self, op, arg):
        if op == 4:
            return self.blocks
        if op == 5:
            return 4096
        if op == 6:
            self.data[arg * 4096:(arg + 1) * 4096] = b"\xff" * 4096
            self.writes.append(("erase", arg))
            return 0

    def writeblocks(self, blk, buf):
        assert 0 <= blk < self.blocks
        self.data[blk * 4096:(blk + 1) * 4096] = buf
        self.writes.append(("write", blk))

    def readblocks(self, blk, buf):
        buf[:] = self.data[blk * 4096:(blk + 1) * 4096]


def fake_stream(image, cut=None):
    def stream(url, sink, on_progress=None, timeout_s=0):
        mv = memoryview(image if cut is None else image[:cut])
        for i in range(0, len(mv), 1000):
            if sink(mv[i:i + 1000]) is False:
                return None
        return len(mv)
    return stream


class PartitionTest(unittest.TestCase):
    def setUp(self):
        self.image = b"OWZ1" + bytes(range(256)) * 50
        self.sha = hashlib.sha256(self.image).hexdigest()

    def test_writes_block_zero_last_and_verifies(self):
        part = FakePartition(8)
        ok, msg = store_io.install_partition(
            "doom", "https://x", len(self.image), self.sha,
            stream_fn=fake_stream(self.image), part=part)
        self.assertTrue(ok, msg)
        self.assertEqual(part.writes[0], ("erase", 0))
        self.assertEqual(part.writes[-1], ("write", 0))
        self.assertEqual(bytes(part.data[:len(self.image)]), self.image)
        self.assertTrue(store_io.partition_matches(
            "doom", len(self.image), self.sha, part=part))

    def test_bad_checksum_leaves_block_zero_erased(self):
        part = FakePartition(8)
        ok, _ = store_io.install_partition(
            "doom", "https://x", len(self.image), "0" * 64,
            stream_fn=fake_stream(self.image), part=part)
        self.assertFalse(ok)
        self.assertEqual(bytes(part.data[:4]), b"\xff" * 4)
        self.assertFalse(store_io.partition_matches(
            "doom", len(self.image), self.sha, part=part))

    def test_short_download_is_rejected(self):
        part = FakePartition(8)
        ok, _ = store_io.install_partition(
            "doom", "https://x", len(self.image), self.sha,
            stream_fn=fake_stream(self.image, cut=5000), part=part)
        self.assertFalse(ok)
        self.assertEqual(bytes(part.data[:4]), b"\xff" * 4)

    def test_failed_request_keeps_existing_data(self):
        part = FakePartition(8)
        before = bytes(part.data)
        ok, _ = store_io.install_partition(
            "doom", "https://x", len(self.image), self.sha,
            stream_fn=lambda *a: None, part=part)
        self.assertFalse(ok)
        self.assertEqual(bytes(part.data), before)
        self.assertEqual(part.writes, [])

    def test_never_writes_past_the_partition(self):
        part = FakePartition(2)
        ok, _ = store_io.install_partition(
            "doom", "https://x", len(self.image), self.sha,
            stream_fn=fake_stream(self.image), part=part)
        self.assertFalse(ok)                  # 12.8 KB image, 8 KB partition
        self.assertEqual(part.writes, [])

    def test_only_allowed_partitions(self):
        for name in ("vfs", "nvs", "factory", "phy_init"):
            ok, _ = store_io.install_partition(
                name, "https://x", 4, "0" * 64, part=FakePartition(4))
            self.assertFalse(ok)


class FakeSocket:
    def __init__(self, raw):
        self.raw = raw
        self.pos = 0

    def readline(self):
        end = self.raw.find(b"\n", self.pos)
        end = len(self.raw) if end < 0 else end + 1
        line = self.raw[self.pos:end]
        self.pos = end
        return line

    def readinto(self, mv):
        n = min(len(mv), len(self.raw) - self.pos, 7)
        mv[:n] = self.raw[self.pos:self.pos + n]
        self.pos += n
        return n


class HttpTest(unittest.TestCase):
    def body(self, raw):
        s = FakeSocket(raw)
        status, length, chunked, location = store_io.read_head(s)
        out = bytearray()
        n = store_io.read_body(s, length, chunked, out.extend)
        return status, location, n, bytes(out)

    def test_content_length(self):
        st, _, n, out = self.body(
            b"HTTP/1.1 200 OK\r\nContent-Length: 11\r\n\r\nhello world")
        self.assertEqual((st, n, out), (200, 11, b"hello world"))

    def test_chunked(self):
        st, _, n, out = self.body(
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
            b"5\r\nhello\r\n6;x=1\r\n world\r\n0\r\n\r\n")
        self.assertEqual((n, out), (11, b"hello world"))

    def test_truncated_body_fails(self):
        _, _, n, _ = self.body(
            b"HTTP/1.1 200 OK\r\nContent-Length: 20\r\n\r\nshort")
        self.assertIsNone(n)

    def test_redirect_location(self):
        st, loc, _, _ = self.body(
            b"HTTP/1.1 302 Found\r\nLocation: https://cdn.example/x\r\n"
            b"Content-Length: 0\r\n\r\n")
        self.assertEqual((st, loc), (302, "https://cdn.example/x"))


if __name__ == "__main__":
    unittest.main()

"""Benchmark the badge's HTTP upload path on the host.

Runs oreoOS/http_server.py under CPython over a local socket pair and
reports wall time, file write() calls and recv calls per upload. Absolute
speeds say nothing about the ESP32; the call counts carry over directly.

    python3 tools/bench_transfer.py              # current tree
    python3 tools/bench_transfer.py --compare main   # also a git ref
"""
import argparse, subprocess
import sys, os, io, socket, threading, time, tempfile, contextlib, importlib.util, builtins
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT + "/tests")
import test_http_transfer as T

def load(path):
    T.load_server()  # installs fakes
    spec = importlib.util.spec_from_file_location("hs_" + os.path.basename(path).replace(".", "_"), path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m

def run(m, size, name):
    m._sessions["ABC234"] = {"state": "approved", "last_ms": 0, "authed_at": 0}
    # Time the stream only; format validation is not what is measured.
    m._validate_uploaded_asset = lambda *a: True
    data = os.urandom(size)
    b = b"----oreoBench"
    part = (b"--" + b + b"\r\nContent-Disposition: form-data; name=\"f\"; filename=\"x.txt\"\r\n\r\n"
            + data + b"\r\n--" + b + b"--\r\n")
    head = (b"POST /upload?token=ABC234 HTTP/1.1\r\nContent-Type: multipart/form-data; boundary=" + b +
            b"\r\nContent-Length: " + str(len(part)).encode() + b"\r\n\r\n")
    writes = [0]
    real_open = builtins.open
    class W:
        def __init__(s, f): s.f = f
        def write(s, x): writes[0] += 1; return s.f.write(x)
        def close(s): s.f.close()
    m.open = lambda p, mode="r": W(real_open(p, mode)) if "w" in mode else real_open(p, mode)
    srv, cli = socket.socketpair()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 5840)   # ~lwIP TCP_WND
    def send():
        cli.sendall(head + part); cli.shutdown(socket.SHUT_WR)
    t = threading.Thread(target=send); t.start()
    calls = {"recv": 0, "bytes_objs": 0}
    class P:
        def __init__(s, k): s.k = k
        def recv(s, n):
            calls["recv"] += 1; d = s.k.recv(n); calls["bytes_objs"] += 1; return d
        def recv_into(s, mv, n): calls["recv"] += 1; return s.k.recv_into(mv, n)
        def __getattr__(s, a): return getattr(s.k, a)
    srv_p = P(srv)
    t0 = time.perf_counter()
    with contextlib.redirect_stdout(io.StringIO()):
        m._handle(srv_p)
    dt = time.perf_counter() - t0
    t.join(); srv.close(); cli.close()
    assert open("documents/x.txt", "rb").read() == data
    os.remove("documents/x.txt")
    print("%-4s %5d KB  %6.1f ms  %7.1f MB/s  flash writes=%5d  recv calls=%5d  per-recv bytes objs=%5d" %
          (name, size // 1024, dt * 1000, size / dt / 1e6, writes[0], calls["recv"], calls["bytes_objs"]))

ap = argparse.ArgumentParser()
ap.add_argument("--compare", metavar="REF", help="git ref to benchmark as 'old'")
args = ap.parse_args()
mods = []
if args.compare:
    src = subprocess.run(["git", "-C", ROOT, "show", args.compare + ":oreoOS/http_server.py"],
                         check=True, capture_output=True).stdout
    tmp = tempfile.mkdtemp()
    with open(os.path.join(tmp, "http_old.py"), "wb") as f:
        f.write(src)
    mods.append(("old", load(os.path.join(tmp, "http_old.py"))))
mods.append(("new", load(ROOT + "/oreoOS/http_server.py")))
os.chdir(tempfile.mkdtemp())
for size in (256 * 1024, 2 * 1024 * 1024):
    for name, m in mods:
        run(m, size, name)

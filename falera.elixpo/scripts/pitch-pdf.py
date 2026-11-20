#!/usr/bin/env python3
"""Screenshot the sponsor deck (/pitch/1/ ... /pitch/N/) and combine it into a PDF.

Each slide is a fixed 1920x1080 page. This renders every slide with headless
Chrome or Chromium at exactly that size, saves the PNGs, and writes them into
one PDF, losslessly (each page is the PNG's pixels, Flate-compressed, at
16:9, 13.333 x 7.5 in).

Start the site first (`npm run dev`, or serve `out/` after a build), then:

    python3 scripts/pitch-pdf.py
    python3 scripts/pitch-pdf.py --base http://localhost:3000 --out ~/Documents/falera-pitch

Needs Pillow. Chrome is found from $CHROME, the usual command names, or
Playwright's browser cache (`npx playwright install chromium-headless-shell`).
If full Chrome hangs in headless mode, point $CHROME at chrome-headless-shell.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zlib
from pathlib import Path

W, H = 1920, 1080


def find_chrome() -> str:
    env = os.environ.get("CHROME")
    if env:
        return env
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    cache = os.path.expanduser("~/.cache/ms-playwright")
    for pattern in (
        "chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell",
        "chromium-*/chrome-linux*/chrome",
        "chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium",
    ):
        hits = sorted(glob.glob(os.path.join(cache, pattern)))
        if hits:
            return hits[-1]
    sys.exit("No Chrome or Chromium found; set CHROME=/path/to/chrome.")


def slide_count(base: str) -> int:
    """Count the slides from the index page's links."""
    with urllib.request.urlopen(f"{base}/pitch/", timeout=120) as r:
        html = r.read().decode("utf-8", "replace")
    nums = {int(m) for m in re.findall(r'href="/pitch/(\d+)/"', html)}
    if not nums:
        sys.exit(f"No slides linked from {base}/pitch/; is the site running?")
    return max(nums)


def shoot(chrome: str, url: str, png: Path) -> None:
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run(
            [
                chrome,
                # chrome-headless-shell is always headless and takes no flag.
                *([] if "headless-shell" in chrome else ["--headless=new"]),
                "--disable-gpu",
                "--no-first-run",
                "--hide-scrollbars",
                "--force-device-scale-factor=1",
                f"--user-data-dir={profile}",
                f"--window-size={W},{H}",
                "--virtual-time-budget=8000",
                f"--screenshot={png}",
                url,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=180,
        )


def write_pdf(pngs: list[Path], out: Path) -> None:
    """A minimal PDF writer: one page per image, pixels kept exactly."""
    from PIL import Image

    objs: list[bytes] = []

    def add(data: bytes) -> int:
        objs.append(data)
        return len(objs)

    pw, ph = 960, 540  # points: 13.333 x 7.5 in, 16:9
    pages_id = add(b"")  # placeholder, filled in below
    kids = []
    for png in pngs:
        im = Image.open(png).convert("RGB")
        w, h = im.size
        raw = zlib.compress(im.tobytes(), 9)
        img = add(
            b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB "
            b"/BitsPerComponent 8 /Filter /FlateDecode /Length %d >>\nstream\n" % (w, h, len(raw))
            + raw
            + b"\nendstream"
        )
        content = b"q %d 0 0 %d 0 0 cm /Im0 Do Q" % (pw, ph)
        cid = add(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
        kids.append(
            add(
                b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %d %d] "
                b"/Resources << /XObject << /Im0 %d 0 R >> >> /Contents %d 0 R >>"
                % (pages_id, pw, ph, img, cid)
            )
        )
    objs[pages_id - 1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % k for k in kids),
        len(kids),
    )
    info = add(b"<< /Title (FaleraOS sponsor deck) /Author (Elixpo) >>")
    catalog = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)

    buf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, data in enumerate(objs, 1):
        offsets.append(len(buf))
        buf += b"%d 0 obj\n" % i + data + b"\nendobj\n"
    xref = len(buf)
    buf += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        buf += b"%010d 00000 n \n" % off
    buf += b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objs) + 1,
        catalog,
        info,
        xref,
    )
    out.write_bytes(bytes(buf))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="http://localhost:3000", help="site URL (default: %(default)s)")
    ap.add_argument("--out", default="~/Documents/falera-pitch", help="output folder (default: %(default)s)")
    ap.add_argument("--pdf", default="FaleraOS-pitch.pdf", help="PDF file name (default: %(default)s)")
    args = ap.parse_args()

    base = args.base.rstrip("/")
    out = Path(os.path.expanduser(args.out))
    out.mkdir(parents=True, exist_ok=True)
    chrome = find_chrome()
    total = slide_count(base)

    pngs = []
    for n in range(1, total + 1):
        png = out / f"slide-{n:02d}.png"
        shoot(chrome, f"{base}/pitch/{n}/?print=1", png)
        pngs.append(png)
        print(f"{png}")

    pdf = out / args.pdf
    write_pdf(pngs, pdf)
    print(f"{pdf} ({total} pages)")


if __name__ == "__main__":
    main()

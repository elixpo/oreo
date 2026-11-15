#!/usr/bin/env python3
"""Write the JLCPCB order files for the routed board into build/jlcpcb/.

    python3 circuit/elixpo/export_jlcpcb.py

- oreo-badge-gerbers.zip: the six copper layers, paste, silkscreen, mask,
  outline and the plated and unplated drill files (no drill maps).
- oreo-badge-BOM.csv and oreo-badge-CPL.csv: JLCPCB's assembly BOM and
  placement list for the SMD parts on both sides. Parts with through-hole
  pins (the 6 mm buttons, the J3 socket, the IR receiver) are hand-soldered
  and left out; so are holes, fiducials and the speaker grille. The USB-C
  receptacle is SMD with shell pegs, which JLCPCB assembles.

Fill in the "LCSC Part #" column (or pick parts in JLCPCB's BOM tool)
before ordering assembly.
"""

import csv
import subprocess
import zipfile
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOARD = HERE / "elixpo.kicad_pcb"
OUT = HERE / "build" / "jlcpcb"
GERBERS = OUT / "gerbers"
# Footprints hand-soldered after assembly (through-hole parts).
HAND_SOLDERED = {"SW_PUSH_6mm", "PinSocket_1x14_P2.54mm_Vertical", "Vishay_MINICAST-3Pin"}
LAYERS = ("F.Cu,In1.Cu,In2.Cu,In3.Cu,In4.Cu,B.Cu,F.Paste,B.Paste,"
          "F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts")


def run(*args):
    subprocess.run(["kicad-cli", *args], check=True, stdout=subprocess.DEVNULL)


def gerbers():
    for old in GERBERS.glob("*"):
        old.unlink()
    GERBERS.mkdir(parents=True, exist_ok=True)
    run("pcb", "export", "gerbers", "--layers", LAYERS, "--no-protel-ext", "-o", f"{GERBERS}/", str(BOARD))
    run("pcb", "export", "drill", "--format", "excellon", "--excellon-separate-th",
        "--excellon-units", "mm", "--generate-map", "-o", f"{GERBERS}/", str(BOARD))
    with zipfile.ZipFile(OUT / "oreo-badge-gerbers.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(GERBERS.iterdir()):
            if f.suffix in (".gbr", ".drl") and "-drl_map" not in f.name:
                z.write(f, f.name)
    return sorted(zipfile.ZipFile(OUT / "oreo-badge-gerbers.zip").namelist())


def assembly():
    pos = OUT / "positions.csv"
    run("pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "both",
        "-o", str(pos), str(BOARD))
    # KiCad's --exclude-fp-th would also drop the ESP32 module (thermal vias
    # in its pad), the USB-C receptacle and the slide switch (shell pegs).
    rows = [r for r in csv.DictReader(pos.open())
            if r["Package"] not in HAND_SOLDERED and not r["Ref"].startswith("FID")]
    with (OUT / "oreo-badge-CPL.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(("Designator", "Mid X", "Mid Y", "Layer", "Rotation"))
        for r in rows:
            w.writerow((r["Ref"], f'{float(r["PosX"]):.4f}mm', f'{float(r["PosY"]):.4f}mm',
                        "Top" if r["Side"] == "top" else "Bottom", f'{float(r["Rot"]):.1f}'))
    groups = defaultdict(list)
    for r in rows:
        groups[(r["Val"], r["Package"])].append(r["Ref"])

    def order(ref):
        head = "".join(c for c in ref if c.isalpha())
        return head, int(ref[len(head):] or 0)

    with (OUT / "oreo-badge-BOM.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(("Comment", "Designator", "Footprint", "Quantity", "Manufacturer Part", "LCSC Part #"))
        for (val, pkg), refs in sorted(groups.items(), key=lambda kv: order(sorted(kv[1], key=order)[0])):
            refs.sort(key=order)
            w.writerow((val, ",".join(refs), pkg, len(refs), "", ""))
    return len(rows), len(groups)


if __name__ == "__main__":
    files = gerbers()
    parts, lines = assembly()
    print(f"Gerber zip: {len(files)} files ({', '.join(files)})")
    print(f"Assembly: {parts} SMD placements in {lines} BOM lines -> {OUT}")

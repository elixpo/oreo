#!/usr/bin/python3
"""Pull the TPS63031's inductor and capacitors in against its pins.

Clears tracks and vias in a box around U5 (in the file's text: removing
them through the API crashes the zone filler), moves the parts, and leaves
the reconnection to finish_badge_pcb.py."""
import os, sys
sys.path.insert(0, "/usr/lib/python3/dist-packages")
import pcbnew
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOARD = HERE / "elixpo.kicad_pcb"
O = (40.0, 30.0)                         # board origin on the page
BOX = (53.5, 117.0, 69.0, 133.0)         # x0, y0, x1, y1 in board mm
MOVES = {                                # ref: (x, y, orientation as seen on the board)
    "L1": (64.0, 124.5, None),           # pads to face pins 2 (L2) and 4 (L1)
    "C21": (61.0, 121.6, None),          # VOUT, at pin 1
    "C28": (61.0, 119.4, None),          # second VOUT cap just above it
    "C20": (61.0, 127.4, None),          # VIN, at pin 5
    "C27": (56.7, 124.5, None),          # VINA filter at pin 8
    "R26": (56.7, 127.0, None),
}

def strip_box(text):
    x0, y0, x1, y1 = (BOX[0] + O[0], BOX[1] + O[1], BOX[2] + O[0], BOX[3] + O[1])
    inside = lambda x, y: x0 <= x <= x1 and y0 <= y <= y1
    import re
    out, i, start, depth, block, n = [], 0, 0, 0, None, len(text)
    removed = 0
    while i < n:
        c = text[i]
        if c == '"':
            i = text.index('"', i + 1)
        elif c == "(":
            depth += 1
            if depth == 2:
                block = i
        elif c == ")":
            if depth == 2 and block is not None:
                chunk = text[block:i + 1]
                hit = False
                if chunk.startswith("(segment") or chunk.startswith("(arc"):
                    pts = re.findall(r"\((?:start|end|mid) ([-\d.]+) ([-\d.]+)\)", chunk)
                    hit = any(inside(float(x), float(y)) for x, y in pts)
                elif chunk.startswith("(via"):
                    m = re.search(r"\(at ([-\d.]+) ([-\d.]+)\)", chunk)
                    hit = bool(m) and inside(float(m.group(1)), float(m.group(2)))
                if hit:
                    out.append(text[start:text.rfind("\n", 0, block)])
                    start = i + 1
                    removed += 1
                block = None
            depth -= 1
        i += 1
    out.append(text[start:])
    return "".join(out), removed

text, removed = strip_box(BOARD.read_text())
BOARD.write_text(text)
project = BOARD.with_suffix(".kicad_pro").read_bytes()
board = pcbnew.LoadBoard(str(BOARD))
for ref, (x, y, _rot) in MOVES.items():
    fp = board.FindFootprintByReference(ref)
    fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(O[0] + x), pcbnew.FromMM(O[1] + y)))
# L1: turn it so its pads run along the pin column, pad 1 (BUCK_L1) towards pin 4
l1 = board.FindFootprintByReference("L1")
u5 = board.FindFootprintByReference("U5")
pin = {p.GetNumber(): p.GetPosition() for p in u5.Pads()}
def pads(fp): return {p.GetNumber(): p.GetPosition() for p in fp.Pads()}
best = None
for ang in (0, 90, 180, 270):
    l1.SetOrientationDegrees(ang)
    lp = pads(l1)
    d = max((lp["1"] - pin["4"]).EuclideanNorm(), (lp["2"] - pin["2"]).EuclideanNorm())
    if best is None or d < best[0]:
        best = (d, ang)
l1.SetOrientationDegrees(best[1])
# capacitors: pad 1 (the supply side) towards its pin
for ref, target in (("C21", "1"), ("C28", "1"), ("C20", "5"), ("C27", "8"), ("R26", "8")):
    fp = board.FindFootprintByReference(ref)
    best = None
    turns = (0, 180) if ref in ("C21", "C28", "C20") else (0, 90, 180, 270)   # keep the caps flat
    for ang in turns:
        fp.SetOrientationDegrees(ang)
        d = (pads(fp)["1"] - pin[target]).EuclideanNorm()
        if best is None or d < best[0]:
            best = (d, ang)
    fp.SetOrientationDegrees(best[1])
board.Save(str(BOARD))
BOARD.with_suffix(".kicad_pro").write_bytes(project)
for ref in MOVES:
    fp = board.FindFootprintByReference(ref)
    near = min((pd.GetPosition() - pin[k]).EuclideanNorm() for pd in fp.Pads() for k in pin if k)
    print(f"{ref}: nearest pad to a U5 pin {pcbnew.ToMM(near):.2f} mm")
print("removed", removed, "tracks/vias in the box")
sys.stdout.flush(); os._exit(0)

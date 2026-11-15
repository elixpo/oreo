#!/usr/bin/python3
"""Generate the Oreo badge PCB (elixpo.kicad_pcb) from the schematic netlist.

Run with the Python that ships KiCad's pcbnew module (on Ubuntu,
/usr/bin/python3), after generate_badge_schematic.py:

    kicad-cli sch export netlist --format kicadsexpr -o build/elixpo.net elixpo.kicad_sch
    /usr/bin/python3 circuit/elixpo/generate_badge_pcb.py

It places every footprint, draws the outline, the lanyard slots and the
speaker grille, pours the ground and power
planes, and writes the net classes. Routing is done afterwards (see
README.md); this script never touches tracks, so a routed board is kept by
running it only when placement changes.

Board coordinates below are millimetres from the board's top-left corner,
looking at the front (the display side). Parts on the back are given in
the same front-view coordinates.
"""

import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, "/usr/lib/python3/dist-packages")
import pcbnew  # noqa: E402

HERE = Path(__file__).resolve().parent
FP_ROOT = Path("/usr/share/kicad/footprints")
NETLIST = HERE / "build" / "elixpo.net"
BOARD_FILE = HERE / "elixpo.kicad_pcb"
PROJECT_FILE = HERE / "elixpo.kicad_pro"

W, H, CORNER = 88.0, 133.5, 4.0           # board outline, mm
ORIGIN = (40.0, 30.0)                     # where the board sits on the page

# Front-face features.
PANEL = (9.4, 60.0, 69.2, 50.0)           # top at 60 mm: the name card covers 0-60 mm           # DT028BTFT outline, landscape: x, y, w, h
BATTERY = (18.0, 74.0, 50.0, 34.0)        # 603450 cell on the back, low for a low centre of gravity
SPEAKER = (70.5, 7.0, 15.0, 11.0)         # 1511 speaker on the back, under the right clip slot
SLOTS = ((10.0, 4.0), (78.0, 4.0))        # lanyard-clip slot centres
SLOT_LEN, SLOT_W = 10.0, 3.2
ART = HERE / "art"
PANDA = (-10.0, 6.0, 54.0)                # front, under the name card: x, y, height (runs off the left edge)
HEART = (79.0, 35.5, 11.0)                # front, far right, where the panda is looking: centre x, y, width
OSHW_MARK = (6.0, 40.0, 13.0)             # back: x, y, height (OSHWA certification mark)        # x, y, w, h: the panel's FPC folds to the back here


def mm(v):
    return pcbnew.FromMM(v)


def pt(x, y):
    return pcbnew.VECTOR2I(mm(ORIGIN[0] + x), mm(ORIGIN[1] + y))


# ---------------------------------------------------------------- netlist

def parse_sexpr(text):
    tokens = re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+', text)
    stack = [[]]
    for tok in tokens:
        if tok == "(":
            stack.append([])
        elif tok == ")":
            item = stack.pop()
            stack[-1].append(item)
        else:
            stack[-1].append(tok[1:-1] if tok.startswith('"') else tok)
    return stack[0][0]


def children(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def value(node, key):
    found = children(node, key)
    return found[0][1] if found else None


def read_netlist():
    tree = parse_sexpr(NETLIST.read_text())
    comps = {}
    for comp in children(children(tree, "components")[0], "comp"):
        ref = value(comp, "ref")
        sheet = children(comp, "sheetpath")[0]
        comps[ref] = dict(value=value(comp, "value"), footprint=value(comp, "footprint"),
                          description=value(comp, "description") or "",
                          path=value(sheet, "tstamps") + value(comp, "tstamps"))
    pads = {}
    for net in children(children(tree, "nets")[0], "net"):
        name = value(net, "name")
        for node in children(net, "node"):
            pads[(value(node, "ref"), value(node, "pin"))] = name
    return comps, pads


# --------------------------------------------------------------- placement
# ref: (x, y, rotation in degrees, side). Rotation is as seen from the front.

F, B = "F", "B"
DPAD = (13.0, 121.5)                       # centre of the D-pad, bottom-left
PLACE = {
    # ---- Front: D-pad bottom-left, then HOME A B C side by side ----
    "SW11": (DPAD[0], DPAD[1] - 7.0, 0, F),    # UP
    "SW12": (DPAD[0], DPAD[1] + 7.0, 0, F),    # DOWN
    "SW13": (DPAD[0] - 7.0, DPAD[1], 90, F),   # LEFT
    "SW14": (DPAD[0] + 7.0, DPAD[1], 90, F),   # RIGHT
    "SW18": (38.0, DPAD[1], 0, F),             # HOME
    "SW15": (52.0, DPAD[1], 0, F),             # A
    "SW16": (66.0, DPAD[1], 0, F),             # B
    "SW17": (80.0, DPAD[1], 0, F),             # C
    "D20": (29.0, DPAD[1] - 2.0, 0, F), "D21": (29.0, DPAD[1] + 2.0, 0, F),
    # Corner LEDs around the panel, status LED right of it.
    "D1": (6.0, 61.5, 90, F), "D2": (82.0, 61.5, 90, F),
    "D3": (6.0, 108.5, 90, F), "D4": (82.0, 108.5, 90, F),
    "U9": (83.5, 85, 90, F),
    # ---- Back: module and RTC at the top, display/expander/IMU behind the top of the
    # screen, battery low, microSD and USB-C at the bottom ----
    "U1": (44, 12.8, 0, B),
    "R1": (56.5, 20, 90, B),
    "C3": (58.5, 20, 90, B),
    "R2": (58.5, 24, 90, B),
    "SW1": (34, 30, 0, B),
    "SW2": (54, 30, 0, B),
    "TP1": (60, 37, 0, B),
    "TP2": (64, 37, 0, B),
    "TP3": (68, 37, 0, B),
    "TP4": (72, 37, 0, B),
    "R17": (31.5, 10, 0, B),
    "R18": (31.5, 12.5, 0, B),
    "C22": (31.5, 15, 0, B),
    "U13": (44, 33, 0, B),
    "C65": (47.5, 33, 90, B),
    "C66": (40.5, 33, 90, B),
    "R61": (44, 37.5, 0, B),
    "J7": (65, 21, 0, B),
    "U12": (66, 28, 0, B),
    "C60": (66, 32.5, 0, B),
    "C61": (70.5, 28, 90, B),
    "R60": (61.5, 28, 90, B),
    "Q1": (78, 28.5, 0, B),
    "R71": (81.5, 28.5, 90, B),
    "R72": (74.5, 28.5, 90, B),
    "R73": (78, 33, 0, B),
    "R70": (79, 21.5, 90, B),
    "C70": (76.5, 21.5, 90, B),
    "J3": (62, 85, 90, F),
    "C30": (57, 76.5, 90, F),
    "C31": (55.5, 76.5, 90, F),
    "R74": (84.5, 89.5, 90, B),
    "C71": (84.5, 81, 90, B),
    "R30": (66, 62, 90, B),
    "R31": (62, 62, 0, B),
    "R32": (62, 64, 0, B),
    "R33": (62, 66, 0, B),
    "R34": (62, 68, 0, B),
    "Q2": (57, 65, 0, B),
    "R35": (57, 70, 0, B),
    "R36": (53, 65, 90, B),
    "U11": (34, 66, 0, B),
    "C40": (38.5, 66, 90, B),
    "R40": (40, 61, 90, B),
    "R41": (42, 61, 90, B),
    "R42": (22, 69.5, 90, B),
    "R43": (24.2, 69.5, 90, B),
    "R44": (26.4, 69.5, 90, B),
    "TP6": (40, 72, 0, B),
    "U7": (48, 66, 0, B),
    "C62": (52.5, 69.5, 0, B),
    "C63": (48, 70.5, 0, B),
    "C64": (44, 61, 90, B),
    "U10": (13, 66, 0, B),
    "C29": (13, 62.5, 0, B),
    "TP5": (7.5, 70, 0, B),
    "J2": (13, 81, 90, B),
    "J4": (9, 122, 90, B),
    "C67": (4, 111, 90, B),
    "C68": (6.2, 111, 90, B),
    "R62": (8.4, 111, 90, B),
    "R63": (10.6, 111, 90, B),
    "R64": (12.8, 111, 90, B),
    "R65": (15, 111, 90, B),
    "R66": (17.2, 111, 90, B),
    "R67": (19.4, 111, 90, B),
    "J1": (44, 129.9, 0, B),
    "U3": (44, 121.5, 0, B),
    "R10": (37.5, 125.5, 90, B),
    "R11": (50.5, 125.5, 90, B),
    "R12": (42.5, 118, 90, B),
    "R13": (45.5, 118, 90, B),
    "R19": (36, 130, 90, B),
    "C23": (52, 130, 90, B),
    "R23": (38.5, 116.5, 0, B),
    "R24": (49.5, 116.5, 0, B),
    "U4": (28, 124.5, 0, B),
    "R14": (24, 129.5, 90, B),
    "R15": (26, 129.5, 90, B),
    "R22": (30, 129.5, 90, B),
    "R25": (32, 129.5, 90, B),
    "R16": (28, 119.5, 0, B),
    "C24": (23.5, 124.5, 90, B),
    "C25": (32.5, 124.5, 90, B),
    "C26": (32, 119.5, 90, B),
    "U5": (60, 124.5, 0, B),
    "L1": (65.5, 124.5, 0, B),
    "R26": (56, 120.5, 0, B),
    "C27": (56, 122.5, 0, B),
    "C20": (60, 120, 0, B),
    "C21": (60, 129, 0, B),
    "C28": (65.5, 129, 0, B),
    "SW3": (84, 111, 270, B),
    "J5": (83.6, 123.5, 270, B),
    "U8": (86, 28, 90, B),
    "D10": (70.5, 22, 0, B),
}
# Button pull-ups: two rows beside the expander.
for i in range(8):
    PLACE[f"R{50 + i}"] = (22.0 + (i % 4) * 2.2, 61.0 + (i // 4) * 2.4, 90, B)

# Passives that belong right at a module pad: ref -> (host, pad, distance
# out from the pad centre, offset along the module edge). They are pushed
# out of whichever module edge the pad is on, long side parallel to it.
AT_PAD = {
    "C2": ("U1", "2", 2.0, 0.0),      # 100 nF closest to the 3V3 pin
    "C1": ("U1", "2", 2.4, 3.0),      # 22 uF next to it
    "R3": ("U1", "20", 2.0, 0.0),     # display clock termination
    "R4": ("U1", "31", 2.0, 0.0),     # SD clock termination
    "R5": ("U1", "12", 2.0, 0.0),     # I2S bit clock termination
}
for _ref, (_host, *_rest) in AT_PAD.items():
    PLACE.setdefault(_ref, (0.0, 0.0, 0, B))   # final position comes from the pad


# -------------------------------------------------------------- board parts

def load_footprint(fpid):
    lib, name = fpid.split(":")
    fp = pcbnew.FootprintLoad(str(FP_ROOT / f"{lib}.pretty"), name)
    if fp is None:
        raise SystemExit(f"footprint not found: {fpid}")
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def place(fp, x, y, rot, side):
    """Rotate as seen from the front, then flip back-side parts left-right
    (KiCad stores a flipped part's orientation as 180 - rotation, so the
    rotation must be applied before the flip)."""
    fp.SetPosition(pt(x, y))
    fp.SetOrientationDegrees(rot)
    if side == B:
        fp.Flip(pt(x, y), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)


def pad_position(fp, number):
    for pad in fp.Pads():
        if pad.GetNumber() == number:
            pos = pad.GetPosition()
            return pcbnew.ToMM(pos.x) - ORIGIN[0], pcbnew.ToMM(pos.y) - ORIGIN[1]
    raise KeyError(number)


def add_line(board, layer, a, b, width=0.15):
    seg = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
    seg.SetLayer(layer)
    seg.SetStart(pt(*a))
    seg.SetEnd(pt(*b))
    seg.SetWidth(mm(width))
    board.Add(seg)


def add_arc(board, layer, centre, start, angle, width=0.15):
    arc = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_ARC)
    arc.SetLayer(layer)
    arc.SetCenter(pt(*centre))
    arc.SetStart(pt(*start))
    arc.SetArcAngleAndEnd(pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T), True)
    arc.SetWidth(mm(width))
    board.Add(arc)


def add_circle(board, layer, centre, radius, width=0.1):
    c = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_CIRCLE)
    c.SetLayer(layer)
    c.SetCenter(pt(*centre))
    c.SetEnd(pt(centre[0] + radius, centre[1]))
    c.SetWidth(mm(width))
    board.Add(c)


def add_rect(board, layer, x, y, w, h, width=0.15):
    for a, b in (((x, y), (x + w, y)), ((x + w, y), (x + w, y + h)),
                 ((x + w, y + h), (x, y + h)), ((x, y + h), (x, y))):
        add_line(board, layer, a, b, width)


def add_rounded_rect(board, layer, x, y, w, h, r, width=0.1):
    add_line(board, layer, (x + r, y), (x + w - r, y), width)
    add_line(board, layer, (x + w, y + r), (x + w, y + h - r), width)
    add_line(board, layer, (x + w - r, y + h), (x + r, y + h), width)
    add_line(board, layer, (x, y + h - r), (x, y + r), width)
    add_arc(board, layer, (x + r, y + r), (x, y + r), 90, width)
    add_arc(board, layer, (x + w - r, y + r), (x + w - r, y), 90, width)
    add_arc(board, layer, (x + w - r, y + h - r), (x + w, y + h - r), 90, width)
    add_arc(board, layer, (x + r, y + h - r), (x + r, y + h), 90, width)


def add_text(board, layer, text, x, y, size=1.0, thickness=0.15, mirror=False, bold=False):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(text)
    t.SetLayer(layer)
    t.SetPosition(pt(x, y))
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(thickness))
    t.SetMirrored(mirror)
    t.SetBold(bold)
    board.Add(t)


def outline(board):
    e = pcbnew.Edge_Cuts
    add_rounded_rect(board, e, 0, 0, W, H, CORNER)
    for cx, cy in SLOTS:
        r = SLOT_W / 2
        half = SLOT_LEN / 2 - r
        add_line(board, e, (cx - half, cy - r), (cx + half, cy - r), 0.1)
        add_line(board, e, (cx + half, cy + r), (cx - half, cy + r), 0.1)
        add_arc(board, e, (cx + half, cy), (cx + half, cy - r), 180, 0.1)
        add_arc(board, e, (cx - half, cy), (cx - half, cy + r), 180, 0.1)


GRILLE_ROWS = (0x41, 0x4E, 0x57, 0x45, 0x53, 0x48, 0x41)   # one row per byte, MSB on the left
GRILLE_PITCH = (1.8, 1.6)                                    # column, row (mm)
GRILLE_HOLES = (0.6, 1.2)                                    # drill for a 0 bit, a 1 bit (mm)


def speaker_grille(board):
    """Drilled (non-plated) holes over the speaker, read from the front:
    every hole passes sound, big holes are 1 bits and small holes 0 bits."""
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference("G1")
    fp.SetValue("speaker grille")
    fp.SetAttributes(pcbnew.FP_BOARD_ONLY | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    sx, sy, sw, sh = SPEAKER
    cx, cy = sx + sw / 2, sy + sh / 2
    fp.SetPosition(pt(cx, cy))
    board.Add(fp)
    dx, dy = GRILLE_PITCH
    for row, byte in enumerate(GRILLE_ROWS):
        for col in range(8):
            bit = (byte >> (7 - col)) & 1
            d = GRILLE_HOLES[bit]
            pad = pcbnew.PAD(fp)
            pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
            pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
            pad.SetSize(pcbnew.VECTOR2I(mm(d), mm(d)))
            pad.SetDrillSize(pcbnew.VECTOR2I(mm(d), mm(d)))
            pad.SetLayerSet(pcbnew.PAD.UnplatedHoleMask())
            fp.Add(pad)
            pad.SetPosition(pt(cx + (col - 3.5) * dx, cy + (row - (len(GRILLE_ROWS) - 1) / 2) * dy))


def raster_art(board, png, layer, x, y, height, mirror=False, threshold=128):
    """Silkscreen artwork from a black-on-white PNG: dark pixels become silk.
    Pixel runs are merged into polygons by KiCad's own polygon engine."""
    from PIL import Image
    img = Image.open(png).convert("L")
    rows = max(1, round(height / 0.05))                     # 0.05 mm per pixel
    cols = max(1, round(img.width * rows / img.height))
    img = img.resize((cols, rows), Image.LANCZOS)
    if mirror:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    px = height / rows
    data = img.load()
    polys = pcbnew.SHAPE_POLY_SET()
    for r in range(rows):
        c = 0
        while c < cols:
            if data[c, r] < threshold:
                start = c
                while c < cols and data[c, r] < threshold:
                    c += 1
                x0, x1 = x + start * px, x + c * px
                y0, y1 = y + r * px, y + (r + 1) * px + 0.001
                polys.NewOutline()
                for vx, vy in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
                    polys.Append(mm(ORIGIN[0] + vx), mm(ORIGIN[1] + vy))
            else:
                c += 1
    polys.Simplify()
    # A polygon shape holds one outline (with its holes), so each merged
    # outline becomes its own shape.
    for i in range(polys.OutlineCount()):
        piece = pcbnew.SHAPE_POLY_SET()
        piece.AddOutline(polys.Outline(i))
        for h in range(polys.HoleCount(i)):
            piece.AddHole(polys.Hole(i, h))
        shape = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_POLY)
        shape.SetLayer(layer)
        shape.SetPolyShape(piece)
        shape.SetFilled(True)
        shape.SetWidth(0)
        board.Add(shape)


def heart(board, layer, cx, cy, width, line=0.3):
    """An outline heart in the line art's weight, drawn as a raster so it
    goes through the same path as the other artwork."""
    from PIL import Image, ImageDraw
    import tempfile
    size = 400
    img = Image.new("L", (size, size), 255)
    draw = ImageDraw.Draw(img)
    pts = []
    for i in range(361):
        t = math.radians(i)
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((size / 2 + x * size / 36, size / 2 - y * size / 36 - 10))
    stroke = max(2, round(line / width * size * 36 / 34))
    draw.line(pts, fill=0, width=stroke, joint="curve")
    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        img.save(tmp.name)
        raster_art(board, Path(tmp.name), layer, cx - width / 2, cy - width / 2, width)


def silkscreen(board):
    fs, bs = pcbnew.F_SilkS, pcbnew.B_SilkS
    # Panel corner marks (the panel itself is placed by hand).
    px, py, pw, ph = PANEL
    for (cx, cy, dx, dy) in ((px, py, 1, 1), (px + pw, py, -1, 1), (px, py + ph, 1, -1), (px + pw, py + ph, -1, -1)):
        add_line(board, pcbnew.F_Fab, (cx, cy), (cx + 3 * dx, cy), 0.1)
        add_line(board, pcbnew.F_Fab, (cx, cy), (cx, cy + 3 * dy), 0.1)
    add_rect(board, pcbnew.F_Fab, px, py, pw, ph, 0.1)
    add_text(board, pcbnew.F_Fab, "DT028BTFT 2.8in panel", px + pw / 2, py + ph / 2, 1.5)
    # The front silkscreen (logo, artwork) is drawn by hand; buttons are not labelled.
    sx, sy, sw, sh = SPEAKER
    # Back.
    bx, by, bw, bh = BATTERY
    add_rect(board, pcbnew.B_Fab, bx, by, bw, bh, 0.1)
    add_rect(board, pcbnew.B_CrtYd, bx, by, bw, bh, 0.05)
    add_text(board, bs, "LiPo 1000 mAh 603450", bx + bw / 2, by + bh / 2 - 2, 1.2, 0.15, mirror=True)
    add_text(board, bs, "JST-PH: check polarity", bx + bw / 2, by + bh / 2 + 1, 1.0, 0.15, mirror=True)
    add_rect(board, pcbnew.B_Fab, sx, sy, sw, sh, 0.1)
    add_rect(board, pcbnew.B_CrtYd, sx, sy, sw, sh, 0.05)
    add_text(board, bs, "OREO BADGE", 44.0, 45.0, 1.5, 0.25, mirror=True, bold=True)
    add_text(board, bs, "oreo.elixpo.com", 44.0, 47.8, 1.0, 0.15, mirror=True)
    add_text(board, bs, "CERN-OHL-P-2.0", 44.0, 50.1, 0.9, 0.15, mirror=True)
    add_text(board, bs, "S/N-2509-0023", 44.0, 52.5, 0.9, 0.15, mirror=True)
    # Art: the Oreo panda in profile on the front, under the name card, and
    # OSHWA's certification mark on the back.
    px_, py_, ph_ = PANDA
    raster_art(board, ART / "oreo-lineart.png", fs, px_, py_, ph_)
    heart(board, fs, *HEART)
    ox, oy, oh = OSHW_MARK
    raster_art(board, ART / "oshw-certification-mark-IN000107.png", bs, ox, oy, oh, mirror=True)
    add_text(board, bs, "RST", 34.0, 26.8, 0.8, 0.12, mirror=True)
    add_text(board, bs, "BOOT", 54.0, 26.8, 0.8, 0.12, mirror=True)
    add_text(board, bs, "ON", 84.0, 104.0, 0.8, 0.12, mirror=True)
    add_text(board, bs, "microSD", 11.0, 131.8, 0.8, 0.12, mirror=True)
    add_text(board, bs, "Qwiic", 83.6, 117.5, 0.8, 0.12, mirror=True)
    for ref, label in (("TP1", "TX"), ("TP2", "RX"), ("TP3", "GND"), ("TP4", "3V3"), ("TP5", "VBAT"), ("TP6", "P17")):
        tx, ty = PLACE[ref][:2]
        add_text(board, bs, label, tx, ty + 2.2, 0.8, 0.12, mirror=True)


def zone(board, net, layer, polygon, priority=0, clearance=0.25, min_width=0.2):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    if net is not None:
        z.SetNet(net)
    z.SetAssignedPriority(priority)
    z.SetLocalClearance(mm(clearance))
    z.SetMinThickness(mm(min_width))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    z.SetThermalReliefGap(mm(0.3))
    z.SetThermalReliefSpokeWidth(mm(0.35))
    outline_ = z.Outline()
    outline_.NewOutline()
    for x, y in polygon:
        outline_.Append(mm(ORIGIN[0] + x), mm(ORIGIN[1] + y))
    board.Add(z)
    return z


def keepout(board, polygon, layers, name):
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    z.SetZoneName(name)
    z.SetDoNotAllowTracks(True)
    z.SetDoNotAllowVias(True)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowZoneFills(True)
    z.SetDoNotAllowFootprints(False)
    ls = pcbnew.LSET()
    for layer in layers:
        ls.AddLayer(layer)
    z.SetLayerSet(ls)
    o = z.Outline()
    o.NewOutline()
    for x, y in polygon:
        o.Append(mm(ORIGIN[0] + x), mm(ORIGIN[1] + y))
    board.Add(z)


def planes(board):
    # 6 layers: F signal / In1 GND / In2 signal / In3 signal / In4 GND / B signal.
    # Every signal layer is next to a solid ground plane; 3.3 V is routed
    # with the Power net class.
    gnd = board.FindNet("GND")
    full = [(0.3, 0.3), (W - 0.3, 0.3), (W - 0.3, H - 0.3), (0.3, H - 0.3)]
    zone(board, gnd, pcbnew.In1_Cu, full)                 # return plane for F and In2
    zone(board, gnd, pcbnew.In4_Cu, full)                 # return plane for In3 and B
    zone(board, gnd, pcbnew.F_Cu, full, clearance=0.3)    # ground fill, stitched to In1
    zone(board, gnd, pcbnew.B_Cu, full, clearance=0.3)
    # Antenna: no copper on any layer beside or under the antenna, per the
    # ESP32-S3-WROOM-1 datasheet; the module's antenna end is on the top edge.
    mx = PLACE["U1"][0]
    copper = [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.In3_Cu, pcbnew.In4_Cu, pcbnew.B_Cu]
    keepout(board, [(mx - 15.0, 0.0), (mx + 15.0, 0.0), (mx + 15.0, 7.0), (mx - 15.0, 7.0)],
            copper, "antenna keep-out")


def stackup(board):
    board.SetCopperLayerCount(6)
    ds = board.GetDesignSettings()
    ds.SetBoardThickness(mm(1.6))
    ds.m_TrackMinWidth = mm(0.15)
    ds.m_MinClearance = mm(0.15)
    ds.m_ViasMinSize = mm(0.5)
    ds.m_MinThroughDrill = mm(0.2)       # the module's own thermal vias
    ds.m_CopperEdgeClearance = mm(0.3)
    ds.m_HoleClearance = mm(0.25)
    ds.m_SilkClearance = mm(0.0)


def write_netclasses():
    """KiCad keeps net classes in the project file."""
    pro = json.loads(PROJECT_FILE.read_text())
    ns = pro.setdefault("net_settings", {})
    base = dict(bus_width=12, diff_pair_gap=0.15, diff_pair_via_gap=0.25, diff_pair_width=0.2,
                line_style=0, microvia_diameter=0.3, microvia_drill=0.1, pcb_color="rgba(0, 0, 0, 0.000)",
                schematic_color="rgba(0, 0, 0, 0.000)", wire_width=6, priority=2147483647)
    ns["classes"] = [
        dict(base, name="Default", clearance=0.15, track_width=0.2, via_diameter=0.6, via_drill=0.3),
        dict(base, name="Power", clearance=0.2, track_width=0.5, via_diameter=0.8, via_drill=0.4, priority=1),
        dict(base, name="Battery", clearance=0.2, track_width=0.8, via_diameter=0.8, via_drill=0.4, priority=0),
        dict(base, name="Fast", clearance=0.2, track_width=0.2, via_diameter=0.6, via_drill=0.3, priority=2),
        dict(base, name="USB", clearance=0.2, track_width=0.3, via_diameter=0.6, via_drill=0.3,
             diff_pair_width=0.3, diff_pair_gap=0.15, priority=3),
    ]
    ns["netclass_patterns"] = (
        [dict(netclass="Battery", pattern=p) for p in ("VBUS_5V", "VSYS", "VSYS_SW", "VBAT", "BUCK_L1", "BUCK_L2")] +
        [dict(netclass="Power", pattern=p) for p in ("+3V3", "GND", "LCD_LEDA", "LCD_BL_SINK", "SPK_P", "SPK_N", "IR_LED_*", "CHASSIS")] +
        [dict(netclass="Fast", pattern=p) for p in ("LCD_SCK*", "LCD_MOSI", "LCD_MISO", "SD_CLK*", "SD_CMD", "SD_D*", "I2S_BCLK*")] +
        [dict(netclass="USB", pattern=p) for p in ("USB_D*", "USB_CONN_D*")]
    )
    PROJECT_FILE.write_text(json.dumps(pro, indent=2) + "\n")


STACKUP = """\t\t(stackup
\t\t\t(layer "F.SilkS" (type "Top Silk Screen") (color "White"))
\t\t\t(layer "F.Paste" (type "Top Solder Paste"))
\t\t\t(layer "F.Mask" (type "Top Solder Mask") (color "Black") (thickness 0.01))
\t\t\t(layer "F.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "dielectric 1" (type "prepreg") (thickness 0.1) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
\t\t\t(layer "In1.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "dielectric 2" (type "core") (thickness 0.535) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
\t\t\t(layer "In2.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "dielectric 3" (type "prepreg") (thickness 0.1) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
\t\t\t(layer "In3.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "dielectric 4" (type "core") (thickness 0.535) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
\t\t\t(layer "In4.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "dielectric 5" (type "prepreg") (thickness 0.1) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))
\t\t\t(layer "B.Cu" (type "copper") (thickness 0.035))
\t\t\t(layer "B.Mask" (type "Bottom Solder Mask") (color "Black") (thickness 0.01))
\t\t\t(layer "B.Paste" (type "Bottom Solder Paste"))
\t\t\t(layer "B.SilkS" (type "Bottom Silk Screen") (color "White"))
\t\t\t(copper_finish "ENIG")
\t\t\t(dielectric_constraints no)
\t\t)
"""


def write_stackup():
    """1.6 mm 6-layer build with black solder mask and white silkscreen.
    The stackup is not exposed to Python, so it goes into the file."""
    text = BOARD_FILE.read_text()
    if "(stackup" not in text:
        text = text.replace("\t(setup\n", "\t(setup\n" + STACKUP, 1)
        BOARD_FILE.write_text(text)


def write_rules():
    (HERE / "elixpo.kicad_dru").write_text(
        '(version 1)\n'
        '# The USB-C receptacle\'s GND pads sit 0.19 mm from its locating holes, as\n'
        '# GCT drew the footprint.\n'
        '(rule "USB-C shell holes"\n'
        '  (condition "A.Parent == \'J1\' && B.Parent == \'J1\'")\n'
        '  (constraint hole_clearance (min 0.15mm)))\n')


def main():
    comps, pad_nets = read_netlist()
    board = pcbnew.BOARD()
    stackup(board)

    nets = {}
    for name in sorted(set(pad_nets.values())):
        net = pcbnew.NETINFO_ITEM(board, name)
        board.Add(net)
        nets[name] = net

    missing = sorted(set(comps) - set(PLACE))
    if missing:
        raise SystemExit(f"no placement for: {', '.join(missing)}")
    footprints = {}
    for ref, comp in sorted(comps.items()):
        fp = load_footprint(comp["footprint"])
        fp.SetReference(ref)
        fp.SetValue(comp["value"])
        fp.SetPath(pcbnew.KIID_PATH(comp["path"]))
        fp.SetField("Description", comp["description"])
        fp.SetExcludedFromBOM(False)
        board.Add(fp)
        for pad in fp.Pads():
            name = pad_nets.get((ref, pad.GetNumber()))
            # Pins marked no-connect in the schematic stay without a net.
            if name and not name.startswith("unconnected-"):
                pad.SetNet(nets[name])
        # Dense passives carry their reference on the fab layer, not silk.
        if not re.match(r"(U\d|J\d|Q\d|SW3$)", ref) or ref in ("U9", "J7", "U8"):
            fp.Reference().SetLayer(pcbnew.F_Fab)   # the flip below moves it to B.Fab
        x, y, rot, side = PLACE[ref]
        place(fp, x, y, rot, side)
        footprints[ref] = fp

    for ref, (host, padnum, dist, along) in AT_PAD.items():
        hx, hy = pad_position(footprints[host], padnum)
        mx, my = PLACE[host][:2]
        fp = footprints[ref]
        if abs(hx - mx) > 8.0:            # side column: push out sideways
            out = 1 if hx > mx else -1
            x, y, rot = hx + out * dist, hy + along, 90
        else:                              # bottom row: push down
            x, y, rot = hx + along, hy + dist, 0
        side = PLACE[ref][3]
        fp.SetOrientationDegrees(180 - rot if side == B else rot)
        fp.SetPosition(pt(x, y))

    outline(board)
    speaker_grille(board)
    silkscreen(board)
    planes(board)

    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    board.Save(str(BOARD_FILE))
    write_stackup()
    write_netclasses()
    write_rules()
    print(f"Placed {len(footprints)} footprints on a {W:g} x {H:g} mm 6-layer board: {BOARD_FILE}")


if __name__ == "__main__":
    main()

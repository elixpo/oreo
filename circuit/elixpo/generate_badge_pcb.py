#!/usr/bin/python3
"""Generate the Oreo badge PCB (elixpo.kicad_pcb) from the schematic netlist.

Run with the Python that ships KiCad's pcbnew module (on Ubuntu,
/usr/bin/python3), after generate_badge_schematic.py:

    kicad-cli sch export netlist --format kicadsexpr -o build/elixpo.net elixpo.kicad_sch
    /usr/bin/python3 circuit/elixpo/generate_badge_pcb.py

It places every footprint, draws the outline, the lanyard slots, the
display's FPC slot and the speaker grille, pours the ground and power
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

W, H, CORNER = 88.0, 128.0, 4.0           # board outline, mm
ORIGIN = (40.0, 30.0)                     # where the board sits on the page

# Front-face features.
PANEL = (3.0, 61.0, 69.2, 50.0)           # DT028BTFT outline, landscape: x, y, w, h
CARD = (4.0, 19.0, 80.0, 39.0)            # name-card window, silkscreen only
BATTERY = (19.0, 27.0, 50.0, 34.0)        # 603450 cell on the back
SPEAKER = (3.5, 7.0, 15.0, 11.0)          # 1511 speaker on the back
SLOTS = ((10.0, 4.0), (78.0, 4.0))        # lanyard-clip slot centres
SLOT_LEN, SLOT_W = 10.0, 3.2
FPC_SLOT = (74.0, 72.0, 1.6, 28.0)        # x, y, w, h: the panel's FPC folds to the back here


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
PLACE = {
    # Module on the back, antenna on the top edge (body 18 x 25.6 mm).
    "U1": (44.0, 12.8, 0, B),
    # Front: buttons. Right column like the Universe badge, row along the bottom.
    "SW11": (80.5, 68.0, 0, F),   # UP
    "SW17": (80.5, 86.0, 0, F),   # C
    "SW12": (80.5, 104.0, 0, F),  # DOWN
    "SW13": (8.5, 121.0, 0, F),   # LEFT
    "SW14": (19.5, 121.0, 0, F),  # RIGHT
    "SW18": (31.0, 121.0, 0, F),  # HOME
    "SW16": (58.0, 121.0, 0, F),  # B
    "SW15": (70.0, 121.0, 0, F),  # A
    # Front: corner LEDs around the panel, status LED, charge LEDs, IR.
    "D1": (4.5, 59.6, 0, F), "D2": (70.7, 59.6, 0, F),
    "D3": (4.5, 112.6, 0, F), "D4": (70.7, 112.6, 0, F),
    "U9": (80.5, 60.5, 0, F),
    "D20": (41.0, 116.5, 0, F), "D21": (47.0, 116.5, 0, F),
    "D10": (76.0, 12.0, 0, F),
    "U8": (80.0, 15.0, 0, F),
    # Back, top-left: speaker connector and amplifier beside the speaker.
    "J7": (10.0, 21.5, 0, B),
    "U12": (10.0, 30.0, 0, B), "C60": (10.0, 35.0, 0, B), "C61": (14.5, 30.0, 90, B),
    "R60": (5.5, 30.0, 90, B),
    # Back, left of the battery: battery connector, fuel gauge.
    "J2": (10.0, 46.0, 90, B),
    "U10": (10.0, 55.5, 0, B), "C29": (14.5, 55.5, 90, B),
    # Back, right of the battery: IR driver and receiver filter.
    "Q1": (78.0, 24.0, 0, B), "R71": (82.0, 24.0, 90, B), "R72": (74.0, 24.0, 90, B),
    "R73": (78.0, 29.0, 0, B), "R70": (84.5, 18.5, 90, B), "C70": (84.5, 13.0, 90, B),
    "R74": (80.5, 56.0, 0, B), "C71": (84.5, 60.5, 90, B),
    "R17": (74.0, 36.0, 90, B), "R18": (76.0, 36.0, 90, B), "C22": (78.0, 36.0, 90, B),
    # Back, behind the panel: display connector by the FPC slot, backlight.
    "J3": (81.6, 86.0, 90, B),
    "C30": (73.5, 104.0, 0, B), "C31": (73.5, 106.0, 0, B),
    "R30": (69.0, 66.0, 90, B),
    "R31": (66.0, 70.0, 0, B), "R32": (66.0, 72.0, 0, B),
    "R33": (66.0, 74.0, 0, B), "R34": (66.0, 76.0, 0, B),
    "Q2": (61.0, 73.0, 0, B), "R35": (61.0, 78.0, 0, B), "R36": (57.0, 73.0, 90, B),
    # Expander, its pull-ups and the I2C bus, centre of the back.
    "U11": (30.0, 82.0, 0, B), "C40": (34.5, 82.0, 90, B),
    "R40": (36.0, 72.0, 90, B), "R41": (38.0, 72.0, 90, B),
    "R42": (24.0, 88.0, 0, B), "R43": (24.0, 90.0, 0, B), "R44": (24.0, 92.0, 0, B),
    # IMU and RTC.
    "U7": (48.0, 84.0, 0, B), "C62": (52.5, 84.0, 90, B), "C63": (48.0, 88.5, 0, B),
    "C64": (43.5, 84.0, 90, B),
    "U13": (12.0, 70.0, 0, B), "C65": (15.5, 70.0, 90, B), "C66": (8.5, 70.0, 90, B),
    "R61": (12.0, 74.5, 0, B),
    # Clock terminations right at the module's pins (moved next to their pads below).
    "R3": (44.0, 29.0, 0, B), "R4": (44.0, 31.0, 0, B), "R5": (44.0, 33.0, 0, B),
    # Module support.
    "C1": (56.5, 9.0, 90, B), "C2": (56.5, 13.0, 90, B),
    "R1": (56.5, 18.0, 90, B), "C3": (58.5, 18.0, 90, B),
    "R2": (58.5, 23.0, 90, B),
    "SW1": (64.0, 118.0, 0, B), "SW2": (64.0, 124.0, 0, B),
    # microSD at the bottom-left, card entering from the left edge.
    "J4": (11.0, 104.0, 270, B),
    "C67": (22.0, 98.0, 0, B), "C68": (22.0, 100.5, 0, B), "R62": (22.0, 102.5, 0, B),
    "R63": (22.0, 104.5, 0, B), "R64": (22.0, 106.5, 0, B), "R65": (22.0, 108.5, 0, B),
    "R66": (22.0, 110.5, 0, B), "R67": (22.0, 112.5, 0, B),
    # Power: USB-C at the bottom centre, charger and regulator beside it.
    "J1": (44.0, 124.4, 0, B),
    "U3": (44.0, 116.0, 0, B),
    "R10": (37.5, 120.0, 90, B), "R11": (50.5, 120.0, 90, B),
    "R12": (42.5, 112.5, 90, B), "R13": (45.5, 112.5, 90, B),
    "R19": (36.0, 124.5, 90, B), "C23": (52.0, 124.5, 90, B),
    "R23": (40.0, 108.5, 0, B), "R24": (48.0, 108.5, 0, B),
    "U4": (32.0, 106.0, 0, B),
    "R14": (28.0, 111.0, 90, B), "R15": (30.0, 111.0, 90, B), "R22": (34.0, 111.0, 90, B),
    "R25": (36.0, 111.0, 90, B), "R16": (27.0, 101.5, 0, B),
    "C24": (36.5, 102.0, 90, B), "C25": (37.0, 106.0, 90, B), "C26": (27.5, 106.0, 90, B),
    "U5": (55.0, 106.0, 0, B), "L1": (60.5, 106.0, 0, B),
    "R26": (51.0, 102.0, 0, B), "C27": (51.0, 104.0, 0, B),
    "C20": (55.0, 101.5, 0, B), "C21": (55.0, 110.5, 0, B), "C28": (60.5, 110.5, 0, B),
    "SW3": (4.2, 88.0, 90, B),
    "J5": (83.6, 112.0, 270, B),
    # Test points along the bottom of the back.
    "TP1": (70.0, 98.0, 0, B), "TP2": (70.0, 94.0, 0, B), "TP3": (66.0, 98.0, 0, B),
    "TP4": (66.0, 94.0, 0, B), "TP5": (16.0, 42.0, 0, B), "TP6": (62.0, 94.0, 0, B),
}
# Button pull-ups: two rows beside the expander.
for i in range(8):
    PLACE[f"R{50 + i}"] = (20.0 + (i % 4) * 2.2, 74.0 + (i // 4) * 2.4, 90, B)

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
    x, y, w, h = FPC_SLOT
    add_rounded_rect(board, e, x, y, w, h, w / 2 - 0.01)
    # Speaker grille: 1.2 mm holes on a hex grid over the speaker.
    sx, sy, sw, sh = SPEAKER
    cx, cy = sx + sw / 2, sy + sh / 2
    for row in range(-2, 3):
        for col in range(-3, 4):
            hx = cx + col * 2.0 + (1.0 if row % 2 else 0.0)
            hy = cy + row * 1.75
            if abs(hx - cx) <= 6.0 and abs(hy - cy) <= 4.0:
                add_circle(board, e, (hx, hy), 0.6)


def silkscreen(board):
    fs, bs = pcbnew.F_SilkS, pcbnew.B_SilkS
    x, y, w, h = CARD
    add_rounded_rect(board, fs, x, y, w, h, 2.5, 0.2)
    add_text(board, fs, "OREO", x + 7, y + 3.2, 1.6, 0.3, bold=True)
    add_text(board, fs, "your name card goes here", x + w / 2, y + h / 2, 1.2, 0.15)
    # Panel corner marks (the panel itself is placed by hand).
    px, py, pw, ph = PANEL
    for (cx, cy, dx, dy) in ((px, py, 1, 1), (px + pw, py, -1, 1), (px, py + ph, 1, -1), (px + pw, py + ph, -1, -1)):
        add_line(board, pcbnew.F_Fab, (cx, cy), (cx + 3 * dx, cy), 0.1)
        add_line(board, pcbnew.F_Fab, (cx, cy), (cx, cy + 3 * dy), 0.1)
    add_rect(board, pcbnew.F_Fab, px, py, pw, ph, 0.1)
    add_text(board, pcbnew.F_Fab, "DT028BTFT 2.8in panel", px + pw / 2, py + ph / 2, 1.5)
    for label, (bx, by) in (("UP", (80.5, 72.2)), ("C", (80.5, 90.2)), ("DOWN", (80.5, 108.2)),
                            ("LEFT", (8.5, 116.8)), ("RIGHT", (19.5, 116.8)), ("HOME", (31.0, 116.8)),
                            ("B", (58.0, 116.8)), ("A", (70.0, 116.8))):
        add_text(board, fs, label, bx, by, 0.9, 0.15)
    add_text(board, fs, "CHG", 44.0, 114.2, 0.8, 0.12)
    sx, sy, sw, sh = SPEAKER
    # Back.
    bx, by, bw, bh = BATTERY
    add_rect(board, pcbnew.B_Fab, bx, by, bw, bh, 0.1)
    add_rect(board, pcbnew.B_CrtYd, bx, by, bw, bh, 0.05)
    add_text(board, bs, "LiPo 1000 mAh 603450", bx + bw / 2, by + bh / 2 - 2, 1.2, 0.15, mirror=True)
    add_text(board, bs, "JST-PH: check polarity", bx + bw / 2, by + bh / 2 + 1, 1.0, 0.15, mirror=True)
    add_rect(board, pcbnew.B_Fab, sx, sy, sw, sh, 0.1)
    add_rect(board, pcbnew.B_CrtYd, sx, sy, sw, sh, 0.05)
    add_text(board, bs, "OREO BADGE rev 1.0", 44.0, 92.0, 1.5, 0.25, mirror=True, bold=True)
    add_text(board, bs, "oreo.elixpo.com", 44.0, 95.0, 1.0, 0.15, mirror=True)
    add_text(board, bs, "CERN-OHL-P-2.0  OSHWA IN000107", 44.0, 97.5, 0.9, 0.15, mirror=True)
    add_text(board, bs, "RST", 64.0, 115.2, 0.8, 0.12, mirror=True)
    add_text(board, bs, "BOOT", 64.0, 127.0, 0.8, 0.12, mirror=True)
    add_text(board, bs, "ON", 4.2, 81.5, 0.8, 0.12, mirror=True)
    add_text(board, bs, "microSD", 11.0, 94.0, 0.8, 0.12, mirror=True)
    add_text(board, bs, "Qwiic", 83.6, 106.0, 0.8, 0.12, mirror=True)
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
    gnd = board.FindNet("GND")
    v33 = board.FindNet("+3V3")
    full = [(0.3, 0.3), (W - 0.3, 0.3), (W - 0.3, H - 0.3), (0.3, H - 0.3)]
    zone(board, gnd, pcbnew.In1_Cu, full)                 # solid return plane under everything
    zone(board, v33, pcbnew.In2_Cu, full)                 # 3.3 V plane
    zone(board, gnd, pcbnew.F_Cu, full, clearance=0.3)    # ground fill, stitched to In1
    zone(board, gnd, pcbnew.B_Cu, full, clearance=0.3)
    # Antenna: no copper on any layer beside or under the antenna, per the
    # ESP32-S3-WROOM-1 datasheet; the module's antenna end is on the top edge.
    mx = PLACE["U1"][0]
    copper = [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]
    keepout(board, [(mx - 15.0, 0.0), (mx + 15.0, 0.0), (mx + 15.0, 7.0), (mx - 15.0, 7.0)],
            copper, "antenna keep-out")


def stackup(board):
    board.SetCopperLayerCount(4)
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
        if not re.match(r"(U\d|J\d|Q\d|SW3$)", ref) or ref == "U9":
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
    silkscreen(board)
    planes(board)

    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    board.Save(str(BOARD_FILE))
    write_netclasses()
    write_rules()
    print(f"Placed {len(footprints)} footprints on a {W:g} x {H:g} mm 4-layer board: {BOARD_FILE}")


if __name__ == "__main__":
    main()

#!/usr/bin/python3
"""Autoroute elixpo.kicad_pcb with Freerouting and pour the planes again.

    /usr/bin/python3 circuit/elixpo/route_badge_pcb.py [path/to/freerouting.jar] [passes]

1. Exports a Specctra DSN from a copy of the board without the ground fills
   on the outer layers (Freerouting treats any fill as an obstacle for other
   nets). The GND and 3.3 V planes on In1 and In2 stay, and pads reach them
   through vias.
2. Runs Freerouting headless and writes build/route.ses.
3. Imports the session into elixpo.kicad_pcb, refills every zone and saves.

Run it after generate_badge_pcb.py; running generate_badge_pcb.py again
discards the tracks.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/usr/lib/python3/dist-packages")
import pcbnew  # noqa: E402

HERE = Path(__file__).resolve().parent
BOARD = HERE / "elixpo.kicad_pcb"
BUILD = HERE / "build"
DSN = BUILD / "route.dsn"
SES = BUILD / "route.ses"
JAR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "src/freerouting-2.5.0/freerouting-2.5.0.jar"
PASSES = sys.argv[2] if len(sys.argv) > 2 else "40"


def export_dsn():
    board = pcbnew.LoadBoard(str(BOARD))
    for zone in list(board.Zones()):
        if not zone.GetIsRuleArea() and zone.GetLayer() in (pcbnew.F_Cu, pcbnew.B_Cu):
            board.Remove(zone)
    BUILD.mkdir(exist_ok=True)
    if not pcbnew.ExportSpecctraDSN(board, str(DSN)):
        raise SystemExit("DSN export failed")


def route():
    SES.unlink(missing_ok=True)
    cmd = ["java", "-jar", str(JAR), "-de", str(DSN), "-do", str(SES), "-mp", PASSES,
           "--gui.enabled=false"]
    print(" ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)
    if not SES.exists():
        raise SystemExit("Freerouting wrote no session file")


def import_ses():
    board = pcbnew.LoadBoard(str(BOARD))
    for track in list(board.GetTracks()):
        board.Remove(track)
    if not pcbnew.ImportSpecctraSES(board, str(SES)):
        raise SystemExit("SES import failed")
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(str(BOARD))
    tracks = [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T]
    vias = [t for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
    print(f"Imported {len(tracks)} track segments and {len(vias)} vias into {BOARD}")


if __name__ == "__main__":
    export_dsn()
    route()
    import_ses()

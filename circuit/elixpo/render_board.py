#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Re-render the board images and the website's 3D model from elixpo.kicad_pcb.

    python3 circuit/elixpo/render_board.py            # renders and GLB
    python3 circuit/elixpo/render_board.py --renders  # renders only
    python3 circuit/elixpo/render_board.py --glb      # GLB only

Renders: renders/front.jpg, back.jpg and top-angle.jpg, with the board
stackup colours (black mask, white silkscreen, HASL). Needs kicad-cli 10
and Pillow.

GLB: falera.elixpo/public/models/falera-badge.glb, the model the badge page's
3D viewer shows. kicad-cli exports the board with its component models; the
materials are retuned for a web viewer (opaque near-black mask with a satin
sheen, silver HASL pads), and `@gltf-transform/cli optimize` (fetched by npx)
dedups, welds and Draco-compresses it. Needs Node.js for npx.
"""
import argparse
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PCB = HERE / "elixpo.kicad_pcb"
RENDERS = HERE / "renders"
GLB_OUT = HERE.parent.parent / "falera.elixpo" / "public" / "models" / "falera-badge.glb"
GLTF_TRANSFORM = "@gltf-transform/cli@4.2.1"

RENDER = ["kicad-cli", "pcb", "render", "--use-board-stackup-colors",
          "--quality", "high", "--background", "opaque"]


def render_images(tmp):
    from PIL import Image

    def run(name, *args):
        out = tmp / f"{name}.png"
        subprocess.run(RENDER + list(args) + ["-o", str(out), str(PCB)],
                       check=True, stdout=subprocess.DEVNULL)
        return Image.open(out).convert("RGB")

    RENDERS.mkdir(exist_ok=True)
    for name, side in (("front", "top"), ("back", "bottom")):
        im = run(name, "-w", "1400", "-h", "2000", "--side", side)
        im = im.crop((36, 14, 1340, 1978))          # the board plus a thin margin
        im = im.resize((round(im.width * 0.62), round(im.height * 0.62)), Image.LANCZOS)
        im.save(RENDERS / f"{name}.jpg", quality=88, optimize=True, progressive=True)
    im = run("top-angle", "-w", "1800", "-h", "1800", "--perspective",
             "--rotate", "-40,0,30", "--zoom", "0.72")
    im.resize((1000, 1000), Image.LANCZOS).save(
        RENDERS / "top-angle.jpg", quality=88, optimize=True, progressive=True)
    print(f"renders -> {RENDERS}")


def tune_materials(src, dst):
    """Rewrite the PBR factors KiCad gives the board's own meshes."""
    b = src.read_bytes()
    n = struct.unpack("<I", b[12:16])[0]
    j = json.loads(b[20:20 + n])
    rest = b[20 + n:]
    looks = {
        "_soldermask": ([0.006, 0.006, 0.007, 1.0], 0.0, 0.38),
        "_pad":        ([0.80, 0.80, 0.82, 1.0], 1.0, 0.28),
        "_PCB":        ([0.42, 0.45, 0.29, 1.0], 0.0, 0.80),
    }
    for mesh in j["meshes"]:
        for suffix, (base, metal, rough) in looks.items():
            if mesh.get("name", "").endswith(suffix):
                for prim in mesh["primitives"]:
                    mat = j["materials"][prim["material"]]
                    mat.setdefault("pbrMetallicRoughness", {}).update(
                        baseColorFactor=base, metallicFactor=metal, roughnessFactor=rough)
                    mat.pop("alphaMode", None)
    js = json.dumps(j, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    dst.write_bytes(b"glTF" + struct.pack("<II", 2, 20 + len(js) + len(rest))
                    + struct.pack("<I", len(js)) + b"JSON" + js + rest)


def export_glb(tmp):
    raw, tuned = tmp / "raw.glb", tmp / "tuned.glb"
    res = subprocess.run(
        ["kicad-cli", "pcb", "export", "glb", "-f", "--subst-models",
         "--include-pads", "--include-silkscreen", "--include-soldermask",
         "-o", str(raw), str(PCB)],
        check=True, capture_output=True, text=True)
    missing = sorted({line for line in (res.stdout + res.stderr).splitlines()
                      if line.startswith("Could not add 3D model")})
    for line in missing:
        print("  " + line)
    tune_materials(raw, tuned)
    GLB_OUT.parent.mkdir(parents=True, exist_ok=True)
    # Instancing is off: it confuses bounding boxes in some viewers.
    # Simplification is off, to keep the full detail of the KiCad models.
    subprocess.run(["npx", "-y", GLTF_TRANSFORM, "optimize", str(tuned), str(GLB_OUT),
                    "--compress", "draco", "--texture-compress", "false",
                    "--instance", "false", "--simplify", "false"],
                   check=True, cwd=tmp)
    print(f"GLB {raw.stat().st_size / 1e6:.1f} MB -> {GLB_OUT} "
          f"{GLB_OUT.stat().st_size / 1e3:.0f} kB")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--renders", action="store_true", help="only the JPEG renders")
    ap.add_argument("--glb", action="store_true", help="only the web GLB")
    a = ap.parse_args()
    both = not (a.renders or a.glb)
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        if both or a.renders:
            render_images(tmp)
        if both or a.glb:
            export_glb(tmp)
    return 0


if __name__ == "__main__":
    sys.exit(main())

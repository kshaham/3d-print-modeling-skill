"""Template: copy to <project>/print/author_<name>.py, rename NAME, replace build().

A small but complete printable part: a wall bracket for two M4 screws. It shows each step once:
  - the part designed for the way it will print (flat on its base, no support anywhere);
  - holes sized for printing, a horizontal hole with a self-supporting roof, a 45 degree rib;
  - a chamfer round the bed face;
  - the printability check as a gate, the export, the manifest and the review board.

  python <skill>/scripts/blender_run.py print/author_<name>.py [--review] [--out DIR]

Writes DIR/<NAME>.3mf, .stl, .json and .blend (DIR defaults to print/out beside this script), and
with --review DIR/<NAME>-review.png. Exits 1 when the check fails, so nothing unprintable ships.
"""
import os
import sys

sys.path.insert(0, os.environ["PRINT_SKILL_SCRIPTS"])   # set by blender_run.py
import printkit as pk  # noqa: E402

NAME = "wall-bracket"
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = ARGS[ARGS.index("--out") + 1] if "--out" in ARGS else \
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")

# Dimensions in millimetres. Name every number that someone may want to change.
BASE = (60.0, 30.0, 4.0)          # length, width, thickness of the plate that sits on the bed
WALL_H, WALL_T = 40.0, 4.0        # upright
RIB_T = 4.0                       # gusset thickness
SCREW = pk.SCREW["M4"]
PEG_D = 5.0                       # horizontal hole for a peg or cable

# What the slicer should be told. Copied into the manifest for whoever prints it.
SETTINGS = {
    "orientation": "as exported, base plate on the bed",
    "layer_height_mm": 0.2,
    "walls": 3,                   # the load runs through the walls: more walls beat more infill
    "infill_percent": 20,
    "supports": "none",
    "brim": "none",
}


def build():
    pk.new_scene()
    sx, sy, sz = BASE

    # Big forms first: plate, upright, and a rib whose slope is exactly 45 degrees.
    body = pk.prism(pk.rounded_rect(sx, sy, 4.0), sz, name=NAME)
    upright = pk.box(WALL_T, sy, WALL_H, at=(-sx / 2 + WALL_T / 2, 0, 0))
    rib = pk.prism([(0, 0), (20, 0), (0, 20)], RIB_T, at=(-sx / 2 + WALL_T, -RIB_T / 2, sz), axis="y")
    pk.union(body, upright, rib)

    # Vertical screw holes: printed holes come out small, so model them larger (hole_d).
    for x in (0.0, 18.0):
        pk.cut(body, pk.counterbore(pk.hole_d(SCREW["clear"]), SCREW["head_d"] + 0.4, SCREW["head_h"],
                                    depth=sz, at=(x, 0, sz)))

    # A horizontal hole would need support under its roof; a teardrop roof prints clean.
    pk.cut(body, pk.teardrop(pk.hole_d(PEG_D), WALL_T + 2.0, at=(-sx / 2 - 1.0, 0, 28.0), axis="x"))

    # Chamfer the edge on the bed: hides elephant's foot and lets the part release.
    pk.chamfer(body, 0.5, "bottom")
    return pk.to_bed(body)


if __name__ == "__main__":
    part = build()
    report = pk.check(part)                                  # reads the saved printer profile
    pk.save_blend(os.path.join(OUT, NAME + ".blend"))
    if not report["pass"]:
        sys.exit(1)
    pk.export(part, os.path.join(OUT, NAME), formats=("3mf", "stl"), settings=SETTINGS, report=report)
    if "--review" in ARGS:
        import print_review as pr
        pr.review(objects=[part], out=os.path.join(OUT, NAME + "-review.png"))
        print("REVIEW BOARD", os.path.join(OUT, NAME + "-review.png"))

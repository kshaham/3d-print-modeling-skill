"""Clearance gauge: print once per printer and material, then design fits from what you measure.

A plate with six holes for an 8 mm pin, each hole larger by a marked clearance per side
(0.05 to 0.40 mm), and the pin. Push the pin through each hole and note which clearance gives
a press fit, a snug fit and a free slide. Save the result with the printer profile:

  python <skill>/scripts/printer_profile.py --set notes="PETG: press 0.05, snug 0.15, slide 0.25"

  python <skill>/scripts/blender_run.py <skill>/assets/author_fit_gauge.py [--out DIR] [--review]

Prints flat with no support in about 20 minutes. The numbers engraved beside the holes are the
clearance per side in hundredths of a millimetre.
"""
import os
import sys

sys.path.insert(0, os.environ["PRINT_SKILL_SCRIPTS"])   # set by blender_run.py
import printkit as pk  # noqa: E402

NAME = "fit-gauge"
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = ARGS[ARGS.index("--out") + 1] if "--out" in ARGS else os.path.join(os.getcwd(), "out")

PIN_D = 8.0
CLEARANCES = (0.05, 0.10, 0.15, 0.20, 0.30, 0.40)      # per side
PITCH, THICK = 13.0, 6.0


def build():
    pk.new_scene()
    length = PITCH * len(CLEARANCES) + 4.0
    plate = pk.prism(pk.rounded_rect(length, 24.0, 3.0), THICK, name=NAME)
    for i, c in enumerate(CLEARANCES):
        x = (i - (len(CLEARANCES) - 1) / 2.0) * PITCH
        pk.cut(plate, pk.cylinder(PIN_D + 2.0 * c, THICK + 2.0, at=(x, 3.0, -1.0)))
        pk.cut(plate, pk.text(f"{round(c * 100):02d}", 4.5, 0.6, at=(x, -8.0, THICK - 0.6)))
    pk.chamfer(plate, 0.5, "bottom")
    pin = pk.cylinder(PIN_D, 16.0, at=(0, 24.0, 0), name=NAME + "-pin")
    pk.chamfer(pin, 0.5, "bottom")
    pk.chamfer(pin, 0.5, "top")
    return [plate, pin]


if __name__ == "__main__":
    parts = build()
    report = pk.check(parts)
    if "--review" in ARGS or not report["pass"]:
        import print_review as pr
        pr.review(objects=parts, out=os.path.join(OUT, NAME + "-review.png"))
    if not report["pass"]:
        sys.exit(1)
    pk.export(parts, os.path.join(OUT, NAME), formats=("3mf", "stl"), report=report, keep_origin=True,
              settings={"layer_height_mm": 0.2, "walls": 3, "supports": "none",
                        "note": "print in the material and with the profile you will use for real parts"})

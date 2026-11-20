"""Self-test: builds known-good and known-bad models and checks that every tool sees them correctly.

Run it after installing the skill, after a Blender update, or after changing a script:

  python scripts/blender_run.py self_test.py

It ignores the saved printer profile, writes only to a temporary folder, and exits 1 if any
expectation fails. Takes about half a minute.
"""
import os
import shutil
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
TMP = tempfile.mkdtemp(prefix="print_self_test_")
os.environ["PRINT_PROFILE"] = os.path.join(TMP, "no-profile.json")     # defaults, whoever runs it

import bmesh  # noqa: E402
import printkit as pk  # noqa: E402
import print_check as pc  # noqa: E402
import print_export as px  # noqa: E402
import print_orient as po  # noqa: E402
import print_review as pr  # noqa: E402

RESULTS = []


def expect(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(("ok    " if ok else "FAIL  ") + name + (f"   [{detail}]" if detail and not ok else ""))


def has(report, kind, text):
    return any(text in line for line in report[kind])


def bracket():
    body = pk.prism(pk.rounded_rect(60, 30, 4), 4, name="bracket")
    pk.union(body, pk.box(4, 30, 40, at=(-28, 0, 0)),
             pk.prism([(0, 0), (20, 0), (0, 20)], 4, at=(-26, -2, 4), axis="y"))
    s = pk.SCREW["M4"]
    for x in (0, 18):
        pk.cut(body, pk.counterbore(pk.hole_d(s["clear"]), s["head_d"] + 0.4, s["head_h"], 4, at=(x, 0, 4)))
    pk.cut(body, pk.teardrop(pk.hole_d(5), 6, at=(-31, 0, 28), axis="x"))
    pk.chamfer(body, 0.5, "bottom")
    return pk.to_bed(body)


def main():
    # ---- a good part, and its files
    pk.new_scene()
    part = bracket()
    r = pc.run(objects=[part])
    expect("bracket passes", r["pass"], r["errors"])
    expect("bracket needs no support", r["orientation"]["support_area_mm2"] < 1.0)
    expect("bracket is one closed shell", r["shells"] == 1 and r["topology"]["open_edges"] == 0)
    expect("bracket size", [round(x) for x in r["size_mm"]] == [60, 30, 40], r["size_mm"])
    out = px.export([part], os.path.join(TMP, "bracket"), formats=("3mf", "stl"), report=r)
    expect("export writes 3mf, stl and manifest", all(os.path.isfile(f) for f in out["files"] + [out["manifest"]]))
    for ext in ("3mf", "stl"):
        pk.new_scene()
        back = pc.run(path=os.path.join(TMP, "bracket." + ext))
        expect(f"{ext} reads back with the same volume",
               back["pass"] and abs(back["volume_mm3"] - r["volume_mm3"]) < 1.0, back.get("volume_mm3"))
    pk.new_scene()
    part = bracket()
    board = os.path.join(TMP, "bracket.png")
    pr.review(objects=[part], out=board, tile=160)
    expect("review board is written", os.path.isfile(board) and os.path.getsize(board) > 10000)

    # ---- overhangs, bridges, orientation
    pk.new_scene()
    tee = pk.union(pk.box(10, 10, 30), pk.box(50, 10, 6, at=(0, 0, 30)))
    r = pc.run(objects=[tee])
    expect("T shape needs support under its arms", 390 < r["orientation"]["support_area_mm2"] < 410,
           r["orientation"]["support_area_mm2"])
    ranked, _ = po.rank(objects=[tee])
    expect("orientation ranker lays the T down", ranked[0]["support_area_mm2"] < 1.0 and ranked[0]["size_mm"][2] < 11)
    po.apply(tee, ranked[0])
    expect("applied orientation needs no support", pc.run(objects=[tee])["orientation"]["support_area_mm2"] < 1.0)

    def bridge(span):
        pk.new_scene()
        half = span / 2.0 + 2.5
        return pk.union(pk.box(5, 10, 20, at=(-half, 0, 0)), pk.box(5, 10, 20, at=(half, 0, 0)),
                        pk.box(span + 10, 10, 4, at=(0, 0, 20)))
    r = pc.run(objects=[bridge(20)])
    expect("20 mm bridge prints unsupported in PLA", r["orientation"]["support_area_mm2"] < 1.0
           and r["orientation"]["bridges"][0]["span_mm"] == 20.0, r["orientation"]["bridges"])
    r = pc.run(objects=[bridge(25)], material="petg")
    expect("25 mm bridge is too long for PETG", has(r, "warnings", "flat span"))
    r = pc.run(objects=[bridge(60)])
    expect("60 mm bridge is flagged", has(r, "warnings", "flat span") and r["orientation"]["support_area_mm2"] > 500)

    pk.new_scene()
    blk = pk.cut(pk.box(30, 30, 30), pk.cylinder(16, 40, at=(-20, 0, 15), axis="x"))
    r1 = pc.run(objects=[blk])
    pk.new_scene()
    blk = pk.cut(pk.box(30, 30, 30), pk.teardrop(16, 40, at=(-20, 0, 15), axis="x"))
    r2 = pc.run(objects=[blk])
    expect("round side hole needs support, teardrop does not",
           r1["orientation"]["support_area_mm2"] > 100 and r2["orientation"]["support_area_mm2"] < 1.0)

    pk.new_scene()
    table = pk.union(pk.box(40, 40, 5, at=(0, 0, 30)), pk.box(6, 6, 30, at=(-15, -15, 0)),
                     pk.cylinder(4, 10, at=(10, 10, 21), d_top=8))
    r = pc.run(objects=[table])
    expect("hanging cone is a mid-air start", r["orientation"]["midair_starts"] == 1, r["orientation"]["midair_at"])

    # ---- walls, cavities, gaps
    pk.new_scene()
    shell = pk.cut(pk.box(30, 30, 30), pk.box(29.4, 29.4, 29.4, at=(0, 0, 0.3)))
    r = pc.run(objects=[shell])
    expect("0.3 mm walls fail", not r["pass"] and has(r, "errors", "thinner than"))
    expect("sealed cavity is found", r["cavities"]["count"] == 1 and 25000 < r["cavities"]["volume_mm3"] < 26000)
    expect("sealed cavity is an error for resin", has(pc.run(objects=[shell], process="resin"), "errors", "drain"))
    pk.new_scene()
    cup = pk.lathe([(0, 0), (20, 0), (25, 40), (22, 40), (18, 3), (0, 3)])
    r = pc.run(objects=[cup])
    expect("cup passes with no false mid-air start", r["pass"] and r["orientation"]["midair_starts"] == 0)

    def pin_in_ring(clearance):
        pk.new_scene()
        ring = pk.cut(pk.cylinder(20, 8), pk.cylinder(10 + 2 * clearance, 10, at=(0, 0, -1)))
        return [ring, pk.cylinder(10, 8, name="pin")]
    expect("0.08 mm gap fuses", has(pc.run(objects=pin_in_ring(0.08)), "warnings", "will fuse"))
    expect("0.30 mm gap is clear", not has(pc.run(objects=pin_in_ring(0.30)), "warnings", "will fuse"))

    # ---- broken, oversized and mis-scaled models
    pk.new_scene()
    cube = pk.box(20, 20, 20)
    bm = bmesh.new()
    bm.from_mesh(cube.data)
    bmesh.ops.delete(bm, geom=[max(bm.faces, key=lambda f: f.calc_center_median().z)], context="FACES")
    bm.to_mesh(cube.data)
    bm.free()
    expect("open mesh fails", has(pc.run(objects=[cube]), "errors", "not watertight"))
    pk.new_scene()
    expect("oversized part fails", has(pc.run(objects=[pk.box(300, 100, 10)]), "errors", "does not fit"))
    pk.new_scene()
    r = pc.run(objects=[pk.box(0.05, 0.02, 0.01)], unit="m")
    expect("metres convert to millimetres", [round(x) for x in r["size_mm"]] == [50, 20, 10], r["size_mm"])

    # ---- colours and parts
    pk.new_scene()
    plate = pk.prism(pk.rounded_rect(50, 20, 3), 3, name="tag")
    logo = pk.text("PRINT", 8, 0.6, at=(0, 0, 2.4), name="tag-text")
    pk.cut(plate, logo, keep=True)
    pk.colour(plate, "#222", "black")
    pk.colour(logo, "#e9c46a", "sand")
    r = pc.run(objects=[plate, logo])
    expect("two-colour inlay passes", r["pass"] and not r["warnings"], r["errors"] + r["warnings"])
    expect("colour is confined to the top layers", r["colours"]["count"] == 2
           and 1 <= r["colours"]["layers_with_several"] <= 4, r["colours"])
    out = px.export([plate, logo], os.path.join(TMP, "tag"), formats=("3mf",))
    parts = pc.read_3mf(out["files"][0], colours=True)
    expect("3mf keeps the two parts and their colours",
           [(n, c) for n, _v, _t, c in parts] == [("tag", "#222222"), ("tag-text", "#E9C46A")], parts and parts[0][3])
    with zipfile.ZipFile(out["files"][0]) as z:
        names = z.namelist()
        model = z.read("3D/3dmodel.model").decode()
        cfg = z.read("Metadata/model_settings.config").decode() if "Metadata/model_settings.config" in names else ""
    expect("3mf is one object with two parts, filaments 1 and 2",
           model.count("<component ") == 2 and model.count("<item ") == 1
           and 'key="extruder" value="2"' in cfg)

    # ---- splitting
    pk.new_scene()
    ball = pk.union(pk.sphere(60, at=(0, 0, 30)), pk.cylinder(20, 50, at=(0, 0, 50)))
    low, high, pegs = pk.split(ball, "z", 30.0, pins=3)
    pk.rotate(low, "x", 180)
    ok = len(pegs) == 3
    for ob in [low, high] + pegs:
        pk.to_bed(ob)
        r = pc.run(objects=[ob])
        ok = ok and r["pass"] and r["orientation"]["support_area_mm2"] < 1.0
    expect("split halves and pegs print without support", ok)

    failed = [n for n, ok in RESULTS if not ok]
    print(f"SELF-TEST {'PASS' if not failed else 'FAIL'}  {len(RESULTS) - len(failed)} of {len(RESULTS)}")
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

"""Rank the ways a model can sit on the bed: least support, least time, good bed contact.

Runs inside Blender (5.x). Tries every large flat face the model can rest on plus the six axis
directions, and scores each with the same analysis as print_check.py.

  blender -b --factory-startup -P print_orient.py -- MODEL.stl [--top 5] [--apply OUT.3mf]
          [--strong-axis x|y|z] [print_check options: --process --nozzle --layer --overhang --build ...]

  --apply OUT       write the best orientation to OUT (.3mf or .stl), sitting on Z=0
  --strong-axis A   the model axis along which the part is pulled or bent hardest. Layers are weakest
                    when that axis is vertical, so those orientations are penalised and flagged

Each result gives `rotate_xyz_deg`: the Euler XYZ rotation that puts the model in that orientation.

From another script running in Blender:
  import print_orient as po
  ranked = po.rank(objects=[obj])            # list of dicts, best first
  po.apply(obj, ranked[0])                   # rotate the object's mesh and sit it on the bed
"""
import argparse
import json
import math
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import print_check as pc  # noqa: E402
import print_export as px  # noqa: E402


def candidates(verts, tris, limit=14):
    """Unit vectors (model space) that could face the bed."""
    normal, area, cen = pc.face_data(verts, tris)
    key = np.round(normal * 24.0).astype(np.int64)
    _, inv = np.unique(key, axis=0, return_inverse=True)
    inv = inv.ravel()
    weight = np.bincount(inv, weights=area)
    found = []
    for b in np.argsort(-weight)[:80].tolist():
        sel = inv == b
        n = (normal[sel] * area[sel, None]).sum(axis=0)
        length = np.linalg.norm(n)
        if length < 1e-9:
            continue
        n /= length
        far = float((verts @ n).max())
        resting = sel & ((cen @ n) > far - 0.05)       # faces of this direction on the outermost plane
        flat = float(area[resting].sum())
        if flat > 1.0:
            found.append((flat, n))
    found.sort(key=lambda f: -f[0])
    dirs = [n for _f, n in found[:limit]]
    for axis in np.concatenate([np.eye(3), -np.eye(3)]):
        dirs.append(axis)
    unique = []
    for d in dirs:
        if all(float(d @ u) < 0.996 for u in unique):
            unique.append(d)
    return unique


def rotation_for(down):
    """Matrix that turns the model so `down` faces the bed (-Z)."""
    return Vector(down).rotation_difference(Vector((0.0, 0.0, -1.0))).to_matrix()


def rank(path=None, objects=None, unit="auto", strong_axis=None, **kw):
    opts = pc.options(**kw)
    if path:
        objs, mm = pc.load_model(path, unit)
    else:
        objs = [bpy.data.objects[o] if isinstance(o, str) else o for o in objects] if objects \
            else pc.scene_objects()
        mm = pc.scene_mm_per_unit(unit)
    verts, tris, _owner, _parts, _welded = pc.collect(objs, mm)
    _n, area, _c = pc.face_data(verts, tris)
    labels, count = pc.shells(verts, tris)
    volume = float(abs(pc.signed_volumes(verts, tris, labels, count)[0].sum()))
    total_area = float(area.sum())
    strong = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}.get((strong_axis or "").lower())
    results = []
    for down in candidates(verts, tris):
        rot = rotation_for(down)
        r = np.array(rot)
        v = verts @ r.T
        orient, _masks = pc.analyse(v, tris, opts, detail=False, touching=count > 1)
        est = pc.estimate(volume, total_area, orient, opts)
        size = v.max(axis=0) - v.min(axis=0)
        b = opts["build"]
        fits = (size[0] <= b[0] and size[1] <= b[1] or size[0] <= b[1] and size[1] <= b[0]) and size[2] <= b[2]
        notes = []
        # minutes, plus a minute for every 25 mm2 that must be supported (removal, scarred surface)
        score = est["time_min_rough"] + orient["support_area_mm2"] / 25.0
        if not fits:
            score += 1e6
            notes.append("does not fit the build volume")
        if opts["supports"]:
            if orient["bed_contact_mm2"] < 20.0:
                score += 1000.0
                notes.append("almost no flat bed contact")
            elif orient["height"] > 5.0 * max(min(orient["bed_footprint_mm"]), 1e-6):
                score *= 1.2
                notes.append("tall and narrow: needs a brim")
        weak = False
        if strong is not None:
            weak = abs(float((r @ np.array(strong, dtype=float))[2])) > 0.7
            if weak:
                score *= 1.5
                notes.append("layers are perpendicular to the main load: weakest this way up")
        euler = rot.to_euler("XYZ")
        results.append({
            "down": [round(float(c), 4) for c in down],
            "rotate_xyz_deg": [round(math.degrees(a), 2) + 0.0 for a in euler],
            "matrix": [[round(float(c), 6) for c in row] for row in r],
            "size_mm": [round(float(s), 2) for s in size],
            "bed_contact_mm2": orient["bed_contact_mm2"],
            "support_area_mm2": orient["support_area_mm2"],
            "support_volume_cm3": round(orient["support_volume_mm3"] / 1000.0, 2),
            "bridges": len(orient["bridges"]),
            "layers": orient["layers"], "time_min_rough": est["time_min_rough"], "mass_g": est["mass_g"],
            "fits_build": bool(fits), "weak_along_load": weak, "notes": notes, "score": round(score, 1),
        })
    results.sort(key=lambda x: x["score"])
    for i, x in enumerate(results, 1):
        x["rank"] = i
    return results, (verts, tris, objs)


def apply(ob, result):
    """Rotate the object's mesh into a ranked orientation and sit it on the bed, centred."""
    m = Matrix(result["matrix"]).to_4x4()
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.transform(m @ ob.matrix_world)
    lo = Vector((min(v.co.x for v in bm.verts), min(v.co.y for v in bm.verts), min(v.co.z for v in bm.verts)))
    hi = Vector((max(v.co.x for v in bm.verts), max(v.co.y for v in bm.verts), max(v.co.z for v in bm.verts)))
    bmesh.ops.translate(bm, vec=(-(lo.x + hi.x) / 2.0, -(lo.y + hi.y) / 2.0, -lo.z), verts=bm.verts[:])
    bm.to_mesh(ob.data)
    bm.free()
    ob.matrix_world = Matrix.Identity(4)
    ob.data.update()
    return ob


def table(results, top):
    lines = ["rank  rotate XYZ deg             size mm               contact  support   time  notes"]
    for x in results[:top]:
        rot = "(%g, %g, %g)" % tuple(x["rotate_xyz_deg"])
        size = "%g x %g x %g" % tuple(x["size_mm"])
        lines.append(f"{x['rank']:>4}  {rot:<25}  {size:<20}  {x['bed_contact_mm2']:>6.0f}  "
                     f"{x['support_area_mm2']:>6.0f}  {x['time_min_rough']:>5}  {'; '.join(x['notes'])}")
    lines.append("contact and support in mm2, time in minutes (rough). Best first.")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(prog="print_orient.py", description=__doc__.split("\n")[0])
    pc.add_arguments(p)
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--apply")
    p.add_argument("--strong-axis", choices=["x", "y", "z"])
    a = p.parse_args(pc.cli_argv())
    results, (verts, tris, objs) = rank(path=a.model, objects=a.objects, strong_axis=a.strong_axis,
                                        **pc.kwargs_from(a))
    print(table(results, a.top))
    out = {"ok": True, "orientations": results[:a.top]}
    if a.apply and results:
        r = np.array(results[0]["matrix"])
        v = verts @ r.T
        lo, hi = v.min(axis=0), v.max(axis=0)
        v = v - np.array([(lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0, lo[2]])
        path = os.path.abspath(a.apply)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        name = os.path.splitext(os.path.basename(path))[0]
        if path.lower().endswith(".stl"):
            px.write_stl(path, v, tris, name)
        else:
            px.write_3mf(path, [(name, v, tris)], name)
        print("WROTE", path)
        out["applied"] = path
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1, default=pc.to_json)
    print(pc.MARK + json.dumps(out, default=pc.to_json, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()

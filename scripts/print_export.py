"""Export print files in millimetres: 3MF and/or binary STL, with a manifest.

Runs inside Blender (5.x). Writes its own files, so no add-on is needed for 3MF.

  blender -b scene.blend -P print_export.py -- --out build/bracket [--format 3mf stl]
          [--objects A B] [--split] [--keep-origin] [--unit auto|mm|cm|m|in]

  --out BASE       path without extension: writes BASE.3mf, BASE.stl, BASE.json
  --format         3mf (default) and/or stl. 3MF carries its unit and several parts in one file.
  --split          one STL per object (BASE-<object>.stl); the 3MF always keeps objects as separate parts
  --keep-origin    keep coordinates as modelled. Default: lowest point moved to Z=0, XY centred on the origin

From another script running in Blender:
  import print_export as px
  files = px.export([obj], "build/bracket", formats=("3mf", "stl"), settings={"layer_height": 0.2})
"""
import argparse
import json
import os
import sys
import zipfile

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import print_check as pc  # noqa: E402


def write_stl(path, verts, tris, name="part"):
    v = verts[tris].astype("<f4")
    n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
    length = np.linalg.norm(n, axis=1)
    n = (n / np.maximum(length, 1e-30)[:, None]).astype("<f4")
    rec = np.zeros(len(tris), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["n"], rec["v"] = n, v
    with open(path, "wb") as f:
        f.write(f"binary STL, millimetres: {name}".encode("ascii", "replace")[:80].ljust(80, b" "))
        f.write(np.uint32(len(tris)).tobytes())
        f.write(rec.tobytes())


def _xml(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def write_3mf(path, parts, title="part", colours=None):
    """parts: [(name, verts Nx3 mm, tris Mx3)]. Core 3MF, unit millimeter, one object per part.
    colours: optional [(hex "#RRGGBB" or None, filament name or None)] per part, written as base
    materials so the parts show in their colours; the slicer still assigns a filament to each part."""
    colours = colours or [(None, None)] * len(parts)
    used = [i for i, (c, _f) in enumerate(colours) if c]
    mat_id = len(parts) + 1
    out = ['<?xml version="1.0" encoding="UTF-8"?>\n'
           '<model unit="millimeter" xml:lang="en-US" '
           'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">\n'
           f' <metadata name="Title">{_xml(title)}</metadata>\n'
           ' <metadata name="Application">3d-print-modeling skill</metadata>\n <resources>\n']
    if used:
        out.append(f'  <basematerials id="{mat_id}">\n')
        for i in used:
            c, f = colours[i]
            out.append(f'   <base name="{_xml(f or parts[i][0])}" displaycolor="{_xml(c.upper())}"/>\n')
        out.append('  </basematerials>\n')
    for i, (name, verts, tris) in enumerate(parts, 1):
        mat = f' pid="{mat_id}" pindex="{used.index(i - 1)}"' if (i - 1) in used else ""
        out.append(f'  <object id="{i}" type="model"{mat} name="{_xml(name)}">\n   <mesh>\n    <vertices>\n')
        out.append("".join(f'     <vertex x="{x:.5f}" y="{y:.5f}" z="{z:.5f}"/>\n' for x, y, z in verts.tolist()))
        out.append("    </vertices>\n    <triangles>\n")
        out.append("".join(f'     <triangle v1="{a}" v2="{b}" v3="{c}"/>\n' for a, b, c in tris.tolist()))
        out.append("    </triangles>\n   </mesh>\n  </object>\n")
    out.append(" </resources>\n <build>\n")
    out.append("".join(f'  <item objectid="{i}"/>\n' for i in range(1, len(parts) + 1)))
    out.append(" </build>\n</model>\n")
    types = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
             '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="/3D/3dmodel.model" Id="rel0" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", types)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", "".join(out))


def export(objects=None, out_base="part", formats=("3mf",), split=False, keep_origin=False, unit="auto",
           settings=None, report=None):
    """Write the files; return {"files": [...], "manifest": path}. `settings` (recommended slicer
    settings) and `report` (a print_check report) are copied into the manifest."""
    objs = [bpy.data.objects[o] if isinstance(o, str) else o for o in objects] if objects \
        else pc.scene_objects()
    if not objs:
        raise ValueError("no mesh objects to export")
    mm = pc.scene_mm_per_unit(unit)
    parts, colours = [], []
    for ob in objs:
        bm, _ = pc.gather([ob], mm)
        verts, tris = pc.arrays(bm)
        bm.free()
        if len(tris):
            parts.append((ob.name, verts, tris))
            colours.append((ob.get("print_colour"), ob.get("print_filament")))
    allv = np.concatenate([p[1] for p in parts])
    lo, hi = allv.min(axis=0), allv.max(axis=0)
    if not keep_origin:
        shift = np.array([(lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0, lo[2]])
        parts = [(n, v - shift, t) for n, v, t in parts]
    out_base = os.path.abspath(out_base)
    os.makedirs(os.path.dirname(out_base), exist_ok=True)
    title = os.path.basename(out_base)
    files = []
    if "3mf" in formats:
        write_3mf(out_base + ".3mf", parts, title, colours)
        files.append(out_base + ".3mf")
    if "stl" in formats:
        if split and len(parts) > 1:
            for name, v, t in parts:
                path = f"{out_base}-{name}.stl"
                write_stl(path, v, t, name)
                files.append(path)
        else:
            offset, vs, ts = 0, [], []
            for _n, v, t in parts:
                vs.append(v)
                ts.append(t + offset)
                offset += len(v)
            write_stl(out_base + ".stl", np.concatenate(vs), np.concatenate(ts), title)
            files.append(out_base + ".stl")
    manifest = {
        "name": title, "unit": "millimeter", "files": [os.path.basename(f) for f in files],
        "parts": [{"name": n, "triangles": int(len(t)), "colour": c, "filament": f,
                   "size_mm": [round(float(s), 3) for s in (v.max(axis=0) - v.min(axis=0))]}
                  for (n, v, t), (c, f) in zip(parts, colours)],
        "size_mm": [round(float(s), 3) for s in (hi - lo)],
        "print_orientation": "as exported: Z up, lowest face on the bed",
        "recommended_settings": settings or {},
    }
    if report:
        manifest["check"] = {k: report.get(k) for k in ("pass", "process", "volume_mm3", "orientation",
                                                        "walls", "estimate", "errors", "warnings", "advice")}
    with open(out_base + ".json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, default=pc.to_json)
    return {"files": files, "manifest": out_base + ".json"}


def main():
    p = argparse.ArgumentParser(prog="print_export.py", description=__doc__.split("\n")[0])
    p.add_argument("--out", required=True)
    p.add_argument("--format", nargs="+", default=["3mf"], choices=["3mf", "stl"])
    p.add_argument("--objects", nargs="+")
    p.add_argument("--split", action="store_true")
    p.add_argument("--keep-origin", action="store_true")
    p.add_argument("--unit", default="auto", choices=["auto"] + list(pc.UNIT_MM))
    a = p.parse_args(pc.cli_argv())
    res = export(a.objects, a.out, tuple(a.format), a.split, a.keep_origin, a.unit)
    for f in res["files"]:
        print("WROTE", f)
    print(pc.MARK + json.dumps(res), flush=True)


if __name__ == "__main__":
    main()

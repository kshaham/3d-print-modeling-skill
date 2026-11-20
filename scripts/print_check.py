"""Printability report for a mesh, in the orientation it will be printed (Z up, bed at its lowest point).

Runs inside Blender (5.x). All lengths in the report are millimetres.

  blender -b --factory-startup -P print_check.py -- MODEL.stl [options]
  blender -b scene.blend -P print_check.py -- [--objects A B] [options]

MODEL may be .stl .3mf .obj .ply .glb .gltf or .blend. Without MODEL the open scene is checked.
Several objects are the parts of one print (one per colour or material): each must be a closed
solid on its own, and they may touch.

Process, build volume, nozzle and material come from the saved printer profile
(printer_profile.py) unless a flag overrides them. Without a profile the defaults are those of a
Bambu Lab P1S: filament, 0.4 mm nozzle, 256 mm cube, PLA.

Options
  --objects A B        only these objects (default: every visible mesh)
  --process P          fdm | resin | sls
  --nozzle MM          FDM nozzle                  --layer MM     layer height (0.2 fdm, 0.05 resin, 0.1 sls)
  --min-wall MM        thinnest wall accepted without a warning (2 nozzle widths; 1.0 resin and sls)
  --overhang DEG       steepest angle from vertical that prints unsupported (45 fdm, 60 resin)
  --bridge MM          longest flat span between two anchors that prints unsupported
                       (PLA 30, PETG/ABS/ASA 20, nylon/PC 15, TPU 10; resin 5)
  --gap MM             facing surfaces closer than this fuse (0.15 fdm, 0.10 resin, 0.30 sls)
  --build X,Y,Z        printer build volume
  --material M         pla petg abs asa tpu pc pa pa12 resin (density and price for the estimate)
  --infill PCT         infill for the estimate (15)    --walls N   perimeters for the estimate (2)
  --unit U             length of one unit in the file: auto (default) | mm | cm | m | in
  --json PATH          also write the report here
  --no-intersections   skip the self-intersection test (slow above about 500k triangles)

Prints a readable summary and one line starting @@JSON@@ with the whole report.
Exit code 1 when the report has errors ("pass": false), so it can gate a build.

From another script running in Blender:
  import print_check as pc
  report = pc.run(objects=[obj], process="fdm")        # the open scene
  report = pc.run(path="part.stl", nozzle=0.6)
"""
import argparse
import json
import math
import os
import sys
import zipfile
import xml.etree.ElementTree as ET

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import printer_profile  # noqa: E402

MARK = "@@JSON@@"

PROCESS = {
    # overhang: degrees from vertical that print without support. bridge / cantilever: mm.
    "fdm": dict(layer=0.2, min_wall=None, hard_wall=None, overhang=45.0, bridge=30.0, cantilever=None,
                supports=True),
    "resin": dict(layer=0.05, min_wall=1.0, hard_wall=0.4, overhang=60.0, bridge=5.0, cantilever=1.0,
                  supports=True),
    "sls": dict(layer=0.1, min_wall=1.0, hard_wall=0.7, overhang=90.0, bridge=1e9, cantilever=1e9,
                supports=False),
}
# density g/cm3, price per kg (rough, for comparing designs; not a quote)
MATERIAL = {
    "pla": (1.24, 20.0), "petg": (1.27, 20.0), "abs": (1.04, 22.0), "asa": (1.07, 28.0),
    "tpu": (1.21, 35.0), "pc": (1.20, 45.0), "pa12": (1.01, 60.0), "pa": (1.14, 50.0),
    "resin": (1.15, 35.0),
}
# FDM limits that depend on the filament: longest clean bridge (mm), steepest overhang from vertical (deg)
FDM_LIMITS = {"pla": (30.0, 45.0), "petg": (20.0, 45.0), "abs": (20.0, 45.0), "asa": (20.0, 45.0),
              "tpu": (10.0, 40.0), "pc": (15.0, 45.0), "pa": (15.0, 45.0)}
# Average flow (mm3/s) a fast current printer sustains over a whole print with a 0.4 mm nozzle
# at 0.2 mm layers, fitted to Bambu Studio's P1S profiles. Older bed-slingers manage about half.
FDM_FLOW = {"pla": 8.0, "petg": 5.0, "abs": 7.0, "asa": 7.0, "tpu": 2.5, "pc": 5.0, "pa": 5.0}
SLOW_PRINTERS = ("ender 3", "ender-3", "mk3", "mk2", "prusa mini", "kobra 2", "cr-10", "anet", "ender 5")
# facing surfaces closer than this fuse together (mm)
GAP = {"fdm": 0.15, "resin": 0.10, "sls": 0.30}
UNIT_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4}
MM3_UNITS = {"micron": 0.001, "millimeter": 1.0, "centimeter": 10.0, "inch": 25.4, "foot": 304.8,
             "meter": 1000.0}
NS_CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
NS_PROD = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"


# --------------------------------------------------------------------------------------- loading

def _mesh_object(name, verts, tris, colour=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(t) for t in tris])
    me.update()
    ob = bpy.data.objects.new(name, me)
    if colour:
        ob["print_colour"] = colour[:7].upper()
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _affine_3mf(text):
    """3MF writes a 4x3 matrix in row-vector form; return it as a column-vector Matrix."""
    if not text:
        return Matrix.Identity(4)
    m = [float(x) for x in text.split()]
    return Matrix(((m[0], m[3], m[6], m[9]), (m[1], m[4], m[7], m[10]),
                   (m[2], m[5], m[8], m[11]), (0.0, 0.0, 0.0, 1.0)))


def read_3mf(path, colours=False):
    """Return [(name, verts Nx3 in mm, tris Mx3)]. Core spec plus the production extension's
    external object files (Bambu Studio and OrcaSlicer projects). With colours=True each entry
    gains a fourth item: the part's display colour ("#RRGGBB") or None."""
    out, cache, tint = [], {}, []
    with zipfile.ZipFile(path) as z:
        names = z.namelist()

        def model(part):
            part = part.lstrip("/")
            if part not in cache:
                root = ET.fromstring(z.read(part))
                scale = MM3_UNITS.get(root.get("unit", "millimeter"), 1.0)
                objs = {o.get("id"): o for o in root.iter(f"{{{NS_CORE}}}object")}
                cache[part] = (root, scale, objs)
            return cache[part]

        def colour_of(root, o):
            if o.get("pid") is None:
                return None
            for group in root.iter(f"{{{NS_CORE}}}basematerials"):
                if group.get("id") == o.get("pid"):
                    bases = list(group.iter(f"{{{NS_CORE}}}base"))
                    i = int(o.get("pindex", "0"))
                    return bases[i].get("displaycolor") if i < len(bases) else None
            return None

        def collect(part, oid, mat, name):
            root_, scale, objs = model(part)
            o = objs.get(oid)
            if o is None:
                return
            name = o.get("name") or name
            mesh = o.find(f"{{{NS_CORE}}}mesh")
            if mesh is not None:
                vs = np.array([[float(v.get("x")), float(v.get("y")), float(v.get("z"))]
                               for v in mesh.iter(f"{{{NS_CORE}}}vertex")], dtype=np.float64) * scale
                ts = np.array([[int(t.get("v1")), int(t.get("v2")), int(t.get("v3"))]
                               for t in mesh.iter(f"{{{NS_CORE}}}triangle")], dtype=np.int64)
                if len(vs) and len(ts):
                    m = np.array(mat)
                    vs = vs @ m[:3, :3].T + m[:3, 3]
                    if np.linalg.det(m[:3, :3]) < 0:
                        ts = ts[:, ::-1]
                    out.append((name or f"object_{oid}", vs, ts))
                    tint.append(colour_of(root_, o))
            for c in o.iter(f"{{{NS_CORE}}}component"):
                sub = c.get(f"{{{NS_PROD}}}path") or part
                t = _affine_3mf(c.get("transform"))
                t.translation = t.translation * scale
                collect(sub, c.get("objectid"), mat @ t, name)

        main = next((n for n in names if n.lower() == "3d/3dmodel.model"), None) or \
            next(n for n in names if n.lower().endswith(".model"))
        root, scale, _ = model(main)
        build = root.find(f"{{{NS_CORE}}}build")
        items = list(build.iter(f"{{{NS_CORE}}}item")) if build is not None else []
        for it in items:
            t = _affine_3mf(it.get("transform"))
            t.translation = t.translation * scale
            collect(it.get(f"{{{NS_PROD}}}path") or main, it.get("objectid"), t, None)
        if not items:
            for oid in model(main)[2]:
                collect(main, oid, Matrix.Identity(4), None)
    return [(n, v, t, c) for (n, v, t), c in zip(out, tint)] if colours else out


def load_model(path, unit="auto"):
    """Open or import a model. Return (objects, mm_per_blender_unit)."""
    ext = os.path.splitext(path)[1].lower()
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    if ext == ".blend":
        bpy.ops.wm.open_mainfile(filepath=path)
        return scene_objects(), scene_mm_per_unit(unit)
    before = set(bpy.data.objects)
    file_mm = 1.0
    if ext == ".stl":
        bpy.ops.wm.stl_import(filepath=path, global_scale=1.0, use_scene_unit=False,
                              forward_axis="Y", up_axis="Z")
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path, forward_axis="Y", up_axis="Z")
    elif ext == ".ply":
        bpy.ops.wm.ply_import(filepath=path, forward_axis="Y", up_axis="Z")
    elif ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
        file_mm = 1000.0  # glTF is metres
    elif ext == ".3mf":
        for name, vs, ts, colour in read_3mf(path, colours=True):
            _mesh_object(name, vs, ts, colour)
    else:
        raise ValueError(f"unsupported model type {ext}")
    objs = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    return objs, (UNIT_MM[unit] if unit in UNIT_MM else file_mm)


def scene_mm_per_unit(unit="auto"):
    if unit in UNIT_MM:
        return UNIT_MM[unit]
    us = bpy.context.scene.unit_settings
    return 1000.0 * us.scale_length if us.system != "NONE" else 1.0


def scene_objects(names=None):
    if names:
        missing = [n for n in names if n not in bpy.data.objects]
        if missing:
            raise ValueError(f"no such object: {', '.join(missing)}")
        return [bpy.data.objects[n] for n in names]
    return [o for o in bpy.context.scene.objects if o.type == "MESH" and not o.hide_render]


# ------------------------------------------------------------------------------------- gathering

def gather(objects, mm_per_bu=1.0):
    """One bmesh in millimetres, world space, modifiers applied, coincident vertices welded.
    Returns (bm, welded_vertex_count)."""
    deps = bpy.context.evaluated_depsgraph_get()
    bm = bmesh.new()
    scale = Matrix.Scale(mm_per_bu, 4)
    for ob in objects:
        ev = ob.evaluated_get(deps)
        me = ev.to_mesh()
        part = bmesh.new()
        part.from_mesh(me)
        ev.to_mesh_clear()
        mat = scale @ ob.matrix_world
        part.transform(mat)
        if mat.determinant() < 0:
            bmesh.ops.reverse_faces(part, faces=part.faces[:])
        tmp = bpy.data.meshes.new("_pc_tmp")
        part.to_mesh(tmp)
        part.free()
        bm.from_mesh(tmp)
        bpy.data.meshes.remove(tmp)
    before = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-4)
    return bm, before - len(bm.verts)


def arrays(bm):
    """(verts Nx3 float64, tris Mx3 int64) of a triangulated copy."""
    t = bm.copy()
    bmesh.ops.triangulate(t, faces=t.faces[:])
    t.verts.ensure_lookup_table()
    verts = np.array([v.co[:] for v in t.verts], dtype=np.float64).reshape(-1, 3)
    tris = np.array([[v.index for v in f.verts] for f in t.faces], dtype=np.int64).reshape(-1, 3)
    t.free()
    return verts, tris


# -------------------------------------------------------------------------------------- topology

def topology(bm):
    boundary = [e for e in bm.edges if e.is_boundary]
    multi = [e for e in bm.edges if len(e.link_faces) > 2]
    wire = [e for e in bm.edges if e.is_wire]
    flipped = [e for e in bm.edges if len(e.link_faces) == 2 and not e.is_contiguous]
    loose = [v for v in bm.verts if not v.link_edges]
    bow = [v for v in bm.verts if v.link_edges and not v.is_manifold
           and all(len(e.link_faces) == 2 for e in v.link_edges)]
    degenerate = [f for f in bm.faces if f.calc_area() < 1e-9]

    def where(items, mid):
        return [[round(c, 2) for c in mid(i)] for i in items[:8]]

    emid = lambda e: (e.verts[0].co + e.verts[1].co) / 2
    return {
        "open_edges": len(boundary), "open_edges_at": where(boundary, emid),
        "nonmanifold_edges": len(multi), "nonmanifold_edges_at": where(multi, emid),
        "flipped_normal_edges": len(flipped), "flipped_at": where(flipped, emid),
        "wire_edges": len(wire), "loose_verts": len(loose),
        "pinched_verts": len(bow), "pinched_at": where(bow, lambda v: v.co),
        "degenerate_faces": len(degenerate),
    }


def shells(verts, tris):
    """Label connected shells. Returns (label per triangle, count)."""
    parent = np.arange(len(verts))

    def find(a):
        root = a
        while parent[root] != root:
            root = parent[root]
        while parent[a] != root:
            parent[a], a = root, parent[a]
        return root

    for a, b, c in tris.tolist():
        ra, rb, rc = find(a), find(b), find(c)
        if rb != ra:
            parent[rb] = ra
        if rc != ra:
            parent[find(c)] = ra
    roots = np.array([find(int(a)) for a in tris[:, 0]])
    _, labels = np.unique(roots, return_inverse=True)
    return labels, int(labels.max()) + 1 if len(labels) else 0


def signed_volumes(verts, tris, labels, count):
    v0, v1, v2 = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    vol = np.einsum("ij,ij->i", v0, np.cross(v1, v2)) / 6.0
    return np.bincount(labels, weights=vol, minlength=count), vol


def make_bvh(verts, tris):
    return BVHTree.FromPolygons(verts.tolist(), tris.tolist(), all_triangles=True, epsilon=0.0)


def _inside(point, direction, verts, tris, skip):
    """Ray parity of `point` against every triangle not flagged in `skip`. Tests each triangle
    directly, so faces of two parts lying on top of each other are both counted."""
    d = np.asarray(direction, dtype=float)
    d /= np.linalg.norm(d)
    t = tris[~skip]
    v0 = verts[t[:, 0]]
    e1, e2 = verts[t[:, 1]] - v0, verts[t[:, 2]] - v0
    h = np.cross(d, e2)
    a = np.einsum("ij,ij->i", e1, h)
    ok = np.abs(a) > 1e-12
    f = 1.0 / np.where(ok, a, 1.0)
    sv = np.asarray(point, dtype=float) - v0
    u = f * np.einsum("ij,ij->i", sv, h)
    q = np.cross(sv, e1)
    v = f * (q @ d)
    dist = f * np.einsum("ij,ij->i", e2, q)
    hit = ok & (u >= 0.0) & (v >= 0.0) & (u + v <= 1.0) & (dist > 1e-9)
    return int(hit.sum()) % 2 == 1


def self_intersections(verts, tris, bvh, limit=8):
    pairs = bvh.overlap(bvh)
    bad, seen = [], 0
    tl = tris.tolist()
    for i, j in pairs:
        if i >= j:
            continue
        a, b = tl[i], tl[j]
        if a[0] in b or a[1] in b or a[2] in b:
            continue
        seen += 1
        if len(bad) < limit:
            bad.append([round(float(c), 2) for c in verts[a].mean(axis=0)])
    return seen, bad


# ------------------------------------------------------------------------------ orientation maths

def face_data(verts, tris):
    v0, v1, v2 = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    cr = np.cross(v1 - v0, v2 - v0)
    twice = np.linalg.norm(cr, axis=1)
    area = 0.5 * twice
    normal = cr / np.maximum(twice, 1e-30)[:, None]
    return normal, area, (v0 + v1 + v2) / 3.0


def _hull(points):
    pts = sorted(set((round(float(x), 4), round(float(y), 4)) for x, y in points))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _inside_hull(hull, p):
    if len(hull) < 3:
        return False
    for i in range(len(hull)):
        a, b = hull[i], hull[(i + 1) % len(hull)]
        if (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) < -1e-6:
            return False
    return True


def _seg_dist(points, a, b):
    """Distances from points (P,2) to segments a->b (S,2): returns (P,S) distances and nearest points."""
    ab = b - a
    ap = points[:, None, :] - a[None, :, :]
    t = np.einsum("psk,sk->ps", ap, ab) / np.maximum(np.einsum("sk,sk->s", ab, ab), 1e-12)[None, :]
    t = np.clip(t, 0.0, 1.0)
    near = a[None, :, :] + t[:, :, None] * ab[None, :, :]
    return np.linalg.norm(points[:, None, :] - near, axis=2), near


def _ceiling_islands(verts, tris, normal, area, ceil_idx, tol):
    """Group flat downward faces into islands; classify each as a bridge, a short ledge or neither."""
    nv = len(verts) + 1
    e = np.sort(np.stack([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]], axis=1), axis=2)
    keys = e[:, :, 0] * nv + e[:, :, 1]                     # (M,3) edge keys
    is_ceil = np.zeros(len(tris), dtype=bool)
    is_ceil[ceil_idx] = True
    # union ceiling faces across shared edges
    ck = keys[ceil_idx].ravel()
    cf = np.repeat(ceil_idx, 3)
    order = np.argsort(ck, kind="stable")
    ck, cf = ck[order], cf[order]
    parent = {int(f): int(f) for f in ceil_idx}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    same = ck[1:] == ck[:-1]
    for i in np.nonzero(same)[0].tolist():
        ra, rb = find(int(cf[i])), find(int(cf[i + 1]))
        if ra != rb:
            parent[rb] = ra
    groups = {}
    for f in ceil_idx.tolist():
        groups.setdefault(find(f), []).append(f)
    # neighbours across every ceiling edge
    ceil_keys = np.unique(ck)
    flat = keys.ravel()
    hit = np.isin(flat, ceil_keys)
    nb_face = np.repeat(np.arange(len(tris)), 3)[hit]
    nb_key = flat[hit]
    by_key = {}
    for k, f in zip(nb_key.tolist(), nb_face.tolist()):
        by_key.setdefault(k, []).append(f)

    out = []
    for faces in groups.values():
        fa = np.array(faces)
        z = float(verts[tris[fa]].reshape(-1, 3)[:, 2].mean())
        anchors = []
        for f in faces:
            for k in keys[f].tolist():
                others = [g for g in by_key.get(k, []) if g != f]
                if any(is_ceil[g] for g in others):
                    continue
                a, b = divmod(k, nv)
                for g in others:
                    third = [v for v in tris[g].tolist() if v != a and v != b]
                    if third and verts[third[0], 2] < z - tol:
                        anchors.append((a, b))
                        break
        pts = np.concatenate([verts[tris[fa]].reshape(-1, 3)[:, :2],
                              verts[tris[fa]].mean(axis=1)[:, :2]])
        if len(pts) > 1500:
            pts = pts[:: len(pts) // 1500 + 1]
        info = {"z": round(z, 2), "area": float(area[fa].sum()), "faces": fa,
                "at": [round(float(c), 2) for c in verts[tris[fa]].reshape(-1, 3).mean(axis=0)]}
        if not anchors:
            info.update(kind="floating", span=None, reach=None)
            out.append(info)
            continue
        if len(anchors) > 1500:
            anchors = anchors[:: len(anchors) // 1500 + 1]
        an = np.array(anchors)
        a2, b2 = verts[an[:, 0], :2], verts[an[:, 1], :2]
        dist, near = _seg_dist(pts, a2, b2)
        first = dist.argmin(axis=1)
        d1 = dist[np.arange(len(pts)), first]
        to1 = near[np.arange(len(pts)), first] - pts
        to_all = near - pts[:, None, :]
        dots = np.einsum("psk,pk->ps", to_all, to1)
        opposite = dots < -0.5 * dist * d1[:, None] - 1e-9          # more than 120 degrees away
        d2 = np.where(opposite, dist, np.inf).min(axis=1)
        on_anchor = d1 < 1e-6
        bridged = np.isfinite(d2) | on_anchor
        span = float(np.where(np.isfinite(d2), d1 + d2, 0.0).max())
        reach = float(np.where(bridged, 0.0, d1).max())
        info.update(kind="bridge" if reach < 1e-6 else "ledge", span=round(span, 2), reach=round(reach, 2))
        out.append(info)
    return out


def _backed(idx, normal, cen, bvh, reach=0.02):
    """Faces of `idx` that lie flat against a face of another shell (two parts touching)."""
    out = np.zeros(len(idx), bool)
    C, N = cen[idx].tolist(), normal[idx]
    for k, i in enumerate(idx.tolist()):
        for _co, n, j, _d in bvh.find_nearest_range(Vector(C[k]), reach):
            if j != i and n is not None and float(N[k] @ np.array(n)) < -0.9:
                out[k] = True
                break
    return out


def analyse(verts, tris, opts, bvh=None, detail=True, touching=False):
    """Everything that depends on which way is up. `opts` comes from options().
    touching=True when the mesh holds several shells that may rest on each other."""
    normal, area, cen = face_data(verts, tris)
    zmin, zmax = float(verts[:, 2].min()), float(verts[:, 2].max())
    tol = max(0.02, 0.25 * opts["layer"])
    tri_z = verts[tris][:, :, 2]
    on_bed = (normal[:, 2] < -0.95) & (tri_z.max(axis=1) < zmin + tol)
    contact = float(area[on_bed].sum())
    res = {"height": round(zmax - zmin, 3), "layers": int(math.ceil((zmax - zmin) / opts["layer"])),
           "bed_contact_mm2": round(contact, 2)}
    bed_pts = verts[np.unique(tris[on_bed])][:, :2] if on_bed.any() else np.zeros((0, 2))
    if len(bed_pts):
        ext = bed_pts.max(axis=0) - bed_pts.min(axis=0)
        res["bed_footprint_mm"] = [round(float(ext[0]), 2), round(float(ext[1]), 2)]
    else:
        res["bed_footprint_mm"] = [0.0, 0.0]

    masks = {"bed": on_bed, "support": np.zeros(len(tris), bool), "near": np.zeros(len(tris), bool),
             "bridge": np.zeros(len(tris), bool)}
    res.update(overhang_area_mm2=0.0, support_area_mm2=0.0, support_volume_mm3=0.0,
               support_on_model_pct=0.0, support_max_height=0.0, bridges=[], ledges=[],
               midair_starts=0, midair_at=[])
    if not opts["supports"]:
        return res, masks

    limit = math.sin(math.radians(opts["overhang"]))
    critical = (normal[:, 2] < -limit - 1e-3) & ~on_bed & (area > 1e-9)
    if touching and critical.any():
        bvh = bvh or make_bvh(verts, tris)
        ci = np.nonzero(critical)[0]
        critical[ci[_backed(ci, normal, cen, bvh)]] = False
    masks["near"] = (normal[:, 2] < -math.sin(math.radians(max(opts["overhang"] - 15.0, 0.0)))) \
        & ~critical & ~on_bed
    res["overhang_area_mm2"] = round(float(area[critical].sum()), 2)
    needs = critical.copy()
    ceil_idx = np.nonzero(critical & (normal[:, 2] < -0.985))[0]
    if len(ceil_idx):
        for isl in _ceiling_islands(verts, tris, normal, area, ceil_idx, tol):
            entry = {"z": isl["z"], "area_mm2": round(isl["area"], 2), "at": isl["at"]}
            if isl["kind"] == "bridge":
                entry["span_mm"] = isl["span"]
                ok = isl["span"] <= opts["bridge"]
                entry["supported"] = not ok
                res["bridges"].append(entry)
                if ok:
                    needs[isl["faces"]] = False
                    masks["bridge"][isl["faces"]] = True
            elif isl["kind"] == "ledge":
                entry["reach_mm"] = isl["reach"]
                ok = isl["reach"] <= opts["cantilever"]
                entry["supported"] = not ok
                res["ledges"].append(entry)
                if ok:
                    needs[isl["faces"]] = False
        res["bridges"].sort(key=lambda b: -b["span_mm"])
        res["ledges"].sort(key=lambda b: -b["reach_mm"])
        res["bridges"], res["ledges"] = res["bridges"][:12], res["ledges"][:12]
    masks["support"] = needs
    res["support_area_mm2"] = round(float(area[needs].sum()), 2)

    idx = np.nonzero(needs)[0]
    if len(idx):
        bvh = bvh or make_bvh(verts, tris)
        if len(idx) > 40000:                       # sample, then scale back up
            step = len(idx) // 40000 + 1
            weight = float(area[idx].sum()) / float(area[idx[::step]].sum())
            idx = idx[::step]
        else:
            weight = 1.0
        down = Vector((0.0, 0.0, -1.0))
        vol = on_model = hmax = 0.0
        for i in idx.tolist():
            c = cen[i]
            loc, _n, _i, dist = bvh.ray_cast(Vector((c[0], c[1], c[2] - 1e-3)), down)
            proj = area[i] * -normal[i, 2]
            if loc is None:
                h = c[2] - zmin
            else:
                h = dist
                on_model += proj
            vol += proj * h
            hmax = max(hmax, h)
        total = float((area[idx] * -normal[idx, 2]).sum())
        res["support_volume_mm3"] = round(vol * weight, 1)
        res["support_on_model_pct"] = round(100.0 * on_model / max(total, 1e-9), 1)
        res["support_max_height"] = round(hmax, 2)

    if detail:
        count, at = _midair_starts(verts, tris, zmin, tol, bvh if touching else None)
        res["midair_starts"], res["midair_at"] = count, at
    return res, masks


def _midair_starts(verts, tris, zmin, tol, bvh=None):
    """Places where material starts with nothing under it: local low points above the bed.
    With a bvh, low points resting on another shell are not counted."""
    e = np.unique(np.sort(np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]]), axis=1), axis=0)
    z = verts[:, 2]
    eps = 1e-4
    dz = z[e[:, 1]] - z[e[:, 0]]
    flat = np.abs(dz) < eps
    parent = np.arange(len(verts))

    def find(a):
        root = a
        while parent[root] != root:
            root = parent[root]
        while parent[a] != root:
            parent[a], a = root, parent[a]
        return root

    for a, b in e[flat].tolist():
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    root = np.array([find(i) for i in range(len(verts))])
    has_lower = np.zeros(len(verts), bool)
    up = e[~flat]
    dzu = dz[~flat]
    higher = np.where(dzu > 0, up[:, 1], up[:, 0])          # the higher end has a lower neighbour
    has_lower[root[higher]] = True
    used = np.zeros(len(verts), bool)
    used[np.unique(tris)] = True
    # material starts at a low point only where the surface around it faces down (a pit's floor faces up)
    normal, area, _cen = face_data(verts, tris)
    facing = np.zeros(len(verts))
    for k in range(3):
        np.add.at(facing, root[tris[:, k]], normal[:, 2] * area)
    cand = used & (root == np.arange(len(verts))) & ~has_lower & (z > zmin + tol) & (facing < 0.0)
    at = []
    count = 0
    rt = root[tris]
    whole = np.nonzero((rt[:, 0] == rt[:, 1]) & (rt[:, 1] == rt[:, 2]))[0]     # faces lying in one region
    face_of = dict(zip(rt[whole, 0].tolist(), whole.tolist()))
    for r in np.nonzero(cand)[0].tolist():
        p = verts[tris[face_of[r]]].mean(axis=0) if r in face_of else verts[root == r].mean(axis=0)
        if bvh is not None and any(n is not None and n.z > 0.9
                                   for _co, n, _j, _d in bvh.find_nearest_range(Vector(p), 0.02)):
            continue
        count += 1
        if len(at) < 8:
            at.append([round(float(c), 2) for c in p])
    return count, at


def wall_thickness(verts, tris, bvh, opts, cap=120000):
    """Thickness along the inward normal at sample points. Returns (report, per-face minimum)."""
    normal, area, _cen = face_data(verts, tris)
    total = float(area.sum())
    spacing = max(opts["min_wall"] * 2.0, math.sqrt(total / cap))
    per = np.clip(np.ceil(area / spacing ** 2), 1, 48).astype(int)
    if per.sum() > cap * 1.5:
        per = np.maximum(1, (per * (cap * 1.5 / per.sum())).astype(int))
    per[area < 1e-9] = 0
    face = np.repeat(np.arange(len(tris)), per)
    k = np.arange(len(face)) - np.repeat(np.cumsum(per) - per, per)
    # low-discrepancy points in each triangle; the first one is the centroid
    u = (0.5 + k * 0.7548776662466927) % 1.0
    v = (0.5 + k * 0.5698402909980532) % 1.0
    flip = u + v > 1.0
    u, v = np.where(flip, 1.0 - u, u), np.where(flip, 1.0 - v, v)
    first = k == 0
    u, v = np.where(first, 1 / 3, u), np.where(first, 1 / 3, v)
    v0, v1, v2 = verts[tris[face, 0]], verts[tris[face, 1]], verts[tris[face, 2]]
    pts = v0 + (v1 - v0) * u[:, None] + (v2 - v0) * v[:, None]
    nrm = normal[face]
    weight = area[face] / np.maximum(per[face], 1)
    thick = np.full(len(face), np.inf)
    gap = np.full(len(face), np.inf)
    reach = max(opts["gap"] * 4.0, 1.0)
    P, N = pts.tolist(), nrm.tolist()
    for i in range(len(face)):
        n = Vector(N[i])
        p = Vector(P[i])
        loc, hn, _idx, dist = bvh.ray_cast(p - n * 1e-3, -n)
        if loc is not None and hn.dot(n) < 0.0:
            thick[i] = dist + 1e-3
        loc, hn, _idx, dist = bvh.ray_cast(p + n * 1e-3, n, reach)       # the surface facing this one
        if loc is not None and hn.dot(n) < -0.5:
            gap[i] = dist + 1e-3
    ok = np.isfinite(thick)
    per_face = np.full(len(tris), np.inf)
    np.minimum.at(per_face, face, thick)
    rep = {"samples": int(len(face)), "min_wall_mm": opts["min_wall"], "hard_wall_mm": opts["hard_wall"]}
    narrow = gap < opts["gap"] - 1e-3
    gaps = {"limit_mm": opts["gap"], "min": round(float(gap.min()), 3) if np.isfinite(gap).any() else None,
            "narrow_area_mm2": round(float(weight[narrow].sum()), 2), "at": []}
    for i in np.argsort(gap)[:200].tolist():
        if not narrow[i] or len(gaps["at"]) >= 6:
            break
        q = pts[i]
        if all(np.linalg.norm(q - np.array(w[:3])) > 5.0 for w in gaps["at"]):
            gaps["at"].append([round(float(q[0]), 2), round(float(q[1]), 2), round(float(q[2]), 2),
                               round(float(gap[i]), 2)])
    rep["gaps"] = gaps
    if not ok.any():
        rep.update(min=None, p01=None, thin_area_mm2=0.0, thin_pct=0.0, too_thin_area_mm2=0.0, thin_at=[])
        return rep, per_face
    order = np.argsort(thick[ok])
    cum = np.cumsum(weight[ok][order])
    p01 = float(thick[ok][order][np.searchsorted(cum, 0.01 * cum[-1])])
    # FDM builds thickness in Z out of layers, so a floor or roof may be thinner than a wall
    upright = (np.abs(nrm[:, 2]) > 0.7) & (opts["process"] == "fdm")
    thin = ok & (thick < np.where(upright, min(3.0 * opts["layer"], opts["min_wall"]), opts["min_wall"]) - 1e-3)
    hard = ok & (thick < np.where(upright, min(opts["layer"], opts["hard_wall"]), opts["hard_wall"]) - 1e-3)
    worst = np.argsort(thick)[:400]
    at = []
    for i in worst.tolist():
        if not thin[i]:
            continue
        p = pts[i]
        if all(np.linalg.norm(p - np.array(q[:3])) > 5.0 for q in at):
            at.append([round(float(p[0]), 2), round(float(p[1]), 2), round(float(p[2]), 2),
                       round(float(thick[i]), 2)])
        if len(at) >= 8:
            break
    rep.update(min=round(float(thick[ok].min()), 3), p01=round(p01, 3),
               thin_area_mm2=round(float(weight[thin].sum()), 2),
               thin_pct=round(100.0 * float(weight[thin].sum()) / max(total, 1e-9), 2),
               too_thin_area_mm2=round(float(weight[hard].sum()), 2), thin_at=at)
    return rep, per_face


# --------------------------------------------------------------------------------------- options

def options(process=None, nozzle=None, layer=None, min_wall=None, overhang=None, bridge=None,
            build=None, material=None, infill=15.0, walls=2, gap=None, **_ignored):
    """Settings for a check. Anything left as None comes from the saved printer profile
    (printer_profile.py), then from the process and material defaults."""
    prof = printer_profile.load()
    process = process or prof.get("process") or "fdm"
    if process not in PROCESS:
        raise ValueError(f"process must be one of {', '.join(PROCESS)}")
    p = dict(PROCESS[process])
    same = prof.get("process", process) == process          # profile numbers only fit its own process
    o = {"process": process, "supports": p["supports"],
         "printer": prof.get("printer") if same else None,
         "colours": prof.get("colors") if same else None,
         "colour_system": (prof.get("color_system") or "") if same else ""}
    fallback = "resin" if process == "resin" else "pa12" if process == "sls" else "pla"
    wanted = (material or (same and prof.get("default_material")) or fallback).lower()
    o["material_name"] = wanted
    o["material"] = wanted if wanted in MATERIAL else next((m for m in MATERIAL if wanted.startswith(m)),
                                                           fallback)
    o["nozzle"] = float(nozzle or (same and prof.get("nozzle")) or 0.4)
    o["layer"] = float(layer or (same and prof.get("layer")) or p["layer"])
    o["line_width"] = 1.125 * o["nozzle"]
    o["hard_wall"] = p["hard_wall"] if p["hard_wall"] is not None else o["nozzle"]
    o["min_wall"] = float(min_wall) if min_wall else (p["min_wall"] if p["min_wall"] is not None
                                                      else 2.0 * o["nozzle"])
    o["hard_wall"] = min(o["hard_wall"], o["min_wall"])
    limits = (p["bridge"], p["overhang"])
    if process == "fdm":
        limits = FDM_LIMITS.get(o["material"], limits)
    o["overhang"] = float(overhang) if overhang is not None else limits[1]
    o["bridge"] = float(bridge) if bridge is not None else limits[0]
    o["cantilever"] = p["cantilever"] if p["cantilever"] is not None else 2.0 * o["nozzle"]
    o["gap"] = float(gap) if gap is not None else GAP[process]
    o["build"] = [float(b) for b in (build or (same and prof.get("build")) or (256.0, 256.0, 256.0))]
    o["infill"] = float(infill)
    o["walls"] = int(walls)
    return o


def estimate(volume, area, orient, opts):
    """Rough material, time and cost, for comparing two designs or orientations. Slice for real numbers."""
    density, price = MATERIAL[opts["material"]]
    if opts["process"] == "fdm":
        shell = min(volume, area * opts["walls"] * opts["line_width"])
        part = shell + (volume - shell) * opts["infill"] / 100.0
        support = orient["support_volume_mm3"] * 0.12
        flow = FDM_FLOW.get(opts["material"], 6.0) * min(2.0, opts["line_width"] * opts["layer"] / 0.09)
        if any(s in (opts.get("printer") or "").lower() for s in SLOW_PRINTERS):
            flow *= 0.5
        seconds = 180.0 + (part + support) / max(flow, 1e-6) + orient["layers"] * 2.0
    elif opts["process"] == "resin":
        part, support = volume, orient["support_volume_mm3"] * 0.03
        seconds = orient["layers"] * 7.0                               # exposure and lift per layer
    else:
        part, support = volume, 0.0
        seconds = orient["layers"] * 12.0
    grams = (part + support) * density / 1000.0
    out = {"material": opts["material_name"], "part_volume_cm3": round(volume / 1000.0, 2),
           "used_material_cm3": round((part + support) / 1000.0, 2),
           "support_material_cm3": round(support / 1000.0, 2),
           "mass_g": round(grams, 1), "cost": round(grams * price / 1000.0, 2),
           "time_min_rough": round(seconds / 60.0), "layers": orient["layers"]}
    if opts["process"] == "fdm":
        out["filament_m"] = round((part + support) / (math.pi * 0.875 ** 2) / 1000.0, 2)
    return out


# ----------------------------------------------------------------------------------------- report

def collect(objs, mm):
    """Gather each object on its own (so parts that touch stay separate solids).
    Returns (verts, tris, part index per triangle, per-part info, welded count)."""
    vs, ts, owner, parts, welded, offset = [], [], [], [], 0, 0
    for i, ob in enumerate(objs):
        bm, w = gather([ob], mm)
        topo = topology(bm)
        v, t = arrays(bm)
        bm.free()
        welded += w
        parts.append({"name": ob.name, "triangles": int(len(t)), "topology": topo,
                      "colour": ob.get("print_colour"), "filament": ob.get("print_filament")})
        if len(t):
            vs.append(v)
            ts.append(t + offset)
            owner.append(np.full(len(t), i))
            offset += len(v)
    if not ts:
        return np.zeros((0, 3)), np.zeros((0, 3), np.int64), np.zeros(0, int), parts, welded
    return np.concatenate(vs), np.concatenate(ts), np.concatenate(owner), parts, welded


def run(path=None, objects=None, unit="auto", intersections=True, keep=False, **kw):
    """Check a file or scene objects. Returns the report dict. Several objects are treated as the
    parts of one print (one per colour or material): each must be a closed solid on its own, and
    they may touch. With keep=True the report carries "_data" for the review renderer."""
    opts = options(**kw)
    if path:
        objs, mm = load_model(path, unit)
    else:
        objs = [bpy.data.objects[o] if isinstance(o, str) else o for o in objects] if objects \
            else scene_objects()
        mm = scene_mm_per_unit(unit)
    if not objs:
        return {"ok": False, "pass": False, "errors": ["no mesh objects to check"], "warnings": []}
    verts, tris, owner, parts, welded = collect(objs, mm)
    if not len(tris):
        return {"ok": False, "pass": False, "errors": ["the mesh has no faces"], "warnings": []}
    multi = len(parts) > 1
    errors, warnings, advice = [], [], []
    size = verts.max(axis=0) - verts.min(axis=0)
    rep = {"ok": True, "process": opts["process"], "printer": opts["printer"],
           "objects": [o.name for o in objs], "mm_per_unit": mm, "triangles": int(len(tris)),
           "size_mm": [round(float(s), 3) for s in size], "welded_verts": int(welded)}

    # --- topology, per part
    topo = {k: 0 for k in ("open_edges", "nonmanifold_edges", "flipped_normal_edges", "wire_edges",
                           "loose_verts", "pinched_verts", "degenerate_faces")}
    for part in parts:
        t = part["topology"]
        who = f"{part['name']}: " if multi else ""
        for k in topo:
            topo[k] += t[k]
        if t["open_edges"]:
            errors.append(f"{who}not watertight: {t['open_edges']} open edges, e.g. at {t['open_edges_at'][:3]}")
        if t["nonmanifold_edges"]:
            errors.append(f"{who}{t['nonmanifold_edges']} edges shared by more than two faces "
                          f"(internal faces or touching shells), e.g. at {t['nonmanifold_edges_at'][:3]}")
        if t["flipped_normal_edges"]:
            errors.append(f"{who}inconsistent face normals along {t['flipped_normal_edges']} edges")
        if t["wire_edges"] or t["loose_verts"]:
            warnings.append(f"{who}{t['wire_edges']} loose edges and {t['loose_verts']} loose vertices")
        if t["pinched_verts"]:
            warnings.append(f"{who}{t['pinched_verts']} vertices where two surfaces meet at a single point "
                            f"(zero-thickness joint), e.g. at {t['pinched_at'][:3]}")
        if t["degenerate_faces"] > max(10, 0.01 * part["triangles"]):
            advice.append(f"{who}{t['degenerate_faces']} zero-area faces; harmless in small numbers, "
                          f"but this many suggests a damaged mesh: remesh or clean it")
    rep["topology"] = topo
    if welded > 0.02 * len(verts):
        advice.append(f"{welded} duplicate vertices were welded for this check; weld them in the source "
                      f"(merge by distance) so the exported file is one connected surface")
    closed = not (topo["open_edges"] or topo["nonmanifold_edges"] or topo["flipped_normal_edges"])

    labels, nshell = shells(verts, tris)
    svol, tri_vol = signed_volumes(verts, tris, labels, nshell)
    bvh = make_bvh(verts, tris)
    rep["shells"] = nshell
    cavities, inverted, nested = [], 0, 0
    if closed and 1 < nshell <= 400 and nshell * len(tris) <= 30000000:
        fn, fa, fc = face_data(verts, tris)
        for s in range(nshell):
            own = labels == s
            big = np.nonzero(own)[0][np.argmax(fa[own])]
            p = fc[big] - fn[big] * 1e-3                  # just behind the shell's largest face
            inside = _inside(p, (0.5377, 0.2913, 0.7911), verts, tris, own)
            if svol[s] < 0 and inside:
                cavities.append(round(float(-svol[s]), 1))
            elif svol[s] < 0:
                inverted += 1
            elif inside:
                nested += 1
    elif closed and nshell == 1 and svol[0] < 0:
        inverted = 1
    rep["cavities"] = {"count": len(cavities), "volume_mm3": round(sum(cavities), 1)}
    if inverted:
        errors.append(f"{inverted} shell(s) are inside out (normals point inward)")
    if nested and multi:
        advice.append(f"{nested} part(s) overlap the volume of another part. Slicers resolve overlaps by "
                      f"part order; cut a pocket for each inlaid part so every volume has one owner")
    elif nested:
        warnings.append(f"{nested} shell(s) sit inside another solid; slicers may treat them as holes. "
                        f"Union the parts into one shell")
    volume = float(svol.sum()) if closed else float(abs(tri_vol.sum()))
    rep["volume_mm3"] = round(volume, 2)
    area_total = float(face_data(verts, tris)[1].sum())
    rep["surface_mm2"] = round(area_total, 2)
    if multi:
        pvol = np.bincount(owner, weights=tri_vol, minlength=len(parts))
        for i, part in enumerate(parts):
            part["volume_mm3"] = round(float(abs(pvol[i])), 2)
            del part["topology"]
        rep["parts"] = parts

    if intersections and len(tris) <= 600000:
        total, where = 0, []
        for i in range(len(parts)):
            sel = np.nonzero(owner == i)[0]
            if not len(sel):
                continue
            n, at = self_intersections(verts, tris[sel], make_bvh(verts, tris[sel]) if multi else bvh)
            total += n
            where += at
        rep["self_intersections"] = total
        if total and nshell > len(parts):
            warnings.append(f"{total} pairs of faces cross or touch without sharing an edge, e.g. at "
                            f"{where[:3]}. Union overlapping pieces into one shell before export")
        elif total:
            advice.append(f"{total} place(s) where faces touch without sharing an edge, e.g. at {where[:3]} "
                          f"(a corner resting on a neighbouring face). Slicers cope; nothing to union")
    else:
        rep["self_intersections"] = None

    # --- size
    b = opts["build"]
    fits = (size[0] <= b[0] and size[1] <= b[1] or size[0] <= b[1] and size[1] <= b[0]) and size[2] <= b[2]
    rep["build_mm"], rep["fits_build"] = b, bool(fits)
    if not fits:
        s3, b3 = sorted(size.tolist()), sorted(b)
        if all(s <= bb for s, bb in zip(s3, b3)):
            errors.append(f"{rep['size_mm']} mm does not fit the {b} mm build volume this way up, "
                          f"but would in another orientation")
        else:
            errors.append(f"{rep['size_mm']} mm does not fit the {b} mm build volume: scale it or split it "
                          f"into keyed parts")
    if size.max() < 2.0:
        warnings.append(f"largest dimension is {size.max():.3f} mm: probably the wrong unit (use --unit m)")
    elif size.max() > 2000.0:
        warnings.append(f"largest dimension is {size.max():.0f} mm: either the wrong unit (try --unit mm) "
                        f"or a life-size model that must be scaled down to print")
    if len(tris) > 1500000:
        advice.append(f"{len(tris)} triangles: decimate to under about 1M; slicers slow down and the "
                      f"printer cannot resolve the difference")

    # --- orientation
    orient, masks = analyse(verts, tris, opts, bvh, touching=nshell > 1)
    rep["orientation"] = orient
    if opts["supports"]:
        if orient["support_area_mm2"] > 1.0:
            warnings.append(
                f"{orient['support_area_mm2']:.0f} mm2 of overhang steeper than {opts['overhang']:.0f} deg "
                f"needs support (about {orient['support_volume_mm3'] / 1000.0:.1f} cm3 of supported space, "
                f"{orient['support_on_model_pct']:.0f}% of it resting on the model)")
        long_b = [x for x in orient["bridges"] if x["supported"]]
        if long_b:
            warnings.append(f"{len(long_b)} flat span(s) longer than {opts['bridge']:.0f} mm, longest "
                            f"{long_b[0]['span_mm']} mm at {long_b[0]['at']}")
        if orient["midair_starts"]:
            warnings.append(f"{orient['midair_starts']} place(s) start in mid-air (a low point with nothing "
                            f"under it), e.g. at {orient['midair_at'][:3]}")
        if orient["bed_contact_mm2"] < 1.0:
            warnings.append("nothing flat touches the bed: add a flat base, cut the model flat, or turn it")
        else:
            fp = orient["bed_footprint_mm"]
            if orient["height"] > 5.0 * max(min(fp), 1e-6) and opts["process"] == "fdm":
                warnings.append(f"tall and narrow: {orient['height']:.0f} mm high on a {fp[0]:.0f} x "
                                f"{fp[1]:.0f} mm footprint. Add a brim, widen the base or lay it down")
    elif rep["cavities"]["count"]:
        warnings.append(f"{rep['cavities']['count']} sealed cavity(ies) will trap powder: add two escape "
                        f"holes of 4 mm or more to each")
    if rep["cavities"]["count"] and opts["process"] == "resin":
        errors.append(f"{rep['cavities']['count']} sealed cavity(ies) will trap liquid resin: add two drain "
                      f"holes of 3.5 mm or more near the build plate")

    # --- stability: is the centre of mass over the footprint?
    if closed and volume > 1e-6:
        com = (tri_vol[:, None] * (verts[tris[:, 0]] + verts[tris[:, 1]] + verts[tris[:, 2]]) / 4.0).sum(0) / volume
        rep["centre_of_mass"] = [round(float(c), 2) for c in com]
        if masks["bed"].any():
            hull = _hull(verts[np.unique(tris[masks["bed"]])][:, :2])
            over = _inside_hull(hull, (float(com[0]), float(com[1])))
            rep["stands_unaided"] = bool(over)
            if not over and opts["supports"]:
                advice.append("the centre of mass is outside the bed footprint: the part leans on bed "
                              "adhesion while printing and will not stand on this face afterwards")

    # --- walls
    walls, per_face = wall_thickness(verts, tris, bvh, opts)
    rep["walls"] = walls
    if walls["min"] is not None:
        floor = max(1.0, 0.001 * area_total)
        if walls["too_thin_area_mm2"] > floor:
            errors.append(f"{walls['too_thin_area_mm2']:.0f} mm2 of wall is thinner than "
                          f"{opts['hard_wall']} mm and will not print (thinnest {walls['min']} mm, "
                          f"e.g. at {[a[:3] for a in walls['thin_at'][:3]]})")
        elif walls["thin_area_mm2"] > max(2.0, 0.002 * area_total):
            warnings.append(f"{walls['thin_area_mm2']:.0f} mm2 of wall is thinner than {opts['min_wall']} mm "
                            f"(thinnest {walls['min']} mm, e.g. at {[a[:3] for a in walls['thin_at'][:3]]})")
        elif walls["thin_at"]:
            advice.append(f"thinnest spot {walls['thin_at'][0][3]} mm at {walls['thin_at'][0][:3]} covers under "
                          f"{max(2.0, 0.002 * area_total):.0f} mm2: a sharp edge or tip. Blunt it if it must be "
                          f"strong or exact")
    gaps = walls.pop("gaps")
    rep["gaps"] = gaps
    if gaps["narrow_area_mm2"] > 1.0:
        warnings.append(f"{gaps['narrow_area_mm2']:.0f} mm2 of facing surfaces are closer than "
                        f"{opts['gap']} mm and will fuse (closest {gaps['min']} mm, e.g. at "
                        f"{[a[:3] for a in gaps['at'][:3]]}). Open the gap or join the parts")

    # --- colours: which layers hold more than one
    if multi and len({p.get("colour") for p in parts if p.get("colour")}) > 1:
        keys = [(p.get("colour") or p["name"]) for p in parts]
        zlo, zhi = np.zeros(len(parts)), np.zeros(len(parts))
        for i in range(len(parts)):
            if (owner == i).any():
                zs = verts[np.unique(tris[owner == i])][:, 2]
                zlo[i], zhi[i] = zs.min(), zs.max()
        mids = float(verts[:, 2].min()) + (np.arange(orient["layers"]) + 0.5) * opts["layer"]
        count = np.zeros(len(mids), int)
        for key in set(keys):
            on = np.zeros(len(mids), bool)
            for i, k in enumerate(keys):
                if k == key:
                    on |= (mids > zlo[i]) & (mids < zhi[i])
            count += on
        mixed = int((count > 1).sum())
        changes = int(np.maximum(count - 1, 0).sum())
        rep["colours"] = {"count": len(set(keys)), "layers_with_several": mixed,
                          "filament_changes": changes}
        have = opts.get("colours")
        if have and len(set(keys)) > int(have):
            warnings.append(f"the model uses {len(set(keys))} colours but the printer profile has {have}")
        if mixed and "manual" in opts.get("colour_system", "").lower():
            warnings.append(f"{mixed} layers hold more than one colour, but colour changes on this printer are "
                            f"manual swaps at a layer: arrange the colours in bands by height")
        elif mixed > 0.25 * orient["layers"] and mixed > 10:
            advice.append(f"{mixed} of {orient['layers']} layers hold more than one colour (about {changes} "
                          f"filament changes). On a single-nozzle changer each change purges and takes a "
                          f"minute or two: keep colour to a few layers, e.g. a 0.6 mm inlay on the top face")

    rep["estimate"] = estimate(volume, area_total, orient, opts)
    rep["settings"] = {k: opts[k] for k in ("nozzle", "layer", "min_wall", "overhang", "bridge", "gap",
                                            "infill", "walls")}
    rep["errors"], rep["warnings"], rep["advice"] = errors, warnings, advice
    rep["pass"] = not errors
    if keep:
        rep["_data"] = {"verts": verts, "tris": tris, "masks": masks, "thickness": per_face, "opts": opts,
                        "owner": owner, "colours": [p.get("colour") for p in parts]}
    return rep


def summary(rep):
    if not rep.get("ok"):
        return "CHECK FAILED: " + "; ".join(rep.get("errors", []))
    o, e = rep["orientation"], rep["estimate"]
    lines = [
        f"{'PASS' if rep['pass'] else 'FAIL'}  {rep['process']}"
        f"{' on ' + rep['printer'] if rep.get('printer') else ''}  "
        f"{rep['size_mm'][0]:g} x {rep['size_mm'][1]:g} x {rep['size_mm'][2]:g} mm  "
        f"{rep['triangles']} triangles  {len(rep['objects'])} part(s)  {rep['shells']} shell(s)  "
        f"{rep['volume_mm3'] / 1000.0:.2f} cm3",
        f"  bed contact {o['bed_contact_mm2']:.0f} mm2   support needed on {o['support_area_mm2']:.0f} mm2 "
        f"({o['support_volume_mm3'] / 1000.0:.1f} cm3)   bridges {len(o['bridges'])}   "
        f"mid-air starts {o['midair_starts']}",
        f"  thinnest wall {rep['walls']['min']} mm   rough estimate {e['mass_g']} g {e['material']}, "
        f"{e['time_min_rough']} min, {e['layers']} layers",
    ]
    if rep.get("colours"):
        c = rep["colours"]
        lines.append(f"  {c['count']} colours   {c['layers_with_several']} layers hold more than one   "
                     f"about {c['filament_changes']} filament changes")
    lines += [f"  ERROR    {x}" for x in rep["errors"]]
    lines += [f"  WARNING  {x}" for x in rep["warnings"]]
    lines += [f"  ADVICE   {x}" for x in rep["advice"]]
    return "\n".join(lines)


def to_json(obj):
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return str(obj)


def add_arguments(p):
    p.add_argument("model", nargs="?")
    p.add_argument("--objects", nargs="+")
    p.add_argument("--process", choices=list(PROCESS))
    p.add_argument("--nozzle", type=float)
    p.add_argument("--layer", type=float)
    p.add_argument("--min-wall", type=float, dest="min_wall")
    p.add_argument("--overhang", type=float)
    p.add_argument("--bridge", type=float)
    p.add_argument("--gap", type=float)
    p.add_argument("--build")
    p.add_argument("--material")
    p.add_argument("--infill", type=float, default=15.0)
    p.add_argument("--walls", type=int, default=2)
    p.add_argument("--unit", default="auto", choices=["auto"] + list(UNIT_MM))
    p.add_argument("--json")


def cli_argv():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def kwargs_from(a):
    kw = {k: getattr(a, k) for k in ("process", "nozzle", "layer", "min_wall", "overhang", "bridge", "gap",
                                     "material", "infill", "walls", "unit")}
    kw["build"] = [float(x) for x in a.build.replace("x", ",").split(",")] if a.build else None
    return kw


def main():
    p = argparse.ArgumentParser(prog="print_check.py", description=__doc__.split("\n")[0])
    add_arguments(p)
    p.add_argument("--no-intersections", action="store_true")
    a = p.parse_args(cli_argv())
    try:
        rep = run(path=a.model, objects=a.objects, intersections=not a.no_intersections, **kwargs_from(a))
    except Exception as exc:  # report, do not dump a traceback at the caller
        rep = {"ok": False, "pass": False, "errors": [f"{type(exc).__name__}: {exc}"], "warnings": []}
    print(summary(rep))
    text = json.dumps(rep, default=to_json, separators=(",", ":"))
    print(MARK + text, flush=True)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(rep, f, default=to_json, indent=1)
    sys.exit(0 if rep.get("pass") else 1)


if __name__ == "__main__":
    main()

"""printkit: build printable solids in Blender from a script. One Blender unit is one millimetre.

  import sys; sys.path.insert(0, "<this skill>/scripts"); import printkit as pk

Every builder returns a closed, outward-facing mesh object. `union` and `cut` use Blender's exact
boolean solver, so results stay watertight. Positions (`at`) are millimetres.

Scene       new_scene()  save_blend(path)
Solids      box  cylinder  sphere  prism  lathe  text
Outlines    rounded_rect  slot  polygon          (lists of (x, y) for prism)
Cutters     teardrop (horizontal hole that prints without support)  countersink  counterbore  hex_pocket
Combine     union  cut  common  copy
Place       move  rotate  to_bed
Edges       chamfer (segments > 1 gives a round)
Numbers     segments_for  FIT  SCREW  hole_d
Colour      colour (one object per colour or material; export keeps them as separate parts)
Finish      clean  check  export
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Clearance to add between two printed parts, per side, for a well-tuned 0.4 mm FDM printer.
# Print the gauge in references/functional-parts.md once per printer and material, then adjust.
FIT = {"press": 0.05, "snug": 0.10, "slide": 0.20, "loose": 0.35, "print_in_place": 0.30}

# Metric screws: thread-forming hole (screw cuts its own thread in plastic), close clearance hole,
# socket-head diameter and height, hex nut across flats and height, heat-set insert hole (typical
# brass insert; check the maker's sheet). Millimetres, nominal: add HOLE_COMP for printed holes.
SCREW = {
    "M2":   dict(tap=1.6, clear=2.4, head_d=3.8, head_h=2.0, nut_af=4.0, nut_h=1.6, insert=3.2),
    "M2.5": dict(tap=2.1, clear=2.9, head_d=4.5, head_h=2.5, nut_af=5.0, nut_h=2.0, insert=4.0),
    "M3":   dict(tap=2.5, clear=3.4, head_d=5.5, head_h=3.0, nut_af=5.5, nut_h=2.4, insert=4.0),
    "M4":   dict(tap=3.3, clear=4.5, head_d=7.0, head_h=4.0, nut_af=7.0, nut_h=3.2, insert=5.6),
    "M5":   dict(tap=4.2, clear=5.5, head_d=8.5, head_h=5.0, nut_af=8.0, nut_h=4.7, insert=6.4),
    "M6":   dict(tap=5.0, clear=6.6, head_d=10.0, head_h=6.0, nut_af=10.0, nut_h=5.2, insert=8.0),
    "M8":   dict(tap=6.8, clear=9.0, head_d=13.0, head_h=8.0, nut_af=13.0, nut_h=6.8, insert=9.6),
}
HOLE_COMP = 0.2   # FDM holes print small: add this to a nominal diameter (vertical holes, 0.4 nozzle)


def hole_d(nominal, comp=HOLE_COMP):
    """Diameter to model so a printed hole measures `nominal`."""
    return nominal + comp


def segments_for(d, chord=0.01, lo=24, hi=256):
    """Facets round a circle of diameter d so the flats deviate at most `chord` mm. Multiple of 4."""
    r = max(d / 2.0, 1e-6)
    n = math.pi / math.acos(max(-1.0, min(1.0, 1.0 - chord / r))) if chord < r else lo
    return int(min(hi, max(lo, 4 * math.ceil(n / 4.0))))


# ----------------------------------------------------------------------------------------- scene

def new_scene():
    """Empty scene in millimetres."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    us = bpy.context.scene.unit_settings
    us.system, us.scale_length, us.length_unit = "METRIC", 0.001, "MILLIMETERS"


def save_blend(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(path))


def _outward(bm):
    """Make every separate shell face outward (positive volume)."""
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    seen = set()
    for start in bm.faces:
        if start in seen:
            continue
        island, i = [start], 0
        seen.add(start)
        while i < len(island):
            for e in island[i].edges:
                for g in e.link_faces:
                    if g not in seen:
                        seen.add(g)
                        island.append(g)
            i += 1
        vol = 0.0
        for f in island:
            v = [x.co for x in f.verts]
            for k in range(1, len(v) - 1):
                vol += v[0].dot(v[k].cross(v[k + 1]))
        if vol < 0.0:
            bmesh.ops.reverse_faces(bm, faces=island)


def _object(name, bm):
    _outward(bm)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _edit(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    return bm


def _store(ob, bm):
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()


def _axis_matrix(axis):
    """Lay a shape built along +Z along +X or +Y instead. Its outline (u, v) lands on (Y, Z) for
    "x" and on (X, Z) for "y", so v is always up."""
    return {"z": Matrix.Identity(4),
            "x": Matrix(((0, 0, 1, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1))),
            "y": Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))}[axis.lower()]


# ---------------------------------------------------------------------------------------- solids

def box(sx, sy, sz, at=(0, 0, 0), name="box"):
    """Box centred in X and Y on `at`, standing on at.z."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts[:])
    bmesh.ops.translate(bm, vec=(at[0], at[1], at[2] + sz / 2.0), verts=bm.verts[:])
    return _object(name, bm)


def cylinder(d, h, at=(0, 0, 0), d_top=None, axis="z", segments=None, name="cylinder"):
    """Cylinder (or cone frustum with d_top) starting at `at` and extending h along +axis."""
    d2 = d if d_top is None else d_top
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments or segments_for(max(d, d2)),
                          radius1=d / 2.0, radius2=d2 / 2.0, depth=h)
    bmesh.ops.translate(bm, vec=(0, 0, h / 2.0), verts=bm.verts[:])
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6)
    bm.transform(Matrix.Translation(at) @ _axis_matrix(axis))
    return _object(name, bm)


def sphere(d, at=(0, 0, 0), segments=None, name="sphere"):
    """Sphere centred on `at`."""
    n = segments or segments_for(d)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=n, v_segments=max(8, n // 2), radius=d / 2.0)
    bmesh.ops.translate(bm, vec=at, verts=bm.verts[:])
    return _object(name, bm)


def prism(points, h, at=(0, 0, 0), axis="z", name="prism"):
    """Extrude a closed 2D outline [(u, v), ...] by h along +axis, starting at `at`.
    axis "z": the outline lies in XY. "x": u is Y and v is Z. "y": u is X and v is Z."""
    bm = bmesh.new()
    vs = [bm.verts.new((x, y, 0.0)) for x, y in points]
    face = bm.faces.new(vs)
    top = bmesh.ops.extrude_face_region(bm, geom=[face])
    bmesh.ops.translate(bm, vec=(0, 0, h), verts=[g for g in top["geom"] if isinstance(g, bmesh.types.BMVert)])
    bm.transform(Matrix.Translation(at) @ _axis_matrix(axis))
    return _object(name, bm)


def lathe(profile, at=(0, 0, 0), segments=None, name="lathe"):
    """Revolve [(radius, z), ...] about Z. Start and end on the axis (radius 0) for a solid, or give
    a closed loop off the axis for a ring."""
    n = segments or segments_for(2.0 * max(r for r, _ in profile))
    bm = bmesh.new()
    vs = [bm.verts.new((r, 0.0, z)) for r, z in profile]
    edges = [bm.edges.new((vs[i], vs[i + 1])) for i in range(len(vs) - 1)]
    if profile[0][0] > 1e-9 or profile[-1][0] > 1e-9:
        edges.append(bm.edges.new((vs[-1], vs[0])))
    bmesh.ops.spin(bm, geom=vs + edges, cent=(0, 0, 0), axis=(0, 0, 1), angle=2.0 * math.pi, steps=n,
                   use_merge=True, use_duplicate=False)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6)
    bmesh.ops.translate(bm, vec=at, verts=bm.verts[:])
    return _object(name, bm)


def text(body, size, depth, at=(0, 0, 0), font=None, spacing=1.0, name="text"):
    """Solid lettering lying in XY, capitals about `size` mm tall, `depth` mm thick from at.z upward,
    centred on `at`. Emboss with union, engrave with cut, or keep it as its own colour. Keep strokes
    at least two nozzle widths wide: bold fonts, 6 mm capitals or larger on a 0.4 mm nozzle.
    Letters that touch at a point are spread a little until every letter is a clean solid."""
    for attempt in range(6):
        cu = bpy.data.curves.new(name + "_curve", "FONT")
        cu.body, cu.size, cu.space_character = body, size / 0.7, spacing + 0.04 * attempt
        cu.align_x, cu.align_y = "CENTER", "CENTER"
        if font:
            cu.font = bpy.data.fonts.load(font, check_existing=True)
        tmp = bpy.data.objects.new(name + "_curve", cu)
        bpy.context.scene.collection.objects.link(tmp)
        bpy.context.view_layer.update()
        me = bpy.data.meshes.new_from_object(tmp.evaluated_get(bpy.context.evaluated_depsgraph_get()))
        bpy.data.objects.remove(tmp)
        bpy.data.curves.remove(cu)
        bm = bmesh.new()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
        # the flat outline of each letter, welded, then pulled up into a closed solid
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
        bmesh.ops.dissolve_degenerate(bm, dist=1e-6, edges=bm.edges[:])
        top = bmesh.ops.extrude_face_region(bm, geom=bm.faces[:])
        bmesh.ops.translate(bm, vec=(0, 0, depth),
                            verts=[g for g in top["geom"] if isinstance(g, bmesh.types.BMVert)])
        if all(len(e.link_faces) == 2 for e in bm.edges) and all(v.is_manifold for v in bm.verts):
            break
        if attempt < 5:
            bm.free()
    bmesh.ops.translate(bm, vec=at, verts=bm.verts[:])
    return _object(name, bm)


# -------------------------------------------------------------------------------------- outlines

def rounded_rect(sx, sy, r, n=8):
    """Outline of a rectangle sx by sy centred on the origin, corners rounded to radius r."""
    r = min(r, sx / 2.0 - 1e-6, sy / 2.0 - 1e-6)
    pts = []
    for cx, cy, a0 in ((sx / 2 - r, sy / 2 - r, 0), (-sx / 2 + r, sy / 2 - r, 90),
                       (-sx / 2 + r, -sy / 2 + r, 180), (sx / 2 - r, -sy / 2 + r, 270)):
        for i in range(n + 1):
            a = math.radians(a0 + 90.0 * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def slot(length, d, n=12):
    """Outline of a slot along X: two half circles of diameter d whose centres are `length` apart."""
    pts = []
    for cx, a0 in ((length / 2.0, -90), (-length / 2.0, 90)):
        for i in range(n + 1):
            a = math.radians(a0 + 180.0 * i / n)
            pts.append((cx + d / 2.0 * math.cos(a), d / 2.0 * math.sin(a)))
    return pts


def polygon(sides, across_flats):
    """Regular polygon outline (6 sides for a nut), a flat facing +X and -X."""
    r = across_flats / 2.0 / math.cos(math.pi / sides)
    return [(r * math.cos(2 * math.pi * (i + 0.5) / sides), r * math.sin(2 * math.pi * (i + 0.5) / sides))
            for i in range(sides)]


# --------------------------------------------------------------------------------------- cutters

def teardrop(d, length, at=(0, 0, 0), axis="x", truncate=0.0, name="teardrop"):
    """Cutter for a horizontal hole of diameter d along X or Y, starting at `at` (the hole's centre
    line). Its roof rises at 45 degrees to a peak, so it prints without support. `truncate` cuts the
    peak flat that many mm below its tip, leaving a short bridge."""
    r, n = d / 2.0, segments_for(d)
    pts = []
    for i in range(n + 1):
        a = math.radians(135.0 + 270.0 * i / n)          # from upper left, round the bottom, to upper right
        pts.append((r * math.cos(a), r * math.sin(a)))
    peak = r * math.sqrt(2.0)
    if truncate > 0.0:
        y = peak - truncate
        pts += [(peak - y, y), (-(peak - y), y)]
    else:
        pts.append((0.0, peak))
    return prism(pts, length, at, axis, name)


def countersink(d, head_d, depth, at=(0, 0, 0), name="countersink"):
    """Cutter for a flat-head screw entering from above: a through hole of diameter d going down
    `depth` from at.z, with a 90 degree cone opening to head_d at the top."""
    hole = cylinder(d, depth + 0.02, (at[0], at[1], at[2] - depth - 0.01), name=name)
    ch = (head_d - d) / 2.0
    cone = cylinder(d, ch + 0.01, (at[0], at[1], at[2] - ch), d_top=head_d + 0.02, name=name + "_cone")
    return union(hole, cone)


def counterbore(d, head_d, head_h, depth, at=(0, 0, 0), name="counterbore"):
    """Cutter for a socket-head screw entering from above: hole d down `depth` from at.z, with a
    pocket head_d wide and head_h deep at the top."""
    hole = cylinder(d, depth + 0.02, (at[0], at[1], at[2] - depth - 0.01), name=name)
    pocket = cylinder(head_d, head_h + 0.01, (at[0], at[1], at[2] - head_h), name=name + "_head")
    return union(hole, pocket)


def hex_pocket(across_flats, depth, at=(0, 0, 0), name="hex_pocket"):
    """Cutter for a captive nut: hexagon across_flats wide, going down `depth` from at.z."""
    return prism(polygon(6, across_flats), depth + 0.01, (at[0], at[1], at[2] - depth), name=name)


# --------------------------------------------------------------------------------------- combine

def _boolean(a, others, op, keep):
    for b in others:
        mod = a.modifiers.new("pk_bool", "BOOLEAN")
        mod.operation, mod.solver, mod.object = op, "EXACT", b
        bpy.context.view_layer.update()
        me = bpy.data.meshes.new_from_object(a.evaluated_get(bpy.context.evaluated_depsgraph_get()))
        a.modifiers.remove(mod)
        old = a.data
        a.data = me
        bpy.data.meshes.remove(old)
        if not keep:
            data = b.data
            bpy.data.objects.remove(b)
            if data.users == 0:
                bpy.data.meshes.remove(data)
    return clean(a)


def union(a, *others, keep=False):
    """Fuse the others into a (they are deleted unless keep=True). Returns a."""
    return _boolean(a, others, "UNION", keep)


def cut(a, *tools, keep=False):
    """Subtract the tools from a (they are deleted unless keep=True). Returns a."""
    return _boolean(a, tools, "DIFFERENCE", keep)


def common(a, *others, keep=False):
    """Keep only what a shares with the others. Returns a."""
    return _boolean(a, others, "INTERSECT", keep)


def copy(ob, name=None):
    new = ob.copy()
    new.data = ob.data.copy()
    new.name = name or ob.name + "_copy"
    bpy.context.scene.collection.objects.link(new)
    return new


# ----------------------------------------------------------------------------------------- place

def _apply(ob, m):
    bm = _edit(ob)
    bm.transform(m)
    if m.determinant() < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    _store(ob, bm)
    return ob


def move(ob, x=0.0, y=0.0, z=0.0):
    return _apply(ob, Matrix.Translation((x, y, z)))


def rotate(ob, axis, degrees, about=(0, 0, 0)):
    """Rotate about a line through `about` parallel to X, Y or Z."""
    t = Matrix.Translation(about)
    return _apply(ob, t @ Matrix.Rotation(math.radians(degrees), 4, axis.upper()) @ t.inverted())


def mirror(ob, axis="x"):
    """Mirror through the plane perpendicular to the axis, at the origin."""
    s = [1.0, 1.0, 1.0]
    s["xyz".index(axis.lower())] = -1.0
    return _apply(ob, Matrix.Diagonal((*s, 1.0)))


def bounds(ob):
    """(min Vector, max Vector) of the object's mesh."""
    cos = [v.co for v in ob.data.vertices]
    return (Vector((min(c.x for c in cos), min(c.y for c in cos), min(c.z for c in cos))),
            Vector((max(c.x for c in cos), max(c.y for c in cos), max(c.z for c in cos))))


def to_bed(ob):
    """Sit the lowest point on Z=0 and centre the object in X and Y."""
    lo, hi = bounds(ob)
    return move(ob, -(lo.x + hi.x) / 2.0, -(lo.y + hi.y) / 2.0, -lo.z)


# ----------------------------------------------------------------------------------------- edges

def chamfer(ob, width, where="bottom", segments=1, angle=30.0):
    """Chamfer sharp edges (segments > 1 rounds them instead).

    where: "bottom"   edges round the face on the bed (use 0.4 to 0.6 mm: hides elephant's foot)
           "top"      edges round the highest face
           "vertical" edges parallel to Z
           "all"      every sharp edge
           callable(mid: Vector, direction: Vector) -> bool, tested on every sharp edge
    Round bottom edges overhang at their start; chamfer those and round the rest.
    """
    bm = _edit(ob)
    bm.edges.ensure_lookup_table()
    zs = [v.co.z for v in bm.verts]
    zmin, zmax, eps = min(zs), max(zs), 1e-4
    picked = []
    for e in bm.edges:
        if len(e.link_faces) != 2 or e.calc_face_angle(0.0) < math.radians(angle):
            continue
        a, b = e.verts[0].co, e.verts[1].co
        d = (b - a).normalized()
        if where == "bottom":
            ok = a.z < zmin + eps and b.z < zmin + eps
        elif where == "top":
            ok = a.z > zmax - eps and b.z > zmax - eps
        elif where == "vertical":
            ok = abs(d.z) > 0.999
        elif where == "all":
            ok = True
        else:
            ok = bool(where((a + b) / 2.0, d))
        if ok:
            picked.append(e)
    if picked:
        bmesh.ops.bevel(bm, geom=picked, offset=width, offset_type="OFFSET", segments=segments,
                        profile=0.5, affect="EDGES", clamp_overlap=True)
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6)
    _store(ob, bm)
    return ob


# ---------------------------------------------------------------------------------------- colour

def colour(ob, hex_colour, filament=None):
    """Mark an object as one colour or material of a multi-part print, e.g. colour(logo, "#d22",
    "red PLA"). Each colour is its own closed solid; cut a pocket for it in the body it sits in
    (cut(body, logo, keep=True)) so no volume belongs to two parts."""
    h = hex_colour.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    ob["print_colour"] = "#" + h.upper()
    if filament:
        ob["print_filament"] = filament
    ob.color = tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)) + (1.0,)
    return ob


# ---------------------------------------------------------------------------------------- finish

def clean(ob):
    """Weld coincident vertices and drop zero-area faces and loose vertices. Face directions are
    left alone: a boolean result is already consistent, and the walls of an inner cavity must keep
    facing into the cavity."""
    bm = _edit(ob)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
    bmesh.ops.dissolve_degenerate(bm, dist=1e-6, edges=bm.edges[:])
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
    _store(ob, bm)
    return ob


def check(objects, **settings):
    """Run print_check on objects in the scene; print the summary and return the report."""
    import print_check as pc
    objs = objects if isinstance(objects, (list, tuple)) else [objects]
    rep = pc.run(objects=objs, **settings)
    print(pc.summary(rep))
    return rep


def export(objects, out_base, formats=("3mf", "stl"), settings=None, report=None, **kw):
    """Write out_base.3mf / .stl / .json (see print_export.py). Returns the file list."""
    import print_export as px
    objs = objects if isinstance(objects, (list, tuple)) else [objects]
    res = px.export(objs, out_base, formats=formats, settings=settings, report=report, **kw)
    for f in res["files"]:
        print("WROTE", f)
    return res

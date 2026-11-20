"""Render a review board that shows how a model will print. Open the PNG and look at it.

Runs inside Blender (5.x), headless, with the Workbench renderer. Runs print_check.py first and
colours the model with its findings.

  blender -b --factory-startup -P print_review.py -- MODEL.stl OUT.png [--tile 560]
          [--section x|y|z[=MM]] [print_check options: --process --nozzle --layer --overhang ...]

Eight tiles, left to right, top row then bottom row. Each tile carries its own caption.
  1 overhang map, from above       5 right side
  2 overhang map, part turned over 6 top
  3 first layer, seen from below   7 wall thickness, from the back
  4 front                          8 section through the middle, wall thickness
Tiles 4 to 6 show each part in its own colour when the print has several parts.

Overhang colours   red: needs support   yellow: within 15 degrees of the limit
                   green: flat span short enough to bridge   blue: on the bed
Thickness colours  red: too thin to print   orange: thinner than the recommended wall
                   dark: the cut face of the section
The checkered bed has 10 mm squares (50 or 100 mm for large models; the caption says which).

Also writes OUT.json: the print_check report. Exit code is 0 even when the check fails; this tool
is for looking, print_check.py is the gate.

From another script running in Blender:
  import print_review as pr
  pr.review(objects=[obj], out="review/part.png")        # returns the print_check report
"""
import argparse
import json
import math
import os
import sys
import tempfile

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import print_check as pc  # noqa: E402

GREY = (0.62, 0.64, 0.66)
RED, YELLOW, GREEN, BLUE = (0.82, 0.08, 0.06), (0.92, 0.66, 0.05), (0.10, 0.58, 0.22), (0.08, 0.28, 0.85)
ORANGE, CUT = (0.95, 0.42, 0.03), (0.07, 0.07, 0.09)
PALETTE = ((0.62, 0.64, 0.66), (0.85, 0.33, 0.10), (0.10, 0.45, 0.70), (0.93, 0.69, 0.13),
           (0.47, 0.67, 0.19), (0.49, 0.18, 0.56), (0.30, 0.75, 0.93), (0.64, 0.08, 0.18))


def _linear(hex_colour):
    h = hex_colour.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return tuple(out)


def _coloured(scene, name, verts, tris, colours):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts.tolist(), [], tris.tolist())
    me.update()
    attr = me.color_attributes.new("print", "FLOAT_COLOR", "CORNER")
    rgba = np.concatenate([np.repeat(colours, 3, axis=0), np.ones((len(tris) * 3, 1))], axis=1)
    attr.data.foreach_set("color", rgba.astype(np.float32).ravel())
    me.color_attributes.active_color = attr
    me.color_attributes.render_color_index = 0
    ob = bpy.data.objects.new(name, me)
    scene.collection.objects.link(ob)
    return ob


def _bed(scene, lo, hi):
    span = max(hi[0] - lo[0], hi[1] - lo[1])
    sq = 10.0 if span <= 400 else 50.0 if span <= 2000 else 100.0
    x0, x1 = math.floor(lo[0] / sq - 1) * sq, math.ceil(hi[0] / sq + 1) * sq
    y0, y1 = math.floor(lo[1] / sq - 1) * sq, math.ceil(hi[1] / sq + 1) * sq
    nx, ny = int(round((x1 - x0) / sq)), int(round((y1 - y0) / sq))
    verts, faces, cols = [], [], []
    z = lo[2] - 0.02
    for i in range(nx):
        for j in range(ny):
            b = len(verts)
            xa, ya = x0 + i * sq, y0 + j * sq
            verts += [(xa, ya, z), (xa + sq, ya, z), (xa + sq, ya + sq, z), (xa, ya + sq, z)]
            faces += [(b, b + 1, b + 2), (b, b + 2, b + 3)]
            c = (0.30, 0.31, 0.33) if (i + j) % 2 else (0.36, 0.37, 0.39)
            cols += [c, c]
    return _coloured(scene, "_bed", np.array(verts), np.array(faces), np.array(cols)), sq


def _section(scene, verts, tris, colours, axis, value):
    """Cut the model with a plane and cap the cut. Returns a coloured object of the kept half."""
    bm = bmesh.new()
    vs = [bm.verts.new(v) for v in verts.tolist()]
    layer = bm.faces.layers.int.new("src")
    for i, t in enumerate(tris.tolist()):
        try:
            f = bm.faces.new((vs[t[0]], vs[t[1]], vs[t[2]]))
            f[layer] = i + 1
        except ValueError:
            pass
    co = [0.0, 0.0, 0.0]
    no = [0.0, 0.0, 0.0]
    co[axis], no[axis] = value, -1.0 if axis == 1 else 1.0     # keep the half away from the viewer
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=co,
                           plane_no=no, clear_outer=True, clear_inner=False)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
    cut_edges = [e for e in bm.edges if e.is_boundary]
    if cut_edges:
        bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=cut_edges, normal=no)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.verts.ensure_lookup_table()
    v = np.array([p.co[:] for p in bm.verts]).reshape(-1, 3)
    t = np.array([[p.index for p in f.verts] for f in bm.faces]).reshape(-1, 3)
    src = np.array([f[layer] for f in bm.faces])
    bm.free()
    cols = np.where(src[:, None] > 0, colours[np.maximum(src - 1, 0)], np.array(CUT)[None, :])
    return _coloured(scene, "_section", v, t, cols)


def _camera(cam, direction, lo, hi):
    d = Vector(direction).normalized()
    centre = (Vector(lo) + Vector(hi)) / 2.0
    diag = (Vector(hi) - Vector(lo)).length
    quat = _look(d)
    cam.matrix_world = Matrix.Translation(centre - d * (diag * 2.0 + 20.0)) @ quat.to_matrix().to_4x4()
    right = quat @ Vector((1, 0, 0))
    up = quat @ Vector((0, 1, 0))
    w = h = 0.0
    for x in (lo[0], hi[0]):
        for y in (lo[1], hi[1]):
            for z in (lo[2], hi[2]):
                p = Vector((x, y, z)) - centre
                w, h = max(w, abs(p.dot(right))), max(h, abs(p.dot(up)))
    cam.data.ortho_scale = 2.0 * max(w, h) * 1.14 + 1e-3
    cam.data.clip_start, cam.data.clip_end = 0.1, diag * 6.0 + 200.0


def _look(d):
    """Camera rotation looking along d with world Z up on screen."""
    z = -d
    x = Vector((0, 0, 1)).cross(z)
    if x.length < 1e-6:
        x = Vector((1, 0, 0))
    x.normalize()
    y = z.cross(x)
    return Matrix((x, y, z)).transposed().to_quaternion()


def _compose(paths, cols, out):
    tiles = []
    for p in paths:
        img = bpy.data.images.load(p)
        w, h = img.size
        px = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        tiles.append(px.reshape(h, w, 4))
        bpy.data.images.remove(img)
    rows = [np.concatenate(tiles[i:i + cols], axis=1) for i in range(0, len(tiles), cols)]
    board = np.concatenate(rows[::-1], axis=0)                 # image rows run bottom to top
    h, w = board.shape[:2]
    img = bpy.data.images.new("_board", w, h, alpha=False)
    img.pixels.foreach_set(board.ravel())
    img.filepath_raw, img.file_format = out, "PNG"
    img.save()
    bpy.data.images.remove(img)


def review(path=None, objects=None, out="review.png", tile=560, section=None, **kw):
    rep = pc.run(path=path, objects=objects, keep=True, **kw)
    out = os.path.abspath(out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    data = rep.pop("_data", None)
    with open(os.path.splitext(out)[0] + ".json", "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=1, default=pc.to_json)
    if data is None:
        return rep
    verts, tris, masks, thick, opts = (data[k] for k in ("verts", "tris", "masks", "thickness", "opts"))
    normal, _area, _cen = pc.face_data(verts, tris)

    over = np.tile(np.array(GREY), (len(tris), 1))
    over[masks["near"]] = YELLOW
    over[masks["bridge"]] = GREEN
    over[masks["support"]] = RED
    over[masks["bed"]] = BLUE
    upright = (np.abs(normal[:, 2]) > 0.7) & (opts["process"] == "fdm")
    lim = np.where(upright, min(3.0 * opts["layer"], opts["min_wall"]), opts["min_wall"])
    hard = np.where(upright, min(opts["layer"], opts["hard_wall"]), opts["hard_wall"])
    wall = np.tile(np.array(GREY), (len(tris), 1))
    wall[thick < lim - 1e-3] = ORANGE
    wall[thick < hard - 1e-3] = RED
    owner, given = data["owner"], data["colours"]
    multi = len(given) > 1
    part_cols = np.array([_linear(c) if c else PALETTE[i % len(PALETTE)] for i, c in enumerate(given)])
    plain = part_cols[owner] if multi else over

    # a clean scene of our own, in millimetres
    scene = bpy.data.scenes.new("_print_review")
    lo, hi = verts.min(axis=0), verts.max(axis=0)
    o_over = _coloured(scene, "_overhang", verts, tris, over)
    o_wall = _coloured(scene, "_walls", verts, tris, wall)
    o_plain = _coloured(scene, "_parts", verts, tris, plain) if multi else o_over
    axis = {"x": 0, "y": 1, "z": 2}[(section or "auto")[0]] if section and section[0] in "xyz" else \
        (1 if (hi[0] - lo[0]) >= (hi[1] - lo[1]) else 0)
    value = float(section.split("=")[1]) if section and "=" in section else float((lo[axis] + hi[axis]) / 2.0)
    o_sec = _section(scene, verts, tris, wall, axis, value)
    bed, sq = _bed(scene, lo, hi)

    cam_data = bpy.data.cameras.new("_cam")
    cam_data.type = "ORTHO"
    cam = bpy.data.objects.new("_cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    world = bpy.data.worlds.new("_world")
    world.color = (0.16, 0.17, 0.19)
    scene.world = world
    r = scene.render
    r.engine = "BLENDER_WORKBENCH"
    r.resolution_x = r.resolution_y = int(tile)
    r.resolution_percentage = 100
    r.image_settings.file_format = "PNG"
    r.film_transparent = False
    sh = scene.display.shading
    sh.light, sh.color_type = "STUDIO", "VERTEX"
    sh.show_cavity, sh.show_object_outline, sh.show_backface_culling = True, False, False
    sh.show_shadows = False
    scene.display.render_aa = "8"
    try:
        scene.view_settings.view_transform = "Standard"
    except TypeError:
        pass
    r.use_stamp = True
    for flag in ("date", "time", "render_time", "frame", "frame_range", "memory", "hostname", "camera",
                 "lens", "scene", "marker", "filename", "sequencer_strip"):
        if hasattr(r, "use_stamp_" + flag):
            setattr(r, "use_stamp_" + flag, False)
    r.use_stamp_note, r.use_stamp_labels = True, False
    r.stamp_font_size = max(11, int(tile / 34))
    r.stamp_background = (0.0, 0.0, 0.0, 0.75)
    r.stamp_foreground = (1.0, 1.0, 1.0, 1.0)

    size = "%g x %g x %g mm" % tuple(rep["size_mm"])
    sup = rep["orientation"]["support_area_mm2"]
    sec_name = "xyz"[axis]
    note_parts = f"  {len(given)} parts in their colours" if multi else ""
    sec_dir = (0, 1, 0) if axis == 1 else (-1, 0, 0) if axis == 0 else (0, 0, -1)
    shots = [
        (f"1 OVERHANG  {size}  squares {sq:g} mm", o_over, (-1, 1, -0.75), True),
        (f"2 TURNED OVER  red needs support: {sup:.0f} mm2", o_over, (-1, 1, -0.75), False),
        (f"3 FIRST LAYER from below  on bed: {rep['orientation']['bed_contact_mm2']:.0f} mm2",
         o_over, (0, 0, 1), False),
        ("4 FRONT" + note_parts, o_plain, (0, 1, 0), True),
        ("5 RIGHT" + note_parts, o_plain, (-1, 0, 0), True),
        ("6 TOP" + note_parts, o_plain, (0, 0, -1), True),
        (f"7 WALLS from the back  thinnest {rep['walls']['min']} mm", o_wall, (1, -1, -0.75), True),
        (f"8 SECTION at {sec_name} = {value:.1f} mm  dark = solid", o_sec, sec_dir, axis != 2),
    ]
    tmp = tempfile.mkdtemp(prefix="print_review_")
    paths = []
    for i, (note, ob, direction, show_bed) in enumerate(shots):
        for o in {o_over, o_wall, o_sec, o_plain}:
            o.hide_render = o is not ob
        bed.hide_render = not show_bed
        if i == 1:                        # the part turned over, so the light falls on its underside
            ob.rotation_euler = (math.pi, 0.0, 0.0)
            _camera(cam, direction, (lo[0], -hi[1], -hi[2]), (hi[0], -lo[1], -lo[2]))
        else:
            ob.rotation_euler = (0.0, 0.0, 0.0)
            _camera(cam, direction, lo, hi)
        r.stamp_note_text = note
        r.filepath = os.path.join(tmp, f"tile{i}.png")
        bpy.ops.render.render(write_still=True, scene=scene.name)
        paths.append(r.filepath)
    _compose(paths, 4, out)
    for p in paths:
        os.remove(p)
    os.rmdir(tmp)
    rep["review_board"] = out
    return rep


def main():
    p = argparse.ArgumentParser(prog="print_review.py", description=__doc__.split("\n")[0])
    pc.add_arguments(p)
    p.add_argument("out", nargs="?")
    p.add_argument("--tile", type=int, default=560)
    p.add_argument("--section")
    a = p.parse_args(pc.cli_argv())
    model, out = a.model, a.out
    if out is None:                       # scene mode: the only positional is the output
        model, out = None, a.model
    rep = review(path=model, objects=a.objects, out=out, tile=a.tile, section=a.section, **pc.kwargs_from(a))
    print(pc.summary(rep))
    if rep.get("review_board"):
        print("REVIEW BOARD", rep["review_board"])
    print(pc.MARK + json.dumps(rep, default=pc.to_json, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()

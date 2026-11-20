# Making an existing model printable

Game assets, render models, sculpts, scans and AI-generated meshes are surfaces made to be
looked at. A printer needs closed solids with real thickness. Run `print_check.py` first: its
errors say which of the steps below apply.

## Contents

- Triage
- From a game or render model
- From a sculpt, scan or AI mesh
- Scale, base and split
- Blender calls that do the work

## Triage

| The check says | Usual cause | Fix |
| --- | --- | --- |
| open edges | planes for cloth, hair, leaves, signs; culled undersides; holes | solidify single-sided surfaces; fill or cap holes; remesh |
| edges shared by more than two faces | faces inside the model, parts sharing an edge | delete inner faces; union the parts |
| inside-out shell, inconsistent normals | mirrored parts, mixed winding | recalculate normals outward |
| many shells, pairs of faces crossing | the model is a pile of interpenetrating pieces | boolean union (exact), or voxel remesh into one shell |
| thin walls | blades, capes, fingers, antennae, wires | thicken to two lines (FDM) or 1 mm (resin); merge into a neighbour |
| probably the wrong unit | modelled in metres or with an arbitrary scale | scale to the wanted size in millimetres |
| no flat bed contact, tall and narrow | characters and organic shapes | add a base, or cut a flat; lean or pose so it stands |
| large support area, mid-air starts | arms out, weapons, chins, wings | re-pose, split into parts, turn; `print_orient.py` |

Keep the source file untouched. Work on a copy and export from that.

## From a game or render model

1. **Import** at the right scale (glTF is metres; the checker and exporter convert). Apply all
   transforms and modifiers.
2. **Drop what cannot print:** particles, decal planes, alpha-card hair and foliage, backface
   shells, collision meshes, LODs, anything smaller than the printer resolves at the print size.
   Rebuild what matters as solid geometry (hair as a solid mass, leaves as thick clumps).
3. **Give single surfaces thickness:** Solidify modifier, thickness at least two lines at print
   scale, offset inward so the silhouette is kept.
4. **Make one solid.** Two routes:
   - *Exact:* boolean union of the closed pieces (`pk.union`, solver EXACT). Keeps sharp edges
     and exact dimensions. Needs each piece closed first.
   - *Voxel remesh:* join everything, then Remesh modifier in VOXEL mode with a voxel about a
     third of the nozzle (0.1–0.15 mm at print scale; larger for big models). Always gives one
     watertight shell, at the price of slightly softened edges. Best for characters and props
     made of many overlapping parts. Decimate afterwards to under a million triangles.
   Thin dangling details (reins, tassels, whiskers, antennae) come out of a remesh as specks and
   slivers: delete or thicken them first, and afterwards remove any leftover shells
   (`shells` above 1 in the check) and re-check for open edges.
5. **Detail carried by textures is gone.** Bake it into geometry if it matters (displace from
   the height or normal map before remeshing), exaggerating depth to at least 0.3–0.4 mm at
   print scale, or leave it for paint.
6. **Colour:** split by material into separate closed solids for multi-colour (see
   `multicolor.md`), or print in one colour and paint.

## From a sculpt, scan or AI mesh

- Usually one dense shell with holes, self-intersections and noise. Voxel remesh first, then
  smooth lightly, then decimate (collapse, keeping the silhouette) to 200k–800k triangles.
- AI meshes often hide inner shells and paper-thin regions: remesh, then read tile 7 (walls) and
  tile 8 (section) of the review board.
- Scans are open underneath: cut flat with a plane and cap.
- Fine surface noise prints as roughness and slows slicing; smooth what is below 0.1 mm.

## Scale, base and split

- **Scale to the detail:** the thinnest feature decides the smallest printable size. Check
  thin walls at the target scale, then thicken or scale up. For miniatures, exaggerate thin
  features (weapons, fingers, straps) by 1.5–2 × rather than scaling the whole figure.
- **Base:** a 2–3 mm disc or plinth unioned under the feet gives bed contact and a standing
  model. Sink feet 0.3 mm into it so the union is solid.
- **Flat cut:** bisect just above the lowest point so the model sits on a real face.
- **Split** large or support-heavy models along natural seams (waist, wrists, panel lines) with
  keyed joints; see `efficiency.md` section 6. Each part gets its own orientation.
- **Hollow** large FDM models only through slicer infill (leave them solid in the file). Hollow
  resin models in the file, with drain holes.

## Blender calls that do the work

Run in an author script (`blender_run.py your_script.py`), one millimetre per unit, on a copy.

```python
import bpy, bmesh
ob = bpy.context.scene.objects["Model"]

def apply(ob, mod):                                   # apply a modifier without bpy.ops
    bpy.context.view_layer.update()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    ob.modifiers.remove(mod); old = ob.data; ob.data = me; bpy.data.meshes.remove(old)

m = ob.modifiers.new("solid", "SOLIDIFY"); m.thickness = 0.9; m.offset = -1.0; apply(ob, m)
m = ob.modifiers.new("remesh", "REMESH"); m.mode = "VOXEL"; m.voxel_size = 0.15; apply(ob, m)
m = ob.modifiers.new("dec", "DECIMATE"); m.ratio = 0.3; apply(ob, m)

bm = bmesh.new(); bm.from_mesh(ob.data)
bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-4)                 # weld
bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary])     # cap small holes
bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],   # flat cut at z = 0.5
                       plane_co=(0, 0, 0.5), plane_no=(0, 0, -1), clear_outer=True)
bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary])
bm.to_mesh(ob.data); bm.free()
```

Voxel size is in scene units: with a model in metres use 0.00015. Re-run `print_check.py`
after each step; remeshing fixes topology but can close gaps and holes that were meant to stay
open, and decimation can thin walls.

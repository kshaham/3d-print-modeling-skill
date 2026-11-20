---
name: 3d-print-modeling
description: >-
  Design, convert, repair, orient and validate 3D models so they print well and
  efficiently on FDM, resin or SLS printers: no or little support, short print time,
  less material, correct fits, single or multi-colour. Use for any request to make
  something 3D printable or to improve how a model prints: STL, 3MF, slicer, supports,
  overhangs, bridges, wall thickness, tolerances, print orientation, brackets,
  enclosures, replacement parts, figurines, miniatures, terrain, cosplay props,
  print-in-place toys, vases, or turning a game, render, sculpt, scan or AI mesh into
  a printable file. Asks once for the user's printer, colours and materials and
  remembers them (default printer: Bambu Lab P1S). Bundles a headless Blender 5
  toolkit: printability checker, orientation ranker, review-board renderer, 3MF/STL
  exporter, solid-modeling helpers, and a slicer driver for Bambu Studio, OrcaSlicer
  and PrusaSlicer that reports real print time and filament.
---

# 3D print modeling

Model for the printer, not for the screen. A printable model is a closed solid in
millimetres, shaped so each layer rests on the one below, sized to the machine's nozzle
and build volume, and turned the way that prints fastest with the least support.

Paths below are relative to this skill's folder. Run every tool through
`python scripts/blender_run.py <script> ...`; it finds Blender and hides its noise.

## 1. Start with the printer profile (ask once, then never again)

Before any modeling, check for a saved profile:

```
python scripts/printer_profile.py --show
```

If `"missing"` is empty, use it and ask nothing. Also check your memory for a printer note.

If anything is missing, ask the user these questions together, in one message (use the
question tool if you have one):

1. **Which 3D printer do you have?** Make and model, or the type (filament, resin, powder
   service) with its build volume and nozzle if it is unusual or home-built.
2. **How many colours can it print at once?** One, or several with a filament changer
   (AMS, MMU and similar), several nozzles or tools, or manual swaps at a layer.
3. **Which materials do you print with?** For example PLA, PETG, ABS/ASA, TPU, nylon, or
   which resin.

Save the answers immediately, in both places:

```
python scripts/printer_profile.py --set printer="Bambu Lab P1S" colors=4 color_system=AMS materials=PLA,PETG,TPU
```

- A known printer name fills in process, build volume and nozzle (`--printers` lists them).
  If `"missing"` still lists `build`, ask for the build volume and set `build=X,Y,Z`.
- **Write the same facts to your persistent memory** if you have one (in Claude Code: a
  `user` memory named `3d-printer-profile`, with its line in `MEMORY.md`), noting that the
  numbers live in the profile file. Later sessions must find it without asking.
- Ask again only when the user mentions a new printer, nozzle, colour unit or material;
  then update both places.
- If the user will not say, proceed with the built-in default printer, a **Bambu Lab P1S**
  (filament, 0.4 mm nozzle, 256 mm cube, PLA, one colour), say that you did, and do not
  save it.

The profile sets the defaults of every tool (process, build volume, nozzle, material).
Colours and materials shape the design itself: read `references/multicolor.md` when the
job has more than one colour, `references/materials.md` when the material is not PLA.
When a job names a material, pass it to every tool (`--material petg`, or `MATERIAL` in
the template): it changes the bridge and overhang limits, not only the mass estimate.

Everything else about a job (what it is for, sizes of mating parts, where the load pulls,
which faces show) belongs to that job: infer it from the request, and ask only for
dimensions you cannot know.

## 2. The quality bar

A model that merely exports is not done. It is done when:

- `print_check.py` reports `PASS`, and every warning is fixed or accepted with a reason
  you can state;
- it needs **no support**, or the support left is the least possible, rests on the bed,
  and you can say why it stays;
- the orientation was chosen on purpose (support, time, strength, visible faces) and is
  already applied in the exported file;
- fits, holes and thin features follow the numbers in `references/design-rules.md`;
- you have **looked at the review board** and critiqued it at least twice;
- the user gets 3MF (and STL if wanted), the manifest, the settings that matter and the
  expected time and material, from a real slice when a slicer is installed.

## 3. The path for a new model

1. **Decide how it prints before drawing it.** Which face sits on the bed, where the
   layers run relative to the load, which faces must look good. Sketch a blockout and run
   `print_orient.py` on it if the answer is not obvious. Read `references/efficiency.md`.
   Find the playbook for the kind of model in `references/model-types.md`.
2. **Start from the template.** Copy `assets/author_template.py` to
   `<project>/print/author_<name>.py`. It is a complete working part: named dimensions,
   `printkit` solids, check as a gate, export, manifest, `--review`. Set `MATERIAL`,
   replace `build()`.
3. **Block out the big forms**, then run it with `--review` and read the board. Fix
   orientation, bed contact and red areas now, while changes are cheap. When the check
   fails the template still renders the board, so look before guessing.
4. **Add features in printing terms:** holes sized with `pk.hole_d`, horizontal holes as
   `pk.teardrop`, ledges turned into 45° chamfers, bed edge chamfered, fits from `pk.FIT`.
   Let cutters overshoot by a millimetre and sink joined parts 0.2 mm into each other,
   rather than leaving faces exactly flush. For load-bearing or mating parts read
   `references/functional-parts.md`; print `assets/author_fit_gauge.py` once to learn the
   printer's real clearances.
5. **Check, look, fix, repeat.** At least two passes of critique → change → re-render.
   Record what each pass changed (support area, time, mass before and after).
6. **Export and hand off** as in section 8.

For precise mechanical parts, a CAD kernel driven by code (build123d, CadQuery, OpenSCAD) is
a good alternative for the geometry if one is installed; export its STL or 3MF and run it
through the same check, orientation and review tools.

## 4. The path for an existing model

Game assets, sculpts, scans, AI meshes, downloaded STLs, or "make this print better":

1. `python scripts/blender_run.py print_check.py model.stl` and read every error.
2. Repair in the order of `references/converting-models.md`: units and scale, thickness,
   one closed shell, thin features, base. Keep the source file untouched.
3. `print_orient.py` for the best way up; apply it with `--apply`.
4. Reduce support and material by design changes (`references/efficiency.md`), not only by
   settings. Split with keyed joints when one piece cannot print well
   (`pk.split(obj, "z", height)` returns two halves with pin sockets, and the pegs).
5. Review board, then export. Report before-and-after numbers.

## 5. Numbers to keep in your head (FDM, 0.4 mm nozzle)

| Rule | Value |
| --- | --- |
| Wall | 0.8 mm minimum (two lines); 1.2–2.4 mm structural; multiples of 0.45 mm |
| Floor and roof | 3–5 layers |
| Overhang | 45° from vertical; flat ledges become chamfers |
| Bridge | under 30 mm between two anchors, at one height |
| Vertical hole | model +0.2 mm (`pk.hole_d`) |
| Horizontal hole | teardrop above about 6 mm |
| Clearance per side | press 0.05, snug 0.10, slide 0.20, loose 0.35, print-in-place 0.30–0.40 mm |
| Bed edge | 0.4–0.6 mm chamfer, never a round |
| Text | strokes 0.9 mm+, capitals 6 mm+, 0.6 mm deep or high |
| Strength | loads along the layers; walls before infill |

Resin, powder and the reasons behind each number: `references/design-rules.md`.

## 6. Tools

The Blender tools run as `python scripts/blender_run.py <script> [args]`. Each prints a
readable summary; put `--json-only` right after `blender_run.py` for the report alone.
Flags `--process --nozzle --layer --min-wall --overhang --bridge --gap --build X,Y,Z
--material --unit` override the saved profile on any of the three analysis tools.
`printer_profile.py` and `print_slice.py` are plain Python: run them directly.

| Tool | Does | Typical call |
| --- | --- | --- |
| `printer_profile.py` | saved printer, colours, materials (plain Python) | `python scripts/printer_profile.py --show` |
| `print_check.py` | the gate: closed solid, size, walls, gaps that fuse, overhangs, bridges, mid-air starts, bed contact, cavities, colour changes, rough time/mass. Exit 1 on errors | `print_check.py part.3mf` |
| `print_orient.py` | ranks ways up by support, time, bed contact; `--strong-axis x` for load; `--apply out.3mf` writes the best | `print_orient.py part.stl --top 5` |
| `print_review.py` | eight-tile review board PNG plus the report as JSON | `print_review.py part.3mf review/part.png` |
| `print_export.py` | 3MF and STL in millimetres plus manifest, from a `.blend` | `--blend scene.blend print_export.py --out build/part --format 3mf stl` |
| `print_slice.py` | real time, grams and filament changes from Bambu Studio, OrcaSlicer or PrusaSlicer, using the printer's own presets | `python scripts/print_slice.py out/part.3mf --compare-supports` |
| `self_test.py` | proves the tools work on this machine and Blender version | `self_test.py` |
| `printkit.py` | modeling helpers for author scripts (below) | `import printkit as pk` |

Inputs: `.stl .3mf .obj .ply .glb .gltf .blend`. STL, OBJ and PLY are read as millimetres,
glTF as metres, `.blend` by its scene unit; `--unit` overrides. Several objects in one file
are treated as the parts of one print (one per colour): each must be closed, and they may touch.

**printkit** (one unit = 1 mm; every builder returns a closed solid):

- Solids: `box cylinder sphere prism lathe text`; outlines for `prism`: `rounded_rect slot polygon`.
- Cutters: `teardrop countersink counterbore hex_pocket`.
- Combine: `union cut common copy` (exact booleans; tools are consumed unless `keep=True`),
  `split` (two keyed halves with pin sockets, plus the pegs).
- Place: `move rotate mirror to_bed bounds`. Edges: `chamfer(obj, width, "bottom"|"top"|"vertical"|"all"|fn)`.
- Numbers: `FIT`, `SCREW["M3"]`, `hole_d`, `segments_for`.
- Colour: `colour(obj, "#hex", "filament")`. Finish: `clean check export save_blend`.

Read the docstrings in `scripts/printkit.py` before using a helper for the first time.

For modeling beyond these helpers (sculpting, Geometry Nodes, remeshing, modifiers), use the
`blender-*` skills if installed (`blender-core` first), working in millimetres, and bring
the result back through `print_check.py`. Their `blender-asset-qa` gate complements this
one; it does not replace the print checks.

## 7. Review by looking

```
python scripts/blender_run.py print_review.py part.3mf review/part.png
```

Open the PNG with your image reader and look at every tile. Left to right, top then bottom:

1. **Overhang map from above.** Red needs support, yellow is within 15° of the limit,
   green is a bridge short enough to print, blue touches the bed. Bed squares are 10 mm.
   Yellow on 45° chamfers, gussets and teardrop roofs is expected: they sit on the limit.
2. **The part turned over.** The same colours on the underside, where the red lives.
3. **First layer from below.** Blue is what holds the print to the bed: one or a few solid
   shapes, not specks.
4. **Front**, 5. **Right**, 6. **Top**: proportions and, for multi-colour prints, each part
   in its own colour.
7. **Wall thickness.** Orange is thinner than recommended, red will not print. The view is
   the corner that shows the most thin wall (the caption says which), the back otherwise.
8. **Section through the middle.** Dark is solid material, with the same orange and red on
   the surfaces behind the cut: look for unintended hollows, thin skins and trapped
   cavities. Move it with `--section x=12` (or `y=`, `z=`).

The report is written beside the image as `<name>.json`; `thin_at` and `gaps.at` in it give
the coordinates of anything the board does not show clearly.

Ask of each board:

- Is there any red, and could a chamfer, teardrop, split or turn remove it?
- Does the first layer hold the part? Is anything tall standing on something small?
- Is anything thinner than two lines, or thicker than it needs to be?
- Will the faces that matter be clean (not supported, not on the bed if it must be smooth)?
- Does it still look like what was asked for, at the size asked for?

Failures seen before:

- a ledge left flat because it looked fine on screen;
- round horizontal holes with drooping tops;
- a part passing the check upright while lying it down halves the time (run `print_orient.py`);
- inlaid text overlapping the body instead of sitting in a pocket;
- letters touching at one point and fusing into a non-manifold edge;
- an inner cavity flipped outward by a normals recalculation, hiding a 0.3 mm wall;
- a model built in metres exported 1000 times too small;
- a cutter ending exactly flush with a wall, leaving a seam the boolean could not close
  (the helpers now repair it, but overshoot anyway);
- a colour inlay exported as a separate object, which the slicer then arranged beside the
  model instead of inside it;
- a PETG part checked with PLA limits because the material was never passed.

## 8. Export and hand-off

Author scripts export with `pk.export(part, "out/name", settings=SETTINGS, report=report)`;
existing scenes with `print_export.py`. Both sit the model on Z = 0 in its print orientation
and write `name.3mf`, `name.stl` (if asked), and `name.json` (the manifest).

Then slice it if a slicer is installed: `python scripts/print_slice.py out/name.3mf`
(add `--compare-supports` when any support is left, `--material`, `--walls`, `--infill` to
match what you recommend). It uses the saved printer's own slicer and presets; for the
default Bambu Lab P1S that is Bambu Studio. Quote its time and grams instead of the
checker's estimate, and pass on any warning the slicer raises.

Tell the user, briefly:

- what was made and its size; the files and where they are;
- orientation (already applied) and whether supports are needed, with the reason if so;
- material and the settings that differ from a standard profile (`references/slicing.md`);
- time, grams and layers from `print_slice.py`, or the checker's figures labelled as rough
  estimates when no slicer is installed;
- for multi-colour: which colour is filament 1, 2, 3 (the manifest lists them), how many
  layers change colour and how many filament changes that costs;
- anything to do after printing, and any warning you accepted and why.

If a print fails, map the symptom to the model with the table in `references/slicing.md`
before changing settings.

## References

- `references/design-rules.md`: limits for FDM, resin and powder, and what the checker enforces.
- `references/efficiency.md`: orientation, designing supports out, material, time, splitting.
- `references/functional-parts.md`: fits, screws and inserts, strength, snap fits, enclosures.
- `references/multicolor.md`: one object per colour, by colour system; mixed materials.
- `references/materials.md`: what each filament, resin and powder changes in the design.
- `references/converting-models.md`: game, sculpt, scan and AI meshes into printable solids.
- `references/model-types.md`: playbooks for brackets, boxes, figurines, minis, terrain, props,
  articulated toys, vases, jigs and replacement parts.
- `references/slicing.md`: hand-off, `print_slice.py`, Bambu Studio and PrusaSlicer notes,
  settings to recommend, failure table.

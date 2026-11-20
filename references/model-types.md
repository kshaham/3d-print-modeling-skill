# Playbooks by kind of model

Pick the nearest kind, follow its order of work, and adapt. Every playbook ends the same way:
`print_check.py` passes, the review board has been looked at, files and settings are handed off.

## Contents

- Brackets, mounts, clips and other load-bearing parts
- Enclosures, boxes and organisers
- Figurines, busts and display models
- Tabletop miniatures
- Terrain, architecture and dioramas
- Large props and cosplay pieces
- Articulated and print-in-place toys
- Vases, planters, lamps and lithophanes
- Jigs, gauges and tools
- Replacement parts

## Brackets, mounts, clips and other load-bearing parts

1. Ask what it holds, where the load pulls, and what it fixes to (screw size, tube diameter).
2. Choose the orientation from the load: layers along the arm. Then shape the part so that
   orientation needs no support (45° gussets, teardrop holes, flat back on the bed).
3. Even 3–4 mm sections with ribs, rounded inside corners, three or more perimeters round holes.
4. Hand-off: 3–5 walls, 20–30 % infill, PETG or better if it flexes or sits in heat.

Reference: `functional-parts.md`. Template: `assets/author_template.py`.

## Enclosures, boxes and organisers

1. Get the contents' dimensions and add 0.5 mm all round (1 mm for things dropped in).
2. Box open side up, lid flat with its outer face on the bed: no support, clean faces.
3. 2 mm walls, rounded vertical corners (2–3 mm), chamfered bed edge, lip or screw bosses.
4. Openings in walls: arched or 45° tops, or leave them to short bridges under 20 mm.
5. Stackable or gridded organisers: keep to the grid's published dimensions exactly.

## Figurines, busts and display models

1. Decide the size from the thinnest feature (FDM: 0.8 mm; resin: 0.5–1 mm).
2. Pose for printing: limbs close to the body or resting on something, chin lifted less than
   45° overhang where possible, cloaks and hair as solid masses that reach down to a support.
3. Base or flat cut for bed contact. Split at natural seams when a limb forces heavy support.
4. FDM: orient so the face and front are free of supports (lean back 10–20°), 0.12–0.16 mm
   layers. Resin: tilt back 20–40°, supports on the back and underside, hollow if bulky.
5. Look hard at tiles 2 and 3 of the review board: every red patch is a scar on the surface.

Reference: `converting-models.md` for sculpts, game assets and AI meshes.

## Tabletop miniatures

Resin where possible. At 28–32 mm scale: weapons, staffs and fingers at least 0.6–0.8 mm
(exaggerate them, do not scale the figure), integral base 2–3 mm thick with the feet sunk in,
no sealed hollows, detail at least 0.2 mm deep to survive paint. FDM minis: 0.2 mm nozzle if
available, lean back, expect supports under chin, arms and weapons, and split off wings.

## Terrain, architecture and dioramas

1. Flat on the bed, open underside or 0 % infill region to save material; 1.2–1.6 mm walls.
2. Overhanging roofs, arches and windows drawn within 45° or as bridges; print roofs separately
   so interiors are reachable and no support is needed inside.
3. Tile to the game's grid; add 0.2 mm clearance to clips and magnets pockets (magnet +0.1 mm,
   one-layer floor to hide it or open pocket to glue).
4. Texture depth 0.4 mm or more so it survives 0.2 mm layers; coarse layers (0.24–0.28) are fine.

## Large props and cosplay pieces

1. Split to the bed with 5–10 mm margin, along seams that sanding or paint will hide.
2. Key every joint (pins, steps, dovetails) and number the parts on a hidden face.
3. Print as shells: 1.2–2 mm walls (3–4 perimeters), 5–10 % infill; 0.6 mm nozzle and 0.3 mm
   layers. Give each part the orientation with the least support on the outside surface.
4. Wearable parts: PETG or ASA, no sharp inside edges, strap slots with rounded ends.
5. Report total time and mass across parts; they add up fast.

## Articulated and print-in-place toys

1. Each segment is a separate shell joined by captive ball, hook or hinge joints with
   0.3–0.4 mm gaps and two-layer vertical gaps.
2. Flat on the bed, every segment touching it; joints built from 45° cones or chamfers.
3. First layer: 0.5 mm between neighbours, or they fuse. No supports anywhere, by design.
4. Check that nothing starts in mid-air and that the shells do not intersect.

## Vases, planters, lamps and lithophanes

- **Vase mode:** a solid shape, slopes within 45° (30° to be safe), no top, a flat bottom. The
  wall is one line; with a 0.6–0.8 mm nozzle it is strong enough to use. Say "spiral vase mode,
  bottom layers 3–5" in the hand-off.
- **Planters:** drainage holes, a separate saucer, PETG or ASA for wet and sun.
- **Lamp shades:** PLA softens near bulbs; LED only, and keep 20 mm from the source.
- **Lithophanes:** thickness 0.6 mm (light) to 3 mm (dark), printed standing on edge (curved
  ones stand by themselves; flat ones need a foot), 0.12 mm layers, 100 % infill, white PLA.

## Jigs, gauges and tools

Accuracy first: critical dimensions in XY, datum faces on the bed, chamfered bed edges, drill
bushings as press-fit metal sleeves rather than printed holes, engraved labels with the size
and the date. Print the clearance gauge from `functional-parts.md` before the first one.

## Replacement parts

1. Measure the original with calipers; ask for each dimension that cannot be seen in a photo.
2. Model to nominal, then adjust fits: holes +0.2 mm, mating bosses −0.1 mm.
3. Find why the original broke and reinforce there (round the corner, thicken the root, turn
   the layers), instead of copying the weakness.
4. Material at least as capable as the original for heat and load; say so if the user's is not.
5. Suggest a quick test slice of just the mating feature before the full print.

# Functional parts: fits, fasteners, flexures and strength

For parts that must fit something, hold something or move. Numbers are for FDM with a 0.4 mm
nozzle unless noted; `printkit` carries them as `pk.FIT`, `pk.SCREW` and `pk.hole_d`.

## Contents

- Fits and clearances
- Calibrate once per printer and material
- Screws, nuts and inserts
- Strength
- Snap fits and flexures
- Moving parts printed in place
- Enclosures

## Fits and clearances

Clearance is per side: a 10 mm pin in a "slide" hole needs a 10.4 mm hole.

| Fit | Per side | Use |
| --- | --- | --- |
| Press | 0.00–0.05 mm | bearings, magnets, pins that stay (add crush ribs, below) |
| Snug | 0.10 mm | lids that hold by friction, locating pegs |
| Slide | 0.20 mm | parts assembled by hand, drawers, telescoping tubes |
| Loose | 0.35 mm | parts that must drop in, anything long |
| Printed in place | 0.30–0.40 mm | hinges and joints printed already assembled |

- Holes shrink, pins grow: apply clearance to the hole and leave the pin nominal.
- **Crush ribs** make press fits tolerant: three to six ribs 0.2–0.3 mm high along the bore, so
  the ribs deform instead of the wall splitting.
- Round holes printed on their side are oval. Put accurate bores upright, or ream them.
- Long sliding fits bind: relieve the middle so only the two ends guide.
- Resin fits are tighter (0.05–0.15 mm per side); powder needs more (0.2–0.3 mm).

## Calibrate once per printer and material

The table is a starting point. A gauge takes 20 minutes to print and replaces guessing:

```
python scripts/blender_run.py assets/author_fit_gauge.py --out out
```

It writes a plate with six holes for an 8 mm pin, marked 05 to 40 (clearance per side in
hundredths of a millimetre), and the pin. Ask the user to try the pin in each hole and say
which clearance gives a press fit, a snug fit and a free slide; save the answer in the printer
profile (`printer_profile.py --set notes="PETG: press 0.05, snug 0.15, slide 0.25"`) and design
from it. `print_check.py` warns when facing surfaces are closer than 0.15 mm (`--gap`), the
distance at which printed parts fuse.

## Screws, nuts and inserts

`pk.SCREW["M3"]` gives, for M2 to M8: `tap` (hole a screw threads straight into plastic),
`clear` (clearance hole), `head_d`, `head_h` (socket head), `nut_af`, `nut_h`, `insert`
(typical heat-set insert hole; check the maker's sheet). Wrap printed holes in `pk.hole_d()`.

- **Screw into plastic** for a few assemblies: hole at `tap` diameter, at least 2.5 diameters
  deep, in a boss at least twice the screw's diameter.
- **Heat-set inserts** for repeated assembly: hole at the insert maker's diameter, 1 mm deeper
  than the insert, boss wall at least 1.6 mm, a small chamfer to start it. Print the boss upright.
- **Captive nut:** `pk.hex_pocket(nut_af + 0.3, nut_h + 0.3, ...)`. Feed it from the side through
  a slot, or from below with a one-layer bridge across the screw hole.
- **Printed threads:** M8 and larger only, axis upright, 0.2–0.4 mm of clearance, chamfered
  starts. Smaller threads strip; use an insert.
- **Counterbores** opening upward or downward print clean; opening sideways they need a teardrop.
- Put at least three perimeters round every screw hole (tell the slicer: 3–4 walls).

## Strength

- Loads along layers, not across them. A bracket printed so its layers stack along the arm
  breaks at a fraction of the load of one printed on its side.
- Bending puts the stress in the skin: perimeters matter, infill hardly does.
- Round every inside corner that sees load (2 mm radius or more), and thicken the root of
  cantilevers.
- Bolts in tension through layers: carry the load with a through-bolt and nut, not threads cut
  across layers.
- Material: PLA is stiff and strong but creeps and softens near 55 °C; PETG is tougher; ABS and
  ASA take heat; nylon and PC take abuse. See `materials.md`.

## Snap fits and flexures

A cantilever snap of length L, root thickness t, deflected by y sees strain ≈ 1.5 · t · y / L².
Keep strain under about 1.5 % for PLA, 3 % for PETG and ABS, 5 % or more for nylon.

- Make arms long and thin rather than short and thick; taper them toward the tip.
- Print the arm lying flat so layers run along it. An arm built up in Z snaps on first use.
- Round the root. Give the hook a 30–45° lead-in and a 90° (permanent) or 45° (releasable) catch.
- **Living hinges:** 0.4–0.6 mm thick (two layers), printed flat with the lines crossing the
  hinge, in PETG, PP or TPU. PLA cracks after a few bends.
- **Springs and clips:** PETG or nylon; PLA takes a set under constant load.

## Moving parts printed in place

- Gap 0.3–0.4 mm in XY, and at least two layers (0.4 mm) in Z between parts that must separate.
- Shape axles and sockets as 45° cones or use teardrop holes so the joint needs no support.
- Keep the first layer of each part separate on the bed (elephant's foot fuses close neighbours):
  0.5 mm gap at bed level or a chamfer on both.
- Give the user a way to break it free: a lever arm, a slot for a blade.
- Check with `print_check.py`: the parts must be separate shells, none floating in mid-air,
  and no "will fuse" warning between them.

## Enclosures

- Walls 2 mm (four lines with a 0.4 mm nozzle); ribs or a lip to keep long walls from bowing.
- Print the box open side up and the lid flat, outside face down, so neither needs support.
- Lid lip 1–1.5 mm with 0.2 mm clearance per side; snap bumps 0.3–0.5 mm high or screw bosses.
- Board standoffs: 2.5 mm above the floor or more, `tap` holes for the board's screws, fillet
  at the base. Leave 0.5 mm round the board.
- Openings for connectors: 0.5 mm clearance all round; openings in walls get 45° or arched tops.
- Vents as vertical slots (they are short bridges) rather than round holes in a wall.

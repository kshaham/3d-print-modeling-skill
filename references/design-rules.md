# Design rules by process

Numbers a model must respect to print. They are starting points for a tuned desktop machine;
a printer's own test prints override them. `print_check.py` enforces the ones marked ✔.

## Contents

- FDM (filament)
- Resin (MSLA, SLA, DLP)
- SLS and MJF (powder)
- Whatever the process

## FDM (filament)

Line width is about 1.1 × nozzle (0.45 mm for a 0.4 mm nozzle). Scale every XY number below
with the nozzle; scale Z numbers with the layer height (25–75 % of the nozzle).

| Feature | Minimum | Prefer | Why |
| --- | --- | --- | --- |
| Wall ✔ | 1 nozzle width (drops out below) | 2 lines (0.8–0.9 mm); structural 3–5 lines (1.2–2.4 mm) | one line has no strength and shows every seam |
| Floor or roof ✔ | 1 layer | 3–5 layers (0.6–1.0 mm at 0.2) | fewer layers show infill and leak |
| Overhang ✔ | 45° from vertical | 50–60° only for PLA with strong cooling | each layer needs half its width resting on the one below |
| Bridge ✔ | up to about 30 mm between two anchors | under 20 mm; straight, at one height | longer spans sag; a span with one anchor is a cantilever and needs support |
| Flat ledge with one anchor ✔ | 2 nozzle widths | none: chamfer it at 45° | prints into air |
| Vertical hole | 2 mm | add 0.2 mm to the diameter (`pk.hole_d`) | holes print 0.1–0.3 mm small; drill the ones that matter |
| Horizontal hole | round up to about 6 mm | teardrop above that (`pk.teardrop`) | the top of a round hole is a flat overhang |
| Pin or post | 3 mm | 5 mm, or print it lying down, or use a screw | upright pins snap along layers |
| Embossed text | stroke 2 lines wide, 2 layers high | 0.6–1.0 mm high, bold sans, capitals 6 mm+ | thin strokes vanish |
| Engraved text | 0.6 mm wide, 0.4 mm deep | on vertical faces engrave, on top faces either | embossed text on a wall is a row of overhangs |
| Gap between parts | 0.2 mm per side sliding | see `functional-parts.md` | parts fuse below about 0.15 mm |
| Bed edge | – | 0.4–0.6 mm chamfer (`pk.chamfer(obj, 0.5, "bottom")`) | first layer squashes wide (elephant's foot); a round here starts as an overhang |
| Vertical edge | – | 1–2 mm round | sharp corners ring, lift and concentrate stress |
| Inside corner under load | – | round, as large as fits | layers crack from sharp inside corners |

- **Snap dimensions to the machine.** Heights in multiples of the layer height; thin walls in
  multiples of the line width (0.9, 1.35, 1.8 mm). A 1.0 mm wall prints as two lines and a gap.
- **Tolerance to expect:** ±0.1–0.2 mm in XY, ± one layer in Z. Put dimensions that matter in the
  XY plane and holes that must be round upright.
- **Layers are the weak direction.** Across layers a part holds roughly half what it holds along
  them. Turn the part so pulling and bending loads run along the layers.
- **Warping** grows with part length and material shrinkage (ABS, ASA, nylon, PC far more than
  PLA and PETG). Past about 100 mm: round the footprint's corners, avoid thick solid slabs, keep
  wall thickness even, or split the part.
- **First layer:** at least one generous flat face on the bed ✔. No small separate islands on the
  first layer; no detail there (it is squashed). Tall narrow parts ✔ need a wider foot or a brim.

## Resin (MSLA, SLA, DLP)

Printed upside down, hanging from the plate, each layer peeled off a film. Supports are normal;
the design goal is to put them where they do not show and to keep peel forces low.

| Feature | Minimum | Prefer |
| --- | --- | --- |
| Wall, supported on both sides ✔ | 0.4 mm | 1.0 mm; 1.5–2.5 mm for hollow shells and large parts |
| Free-standing wall or fin | 0.6 mm | 1.0 mm+, with a round at its root |
| Overhang ✔ | about 60° from vertical unsupported | support every island and every edge that starts a layer |
| Unsupported flat ledge | 1 mm | none |
| Bridge ✔ | about 5 mm | thicker bridges span further |
| Hole | 0.5 mm | 0.8 mm+; tiny holes fill with resin |
| Embossed detail | 0.1 mm high | 0.3 mm |
| Engraved detail | 0.3 mm wide and deep | 0.4 mm |
| Gap between parts | 0.1–0.2 mm fit, 0.4–0.5 mm moving | – |
| Drain holes in a hollow part ✔ | two, 3 mm+ | 3.5–5 mm, one near the plate, one far from it |

- **Sealed cavities are errors ✔.** They hold liquid resin that later cracks the part. Hollow
  anything bulky (saves resin, lowers peel force) and give every cavity two holes: resin out, air in.
- **Cups** (an open hollow facing the film) trap suction. Tilt the part or add a vent at the top.
- **Avoid big faces parallel to the plate.** Tilt 15–45° so the cross-section changes gradually.
  That trades support marks for reliability; put marks on the side nobody sees.
- **Cross-section:** keep each layer's solid area modest and changing smoothly; sudden jumps leave
  lines and can tear the part off its supports.
- Resin is brittle and creeps. Thin snap fits and threads fail; use tough or ABS-like resin and
  thicker sections for anything that flexes.

## SLS and MJF (powder)

No supports: the powder holds the part. Orientation matters for surface, warping and cost, not
for overhangs, so `print_check.py --process sls` skips support analysis.

| Feature | Minimum | Prefer |
| --- | --- | --- |
| Wall ✔ | 0.7 mm | 1.0–1.5 mm, uniform |
| Hole | 1.5 mm | 2 mm+ |
| Gap between moving parts | 0.3 mm (short) | 0.5 mm+ |
| Embossed or engraved detail | 0.5 mm | 1 mm high or deep |
| Escape holes in a hollow part ✔ | two, 4 mm+ | larger and more for long cavities |

- Sealed cavities stay full of powder ✔. Add escape holes or leave the part solid.
- Large flat plates warp: rib them, or curve them slightly. Avoid thick lumps next to thin walls.
- Bureaus price by bounding volume and height. Nest parts, keep them compact, and join small
  parts with a sprue or put them in a cage so none are lost.
- Chains, hinges and assemblies print in place with 0.5 mm gaps.

## Whatever the process

- One closed, outward-facing shell per part ✔: no open edges, no faces inside, no zero-thickness
  joins. Union overlapping pieces instead of leaving them interpenetrating.
- Millimetres ✔. STL has no unit; a model 1000 × too small or too large is a unit mistake.
- Fits inside the build volume with a few millimetres to spare ✔, or is split into keyed parts.
- Enough triangles that curves look round (flats under about 0.01–0.05 mm from the true curve,
  `pk.segments_for`), not so many that the slicer crawls (over about a million).

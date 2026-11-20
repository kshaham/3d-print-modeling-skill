# Materials and what they change in the design

Pick from what the user has (the saved profile lists it). If the job needs something they do
not have, say so and say why.

## Filament

| Material | Good for | Design consequences |
| --- | --- | --- |
| PLA | display pieces, prototypes, jigs, most indoor parts | stiffest and easiest; bridges and overhangs best (cooling). Brittle, creeps under constant load, softens near 55 °C: not for cars, sun, springs or clips that stay bent |
| PETG | functional parts, outdoor, snap fits, containers | tougher and more flexible than PLA, 70–80 °C. Strings and bridges worse: keep bridges under 20 mm, overhangs at 45°. Sticks hard to smooth beds. Thin walls less crisp |
| ABS / ASA | heat (90–100 °C), outdoor UV (ASA), parts to be solvent-smoothed or glued | shrinks and warps: enclosure needed, round every bed corner, no long thin flat parts, even wall thickness, split large parts. Poor bridging (little cooling) |
| TPU (95A) | grips, seals, bumpers, flexible hinges, tyres | flexes: walls 1.2 mm+ for shape, 0.8 mm for soft. No fine detail, no supports worth removing, strings. Design overhangs out completely. Fits need 0.3–0.5 mm |
| Nylon (PA), PA-CF | gears, hinges, wear parts, tough brackets | strong and slippery but absorbs water and warps like ABS. CF grades are stiff and dimensionally stable but abrasive (hardened nozzle) and weak between layers: orient carefully |
| PC | heat (110 °C+) and impact | hardest to print: enclosure, high temperatures, warps. Keep geometry simple and compact |
| PVA / BVOH | soluble support | only as support interface; see `multicolor.md` |

- **Strength direction** matters most for CF-filled and least for PETG and TPU, whose layers
  bond well.
- **Shrinkage** shifts fits: add about 0.1 mm of clearance for ABS, ASA and nylon over PLA values,
  or print the gauge in `functional-parts.md`.
- **Heat:** a part in a car, near a motor or in sun needs PETG at least, usually ASA or ABS.
- **Food and skin contact, toys for small children, load-bearing safety parts:** say plainly
  that layer lines trap residue and that printed parts are not certified; suggest a coating,
  a liner or a bought part where failure would hurt someone.

## Resin

| Resin | Good for | Design consequences |
| --- | --- | --- |
| Standard | miniatures, display models, fine detail | brittle: thin pegs and blades snap; thicken to 1 mm+ or accept fragility |
| ABS-like / tough | functional small parts, snap features, miniatures that get handled | a little less crisp; still creeps under load |
| Flexible | gaskets, soft grips | supports tear the soft surface; thick sections cure slowly |
| Water-washable | convenience | more brittle, cracks if hollow parts are not fully drained and dried |
| High-temperature, castable, dental | specialist | follow the maker's sheet for wall thickness and supports |

All resin parts: hollow and drain anything bulky, avoid sealed voids, keep large flats off the
plate's parallel, expect ±0.1 mm.

## Powder (SLS, MJF)

PA12 is the default: tough, slightly flexible, about 1.0 g/cm³, grainy surface. PA11 is more
ductile. Glass- or carbon-filled grades are stiffer and more brittle. TPU powder gives rubbery
parts with 1.5 mm minimum walls. No supports in any of them; see `design-rules.md`.

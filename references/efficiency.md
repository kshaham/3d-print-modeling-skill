# Printing efficiently: less support, time, material and failure

A print's cost is the time on the machine, the material used, the work after printing, and the
chance it fails. A failed print costs all of it twice. Work through these in order; compare each
change with numbers from `print_check.py` (mass, rough time, support area) instead of by feel.

## Contents

- 1. Choose the orientation before modeling
- 2. Design the supports out
- 3. Spend material where it works
- 4. Cut time
- 5. Make it print the first time
- 6. Split when one piece fights the process
- 7. Report the saving

## 1. Choose the orientation before modeling

The way up decides supports, strength, surface and time, so decide it first and model for it.
Run `print_orient.py` on a blockout, then weigh its ranking against what the tool cannot know:

- **Load:** layers are the weak direction. A hook, clip or lever is printed lying on its side so
  its layers run along the arm. Pass `--strong-axis` to penalise the weak way up.
- **Visible faces:** the top is the best-looking face, walls show layer lines, the bed face takes
  the bed's texture, and any supported face is scarred. Put supports on the side nobody sees.
- **Accuracy:** round holes and fits are most accurate in the XY plane.
- **Height:** time grows with layer count. Laying a part down usually prints faster.

## 2. Design the supports out

Supports cost material, time, removal work and surface quality. Most can be designed away:

| Problem | Support-free form |
| --- | --- |
| Flat ledge or shelf sticking out | 45° chamfer or gusset under it (`pk.prism` with a 45° triangle) |
| Round hole or tunnel on its side | teardrop or diamond roof (`pk.teardrop`); small holes (≤ 6 mm) can stay round |
| Flat roof over a wide opening | pitched roof (two 45° slopes), arch, or a bridge under 30 mm between two walls |
| Overhang that only needs one end held | give it a second anchor so it becomes a bridge |
| Counterbore facing the bed | one sacrificial layer across the hole (drill it out after), or stepped bridges |
| Round edge on the bed face | chamfer instead; rounds belong on vertical and top edges |
| Sphere or dome resting on the bed | cut a flat on the bottom, or split it into two halves |
| Hanging detail (a nose, a hand, a stalactite) | turn the model, thicken the join to 45°, or make it a separate glued part |
| Text on a wall | engrave it (the top of each groove is a tiny bridge) |
| Letter or logo floating in a window | tie it to the frame with bars |
| Hollow that would trap support | open it toward the top, or split the part through the hollow |

When support cannot be avoided, keep it short, resting on the bed rather than on the model, away
from fits and show faces, and say so in the hand-off (`support_on_model_pct` in the report).

## 3. Spend material where it works

- **Walls carry load, infill mostly holds the roof up.** For strength add perimeters (3–5) before
  infill. 10–20 % gyroid suits most parts; solid infill rarely pays.
- **No thick solid lumps.** Anything over about 10 mm thick becomes a shell with ribs, or gets
  pockets and through-holes that also add perimeters where the stress is. Keep wall thickness even:
  it prints faster, warps less and wastes less.
- **Ribs and gussets beat thickness.** A 2 mm plate with 2 mm ribs is stiffer than a 4 mm plate
  for less plastic. Round or chamfer the rib roots.
- **Open the pockets upward** (or give them 45° roofs) so lightening holes do not need support.
- **Containers and shades:** design for vase mode. One continuous wall exactly one line thick
  (0.45 mm for a 0.4 nozzle, modelled as a solid: the slicer spirals it), no top, slopes within 45°.
- **Resin:** hollow anything bulky with 1.5–2.5 mm walls and two drain holes.

## 4. Cut time

- Lower the part: fewer layers. A model 20 mm tall prints in a third of the time of the same
  volume standing 60 mm tall.
- Match the nozzle and layer to the part. Large plain parts: 0.6 mm nozzle and 0.3 mm layers
  roughly halve the time. Small detailed parts: 0.4 mm nozzle, 0.12–0.16 mm layers only where
  the detail is (variable layer height). Say which in the hand-off.
- Fewer separate islands per layer means fewer travel moves and retractions. Join small posts
  with a web, and put several small parts close together on one plate.
- Features thinner than two lines force slow single-line passes or vanish. Make them two lines.
- Tiny cross-sections near the top (a spike, an antenna) overheat because each layer has no time
  to cool. Print two copies at once, or thicken the tip.

## 5. Make it print the first time

- **Bed contact:** one generous flat face on the bed. Tall and narrow parts get a wider foot,
  built-in brim ears (0.4 mm discs at the corners, cut off later), or are laid down.
- **Warping:** round the footprint's corners, avoid long thin straight edges on the bed in
  shrink-prone materials, keep thickness even.
- **Elephant's foot:** 0.4–0.6 mm chamfer round the bed face of anything that must fit.
- **Mid-air starts:** every low point above the bed needs something under it (`midair_starts` in
  the report). They are the most common cause of spaghetti.
- **Thin tall walls** wobble. Tie them to something with a rib or a round at the base.
- **Check the first layer** on the review board (tile 3): it should be one or a few solid shapes.

## 6. Split when one piece fights the process

Split a model when it does not fit, when no single orientation avoids support, or when two
regions need different strength directions.

- Cut along a flat plane through the widest section so both halves print cut-face down.
- Key the joint: two or more pins and sockets (pin 5 mm, socket +0.2 mm diameter, 0.3 mm short),
  a dovetail, or a step. Pins print better as separate pegs lying down than as upright stubs.
- Hide the seam on an edge, a panel line or a colour change.
- Joining: cyanoacrylate for PLA and PETG, solvent for ABS and ASA, screws or heat-set inserts
  where it must come apart.

## 7. Report the saving

When asked to make a model print better, give the before and after: support area, rough time,
mass, layers and anything that stopped being an error. The numbers come from `print_check.py`;
they are estimates for comparing two versions, and a slicer gives the real ones
(see `slicing.md`).

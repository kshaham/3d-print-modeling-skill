# Colour and multi-material prints

How to build the model depends on how the printer changes colour. The saved profile says which
(`colors`, `color_system`). Read this before modeling anything with more than one colour or material.

## Contents

- One object per colour
- By colour system
- Design rules for colour
- Mixing materials
- Checking and exporting

## One object per colour

Every colour or material is its own closed solid, and no volume belongs to two of them.

```python
body = pk.prism(pk.rounded_rect(50, 20, 3), 3, name="tag")
logo = pk.text("NAME", 8, 0.6, at=(0, 0, 2.4), name="tag-text")   # top 0.6 mm of the plate
pk.cut(body, logo, keep=True)                # pocket in the body, logo kept as its own part
pk.colour(body, "#222222", "black PLA")
pk.colour(logo, "#e9c46a", "sand PLA")
report = pk.check([body, logo])              # parts may touch; each must be closed
pk.export([body, logo], "out/tag", report=report)
```

`pk.export` writes one 3MF in which the coloured objects are the parts of a single object, so
the slicer keeps them together when it arranges the plate (written as separate objects, an
inlay is moved out of its pocket). Each part carries its display colour and a filament number:
distinct colours become filaments 1, 2, 3 in the order the objects are passed. Bambu Studio
opens such a file with the filaments already assigned; the manifest lists them for any other
slicer. STL has no parts: use `--split` for one STL per colour, all sharing the same origin.
Objects without a colour stay separate objects: a plate of loose items.

## By colour system

**Automatic filament changer on one nozzle (AMS, MMU, CFS, ACE and similar).** Every colour
change on a layer purges plastic and takes one to two minutes. The cost is the number of *layers
that contain more than one colour* times the number of changes on each, so:

- Confine colour to as few layers as possible. A flush inlay 0.4–0.6 mm deep on the top face
  changes colour on two or three layers; the same logo embossed through the whole height changes
  on every layer.
- Put the coloured face on the top or on the bed (first-layer inlays are crisp and cost little),
  not up a wall.
- Use few colours per layer: two colours on a layer cost one change, four cost three.
- Many copies on one plate share each purge: batch small coloured parts.
- Tell the user to enable purging into infill or into a waste object for large prints.

**Several nozzles or tools (toolchanger, IDEX, dual nozzle).** Changes are cheap and nearly
waste-free, so colour can run through the full height. The nozzles are aligned to each other
only to about 0.1 mm: avoid hairline features that depend on perfect registration. Idle nozzles
ooze: keep colour regions compact.

**One nozzle, manual swap (pause at a layer).** Colour can only change with height. Design in
bands: base in one colour, then raised text or a rim that starts at a set height. Give the
change heights in the hand-off as layer numbers and millimetres ("change to white at 3.0 mm,
layer 16"). Each height must be a multiple of the layer height. A single object is enough.

**Single colour.** Get contrast from geometry instead: raised or engraved text, textures, or
separately printed parts in other colours that press or glue in (design them as inlays with
0.1–0.15 mm clearance per side).

## Design rules for colour

- Colour features at least two lines wide (0.9 mm with a 0.4 mm nozzle); text strokes 1 mm or
  more, capitals 6 mm or more. Thinner regions are dropped or bleed.
- Top-face inlay depth: 0.4–0.6 mm (two or three layers) hides the colour underneath for most
  filaments; white and yellow over dark need 0.8–1.0 mm.
- Dark next to light bleeds a little: let the dark part own the boundary wall.
- A colour island floating inside another colour is fine on a top face; inside a wall it must
  still be supported by what is under it (the checker treats touching parts as resting on each
  other).
- Keep the pocket: an inlay that merely overlaps the body leaves the slicer to decide which part
  wins. The checker reports overlapping parts.

## Mixing materials

- **Soluble or breakaway support interface** (PVA or BVOH with PLA, PLA under PETG and the
  reverse): lets supported faces come out clean. Worth it only where support is unavoidable.
- **Rigid plus flexible** (PLA or PETG with TPU for grips, seals, hinges): the two must
  interlock mechanically (dovetails, holes the TPU flows through), since adhesion between
  unlike plastics is weak. PETG and TPU bond fairly well; PLA and PETG do not bond.
- Only combine materials that print at similar bed temperatures.
- Each material is its own object, as with colour.

## Checking and exporting

- `print_check.py` on a multi-part file checks each part alone for holes and bad edges, then
  all of them together for orientation, support, walls and size.
- When the parts carry colours it also reports how many layers hold more than one colour and
  roughly how many filament changes that means. Use those two numbers to compare designs: the
  flush 0.6 mm inlay above changes colour on three layers; the same logo through a 20 mm part
  changes on a hundred. It warns when the model uses more colours than the saved profile has,
  and when a manual-swap printer is given colours that share a layer.
- The review board's front, right and top tiles show the parts in their colours. Look for
  slivers, strokes that are too thin and inlays that are not flush.
- `print_slice.py` on the exported 3MF gives the real cost when Bambu Studio is installed: the
  number of filament changes and the time including purging. On a P1S profile a 50 mm tag with
  a 0.6 mm inlay in a second colour sliced at 12 minutes and 3.3 g, against 4 minutes and 2.6 g
  for the plain tag: two filament changes cost eight minutes and 0.7 g.
- Report to the user: how many colours and which filament number each is, how many layers carry
  more than one, and for manual swaps the change heights.

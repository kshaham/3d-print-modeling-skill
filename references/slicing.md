# Hand-off to the slicer

The model is half the print; the other half is settings. Recommend them with the files, and
when a slicer is installed, slice to replace the checker's rough numbers with real ones.

## Contents

- What to hand over
- Real numbers: `print_slice.py`
- Bambu Studio and OrcaSlicer
- PrusaSlicer
- Settings to recommend
- When the print fails

## What to hand over

- `name.3mf` (preferred: carries millimetres, parts and their filaments) and `name.stl` if asked.
- `name.json`, the manifest written by `print_export.py`: size, parts, colours and filament
  numbers, the check summary and the recommended settings.
- The review board PNG.
- A short note: orientation (already applied in the file), supports yes or no and where,
  material, settings that differ from the slicer's defaults, anything to do after printing
  (drill a sacrificial layer, break a joint free, glue order).

## Real numbers: `print_slice.py`

```
python scripts/print_slice.py out/part.3mf                      time, grams, metres, layers
python scripts/print_slice.py out/part.3mf --compare-supports   what supports would cost
python scripts/print_slice.py out/part.3mf --material petg --walls 4 --infill 25 --layer 0.16
python scripts/print_slice.py --which                           slicers found on this machine
```

It finds Bambu Studio, OrcaSlicer or PrusaSlicer in their usual install folders (or the one
saved with `--set-slicer PATH`), prefers the one that belongs to the saved printer, and reads
printer, nozzle and material from the printer profile. It writes the G-code to `sliced/` beside
the model. Plain Python; it does not need Blender.

- Use it before quoting a print time, and to compare two designs or orientations when the
  difference matters. Passing through the slicer's own warnings (for example "floating regions")
  is part of its value: treat them like checker warnings.
- If it reports that no slicer is found, give the checker's estimates, labelled rough, and say
  that installing the slicer on this machine would give real figures. Do not guess a path.
- The checker's own estimate is fitted to a handful of Bambu Studio slices for the P1S and halves
  the speed for older bed-slingers. In those tests it was within about a third of the slicer for
  mass and further off for time; it is for ranking alternatives, not for promises.
- Tested against Bambu Studio 2.9 and PrusaSlicer 2.9 on Windows. OrcaSlicer shares Bambu
  Studio's command line and presets and takes the same path here, but was not tested.

## Bambu Studio and OrcaSlicer

- The tool slices with the slicer's own system presets: the machine preset for the printer and
  nozzle ("Bambu Lab P1S 0.4 nozzle"), the process preset for the layer height ("0.20mm Standard
  @BBL X1C"; pass `--process "0.20mm Strength @BBL X1C"` for another), and the filament preset
  for the material ("Bambu PLA Basic ...", "Bambu PETG Basic ...", else "Generic ..."; override
  with `--filament`). It flattens the presets' inheritance first; the slicers' command lines do
  not, and silently fall back to a 200 mm bed otherwise.
- Build plate defaults to "Textured PEI Plate", which suits every common filament. The Cool
  Plate rejects PETG and others (`--plate` to change).
- **Multi-colour files open ready to print.** `print_export.py` writes a coloured model as one
  object with several parts and records each part's filament number in the form Bambu Studio
  reads: part colours map to filaments 1, 2, 3 in the order the manifest lists. Tell the user
  which AMS slot should hold which colour. `print_slice.py` then reports the colours, the
  filament changes and the time including purging.
- In the app, import the 3MF (drag it onto the plate). This was verified through Bambu Studio's
  command line, not by hand in its window: ask the user to confirm the parts show their colours
  the first time, and if the app asks whether to load the file as one object with several
  parts, the answer is yes.
- Useful app settings to name in the hand-off (Bambu Studio's wording): layer height and the
  process preset, "Wall loops", "Sparse infill density", "Enable support" with type "tree(auto)"
  and "On build plate only", "Brim type", and for multi-colour "Flush into objects' infill".

## PrusaSlicer

`print_slice.py` drives `prusa-slicer-console` with the bed size, nozzle and material from the
printer profile and generic machine limits, which makes its times pessimistic. For times that
match a real machine, export that printer's config from the app (File > Export > Export Config)
and pass it with `--config printer.ini`. Colours are not set up on this route: a multi-part
file is sliced in one filament and the tool says so.

## Settings to recommend

Only state what differs from a standard 0.2 mm profile and why.

| Situation | Setting |
| --- | --- |
| Part carries load | 3–5 walls, 20–30 % gyroid or cubic infill, 5 top and bottom layers |
| Display piece | 2 walls, 10–15 % infill, 0.12–0.16 mm layers, seam aligned at the back |
| Large plain part | 0.6 mm nozzle, 0.3 mm layers, 3 walls, 10 % infill |
| Curved top surfaces | variable layer height, fine on the curve only |
| Small bed contact, tall part, ABS or ASA | brim 5–8 mm, or ears designed in |
| Unavoidable support | tree (organic) support, on build plate only when possible, 0.2 mm top gap; say which faces |
| Bridges over 20 mm | lower bridge speed, full fan; PETG and ABS bridge worse than PLA |
| Vase or shade designed as one wall | spiral vase mode, 3–5 bottom layers, 0 top layers |
| Flexible filament | slow (25–30 mm/s), retraction low, no supports |
| Multi-colour | filaments per part as exported, purge into infill, see `multicolor.md` |
| Resin | tilt and supports as designed, hollow with drain holes as modelled, layer 0.05 mm |

## When the print fails

Map the symptom back to the model before blaming settings:

| Symptom | Likely cause in the model |
| --- | --- |
| Spaghetti from mid-height | a mid-air start or an overhang that lost its support |
| Part came off the bed | too little bed contact, tall and narrow, sharp bed corners that warped |
| Hole too tight, parts will not fit | no hole compensation, no elephant's-foot chamfer, clearance under 0.15 mm |
| Rough, drooping underside | overhang past 45° or a long bridge; add a chamfer or turn the part |
| Thin feature missing | below one line width; thicken to two |
| Snapped along a layer | load across layers; turn the part or add a through-bolt |
| Layer shift or knock-over | tall thin part wobbling; add a rib or print lying down |
| Stringy, blobby colour boundaries | colour regions too thin or too many changes per layer |
| Colour part printed beside the model | the file was loaded as separate objects; re-import as one object, or re-export |

Ask for a photo of the failure and the height at which it started; compare with the review
board at that height (use `--section z=<height>`).

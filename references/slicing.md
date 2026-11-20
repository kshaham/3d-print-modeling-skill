# Hand-off to the slicer

The model is half the print; the other half is settings. Recommend them with the files, and
when a slicer is installed, slice to replace the checker's rough numbers with real ones.

## Contents

- What to hand over
- Settings to recommend
- Slicing from the command line
- When the print fails

## What to hand over

- `name.3mf` (preferred: carries millimetres and separate parts) and `name.stl` if asked.
- `name.json`, the manifest written by `print_export.py`: size, parts and colours, the check
  summary and the recommended settings.
- The review board PNG.
- A short note: orientation (already applied in the file), supports yes or no and where,
  material, settings that differ from the slicer's defaults, anything to do after printing
  (drill a sacrificial layer, break a joint free, glue order).

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
| Multi-colour | assign filaments per part, purge into infill, see `multicolor.md` |
| Resin | tilt and supports as designed, hollow with drain holes as modelled, layer 0.05 mm |

## Slicing from the command line

A slicer gives the true time, filament and support numbers. Look for one before quoting figures:

- PrusaSlicer: `prusa-slicer-console.exe` (Windows), `PrusaSlicer` (macOS app bundle, Linux AppImage)
- OrcaSlicer and Bambu Studio: `orca-slicer`, `bambu-studio` executables in their install folders

PrusaSlicer, with a printer profile exported from the app as `config.ini`:

```
prusa-slicer-console --export-gcode --load config.ini --layer-height 0.2 --fill-density 15% \
  --perimeters 3 --support-material --output out/part.gcode out/part.3mf
```

The end of the G-code holds the results as comments: `; estimated printing time (normal mode)`,
`; filament used [mm]`, `; filament used [g]`. Run it once with and once without
`--support-material` to see what supports cost.

OrcaSlicer and Bambu Studio also slice from the command line, with JSON machine, process and
filament profiles (`--load-settings`, `--load-filaments`, `--slice`, `--export-3mf`).

Flags differ between slicers and versions: run the slicer's `--help` first and do not guess. If
no slicer is installed, give the checker's estimates and label them rough: they are for
comparing two versions of a design, not for quoting a print time.

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

Ask for a photo of the failure and the height at which it started; compare with the review
board at that height (use `--section z=<height>`).

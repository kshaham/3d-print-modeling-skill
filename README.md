# 3d-print-modeling

An agent skill for designing 3D models that print well and efficiently: little or no support,
short print time, less material, correct fits, single or multi-colour. It works for any kind of
model (brackets, enclosures, replacement parts, figurines, miniatures, terrain, props,
print-in-place toys, vases) and for making existing meshes printable (game assets, sculpts,
scans, AI-generated meshes).

The skill asks once for your printer, how many colours it prints and which materials you use,
saves the answers, and never asks again.

![Review board for the template bracket](docs/review-board.png)

## What is inside

| Path | What it is |
| --- | --- |
| `SKILL.md` | the instructions the agent follows |
| `references/` | design rules per process, efficiency, functional parts, multi-colour, materials, converting models, playbooks per model type, slicer hand-off |
| `scripts/print_check.py` | printability gate: closed solid, size, wall thickness, overhangs, bridges, mid-air starts, bed contact, cavities, rough time and mass |
| `scripts/print_orient.py` | ranks the ways a model can sit on the bed |
| `scripts/print_review.py` | renders the eight-tile review board above |
| `scripts/print_export.py` | writes 3MF and binary STL in millimetres, with a manifest |
| `scripts/printkit.py` | helpers for building printable solids from a script |
| `scripts/printer_profile.py` | the saved printer, colours and materials |
| `scripts/blender_run.py` | finds Blender and runs any of the above headless |
| `assets/author_template.py` | a complete example part to copy |

## Requirements

- [Blender](https://www.blender.org/download/) 5.0 or newer (developed on 5.2). No add-ons.
- Python 3.9 or newer to launch it.

## Install

Clone into your agent's skills folder. For Claude Code:

```
git clone https://github.com/kshaham/3d-print-modeling-skill ~/.claude/skills/3d-print-modeling
```

For Codex, clone into `~/.codex/skills/3d-print-modeling`. Then ask for something printable,
for example "design a wall bracket for two M4 screws that prints without support".

## Using the tools directly

```
python scripts/printer_profile.py --set printer="Prusa MK4S" colors=1 materials=PLA,PETG
python scripts/blender_run.py print_check.py model.stl
python scripts/blender_run.py print_orient.py model.stl --top 5
python scripts/blender_run.py print_review.py model.stl review.png
python scripts/blender_run.py assets/author_template.py --review --out out
```

Inputs: `.stl .3mf .obj .ply .glb .gltf .blend`. The time, mass and cost figures are rough
estimates for comparing two versions of a design; slice the model for real numbers.

## Credits

Blender discovery in `scripts/blender_run.py` is adapted from
[EL4CTEO/blender-skills](https://github.com/EL4CTEO/blender-skills) (MIT); see
`THIRD_PARTY_NOTICES.md`.

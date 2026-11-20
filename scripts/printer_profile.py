"""The saved printer profile: which printer, how many colours, which materials.

Asked once, then reused: print_check.py, print_orient.py and print_review.py take their process,
build volume, nozzle and material from it unless a flag overrides them. Plain Python, no Blender.

  python printer_profile.py --show
        prints the profile as JSON, or {"saved": false} when nothing has been saved yet
  python printer_profile.py --set printer="Bambu Lab P1S" colors=4 color_system=AMS materials=PLA,PETG
        naming a known printer fills in process, build volume and nozzle; later values override
  python printer_profile.py --set build=220,220,250 nozzle=0.6 default_material=petg
  python printer_profile.py --printers      list the printers known by name
  python printer_profile.py --clear

Fields
  printer           make and model, as the user said it
  process           fdm | resin | sls
  build             X,Y,Z build volume in mm
  nozzle            mm (fdm)
  colors            how many colours or materials one print can use (1 = single)
  color_system      none | AMS | MMU | toolchanger | IDEX | manual (filament swap at a layer)
  materials         what the user prints with, e.g. PLA,PETG,TPU
  default_material  the one to assume when a job does not say
  layer             usual layer height in mm (optional)
  notes             anything else worth keeping (enclosure, hardened nozzle, bed type)
  blender           path to the Blender executable (set by blender_run.py --set-blender)
  slicer            path to the slicer executable (set by print_slice.py --set-slicer)

Stored at ~/.3d-print-modeling/profile.json, or wherever $PRINT_PROFILE points.
"""
import json
import os
import sys

# name fragments (lower case) -> process, build volume, stock nozzle, colours with the maker's
# multi-material unit. Variants differ: confirm the build volume with the user when unsure.
PRINTERS = {
    "bambu lab a1 mini": ("fdm", (180, 180, 180), 0.4, "AMS lite, 4 colours"),
    "bambu lab a1": ("fdm", (256, 256, 256), 0.4, "AMS lite, 4 colours"),
    "bambu lab p1p": ("fdm", (256, 256, 256), 0.4, "AMS, 4 to 16 colours"),
    "bambu lab p1s": ("fdm", (256, 256, 256), 0.4, "AMS, 4 to 16 colours"),
    "bambu lab x1 carbon": ("fdm", (256, 256, 256), 0.4, "AMS, 4 to 16 colours"),
    "bambu lab x1c": ("fdm", (256, 256, 256), 0.4, "AMS, 4 to 16 colours"),
    "bambu lab h2d": ("fdm", (350, 320, 325), 0.4, "two nozzles plus AMS"),
    "prusa mk3": ("fdm", (250, 210, 210), 0.4, "MMU, 5 colours"),
    "prusa mk4": ("fdm", (250, 210, 220), 0.4, "MMU3, 5 colours"),
    "prusa mini": ("fdm", (180, 180, 180), 0.4, "single"),
    "prusa core one": ("fdm", (250, 220, 270), 0.4, "MMU3, 5 colours"),
    "prusa xl": ("fdm", (360, 360, 360), 0.4, "toolchanger, up to 5 tools"),
    "creality ender 3": ("fdm", (220, 220, 250), 0.4, "single"),
    "creality k1 max": ("fdm", (300, 300, 300), 0.4, "CFS, 4 colours"),
    "creality k1": ("fdm", (220, 220, 250), 0.4, "single"),
    "creality k2 plus": ("fdm", (350, 350, 350), 0.4, "CFS, 4 to 16 colours"),
    "elegoo neptune 4 max": ("fdm", (420, 420, 480), 0.4, "single"),
    "elegoo neptune 4 plus": ("fdm", (320, 320, 385), 0.4, "single"),
    "elegoo neptune 4": ("fdm", (225, 225, 265), 0.4, "single"),
    "anycubic kobra 3": ("fdm", (250, 250, 260), 0.4, "ACE Pro, 4 to 8 colours"),
    "anycubic kobra 2": ("fdm", (220, 220, 250), 0.4, "single"),
    "voron 2.4 350": ("fdm", (350, 350, 340), 0.4, "single"),
    "voron 2.4 300": ("fdm", (300, 300, 290), 0.4, "single"),
    "voron 2.4 250": ("fdm", (250, 250, 240), 0.4, "single"),
    "elegoo saturn 4": ("resin", (218, 122, 220), None, "single"),
    "elegoo mars 5": ("resin", (143, 89, 150), None, "single"),
    "anycubic photon mono m5": ("resin", (218, 123, 200), None, "single"),
    "formlabs form 4": ("resin", (200, 125, 210), None, "single"),
    "formlabs form 3": ("resin", (145, 145, 185), None, "single"),
    "formlabs fuse 1": ("sls", (165, 165, 300), None, "single"),
}
FIELDS = ("printer", "process", "build", "nozzle", "colors", "color_system", "materials",
          "default_material", "layer", "notes", "blender", "slicer")


def path():
    return os.environ.get("PRINT_PROFILE") or os.path.join(os.path.expanduser("~"), ".3d-print-modeling",
                                                           "profile.json")


def load():
    """The saved profile as a dict, or {} when there is none."""
    try:
        with open(path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def lookup(name):
    """Best match for a printer name in PRINTERS, or None."""
    tokens = name.lower().replace("-", " ").replace("+", " ").split()
    makers = {k.split()[0] for k in PRINTERS} | {"lab"}
    said = makers & set(tokens)

    def has(word):                        # "mk4s" matches mk4; a bare number must match exactly
        return any(t == word if word.isdigit() else t.startswith(word) for t in tokens)

    hits = []
    for k in PRINTERS:
        words = k.split()
        if said and not (said & set(words)):
            continue                      # a different maker was named
        if all(has(w) for w in words if w not in makers):
            hits.append(k)
    return max(hits, key=len) if hits else None


def _value(field, text):
    if field == "build":
        vals = [float(x) for x in text.replace("x", ",").split(",")]
        if len(vals) != 3:
            raise ValueError("build needs three numbers: X,Y,Z")
        return vals
    if field in ("nozzle", "layer"):
        return float(text)
    if field == "colors":
        return int(text)
    if field == "materials":
        return [m.strip().lower() for m in text.split(",") if m.strip()]
    if field in ("process", "default_material"):
        return text.strip().lower()
    return text.strip()


def set_fields(pairs):
    prof = load()
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"expected field=value, got {pair!r}")
        field, text = pair.split("=", 1)
        if field not in FIELDS:
            raise ValueError(f"unknown field {field!r}; fields are {', '.join(FIELDS)}")
        prof[field] = _value(field, text)
        if field == "printer":
            hit = lookup(text)
            if hit:
                process, build, nozzle, colour = PRINTERS[hit]
                prof.update(process=process, build=list(build), matched=hit, maker_colour_option=colour)
                if nozzle:
                    prof["nozzle"] = nozzle
            else:
                prof.pop("matched", None)
                prof.pop("maker_colour_option", None)
    if prof.get("process") not in ("fdm", "resin", "sls"):
        prof.setdefault("process", "fdm")
    if prof.get("materials") and not prof.get("default_material"):
        prof["default_material"] = prof["materials"][0]
    os.makedirs(os.path.dirname(path()), exist_ok=True)
    with open(path(), "w", encoding="utf-8") as f:
        json.dump(prof, f, indent=1)
    return prof


def missing(prof):
    """What still has to be asked before the profile is complete."""
    need = [f for f in ("printer", "colors", "materials") if not prof.get(f)]
    if prof and not prof.get("build"):
        need.append("build")
    return need


def main(argv):
    if "--printers" in argv:
        for name, (process, build, nozzle, colour) in PRINTERS.items():
            print(f"{name:<28} {process:<5} {build[0]} x {build[1]} x {build[2]} mm   {colour}")
        return 0
    if "--clear" in argv:
        if os.path.isfile(path()):
            os.remove(path())
        print(json.dumps({"saved": False}))
        return 0
    if "--set" in argv:
        try:
            prof = set_fields(argv[argv.index("--set") + 1:])
        except ValueError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}))
            return 1
    elif "--show" in argv or not argv:
        prof = load()
    else:
        print(__doc__)
        return 1
    out = dict(prof)
    out["saved"] = bool(prof)
    out["missing"] = missing(prof)
    out["file"] = path()
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

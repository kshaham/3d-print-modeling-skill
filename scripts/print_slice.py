"""Slice a model with an installed slicer and report the real print time and filament.

Plain Python (3.9+), no Blender. Supports Bambu Studio, OrcaSlicer and PrusaSlicer. The printer,
nozzle and material come from the saved printer profile unless flags override them.

  python print_slice.py MODEL.3mf                          slice with the printer's own slicer
  python print_slice.py MODEL.stl --supports --material petg --layer 0.16 --walls 3 --infill 20
  python print_slice.py MODEL.3mf --compare-supports       slice twice: without and with supports
  python print_slice.py --which                            the slicers found, first is the default
  python print_slice.py --set-slicer "C:/Program Files/Bambu Studio/bambu-studio.exe"

Options
  --slicer S        auto (default) | bambu | orca | prusa | path to the executable
  --printer NAME    printer to slice for (default: the saved profile's, else Bambu Lab P1S)
  --nozzle MM       --layer MM   --walls N   --infill PCT   --material M
  --supports        turn supports on (default: off, to show what the design needs unaided)
  --process NAME    Bambu/Orca process preset by name or file, e.g. "0.20mm Strength @BBL X1C"
  --filament NAME   Bambu/Orca filament preset by name or file
  --plate NAME      Bambu/Orca build plate (default "Textured PEI Plate"; also "Cool Plate",
                    "Engineering Plate", "High Temp Plate")
  --config FILE     PrusaSlicer config.ini exported from the app (repeatable)
  --out DIR         where the G-code and sliced 3MF go (default: beside the model, in sliced/)
  --json PATH       also write the result here

Bambu Studio and OrcaSlicer are driven with their own system presets for the printer (machine,
process for the layer height, filament for the material), so the time is what that printer's
standard profile gives. PrusaSlicer uses its generic limits unless you pass --config.

Prints a summary and one line starting @@JSON@@. Exit code 2 when no slicer is found, 1 when
slicing fails.
"""
import argparse
import glob
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import printer_profile  # noqa: E402

MARK = "@@JSON@@"
DENSITY = {"pla": 1.24, "petg": 1.27, "abs": 1.04, "asa": 1.07, "tpu": 1.21, "pc": 1.20, "pa": 1.14}
HOME = os.path.expanduser("~")
PLACES = {
    "bambu": {"win32": [r"C:\Program Files\Bambu Studio\bambu-studio.exe"],
              "darwin": ["/Applications/BambuStudio.app/Contents/MacOS/BambuStudio"],
              "linux": ["bambu-studio", os.path.join(HOME, "Applications", "Bambu*Studio*.AppImage"),
                        os.path.join(HOME, "Bambu*Studio*.AppImage")]},
    "orca": {"win32": [r"C:\Program Files\OrcaSlicer\orca-slicer.exe"],
             "darwin": ["/Applications/OrcaSlicer.app/Contents/MacOS/OrcaSlicer"],
             "linux": ["orca-slicer", os.path.join(HOME, "Applications", "OrcaSlicer*.AppImage"),
                       os.path.join(HOME, "OrcaSlicer*.AppImage")]},
    "prusa": {"win32": [r"C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer-console.exe"],
              "darwin": ["/Applications/Original Prusa Drivers/PrusaSlicer.app/Contents/MacOS/PrusaSlicer",
                         "/Applications/PrusaSlicer.app/Contents/MacOS/PrusaSlicer"],
              "linux": ["prusa-slicer", os.path.join(HOME, "Applications", "PrusaSlicer*.AppImage"),
                        os.path.join(HOME, "PrusaSlicer*.AppImage")]},
}


def kind_of(path):
    name = os.path.basename(path).lower()
    return "bambu" if "bambu" in name else "orca" if "orca" in name else "prusa" if "prusa" in name else None


def find_slicers(printer=""):
    """[(kind, path)] in order of preference for this printer."""
    plat = "win32" if sys.platform == "win32" else "darwin" if sys.platform == "darwin" else "linux"
    found = []
    for cand in (os.environ.get("PRINT_SLICER"), printer_profile.load().get("slicer")):
        if cand and os.path.isfile(cand) and kind_of(cand):
            found.append((kind_of(cand), cand))
    p = printer.lower()
    order = ["bambu", "orca", "prusa"] if "bambu" in p else ["prusa", "orca", "bambu"] if "prusa" in p \
        else ["orca", "bambu", "prusa"]
    for kind in order:
        for pat in PLACES[kind][plat]:
            hits = [h for h in glob.glob(pat) if os.path.isfile(h)] if os.path.isabs(pat) else \
                ([shutil.which(pat)] if shutil.which(pat) else [])
            for h in hits:
                if (kind, h) not in found:
                    found.append((kind, h))
    return found


# ------------------------------------------------------------------------ Bambu Studio, OrcaSlicer

def profile_root(exe):
    base = os.path.dirname(os.path.abspath(exe))
    for cand in (os.path.join(base, "resources", "profiles"),
                 os.path.join(base, "..", "Resources", "profiles"),          # macOS bundle
                 os.path.join(base, "..", "share", "BambuStudio", "profiles"),
                 os.path.join(base, "..", "share", "OrcaSlicer", "profiles")):
        if os.path.isdir(cand):
            return os.path.normpath(cand)
    return None


class Presets:
    """A vendor's system presets, with `inherits` chains flattened (the command line does not
    resolve them: an unflattened machine preset slices for a 200 mm bed)."""

    def __init__(self, vendor_dir):
        self.dir = vendor_dir
        self.cache = {}

    def load(self, sub, name):
        key = (sub, name)
        if key not in self.cache:
            path = name if os.path.isfile(name) else os.path.join(self.dir, sub, name + ".json")
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            parent = data.get("inherits")
            if parent and os.path.isfile(os.path.join(self.dir, sub, parent + ".json")):
                merged = dict(self.load(sub, parent))
                merged.update(data)
                data = merged
            data["inherits"] = ""
            self.cache[key] = data
        return self.cache[key]

    def names(self, sub):
        return sorted(os.path.splitext(f)[0] for f in os.listdir(os.path.join(self.dir, sub))
                      if f.endswith(".json"))


def pick_machine(root, printer, nozzle):
    """(Presets, machine preset name) for a printer name such as "Bambu Lab P1S"."""
    want = " ".join(printer.lower().split())
    tag = f"{nozzle:g} nozzle"
    best = None
    for vendor in sorted(os.listdir(root)):
        mdir = os.path.join(root, vendor, "machine")
        if not os.path.isdir(mdir):
            continue
        for f in os.listdir(mdir):
            name = os.path.splitext(f)[0]
            low = name.lower()
            if not f.endswith(".json") or "template" in low or tag not in low:
                continue
            model = low.replace(tag, "").strip()
            if model == want or all(w in model.split() for w in want.split() if w not in ("lab", "labs")):
                score = (model == want, -len(model))
                if best is None or score > best[0]:
                    best = (score, vendor, name)
    if not best:
        return None, None
    return Presets(os.path.join(root, best[1])), best[2]


def _compatible(preset, machine):
    return machine in (preset.get("compatible_printers") or [])


def pick_process(presets, machine, layer, wanted=None):
    if wanted:
        return wanted
    prefix = f"{layer:.2f}mm"
    names = [n for n in presets.names("process") if n.startswith(prefix)]
    names = [n for n in names if _compatible(presets.load("process", n), machine)]
    for word in ("Standard", "Optimal", "Fine", "Draft", ""):
        for n in names:
            if word in n:
                return n
    return None


def pick_filament(presets, machine, material, wanted=None):
    if wanted:
        return wanted
    mat = material.upper()
    token = {"PA": "PA", "TPU": "TPU"}.get(mat, mat)
    names = [n for n in presets.names("filament") if token in n.upper()]
    good = []
    for n in names:
        p = presets.load("filament", n)
        kind = p.get("filament_type")
        kind = kind[0] if isinstance(kind, list) and kind else kind
        if _compatible(p, machine) and str(kind).upper().startswith(mat):
            good.append(n)
    for start in (f"Bambu {mat} Basic", f"Generic {mat}", f"Bambu {mat}", ""):
        hits = sorted((n for n in good if n.startswith(start)), key=len)
        if hits:
            return hits[0]
    return None


def colours_in(model):
    """Display colours of the filaments a 3MF asks for, in filament order ([] for one filament)."""
    if not model.lower().endswith(".3mf"):
        return []
    try:
        with zipfile.ZipFile(model) as z:
            names = z.namelist()
            main = next((n for n in names if n.lower() == "3d/3dmodel.model"), None)
            text = z.read(main).decode("utf-8", "replace") if main else ""
            cfg = z.read("Metadata/model_settings.config").decode("utf-8", "replace") \
                if "Metadata/model_settings.config" in names else ""
    except (OSError, zipfile.BadZipFile):
        return []
    shades = re.findall(r'<base [^>]*displaycolor="(#[0-9A-Fa-f]{6})', text)
    slots = [int(x) for x in re.findall(r'key="extruder" value="(\d+)"', cfg)]
    count = max(slots + [len(shades)]) if (slots or shades) else 0
    if count < 2:
        return []
    return [(shades[i] if i < len(shades) else "#808080") for i in range(count)]


def slice_bbl(kind, exe, model, a, out_dir, supports):
    root = profile_root(exe)
    if not root:
        return {"ok": False, "error": f"no presets found beside {exe}"}
    presets, machine = pick_machine(root, a.printer, a.nozzle)
    if not machine:
        return {"ok": False, "error": f"{os.path.basename(exe)} has no preset for {a.printer!r} with a "
                                      f"{a.nozzle:g} mm nozzle; pass --printer with the name the slicer uses"}
    process = pick_process(presets, machine, a.layer, a.process)
    filament = pick_filament(presets, machine, a.material, a.filament)
    if not process or not filament:
        return {"ok": False, "error": f"no {'process' if not process else 'filament'} preset for {machine} "
                                      f"({a.layer} mm, {a.material}); pass --process / --filament"}
    tmp = tempfile.mkdtemp(prefix="print_slice_")
    shades = colours_in(model)
    try:
        files = {}
        loads = []
        for n, shade in enumerate(shades or [None], 1):                 # one filament preset per colour
            data = dict(presets.load("filament", filament))
            if shade:
                data["filament_colour"] = [shade]
            loads.append(os.path.join(tmp, f"filament{n}.json"))
            with open(loads[-1], "w", encoding="utf-8") as f:
                json.dump(data, f)
        for sub, name in (("machine", machine), ("process", process)):
            data = dict(presets.load(sub, name))
            if sub == "process":
                data["layer_height"] = f"{a.layer:g}"
                if a.walls is not None:
                    data["wall_loops"] = str(a.walls)
                if a.infill is not None:
                    data["sparse_infill_density"] = f"{a.infill:g}%"
                data["enable_support"] = "1" if supports else "0"
                data["curr_bed_type"] = a.plate
            files[sub] = os.path.join(tmp, sub + ".json")
            with open(files[sub], "w", encoding="utf-8") as f:
                json.dump(data, f)
        result = os.path.join(out_dir, "result.json")
        if os.path.isfile(result):
            os.remove(result)
        name = os.path.splitext(os.path.basename(model))[0] + ("-supports" if supports else "")
        cmd = [exe, "--debug", "1", "--load-settings", files["machine"] + ";" + files["process"],
               "--load-filaments", ";".join(loads), "--arrange", "1", "--slice", "0",
               "--outputdir", out_dir, "--export-3mf", name + ".sliced.3mf", model]
        proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=1800)
        if not os.path.isfile(result):
            return {"ok": False, "error": f"{os.path.basename(exe)} wrote no result (exit {proc.returncode})",
                    "log": (proc.stdout + proc.stderr)[-600:]}
        with open(result, encoding="utf-8") as f:
            res = json.load(f)
        if res.get("return_code", 1) != 0:
            return {"ok": False, "error": res.get("error_string", "slicing failed")}
        gcode = os.path.join(out_dir, "plate_1.gcode")
        head = ""
        if os.path.isfile(gcode):
            with open(gcode, encoding="utf-8", errors="replace") as f:
                head = f.read(4000)
            final = os.path.join(out_dir, name + ".gcode")
            os.replace(gcode, final)
            gcode = final
        plate = (res.get("sliced_plates") or [{}])[0]
        length = float((re.search(r"total filament length \[mm\] : ([0-9.]+)", head) or [0, 0])[1])
        layers = int((re.search(r"total layer number: (\d+)", head) or [0, 0])[1])
        dia = 1.75
        fil = presets.load("filament", filament)
        dens = fil.get("filament_density")
        dens = float(dens[0] if isinstance(dens, list) else dens or 0) or DENSITY.get(a.material, 1.24)
        cm3 = length * math.pi * (dia / 2.0) ** 2 / 1000.0
        return {"ok": True, "slicer": kind, "machine": machine, "process": process, "filament": filament,
                "supports": supports, "time_s": round(float(plate.get("total_predication") or 0)),
                "filament_m": round(length / 1000.0, 2), "filament_cm3": round(cm3, 2),
                "filament_g": round(cm3 * dens, 1), "layers": layers,
                "colours": len(shades) or 1,
                "filament_changes": plate.get("filament_change_times", 0),
                "warning": plate.get("warning_message") or "",
                "gcode": gcode, "sliced_3mf": os.path.join(out_dir, name + ".sliced.3mf")}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------------------------ PrusaSlicer

def _seconds(text):
    total = 0
    for value, unit in re.findall(r"(\d+)\s*([dhms])", text):
        total += int(value) * {"d": 86400, "h": 3600, "m": 60, "s": 1}[unit]
    return total


def slice_prusa(exe, model, a, out_dir, supports):
    bx, by, bz = a.build
    name = os.path.splitext(os.path.basename(model))[0] + ("-supports" if supports else "")
    gcode = os.path.join(out_dir, name + ".gcode")
    dens = DENSITY.get(a.material, 1.24)
    cmd = [exe, "--export-gcode"]
    for cfg in a.config or []:
        cmd += ["--load", cfg]
    if not a.config:
        cmd += ["--bed-shape", f"0x0,{bx:g}x0,{bx:g}x{by:g},0x{by:g}", "--max-print-height", f"{bz:g}",
                "--nozzle-diameter", f"{a.nozzle:g}", "--filament-type", a.material.upper()]
    cmd += ["--filament-density", f"{dens:g}", "--center", f"{bx / 2:g},{by / 2:g}",
            "--layer-height", f"{a.layer:g}"]
    if a.walls is not None:
        cmd += ["--perimeters", str(a.walls)]
    if a.infill is not None:
        cmd += ["--fill-density", f"{a.infill:g}%"]
    if supports:
        cmd += ["--support-material"]
    cmd += ["--output", gcode, model]
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=1800)
    if proc.returncode != 0 or not os.path.isfile(gcode):
        return {"ok": False, "error": (proc.stdout + proc.stderr).strip().splitlines()[-1:] or "slicing failed"}
    with open(gcode, encoding="utf-8", errors="replace") as f:
        text = f.read()
    tail = text[-20000:]

    def num(pattern):
        m = re.search(pattern, tail)
        return float(m.group(1)) if m else 0.0

    t = re.search(r"estimated printing time \(normal mode\) = (.+)", tail)
    cm3 = num(r"filament used \[cm3\] = ([0-9.]+)")
    note = "sliced in one filament: the PrusaSlicer route here does not set up several" \
        if colours_in(model) else ""
    return {"ok": True, "slicer": "prusa", "machine": "generic limits" if not a.config else "from --config",
            "supports": supports, "time_s": _seconds(t.group(1)) if t else 0,
            "filament_m": round(num(r"filament used \[mm\] = ([0-9.]+)") / 1000.0, 2),
            "filament_cm3": round(cm3, 2), "filament_g": round(cm3 * dens, 1),
            "layers": text.count(";LAYER_CHANGE"), "filament_changes": 0, "warning": note, "gcode": gcode}


# ------------------------------------------------------------------------------------------- main

def clock(seconds):
    h, m = divmod(round(seconds / 60.0), 60)
    return f"{h} h {m:02d} min" if h else f"{m} min"


def line(res):
    if not res.get("ok"):
        return f"SLICE FAILED  {res.get('error')}"
    extra = f"  {res.get('colours', 1)} colours, {res['filament_changes']} filament changes" \
        if res.get("filament_changes") else ""
    return (f"{'with supports' if res['supports'] else 'no supports  '}  {clock(res['time_s'])}  "
            f"{res['filament_g']} g  {res['filament_m']} m  {res['layers']} layers{extra}")


def main(argv):
    p = argparse.ArgumentParser(prog="print_slice.py", description=__doc__.split("\n")[0])
    p.add_argument("model", nargs="?")
    p.add_argument("--slicer", default="auto")
    p.add_argument("--printer")
    p.add_argument("--nozzle", type=float)
    p.add_argument("--layer", type=float)
    p.add_argument("--walls", type=int)
    p.add_argument("--infill", type=float)
    p.add_argument("--material")
    p.add_argument("--supports", action="store_true")
    p.add_argument("--compare-supports", action="store_true")
    p.add_argument("--process")
    p.add_argument("--filament")
    p.add_argument("--plate", default="Textured PEI Plate")
    p.add_argument("--config", action="append")
    p.add_argument("--out")
    p.add_argument("--json")
    p.add_argument("--which", action="store_true")
    p.add_argument("--set-slicer")
    a = p.parse_args(argv)
    prof = printer_profile.load()
    if a.set_slicer:
        if not os.path.isfile(a.set_slicer) or not kind_of(a.set_slicer):
            print("not a Bambu Studio, OrcaSlicer or PrusaSlicer executable:", a.set_slicer)
            return 1
        printer_profile.set_fields([f"slicer={os.path.abspath(a.set_slicer)}"])
        print("saved", os.path.abspath(a.set_slicer))
        return 0
    a.printer = a.printer or prof.get("printer") or "Bambu Lab P1S"
    a.nozzle = a.nozzle or prof.get("nozzle") or 0.4
    a.layer = a.layer or prof.get("layer") or 0.2
    a.material = (a.material or prof.get("default_material") or "pla").lower()
    a.build = prof.get("build") or [256.0, 256.0, 256.0]
    slicers = find_slicers(a.printer)
    if a.slicer != "auto":
        slicers = [(kind_of(a.slicer), a.slicer)] if os.path.isfile(a.slicer) else \
            [s for s in slicers if s[0] == a.slicer]
    if a.which:
        for kind, path in slicers:
            print(kind, path)
        if not slicers:
            print("no slicer found")
        return 0 if slicers else 2
    if not slicers:
        print("No slicer found. Install Bambu Studio, OrcaSlicer or PrusaSlicer, or point to one:\n"
              "  python print_slice.py --set-slicer /path/to/slicer")
        print(MARK + json.dumps({"ok": False, "error": "no slicer found"}))
        return 2
    if not a.model or not os.path.isfile(a.model):
        print(__doc__ if not a.model else f"no such file: {a.model}")
        return 1
    kind, exe = slicers[0]
    model = os.path.abspath(a.model)
    out_dir = os.path.abspath(a.out or os.path.join(os.path.dirname(model), "sliced"))
    os.makedirs(out_dir, exist_ok=True)
    runs = []
    for supports in ([False, True] if a.compare_supports else [a.supports]):
        res = slice_prusa(exe, model, a, out_dir, supports) if kind == "prusa" else \
            slice_bbl(kind, exe, model, a, out_dir, supports)
        runs.append(res)
    first = runs[0]
    if first.get("ok"):
        print(f"SLICED  {os.path.basename(model)}  with {os.path.basename(exe)} for "
              f"{first.get('machine')}, {first.get('process', str(a.layer) + ' mm')}, "
              f"{first.get('filament', a.material)}")
    for res in runs:
        print("  " + line(res))
        if res.get("warning"):
            print("  slicer warning:", res["warning"])
    if len(runs) == 2 and all(r.get("ok") for r in runs):
        dt, dg = runs[1]["time_s"] - runs[0]["time_s"], runs[1]["filament_g"] - runs[0]["filament_g"]
        print(f"  supports cost {clock(max(dt, 0))} and {max(dg, 0):.1f} g")
    out = {"ok": all(r.get("ok") for r in runs), "runs": runs}
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
    print(MARK + json.dumps(out, separators=(",", ":")))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

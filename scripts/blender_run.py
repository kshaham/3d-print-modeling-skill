"""Run one of this skill's scripts, or your own author script, in headless Blender.

Plain Python (3.9+). Finds Blender, hides its start-up noise, and passes the exit code through.

  python blender_run.py print_check.py MODEL.stl --nozzle 0.6
  python blender_run.py print_review.py MODEL.stl review.png
  python blender_run.py --blend scene.blend print_check.py --objects Body
  python blender_run.py path/to/author_part.py --review
  python blender_run.py --json print_check.py MODEL.stl     only the JSON report line
  python blender_run.py --which                             the Blender it would use
  python blender_run.py --set-blender "C:/path/to/blender.exe"   remember a Blender for next time

A script name without a folder is looked up in this folder first. Everything after the script
name goes to the script. Author scripts can import the helpers with:
  import os, sys; sys.path.insert(0, os.environ["PRINT_SKILL_SCRIPTS"]); import printkit as pk

Blender is found in this order: $BLENDER_EXE, the path saved with --set-blender, PATH, the
standard install folders (newest version wins). Blender 5.0 or newer is expected.
Exit code: the script's own (print_check.py: 1 when the model fails), 2 when Blender is missing.
"""
import glob
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import printer_profile  # noqa: E402

MARK = "@@JSON@@"
NOISE = ("Blender ", "Read prefs", "Read blend", "Blender quit", "Color management", "Saved: ",
         "Time: ", "Fra:", "Timer ", " Time: ", "Info: Saved", "Import finished", "Data are loaded")
LOG = re.compile(r"^[0-9]+:[0-9]+[.:][0-9]+ +([a-z_]+ +)?[|]")    # Blender's and importers' log lines


def _version(path):
    m = re.search(r"(\d+)\.(\d+)", path)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def find_blender():
    # adapted from EL4CTEO/blender-skills (MIT); see THIRD_PARTY_NOTICES.md
    for cand in (os.environ.get("BLENDER_EXE"), printer_profile.load().get("blender")):
        if cand and os.path.isfile(cand):
            return cand
    hit = shutil.which("blender")
    if hit:
        return hit
    home = os.path.expanduser("~")
    patterns = {
        "win32": [r"C:\Program Files\Blender Foundation\Blender *\blender.exe",
                  os.path.expandvars(r"%LOCALAPPDATA%\Programs\Blender Foundation\Blender *\blender.exe"),
                  r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe",
                  os.path.join(home, "Documents", "*", "blender-*", "blender.exe"),
                  os.path.join(home, "Downloads", "blender-*", "blender.exe")],
        "darwin": ["/Applications/Blender*.app/Contents/MacOS/Blender",
                   os.path.join(home, "Applications/Blender*.app/Contents/MacOS/Blender")],
    }.get(sys.platform, ["/usr/bin/blender", "/opt/blender*/blender", "/snap/bin/blender",
                         os.path.join(home, "blender*/blender")])
    found = [p for pat in patterns for p in glob.glob(pat) if os.path.isfile(p)]
    return max(found, key=_version) if found else None


def main(argv):
    json_only = "--json" in argv[:3]
    if json_only:
        argv = [a for i, a in enumerate(argv) if not (a == "--json" and i < 3)]
    if argv[:1] == ["--set-blender"]:
        if len(argv) < 2 or not os.path.isfile(argv[1]):
            print("no such file" if len(argv) > 1 else "give the path to the Blender executable")
            return 1
        printer_profile.set_fields([f"blender={os.path.abspath(argv[1])}"])
        print("saved", os.path.abspath(argv[1]))
        return 0
    exe = find_blender()
    if argv[:1] == ["--which"]:
        print(exe or "Blender not found: install Blender 5 or run --set-blender PATH")
        return 0 if exe else 2
    if not exe:
        print("Blender not found. Install Blender 5.x, or tell me where it is:\n"
              "  python blender_run.py --set-blender /path/to/blender")
        return 2
    blend = None
    if argv[:1] == ["--blend"]:
        blend, argv = argv[1], argv[2:]
    if not argv or not argv[0].endswith(".py"):
        print(__doc__)
        return 1
    script, rest = argv[0], argv[1:]
    if not os.path.isfile(script) and os.path.isfile(os.path.join(HERE, script)):
        script = os.path.join(HERE, script)
    if not os.path.isfile(script):
        print(f"no such script: {script}")
        return 1
    cmd = [exe, "--background", "--factory-startup"]
    if blend:
        cmd.append(blend)
    cmd += ["--python-exit-code", "1", "--python", script, "--"] + rest
    env = dict(os.environ, PRINT_SKILL_SCRIPTS=HERE, PYTHONIOENCODING="utf-8")
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    shown = 0
    for line in proc.stdout.splitlines():
        if line.startswith(MARK):
            if json_only:
                print(line[len(MARK):])
                shown += 1
            continue
        if json_only or not line.strip() or line.startswith(NOISE) or LOG.match(line):
            continue
        print(line)
        shown += 1
    if proc.returncode != 0 and (not shown or "Traceback" in proc.stderr):
        tail = [ln for ln in proc.stderr.strip().splitlines() if not LOG.match(ln)][-15:]
        print("\n".join(tail))
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

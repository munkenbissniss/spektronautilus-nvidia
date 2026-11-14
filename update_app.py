#!/usr/bin/env python3
"""Optional, for whoever maintains both projects: copies a newer website and Linux launcher into app/ from a checkout of the main
Spektronautilus repository (run its build.py first). This repository works on its own without it.
   python3 update_app.py /path/to/spektronautilus"""
import shutil, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; APP = HERE / "app"
if len(sys.argv) != 2: sys.exit(__doc__)
MAIN = Path(sys.argv[1]).resolve()
for need in ("docs/index.html", "linux/spektronautilus.py", "linux/spektronautilus.svg"):
    if not (MAIN / need).exists(): sys.exit(f"Not found: {MAIN / need}")
if "comfyReady" not in (MAIN / "docs/tools/app/steps.js").read_text(encoding="utf-8"): sys.exit("That website does not know ReCaVSR yet (too old).")
shutil.rmtree(APP / "docs", ignore_errors=True)
shutil.copytree(MAIN / "docs", APP / "docs", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
for f in ("spektronautilus.py", "spektronautilus.svg"): shutil.copy2(MAIN / "linux" / f, APP / f)
print("app/ updated from", MAIN)

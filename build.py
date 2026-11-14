#!/usr/bin/env python3
"""Builds dist/spektronautilus-nvidia.tar.gz from this repository alone: app/ (the website, the Linux launcher and the NVIDIA part),
the installer, README and LICENSE. No other repository is needed."""
import shutil, sys, tarfile, tempfile
from pathlib import Path
HERE = Path(__file__).resolve().parent; APP = HERE / "app"
for need in ("docs/index.html", "docs/tools/hospital/index.html", "spektronautilus.py", "spektronautilus.svg", "spektronautilus_nvidia.py"):
    if not (APP / need).exists(): sys.exit(f"Missing: app/{need}")
tmp = Path(tempfile.mkdtemp()) / "spektronautilus-nvidia"; tmp.mkdir()
shutil.copytree(APP, tmp / "app", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
for f in ("install.sh", "uninstall.sh", "README.md", "LICENSE"): shutil.copy2(HERE / f, tmp / f)
for f in ("install.sh", "uninstall.sh", "app/spektronautilus_nvidia.py", "app/spektronautilus.py"): (tmp / f).chmod(0o755)
out = HERE / "dist" / "spektronautilus-nvidia.tar.gz"; out.parent.mkdir(exist_ok=True)
with tarfile.open(out, "w:gz") as t: t.add(tmp, arcname="spektronautilus-nvidia")
shutil.rmtree(tmp.parent)
print(f"built {out} {out.stat().st_size // 1024} kB")

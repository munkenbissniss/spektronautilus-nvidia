#!/usr/bin/env bash
# Spektronautilus NVIDIA: installs Spektronautilus, ComfyUI, the ReCaVSR nodes and the ReCaVSR model (int8, 6.3 GB) for your user.
# For Ubuntu (and Pop!_OS) with an NVIDIA graphics card, RTX 20 series or newer (RTX 30 or newer for the fast kernels).
# Run it again to update. Nothing is installed system-wide, except the packages it asks you to install with apt.
#   ./install.sh            normal install
#   ./install.sh --yes      do not ask (accepts the model download, see the licence note below)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="${XDG_DATA_HOME:-$HOME/.local/share}/spektronautilus-nvidia"
BIN="$HOME/.local/bin"; APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
YES=0; [ "${1:-}" = "--yes" ] && YES=1
say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
die() { printf '\n\033[31mStopped: %s\033[0m\n' "$*"; exit 1; }
ask() { [ $YES = 1 ] && return 0; read -r -p "$1 [y/N] " a; [ "$a" = y ] || [ "$a" = Y ] || [ "$a" = j ] || [ "$a" = J ]; }

say "Checking this computer"
command -v nvidia-smi >/dev/null || die "No NVIDIA driver found (nvidia-smi). Install it first: sudo ubuntu-drivers install   (then restart)"
GPU="$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | head -1)"; echo "Graphics card: $GPU"
CUDA="$(nvidia-smi | sed -n 's/.*CUDA Version: *\([0-9]*\.[0-9]*\).*/\1/p' | head -1)"; echo "The driver supports CUDA $CUDA"
[ -n "$CUDA" ] || die "Could not read the CUDA version from nvidia-smi."
MISSING=""
for c in git python3 ffmpeg; do command -v $c >/dev/null || MISSING="$MISSING $c"; done
python3 -c "import venv, ensurepip" 2>/dev/null || MISSING="$MISSING python3-venv"
python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" || die "Python 3.10 or newer is needed."
[ -z "$MISSING" ] || die "Please install:$MISSING   ->   sudo apt install$MISSING"
mkdir -p "$DEST"
FREE=$(df -Pk "$DEST" | awk 'NR==2{print int($4/1048576)}'); echo "Free disk: $FREE GB"
[ "$FREE" -ge 22 ] || [ -d "$DEST/ComfyUI/models/recavsr" ] || die "About 22 GB of free disk is needed (Python packages about 12 GB, the model 6.5 GB)."
RAM=$(awk '/MemTotal/{print int($2/1048576+0.5)}' /proc/meminfo); echo "Memory: $RAM GB"
[ "$RAM" -ge 15 ] || echo "Note: less than 16 GB memory. ReCaVSR may be slow or stop. Close other programs while it runs."

say "Spektronautilus"
[ -f "$HERE/app/spektronautilus.py" ] || die "The app folder is missing. Use the package made by build.py (dist/spektronautilus-nvidia.tar.gz)."
rm -rf "$DEST/app"; cp -r "$HERE/app" "$DEST/app"
cp "$HERE/uninstall.sh" "$DEST/"; chmod +x "$DEST/app/spektronautilus_nvidia.py" "$DEST/uninstall.sh"

say "ComfyUI"
if [ -d "$DEST/ComfyUI" ] && [ ! -d "$DEST/ComfyUI/.git" ]; then   # left by "uninstall.sh --keep-model": keep the model, get ComfyUI again
  mv "$DEST/ComfyUI" "$DEST/ComfyUI.keep"
fi
if [ -d "$DEST/ComfyUI/.git" ]; then git -C "$DEST/ComfyUI" fetch -q --tags; else git clone -q https://github.com/comfyanonymous/ComfyUI "$DEST/ComfyUI"; git -C "$DEST/ComfyUI" fetch -q --tags; fi
if [ -d "$DEST/ComfyUI.keep/models/recavsr" ]; then mkdir -p "$DEST/ComfyUI/models"; rm -rf "$DEST/ComfyUI/models/recavsr"; mv "$DEST/ComfyUI.keep/models/recavsr" "$DEST/ComfyUI/models/"; fi
rm -rf "$DEST/ComfyUI.keep"
TAG="$(git -C "$DEST/ComfyUI" tag -l 'v*' --sort=-v:refname | head -1)"
if [ -n "$TAG" ]; then git -C "$DEST/ComfyUI" -c advice.detachedHead=false checkout -q "$TAG"; echo "ComfyUI $TAG (the newest release)"; fi

say "Python packages (PyTorch for CUDA $CUDA). This downloads several GB the first time."
[ -x "$DEST/venv/bin/python" ] || python3 -m venv "$DEST/venv"
PY="$DEST/venv/bin/python"; PIP="$PY -m pip"
$PIP install -q --upgrade pip wheel
cuda_ok() { "$PY" -c "import torch, sys; sys.exit(0 if torch.cuda.is_available() else 1)" 2>/dev/null; }
if ! cuda_ok; then
  MAJ=${CUDA%%.*}; MIN=${CUDA#*.}; V=$((MAJ * 10 + MIN)); TRIED=""
  for idx in cu132 cu130 cu129 cu128 cu126; do   # the newest that this driver can run
    n=${idx#cu}; [ "$n" -le "$V" ] || continue
    echo "Trying PyTorch for $idx…"; TRIED="$TRIED $idx"
    if $PIP install -q --upgrade torch torchvision torchaudio --index-url "https://download.pytorch.org/whl/$idx" && cuda_ok; then break; fi
  done
  cuda_ok || die "PyTorch could not use the graphics card (tried:$TRIED). Update the NVIDIA driver (sudo ubuntu-drivers install), restart, and run install.sh again."
fi
"$PY" -c "import torch; print('PyTorch', torch.__version__, 'sees', torch.cuda.get_device_name(0))"
$PIP install -q -r "$DEST/ComfyUI/requirements.txt"

say "ReCaVSR nodes"
N="$DEST/ComfyUI/custom_nodes/ComfyUI-ReCaVSR"
if [ -d "$N/.git" ]; then git -C "$N" pull -q --ff-only; else git clone -q https://github.com/PedroMarinhoDev/ComfyUI-ReCaVSR "$N"; fi
$PIP install -q -r "$N/requirements.txt"

say "ReCaVSR model"
M="$DEST/ComfyUI/models/recavsr"; mkdir -p "$M"
if [ ! -f "$M/transformer_int8_convrot.safetensors" ] || [ ! -f "$M/flashdecoder.safetensors" ] || [ ! -f "$M/prompt.safetensors" ]; then
  echo "The model files come from Hugging Face (kopper/ReCaVSR and PedroMarinhoDev/ReCaVSR-ComfyUI), about 6.5 GB."
  echo "Their makers state no licence for the model weights. They are downloaded to this computer for your own use; Spektronautilus does not include or share them."
  ask "Download the model now?" || die "The model is needed for AI video upscaling. Run install.sh again when you are ready."
  $PIP install -q --upgrade "huggingface_hub[cli]"
  HF="$DEST/venv/bin/hf"
  "$HF" download kopper/ReCaVSR prompt.safetensors flashdecoder.safetensors --local-dir "$M"
  "$HF" download PedroMarinhoDev/ReCaVSR-ComfyUI recavsr/transformer_int8_convrot.safetensors --local-dir "$DEST/ComfyUI/models"
fi
ls -la "$M" | sed -n '2,10p'

say "Menu entry"
mkdir -p "$BIN" "$APPS"
ln -sf "$DEST/app/spektronautilus_nvidia.py" "$BIN/spektronautilus-nvidia"
cat > "$APPS/spektronautilus-nvidia.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Spektronautilus NVIDIA
GenericName=VJ and video mixer with AI video upscaling
Comment=Loop Hospital with ReCaVSR on your NVIDIA card
Exec=python3 "$DEST/app/spektronautilus_nvidia.py"
Icon=$DEST/app/spektronautilus.svg
Terminal=false
Categories=AudioVideo;Video;
Actions=hospital;

[Desktop Action hospital]
Name=Loop Hospital
Exec=python3 "$DEST/app/spektronautilus_nvidia.py" --path tools/hospital/
DESK
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" 2>/dev/null || true

say "Done"
echo "Start it from your application menu (Spektronautilus NVIDIA), or type:  spektronautilus-nvidia"
echo "ComfyUI starts in the background with it (the first start takes up to a minute). Its log: $DEST/comfyui.log"
echo "In the Loop Hospital, choose Upscale -> AI video (ReCaVSR)."

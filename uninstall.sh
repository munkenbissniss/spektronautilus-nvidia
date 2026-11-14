#!/bin/sh
# Removes Spektronautilus NVIDIA: the program, ComfyUI, its Python packages and the menu entry.
#   ./uninstall.sh                 everything, also the ReCaVSR model (6.5 GB)
#   ./uninstall.sh --keep-model    keeps ComfyUI/models/recavsr, so a new install does not download it again
DEST="${XDG_DATA_HOME:-$HOME/.local/share}/spektronautilus-nvidia"
if [ "$1" = "--keep-model" ] && [ -d "$DEST/ComfyUI/models/recavsr" ]; then
  KEEP="$(mktemp -d)"; mv "$DEST/ComfyUI/models/recavsr" "$KEEP/"
  rm -rf "$DEST"; mkdir -p "$DEST/ComfyUI/models"; mv "$KEEP/recavsr" "$DEST/ComfyUI/models/"; rmdir "$KEEP"
  echo "Kept the model in $DEST/ComfyUI/models/recavsr"
else
  rm -rf "$DEST"
fi
rm -f "$HOME/.local/bin/spektronautilus-nvidia" "${XDG_DATA_HOME:-$HOME/.local/share}/applications/spektronautilus-nvidia.desktop"
echo "Removed. (Your browser settings for Spektronautilus stay in ~/.config/spektronautilus.)"

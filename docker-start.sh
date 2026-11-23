#!/bin/sh
# Starts Spektronautilus NVIDIA in Docker. The ReCaVSR model lives in the /models volume and is downloaded only when asked
# (SPEKTRO_ACCEPT_MODEL=1): its makers state no licence for the weights, so it is fetched for your own use and never part of the image.
set -e
M=/models/recavsr; mkdir -p "$M"
if [ ! -f "$M/transformer_int8_convrot.safetensors" ] || [ ! -f "$M/flashdecoder.safetensors" ] || [ ! -f "$M/prompt.safetensors" ]; then
  if [ "${SPEKTRO_ACCEPT_MODEL:-0}" = "1" ]; then
    echo "Downloading the ReCaVSR model (about 6.5 GB, once) from Hugging Face (kopper/ReCaVSR, PedroMarinhoDev/ReCaVSR-ComfyUI)…"
    HF=/opt/spektro/venv/bin/hf
    "$HF" download kopper/ReCaVSR prompt.safetensors flashdecoder.safetensors --local-dir "$M"
    "$HF" download PedroMarinhoDev/ReCaVSR-ComfyUI recavsr/transformer_int8_convrot.safetensors --local-dir /models
  else
    echo "The ReCaVSR model is not downloaded yet, so AI video upscaling (ReCaVSR) is off. Everything else works."
    echo "To get it (6.5 GB, once): start with SPEKTRO_ACCEPT_MODEL=1. Its makers state no licence for the model weights;"
    echo "they are downloaded for your own use only."
  fi
fi
if command -v nvidia-smi >/dev/null 2>&1; then nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader || true
else echo "No NVIDIA graphics card is visible in the container. Start it with the GPU (see DOCKER.md); without it the AI tools are off."; fi
exec python3 /opt/spektro/app/spektronautilus_nvidia.py --no-browser "$@"

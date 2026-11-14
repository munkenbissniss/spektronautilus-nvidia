# Spektronautilus NVIDIA

**AI video upscaling for your VJ loops, on your own NVIDIA graphics card.**

This is the Linux version of [Spektronautilus](https://github.com/munkenbissniss/spektronautilus), the magic video mixer, with one addition: the Loop Hospital can upscale clips with **ReCaVSR**, a diffusion model made for video. It adds real detail instead of only sharpening, and it stays steady from frame to frame. One installer sets up everything on the computer with the graphics card: Spektronautilus, [ComfyUI](https://github.com/comfyanonymous/ComfyUI), the [ReCaVSR nodes](https://github.com/PedroMarinhoDev/ComfyUI-ReCaVSR) and the model. One menu entry starts it all.

Everything else is the normal Spektronautilus: the mixers, the VJ tools, Video2X if you have it. Free, no ads, no account.

## What you need

| | |
|---|---|
| System | Ubuntu or Pop!_OS (64-bit) |
| Graphics card | NVIDIA, RTX 20 series or newer. RTX 30 series or newer for the fast kernels. 8 GB is enough for 1080p results |
| Driver | The NVIDIA driver (`sudo ubuntu-drivers install`, then restart) |
| Memory | 16 GB |
| Disk | About 22 GB free (Python packages about 12 GB, the model 6.5 GB) |
| Packages | `sudo apt install git python3-venv ffmpeg` |

Tested here only against a stand-in for ComfyUI (see Tests). The speed numbers below are from the ReCaVSR nodes' own page.

## Install

1. Download `spektronautilus-nvidia.tar.gz` (from Releases, or build it with `python3 build.py`) and unpack it.
2. In the unpacked folder:

   ```bash
   ./install.sh
   ```

   It checks the computer, installs ComfyUI and PyTorch for your driver's CUDA version, adds the ReCaVSR nodes, asks before downloading the model, and adds **Spektronautilus NVIDIA** to the application menu. The first install takes a while (several GB to download). Run it again later to update everything.
3. Start **Spektronautilus NVIDIA** from the menu, or type `spektronautilus-nvidia`. ComfyUI starts in the background (up to a minute the first time).
4. In the **Loop Hospital**, choose **Upscale → AI video (ReCaVSR)** and pick 2×, 3× or 4×.

Uninstall: `~/.local/share/spektronautilus-nvidia/uninstall.sh` (add `--keep-model` to keep the 6.5 GB model for a later install).

## How it works

- Spektronautilus runs its usual small local server and sends the clip to ComfyUI (on `127.0.0.1:8188`), starts the ReCaVSR workflow and fetches the result. The progress bar follows ComfyUI as it works. **Stop** also stops the job in ComfyUI.
- The **int8** model is used (6.3 GB, faster, and it fits next to other work on a 16 GB computer). If you add the bf16 model (`transformer.safetensors`) to `ComfyUI/models/recavsr`, int8 is still preferred.
- **Loops stay seamless.** ReCaVSR works forward in time and remembers what came before, so a loop's end and start would not match. The clip is upscaled twice in a row and the second round is kept: its start follows on from the end. This takes twice as long; switch it off under *Advanced* for clips that do not loop.
- Above 2560×1440 the attention memory is kept in RAM (`kv_offload`), so big results fit on an 8 GB card. Results larger than 4K are refused.
- **Colour match** (Advanced): *Keep the colours of the original* (wavelet) or *Match brightness and contrast* (AdaIN), if the result shifts in colour.

### Speed (from the ReCaVSR nodes' page)

| Clip | RTX 3090 | RTX 4090 |
|---|---|---|
| 360×360 → 1440×1440, 180 frames, int8 | 23 s | 15 s |
| 960×480 → 3840×1920, 149 frames, int8 | 67 s | 36 s |

On a card limited to 8 GB the first one took 27 s (measured by the makers on a 3090). Expect an RTX 3070 to be somewhat slower than a 3090. With the seam kept, double it.

## Settings

Environment variables, all optional:

| | |
|---|---|
| `SPEKTRO_COMFYUI` | ComfyUI's address, default `http://127.0.0.1:8188` |
| `SPEKTRO_COMFYUI_START=0` | Do not start ComfyUI; use one that is already running |
| `SPEKTRO_COMFYUI_DIR` | Where ComfyUI is installed |

ComfyUI's log: `~/.local/share/spektronautilus-nvidia/comfyui.log`. If the normal Spektronautilus is already running, close it first (both use the same port, so they share your settings).

## Licences

- This repository: MIT (see LICENSE), like Spektronautilus.
- ComfyUI and the ReCaVSR nodes (GPL-3.0) are downloaded by the installer from their own repositories; they are not part of this repository.
- **The ReCaVSR model weights:** their makers ([kopper/ReCaVSR](https://huggingface.co/kopper/ReCaVSR)) state no licence. The installer downloads them to your computer for your own use and asks first. Spektronautilus does not include or share them. Check the makers' terms before using results commercially.

## Build and test

This repository stands on its own: `app/` holds the website and the Linux launcher, next to the NVIDIA part (`app/spektronautilus_nvidia.py`).

```bash
python3 build.py                       # -> dist/spektronautilus-nvidia.tar.gz
python3 tests/test_nvidia.py           # needs ffmpeg + playwright (builds the package first)
```

To bring in a newer website from the main Spektronautilus repository later (optional): `python3 update_app.py /path/to/spektronautilus`.

The test runs the real launcher and the real Loop Hospital against a stand-in for ComfyUI that answers like ComfyUI with the ReCaVSR nodes (upload, workflow, progress over the websocket, history, download, interrupt) and upscales with plain ffmpeg. It checks the workflow that is sent, the seam handling (twice in, second round kept, same length), the size, the progress bar, Stop, and that the normal Linux launcher does not show the choice. Not tested here: real ComfyUI, ReCaVSR itself, an NVIDIA card and `install.sh` (only its syntax).

# Spektronautilus NVIDIA in Docker (all in one)

One container with everything: the Spektronautilus site and its local helper, ffmpeg, [Video2X](https://github.com/k4yt3x/video2x)
6.4.0 (AI upscaling and AI slow motion), and [ComfyUI](https://github.com/comfyanonymous/ComfyUI) with the
[ReCaVSR nodes](https://github.com/PedroMarinhoDev/ComfyUI-ReCaVSR) (AI video upscaling).

## What you need

- An NVIDIA graphics card, RTX 20 series or newer (8 GB is enough for 1080p results), and 16 GB memory
- The NVIDIA driver, **570 or newer** for the default PyTorch build (CUDA 12.8). Older driver: see *Build settings*
- Docker with the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
- About 25 GB of disk: the image is about 15 GB (PyTorch for CUDA), the model 6.5 GB

## Start

```bash
docker compose up -d --build                      # the first build takes a while
SPEKTRO_ACCEPT_MODEL=1 docker compose up -d       # downloads the ReCaVSR model once (6.5 GB)
```

Open **http://localhost:8765/**. ComfyUI starts inside the container (up to a minute). Follow it with `docker compose logs -f`.

**The model** is never part of the image. Its makers ([kopper/ReCaVSR](https://huggingface.co/kopper/ReCaVSR)) state no licence for
the weights, so it is only downloaded when you start with `SPEKTRO_ACCEPT_MODEL=1`, into the `models` volume, for your own use.
Without it everything works except **Upscale → AI video (ReCaVSR)**.

## Settings

| Variable | Default | What it does |
|---|---|---|
| `SPEKTRO_ACCEPT_MODEL` | `0` | `1` downloads the ReCaVSR model if it is missing |
| `SPEKTRO_PORT` | `8765` | the port on this computer (published on 127.0.0.1 only) |
| `SPEKTRO_HOSTS` | (none) | other names or addresses the page may be opened with, comma-separated |

Other devices at home: see `DOCKER.md` in the main Spektronautilus repository (HTTPS with Caddy). The fast way, offline use and
MIDI only work on HTTPS pages or on localhost.

## Build settings

```bash
docker compose build --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cu126    # NVIDIA driver 560-569
docker compose build --build-arg COMFYUI_REF=v0.3.40                                      # a fixed ComfyUI version (default: its newest release)
```

Also `VIDEO2X_IMAGE` (default `ghcr.io/k4yt3x/video2x:6.4.0`) and `FFMPEG_VERSION` (static ffmpeg, default `7.1`).

## Volumes

- `models` (`/models`): the ReCaVSR model and the Hugging Face cache. Keep it to avoid downloading again.
- `work` (`/work`): clips are worked on here while a job runs.

## How it is built

The image starts from the official Video2X image and changes nothing in it. ffmpeg is added as one static program, Python as a
self-contained copy (with [uv](https://github.com/astral-sh/uv)), and ComfyUI, its Python packages and PyTorch in their own
environment in `/opt/spektro/venv`. The helper listens on all addresses inside the container but only answers to `localhost`,
`127.0.0.1` and the names in `SPEKTRO_HOSTS`.

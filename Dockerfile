# syntax=docker/dockerfile:1
# Spektronautilus NVIDIA in Docker, all in one: the whole site and its local helper, ffmpeg, Video2X (AI upscaling and slow motion),
# and ComfyUI with the ReCaVSR nodes (AI video upscaling). For a computer with an NVIDIA graphics card (RTX 20 series or newer),
# the NVIDIA driver and the NVIDIA Container Toolkit.
#
#   docker compose up -d --build                         then open http://localhost:8765/
#   SPEKTRO_ACCEPT_MODEL=1 docker compose up -d          also downloads the ReCaVSR model (6.5 GB, once, into a volume)
#
# The image is big (about 15 GB: PyTorch for CUDA). See DOCKER.md.

ARG VIDEO2X_IMAGE=ghcr.io/k4yt3x/video2x:6.4.0
ARG FFMPEG_VERSION=7.1

FROM mwader/static-ffmpeg:${FFMPEG_VERSION} AS ffmpeg
FROM ghcr.io/astral-sh/uv:0.5.11 AS uv

# ComfyUI (its newest release, or COMFYUI_REF) and the ReCaVSR nodes, without their git history
FROM alpine/git:latest AS src
ARG COMFYUI_REF=
RUN set -eux; git clone -q https://github.com/comfyanonymous/ComfyUI /src/ComfyUI; cd /src/ComfyUI; git fetch -q --tags; \
    ref="${COMFYUI_REF:-$(git tag -l 'v*' --sort=-v:refname | head -1)}"; [ -z "$ref" ] || git -c advice.detachedHead=false checkout -q "$ref"; \
    echo "ComfyUI ${ref:-master}" > /src/ComfyUI/SPEKTRO_VERSION; rm -rf .git; \
    git clone -q --depth 1 https://github.com/PedroMarinhoDev/ComfyUI-ReCaVSR /src/ComfyUI/custom_nodes/ComfyUI-ReCaVSR; rm -rf /src/ComfyUI/custom_nodes/ComfyUI-ReCaVSR/.git

FROM ${VIDEO2X_IMAGE}
USER root
# nothing in the Video2X image is upgraded or replaced (that could break Video2X): ffmpeg is one static program, Python a self-contained copy
COPY --from=ffmpeg /ffmpeg /ffprobe /usr/local/bin/
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_INSTALL_DIR=/opt/python UV_LINK_MODE=copy UV_NO_CACHE=1
RUN set -eux; uv python install 3.12; ln -sf "$(uv python find 3.12)" /usr/local/bin/python3; \
    ffmpeg -hide_banner -encoders | grep -q libx264; command -v video2x >/dev/null
# PyTorch for CUDA 12.8 needs NVIDIA driver 570 or newer. For an older driver build with
#   docker compose build --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cu126
ARG TORCH_INDEX=https://download.pytorch.org/whl/cu128
COPY --from=src /src/ComfyUI /opt/spektro/ComfyUI
RUN set -eux; uv venv /opt/spektro/venv --python 3.12; P=/opt/spektro/venv/bin/python; \
    uv pip install --python $P torch torchvision torchaudio --index-url "$TORCH_INDEX"; \
    uv pip install --python $P -r /opt/spektro/ComfyUI/requirements.txt; \
    uv pip install --python $P -r /opt/spektro/ComfyUI/custom_nodes/ComfyUI-ReCaVSR/requirements.txt; \
    uv pip install --python $P "huggingface_hub[cli]"; \
    rm -rf /opt/spektro/ComfyUI/models/recavsr; ln -s /models/recavsr /opt/spektro/ComfyUI/models/recavsr
COPY app /opt/spektro/app
COPY docker-start.sh /opt/spektro/docker-start.sh
RUN chmod +x /opt/spektro/docker-start.sh /opt/spektro/app/*.py; mkdir -p /work /models/recavsr
ENV SPEKTRO_HOST=0.0.0.0 TMPDIR=/work HF_HOME=/models/.hf PYTHONUNBUFFERED=1 NVIDIA_DRIVER_CAPABILITIES=all NVIDIA_VISIBLE_DEVICES=all PATH=/usr/local/bin:$PATH
VOLUME ["/work", "/models"]
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python3 -c "import urllib.request as u; u.urlopen(u.Request('http://127.0.0.1:8765/api/ping', headers={'X-Spk': '1'}), timeout=4)"
ENTRYPOINT ["/opt/spektro/docker-start.sh"]

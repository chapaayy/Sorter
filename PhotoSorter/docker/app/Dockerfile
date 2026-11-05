# Build only static frontend assets; no Node server or npm runtime in production.
FROM node:24-alpine AS vue-build
WORKDIR /ui
COPY PhotoSorter/frontend/package.json PhotoSorter/frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY PhotoSorter/frontend/tsconfig.json PhotoSorter/frontend/vite.config.ts PhotoSorter/frontend/index.html ./
COPY PhotoSorter/frontend/src ./src
RUN npm run build

FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PHOTOSORTER_FORCE_CPU=1 PHOTOSORTER_CPU_THREADS=8 PHOTOSORTER_BATCH_SIZE=4 PHOTOSORTER_PREFETCH_WORKERS=2 \
    HOME=/workspace/Models/cache XDG_CACHE_HOME=/workspace/Models/cache/xdg \
    HF_HOME=/workspace/Models/cache/huggingface HF_HUB_CACHE=/workspace/Models/cache/huggingface/hub \
    HF_XET_CACHE=/workspace/Models/cache/huggingface/xet TORCH_HOME=/workspace/Models/cache/torch
WORKDIR /workspace/PhotoSorter
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 ca-certificates && rm -rf /var/lib/apt/lists/*
# Verified CPU-only wheels; no CUDA runtime or GPU image layers.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.14.1+cpu torchvision==0.29.1+cpu
COPY PhotoSorter/requirements-base.txt PhotoSorter/requirements.txt PhotoSorter/requirements-server.txt ./
RUN pip install -r requirements.txt -r requirements-server.txt
COPY PhotoSorter/backend ./backend
COPY PhotoSorter/frontend ./frontend
COPY --from=vue-build /ui/dist ./frontend/dist
ENV PYTHONPATH=/workspace/PhotoSorter/backend
USER 10001:10001


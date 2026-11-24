# Build only static frontend assets; no Node server or npm runtime in production.
FROM node:24-alpine AS vue-build
WORKDIR /ui
COPY PhotoSorter/frontend/package.json PhotoSorter/frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY PhotoSorter/frontend/tsconfig.json PhotoSorter/frontend/vite.config.ts PhotoSorter/frontend/index.html ./
COPY PhotoSorter/frontend/src ./src
COPY PhotoSorter/frontend/public ./public
RUN npm run build

FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PHOTOSORTER_FORCE_CPU=1 PHOTOSORTER_CPU_THREADS=8 PHOTOSORTER_BATCH_SIZE=4 PHOTOSORTER_PREFETCH_WORKERS=2 \
    HOME=/storage/app/cache XDG_CACHE_HOME=/storage/app/cache/xdg \
    HF_HOME=/storage/app/cache/huggingface HF_HUB_CACHE=/storage/app/cache/huggingface/hub \
    HF_XET_CACHE=/storage/app/cache/huggingface/xet TORCH_HOME=/storage/app/cache/torch
WORKDIR /workspace/PhotoSorter
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 ca-certificates file ffmpeg && rm -rf /var/lib/apt/lists/*
# Verified CPU-only wheels; no CUDA runtime or GPU image layers.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.14.1+cpu torchvision==0.29.1+cpu
COPY PhotoSorter/requirements-base.txt PhotoSorter/requirements.txt PhotoSorter/requirements-server.txt ./
RUN pip install -r requirements.txt -r requirements-server.txt
COPY docs/storage-layout-v2.json /workspace/docs/storage-layout-v2.json
COPY PhotoSorter/backend ./backend
COPY PhotoSorter/frontend ./frontend
COPY --from=vue-build /ui/dist ./frontend/dist
ENV PYTHONPATH=/workspace/PhotoSorter/backend
USER 10001:10001
ENTRYPOINT ["python", "-m", "app.storage.entrypoint"]


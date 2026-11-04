#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
command -v docker >/dev/null || { echo 'Install Docker Engine and Compose v2 first.' >&2; exit 1; }
docker compose version >/dev/null || { echo 'Docker Compose v2 is required.' >&2; exit 1; }
[[ -f .env ]] || cp .env.example .env
set -a
# shellcheck disable=SC1091
source .env
set +a
if [[ -z "${DOMAIN:-}" || "$DOMAIN" == 'sorter.example.com' || ! "$DOMAIN" =~ ^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?$ ]]; then
  echo 'Set a real hostname in .env: DOMAIN=sorter.yourdomain.com' >&2
  exit 1
fi
if [[ ! -f .env.generated ]]; then
  umask 077
  PYTHON_CMD="$(command -v python3 || true)"
  [[ -n "$PYTHON_CMD" ]] || { echo 'python3 required to generate passwords' >&2; exit 1; }
  "$PYTHON_CMD" - <<'PY' > .env.generated
import secrets
print('POSTGRES_PASSWORD='+secrets.token_hex(24))
print('ADMIN_PASSWORD='+secrets.token_urlsafe(24))
PY
  chmod 600 .env.generated
  echo '[INFO] Generated private credentials in .env.generated (do not commit or lose this file).'
fi
mkdir -p Models/models/megaloc Models/cache/huggingface/{hub,xet} Models/cache/{torch,xdg,downloads} PhotoSorter/data/{references,uploads,runs,cache,outputs}
# Docker image runs as UID 10001; prevent root-owned files after upgrades.
if [[ "$(id -u)" == '0' ]]; then
  chown -R 10001:10001 Models PhotoSorter/data
else
  echo '[INFO] Ensure ./Models and ./PhotoSorter/data are writable by UID 10001.'
  docker run --rm -v "$(pwd)/Models:/models" -v "$(pwd)/PhotoSorter/data:/data" alpine:3.21 sh -c 'chown -R 10001:10001 /models /data'
fi
COMPOSE=(docker compose --env-file .env --env-file .env.generated)
"${COMPOSE[@]}" up -d --build
printf '\n[OK] Site: https://%s\n' "$DOMAIN"
echo '[INFO] Login: admin'
grep '^ADMIN_PASSWORD=' .env.generated | sed 's/^ADMIN_PASSWORD=/[INFO] Initial password: /'
echo '[INFO] DNS must point to this VPS, ports 80/443 must be reachable.'

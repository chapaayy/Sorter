#!/usr/bin/env bash
# Beta install/update: one deployment path, no version-selection switches.
set -euo pipefail
cd "$(dirname "$0")"

usage() {
  echo "Usage: ./install.sh [--check | --deploy]"
  echo "  --check : read-only env/Compose/CPU prerequisite checks (no creation or restart)"
  echo "  --deploy: initial install or approved upgrade"
}
MODE="${1:---deploy}"
if [[ "$MODE" != "--check" && "$MODE" != "--deploy" ]]; then usage >&2; exit 2; fi
command -v docker >/dev/null || { echo 'Install Docker Engine and Compose v2 first.' >&2; exit 1; }
docker compose version >/dev/null || { echo 'Docker Compose v2 is required.' >&2; exit 1; }
command -v python3 >/dev/null || { echo 'Python 3 is required.' >&2; exit 1; }

if [[ ! -f .env ]]; then
  if [[ "$MODE" == "--check" ]]; then echo '[ERROR] .env missing' >&2; exit 1; fi
  cp .env.example .env
fi
set -a
# shellcheck disable=SC1091
source .env
set +a
if [[ -z "${DOMAIN:-}" || "$DOMAIN" == 'sorter.example.com' || ! "$DOMAIN" =~ ^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?$ ]]; then
  echo 'Set a real hostname in .env: DOMAIN=sorter.yourdomain.com' >&2
  exit 1
fi

# Deterministic volume name derives from "name: outdoor-sorter" in compose.yaml.
# A missing .env.generated while PostgreSQL volume exists MUST NOT generate a
# new DB password. Existing admin hash is only changed by an explicit recovery.
EXISTING_POSTGRES=0
if docker volume inspect outdoor-sorter_postgres_data >/dev/null 2>&1; then
  EXISTING_POSTGRES=1
fi
if [[ ! -f .env.generated ]]; then
  if [[ "$EXISTING_POSTGRES" -eq 1 ]]; then
    echo '[ERROR] Existing PostgreSQL volume but .env.generated is missing.' >&2
    echo 'Restore the ORIGINAL credentials from your backup; do not regenerate.' >&2
    exit 1
  fi
  if [[ "$MODE" == "--check" ]]; then echo '[ERROR] .env.generated missing' >&2; exit 1; fi
  umask 077
  python3 - <<'PY' > .env.generated
import secrets
print('POSTGRES_PASSWORD='+secrets.token_hex(24))
print('ADMIN_PASSWORD='+secrets.token_urlsafe(24))
PY
  chmod 600 .env.generated
  echo '[INFO] Generated new install credentials in .env.generated (keep offline backup).'
  CREATED_CREDENTIALS=1
else
  CREATED_CREDENTIALS=0
fi

# Verify that secrets exist without echoing them to CI/logs.
if ! grep -Eq '^POSTGRES_PASSWORD=.{16,}$' .env.generated ||
   ! grep -Eq '^ADMIN_PASSWORD=.{16,}$' .env.generated; then
  echo '[ERROR] .env.generated incomplete; restore correct credentials.' >&2
  exit 1
fi
COMPOSE=(docker compose --env-file .env --env-file .env.generated)
"${COMPOSE[@]}" config --quiet
# The default Stage2 worker cpuset assumes >=7 CPUs. Fail before Docker changes.
CPUSET="${PHOTOSORTER_WORKER_CPUSET:-0-6}"
if ! python3 - "$CPUSET" <<'PY'
import os,sys
try:
    allowed=set(os.sched_getaffinity(0))
    selected=set()
    for part in sys.argv[1].split(','):
        if '-' in part:
            a,b=map(int,part.split('-',1))
            if b<a or b-a>255:raise ValueError()
            selected.update(range(a,b+1))
        else:selected.add(int(part))
    if not selected or not selected.issubset(allowed):
        raise ValueError(f"cpuset {sys.argv[1]} not available; allowed CPUs={sorted(allowed)}")
except (ValueError,AttributeError) as exc:
    print("[ERROR] Invalid worker CPU affinity:",exc,file=sys.stderr)
    sys.exit(1)
PY
then
  echo '[ERROR] Set PHOTOSORTER_WORKER_CPUSET to valid CPU IDs before deployment.' >&2
  exit 1
fi

if [[ "$MODE" == "--check" ]]; then
  echo '[OK] Read-only preflight passed. No files or containers changed.'
  exit 0
fi

if [[ "$EXISTING_POSTGRES" -eq 1 ]]; then
  echo '[INFO] Updating beta test containers; existing Docker volumes are unchanged.'
fi

mkdir -p Models/models/megaloc Models/cache/huggingface/{hub,xet} Models/cache/{torch,xdg,downloads} PhotoSorter/data/{references,uploads,runs,cache,outputs}
if [[ "$EXISTING_POSTGRES" -eq 0 ]]; then
  # Ownership initialization is safe only on a fresh empty project.
  if [[ "$(id -u)" == '0' ]]; then
    chown -R 10001:10001 Models PhotoSorter/data
  else
    docker run --rm -v "$(pwd)/Models:/models" -v "$(pwd)/PhotoSorter/data:/data" alpine:3.21 sh -c 'chown -R 10001:10001 /models /data'
  fi
else
  echo '[INFO] Skipped recursive chown of existing model/photo storage.'
fi
"${COMPOSE[@]}" up -d --build
printf '\n[OK] Site: https://%s\n' "$DOMAIN"
echo '[INFO] Login: admin'
if [[ "$CREATED_CREDENTIALS" -eq 1 ]]; then
  echo '[INFO] Initial password was generated in .env.generated (not printed for security).'
fi
echo '[INFO] DNS and ports 80/443 must point to this VPS.'

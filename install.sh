#!/usr/bin/env bash
# Beta install/update: one deployment path, no version-selection switches.
set -euo pipefail
cd "$(dirname "$0")"

usage() {
  echo "Usage: ./install.sh [--check | --deploy]"
  echo "  --check : read-only env/Compose/CPU prerequisite checks"
  echo "  --deploy: install missing prerequisites on Ubuntu/Debian, then deploy Sorter"
}
MODE="${1:---deploy}"
if [[ "$MODE" != "--check" && "$MODE" != "--deploy" ]]; then usage >&2; exit 2; fi
if [[ ! -f .env ]]; then
  if [[ "$MODE" == "--check" ]]; then echo '[ERROR] .env missing' >&2; exit 1; fi
  cp .env.example .env
fi
unset ADMIN_PASSWORD
set -a
# shellcheck disable=SC1091
if ! source .env 2>/dev/null; then
  echo '[ERROR] Cannot read .env. Check its syntax.' >&2
  exit 1
fi
set +a
if [[ -z "${DOMAIN:-}" || "$DOMAIN" == 'sorter.example.com' || ! "$DOMAIN" =~ ^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?$ ]]; then
  echo 'Set a real hostname in .env: DOMAIN=sorter.yourdomain.com' >&2
  exit 1
fi
if [[ -z "${ADMIN_PASSWORD:-}" || "${#ADMIN_PASSWORD}" -lt 16 || "${#ADMIN_PASSWORD}" -gt 256 ]]; then
  echo '[ERROR] Set ADMIN_PASSWORD in .env (16–256 characters).' >&2
  exit 1
fi

if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1 ||
   ! command -v python3 >/dev/null; then
  if [[ "$MODE" == "--check" ]]; then
    echo '[ERROR] Docker Engine, Compose v2 and Python 3 are required. --check installs nothing.' >&2
    exit 1
  fi
  bash PhotoSorter/tools/maintenance/install_prerequisites.sh
fi
if ! docker info --format '{{.ServerVersion}}' >/dev/null; then
  echo '[ERROR] Cannot reach Docker Engine. Check that it is running and accessible to this user.' >&2
  exit 1
fi

# Deterministic volume name derives from "name: outdoor-sorter" in compose.yaml.
# A missing .env.generated while PostgreSQL volume exists MUST NOT generate a
# new DB password. The admin password is configured separately in .env.
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
  (umask 077; python3 - <<'PY' > .env.generated
import secrets
print('POSTGRES_PASSWORD='+secrets.token_hex(24))
PY
  )
  echo '[INFO] Created PostgreSQL credentials in .env.generated.'
fi

# Verify that secrets exist without echoing them to CI/logs.
if ! grep -Eq '^POSTGRES_PASSWORD=.{16,}$' .env.generated; then
  echo '[ERROR] .env.generated incomplete; restore correct credentials.' >&2
  exit 1
fi
# Derive an available model cpuset for new VPS sizes, reserving one CPU for the site.
# An explicit operator override in .env always wins.
if [[ -z "${PHOTOSORTER_WORKER_CPUSET:-}" ]]; then
  export PHOTOSORTER_WORKER_CPUSET="$(python3 - <<'PY'
import os
allowed=sorted(os.sched_getaffinity(0))
print(','.join(map(str,allowed[:-1] or allowed)))
PY
)"
fi
if [[ -z "${PHOTOSORTER_WORKER_CPUS:-}" ]]; then
  export PHOTOSORTER_WORKER_CPUS="$(python3 - "$PHOTOSORTER_WORKER_CPUSET" <<'PY'
import sys
ids=set()
for p in sys.argv[1].split(','):
    if '-' in p:
        a,b=map(int,p.split('-',1));ids.update(range(a,b+1))
    else:ids.add(int(p))
print(len(ids))
PY
)"
fi
if [[ -z "${PHOTOSORTER_CPU_THREADS:-}" ]]; then
  export PHOTOSORTER_CPU_THREADS="${PHOTOSORTER_WORKER_CPUS}"
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
  bash PhotoSorter/tools/maintenance/setup_tcp_bbr.sh --check
  echo '[OK] Read-only preflight passed. No files or containers changed.'
  exit 0
fi

if [[ "$EXISTING_POSTGRES" -eq 1 ]]; then
  echo '[INFO] Updating beta test containers; existing Docker volumes are unchanged.'
fi
chmod 600 .env .env.generated

# Optional Linux host networking optimization, not a Docker setting.
bash PhotoSorter/tools/maintenance/setup_tcp_bbr.sh --apply
# Caddy has a separate network namespace; configure it explicitly at container creation.
ACTIVE_TCP_CC="$(sysctl -n net.ipv4.tcp_congestion_control 2>/dev/null || true)"
case "$ACTIVE_TCP_CC" in
  bbr|cubic|reno) export PHOTOSORTER_CADDY_TCP_CC="$ACTIVE_TCP_CC" ;;
  *) echo '[WARN] Could not determine host TCP algorithm; Caddy uses default CUBIC.' >&2 ;;
esac

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
# Clean up the previous installer’s copy after Compose accepts the deployment.
if grep -Eq '^ADMIN_PASSWORD=' .env.generated; then
  sed -i '/^ADMIN_PASSWORD=/d' .env.generated
fi
printf '\n[OK] Site: https://%s\n' "$DOMAIN"
echo '[INFO] Login: admin (ADMIN_PASSWORD in .env)'
echo '[INFO] DNS and ports 80/443 must point to this VPS.'

#!/usr/bin/env bash
# Beta install/update: one deployment path, no version-selection switches.
set -euo pipefail
cd "$(dirname "$0")"

usage() {
  echo "Usage: ./install.sh [--check | --deploy | --configure]"
  echo "  --configure: fresh install; prompt for hostname and admin password, then deploy"
  echo "  --check : read-only env/Compose/CPU prerequisite checks"
  echo "  --deploy: install missing prerequisites on Ubuntu/Debian, then deploy Sorter"
}
MODE="${1:---deploy}"
if [[ "$MODE" != "--check" && "$MODE" != "--deploy" && "$MODE" != "--configure" ]]; then usage >&2; exit 2; fi
if [[ "$MODE" != "--check" && "$(id -u)" != 0 ]]; then
  echo '[ERROR] Run the installer as root.' >&2; exit 1
fi
if [[ -L .env || -L .env.generated ]]; then
  echo '[ERROR] Symlinked deployment configuration is forbidden.' >&2; exit 1
fi
if [[ "$MODE" == "--configure" ]]; then
  if [[ -e .env || -e .env.generated ]]; then
    echo '[ERROR] Existing configuration: use --deploy, never overwrite credentials.' >&2; exit 1
  fi
  read -r -p 'Domain (DNS hostname): ' domain
  if [[ -z "$domain" || "$domain" == 'sorter.example.com' || ! "$domain" =~ ^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?$ ]]; then
    echo '[ERROR] Invalid hostname.' >&2; exit 1
  fi
  read -r -s -p 'Admin password (16–256 characters; no single quote or backslash): ' password
  printf '\n'
  if [[ "${#password}" -lt 16 || "${#password}" -gt 256 || "$password" == *"'"* || "$password" == *\\* || "$password" == *[[:cntrl:]]* ]]; then
    echo '[ERROR] Invalid password.' >&2; exit 1
  fi
  (umask 077; set -o noclobber; printf "DOMAIN=%s\nADMIN_PASSWORD='%s'\nPHOTOSORTER_ENABLE_BBR=1\n" "$domain" "$password" > .env)
  unset domain password
  MODE=--deploy
fi
if [[ ! -f .env ]]; then
  if [[ "$MODE" == "--check" ]]; then echo '[ERROR] .env missing' >&2; exit 1; fi
  (umask 077; cp .env.example .env)
fi
unset ADMIN_PASSWORD POSTGRES_PASSWORD
unset MAP_STORAGE_ROOT
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

export MAP_STORAGE_ROOT="${MAP_STORAGE_ROOT:-$PWD/storage}"
if [[ "$MAP_STORAGE_ROOT" != /* || "$MAP_STORAGE_ROOT" == / || "$MAP_STORAGE_ROOT" == *[!a-zA-Z0-9_./-]* ]]; then
  echo '[ERROR] MAP_STORAGE_ROOT must be a safe absolute directory path.' >&2; exit 1
fi
python3 - "$MAP_STORAGE_ROOT" "$PWD" <<'PY'
from pathlib import Path
import sys
root,project=map(Path,sys.argv[1:])
if root.resolve()!=root or root==project or project.is_relative_to(root) or (root.is_relative_to(project) and root!=project/"storage"):
    raise SystemExit("[ERROR] Unsafe storage root: use project/storage or a separate absolute directory")
PY

# Existing bind-mounted PGDATA must retain original credentials.
EXISTING_POSTGRES=0
if [[ -e "$MAP_STORAGE_ROOT/infrastructure/postgres/data/PG_VERSION" ]]; then
  EXISTING_POSTGRES=1
fi
if [[ ! -f .env.generated ]]; then
  if [[ "$EXISTING_POSTGRES" -eq 1 ]]; then
    echo '[ERROR] Existing PostgreSQL data but .env.generated is missing.' >&2
    echo 'Restore the ORIGINAL credentials from your backup; do not regenerate.' >&2
    exit 1
  fi
  if [[ "$MODE" == "--check" ]]; then echo '[ERROR] .env.generated missing' >&2; exit 1; fi
  (umask 077; python3 - <<'PY' > .env.generated
import os,secrets
print('POSTGRES_PASSWORD='+secrets.token_hex(24))
print('MAP_STORAGE_ROOT='+os.environ['MAP_STORAGE_ROOT'])
PY
  )
  echo '[INFO] Created PostgreSQL credentials in .env.generated.'
fi

# The generated host path is immutable for this installation.
if [[ "$(grep -c '^MAP_STORAGE_ROOT=' .env.generated || true)" != 1 ]] ||
   ! grep -Fxq "MAP_STORAGE_ROOT=$MAP_STORAGE_ROOT" .env.generated; then
  echo '[ERROR] Storage root does not match the installation credentials; refusing to switch roots.' >&2; exit 1
fi
if [[ "$EXISTING_POSTGRES" -eq 1 && ! -f "$MAP_STORAGE_ROOT/system/state/layout-version" ]]; then
  echo '[ERROR] Existing database but no v2 layout marker; refusing to initialize another storage root.' >&2; exit 1
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
  python3 PhotoSorter/tools/maintenance/bootstrap_storage.py "$MAP_STORAGE_ROOT" --check
  bash PhotoSorter/tools/maintenance/setup_tcp_bbr.sh --check
  echo '[OK] Read-only preflight passed. No files or containers changed.'
  exit 0
fi

if [[ "$EXISTING_POSTGRES" -eq 1 ]]; then
  echo '[INFO] Updating beta test containers; persistent PostgreSQL and Caddy binds are unchanged.'
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

# A fresh v2 application root; no legacy media bind or recursive chown.
if [[ "$(id -u)" != 0 ]]; then
  echo '[ERROR] Run the installer as root to initialize protected storage.' >&2; exit 1
fi
python3 PhotoSorter/tools/maintenance/bootstrap_storage.py "$MAP_STORAGE_ROOT"
# Host updater and disposable builder on production Ubuntu. CI uses Compose.
if [[ "$(id -u)" == 0 && "${CI:-}" != true && "${GITHUB_ACTIONS:-}" != true ]] &&
   [[ -d /run/systemd/system ]] && command -v systemctl >/dev/null; then
  mkdir -p "$MAP_STORAGE_ROOT/system/updater/private"
  if [[ "${MAP_UPDATER_PREBUILT:-0}" != 1 ]]; then
    exec 9>"$MAP_STORAGE_ROOT/system/updater/private/deploy.lock"
    flock -n 9 || { echo '[ERROR] Another MAP deployment is running'; exit 1; }
  fi
  bash PhotoSorter/tools/maintenance/install_map_updater.sh
  if [[ "${MAP_UPDATER_PREBUILT:-0}" != 1 ]]; then
    python3 PhotoSorter/tools/maintenance/map_build.py "$PWD" "$(git rev-parse HEAD)" --storage-root "$MAP_STORAGE_ROOT"
  fi
  "${COMPOSE[@]}" up -d --no-build --wait --wait-timeout 180
  if [[ "${MAP_UPDATER_PREBUILT:-0}" != 1 ]]; then
    systemctl restart map-updater.service
  fi
else
  if [[ "${MAP_UPDATER_PREBUILT:-0}" != 1 ]]; then
    exec 9>"$MAP_STORAGE_ROOT/system/updater/private/deploy.lock"
    flock -n 9 || { echo '[ERROR] Another MAP deployment is running'; exit 1; }
    python3 PhotoSorter/tools/maintenance/map_build.py "$PWD" "$(git rev-parse HEAD)" --storage-root "$MAP_STORAGE_ROOT"
  fi
  "${COMPOSE[@]}" up -d --no-build --wait --wait-timeout 180
fi
# Remove an obsolete duplicate credential only after successful deployment.
if grep -Eq '^ADMIN_PASSWORD=' .env.generated; then
  sed -i '/^ADMIN_PASSWORD=/d' .env.generated
fi
printf '\n[OK] Site: https://%s\n' "$DOMAIN"
echo '[INFO] Login: admin (ADMIN_PASSWORD in .env)'
echo '[INFO] DNS and ports 80/443 must point to this VPS.'

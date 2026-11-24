#!/usr/bin/env bash
# Ephemeral CI ONLY. Builds full Python/Torch runtime, Caddy and Postgres.
# Never target the user's running VPS, persistent volumes or credentials.
set -euo pipefail
if [[ "${CI:-}" != "true" || "${GITHUB_ACTIONS:-}" != "true" ]]; then
  echo '[BLOCKED] This test is permitted ONLY on ephemeral GitHub Actions runner.' >&2
  exit 1
fi
cd "$(dirname "$0")/../../.."
export DOMAIN="localhost"
export POSTGRES_PASSWORD="ci_only_disposable_not_a_real_password"
export ADMIN_PASSWORD="ci_only_disposable_admin_password"
export PHOTOSORTER_WORKER_CPUSET
PHOTOSORTER_WORKER_CPUSET="$(python3 - <<'PY'
import os
print(min(os.sched_getaffinity(0)))
PY
)"
export PHOTOSORTER_CPU_THREADS="1"
export PHOTOSORTER_WORKER_CPUS="1"
export MAP_STORAGE_ROOT="$PWD/storage"
sudo python3 PhotoSorter/tools/maintenance/bootstrap_storage.py "$MAP_STORAGE_ROOT"
sudo python3 PhotoSorter/tools/maintenance/bootstrap_storage.py "$MAP_STORAGE_ROOT"
echo "[INFO] Isolated Docker Compose build for disposable CI containers"
cleanup() {
  docker compose ps || true
  docker compose logs --tail=80 api worker thumbnail cleanup postgres caddy || true
  docker compose down --remove-orphans || true
}
trap cleanup EXIT
# Exercise the exact disposable builder used by the VPS updater.
sudo install -d -m 0755 /var/lib/map-updater/control
sudo touch /var/lib/map-updater/control/activity.lock
sudo chmod 0644 /var/lib/map-updater/control/activity.lock
sudo install -d -o "$(id -u)" -g "$(id -g)" -m 0700 /var/lib/map-updater/private/builders
python3 PhotoSorter/tools/maintenance/map_build.py "$PWD" "$(git rev-parse HEAD)"
test -z "$(find /var/lib/map-updater/private/builders -type f -print -quit)"
docker compose up -d --no-build
# Real app UID, same mount hardlink and rename, private host paths not mounted.
docker compose exec -T api python - <<'PY'
import os
from pathlib import Path
from app.config import APP_STORAGE_ROOT
from app.storage.filesystem import atomic_write, file_stat, atomic_publish
from app.storage.temporary import temporary_operation
assert os.getuid() == 10001
assert APP_STORAGE_ROOT == Path("/storage/app")
assert not Path("/storage/system").exists()
assert not Path("/storage/infrastructure").exists()
assert not Path("/workspace/PhotoSorter/data").exists()
assert not Path("/workspace/Models").exists()
with temporary_operation(APP_STORAGE_ROOT, "api") as scratch:
    key = scratch.relative_to(APP_STORAGE_ROOT) / "a"
    with atomic_write(APP_STORAGE_ROOT, key) as f:
        f.write(b"synthetic")
    target = APP_STORAGE_ROOT / "users" / "ci-link"
    try:
        os.link(APP_STORAGE_ROOT / key, target)
        assert target.stat().st_ino == file_stat(APP_STORAGE_ROOT, key)["inode"]
        atomic_publish(APP_STORAGE_ROOT, "users/ci-link", (scratch / "b").relative_to(APP_STORAGE_ROOT))
        assert (scratch / "b").read_bytes() == b"synthetic"
    finally:
        target.unlink(missing_ok=True)
PY

healthy=0
for i in $(seq 1 90); do
  if curl -kfsS --max-time 4 https://localhost/api/health >/dev/null 2>&1; then healthy=1;break;fi
  sleep 2
done
if [[ "$healthy" -ne 1 ]]; then
  echo "[ERROR] HTTPS/API failed to become ready" >&2
  exit 1
fi
curl -kfsS --max-time 10 https://localhost/ | grep -Fq '<title>MAP</title>'
curl -kfsS --max-time 10 https://localhost/fo | grep -Fq '<title>MAP</title>'
curl -kfsS --max-time 10 https://localhost/assets/logo.webp | cmp - PhotoSorter/frontend/public/assets/logo.webp
test "$(curl -ksS -o /dev/null -w '%{http_code}' https://localhost/v3/)" = 404
test "$(curl -ksS -o /dev/null -w '%{http_code}' https://localhost/static/app.js)" = 404
cookie_file="$(mktemp)"
chmod 600 "$cookie_file"
trap 'rm -f "$cookie_file";cleanup' EXIT
printf '{"username":"admin","password":"%s"}' "$ADMIN_PASSWORD" |
 curl -kfsS --max-time 10 -c "$cookie_file" \
   -H 'Content-Type: application/json' -H 'Origin: https://localhost' \
   --data-binary @- https://localhost/api/auth/login >/dev/null
ready=0
for i in $(seq 1 40); do
  state="$(curl -ksS --max-time 6 -b "$cookie_file" https://localhost/api/system/status || true)"
  if printf '%s' "$state" | python3 -c 'import json,sys;data=json.load(sys.stdin);roles=data.get("services",{});sys.exit(0 if all(roles.get(k,{}).get("alive") for k in ("megaloc","thumbnail","cleanup")) else 1)' 2>/dev/null; then
    ready=1;break
  fi
  sleep 2
done
if [[ "$ready" -ne 1 ]]; then
  echo "[ERROR] Worker heartbeat did not become healthy" >&2
  exit 1
fi
# Real bind-mounted lock/maintenance gate and owner-only status endpoint.
curl -kfsS --max-time 8 -b "$cookie_file" https://localhost/api/system/update | grep -q '"available":false'
sudo touch /var/lib/map-updater/control/maintenance
test "$(curl -ksS -o /dev/null -w '%{http_code}' -b "$cookie_file" https://localhost/api/system/status)" = 503
curl -kfsS --max-time 8 https://localhost/api/health >/dev/null
sudo rm /var/lib/map-updater/control/maintenance
created="$(curl -kfsS --max-time 8 -b "$cookie_file" \
  -H 'Content-Type: application/json' -H 'Origin: https://localhost' \
  --data '{"display_name":"PHOTOSORTER_CI_SYNTHETIC_ONLY"}' \
  https://localhost/api/batches)"
id="$(printf '%s' "$created" | python3 -c 'import json,sys;print(json.load(sys.stdin)["batch_id"])')"
curl -kfsS --max-time 8 -b "$cookie_file" "https://localhost/api/batches/$id" >/dev/null
curl -kfsS --max-time 8 -b "$cookie_file" -X DELETE \
  -H 'Origin: https://localhost' "https://localhost/api/batches/$id" >/dev/null
echo "[OK] Full image build and isolated runtime: TLS self-signed, API/login, root Vue SPA, 3 workers and synthetic batch lifecycle"


# Stage 5: real official MegaLoc assets, real photo fixtures, offline processing.
# No mock engine or dummy checkpoint; a failed network download fails CI.
docker compose stop worker thumbnail cleanup api
fixture="$PWD/PhotoSorter/tools/maintenance/ci_megaloc_offline.py"
docker compose run --rm --no-deps -v "$fixture:/ci_megaloc.py:ro" api python /ci_megaloc.py prepare
private_network="$(docker network ls --filter label=com.docker.compose.project=outdoor-sorter --filter label=com.docker.compose.network=private --format '{{.Name}}')"
test "$(docker network inspect "$private_network" --format '{{.Internal}}')" = true
docker compose run --rm --no-deps -v "$fixture:/ci_megaloc.py:ro" worker python /ci_megaloc.py before
offline() {
  docker run --rm --network none -e MAP_APP_STORAGE_ROOT=/storage/app -e PHOTOSORTER_CPU_THREADS=2 \
    -e MAP_SERVICE=models -v "$MAP_STORAGE_ROOT/app:/storage/app" -v "$fixture:/ci_megaloc.py:ro" \
    map-local/app:current python /ci_megaloc.py "$1"
}
offline network-none
# No application process is running. Bypass entrypoint only for exclusive offline maintenance.
docker run --rm --network none --entrypoint python -e MAP_APP_STORAGE_ROOT=/storage/app \
  -v "$MAP_STORAGE_ROOT/app:/storage/app" -v "$fixture:/ci_megaloc.py:ro" \
  map-local/app:current /ci_megaloc.py purge
offline network-none
docker compose run --rm --no-deps -v "$fixture:/ci_megaloc.py:ro" worker python /ci_megaloc.py after
echo "[OK] Actual MegaLoc: official weights and source, real photo FO pipeline, cache purge, process restart, no external network, reference embedding reuse"

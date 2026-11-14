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
mkdir -p Models/models/megaloc Models/cache/{torch,xdg,downloads,huggingface} PhotoSorter/data/{references,uploads,runs,cache,outputs}
sudo chown -R 10001:10001 Models PhotoSorter/data
echo "[INFO] Isolated Docker Compose build for disposable CI containers"
cleanup() {
  docker compose ps || true
  docker compose logs --tail=80 api worker thumbnail cleanup postgres caddy || true
  docker compose down --remove-orphans || true
}
trap cleanup EXIT
docker compose up -d --build

healthy=0
for i in $(seq 1 90); do
  if curl -kfsS --max-time 4 https://localhost/api/health >/dev/null 2>&1; then healthy=1;break;fi
  sleep 2
done
if [[ "$healthy" -ne 1 ]]; then
  echo "[ERROR] HTTPS/API failed to become ready" >&2
  exit 1
fi
curl -kfsS --max-time 10 https://localhost/ | grep -q 'OUTDOOR'
curl -kfsS --max-time 10 https://localhost/fo | grep -q 'OUTDOOR'
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
created="$(curl -kfsS --max-time 8 -b "$cookie_file" \
  -H 'Content-Type: application/json' -H 'Origin: https://localhost' \
  --data '{"display_name":"PHOTOSORTER_CI_SYNTHETIC_ONLY"}' \
  https://localhost/api/batches)"
id="$(printf '%s' "$created" | python3 -c 'import json,sys;print(json.load(sys.stdin)["batch_id"])')"
curl -kfsS --max-time 8 -b "$cookie_file" "https://localhost/api/batches/$id" >/dev/null
curl -kfsS --max-time 8 -b "$cookie_file" -X DELETE \
  -H 'Origin: https://localhost' "https://localhost/api/batches/$id" >/dev/null
echo "[OK] Full image build and isolated runtime: TLS self-signed, API/login, root Vue SPA, 3 workers and synthetic batch lifecycle"

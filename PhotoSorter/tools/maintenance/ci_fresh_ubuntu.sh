#!/usr/bin/env bash
# Fresh disposable Ubuntu VM only. Never run this against an existing server.
set -euo pipefail
[[ "${CI:-}" == true && "${GITHUB_ACTIONS:-}" == true ]] || exit 1
cd "$(dirname "$0")/../../.."
revision="$(git rev-parse HEAD)"
vm="$(mktemp -d)"
cleanup() {
  if [[ -f "$vm/pid" ]]; then sudo kill "$(cat "$vm/pid")" 2>/dev/null || true; fi
  if [[ -f "$vm/serial.log" ]]; then tail -n 80 "$vm/serial.log"; fi
  sudo rm -rf -- "$vm"
}
trap cleanup EXIT
sudo apt-get update -qq
sudo apt-get install -y --no-install-recommends qemu-system-x86 qemu-utils cloud-image-utils openssh-client
[[ -c /dev/kvm ]] || { echo "BLOCKED: hosted runner has no KVM; no substitute systemd result"; exit 1; }
base=https://cloud-images.ubuntu.com/noble/current
image=noble-server-cloudimg-amd64.img
curl --fail --retry 3 -sSL "$base/SHA256SUMS" -o "$vm/SHA256SUMS"
curl --fail --retry 3 -sSL "$base/$image" -o "$vm/$image"
(cd "$vm"; grep -E "[ *]$image\$" SHA256SUMS | sha256sum -c -)
sha256sum "$vm/$image"
qemu-img create -f qcow2 -F qcow2 -b "$vm/$image" "$vm/disk.qcow2" 64G
ssh-keygen -q -t ed25519 -N '' -f "$vm/key"
cat > "$vm/user-data" <<EOF
#cloud-config
users:
  - name: ci
    groups: [sudo]
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    ssh_authorized_keys:
      - $(cat "$vm/key.pub")
ssh_pwauth: false
disable_root: true
EOF
printf 'instance-id: map-stage10\nlocal-hostname: map-stage10\n' > "$vm/meta-data"
cloud-localds "$vm/seed.img" "$vm/user-data" "$vm/meta-data"
sudo qemu-system-x86_64 -enable-kvm -cpu host -smp 2 -m 4608 \
  -drive "file=$vm/disk.qcow2,if=virtio,format=qcow2" \
  -drive "file=$vm/seed.img,if=virtio,format=raw,readonly=on" \
  -netdev user,id=net,hostfwd=tcp:127.0.0.1:2222-:22 -device virtio-net-pci,netdev=net \
  -display none -serial "file:$vm/serial.log" -daemonize -pidfile "$vm/pid"
sshvm=(ssh -i "$vm/key" -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -p 2222 ci@127.0.0.1)
wait_ssh() {
  for _ in $(seq 1 180); do
    if "${sshvm[@]}" true 2>/dev/null; then return; fi
    sleep 2
  done
  echo 'VM SSH deadline exceeded'; return 1
}
wait_ssh
"${sshvm[@]}" sudo bash -s -- "$revision" <<'GUEST'
set -euo pipefail
revision=$1
cloud-init status --wait
. /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 24.04 ]]
[[ "$(ps -p 1 -o comm=)" == systemd ]]
! command -v docker
! systemctl cat map-updater.service >/dev/null 2>&1
test ! -e /opt/Sorter
echo STAGE10_PRISTINE_UBUNTU_OK
apt-get update -qq
apt-get install -y git ca-certificates curl
git clone --branch feature/storage-architecture-v2 --single-branch https://github.com/chapaayy/Sorter.git /opt/Sorter
cd /opt/Sorter
git reset --hard "$revision"
test "$(git rev-parse HEAD)" = "$revision"
printf 'localhost\nstage10_disposable_password_only\n' | bash install.sh --configure
systemctl is-active --quiet docker.service
systemctl is-enabled --quiet map-updater.service
systemctl is-active --quiet map-updater.service
systemctl is-enabled --quiet map-log-maintenance.timer
systemctl is-active --quiet map-log-maintenance.timer
test "$(systemctl show -p MainPID --value map-updater.service)" -gt 1
bash install.sh --check
test "$(stat -c %a .env)" = 600
test "$(stat -c %a .env.generated)" = 600
echo STAGE10_SYSTEMD_INSTALL_OK
# Use the actual HTTPS owner API, not a manually launched updater/model daemon.
umask 077
cookie=/root/stage10-cookie
api() { curl -kfsS --max-time 60 -b "$cookie" -H 'Origin: https://localhost' "$@"; }
for _ in $(seq 1 120); do
  if api https://localhost/api/health >/dev/null 2>&1; then break; fi
  sleep 2
done
api https://localhost/api/health >/dev/null
printf '{"username":"admin","password":"stage10_disposable_password_only"}' |
  api -c "$cookie" -H 'Content-Type: application/json' --data-binary @- https://localhost/api/auth/login >/dev/null
api https://localhost/api/system/update | python3 -c 'import json,sys;d=json.load(sys.stdin);assert d["available"] and d["branch"]=="feature/storage-architecture-v2"'
api -X POST https://localhost/api/models/megaloc/download >/dev/null
for _ in $(seq 1 600); do
  if api https://localhost/api/models | python3 -c 'import json,sys;d=json.load(sys.stdin);sys.exit(not d["models"][0]["available"])'; then break; fi
  sleep 3
done
api https://localhost/api/models | python3 -c 'import json,sys;assert json.load(sys.stdin)["models"][0]["available"]'
docker compose --env-file .env --env-file .env.generated exec -T api python -c 'from app.system.model_store import verified;assert verified()'
echo STAGE10_MODEL_VERIFIED_OK
api -H 'Content-Type: application/json' --data '{"display_name":"STAGE10_REBOOT_SENTINEL"}' https://localhost/api/batches > /root/stage10-batch.json
sha256sum .env.generated > /root/stage10-secrets.sha
find storage/app/models -type f -exec sha256sum {} + | sort > /root/stage10-model.sha
openssl s_client -connect localhost:443 -servername localhost </dev/null 2>/dev/null | openssl x509 -fingerprint -sha256 -noout > /root/stage10-cert
cat /proc/sys/kernel/random/boot_id > /root/stage10-boot
bash install.sh --deploy
sha256sum -c /root/stage10-secrets.sha
sha256sum -c /root/stage10-model.sha
echo STAGE10_REPEAT_INSTALL_OK
GUEST
"${sshvm[@]}" sudo systemctl reboot || true
sleep 15
wait_ssh
"${sshvm[@]}" sudo bash -s <<'GUEST'
set -euo pipefail
cd /opt/Sorter
test "$(cat /proc/sys/kernel/random/boot_id)" != "$(cat /root/stage10-boot)"
systemctl is-active --quiet docker.service
for _ in $(seq 1 120); do
  if systemctl is-active --quiet map-updater.service && curl -kfsS https://localhost/api/health >/dev/null 2>&1; then break; fi
  sleep 2
done
systemctl is-enabled --quiet map-updater.service
systemctl is-active --quiet map-updater.service
systemctl is-active --quiet map-log-maintenance.timer
cookie=/root/stage10-cookie
api() { curl -kfsS --max-time 60 -b "$cookie" -H 'Origin: https://localhost' "$@"; }
api https://localhost/api/system/update | python3 -c 'import json,sys;assert json.load(sys.stdin)["available"]'
sha256sum -c /root/stage10-secrets.sha
sha256sum -c /root/stage10-model.sha
id=$(python3 -c 'import json;print(json.load(open("/root/stage10-batch.json"))["batch_id"])')
api "https://localhost/api/batches/$id" | python3 -c 'import json,sys;assert json.load(sys.stdin)["display_name"]=="STAGE10_REBOOT_SENTINEL"'
echo STAGE10_REAL_REBOOT_OK
# Create a *local* second revision on a disposable bare origin; never push to GitHub.
git clone --bare . /root/stage10-origin.git
git clone --branch feature/storage-architecture-v2 /root/stage10-origin.git /root/stage10-next
git -C /root/stage10-next config user.name 'Stage10 disposable'
git -C /root/stage10-next config user.email 'ci@example.test'
printf 'Stage 10 local revision\n' >/root/stage10-next/docs/ci-stage10-marker.txt
git -C /root/stage10-next add docs/ci-stage10-marker.txt
git -C /root/stage10-next commit -m 'Disposable VM updater acceptance'
git -C /root/stage10-next push origin feature/storage-architecture-v2
target=$(git -C /root/stage10-next rev-parse HEAD)
git config url.file:///root/stage10-origin.git.insteadOf https://github.com/chapaayy/Sorter.git
api -X POST https://localhost/api/system/update/check >/dev/null
for _ in $(seq 1 120); do
  if api https://localhost/api/system/update | python3 -c 'import json,sys;d=json.load(sys.stdin);sys.exit(not(d["phase"]=="checked" and d["update_available"]))'; then break; fi
  sleep 2
done
api https://localhost/api/system/update | python3 -c 'import json,sys;d=json.load(sys.stdin);assert d["phase"]=="checked" and d["update_available"]'
api -X POST https://localhost/api/system/update/start >/dev/null
for _ in $(seq 1 600); do
  if api https://localhost/api/system/update 2>/dev/null | python3 -c 'import json,sys;d=json.load(sys.stdin);sys.exit(not(d["phase"]=="success" and not d["busy"]))' 2>/dev/null; then break; fi
  sleep 3
done
api https://localhost/api/system/update | python3 -c 'import json,sys;d=json.load(sys.stdin);assert d["phase"]=="success" and not d["busy"]'
test "$(git rev-parse HEAD)" = "$target"
systemctl is-active --quiet map-updater.service
sha256sum -c /root/stage10-secrets.sha
sha256sum -c /root/stage10-model.sha
openssl s_client -connect localhost:443 -servername localhost </dev/null 2>/dev/null | openssl x509 -fingerprint -sha256 -noout | cmp - /root/stage10-cert
api "https://localhost/api/batches/$id" | python3 -c 'import json,sys;assert json.load(sys.stdin)["display_name"]=="STAGE10_REBOOT_SENTINEL"'
echo STAGE10_REAL_SYSTEMD_API_UPDATE_OK
GUEST
echo STAGE10_FRESH_UBUNTU_COMPLETE

#!/usr/bin/env bash
# Bootstrap host packages on a clean Ubuntu/Debian VPS. Never remove packages.
set -euo pipefail

need_docker=0
need_compose=0
need_python=0
if ! command -v docker >/dev/null; then
  need_docker=1
elif ! docker compose version >/dev/null 2>&1; then
  need_compose=1
fi
command -v python3 >/dev/null || need_python=1
if (( !need_docker && !need_compose && !need_python )); then exit 0; fi

if [[ "$(id -u)" != 0 ]]; then
  echo '[ERROR] Run install.sh --deploy as root to install missing host packages.' >&2
  exit 1
fi
if [[ ! -r /etc/os-release ]] || ! command -v apt-get >/dev/null; then
  echo '[ERROR] Automatic setup needs Ubuntu or Debian. Install Docker, Compose v2 and Python 3 manually.' >&2
  exit 1
fi
# shellcheck disable=SC1091
. /etc/os-release
case "${ID:-}" in
  ubuntu) suite=${UBUNTU_CODENAME:-${VERSION_CODENAME:-}} ;;
  debian) suite=${VERSION_CODENAME:-} ;;
  *) echo '[ERROR] Automatic setup needs Ubuntu or Debian. Install missing prerequisites manually.' >&2; exit 1 ;;
esac
if [[ ! "$suite" =~ ^[a-z][a-z0-9-]*$ ]]; then
  echo '[ERROR] Cannot determine the distribution codename for apt.' >&2
  exit 1
fi

# Do not switch an existing Docker installation to a different package family.
if (( need_compose )) && ! dpkg-query -W -f='${Status}' docker-ce-cli 2>/dev/null | grep -qx 'install ok installed'; then
  echo '[ERROR] Existing Docker lacks Compose v2. Install its matching Compose plugin and rerun.' >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
echo '[INFO] Installing missing host prerequisites with apt.'
apt-get update
packages=()
if (( need_docker || need_compose )); then
  if ! apt-cache show docker-ce >/dev/null 2>&1; then
    apt-get install -y --no-remove ca-certificates curl
    arch=$(dpkg --print-architecture)
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL "https://download.docker.com/linux/$ID/gpg" -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/$ID
Suites: $suite
Components: stable
Architectures: $arch
Signed-By: /etc/apt/keyrings/docker.asc
EOF
    apt-get update
  fi
  if (( need_docker )); then
    packages+=(docker-ce docker-ce-cli containerd.io docker-buildx-plugin)
  fi
  packages+=(docker-compose-plugin)
fi
if (( need_python )); then packages+=(python3); fi
apt-get install -y --no-remove "${packages[@]}"

if (( need_docker )) && command -v systemctl >/dev/null && [[ -d /run/systemd/system ]]; then
  systemctl enable --now docker.service
fi
docker compose version
command -v python3 >/dev/null

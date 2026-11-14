#!/usr/bin/env bash
# Exercise the real entry point without modifying host packages or Docker.
set -euo pipefail
cd "$(dirname "$0")/../../.."
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
export SORTER_TEST_TMP=$tmp
export BASH_ENV=$tmp/mocks

cat > "$BASH_ENV" <<'MOCKS'
command() {
  case "$*" in
    '-v docker') [[ -f "$SORTER_TEST_TMP/docker" ]] ;;
    '-v python3') [[ -f "$SORTER_TEST_TMP/python" ]] ;;
    *) builtin command "$@" ;;
  esac
}
id() { echo "${SORTER_TEST_UID:-0}"; }
apt-get() {
  echo "apt-get $*" >> "$SORTER_TEST_TMP/calls"
  if [[ "$1" == update && -f "$SORTER_TEST_TMP/docker.sources" && "${SORTER_TEST_NO_DOCKER_INDEX:-0}" != 1 ]]; then
    touch "$SORTER_TEST_TMP/docker-index"
  fi
  if [[ "$*" == *'docker-compose-plugin'* ]]; then
    [[ -f "$SORTER_TEST_TMP/docker-index" ]] || return 100
    touch "$SORTER_TEST_TMP/docker" "$SORTER_TEST_TMP/compose"
  fi
  if [[ "$*" == *' python3'* ]]; then touch "$SORTER_TEST_TMP/python"; fi
}
apt-cache() {
  case "$1" in
    show) return 0 ;; # APT can recognize the name without an installable version.
    policy)
      if [[ -f "$SORTER_TEST_TMP/docker-index" ]]; then
        printf '%s:\n  Installed: (none)\n  Candidate: 1.2.3\n' "$2"
      else
        printf '%s:\n  Installed: (none)\n  Candidate: (none)\n' "$2"
      fi ;;
    *) return 1 ;;
  esac
}
dpkg() { [[ "$1" == --print-architecture ]]; echo amd64; }
dpkg-query() { [[ "${SORTER_TEST_DOCKER_CE:-0}" == 1 ]] && printf '%s' 'install ok installed'; }
install() { echo "install $*" >> "$SORTER_TEST_TMP/calls"; }
curl() { echo "curl $*" >> "$SORTER_TEST_TMP/calls"; }
tee() { cat > "$SORTER_TEST_TMP/docker.sources"; }
chmod() {
  if [[ "$*" == 'a+r /etc/apt/keyrings/docker.asc' ]]; then return 0; fi
  builtin command chmod "$@"
}
systemctl() { echo "systemctl $*" >> "$SORTER_TEST_TMP/calls"; }
sysctl() { echo cubic; }
chown() { return 0; }
docker() {
  case "$*" in
    'compose version') [[ -f "$SORTER_TEST_TMP/compose" ]] ;;
    'info --format {{.ServerVersion}}') [[ -f "$SORTER_TEST_TMP/docker" ]] ;;
    'volume inspect outdoor-sorter_postgres_data') [[ -f "$SORTER_TEST_TMP/postgres" ]] ;;
    'compose --env-file .env --env-file .env.generated config --quiet') return 0 ;;
    'compose --env-file .env --env-file .env.generated up -d --build') touch "$SORTER_TEST_TMP/postgres" ;;
    *) echo "Unexpected Docker command: $*" >&2; return 1 ;;
  esac
}
MOCKS

mkdir -p "$tmp/project/PhotoSorter/tools/maintenance"
cp install.sh "$tmp/project/"
cp PhotoSorter/tools/maintenance/{install_prerequisites,setup_tcp_bbr}.sh "$tmp/project/PhotoSorter/tools/maintenance/"
cd "$tmp/project"
printf 'DOMAIN=sorter.example.com\n' > .env

expect_failure() {
  local message=$1
  shift
  if "$@" > "$tmp/output" 2>&1; then
    echo "Expected failure: $*" >&2
    exit 1
  fi
  grep -Fq -- "$message" "$tmp/output" || { cat "$tmp/output" >&2; exit 1; }
}

expect_failure 'Set a real hostname' bash install.sh --deploy
printf "DOMAIN=sorter.example.test\nADMIN_PASSWORD='disposable test password'\nPHOTOSORTER_ENABLE_BBR=0\n" > .env
expect_failure '--check installs nothing' bash install.sh --check
expect_failure 'as root' env SORTER_TEST_UID=1000 bash install.sh --deploy
[[ ! -e "$tmp/calls" && ! -e .env.generated ]]

expect_failure 'Docker packages still have no apt candidate' env SORTER_TEST_NO_DOCKER_INDEX=1 bash install.sh --deploy
[[ ! -e "$tmp/docker" && ! -e .env.generated ]]
! grep -q docker-compose-plugin "$tmp/calls"
rm "$tmp/calls" "$tmp/docker.sources"

bash install.sh --deploy
grep -Eq '^URIs: https://download.docker.com/linux/(ubuntu|debian)$' "$tmp/docker.sources"
grep -Fxq 'apt-get install -y --no-remove docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin python3' "$tmp/calls"
[[ -f "$tmp/postgres" && "$(stat -c %a .env.generated)" == 600 ]]
[[ "$(stat -c %a .env)" == 600 ]]
! grep -q '^ADMIN_PASSWORD=' .env.generated
grep -q '^POSTGRES_PASSWORD=' .env.generated
cp .env.generated "$tmp/credentials"
cp "$tmp/calls" "$tmp/first-install-calls"

bash install.sh --check
bash install.sh --deploy
cmp -s "$tmp/credentials" .env.generated
cmp -s "$tmp/first-install-calls" "$tmp/calls"

rm "$tmp/compose"
expect_failure 'Install its matching Compose plugin' bash install.sh --deploy
cmp -s "$tmp/first-install-calls" "$tmp/calls"
SORTER_TEST_DOCKER_CE=1 bash install.sh --deploy
grep -Fxq 'apt-get install -y --no-remove docker-compose-plugin' "$tmp/calls"
cmp -s "$tmp/credentials" .env.generated
[[ "$(grep -c '^curl ' "$tmp/calls")" == 1 ]] # Reuse the existing official apt source.
echo '[OK] Bootstrap, read-only check, repeat deployment and Compose-only installation'

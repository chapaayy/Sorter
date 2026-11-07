#!/usr/bin/env bash
# Linux host TCP BBR tuning, independent of Docker and application code.
set -euo pipefail
MODE="--apply"
if [[ $# -gt 0 ]]; then MODE="$1"; fi
case "$MODE" in
  --check|--apply|--disable) ;;
  *) echo "Usage: bash setup_tcp_bbr.sh [--check | --apply | --disable]" >&2; exit 2 ;;
esac
CONFIG_ROOT="/etc"
if [[ -v PHOTOSORTER_BBR_ETC_ROOT ]]; then CONFIG_ROOT="$PHOTOSORTER_BBR_ETC_ROOT"; fi
SYSCTL_CONF="$CONFIG_ROOT/sysctl.d/99-photosorter-bbr.conf"
MODULE_CONF="$CONFIG_ROOT/modules-load.d/99-photosorter-bbr.conf"

if [[ "$MODE" == "--check" ]]; then
  current="$(sysctl -n net.ipv4.tcp_congestion_control 2>/dev/null || true)"
  echo "[INFO] Host TCP congestion control: $current (read-only)"
  exit 0
fi
if [[ "$(id -u)" != "0" ]]; then
  echo "[WARN] TCP BBR requires root on the VPS; Docker deployment continues unchanged." >&2
  exit 0
fi
if [[ "$MODE" == "--disable" ]]; then
  rm -f -- "$SYSCTL_CONF" "$MODULE_CONF"
  if sysctl -w net.ipv4.tcp_congestion_control=cubic >/dev/null 2>&1; then
    echo "[OK] Removed PhotoSorter BBR persistence; CUBIC now active for new TCP connections."
  else
    echo "[WARN] Removed persistence but could not activate CUBIC." >&2
  fi
  exit 0
fi

ENABLED=1
if [[ -v PHOTOSORTER_ENABLE_BBR ]]; then ENABLED="$PHOTOSORTER_ENABLE_BBR"; fi
case "$ENABLED" in
  1) ;;
  0) echo "[INFO] BBR setup skipped (PHOTOSORTER_ENABLE_BBR=0)."; exit 0 ;;
  *) echo "[ERROR] PHOTOSORTER_ENABLE_BBR must be 0 or 1." >&2; exit 2 ;;
esac
if ! command -v sysctl >/dev/null 2>&1; then
  echo "[WARN] Missing sysctl; skipping BBR setup." >&2
  exit 0
fi
available="$(sysctl -n net.ipv4.tcp_available_congestion_control 2>/dev/null || true)"
if ! grep -qw bbr <<< "$available"; then
  if ! command -v modprobe >/dev/null 2>&1 || ! modprobe tcp_bbr >/dev/null 2>&1; then
    echo "[WARN] Kernel tcp_bbr module unavailable; Docker deployment continues." >&2
    exit 0
  fi
  available="$(sysctl -n net.ipv4.tcp_available_congestion_control 2>/dev/null || true)"
fi
if ! grep -qw bbr <<< "$available"; then
  echo "[WARN] Kernel does not expose BBR; Docker deployment continues." >&2
  exit 0
fi

# Do not change fq_codel: this VPS was already benchmarked successfully with it.
if ! sysctl -w net.ipv4.tcp_congestion_control=bbr >/dev/null 2>&1; then
  echo "[WARN] Could not enable BBR; Docker deployment continues." >&2
  exit 0
fi

write_atomic() {
  local path="$1" value="$2" tmp
  tmp="$(mktemp "$path.XXXXXX")" || return 1
  if ! printf '%s\n' "$value" > "$tmp" || ! chmod 0644 "$tmp" || ! mv -f -- "$tmp" "$path"; then
    rm -f -- "$tmp"
    return 1
  fi
}
if ! mkdir -p -- "$(dirname "$SYSCTL_CONF")" "$(dirname "$MODULE_CONF")" ||
   ! write_atomic "$MODULE_CONF" "tcp_bbr" ||
   ! write_atomic "$SYSCTL_CONF" "net.ipv4.tcp_congestion_control = bbr"; then
  echo "[WARN] BBR is active, but reboot persistence could not be saved." >&2
  exit 0
fi
actual="$(sysctl -n net.ipv4.tcp_congestion_control 2>/dev/null || true)"
if [[ "$actual" == "bbr" ]]; then
  echo "[OK] Host TCP BBR enabled and persisted for reboot (qdisc unchanged)."
else
  echo "[WARN] Host TCP algorithm is $actual, expected bbr; check sysctl conflicts." >&2
fi

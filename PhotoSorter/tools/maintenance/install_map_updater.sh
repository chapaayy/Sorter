#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
[[ "$(id -u)" == 0 ]] || exit 1
[[ "$ROOT" =~ ^/[a-zA-Z0-9_./-]+$ ]] || { echo "Unsupported project path"; exit 1; }
STORAGE="${MAP_STORAGE_ROOT:?Run install.sh}"
install -d -o root -g root -m 0755 /usr/local/lib/map-updater
CONTROL="$STORAGE/system/updater/control"
# Keep the same lock inode for every container.
touch "$CONTROL/activity.lock"
chown root:root "$CONTROL/activity.lock"
chmod 0644 "$CONTROL/activity.lock"
install -m 0644 "$ROOT/PhotoSorter/tools/maintenance/map_updater.py" /usr/local/lib/map-updater/map_updater.py
install -m 0644 "$ROOT/PhotoSorter/tools/maintenance/map_build.py" /usr/local/lib/map-updater/map_build.py
install -m 0644 "$ROOT/PhotoSorter/tools/maintenance/host_logs.py" /usr/local/lib/map-updater/host_logs.py
install -m 0644 "$ROOT/PhotoSorter/tools/maintenance/host_accounting.py" /usr/local/lib/map-updater/host_accounting.py
install -m 0644 "$ROOT/PhotoSorter/tools/maintenance/storage_tree.py" /usr/local/lib/map-updater/storage_tree.py
cat > /etc/systemd/system/map-updater.service <<EOF
[Unit]
Description=MAP restricted host updater
After=docker.service
Requires=docker.service

[Service]
Type=simple
User=root
Group=root
UMask=0077
WorkingDirectory=$ROOT
ExecStart=/usr/bin/python3 /usr/local/lib/map-updater/map_updater.py --project-root $ROOT --storage-root $STORAGE
Restart=always
RestartSec=3
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF
cat > /etc/systemd/system/map-log-maintenance.service <<EOF
[Unit]
Description=Bounded MAP PostgreSQL journal cleanup
[Service]
Type=oneshot
User=root
ExecStart=/usr/bin/python3 /usr/local/lib/map-updater/host_logs.py $STORAGE
EOF
cat > /etc/systemd/system/map-log-maintenance.timer <<EOF
[Unit]
Description=Periodic MAP journal maintenance
[Timer]
OnBootSec=1min
OnUnitActiveSec=1min
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now map-log-maintenance.timer
systemctl enable map-updater.service

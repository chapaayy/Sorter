#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
[[ "$(id -u)" == 0 ]] || exit 1
[[ "$ROOT" =~ ^/[a-zA-Z0-9_./-]+$ ]] || { echo "Unsupported project path"; exit 1; }
install -d -o root -g root -m 0755 /var/lib/map-updater /var/lib/map-updater/control /var/lib/map-updater/rpc /usr/local/lib/map-updater
install -d -o root -g root -m 0700 /var/lib/map-updater/private
# Keep the same lock inode for every container.
touch /var/lib/map-updater/control/activity.lock
chown root:root /var/lib/map-updater/control/activity.lock
chmod 0644 /var/lib/map-updater/control/activity.lock
install -m 0644 "$ROOT/PhotoSorter/tools/maintenance/map_updater.py" /usr/local/lib/map-updater/map_updater.py
install -m 0644 "$ROOT/PhotoSorter/tools/maintenance/map_build.py" /usr/local/lib/map-updater/map_build.py
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
ExecStart=/usr/bin/python3 /usr/local/lib/map-updater/map_updater.py --project-root $ROOT
Restart=always
RestartSec=3
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable map-updater.service

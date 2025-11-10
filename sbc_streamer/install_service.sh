#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="sbc-streamer"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_PATH="${SCRIPT_DIR}/run.sh"
UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root." >&2
  exit 1
fi

if [[ ! -f "${RUN_PATH}" ]]; then
  echo "run.sh not found at ${RUN_PATH}" >&2
  exit 1
fi

chmod +x "${RUN_PATH}"

cat > "${UNIT_PATH}" <<EOF
[Unit]
Description=SBC Streamer (Tank Robot)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${SCRIPT_DIR}
ExecStart=${RUN_PATH}
Restart=on-failure
RestartSec=5
User=root
Group=root

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}.service"

systemctl status "${SERVICE_NAME}.service" --no-pager

#!/usr/bin/env bash
#
# manuEdge update path (git-pull + systemd restart).
# Run on the Pi: sudo bash /opt/manuedge/scripts/deploy.sh
#
set -euo pipefail

INSTALL_DIR="/opt/manuedge"

echo "[manuEdge] pulling latest..."
git -C "$INSTALL_DIR" pull --ff-only

echo "[manuEdge] reinstalling (in case deps changed)..."
"$INSTALL_DIR/.venv/bin/pip" install --upgrade "$INSTALL_DIR[pi]"

echo "[manuEdge] restarting service..."
systemctl restart manuedge.service
systemctl --no-pager status manuedge.service | head -n 10

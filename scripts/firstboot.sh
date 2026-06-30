#!/usr/bin/env bash
#
# manuEdge first-boot provisioning.
#
# Goal: empty SD → flash Raspberry Pi OS Lite (Bookworm 64-bit) with Imager
# (set hostname + SSH key) → drop agent.toml on the boot partition → first boot
# runs this once and the agent comes up.
#
# Run as root on the Pi (manually for now; later wired to a oneshot systemd unit
# or baked into a pi-gen image):
#     sudo bash firstboot.sh
#
set -euo pipefail

REPO_URL="https://github.com/mtc8608/manuEdge.git"
INSTALL_DIR="/opt/manuedge"
CONFIG_DIR="/etc/manuedge"
BOOT_CONFIG="/boot/firmware/agent.toml"   # Bookworm boot partition
SERVICE_USER="manuedge"

echo "[manuEdge] 1/7 enabling SPI..."
raspi-config nonint do_spi 0 || true

echo "[manuEdge] 2/7 SD-wear stopgaps (log2ram, noatime, swap off)..."
apt-get update -y
apt-get install -y git python3-venv python3-pip log2ram || apt-get install -y git python3-venv python3-pip
systemctl disable --now dphys-swapfile 2>/dev/null || true
# add noatime to the root mount if not already present
if ! grep -q 'noatime' /etc/fstab; then
  sed -i 's/\(\s\/\s.*defaults\)/\1,noatime/' /etc/fstab || true
fi

echo "[manuEdge] 3/7 creating service user + dirs..."
id -u "$SERVICE_USER" >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
usermod -aG spi,gpio "$SERVICE_USER" 2>/dev/null || true
mkdir -p "$CONFIG_DIR"

echo "[manuEdge] 4/7 fetching agent code..."
if [ -d "$INSTALL_DIR/.git" ]; then
  git -C "$INSTALL_DIR" pull --ff-only
else
  git clone "$REPO_URL" "$INSTALL_DIR"
fi

echo "[manuEdge] 5/7 creating venv + installing..."
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install "$INSTALL_DIR[pi]"

echo "[manuEdge] 6/7 installing per-device config..."
if [ -f "$BOOT_CONFIG" ]; then
  install -m 600 "$BOOT_CONFIG" "$CONFIG_DIR/agent.toml"
  chown "$SERVICE_USER":"$SERVICE_USER" "$CONFIG_DIR/agent.toml"
elif [ ! -f "$CONFIG_DIR/agent.toml" ]; then
  echo "  WARNING: no $BOOT_CONFIG and no $CONFIG_DIR/agent.toml — copy config/agent.example.toml and edit."
fi

echo "[manuEdge] 7/7 installing + starting service..."
install -m 644 "$INSTALL_DIR/systemd/manuedge.service" /etc/systemd/system/manuedge.service
systemctl daemon-reload
systemctl enable --now manuedge.service

echo "[manuEdge] done. Check status: systemctl status manuedge"

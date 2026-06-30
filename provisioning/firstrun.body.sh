# shellcheck disable=SC2148
# manuEdge first-boot body — runs ONCE as root at first boot, hooked via
# cmdline.txt (systemd.run). The flasher prepends FR_* variable assignments
# above this line, so do not run this file standalone.
#
# Responsibilities: hostname, key-only user, SSH, Wi-Fi (Ethernet preferred),
# stage the manuEdge config, and install a one-shot that does the networked
# install (apt/git/venv) on the next boot. Best-effort throughout — a single
# failure must never brick first boot.

LOG=/var/log/manuedge-firstrun.log
exec >>"$LOG" 2>&1
echo "[firstrun] starting"

# --- hostname ---
echo "$FR_HOSTNAME" > /etc/hostname
if grep -q '^127.0.1.1' /etc/hosts; then
  sed -i "s/^127.0.1.1.*/127.0.1.1\t$FR_HOSTNAME/" /etc/hosts
else
  printf '127.0.1.1\t%s\n' "$FR_HOSTNAME" >> /etc/hosts
fi
hostnamectl set-hostname "$FR_HOSTNAME" 2>/dev/null || true

# --- key-only admin user ---
if ! id -u "$FR_USERNAME" >/dev/null 2>&1; then
  useradd -m -s /bin/bash "$FR_USERNAME"
fi
for g in sudo adm dialout audio video plugdev users input netdev gpio spi i2c; do
  usermod -aG "$g" "$FR_USERNAME" 2>/dev/null || true
done
install -d -m700 -o "$FR_USERNAME" -g "$FR_USERNAME" "/home/$FR_USERNAME/.ssh"
printf '%s\n' "$FR_AUTHKEY" > "/home/$FR_USERNAME/.ssh/authorized_keys"
chmod 600 "/home/$FR_USERNAME/.ssh/authorized_keys"
chown "$FR_USERNAME:$FR_USERNAME" "/home/$FR_USERNAME/.ssh/authorized_keys"
passwd -l "$FR_USERNAME" 2>/dev/null || true
printf '%s ALL=(ALL) NOPASSWD:ALL\n' "$FR_USERNAME" > /etc/sudoers.d/010-manuedge
chmod 440 /etc/sudoers.d/010-manuedge

# --- SSH: enable, key-only ---
systemctl enable ssh 2>/dev/null || true
mkdir -p /etc/ssh/sshd_config.d
cat > /etc/ssh/sshd_config.d/manuedge.conf <<'SSHD'
PasswordAuthentication no
PubkeyAuthentication yes
SSHD

# --- Wi-Fi (optional). Ethernet preferred via negative autoconnect priority. ---
if [ -n "$FR_WIFI_SSID" ]; then
  raspi-config nonint do_wifi_country "$FR_WIFI_COUNTRY" 2>/dev/null || true
  rfkill unblock wifi 2>/dev/null || true
  install -d -m700 /etc/NetworkManager/system-connections
  CONN="/etc/NetworkManager/system-connections/${FR_WIFI_SSID}.nmconnection"
  cat > "$CONN" <<EOF
[connection]
id=$FR_WIFI_SSID
type=wifi
autoconnect=true
autoconnect-priority=-10
[wifi]
mode=infrastructure
ssid=$FR_WIFI_SSID
[wifi-security]
key-mgmt=wpa-psk
psk=$FR_WIFI_PSK
[ipv4]
method=auto
[ipv6]
method=auto
EOF
  chmod 600 "$CONN"
fi

# --- stage manuEdge per-device config ---
for src in /boot/firmware/agent.toml /boot/agent.toml; do
  if [ -f "$src" ]; then
    install -D -m600 "$src" /etc/manuedge/agent.toml
    break
  fi
done

# --- one-shot networked install (next boot, after network is up) ---
cat > /usr/local/sbin/manuedge-bootstrap <<EOF
#!/bin/bash
exec >>/var/log/manuedge-bootstrap.log 2>&1
echo "[bootstrap] starting"
set -e
# Raspberry Pi OS Lite has no git — install it before the clone.
if ! command -v git >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y git
fi
if [ -d /opt/manuedge/.git ]; then
  git -C /opt/manuedge pull --ff-only || true
else
  git clone "$FR_REPO_URL" /opt/manuedge
fi
bash /opt/manuedge/scripts/firstboot.sh
systemctl disable manuedge-bootstrap.service || true
echo "[bootstrap] done"
EOF
chmod +x /usr/local/sbin/manuedge-bootstrap

cat > /etc/systemd/system/manuedge-bootstrap.service <<'UNIT'
[Unit]
Description=manuEdge one-time bootstrap (install agent on first networked boot)
After=network-online.target
Wants=network-online.target
ConditionPathExists=!/opt/manuedge/.installed
[Service]
Type=oneshot
RemainAfterExit=true
ExecStart=/usr/local/sbin/manuedge-bootstrap
[Install]
WantedBy=multi-user.target
UNIT
systemctl enable manuedge-bootstrap.service 2>/dev/null || true

# --- remove the firstrun hook so this never runs again, then reboot ---
CMD=/boot/firmware/cmdline.txt
[ -f "$CMD" ] || CMD=/boot/cmdline.txt
sed -i 's| systemd.run=[^ ]*||g; s| systemd.run_success_action=[^ ]*||g; s| systemd.unit=[^ ]*||g' "$CMD"
echo "[firstrun] done"
exit 0

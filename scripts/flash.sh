#!/usr/bin/env bash
#
# manuEdge SD-card flasher — "Raspberry Pi Imager, automated".
#
#   ./run flash               # interactive: write image + bake all config
#   ./run flash --dry-run     # generate + print the config artifacts, touch nothing
#   ./run flash --refresh     # re-download the OS image first
#
# Insert card → run → answer per-Pi prompts → card in Pi → power up → it works.
# Shared answers (server URL, Wi-Fi, username, country) are remembered as
# defaults in .run/flash-profile.env; per-Pi answers (node_id, token) are asked
# every time.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNDIR="$ROOT/.run"
PROFILE="$RUNDIR/flash-profile.env"
IMG_DIR="$RUNDIR/images"
IMG="$IMG_DIR/raspios_lite_arm64_latest.img.xz"
IMG_URL="https://downloads.raspberrypi.com/raspios_lite_arm64_latest"
REPO_URL_DEFAULT="https://github.com/mtc8608/manuEdge.git"

DRY_RUN=false
REFRESH=false
for a in "$@"; do
  case "$a" in
    --dry-run) DRY_RUN=true ;;
    --refresh) REFRESH=true ;;
    -h|--help) sed -n '3,16p' "$0"; exit 0 ;;
  esac
done

if [ -t 0 ] && [ -z "${MANUEDGE_BATCH:-}" ]; then INTERACTIVE=true; else INTERACTIVE=false; fi

c()  { printf '\033[1;36m%s\033[0m\n' "$*"; }
err() { printf '\033[1;31m%s\033[0m\n' "$*" >&2; }
die() { err "$*"; exit 1; }

# prompt VAR "label" "default"  — uses $VAR (env) or default; asks if interactive
prompt() {
  local __var=$1 __label=$2 __def=${3:-} __in __cur=${!1:-}
  local __d=${__cur:-$__def}
  if $INTERACTIVE; then
    read -rp "  ${__label}${__d:+ [$__d]}: " __in || true
    __d=${__in:-$__d}
  fi
  printf -v "$__var" '%s' "$__d"
}
prompt_secret() {
  local __var=$1 __label=$2 __in
  if $INTERACTIVE; then
    read -rsp "  ${__label}: " __in || true; echo
    printf -v "$__var" '%s' "${__in:-${!__var:-}}"
  else
    printf -v "$__var" '%s' "${!__var:-}"
  fi
}

detect_pubkey() {
  local k f
  for k in id_ed25519 id_ecdsa id_rsa; do
    [ -f "$HOME/.ssh/$k.pub" ] && { cat "$HOME/.ssh/$k.pub"; return 0; }
  done
  f=$(ls "$HOME"/.ssh/*.pub 2>/dev/null | head -1 || true)
  [ -n "$f" ] && { cat "$f"; return 0; }
  return 1
}

# ---------------------------------------------------------------- gather inputs
mkdir -p "$RUNDIR"
# shellcheck disable=SC1090
[ -f "$PROFILE" ] && source "$PROFILE"

c "manuEdge SD flasher"
echo "Per-Pi settings:"
prompt NODE_ID    "node_id / hostname"  "${NODE_ID:-bedside-01}"
prompt SERVER_URL "manuBeat server URL" "${SERVER_URL:-https://manubeat.example.hospital}"
prompt_secret TOKEN "enrollment token (per device)"
echo "Network (Ethernet preferred; Wi-Fi is the fallback):"
prompt WIFI_SSID    "Wi-Fi SSID (blank = Ethernet only)" "${WIFI_SSID:-}"
if [ -n "$WIFI_SSID" ]; then
  prompt_secret WIFI_PSK "Wi-Fi passphrase"
  prompt WIFI_COUNTRY "Wi-Fi country code" "${WIFI_COUNTRY:-GB}"
fi
echo "Login:"
prompt USERNAME "admin username (SSH key only)" "${USERNAME:-manu}"
REPO_URL=${REPO_URL:-$REPO_URL_DEFAULT}

AUTHKEY=${AUTHKEY:-$(detect_pubkey || true)}
[ -n "$AUTHKEY" ] || die "no SSH public key found in ~/.ssh/*.pub — run: ssh-keygen -t ed25519"

# remember shared defaults (never persist secrets: token, Wi-Fi PSK)
cat > "$PROFILE" <<EOF
NODE_ID=$(printf '%q' "$NODE_ID")
SERVER_URL=$(printf '%q' "$SERVER_URL")
USERNAME=$(printf '%q' "$USERNAME")
WIFI_SSID=$(printf '%q' "$WIFI_SSID")
WIFI_COUNTRY=$(printf '%q' "${WIFI_COUNTRY:-GB}")
REPO_URL=$(printf '%q' "$REPO_URL")
EOF

# ------------------------------------------------------------ build artifacts
WORK="$RUNDIR/flash-build"
rm -rf "$WORK"; mkdir -p "$WORK"

# agent.toml (bench channels by default; remap later via the config agent)
cat > "$WORK/agent.toml" <<EOF
node_id = "$NODE_ID"

[server]
url = "$SERVER_URL"
enrollment_token = "$TOKEN"
verify_tls = true

[uplink]
batch_records = 200
poll_interval_s = 1.0

[heartbeat]
interval_s = 15.0

[buffer]
backend = "memory"
max_records = 500000

[[drivers]]
name = "ads1256"
spi_bus = 0
spi_device = 0
cs_pin = 22
drdy_pin = 17
rst_pin = 18
loop_hz = 50

[[drivers.channels]]
ain = 0
modality = "bench_pot"

[[drivers.channels]]
ain = 1
modality = "bench_ldr"
EOF

# firstrun.sh = generated FR_* header + static body
{
  echo '#!/bin/bash'
  printf 'FR_HOSTNAME=%q\n'     "$NODE_ID"
  printf 'FR_USERNAME=%q\n'     "$USERNAME"
  printf 'FR_AUTHKEY=%q\n'      "$AUTHKEY"
  printf 'FR_WIFI_SSID=%q\n'    "${WIFI_SSID:-}"
  printf 'FR_WIFI_PSK=%q\n'     "${WIFI_PSK:-}"
  printf 'FR_WIFI_COUNTRY=%q\n' "${WIFI_COUNTRY:-GB}"
  printf 'FR_REPO_URL=%q\n'     "$REPO_URL"
  echo
  cat "$ROOT/provisioning/firstrun.body.sh"
} > "$WORK/firstrun.sh"
chmod +x "$WORK/firstrun.sh"

if $DRY_RUN; then
  PREVIEW="$RUNDIR/flash-preview"; rm -rf "$PREVIEW"; cp -r "$WORK" "$PREVIEW"
  c "DRY RUN — no device touched. Artifacts written to $PREVIEW"
  echo; c "===== agent.toml ====="; cat "$PREVIEW/agent.toml"
  echo; c "===== firstrun.sh (header) ====="; sed -n '1,9p' "$PREVIEW/firstrun.sh"
  echo "  … (+ $(wc -l < "$PREVIEW/firstrun.sh") lines total)"
  echo; c "cmdline.txt would gain: systemd.run=/boot/firmware/firstrun.sh systemd.run_success_action=reboot systemd.unit=kernel-command-line.target"
  echo   "config.txt would gain:  dtparam=spi=on"
  exit 0
fi

# --------------------------------------------------------------- get the image
mkdir -p "$IMG_DIR"
if [ ! -f "$IMG" ] || $REFRESH; then
  c "Downloading Raspberry Pi OS Lite (64-bit)…"
  command -v curl >/dev/null || die "curl not found"
  curl -L --fail -o "$IMG.part" "$IMG_URL"
  mv "$IMG.part" "$IMG"
fi
command -v xz >/dev/null || die "xz not found (sudo apt install xz-utils)"

# --------------------------------------------------------- choose target device
c "Removable block devices:"
lsblk -dpno NAME,SIZE,TRAN,RM,MODEL | awk '$4==1 || $3=="usb" {print "  " $0}'
ROOT_DISK=$(lsblk -no PKNAME "$(findmnt -no SOURCE /)" 2>/dev/null | head -1 || true)
prompt DEVICE "Target device (e.g. /dev/sdb or /dev/mmcblk0)" "${DEVICE:-}"
[ -n "$DEVICE" ] || die "no device given"
[ -b "$DEVICE" ] || die "$DEVICE is not a block device"
[ "$(basename "$DEVICE")" != "$ROOT_DISK" ] || die "$DEVICE is your system disk — refusing"

SIZE=$(lsblk -dno SIZE "$DEVICE"); MODEL=$(lsblk -dno MODEL "$DEVICE" || true)
err "About to ERASE $DEVICE  ($SIZE  $MODEL)"
read -rp "Type ERASE to confirm: " CONFIRM
[ "$CONFIRM" = "ERASE" ] || die "aborted"

case "$DEVICE" in *mmcblk*|*nvme*) P="p" ;; *) P="" ;; esac
BOOT="${DEVICE}${P}1"

# ---------------------------------------------------------------- write + inject
c "Unmounting any existing partitions…"
for p in "${DEVICE}${P}"*; do sudo umount "$p" 2>/dev/null || true; done

c "Writing image to $DEVICE (this takes a few minutes)…"
xz -dc "$IMG" | sudo dd of="$DEVICE" bs=4M conv=fsync status=progress
sync
sudo partprobe "$DEVICE" 2>/dev/null || true
sleep 2

c "Mounting boot partition $BOOT…"
MNT=$(mktemp -d)
sudo mount "$BOOT" "$MNT"

c "Injecting config…"
sudo cp "$WORK/firstrun.sh" "$MNT/firstrun.sh"; sudo chmod +x "$MNT/firstrun.sh"
sudo cp "$WORK/agent.toml"  "$MNT/agent.toml"
sudo touch "$MNT/ssh"
grep -q '^dtparam=spi=on' "$MNT/config.txt" 2>/dev/null || \
  echo 'dtparam=spi=on' | sudo tee -a "$MNT/config.txt" >/dev/null
sudo cp "$MNT/cmdline.txt" "$MNT/cmdline.txt.orig"
CUR=$(sudo cat "$MNT/cmdline.txt" | tr -d '\n')
echo "$CUR systemd.run=/boot/firmware/firstrun.sh systemd.run_success_action=reboot systemd.unit=kernel-command-line.target" \
  | sudo tee "$MNT/cmdline.txt" >/dev/null

sync
sudo umount "$MNT"; rmdir "$MNT"

c "Done. Insert the card into '$NODE_ID' and power up."
echo "  First boot configures the OS + Wi-Fi and reboots; the second boot"
echo "  installs manuEdge over the network and starts the service."
echo "  Then: ssh $USERNAME@${NODE_ID}.local   journalctl -u manuedge -f"

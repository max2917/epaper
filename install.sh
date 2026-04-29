#!/usr/bin/env bash
# install.sh — set up epaper-reddit on a fresh Raspberry Pi Zero W.
#
# Run as root (or with sudo) on the Pi:
#     sudo ./install.sh
#
# What it does:
#   1. Enables SPI via raspi-config (no-op if already on).
#   2. Installs apt packages (Python, Pillow, RPi.GPIO, spidev, git).
#   3. Clones Waveshare's e-Paper repo to /opt/waveshare-epaper.
#   4. Copies this project to /opt/epaper-reddit.
#   5. Drops config.example.toml at /etc/epaper-reddit/config.toml (if absent).
#   6. Installs the systemd service + timer and enables the timer.
#
# The script is idempotent — re-running it just updates the install.

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Please run as root: sudo $0" >&2
    exit 1
fi

PROJECT_SRC="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="/opt/epaper-reddit"
WAVESHARE_DIR="/opt/waveshare-epaper"
CONFIG_DIR="/etc/epaper-reddit"
STATE_DIR="/var/lib/epaper-reddit"

echo "[1/6] Enabling SPI..."
if command -v raspi-config >/dev/null 2>&1; then
    raspi-config nonint do_spi 0 || true
else
    echo "  raspi-config not found; make sure SPI is enabled in /boot/config.txt"
fi

echo "[2/6] Installing apt + pip dependencies..."
apt-get update -y
apt-get install -y --no-install-recommends \
    git python3 python3-pip python3-pil python3-numpy \
    python3-rpi.gpio python3-spidev

# tomli only needed if we're on Python <3.11 (Bullseye ships 3.9).
PY_MINOR=$(python3 -c 'import sys; print(sys.version_info[1])')
if [[ "$PY_MINOR" -lt 11 ]]; then
    pip3 install --break-system-packages tomli || pip3 install tomli
fi
pip3 install --break-system-packages requests || pip3 install requests

echo "[3/6] Fetching Waveshare e-Paper library to ${WAVESHARE_DIR}..."
if [[ -d "$WAVESHARE_DIR/.git" ]]; then
    git -C "$WAVESHARE_DIR" pull --ff-only
else
    git clone --depth 1 https://github.com/waveshare/e-Paper "$WAVESHARE_DIR"
fi

echo "[4/6] Installing project to ${APP_DIR}..."
mkdir -p "$APP_DIR"
# Copy the python package only — keep /opt clean.
cp -r "$PROJECT_SRC/epaper_reddit" "$APP_DIR/"
mkdir -p "$STATE_DIR"

echo "[5/6] Installing config to ${CONFIG_DIR}..."
mkdir -p "$CONFIG_DIR"
if [[ ! -f "$CONFIG_DIR/config.toml" ]]; then
    cp "$PROJECT_SRC/config.example.toml" "$CONFIG_DIR/config.toml"
    echo "  Wrote $CONFIG_DIR/config.toml — edit it to set your subreddit + User-Agent."
else
    echo "  $CONFIG_DIR/config.toml already exists; leaving it alone."
fi

echo "[6/6] Installing systemd units..."
install -m 0644 "$PROJECT_SRC/systemd/epaper-reddit.service" /etc/systemd/system/
install -m 0644 "$PROJECT_SRC/systemd/epaper-reddit.timer"   /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now epaper-reddit.timer

echo
echo "Install complete."
echo "  - Edit:    $CONFIG_DIR/config.toml"
echo "  - Test:    sudo systemctl start epaper-reddit.service && journalctl -u epaper-reddit -b"
echo "  - Status:  systemctl list-timers epaper-reddit.timer"
echo "  - Manual:  sudo PYTHONPATH=$APP_DIR:$WAVESHARE_DIR/RaspberryPi_JetsonNano/python/lib \\"
echo "                  python3 -m epaper_reddit --config $CONFIG_DIR/config.toml"

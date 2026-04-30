#!/usr/bin/env bash
# update.sh — push code changes to an already-installed epaper-reddit.
#
# Run as root (or with sudo) on the Pi after pulling new code:
#     sudo ./update.sh
#
# Copies the Python package to /opt/epaper-reddit and reloads the systemd
# units if they changed. Does not touch apt packages, the Waveshare library,
# config, or SPI settings.

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Please run as root: sudo $0" >&2
    exit 1
fi

PROJECT_SRC="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="/opt/epaper-reddit"

if [[ ! -d "$APP_DIR" ]]; then
    echo "epaper-reddit doesn't appear to be installed at $APP_DIR." >&2
    echo "Run sudo ./install.sh first." >&2
    exit 1
fi

echo "Updating Python package..."
cp -r "$PROJECT_SRC/epaper_reddit" "$APP_DIR/"

echo "Updating systemd units..."
install -m 0644 "$PROJECT_SRC/systemd/epaper-reddit.service" /etc/systemd/system/
install -m 0644 "$PROJECT_SRC/systemd/epaper-reddit.timer"   /etc/systemd/system/
systemctl daemon-reload

echo
echo "Update complete. Starting service..."
systemctl start epaper-reddit.service
echo "Done. To follow logs:"
echo "  journalctl -u epaper-reddit.service -f"

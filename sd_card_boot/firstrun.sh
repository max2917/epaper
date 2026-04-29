#!/bin/bash
# firstrun.sh — runs once on the Pi's first boot to configure:
#   - WiFi (SSID: STEPHENSON, WPA2 PSK)
#   - Static IPv4 192.168.1.150/24, gateway 192.168.1.1, DNS 1.1.1.1 + 8.8.8.8
#   - Hostname: epaper-pi
#   - WiFi regulatory country: US
#   - SSH enabled (the empty `ssh` boot file already does this; we belt-and-brace)
#
# Triggered from cmdline.txt by the systemd.run= chain that apply_to_sd.sh
# (or your manual edit) appended to the kernel command line. The script
# strips that chain back out at the end so it only runs once.
#
# Works on both Bookworm (NetworkManager-based) and Bullseye (dhcpcd +
# wpa_supplicant) — it auto-detects which networking stack is in use.

set +e
exec >/boot/firstrun.log 2>&1
echo "[firstrun] $(date -u) starting"

# ---- Settings ---------------------------------------------------------------
WIFI_SSID="STEPHENSON"
WIFI_PSK="6156610296"
WIFI_COUNTRY="US"
STATIC_IP="192.168.1.150"
STATIC_PREFIX="24"
STATIC_GATEWAY="192.168.1.1"
DNS_SERVERS="1.1.1.1 8.8.8.8"
HOSTNAME="epaper-pi"
# -----------------------------------------------------------------------------

# Hostname ---------------------------------------------------------------------
echo "[firstrun] setting hostname to $HOSTNAME"
echo "$HOSTNAME" > /etc/hostname
sed -i "s/^127\.0\.1\.1.*/127.0.1.1\t$HOSTNAME/" /etc/hosts || \
    echo -e "127.0.1.1\t$HOSTNAME" >> /etc/hosts
hostname "$HOSTNAME" 2>/dev/null || true

# WiFi regulatory --------------------------------------------------------------
if command -v raspi-config >/dev/null 2>&1; then
    echo "[firstrun] setting WiFi country to $WIFI_COUNTRY via raspi-config"
    raspi-config nonint do_wifi_country "$WIFI_COUNTRY" || true
fi

# Networking -------------------------------------------------------------------
# Bookworm uses NetworkManager. Bullseye uses dhcpcd + wpa_supplicant. We
# detect the active stack and write whichever the system will read.
if command -v nmcli >/dev/null 2>&1 && [ -d /etc/NetworkManager ]; then
    echo "[firstrun] NetworkManager detected — writing connection profile"
    NM_DIR="/etc/NetworkManager/system-connections"
    mkdir -p "$NM_DIR"
    cat > "$NM_DIR/${WIFI_SSID}.nmconnection" <<NMEOF
[connection]
id=${WIFI_SSID}
type=wifi
autoconnect=true
interface-name=wlan0

[wifi]
mode=infrastructure
ssid=${WIFI_SSID}

[wifi-security]
key-mgmt=wpa-psk
psk=${WIFI_PSK}

[ipv4]
method=manual
addresses=${STATIC_IP}/${STATIC_PREFIX}
gateway=${STATIC_GATEWAY}
dns=$(echo "$DNS_SERVERS" | tr ' ' ';');

[ipv6]
method=ignore

[proxy]
NMEOF
    chmod 600 "$NM_DIR/${WIFI_SSID}.nmconnection"
    chown root:root "$NM_DIR/${WIFI_SSID}.nmconnection"
    nmcli connection reload 2>/dev/null || true
else
    echo "[firstrun] NetworkManager not present — using wpa_supplicant + dhcpcd"
    cat > /etc/wpa_supplicant/wpa_supplicant.conf <<WPAEOF
country=${WIFI_COUNTRY}
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1

network={
    ssid="${WIFI_SSID}"
    psk="${WIFI_PSK}"
    key_mgmt=WPA-PSK
}
WPAEOF
    chmod 600 /etc/wpa_supplicant/wpa_supplicant.conf

    # Static IP via dhcpcd. Append-with-marker so re-runs don't duplicate.
    if ! grep -q "# epaper-reddit static IP" /etc/dhcpcd.conf 2>/dev/null; then
        cat >> /etc/dhcpcd.conf <<DHCPCDEOF

# epaper-reddit static IP
interface wlan0
static ip_address=${STATIC_IP}/${STATIC_PREFIX}
static routers=${STATIC_GATEWAY}
static domain_name_servers=${DNS_SERVERS}
DHCPCDEOF
    fi
fi

# SSH (the empty boot/ssh file handles this on first boot, but enable explicitly
# in case the system already booted past that step).
echo "[firstrun] enabling ssh"
systemctl enable ssh 2>/dev/null || true

# Self-cleanup -----------------------------------------------------------------
# Remove the systemd.run= chain we added to cmdline.txt so this script doesn't
# run again. Both possible boot-partition mount points covered.
echo "[firstrun] cleaning up cmdline.txt"
for cmdline in /boot/cmdline.txt /boot/firmware/cmdline.txt; do
    [ -f "$cmdline" ] || continue
    sed -i 's| systemd\.run=[^ ]*||g; s| systemd\.run_success_action=[^ ]*||g; s| systemd\.unit=kernel-command-line\.target||g' "$cmdline"
done

# Remove this script itself.
rm -f /boot/firstrun.sh /boot/firmware/firstrun.sh

echo "[firstrun] done — rebooting in 5s"
sync
( sleep 5 && systemctl reboot ) &
exit 0

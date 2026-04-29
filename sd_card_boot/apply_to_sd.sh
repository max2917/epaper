#!/usr/bin/env bash
# apply_to_sd.sh — copy the boot files to a freshly-flashed Raspberry Pi OS
# SD card, and patch cmdline.txt so firstrun.sh runs on first boot.
#
# Workflow:
#   1. Flash Raspberry Pi OS Lite (64-bit recommended) with Raspberry Pi
#      Imager and "no customizations" (or any settings — we overwrite).
#   2. Eject + reinsert the card so it remounts.
#   3. ./apply_to_sd.sh                 (auto-detects /Volumes/bootfs or /Volumes/boot)
#      ./apply_to_sd.sh /Volumes/bootfs (or pass an explicit path)
#
# Idempotent: re-running just refreshes the files; the cmdline.txt patch is
# only added if it isn't already there.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

# ---- Locate the boot volume -------------------------------------------------
if [[ $# -ge 1 ]]; then
    BOOT="$1"
elif [[ -d /Volumes/bootfs ]]; then
    BOOT="/Volumes/bootfs"        # Bookworm and later
elif [[ -d /Volumes/boot ]]; then
    BOOT="/Volumes/boot"          # Bullseye and earlier
else
    echo "Could not find the SD card boot volume." >&2
    echo "Pass it as an argument, e.g.: $0 /Volumes/bootfs" >&2
    exit 1
fi

if [[ ! -f "$BOOT/cmdline.txt" ]]; then
    echo "$BOOT does not look like a Raspberry Pi boot partition (no cmdline.txt)." >&2
    exit 1
fi

echo "Using boot volume: $BOOT"

# ---- Copy files -------------------------------------------------------------
echo "  -> ssh         (enables SSH on first boot)"
cp "$HERE/ssh"          "$BOOT/ssh"

echo "  -> userconf.txt (creates 'pi' user)"
cp "$HERE/userconf.txt" "$BOOT/userconf.txt"

echo "  -> firstrun.sh  (configures WiFi + static IP)"
cp "$HERE/firstrun.sh"  "$BOOT/firstrun.sh"
# FAT32 doesn't carry exec bits, but we set them anyway in case we're running on
# a Linux host where the partition does honour the mode.
chmod +x "$BOOT/firstrun.sh" 2>/dev/null || true

# ---- Patch cmdline.txt ------------------------------------------------------
APPEND=" systemd.run=/boot/firstrun.sh systemd.run_success_action=reboot systemd.unit=kernel-command-line.target"

if grep -q "systemd.run=/boot/firstrun.sh" "$BOOT/cmdline.txt"; then
    echo "  -> cmdline.txt already patched, skipping"
else
    # cmdline.txt is a single line — strip any trailing newline, append, re-add newline.
    cp "$BOOT/cmdline.txt" "$BOOT/cmdline.txt.bak"
    # shellcheck disable=SC2002 — explicit cat is clearer here than redirection.
    cur=$(cat "$BOOT/cmdline.txt" | tr -d '\n')
    printf '%s%s\n' "$cur" "$APPEND" > "$BOOT/cmdline.txt"
    echo "  -> cmdline.txt patched (backup: cmdline.txt.bak)"
fi

# ---- Sanity output ----------------------------------------------------------
echo
echo "Done."
echo "  Eject the SD card, put it in the Pi, power up."
echo "  After ~90s the Pi should be reachable at:  ssh pi@192.168.1.150"
echo "  Default password: raspberry  (change immediately with: passwd)"
echo
echo "  If something goes wrong, the firstrun.log file on the boot partition"
echo "  has the script's output. (Pop the SD card back into your Mac to read it.)"

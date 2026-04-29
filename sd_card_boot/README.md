# SD card boot files

Drop these onto a freshly-flashed Raspberry Pi OS Lite SD card to bring up
your headless Pi Zero W with WiFi, a fixed IP, and SSH already running.

## Preconfigured settings

| Setting             | Value                              |
| ------------------- | ---------------------------------- |
| WiFi SSID           | `STEPHENSON`                       |
| WiFi password       | `6156610296`                       |
| WiFi country        | `US`                               |
| Static IP           | `192.168.1.150/24`                 |
| Gateway             | `192.168.1.1` *(assumed standard)* |
| DNS                 | `1.1.1.1`, `8.8.8.8`               |
| Hostname            | `epaper-pi`                        |
| Username            | `pi`                               |
| Password            | `raspberry` *(change on first SSH)* |
| SSH                 | Enabled                            |

To change any of these *before* flashing, edit `firstrun.sh` (network/hostname
settings are at the top of the file) or regenerate `userconf.txt` with a new
SHA-512 hash:

```bash
echo "pi:$(openssl passwd -6 'YourNewPassword')" > userconf.txt
```

## Files

| File                | Purpose                                                   |
| ------------------- | --------------------------------------------------------- |
| `ssh`               | Empty file — its presence enables the SSH daemon on first boot. |
| `userconf.txt`      | Creates the `pi` user with the SHA-512-hashed password above. |
| `firstrun.sh`       | Runs once on first boot: WiFi, static IP, hostname, SSH.  |
| `cmdline_append.txt`| The exact tokens to append to `cmdline.txt` so the kernel runs `firstrun.sh`. |
| `apply_to_sd.sh`    | macOS/Linux helper: copies files to the SD card and patches `cmdline.txt` for you. |

## Usage

### 1. Flash the OS

Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/):

- **Operating System** → *Raspberry Pi OS (other)* → **Raspberry Pi OS Lite (64-bit)**
  *(32-bit Lite also works — the Pi Zero W's ARMv6 actually requires 32-bit;
  pick "Raspberry Pi OS Lite (Legacy, 32-bit)" if 64-bit refuses to boot.)*
- **Storage** → your microSD card
- *(Don't bother with custom OS settings — `firstrun.sh` overrides them anyway.)*
- Click **Write** and wait.

When Imager finishes, eject and reinsert the card so the boot partition
remounts (it shows up as `bootfs` on Bookworm or `boot` on older releases).

### 2. Apply these files

**Option A — automatic (recommended on macOS):**

```bash
cd sd_card_boot
./apply_to_sd.sh
```

The script auto-detects `/Volumes/bootfs` or `/Volumes/boot`, copies the four
files, and appends the kernel-command-line tokens to `cmdline.txt`. It backs
up the original `cmdline.txt` to `cmdline.txt.bak`.

**Option B — manual:**

1. Copy `ssh`, `userconf.txt`, and `firstrun.sh` to the boot partition.
2. Open `cmdline.txt` on the boot partition. It's a single line — append the
   contents of `cmdline_append.txt` to the end of that line (keeping it one
   line). Result should look something like:

   ```
   console=serial0,115200 console=tty1 root=PARTUUID=... rootfstype=ext4 ... rootwait systemd.run=/boot/firstrun.sh systemd.run_success_action=reboot systemd.unit=kernel-command-line.target
   ```

### 3. Boot

Eject the SD card, insert it into the Pi Zero W, plug in power. About 60–90s
later — after the Pi joins WiFi, `firstrun.sh` runs, then the Pi reboots —
you should be able to:

```bash
ssh pi@192.168.1.150          # password: raspberry  (change immediately)
```

### 4. Install the e-paper app

Once SSH'd in:

```bash
git clone <this repo url> ~/epaper-reddit
cd ~/epaper-reddit
sudo ./install.sh
```

See the project root's [README](../README.md) for the full app setup.

## Troubleshooting

If the Pi never appears at `192.168.1.150`:

1. Pop the SD card back into your Mac and look at `firstrun.log` on the boot
   partition — it shows exactly where `firstrun.sh` got stuck.
2. Confirm your router is on the `192.168.1.0/24` subnet with `.1` as the
   gateway. If yours is different (e.g. `10.0.0.0/24`), edit the `STATIC_*`
   variables at the top of `firstrun.sh` and reflash.
3. If the Pi appears on DHCP but not at the static IP, your wpa_supplicant
   path likely succeeded but dhcpcd didn't pick up the static config — try a
   reboot, then check `ip -4 addr show wlan0` over SSH.
4. If you see "WiFi country not set" warnings on console, run
   `sudo raspi-config` → *Localisation Options* → *WLAN Country* once.

## Notes on what's going on

- `cmdline.txt` patch tells the kernel to run `firstrun.sh` as PID 1 (well,
  via systemd) on first boot. This is the same mechanism Raspberry Pi
  Imager's "advanced settings" use under the hood.
- `firstrun.sh` writes the WiFi+IP config to whichever stack the OS uses
  (NetworkManager on Bookworm, dhcpcd+wpa_supplicant on Bullseye), then
  strips its own command-line entry from `cmdline.txt` so it never runs
  again, then reboots cleanly.
- If you use Bookworm and `wpa_supplicant.conf` looked tempting: that file
  is no longer honored on Bookworm. We use NetworkManager profiles instead.

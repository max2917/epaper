# epaper-reddit

Pulls the top image post from a configurable subreddit (default `r/earthporn`),
dithers it to the 7-color palette of a Waveshare 7.3" e-paper panel
(model `epd7in3f`, [Amazon B0BMQ83W7W](https://www.amazon.com/dp/B0BMQ83W7W)),
saves it as a BMP, and pushes it to the display. Designed to run on a
Raspberry Pi Zero W under a systemd timer.

## How it works

```
reddit.com/r/<sub>.json    (default listing, same as the browser view)
        |
        v
  pick first post that's a direct image (skip galleries/videos/text)
        |
        v
  download to /tmp
        |
        v
  Pillow:  EXIF-orient -> crop-to-fill 800x480 -> Floyd-Steinberg dither
           against the 7 Waveshare inks (black/white/green/blue/red/yellow/orange)
        |
        v
  save BMP to /var/lib/epaper-reddit/current.bmp
        |
        v
  waveshare_epd.epd7in3f.EPD().display(epd.getbuffer(img))  -> sleep()
```

The dither happens in Pillow (not in the Waveshare driver) so that we get
proper Floyd-Steinberg error diffusion instead of nearest-color quantization,
which makes a huge difference on photographic content.

## Project layout

```
epaper_reddit/
  __main__.py    # CLI entry: python -m epaper_reddit
  config.py      # TOML loader + dataclass schema
  reddit.py      # /r/<sub>/top.json -> first usable image post
  image.py       # resize + dither to 7-color palette + BMP save
  display.py     # waveshare_epd wrapper (with sleep on exit)
systemd/
  epaper-reddit.service
  epaper-reddit.timer
config.example.toml
install.sh
requirements.txt
```

## Install on the Pi

Flash Raspberry Pi OS Lite, get the Pi on Wi-Fi, SSH in, then:

```bash
git clone <this repo> ~/epaper-reddit
cd ~/epaper-reddit
sudo ./install.sh
sudoedit /etc/epaper-reddit/config.toml   # set User-Agent and subreddit
sudo systemctl start epaper-reddit.service
journalctl -u epaper-reddit -b
```

`install.sh` will:

1. enable SPI
2. install Python + Pillow + RPi.GPIO + spidev via apt
3. clone the official Waveshare [e-Paper](https://github.com/waveshare/e-Paper)
   repo to `/opt/waveshare-epaper`
4. copy this project to `/opt/epaper-reddit`
5. drop a config at `/etc/epaper-reddit/config.toml`
6. enable the systemd timer (defaults to hourly)

## Configuration

Everything is in `/etc/epaper-reddit/config.toml`. The most useful knobs:

| Key                       | Default      | Notes                              |
| ------------------------- | ------------ | ---------------------------------- |
| `[reddit].subreddit`      | `earthporn`  | Any SFW subreddit with image posts.|
| `[reddit].max_candidates` | `25`         | Posts to walk before giving up.    |
| `[reddit].user_agent`     | placeholder  | **Set this** — Reddit rate-limits generic UAs. |
| `[image].fit`             | `crop`       | `crop` / `fit` (letterbox) / `stretch` |
| `[image].dither`          | `true`       | Off = posterized; on = recommended.|
| `[display].driver`        | `epd7in3f`   | Module name in `waveshare_epd/`.   |
| `[display].dry_run`       | `false`      | Skip the actual SPI push.          |

Override any field on the command line with `--subreddit`, `--driver`,
`--dry-run`, etc. Run `python -m epaper_reddit --help` for the full list.

## Refresh interval

Edit `OnUnitActiveSec=` in `systemd/epaper-reddit.timer` (or
`/etc/systemd/system/epaper-reddit.timer` after install). E-paper has a
limited update count over its lifetime — Waveshare's 7-color panels are
rated for tens of thousands of refreshes, so hourly is fine, but going
sub-minute is a bad idea.

## Testing on a non-Pi machine

Everything except the actual SPI push works on macOS or any Linux box:

```bash
pip install requests Pillow tomli
python -m epaper_reddit --dry-run --subreddit earthporn -v
```

Or test the conversion pipeline with a local image:

```bash
python -m epaper_reddit --from-file ~/Pictures/test.jpg --dry-run --output-bmp /tmp/test.bmp
```

The BMP it writes is a normal RGB BMP using only the 7 panel colors —
opening it in Preview/feh shows roughly what the panel will look like.

## Other Waveshare panels

Swap `[display].driver` to the matching `waveshare_epd.<name>` module.
If the new panel has a different palette (e.g. the 4.01" 7-color uses the
same one, but the B/W/Red panels use 3 colors), edit
`WAVESHARE_7C_PALETTE_RGB` in `epaper_reddit/image.py`.

## Caveats

- `r/earthporn` is SFW, but the script does not filter NSFW content. If you
  point it at a sub that mixes content, add an `over_18` check in
  `reddit._candidate_url`.
- Reddit's public JSON endpoint will rate-limit you if your User-Agent looks
  generic. Set `[reddit].user_agent` to something like
  `epaper-reddit/1.0 (by /u/yourname)`.
- The driver requires `User=root` in the service unit because `/dev/spidev0.0`
  and the GPIO chardev are root-owned by default. If you want non-root, add
  udev rules and change `User=` accordingly.

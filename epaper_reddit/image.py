"""Image processing — fit to 800x480 and dither to the Waveshare 7-color palette.

The 7.3" "F" panel (epd7in3f / B0BMQ83W7W) physically renders only these
seven inks:

    Black  (0,   0,   0)
    White  (255, 255, 255)
    Green  (0,   255, 0)
    Blue   (0,   0,   255)
    Red    (255, 0,   0)
    Yellow (255, 255, 0)
    Orange (255, 128, 0)

Anything else has to be approximated. Floyd-Steinberg dithering against this
exact palette gives much better-looking results than the nearest-color mapping
the Waveshare lib does on its own, so we do the dither here in Pillow and pass
the already-quantized image to the display driver.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Tuple

from PIL import Image, ImageOps

log = logging.getLogger(__name__)

# Order matters only for human readability; the values are what go into the
# palette image. We pad to 256 colors with black so PIL accepts it as a P-mode
# palette.
WAVESHARE_7C_PALETTE_RGB: list[Tuple[int, int, int]] = [
    (0, 0, 0),         # Black
    (255, 255, 255),   # White
    (0, 255, 0),       # Green
    (0, 0, 255),       # Blue
    (255, 0, 0),       # Red
    (255, 255, 0),     # Yellow
    (255, 128, 0),     # Orange
]


def _palette_image() -> Image.Image:
    """Return a 1x1 P-mode image whose palette is the 7 Waveshare colors.

    Pillow's quantize(palette=...) needs a P-mode image; the first N*3 bytes of
    its palette become the available colors. We pad the rest with black so PIL
    is happy, but the dither will only ever pick from the first 7 entries
    because they're the only ones we ever map *to*.
    """
    flat: list[int] = []
    for rgb in WAVESHARE_7C_PALETTE_RGB:
        flat.extend(rgb)
    # Pad to 768 bytes (256 colors * 3) by repeating black.
    flat.extend([0, 0, 0] * (256 - len(WAVESHARE_7C_PALETTE_RGB)))

    pal_img = Image.new("P", (1, 1))
    pal_img.putpalette(flat)
    return pal_img


_PALETTE_IMG = _palette_image()


def _resize_crop(img: Image.Image, size: Tuple[int, int]) -> Image.Image:
    """Scale-and-crop so the result exactly fills `size` (no letterboxing)."""
    return ImageOps.fit(img, size, method=Image.LANCZOS, centering=(0.5, 0.5))


def _resize_fit(img: Image.Image, size: Tuple[int, int]) -> Image.Image:
    """Scale to fit entirely inside `size`, padding with white."""
    fitted = ImageOps.contain(img, size, method=Image.LANCZOS)
    canvas = Image.new("RGB", size, (255, 255, 255))
    x = (size[0] - fitted.width) // 2
    y = (size[1] - fitted.height) // 2
    canvas.paste(fitted, (x, y))
    return canvas


def _resize_stretch(img: Image.Image, size: Tuple[int, int]) -> Image.Image:
    return img.resize(size, Image.LANCZOS)


_FIT_FUNCS = {
    "crop": _resize_crop,
    "fit": _resize_fit,
    "stretch": _resize_stretch,
}


def prepare_image(
    src_path: str | Path,
    width: int = 800,
    height: int = 480,
    fit: str = "crop",
    dither: bool = True,
) -> Image.Image:
    """Open `src_path`, fit it to (width, height), and dither to the 7-color palette.

    Returns a P-mode image whose pixels are indices into a palette that begins
    with the 7 Waveshare colors. The Waveshare driver's getbuffer() will then
    map those colors into framebuffer bytes.
    """
    if fit not in _FIT_FUNCS:
        raise ValueError(f"Unknown fit mode: {fit!r}. Use one of {list(_FIT_FUNCS)}.")

    with Image.open(src_path) as raw:
        # Honour EXIF rotation; convert away from RGBA so paste/crop don't
        # leave alpha noise behind.
        oriented = ImageOps.exif_transpose(raw).convert("RGB")

    sized = _FIT_FUNCS[fit](oriented, (width, height))

    dither_method = Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE
    quantized = sized.quantize(
        palette=_PALETTE_IMG,
        dither=dither_method,
    )
    log.debug(
        "Prepared image: src=%s -> %dx%d fit=%s dither=%s",
        src_path, width, height, fit, dither,
    )
    return quantized


def save_bmp(img: Image.Image, dest_path: str | Path) -> str:
    """Save `img` as a 24-bit BMP at `dest_path` (creates parent dirs)."""
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Convert back to RGB so the BMP is universally viewable on a desktop;
    # the on-display rendering goes through epd.getbuffer() which accepts
    # either P-mode or RGB.
    img.convert("RGB").save(dest, format="BMP")
    log.debug("Saved BMP -> %s", dest)
    return str(dest)

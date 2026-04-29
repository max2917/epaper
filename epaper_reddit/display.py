"""Thin wrapper over Waveshare's epd7in3f driver.

We import waveshare_epd lazily so that:
  - `--dry-run` works on a non-Pi dev machine without RPi.GPIO installed
  - import errors are surfaced with a useful hint rather than at module load
"""
from __future__ import annotations

import importlib
import logging
from contextlib import contextmanager
from typing import Iterator

from PIL import Image

log = logging.getLogger(__name__)


class DisplayError(RuntimeError):
    pass


@contextmanager
def _open_panel(driver_name: str) -> Iterator[object]:
    """Init the panel, yield the driver instance, always sleep() on exit.

    Sleeping the panel is important — Waveshare's color e-paper specifies
    that leaving the panel powered between updates can damage it. We always
    put it to sleep, even on exception.
    """
    try:
        module = importlib.import_module(f"waveshare_epd.{driver_name}")
    except ImportError as e:
        raise DisplayError(
            f"Could not import waveshare_epd.{driver_name}. Make sure the "
            "Waveshare e-Paper repo is on PYTHONPATH (install.sh handles this)."
        ) from e

    epd = module.EPD()
    log.debug("Initializing %s (%dx%d)", driver_name, epd.width, epd.height)
    epd.init()
    try:
        yield epd
    finally:
        try:
            log.debug("Sleeping panel")
            epd.sleep()
        except Exception:  # noqa: BLE001 — best-effort cleanup
            log.exception("Failed to sleep panel cleanly")


def push_to_display(img: Image.Image, driver_name: str = "epd7in3f", dry_run: bool = False) -> None:
    """Render `img` to the panel. With `dry_run=True`, just log what would happen."""
    if dry_run:
        log.info("[dry-run] would push %s image to %s", img.size, driver_name)
        return

    with _open_panel(driver_name) as epd:
        # epd.getbuffer expects an RGB or P-mode Pillow image at the panel's
        # native resolution. We pass through whichever the caller has — the
        # driver is happy with either.
        log.info("Pushing %s image to %s", img.size, driver_name)
        epd.display(epd.getbuffer(img))

"""CLI entry point: python -m epaper_reddit [...].

Pipeline:
    1. Read config (TOML + CLI overrides).
    2. Pull r/<sub>/top.json, find first image post.
    3. Download image to a temp file.
    4. Crop-to-fill 800x480 + Floyd-Steinberg dither to 7-color palette.
    5. Save BMP.
    6. Push to the Waveshare panel (or skip with --dry-run).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from pathlib import Path
from typing import Optional

from .config import Config, load_config
from .image import prepare_image, save_bmp
from .reddit import RedditError, download_image, fetch_top_image

log = logging.getLogger("epaper_reddit")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="epaper-reddit",
        description="Pull the top image from a subreddit and show it on a Waveshare 7.3in 7-color e-paper.",
    )
    p.add_argument("--config", help="Path to TOML config file.", default=None)
    p.add_argument("--subreddit", help="Override [reddit].subreddit", default=None)
    p.add_argument("--driver", help="Override [display].driver (e.g. epd7in3f)", default=None)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Do everything except push to the panel. Useful on a non-Pi machine.",
    )
    p.add_argument(
        "--from-file",
        help="Skip Reddit; use this local image as input. Handy for testing the BMP pipeline.",
        default=None,
    )
    p.add_argument(
        "--output-bmp",
        help="Override [image].output_bmp path.",
        default=None,
    )
    p.add_argument("-v", "--verbose", action="store_true", help="DEBUG-level logging.")
    return p


def _apply_cli_overrides(cfg: Config, args: argparse.Namespace) -> None:
    if args.subreddit:
        cfg.reddit.subreddit = args.subreddit
    if args.driver:
        cfg.display.driver = args.driver
    if args.dry_run:
        cfg.display.dry_run = True
    if args.output_bmp:
        cfg.image.output_bmp = args.output_bmp
    if args.verbose:
        cfg.log.level = "DEBUG"


def _setup_logging(level_name: str) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _state_paths(state_dir: str) -> tuple[Optional[Path], Optional[Path]]:
    """Returns (state_dir_path, history_file) or (None, None) if disabled."""
    if not state_dir:
        return None, None
    d = Path(state_dir)
    return d, d / "recent_history.json"


def _load_recent_ids(history_file: Optional[Path]) -> list[str]:
    """Read the rolling list of recently-shown post IDs (most recent first)."""
    if not history_file or not history_file.exists():
        return []
    try:
        data = json.loads(history_file.read_text())
        ids = data.get("recent_ids")
        if isinstance(ids, list):
            return [i for i in ids if isinstance(i, str)]
        return []
    except Exception:  # noqa: BLE001 — corrupt state file shouldn't crash the run
        log.warning("Could not read %s; ignoring", history_file)
        return []


def _record_shown(history_file: Optional[Path], post_id: str, history_size: int) -> None:
    """Prepend `post_id` to the rolling history and trim to `history_size` entries."""
    if not history_file or history_size < 1:
        return
    existing = _load_recent_ids(history_file)
    updated = [post_id] + [i for i in existing if i != post_id]
    updated = updated[:history_size]
    history_file.parent.mkdir(parents=True, exist_ok=True)
    history_file.write_text(json.dumps({"recent_ids": updated}))


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    cfg = load_config(args.config)
    _apply_cli_overrides(cfg, args)
    _setup_logging(cfg.log.level)

    log.info(
        "Starting epaper-reddit: subreddit=%s dry_run=%s",
        cfg.reddit.subreddit, cfg.display.dry_run,
    )

    # Reddit -> local image file ------------------------------------------------
    tmp_download: Optional[Path] = None
    try:
        if args.from_file:
            local_image = Path(args.from_file)
            if not local_image.exists():
                log.error("--from-file points at a missing path: %s", local_image)
                return 2
            log.info("Using local file %s (skipping Reddit)", local_image)
            post_id: Optional[str] = None
        else:
            state_dir, history_file = _state_paths(cfg.image.state_dir)
            recent_ids = set(_load_recent_ids(history_file))
            try:
                post = fetch_top_image(
                    subreddit=cfg.reddit.subreddit,
                    max_candidates=cfg.reddit.max_candidates,
                    user_agent=cfg.reddit.user_agent,
                    skip_post_ids=recent_ids,
                )
            except RedditError as e:
                log.warning("No new image to display, skipping refresh: %s", e)
                return 0

            # Download to a temp file. We don't keep the original around — only the
            # final BMP. If you want the source, look at post.url in the logs.
            tmp_download = Path(tempfile.gettempdir()) / f"epaper_reddit_{post.id}"
            try:
                download_image(post.url, cfg.reddit.user_agent, str(tmp_download))
            except Exception as e:  # noqa: BLE001
                log.error("Download failed: %s", e)
                return 4
            local_image = tmp_download
            post_id = post.id

        # Image processing ------------------------------------------------------
        try:
            prepared = prepare_image(
                local_image,
                width=cfg.image.width,
                height=cfg.image.height,
                fit=cfg.image.fit,
                dither=cfg.image.dither,
            )
        except Exception as e:  # noqa: BLE001
            log.exception("Image processing failed: %s", e)
            return 5

        bmp_path = cfg.image.output_bmp
        if not cfg.image.keep_bmp:
            # Still write one — the display driver wants a Pillow image, but writing
            # the BMP is cheap and useful for debugging. We just put it in /tmp.
            bmp_path = str(Path(tempfile.gettempdir()) / "epaper_reddit_current.bmp")
        save_bmp(prepared, bmp_path)
        log.info("BMP saved to %s", bmp_path)

        # Display ---------------------------------------------------------------
        # Import display lazily so dry-run works without RPi.GPIO installed.
        from .display import DisplayError, push_to_display
        try:
            push_to_display(prepared, driver_name=cfg.display.driver, dry_run=cfg.display.dry_run)
        except DisplayError as e:
            log.error("Display failed: %s", e)
            return 6

        # Record what we showed so the next run can skip it (if Reddit is the source).
        if post_id and not args.from_file:
            _, history_file = _state_paths(cfg.image.state_dir)
            _record_shown(history_file, post_id, cfg.image.recent_history_size)

        log.info("Done.")
        return 0
    finally:
        if tmp_download is not None:
            tmp_download.unlink(missing_ok=True)
            log.debug("Removed temp download %s", tmp_download)


if __name__ == "__main__":
    sys.exit(main())

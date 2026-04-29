"""Config loading. TOML on disk + CLI overrides."""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


def _load_toml_module():
    """tomllib is stdlib on 3.11+; on older Pis we fall back to the `tomli`
    backport. We only import it when load_config() actually needs to parse a
    file, so missing tomli isn't fatal for users running with all defaults."""
    if sys.version_info >= (3, 11):
        import tomllib  # type: ignore[import-not-found]
        return tomllib
    try:
        import tomli  # type: ignore[import-not-found]
        return tomli
    except ImportError as e:
        raise RuntimeError(
            "Reading a TOML config requires the 'tomli' package on Python <3.11. "
            "Install it with: pip install tomli"
        ) from e


@dataclass
class RedditConfig:
    subreddit: str = "earthporn"
    max_candidates: int = 25
    user_agent: str = "epaper-reddit/1.0 (by /u/yourname)"


@dataclass
class ImageConfig:
    width: int = 800
    height: int = 480
    fit: str = "crop"
    dither: bool = True
    keep_bmp: bool = True
    output_bmp: str = "/var/lib/epaper-reddit/current.bmp"
    state_dir: str = "/var/lib/epaper-reddit"


@dataclass
class DisplayConfig:
    driver: str = "epd7in3f"
    dry_run: bool = False


@dataclass
class LogConfig:
    level: str = "INFO"


@dataclass
class Config:
    reddit: RedditConfig = field(default_factory=RedditConfig)
    image: ImageConfig = field(default_factory=ImageConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    log: LogConfig = field(default_factory=LogConfig)


def _merge_section(base: Any, overrides: dict) -> None:
    """Apply a dict of overrides onto a dataclass instance, in-place."""
    for key, val in overrides.items():
        if hasattr(base, key):
            setattr(base, key, val)
        # Unknown keys are ignored on purpose so old configs don't break new code.


def load_config(path: Optional[str | Path]) -> Config:
    """Load a config file if `path` is given, otherwise return defaults."""
    cfg = Config()
    if not path:
        return cfg
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p}")
    toml_mod = _load_toml_module()
    with p.open("rb") as f:
        data = toml_mod.load(f)
    for section_name in ("reddit", "image", "display", "log"):
        section = data.get(section_name) or {}
        _merge_section(getattr(cfg, section_name), section)
    return cfg

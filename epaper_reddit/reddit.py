"""Reddit fetcher — find the first post on a subreddit that's a usable image.

Uses the public JSON endpoint (no auth). Hits the default subreddit listing
(equivalent to visiting reddit.com/r/<sub> in a browser — currently "hot")
and returns the first entry that points to a direct JPG/PNG, skipping
galleries, videos, text posts, and deleted/removed posts.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterator, Optional

import requests

log = logging.getLogger(__name__)

# Hosts/extensions we treat as "this is definitely a still image".
_IMAGE_EXT_RE = re.compile(r"\.(jpe?g|png|webp)(\?|$)", re.IGNORECASE)
_IMAGE_HOSTS = ("i.redd.it", "i.imgur.com")


@dataclass
class RedditPost:
    """A post we'd consider showing on the display."""

    id: str
    title: str
    url: str           # Direct image URL.
    permalink: str     # https://reddit.com/... — for logging.
    author: str
    score: int


class RedditError(RuntimeError):
    """Raised when we couldn't get a usable post from Reddit."""


def _candidate_url(post_data: dict) -> Optional[str]:
    """Return a direct image URL for this post, or None if it isn't an image post.

    Reddit posts have a few shapes; we cover the common ones:
    - direct image: data.url ends in .jpg/.png/.webp
    - i.redd.it / i.imgur.com hosted: same, sometimes with query strings
    - reddit-hosted preview: data.preview.images[0].source.url
    Galleries (data.is_gallery=true), videos (is_video=true), self-posts
    (is_self=true), and removed/deleted posts return None.
    """
    if post_data.get("is_self"):
        return None
    if post_data.get("is_video"):
        return None
    if post_data.get("is_gallery"):
        # Per the user's preference we skip galleries entirely.
        return None
    if post_data.get("removed_by_category") or post_data.get("removed"):
        return None

    url = post_data.get("url_overridden_by_dest") or post_data.get("url") or ""
    if _IMAGE_EXT_RE.search(url):
        return url
    if any(host in url for host in _IMAGE_HOSTS):
        # i.imgur.com sometimes serves /abc (no extension) — append .jpg as a
        # last-resort hint; imgur will redirect.
        if not _IMAGE_EXT_RE.search(url):
            return url + ".jpg"
        return url

    # Fall back to Reddit's own preview if it has one. The preview URL is
    # HTML-escaped (&amp;) — un-escape for requests.
    preview = post_data.get("preview", {})
    images = preview.get("images") or []
    if images:
        src = images[0].get("source", {}).get("url")
        if src:
            return src.replace("&amp;", "&")

    return None


def _iter_posts(subreddit: str, limit: int, user_agent: str) -> Iterator[dict]:
    """Yield raw post dicts from the default /r/<sub>.json listing (hot)."""
    url = f"https://www.reddit.com/r/{subreddit}.json"
    params = {"limit": limit}
    headers = {"User-Agent": user_agent}

    log.debug("GET %s params=%s", url, params)
    resp = requests.get(url, params=params, headers=headers, timeout=15)
    if resp.status_code == 429:
        raise RedditError("Reddit rate-limited us (HTTP 429). Set a unique User-Agent.")
    resp.raise_for_status()
    payload = resp.json()
    children = payload.get("data", {}).get("children", []) or []
    for child in children:
        data = child.get("data") or {}
        if data:
            yield data


def fetch_top_image(
    subreddit: str,
    max_candidates: int = 25,
    user_agent: str = "epaper-reddit/1.0",
    skip_post_ids: Optional[set[str]] = None,
) -> RedditPost:
    """Return the first post on the subreddit's default listing that's a direct image.

    Walks /r/<sub>.json (the same listing you'd see in a browser at
    reddit.com/r/<sub>) and returns the first qualifying image post. Raises
    RedditError if none of the first `max_candidates` posts qualify.
    `skip_post_ids` lets the caller exclude posts already shown.
    """
    skip_post_ids = skip_post_ids or set()
    examined = 0
    for data in _iter_posts(subreddit, max_candidates, user_agent):
        examined += 1
        post_id = data.get("id", "")
        if post_id in skip_post_ids:
            log.debug("Skipping already-shown post %s", post_id)
            continue
        url = _candidate_url(data)
        if not url:
            log.debug("Skipping non-image post %s (%s)", post_id, data.get("title", ""))
            continue
        log.info(
            "Picked r/%s post %s '%s' (score=%s)",
            subreddit,
            post_id,
            (data.get("title") or "")[:60],
            data.get("score"),
        )
        return RedditPost(
            id=post_id,
            title=data.get("title") or "",
            url=url,
            permalink="https://reddit.com" + (data.get("permalink") or ""),
            author=data.get("author") or "",
            score=int(data.get("score") or 0),
        )

    raise RedditError(
        f"No usable image found in the first {examined} posts of r/{subreddit}"
    )


def download_image(url: str, user_agent: str, dest_path: str) -> str:
    """Stream the image to disk. Returns dest_path."""
    headers = {"User-Agent": user_agent}
    log.debug("Downloading %s", url)
    with requests.get(url, headers=headers, timeout=30, stream=True) as resp:
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=64 * 1024):
                if chunk:
                    f.write(chunk)
    log.debug("Wrote %s", dest_path)
    return dest_path

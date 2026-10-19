"""On-demand wiki page cache. Seven days, like snaps. No bulk crawl."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from battlebuddy.databank.fetch import FetchResult, fetch_page
from battlebuddy.databank.slug import game_slug
from battlebuddy.sources.store import games_root

KEEP_DAYS = 7
_PREFIX = "page-"
_TEXT_CAP = 12_000


def cache_dir(game: str | None, home: Path | None = None) -> Path:
    return games_root(home) / game_slug(game) / "cache"


def cache_id(url: str) -> str:
    return hashlib.sha256((url or "").encode("utf-8")).hexdigest()[:16]


def prune_cache(
    game: str | None,
    home: Path | None = None,
    *,
    now: float | None = None,
    keep_days: int = KEEP_DAYS,
) -> int:
    folder = cache_dir(game, home)
    if not folder.is_dir():
        return 0
    moment = time.time() if now is None else float(now)
    cutoff = moment - (max(0, int(keep_days)) * 86400)
    removed = 0
    for path in folder.glob(f"{_PREFIX}*.json"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def fetch_cached(
    url: str,
    game: str | None,
    home: Path | None = None,
    *,
    fetch_fn: object | None = None,
) -> FetchResult:
    """Return a cached page when fresh. Otherwise GET once and file it."""
    prune_cache(game, home)
    path = cache_dir(game, home) / f"{_PREFIX}{cache_id(url)}.json"
    cached = _read(path)
    if cached is not None:
        return cached
    getter = fetch_fn if fetch_fn is not None else fetch_page
    result = getter(url)
    if getattr(result, "ok", False):
        _write(path, result)
    return result


def _read(path: Path) -> FetchResult | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    text = str(raw.get("text") or "")
    url = str(raw.get("url") or "")
    if not text.strip() or not url:
        return None
    return FetchResult(
        ok=True,
        url=url,
        message="cached",
        title=str(raw.get("title") or ""),
        text=text,
        kind="ok",
    )


def _write(path: Path, result: FetchResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (result.text or "")[:_TEXT_CAP]
    payload = {
        "url": result.url,
        "title": result.title,
        "text": text,
    }
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)

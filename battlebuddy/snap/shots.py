"""Screenshots stay under the Battle Buddy home. Seven-day clear. Nothing uploaded."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from battlebuddy.memory.store import default_home

KEEP_DAYS = 7
_PREFIX = "snap-"


def snap_dir(home: Path | None = None) -> Path:
    base = home if home is not None else default_home()
    return base / "snaps"


def fitted_size(width: int, height: int, max_width: int = 1280) -> tuple[int, int]:
    """Cap a full-monitor grab before OCR upscales it again."""
    wide = max(1, int(width))
    tall = max(1, int(height))
    limit = max(1, int(max_width))
    if wide <= limit:
        return wide, tall
    scaled = max(1, int(tall * (limit / wide)))
    return limit, scaled


def save_snap(image: object, home: Path | None = None, *, now: datetime | None = None) -> Path:
    folder = snap_dir(home)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = (now if now is not None else datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    path = folder / f"{_PREFIX}{stamp}.png"
    image.save(path, format="PNG")  # type: ignore[attr-defined]
    return path


def prune_snaps(
    home: Path | None = None,
    *,
    now: float | None = None,
    keep_days: int = KEEP_DAYS,
) -> int:
    """Delete snap images older than keep_days. Returns how many went away."""
    folder = snap_dir(home)
    if not folder.is_dir():
        return 0
    moment = time.time() if now is None else float(now)
    cutoff = moment - (max(0, int(keep_days)) * 86400)
    removed = 0
    for path in folder.glob(f"{_PREFIX}*.png"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed

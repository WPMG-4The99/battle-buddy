"""Newest local screenshot. Paths only. No process inject."""

from __future__ import annotations

import os
from pathlib import Path

from battlebuddy.games import corsair_cove as cove
from battlebuddy.steam.library import library_roots, steam_root

_IMAGE = {".png", ".jpg", ".jpeg", ".webp"}
_SKIP_NAME = ("thumb", ".tmp")


def _local_appdata() -> Path:
    raw = (os.environ.get("LOCALAPPDATA") or "").strip()
    if raw:
        return Path(raw)
    return Path.home() / "AppData" / "Local"


def screenshot_roots(
    *,
    extra: list[Path] | None = None,
    local_appdata: Path | None = None,
    steam: Path | None = None,
    home: Path | None = None,
) -> list[Path]:
    """Known screenshot folders. Never walk the 29GB install tree."""
    appdata = local_appdata if local_appdata is not None else _local_appdata()
    user = home if home is not None else Path.home()
    found: list[Path] = [
        cove.saved_root(appdata) / "Screenshots",
        user / "Pictures" / "Screenshots",
    ]
    raw_env = (os.environ.get("BATTLEBUDDY_SHOTS") or "").strip()
    if raw_env:
        found.append(Path(raw_env))
    try:
        for library in library_roots(steam if steam is not None else steam_root()):
            remote = library / "userdata"
            if not remote.is_dir():
                continue
            for user_dir in remote.iterdir():
                shots = user_dir / "760" / "remote" / cove.APP_ID / "screenshots"
                found.append(shots)
    except OSError:
        pass
    if extra:
        found.extend(extra)
    return found


def newest_screenshot(roots: list[Path] | None = None) -> Path | None:
    """Newest image by mtime. Skip thumbs. Do not open the file."""
    folders = roots if roots is not None else screenshot_roots()
    hits: list[Path] = []
    for folder in folders:
        if not folder.is_dir():
            continue
        try:
            for path in folder.rglob("*"):
                if not path.is_file():
                    continue
                if path.suffix.lower() not in _IMAGE:
                    continue
                name = path.name.lower()
                if any(token in name for token in _SKIP_NAME):
                    continue
                hits.append(path)
        except OSError:
            continue
    if not hits:
        return None
    return max(hits, key=lambda item: item.stat().st_mtime)

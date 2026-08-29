"""Game display name → folder slug. Manor Lords → manor-lords."""

from __future__ import annotations

import re

_GENERAL = "general"
_SPLIT = re.compile(r"[^a-z0-9]+")


def game_slug(game: str | None) -> str:
    """Folder name for a game. Empty or no detect → general."""
    text = (game or "").strip().lower()
    if not text:
        return _GENERAL
    parts = [part for part in _SPLIT.split(text) if part]
    slug = "-".join(parts)
    return slug if slug else _GENERAL


def databank_label(game: str | None) -> str:
    """Quiet header: DATABANK  ·  manor-lords."""
    return f"DATABANK  ·  {game_slug(game)}"

"""Snap text as a sourced fact for one game. No supersede, no brief, no tidy."""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from battlebuddy.databank.slug import game_slug
from battlebuddy.memory.catalog import catalog_path

SOURCE_SNAP = "snap"


@dataclass(frozen=True)
class SnapFact:
    id: str
    game: str
    text: str
    source: str
    created_at: str


def add_snap_fact(
    text: str,
    game: str | None,
    home: Path | None = None,
    *,
    now: datetime | None = None,
) -> SnapFact:
    body = (text or "").strip()
    if not body:
        raise ValueError("Snap fact text is empty.")
    if len(body) > 4000:
        body = body[:4000].rstrip()
    fact = SnapFact(
        id=uuid.uuid4().hex[:8],
        game=game_slug(game),
        text=body,
        source=SOURCE_SNAP,
        created_at=(now if now is not None else datetime.now(timezone.utc)).isoformat(),
    )
    conn = _connect(home)
    try:
        conn.execute(
            "INSERT INTO facts (id, game, text, source, created_at) VALUES (?, ?, ?, ?, ?)",
            (fact.id, fact.game, fact.text, fact.source, fact.created_at),
        )
        conn.commit()
    finally:
        conn.close()
    return fact


def list_snap_facts(game: str | None, home: Path | None = None) -> list[SnapFact]:
    """Facts for this game only. Another title's snaps stay out."""
    wanted = game_slug(game)
    conn = _connect(home)
    try:
        rows = conn.execute(
            "SELECT id, game, text, source, created_at FROM facts "
            "WHERE source = ? AND game = ? ORDER BY created_at DESC",
            (SOURCE_SNAP, wanted),
        ).fetchall()
    finally:
        conn.close()
    return [
        SnapFact(
            id=str(row["id"]),
            game=str(row["game"]),
            text=str(row["text"]),
            source=str(row["source"]),
            created_at=str(row["created_at"]),
        )
        for row in rows
    ]


def _connect(home: Path | None) -> sqlite3.Connection:
    path = catalog_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS facts (
            id TEXT PRIMARY KEY,
            game TEXT NOT NULL,
            text TEXT NOT NULL,
            source TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn

"""Durable game / note catalog. SQLite. Same BATTLEBUDDY_HOME. No account."""

from __future__ import annotations

import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from battlebuddy.memory.store import default_home


def _game_slug(game: str | None) -> str:
    from battlebuddy.databank.slug import game_slug

    return game_slug(game)

CATALOG_NAME = "catalog.sqlite"
SOURCE_SCAN = "scan"
SOURCE_WIKI = "wiki"
SOURCE_NOTE = "note"

_NOTE = re.compile(
    r"^\s*note(?:\s+for\s+(?P<game>.+?):)?\s*:?\s+(?P<text>.+?)\s*$",
    re.IGNORECASE,
)
_GAMES = re.compile(r"^\s*(?:list\s+)?games\s*$", re.IGNORECASE)
_NOTES = re.compile(r"^\s*(?:list\s+)?notes\s*$", re.IGNORECASE)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def catalog_path(home: Path | None = None) -> Path:
    base = home if home is not None else default_home()
    return base / CATALOG_NAME


@dataclass(frozen=True)
class SeenGame:
    slug: str
    name: str
    first_seen_at: str
    last_seen_at: str
    source: str


@dataclass(frozen=True)
class Note:
    id: str
    text: str
    game: str | None
    created_at: str

    def page_body(self) -> str:
        title = f"Note · {self.game}" if self.game else "Note"
        return f"{title}\nlocal-note:{self.id}\n\n{self.text.rstrip()}\n"


@dataclass(frozen=True)
class ParsedNote:
    text: str
    game: str | None


def parse_note(line: str) -> ParsedNote | None:
    raw = " ".join((line or "").split())
    if not raw:
        return None
    match = _NOTE.match(raw)
    if not match:
        return None
    text = (match.group("text") or "").strip()
    if not text:
        return None
    game = (match.group("game") or "").strip() or None
    return ParsedNote(text=text, game=game)


def is_games_command(line: str) -> bool:
    return bool(_GAMES.match(" ".join((line or "").split())))


def is_notes_command(line: str) -> bool:
    return bool(_NOTES.match(" ".join((line or "").split())))


def is_catalog_command(line: str) -> bool:
    raw = " ".join((line or "").split())
    return bool(parse_note(raw) or is_games_command(raw) or is_notes_command(raw))


def seen_on_disk_line(games: list[SeenGame], notes: list[Note]) -> str:
    """One muted line. Games and notes that survive restart."""
    if not games and not notes:
        return "No games or notes on disk."
    parts = [item.name for item in games]
    if len(notes) == 1:
        parts.append(f"note: {_clip(notes[0].text)}")
    elif notes:
        parts.append(f"{len(notes)} notes")
    return "On disk: " + " · ".join(parts)


def _clip(text: str, limit: int = 40) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."


class KnowledgeCatalog:
    """Games from SCAN / wiki plus optional notes. Offline. No key."""

    def __init__(self, home: Path | None = None) -> None:
        self.home = home if home is not None else default_home()
        self.path = catalog_path(self.home)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS games (
                slug TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                source TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                game TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
        return conn

    def remember_game(
        self,
        name: str,
        *,
        source: str = SOURCE_SCAN,
        now: datetime | None = None,
    ) -> SeenGame | None:
        clean = (name or "").strip()
        if not clean:
            return None
        slug = _game_slug(clean)
        if slug == "general":
            return None
        stamp = (now if now is not None else _utc_now()).isoformat()
        kind = (source or SOURCE_SCAN).strip() or SOURCE_SCAN
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT slug, name, first_seen_at, last_seen_at, source FROM games WHERE slug = ?",
                (slug,),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO games (slug, name, first_seen_at, last_seen_at, source) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (slug, clean, stamp, stamp, kind),
                )
            else:
                conn.execute(
                    "UPDATE games SET name = ?, last_seen_at = ? WHERE slug = ?",
                    (clean, stamp, slug),
                )
            conn.commit()
        finally:
            conn.close()
        found = self.get_game(slug)
        return found

    def get_game(self, slug: str) -> SeenGame | None:
        key = (slug or "").strip()
        if not key:
            return None
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT slug, name, first_seen_at, last_seen_at, source FROM games WHERE slug = ?",
                (key,),
            ).fetchone()
        finally:
            conn.close()
        return _game_from_row(row)

    def list_games(self) -> list[SeenGame]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT slug, name, first_seen_at, last_seen_at, source "
                "FROM games ORDER BY last_seen_at DESC, name COLLATE NOCASE"
            ).fetchall()
        finally:
            conn.close()
        return [item for item in (_game_from_row(row) for row in rows) if item is not None]

    def last_game(self) -> str | None:
        games = self.list_games()
        if not games:
            return None
        return games[0].name

    def add_note(
        self,
        text: str,
        game: str | None = None,
        now: datetime | None = None,
    ) -> Note:
        clean = (text or "").strip()
        if not clean:
            raise ValueError("Note text is empty.")
        label = (game or "").strip() or None
        stamp = (now if now is not None else _utc_now()).isoformat()
        if label:
            self.remember_game(label, source=SOURCE_NOTE, now=now)
        note = Note(
            id=uuid.uuid4().hex[:8],
            text=clean,
            game=label,
            created_at=stamp,
        )
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO notes (id, text, game, created_at) VALUES (?, ?, ?, ?)",
                (note.id, note.text, note.game, note.created_at),
            )
            conn.commit()
        finally:
            conn.close()
        return note

    def list_notes(self, game: str | None = None) -> list[Note]:
        conn = self._connect()
        try:
            if game is None:
                rows = conn.execute(
                    "SELECT id, text, game, created_at FROM notes "
                    "ORDER BY created_at DESC"
                ).fetchall()
            else:
                slug = _game_slug(game)
                rows = conn.execute(
                    "SELECT id, text, game, created_at FROM notes "
                    "ORDER BY created_at DESC"
                ).fetchall()
                kept: list[sqlite3.Row] = []
                for row in rows:
                    name = (row["game"] or "").strip()
                    if not name or _game_slug(name) == slug:
                        kept.append(row)
                rows = kept
        finally:
            conn.close()
        return [item for item in (_note_from_row(row) for row in rows) if item is not None]

    def has_notes(self, game: str | None = None) -> bool:
        return bool(self.list_notes(game))


def _game_from_row(row: sqlite3.Row | None) -> SeenGame | None:
    if row is None:
        return None
    slug = str(row["slug"] or "").strip()
    name = str(row["name"] or "").strip()
    if not slug or not name:
        return None
    return SeenGame(
        slug=slug,
        name=name,
        first_seen_at=str(row["first_seen_at"] or ""),
        last_seen_at=str(row["last_seen_at"] or ""),
        source=str(row["source"] or SOURCE_SCAN),
    )


def _note_from_row(row: sqlite3.Row | None) -> Note | None:
    if row is None:
        return None
    note_id = str(row["id"] or "").strip()
    text = str(row["text"] or "").strip()
    if not note_id or not text:
        return None
    game = str(row["game"] or "").strip() or None
    return Note(
        id=note_id,
        text=text,
        game=game,
        created_at=str(row["created_at"] or ""),
    )

"""On-disk databank. sources.json + page text. Same BATTLEBUDDY_HOME."""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from battlebuddy.databank.slug import game_slug
from battlebuddy.memory.store import default_home


def databanks_root(home: Path | None = None) -> Path:
    """%USERPROFILE%\\.battlebuddy\\databanks (or BATTLEBUDDY_HOME)."""
    base = home if home is not None else default_home()
    return base / "databanks"


def game_dir(game: str | None, home: Path | None = None) -> Path:
    return databanks_root(home) / game_slug(game)


@dataclass
class Source:
    id: str
    url: str
    title: str
    file: str
    saved_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "file": self.file,
            "saved_at": self.saved_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Source | None:
        try:
            source_id = str(raw["id"]).strip()
            url = str(raw["url"]).strip()
            title = str(raw.get("title") or "").strip()
            file_name = str(raw["file"]).strip()
            saved_at = str(raw.get("saved_at") or "").strip()
        except (KeyError, TypeError):
            return None
        if not source_id or not url or not file_name:
            return None
        return cls(
            id=source_id,
            url=url,
            title=title,
            file=file_name,
            saved_at=saved_at,
        )


def source_id_for(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]


class DatabankStore:
    """One folder per game slug. Page text stays local. No cloud."""

    def __init__(self, home: Path | None = None) -> None:
        self.home = home if home is not None else default_home()

    def folder(self, game: str | None) -> Path:
        return game_dir(game, self.home)

    def sources_path(self, game: str | None) -> Path:
        return self.folder(game) / "sources.json"

    def list_sources(self, game: str | None) -> list[Source]:
        path = self.sources_path(game)
        if not path.is_file():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(raw, dict):
            return []
        rows = raw.get("sources", [])
        if not isinstance(rows, list):
            return []
        out: list[Source] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            parsed = Source.from_dict(item)
            if parsed is not None:
                out.append(parsed)
        return out

    def add_url(self, game: str | None, raw_url: str) -> "FetchResult":
        """GET a public page, save text, list the URL. Failures say so."""
        from battlebuddy.databank.fetch import fetch_page

        result = fetch_page(raw_url)
        if not result.ok:
            return result
        self.save_page(game, result.url, result.title, result.text)
        result.message = "Saved on disk."
        return result

    def save_page(
        self,
        game: str | None,
        url: str,
        title: str,
        text: str,
        now: datetime | None = None,
    ) -> Source:
        """Write page text and list the URL in sources.json."""
        folder = self.folder(game)
        folder.mkdir(parents=True, exist_ok=True)
        sid = source_id_for(url)
        file_name = f"{sid}.txt"
        body = _page_body(url, title, text)
        (folder / file_name).write_text(body, encoding="utf-8")
        stamp = (now if now is not None else datetime.now(timezone.utc)).isoformat()
        source = Source(
            id=sid,
            url=url,
            title=title.strip() or url,
            file=file_name,
            saved_at=stamp,
        )
        self._upsert(game, source)
        return source

    def _upsert(self, game: str | None, source: Source) -> None:
        existing = self.list_sources(game)
        kept = [item for item in existing if item.url != source.url and item.id != source.id]
        kept.append(source)
        payload = {
            "slug": game_slug(game),
            "game": (game or "").strip(),
            "sources": [item.to_dict() for item in kept],
        }
        path = self.sources_path(game)
        path.parent.mkdir(parents=True, exist_ok=True)
        blob = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(blob, encoding="utf-8")
        tmp.replace(path)


def _page_body(url: str, title: str, text: str) -> str:
    head = (title or "").strip() or "untitled"
    return f"{head}\n{url}\n\n{text.rstrip()}\n"

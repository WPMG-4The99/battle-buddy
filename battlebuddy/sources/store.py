"""Per-game wiki hub list. games/<slug>/sources.json. Not the databank page inventory."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from battlebuddy.databank.fetch import normalize_url
from battlebuddy.databank.slug import game_slug
from battlebuddy.memory.store import default_home

_MAX_HOSTS = 5


@dataclass(frozen=True)
class WikiSource:
    """One wiki hub. Search pattern is optional. Pinned ranks first."""

    name: str
    url: str
    search: str = ""
    pinned: bool = False

    def to_dict(self) -> dict[str, object]:
        row: dict[str, object] = {"name": self.name, "url": self.url}
        if self.search:
            row["search"] = self.search
        if self.pinned:
            row["pinned"] = True
        return row

    @classmethod
    def from_dict(cls, raw: object) -> WikiSource | None:
        if not isinstance(raw, dict):
            return None
        url = normalize_url(str(raw.get("url") or raw.get("href") or ""))
        if not url:
            return None
        name = " ".join(str(raw.get("name") or raw.get("title") or "").split())
        if not name:
            name = _name_from_url(url)
        search = str(raw.get("search") or raw.get("search_url") or "").strip()
        pinned = bool(raw.get("pinned"))
        return cls(name=name, url=url, search=search, pinned=pinned)


def games_root(home: Path | None = None) -> Path:
    base = home if home is not None else default_home()
    return base / "games"


def sources_path(game: str | None, home: Path | None = None) -> Path:
    return games_root(home) / game_slug(game) / "sources.json"


def needs_discover(game: str | None, home: Path | None = None) -> bool:
    """True when SCAN named a game and that game has no wiki list yet."""
    if not (game or "").strip():
        return False
    return not load_sources(game, home)


def load_sources(game: str | None, home: Path | None = None) -> list[WikiSource]:
    path = sources_path(game, home)
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows: object
    if isinstance(raw, dict):
        rows = raw.get("sources")
    else:
        rows = raw
    if not isinstance(rows, list):
        return []
    out: list[WikiSource] = []
    seen: set[str] = set()
    for item in rows:
        source = WikiSource.from_dict(item)
        if source is None or source.url in seen:
            continue
        seen.add(source.url)
        out.append(source)
    return out


def save_sources(
    game: str | None,
    sources: list[WikiSource],
    home: Path | None = None,
) -> Path:
    path = sources_path(game, home)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "game": (game or "").strip() or game_slug(game),
        "sources": [item.to_dict() for item in sources],
    }
    blob = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(blob, encoding="utf-8")
    tmp.replace(path)
    return path


def ranked_sources(game: str | None, home: Path | None = None) -> list[WikiSource]:
    """User-pinned hubs first. Then the saved order."""
    items = load_sources(game, home)
    pinned = [item for item in items if item.pinned]
    rest = [item for item in items if not item.pinned]
    return pinned + rest


def add_source(
    game: str | None,
    url: str,
    *,
    name: str = "",
    search: str = "",
    pinned: bool = False,
    home: Path | None = None,
) -> WikiSource | None:
    source = WikiSource.from_dict(
        {"name": name, "url": url, "search": search, "pinned": pinned}
    )
    if source is None:
        return None
    items = load_sources(game, home)
    next_items: list[WikiSource] = []
    replaced = False
    for item in items:
        if item.url == source.url:
            next_items.append(
                WikiSource(
                    name=source.name or item.name,
                    url=item.url,
                    search=source.search or item.search,
                    pinned=source.pinned or item.pinned,
                )
            )
            replaced = True
        else:
            next_items.append(item)
    if not replaced:
        next_items.append(source)
    save_sources(game, next_items, home)
    return source


def remove_source(game: str | None, url: str, home: Path | None = None) -> bool:
    clean = normalize_url(url) or (url or "").strip()
    if not clean:
        return False
    items = load_sources(game, home)
    kept = [item for item in items if item.url != clean]
    if len(kept) == len(items):
        return False
    save_sources(game, kept, home)
    return True


def pin_source(
    game: str | None,
    url: str,
    pinned: bool = True,
    home: Path | None = None,
) -> bool:
    clean = normalize_url(url) or (url or "").strip()
    if not clean:
        return False
    items = load_sources(game, home)
    changed = False
    next_items: list[WikiSource] = []
    for item in items:
        if item.url == clean and item.pinned != pinned:
            next_items.append(
                WikiSource(name=item.name, url=item.url, search=item.search, pinned=pinned)
            )
            changed = True
        else:
            next_items.append(item)
    if not changed:
        return False
    save_sources(game, next_items, home)
    return True


def allowed_hosts(game: str | None, home: Path | None = None) -> list[str]:
    """Hostnames for xAI allowed_websites. Pinned first. Max 5."""
    out: list[str] = []
    seen: set[str] = set()
    for item in ranked_sources(game, home):
        host = _host(item.url)
        if not host or host in seen:
            continue
        seen.add(host)
        out.append(host)
        if len(out) >= _MAX_HOSTS:
            break
    return out


def _host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _name_from_url(url: str) -> str:
    host = _host(url)
    if not host:
        return "Wiki"
    head = host.split(".")[0]
    if head in {"www", "wiki"}:
        parts = [part for part in host.split(".") if part not in {"www", "com", "net", "org", "gg"}]
        head = parts[0] if parts else host
    return head.replace("-", " ").title() + " wiki"

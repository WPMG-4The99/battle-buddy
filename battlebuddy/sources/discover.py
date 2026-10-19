"""Discover a game's main wiki hubs via xAI live search. Save the list only."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

from battlebuddy.databank.fetch import normalize_url
from battlebuddy.databank.seed import looks_like_wiki_url
from battlebuddy.session.log import report
from battlebuddy.sources.store import WikiSource, load_sources, needs_discover, save_sources
from battlebuddy.xai.loop import (
    SEARCH_TIMEOUT,
    ChatOut,
    api_key,
    chat_out,
    web_search_parameters,
)

_MAX_SOURCES = 8
_EXTRA_HOSTS = (
    "fextralife.com",
    "fandom.com",
    "wiki.gg",
    "paradoxwikis.com",
    "wikipedia.org",
    "hoodedhorse.com",
)
_DISCOVER_SYSTEM = (
    "List the main public wiki sites for this video game. JSON only. "
    'Use {"sources":[{"name":"Official wiki","url":"https://...","search":"https://...{q}"}]}. '
    "Prefer the official wiki, wiki.gg, Fandom, Paradox wikis, Fextralife. "
    "Hub or home URLs only. No article dumps. Max 8. Do not invent URLs."
)


def discover_sources(
    game: str,
    *,
    home: Path | None = None,
    key: str | None = None,
    chat_fn: Callable[..., ChatOut] | None = None,
) -> list[WikiSource]:
    """Live-search wiki hubs for this game. Empty when offline. Does not fetch articles."""
    name = (game or "").strip()
    token = (key if key is not None else api_key()) or ""
    if not name:
        report("wiki discover skipped: no game")
        return []
    if not token:
        report(f"wiki discover skipped: no key ({name})")
        return []
    poster = chat_fn or chat_out
    query = f"{name} official wiki fandom wiki.gg paradox fextralife"
    try:
        out = poster(
            [
                {"role": "system", "content": _DISCOVER_SYSTEM},
                {"role": "user", "content": query},
            ],
            key=token,
            timeout=SEARCH_TIMEOUT,
            max_tokens=500,
            search_parameters=web_search_parameters(
                ["fandom.com", "wiki.gg", "paradoxwikis.com", "fextralife.com", "wikipedia.org"]
            ),
        )
    except Exception as exc:
        report("wiki discover call failed", exc)
        return []
    if out.error == "network" or (out.text is None and not out.citations):
        report(f"wiki discover failed: {out.error or 'empty'} ({name})")
        return []
    parsed = parse_source_list(out.text, out.citations, game=name)
    if not parsed:
        report(f"wiki discover found no hubs for {name}")
        return []
    save_sources(name, parsed, home)
    report(f"wiki discover filed {len(parsed)} hubs for {name}")
    return parsed


def maybe_discover(
    game: str | None,
    home: Path | None = None,
    *,
    key: str | None = None,
    chat_fn: Callable[..., ChatOut] | None = None,
) -> list[WikiSource]:
    """First SCAN of a game with no list. Existing lists stay put."""
    if not needs_discover(game, home):
        return load_sources(game, home)
    return discover_sources(game or "", home=home, key=key, chat_fn=chat_fn)


def parse_source_list(
    raw: str | None,
    citations: tuple[str, ...] | list[str] = (),
    *,
    game: str = "",
) -> list[WikiSource]:
    """JSON hubs first. Citation URLs fill gaps. Wiki hosts only."""
    from battlebuddy.xai.loop import _json_object

    items: list[WikiSource] = []
    seen: set[str] = set()
    data = _json_object(raw)
    rows: object = None
    if isinstance(data, dict):
        rows = data.get("sources") or data.get("wikis") or data.get("sites")
    elif isinstance(data, list):
        rows = data
    if isinstance(rows, list):
        for item in rows:
            source = WikiSource.from_dict(item)
            if source is None or source.url in seen or not is_game_wiki_url(source.url):
                continue
            seen.add(source.url)
            items.append(source)
            if len(items) >= _MAX_SOURCES:
                return items
    for url in citations:
        source = WikiSource.from_dict({"url": url, "name": ""})
        if source is None or source.url in seen or not is_game_wiki_url(source.url):
            continue
        seen.add(source.url)
        items.append(source)
        if len(items) >= _MAX_SOURCES:
            break
    if items:
        return items
    # Bare URLs in the model text.
    for word in (raw or "").split():
        clean = normalize_url(word.strip(".,;()[]"))
        if not clean or clean in seen or not is_game_wiki_url(clean):
            continue
        seen.add(clean)
        items.append(WikiSource(name=_label(clean, game), url=clean))
        if len(items) >= _MAX_SOURCES:
            break
    return items


def is_game_wiki_url(url: str) -> bool:
    """Official-ish wiki hosts. Skip stores and login."""
    if looks_like_wiki_url(url):
        return True
    clean = normalize_url(url)
    if not clean:
        return False
    host = (urlparse(clean).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return any(host == item or host.endswith("." + item) for item in _EXTRA_HOSTS)


def _label(url: str, game: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if "fandom" in host:
        return f"{game} Fandom".strip() or "Fandom wiki"
    if host.endswith("wiki.gg"):
        return f"{game} wiki.gg".strip() or "wiki.gg"
    if "paradox" in host:
        return f"{game} Paradox wiki".strip() or "Paradox wiki"
    if "fextralife" in host:
        return f"{game} Fextralife".strip() or "Fextralife"
    return (game + " wiki").strip() or "Wiki"

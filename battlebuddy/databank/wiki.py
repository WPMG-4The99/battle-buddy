"""Hunt the detected game's public wiki. Same origin. No model. No invent."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urlencode, urlparse

from battlebuddy.databank.fetch import fetch_page, normalize_url
from battlebuddy.databank.search import AskResult, ask_pages, content_terms, query_terms
from battlebuddy.databank.store import DatabankStore, Source

_MAX_PAGES = 3
_SEARCH_LIMIT = 5
_LANG_SUFFIX = ("/en", "/de", "/fr")
_NO_WIKI_MATCH = "No match on the wiki. Nothing invented."
_KNOWN_HOSTS = (
    "wiki.hoodedhorse.com",
    "rimworldwiki.com",
    "www.rimworldwiki.com",
    "valheim.fandom.com",
)


@dataclass(frozen=True)
class WikiHome:
    origin: str
    api: str
    article_base: str


KNOWN_WIKIS: dict[str, WikiHome] = {
    "manor lords": WikiHome(
        origin="https://wiki.hoodedhorse.com",
        api="https://wiki.hoodedhorse.com/Manor_Lords/api.php",
        article_base="https://wiki.hoodedhorse.com/Manor_Lords/",
    ),
    "rimworld": WikiHome(
        origin="https://rimworldwiki.com",
        api="https://rimworldwiki.com/api.php",
        article_base="https://rimworldwiki.com/wiki/",
    ),
    "valheim": WikiHome(
        origin="https://valheim.fandom.com",
        api="https://valheim.fandom.com/api.php",
        article_base="https://valheim.fandom.com/wiki/",
    ),
}


def wiki_home_for(game: str | None, store: DatabankStore) -> WikiHome | None:
    """Known detect name, or the wiki already saved for this game. No web wander."""
    known = KNOWN_WIKIS.get(_norm_game(game))
    inferred = infer_wiki_from_sources(store.list_sources(game))
    if known is not None and inferred is not None:
        return inferred
    if known is not None:
        return known
    if inferred is not None and _known_host(inferred.origin):
        return inferred
    return None


def infer_wiki_from_sources(sources: list[Source]) -> WikiHome | None:
    for item in sources:
        home = infer_wiki_from_url(item.url)
        if home is not None:
            return home
    return None


def infer_wiki_from_url(raw_url: str) -> WikiHome | None:
    """Same host + MediaWiki script path. Used so a saved page pins the wiki."""
    url = normalize_url(raw_url)
    if url is None:
        return None
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    origin = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path or "/"
    if path.endswith("/api.php"):
        prefix = path[: -len("api.php")]
        return WikiHome(origin=origin, api=f"{origin}{path}", article_base=f"{origin}{prefix}")
    wiki_at = path.find("/wiki/")
    if wiki_at >= 0:
        root = path[:wiki_at]
        return WikiHome(
            origin=origin,
            api=f"{origin}{root}/api.php",
            article_base=f"{origin}{root}/wiki/",
        )
    stripped = path.rstrip("/")
    if stripped.endswith("/wiki"):
        root = stripped[: -len("/wiki")]
        return WikiHome(
            origin=origin,
            api=f"{origin}{root}/api.php",
            article_base=f"{origin}{root}/wiki/",
        )
    if _known_host(origin):
        parts = [part for part in path.split("/") if part]
        if not parts:
            return WikiHome(origin=origin, api=f"{origin}/api.php", article_base=f"{origin}/")
        prefix = f"/{parts[0]}/"
        return WikiHome(
            origin=origin,
            api=f"{origin}{prefix}api.php",
            article_base=f"{origin}{prefix}",
        )
    return None


def ask_or_hunt(store: DatabankStore, game: str | None, question: str) -> AskResult:
    """Local retrieve first. Hunt only when the folder has no real hit."""
    result = ask_pages(store, game, question)
    if result.hits or not result.ok:
        return result
    if wiki_home_for(game, store) is None:
        return result
    return hunt_and_ask(store, game, question)


def hunt_and_ask(store: DatabankStore, game: str | None, question: str) -> AskResult:
    """Search the game wiki, save up to 3 same-origin pages, retrieve again."""
    home = wiki_home_for(game, store)
    if home is None:
        return ask_pages(store, game, question)
    needed = content_terms(query_terms(question))
    if not needed:
        return AskResult(ok=True, empty=False, message=_NO_WIKI_MATCH)
    urls = search_wiki_urls(home, needed)
    existing = {item.url for item in store.list_sources(game)}
    saved = 0
    for url in urls:
        if saved >= _MAX_PAGES:
            break
        if url in existing:
            continue
        result = store.add_url(game, url)
        if result.ok:
            saved += 1
            existing.add(result.url)
    found = ask_pages(store, game, question)
    if found.hits:
        return found
    return AskResult(ok=True, empty=False, message=_NO_WIKI_MATCH, hits=())


def search_wiki_urls(home: WikiHome, terms: list[str]) -> list[str]:
    """MediaWiki text search. srwhat=text is required. Same origin only."""
    if not terms:
        return []
    params = {
        "action": "query",
        "list": "search",
        "srwhat": "text",
        "srsearch": " ".join(terms),
        "srlimit": str(_SEARCH_LIMIT),
        "format": "json",
    }
    glue = "&" if "?" in home.api else "?"
    api_url = f"{home.api}{glue}{urlencode(params)}"
    fetched = fetch_page(api_url)
    if fetched.ok:
        return parse_search_urls(fetched.text, home)
    if fetched.kind == "404":
        return fallback_title_urls(home, terms)
    return []


def parse_search_urls(blob: str, home: WikiHome) -> list[str]:
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    query = data.get("query")
    if not isinstance(query, dict):
        return []
    rows = query.get("search")
    if not isinstance(rows, list):
        return []
    titles: list[str] = []
    urls: list[str] = []
    seen: set[str] = set()
    for item in rows:
        if not isinstance(item, dict):
            continue
        raw_url = item.get("fullurl") or item.get("url")
        if isinstance(raw_url, str) and raw_url.strip():
            normalized = normalize_url(raw_url)
            if normalized is None or not same_origin(normalized, home):
                continue
            if normalized not in seen:
                seen.add(normalized)
                urls.append(normalized)
            continue
        title = str(item.get("title") or "").strip()
        if title:
            titles.append(title)
    for title in _canonical_titles(titles):
        built = article_url(home, title)
        if built is None or not same_origin(built, home):
            continue
        if built not in seen:
            seen.add(built)
            urls.append(built)
    return urls


def fallback_title_urls(home: WikiHome, terms: list[str]) -> list[str]:
    """api.php missing: try Title-case article paths on the same wiki only."""
    urls: list[str] = []
    seen: set[str] = set()
    for term in terms:
        title = term[:1].upper() + term[1:]
        built = article_url(home, title)
        if built is None or not same_origin(built, home) or built in seen:
            continue
        seen.add(built)
        urls.append(built)
    return urls


def article_url(home: WikiHome, title: str) -> str | None:
    text = (title or "").strip()
    if not text:
        return None
    if "://" in text:
        normalized = normalize_url(text)
        if normalized is None or not same_origin(normalized, home):
            return None
        return normalized
    slug = text.replace(" ", "_")
    base = home.article_base if home.article_base.endswith("/") else f"{home.article_base}/"
    return normalize_url(f"{base}{slug}")


def same_origin(url: str, home: WikiHome) -> bool:
    left = urlparse(url)
    right = urlparse(home.origin)
    return (left.scheme, left.hostname, left.port) == (right.scheme, right.hostname, right.port)


def _canonical_titles(titles: list[str]) -> list[str]:
    bag = set(titles)
    out: list[str] = []
    seen: set[str] = set()
    for title in titles:
        canon = title
        for suffix in _LANG_SUFFIX:
            if title.endswith(suffix):
                parent = title[: -len(suffix)]
                if parent in bag:
                    canon = parent
                break
        if not canon or canon in seen:
            continue
        seen.add(canon)
        out.append(canon)
    return out


def _norm_game(game: str | None) -> str:
    return re.sub(r"\s+", " ", (game or "").strip().lower())


def _known_host(origin: str) -> bool:
    host = (urlparse(origin).hostname or "").lower()
    if host in _KNOWN_HOSTS:
        return True
    return any(host.endswith(f".{item}") for item in _KNOWN_HOSTS)

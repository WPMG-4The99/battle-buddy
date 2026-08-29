"""Hunt the detected game's public wiki. Same origin. No model. No invent."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urlencode, urlparse

from battlebuddy.databank.fetch import fetch_page, normalize_url
from battlebuddy.databank.search import (
    AskResult,
    Hit,
    ask_pages,
    content_terms,
    page_files,
    query_terms,
)
from battlebuddy.databank.store import DatabankStore, Source

_MAX_PAGES = 3
_SEARCH_LIMIT = 5
_LANG_SUFFIX = (
    "/en",
    "/de",
    "/fr",
    "/nl",
    "/es",
    "/it",
    "/pl",
    "/ru",
    "/sv",
    "/tr",
    "/uk",
    "/el",
)
_CRAFT_CUES = (
    "obtain",
    "obtained",
    "produced",
    "produce",
    "craft",
    "workshop",
    "blacksmith",
    "backyard",
    "planks",
    "iron",
)
_HOWTO = {"how", "start", "produce", "production", "make", "craft", "obtain"}
_NO_WIKI_MATCH = "No match on the wiki. Nothing invented."
_HTML_TAG = re.compile(r"<[^>]+>")
_WORD = re.compile(r"[a-z0-9]+")
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


@dataclass(frozen=True)
class SearchHit:
    title: str
    snippet: str
    url: str


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
    homes = wiki_homes_for(game, store)
    if not homes:
        return None
    known = KNOWN_WIKIS.get(_norm_game(game))
    inferred = infer_wiki_from_sources(store.list_sources(game))
    if known is not None and inferred is not None:
        return inferred
    return homes[0]


def wiki_homes_for(game: str | None, store: DatabankStore) -> list[WikiHome]:
    """Known map plus each unique origin already on disk. One miss must not block the rest."""
    known = KNOWN_WIKIS.get(_norm_game(game))
    inferred: list[WikiHome] = []
    seen: set[str] = set()
    for item in store.list_sources(game):
        home = infer_wiki_from_url(item.url)
        if home is None or home.origin in seen:
            continue
        seen.add(home.origin)
        inferred.append(home)
    homes: list[WikiHome] = []
    loopback = any(_is_loopback(home.origin) for home in inferred)
    if known is not None and not loopback:
        homes.append(known)
        seen.add(known.origin)
    for home in inferred:
        if home.origin in {item.origin for item in homes}:
            continue
        if known is None and not _known_host(home.origin) and not _is_loopback(home.origin):
            # Unknown game: only pin a saved wiki on a known host (or a local test server).
            continue
        homes.append(home)
    return homes


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


def search_variants(terms: list[str]) -> list[str]:
    """Each content word plus simple singular/plural. Never AND the question."""
    out: list[str] = []
    seen: set[str] = set()
    for term in terms:
        for item in (term, _pluralize(term), _singularize(term)):
            if not item or item in seen:
                continue
            seen.add(item)
            out.append(item)
    return out


def should_hunt(
    store: DatabankStore,
    game: str | None,
    question: str,
    result: AskResult,
) -> bool:
    """Hunt when local text is a miss, or a how-to with the noun but no craft cue."""
    if not result.ok:
        return False
    if local_covers(store, game, question, result):
        return False
    return bool(wiki_homes_for(game, store))


def local_covers(
    store: DatabankStore,
    game: str | None,
    question: str,
    result: AskResult,
) -> bool:
    """A how-to needs the noun plus a craft cue. Other questions keep a keyword hit."""
    if not result.hits:
        return False
    if not _is_howto(question):
        return True
    nouns = search_variants(content_terms(query_terms(question)))
    if any(_noun_and_craft(hit.title, hit.snippet, nouns) for hit in result.hits):
        return True
    for path in page_files(store.folder(game)):
        try:
            body = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if _noun_and_craft("", body, nouns):
            return True
    return False


def rank_ask_result(result: AskResult, question: str) -> AskResult:
    """Craft-cue pages first. Drop militia/Approval filler when a recipe hit exists."""
    if not result.hits:
        return result
    nouns = search_variants(content_terms(query_terms(question)))
    strong: list[Hit] = []
    weak: list[Hit] = []
    for hit in result.hits:
        if _noun_and_craft(hit.title, hit.snippet, nouns):
            strong.append(hit)
        else:
            weak.append(hit)
    kept = strong if strong else weak
    kept.sort(key=lambda item: _ask_hit_score(item, nouns), reverse=True)
    return AskResult(ok=result.ok, empty=result.empty, message=result.message, hits=tuple(kept))


def ask_or_hunt(store: DatabankStore, game: str | None, question: str) -> AskResult:
    """Local retrieve first. Hunt when the folder has no real how-to hit."""
    result = ask_pages(store, game, question)
    if not result.ok:
        return result
    if local_covers(store, game, question, result) or not wiki_homes_for(game, store):
        return rank_ask_result(result, question)
    return hunt_and_ask(store, game, question)


def hunt_and_ask(store: DatabankStore, game: str | None, question: str) -> AskResult:
    """Search each wiki home, save top ranked same-origin pages, retrieve again."""
    homes = wiki_homes_for(game, store)
    if not homes:
        return rank_ask_result(ask_pages(store, game, question), question)
    needed = content_terms(query_terms(question))
    if not needed:
        return AskResult(ok=True, empty=False, message=_NO_WIKI_MATCH)
    existing = {item.url for item in store.list_sources(game)}
    for home in homes:
        urls = search_wiki_urls(home, needed)
        saved = 0
        for url in urls:
            if saved >= _MAX_PAGES:
                break
            if url in existing:
                continue
            fetched = store.add_url(game, url)
            if fetched.ok:
                saved += 1
                existing.add(fetched.url)
    found = rank_ask_result(ask_pages(store, game, question), question)
    if found.hits:
        return found
    return AskResult(ok=True, empty=False, message=_NO_WIKI_MATCH, hits=())


def search_wiki_urls(home: WikiHome, terms: list[str]) -> list[str]:
    """One srwhat=text query per variant. Union, rank, return top same-origin URLs."""
    hits = search_wiki_hits(home, terms)
    ranked = rank_search_hits(hits, search_variants(terms))
    urls: list[str] = []
    seen: set[str] = set()
    for hit in ranked:
        if hit.url in seen:
            continue
        seen.add(hit.url)
        urls.append(hit.url)
        if len(urls) >= _MAX_PAGES:
            break
    return urls


def search_wiki_hits(home: WikiHome, terms: list[str]) -> list[SearchHit]:
    variants = search_variants(terms)
    if not variants:
        return []
    hits: list[SearchHit] = []
    seen: set[str] = set()
    api_missing = False
    for variant in variants:
        fetched = _search_api(home, variant)
        if fetched.ok:
            for hit in parse_search_hits(fetched.text, home):
                if hit.url in seen:
                    continue
                seen.add(hit.url)
                hits.append(hit)
            continue
        if fetched.kind == "404":
            api_missing = True
    if hits:
        return hits
    if api_missing:
        for url in fallback_title_urls(home, variants):
            if url in seen:
                continue
            title = urlparse(url).path.rstrip("/").split("/")[-1].replace("_", " ")
            seen.add(url)
            hits.append(SearchHit(title=title, snippet="", url=url))
    return hits


def parse_search_hits(blob: str, home: WikiHome) -> list[SearchHit]:
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
    hits: list[SearchHit] = []
    seen: set[str] = set()
    titles: list[tuple[str, str]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        snippet = _plain_snippet(item.get("snippet") or "")
        raw_url = item.get("fullurl") or item.get("url")
        if isinstance(raw_url, str) and raw_url.strip():
            normalized = normalize_url(raw_url)
            if normalized is None or not same_origin(normalized, home):
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            hits.append(SearchHit(title=title, snippet=snippet, url=normalized))
            continue
        if title:
            titles.append((title, snippet))
    for title in _canonical_titles([item[0] for item in titles]):
        built = article_url(home, title)
        if built is None or not same_origin(built, home) or built in seen:
            continue
        snippet = next((snip for name, snip in titles if name == title), "")
        seen.add(built)
        hits.append(SearchHit(title=title, snippet=snippet, url=built))
    return hits


def parse_search_urls(blob: str, home: WikiHome) -> list[str]:
    return [hit.url for hit in parse_search_hits(blob, home)]


def rank_search_hits(hits: list[SearchHit], nouns: list[str]) -> list[SearchHit]:
    """Boost noun + craft cue. Penalize translations and militia/Approval filler."""
    return sorted(hits, key=lambda hit: _search_hit_score(hit, nouns), reverse=True)


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


def _search_api(home: WikiHome, term: str):
    params = {
        "action": "query",
        "list": "search",
        "srwhat": "text",
        "srsearch": term,
        "srlimit": str(_SEARCH_LIMIT),
        "format": "json",
    }
    glue = "&" if "?" in home.api else "?"
    api_url = f"{home.api}{glue}{urlencode(params)}"
    return fetch_page(api_url)


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


def _search_hit_score(hit: SearchHit, nouns: list[str]) -> int:
    title = hit.title.lower()
    snippet = hit.snippet.lower()
    blob = f"{title} {snippet}"
    has_noun = _has_any_word(blob, nouns)
    has_craft = _has_craft(blob)
    score = 0
    if has_noun:
        score += 10
    if has_noun and has_craft:
        score += 50
    if _has_lang_suffix(hit.title) or _has_lang_suffix(hit.url):
        score -= 20
    if "militia" in blob and not has_craft:
        score -= 15
    if "approval" in title and not has_craft:
        score -= 15
    return score


def _ask_hit_score(hit: Hit, nouns: list[str]) -> int:
    blob = f"{hit.title} {hit.snippet}".lower()
    score = hit.score
    if _noun_and_craft(hit.title, hit.snippet, nouns):
        score += 50
    if "militia" in blob and not _has_craft(blob):
        score -= 15
    if "approval" in hit.title.lower() and not _has_craft(blob):
        score -= 15
    return score


def _noun_and_craft(title: str, snippet: str, nouns: list[str]) -> bool:
    blob = f"{title} {snippet}".lower()
    return _has_any_word(blob, nouns) and _has_craft(blob)


def _has_craft(blob: str) -> bool:
    return any(cue in blob for cue in _CRAFT_CUES)


def _has_any_word(blob: str, words: list[str]) -> bool:
    bag = set(_WORD.findall(blob.lower()))
    return any(word in bag for word in words)


def _is_howto(question: str) -> bool:
    words = set(_WORD.findall((question or "").lower()))
    return bool(words & _HOWTO)


def _plain_snippet(raw: object) -> str:
    text = _HTML_TAG.sub(" ", str(raw or ""))
    return " ".join(text.split())


def _has_lang_suffix(text: str) -> bool:
    lowered = (text or "").lower().rstrip("/")
    return any(lowered.endswith(suffix) for suffix in _LANG_SUFFIX)


def _pluralize(word: str) -> str:
    if word.endswith("s"):
        return word
    return f"{word}s"


def _singularize(word: str) -> str:
    if len(word) > 1 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _is_loopback(origin: str) -> bool:
    host = (urlparse(origin).hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def _norm_game(game: str | None) -> str:
    return re.sub(r"\s+", " ", (game or "").strip().lower())


def _known_host(origin: str) -> bool:
    host = (urlparse(origin).hostname or "").lower()
    if host in _KNOWN_HOSTS:
        return True
    return any(host.endswith(f".{item}") for item in _KNOWN_HOSTS)

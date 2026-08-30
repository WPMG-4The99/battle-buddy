"""Hunt the detected game's public wiki. Same origin. No model. No invent."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urlencode, urlparse

from battlebuddy.databank.clean import (
    expand_search_terms,
    is_claim_question,
    is_howto_question,
    is_patch_title,
    strip_markup,
)
from battlebuddy.databank.fetch import fetch_page, normalize_url
from battlebuddy.databank.search import (
    AskResult,
    Hit,
    ask_pages,
    compile_ask_line,
    content_terms,
    page_texts_for_hits,
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
# ASK-snippet how-to coverage only. Lone "blacksmith" or "produced" is not a recipe.
_STRONG_CRAFT_WORDS = ("obtained",)
_STRONG_CRAFT_PAIRS = (("blacksmiths", "workshop"), ("blacksmith", "workshop"))
_NO_WIKI_MATCH = "No match on the wiki. Nothing invented."
_TAX_FALLBACKS = ("Buildings", "FAQ", "Manor")
_CLAIM_FALLBACKS = ("FAQ", "Game_setup", "Warfare", "Regions")
_CLAIM_HINTS = frozenset(
    {
        "baron",
        "claim",
        "defeat",
        "eliminate",
        "enemy",
        "influence",
        "kill",
        "ruler",
    }
)
_TRANSLATED_TITLES = {
    "byggnad": "building",
    "byggnader": "buildings",
}
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
        for item in (term, _pluralize(term), _singularize(term), _destem(term)):
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
    """Hunt when local text is a miss, or a how-to snippet lacks a strong recipe cue."""
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
    """How-to coverage is noun + strong cue on the ASK snippet. Not the full page dump."""
    if not result.hits:
        return False
    if not is_howto_question(question):
        return True
    texts = page_texts_for_hits(store, game, result)
    if compile_ask_line(question, texts):
        return True
    nouns = search_variants(content_terms(query_terms(question)))
    best = result.hits[0]
    if _militia_or_approval(best) and not _noun_and_craft(best.title, best.snippet, nouns):
        return False
    return any(_noun_and_craft(hit.title, hit.snippet, nouns) for hit in result.hits)


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
    kept = _drop_translated_duplicates(kept)
    kept.sort(key=lambda item: _ask_hit_score(item, nouns), reverse=True)
    return AskResult(
        ok=result.ok,
        empty=result.empty,
        message=result.message,
        hits=tuple(kept),
        question=question or result.question,
    )


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
    needed = expand_search_terms(question, content_terms(query_terms(question)))
    if is_claim_question(question):
        needed = [term for term in needed if term not in {"defeat", "kill", "ruler"}]
    if not needed:
        return AskResult(ok=True, empty=False, message=_NO_WIKI_MATCH, question=question)
    existing = {item.url for item in store.list_sources(game)}
    nouns = search_variants(needed)
    collected: list[SearchHit] = []
    for home in homes:
        hits = search_wiki_hits(home, needed)
        collected.extend(hits)
        ranked = rank_search_hits(hits, nouns)
        saved = 0
        for hit in ranked:
            if saved >= _MAX_PAGES:
                break
            if hit.url in existing:
                continue
            fetched = store.add_url(game, hit.url)
            if fetched.ok:
                saved += 1
                existing.add(fetched.url)
    found = rank_ask_result(ask_pages(store, game, question), question)
    led = _lead_with_search_recipe(found, collected, nouns)
    texts = page_texts_for_hits(store, game, led)
    if compile_ask_line(question, texts):
        return led
    if is_howto_question(question) or not led.hits:
        return AskResult(ok=True, empty=False, message=_NO_WIKI_MATCH, hits=(), question=question)
    return led


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
    if hits and not (api_missing or _wants_claim_fallback(variants)):
        return hits
    if api_missing or _wants_claim_fallback(variants):
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
    extras: list[str] = []
    bag = {item.lower() for item in terms}
    if bag & {"tax", "taxes", "taxing", "taxation"}:
        extras.extend(_TAX_FALLBACKS)
    if bag & _CLAIM_HINTS:
        extras.extend(_CLAIM_FALLBACKS)
    for term in list(terms) + extras:
        title = term[:1].upper() + term[1:] if term[:1].islower() else term
        if term in _TAX_FALLBACKS:
            title = term
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
    if is_patch_title(hit.title):
        score -= 80
    if _has_lang_suffix(hit.title) or _has_lang_suffix(hit.url):
        score -= 20
    if _title_head(hit.title) in _TRANSLATED_TITLES:
        score -= 25
    host = (urlparse(hit.url).hostname or "").lower()
    if host.endswith("fandom.com"):
        score -= 15
    if host.endswith("hoodedhorse.com"):
        score += 10
    if "militia" in blob and not has_craft:
        score -= 15
    if "approval" in title and not has_craft:
        score -= 15
    return score


def _ask_hit_score(hit: Hit, nouns: list[str]) -> int:
    blob = f"{hit.title} {hit.snippet}".lower()
    score = hit.score
    if is_patch_title(hit.title):
        score -= 80
    if _noun_and_craft(hit.title, hit.snippet, nouns):
        score += 50
    if "official wiki" in hit.title.lower():
        score += 8
    if "fandom" in hit.title.lower():
        score -= 8
    if _title_head(hit.title) in _TRANSLATED_TITLES:
        score -= 25
    if "militia" in blob and not _has_craft(blob):
        score -= 15
    if "approval" in hit.title.lower() and not _has_craft(blob):
        score -= 15
    return score


def _lead_with_search_recipe(
    result: AskResult,
    search_hits: list[SearchHit],
    nouns: list[str],
) -> AskResult:
    """MediaWiki snippet with obtained / blacksmith's workshop leads. No invent."""
    recipes: list[Hit] = []
    seen: set[str] = set()
    for hit in rank_search_hits(search_hits, nouns):
        if not _noun_and_craft(hit.title, hit.snippet, nouns):
            continue
        key = hit.title.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        recipes.append(Hit(title=hit.title, snippet=strip_markup(hit.snippet), score=100))
    if not recipes:
        return result
    rest = [item for item in result.hits if item.title.strip().lower() not in seen]
    kept = tuple((recipes + rest)[:_MAX_PAGES])
    return AskResult(
        ok=True,
        empty=False,
        message=result.message,
        hits=kept,
        question=result.question,
    )


def _noun_and_craft(title: str, snippet: str, nouns: list[str]) -> bool:
    blob = f"{title} {snippet}".lower()
    return _has_any_word(blob, nouns) and _has_craft(blob)


def _militia_or_approval(hit: Hit) -> bool:
    title = hit.title.lower()
    blob = f"{title} {hit.snippet}".lower()
    return "militia" in blob or "approval" in title or "warfare" in title


def _has_craft(blob: str) -> bool:
    """obtained / produced / backyard / into N. Lone blacksmith does not count."""
    words = _cue_words(blob)
    if set(words) & set(_STRONG_CRAFT_WORDS):
        return True
    for index, word in enumerate(words[:-1]):
        if word == "into" and words[index + 1].isdigit():
            return True
    pairs = set(_STRONG_CRAFT_PAIRS)
    return any((words[i], words[i + 1]) in pairs for i in range(len(words) - 1))


def _cue_words(blob: str) -> list[str]:
    text = (blob or "").lower().replace("'", "").replace("’", "")
    return _WORD.findall(text)


def _has_any_word(blob: str, words: list[str]) -> bool:
    bag = set(_WORD.findall(blob.lower()))
    return any(word in bag for word in words)


def _wants_claim_fallback(terms: list[str]) -> bool:
    bag = {item.lower() for item in terms}
    return bool(bag & _CLAIM_HINTS)


def _plain_snippet(raw: object) -> str:
    return strip_markup(str(raw or ""))


def _has_lang_suffix(text: str) -> bool:
    lowered = (text or "").lower().rstrip("/")
    return any(lowered.endswith(suffix) for suffix in _LANG_SUFFIX)


def _drop_translated_duplicates(hits: list[Hit]) -> list[Hit]:
    """Drop Byggnader when Buildings exists. Keep the English page."""
    if not hits:
        return hits
    heads = [_title_head(hit.title) for hit in hits]
    english = {head for head in heads if head not in _TRANSLATED_TITLES}
    kept: list[Hit] = []
    for hit in hits:
        head = _title_head(hit.title)
        alias = _TRANSLATED_TITLES.get(head)
        if alias and (alias in english or any(alias == item for item in heads)):
            continue
        if _has_lang_suffix(hit.title):
            parent = _title_head(hit.title)
            if any(parent == other and other != head for other in heads):
                continue
        kept.append(hit)
    return kept or hits


def _title_head(title: str) -> str:
    raw = (title or "").strip().lower()
    if " - " in raw:
        raw = raw.split(" - ", 1)[0]
    if "/" in raw:
        raw = raw.split("/", 1)[0]
    return raw.strip()


def _destem(word: str) -> str:
    if word.endswith("ation") and len(word) > 7:
        return word[:-5]
    if word.endswith("ing") and len(word) > 5:
        return word[:-3]
    return word


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

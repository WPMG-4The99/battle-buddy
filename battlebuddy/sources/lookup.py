"""Ask-time live wiki lookup. Restricted to this game's sources. On-demand fetch."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from battlebuddy.databank.fetch import normalize_url
from battlebuddy.session.log import report
from battlebuddy.snap.context import grounded_answer, pack_context
from battlebuddy.sources.cache import fetch_cached
from battlebuddy.sources.discover import is_game_wiki_url, maybe_discover
from battlebuddy.sources.store import allowed_hosts, ranked_sources
from battlebuddy.voice.tts import speak_async
from battlebuddy.xai.loop import (
    SEARCH_TIMEOUT,
    ChatOut,
    api_key,
    chat_out,
    web_search_parameters,
)

LOOKING_CUE = "Looking it up"
_NO_KEY = "No Grok key. Answering from local notes and the snap."
_NO_NET = "Could not reach the wiki. Answering from local notes and the snap."
_MAX_PAGES = 3
_OCR_CAP = 400
_PAGE_LINE_CAP = 1800
_LOOKUP_SYSTEM = (
    "Answer from the cited wiki pages and the screen text only. "
    "One or two spoken sentences. JSON only: "
    '{"answer":"short answer","urls":["https://..."]}. '
    "Do not invent. If those pages do not say, set answer to "
    "Can't find that on the wiki."
)
_GROUND_SYSTEM = (
    "Answer from the context only (screen, notes, wiki pages). "
    "One or two sentences. Do not invent. "
    "If the context does not say, reply exactly: Can't find that on the wiki."
)


@dataclass(frozen=True)
class LookupResult:
    """Spoken answer plus source links. Never silent. local_only means no live web."""

    answer: str
    speak: str
    urls: tuple[str, ...]
    notice: str = ""
    local_only: bool = False
    page_lines: tuple[str, ...] = ()


def live_lookup(
    question: str,
    game: str | None,
    *,
    ocr: str = "",
    notes: list[str] | None = None,
    pages: list[str] | None = None,
    home: Path | None = None,
    key: str | None = None,
    chat_fn: Callable[..., ChatOut] | None = None,
    fetch_fn: object | None = None,
    cue: bool = True,
) -> LookupResult:
    """Search this game's wiki hubs, fetch a couple of pages, answer. Speak a cue."""
    asked = " ".join((question or "").split())
    held = [item.strip() for item in (notes or []) if (item or "").strip()]
    local_pages = [item.strip() for item in (pages or []) if (item or "").strip()]
    pack = pack_context(ocr, held, local_pages)
    local = grounded_answer(asked, pack) if pack else ""
    token = (key if key is not None else api_key()) or ""
    if not asked:
        return LookupResult(answer=local or "Type a question.", speak="", urls=(), local_only=True)
    if not token:
        report("live lookup skipped: no key")
        return _fallback(_NO_KEY, local, pack)
    if cue:
        try:
            speak_async(LOOKING_CUE)
        except Exception as exc:
            report("lookup cue TTS failed", exc)
    sources = ranked_sources(game, home)
    if not sources:
        sources = maybe_discover(game, home, key=token, chat_fn=chat_fn)
    hosts = allowed_hosts(game, home)
    poster = chat_fn or chat_out
    query = _query(asked, game, ocr, hosts)
    try:
        out = poster(
            [
                {"role": "system", "content": _LOOKUP_SYSTEM},
                {"role": "user", "content": query},
            ],
            key=token,
            timeout=SEARCH_TIMEOUT,
            max_tokens=280,
            search_parameters=web_search_parameters(hosts),
        )
    except Exception as exc:
        report("live lookup call failed", exc)
        return _fallback(_NO_NET, local, pack)
    if out.error in {"network", "bad_url"} or (out.text is None and not out.citations):
        report(f"live lookup failed: {out.error or 'empty'}")
        return _fallback(_NO_NET, local, pack)
    urls = _pick_urls(out, sources, hosts)
    fetched = _fetch_pages(urls, game, home, fetch_fn)
    page_lines = tuple(_page_line(item) for item in fetched)
    rich = pack_context(ocr, held, local_pages + list(page_lines))
    parsed_answer, parsed_urls = _parse_lookup(out.text)
    from_pages = grounded_answer(asked, rich) if page_lines else ""
    answer = (parsed_answer or from_pages or local or "").strip()
    if _is_miss(answer) and page_lines:
        answer = (_ground(asked, rich, token, poster) or answer).strip()
    if not answer:
        answer = "Can't find that on the wiki."
    links = parsed_urls or urls
    shown = format_answer(answer, links)
    report(f"live lookup ok ({game or 'general'}): {len(links)} sources")
    return LookupResult(
        answer=shown,
        speak=answer,
        urls=links,
        page_lines=page_lines,
    )


def format_answer(answer: str, urls: list[str] | tuple[str, ...], notice: str = "") -> str:
    """Spoken line first. Source URLs on their own lines for the pane."""
    parts: list[str] = []
    note = (notice or "").strip()
    text = (answer or "").strip()
    if note:
        parts.append(note)
    if text and text != note:
        parts.append(text)
    clean = [item for item in urls if (item or "").strip()]
    if clean:
        parts.append("Sources:")
        parts.extend(clean)
    return "\n".join(parts).strip()


def _fallback(notice: str, local: str, pack: str) -> LookupResult:
    body = (local or grounded_answer("", pack) or "Can't find that.").strip()
    shown = format_answer(body, (), notice)
    speak = f"{notice} {body}".strip()
    report(notice)
    return LookupResult(
        answer=shown,
        speak=speak,
        urls=(),
        notice=notice,
        local_only=True,
    )


def _query(question: str, game: str | None, ocr: str, hosts: list[str]) -> str:
    name = (game or "").strip()
    screen = " ".join((ocr or "").split())[:_OCR_CAP]
    sites = " OR ".join(f"site:{host}" for host in hosts[:5])
    parts = [f"Game: {name}" if name else "Game: unknown"]
    if sites:
        parts.append(f"Stay on: {sites}")
    parts.append(f"Question: {question}")
    if screen:
        parts.append(f"Screen: {screen}")
    return "\n".join(parts)


def _pick_urls(
    out: ChatOut,
    sources: list[object],
    hosts: list[str],
) -> tuple[str, ...]:
    found: list[str] = []
    seen: set[str] = set()
    parsed = _parse_lookup(out.text)[1]
    for raw in list(parsed) + list(out.citations):
        url = normalize_url(raw) or (raw or "").strip()
        if not url or url in seen:
            continue
        if hosts and not _on_hosts(url, hosts) and not is_game_wiki_url(url):
            continue
        if not hosts and not is_game_wiki_url(url):
            continue
        seen.add(url)
        found.append(url)
        if len(found) >= _MAX_PAGES:
            break
    if found:
        return tuple(found)
    for item in sources:
        url = getattr(item, "url", "")
        if url and url not in seen:
            found.append(url)
            if len(found) >= 1:
                break
    return tuple(found)


def _fetch_pages(
    urls: tuple[str, ...],
    game: str | None,
    home: Path | None,
    fetch_fn: object | None,
) -> list[object]:
    pages: list[object] = []
    for url in urls[:_MAX_PAGES]:
        try:
            result = fetch_cached(url, game, home, fetch_fn=fetch_fn)
        except Exception as exc:
            report("wiki page fetch failed", exc)
            continue
        if getattr(result, "ok", False) and (getattr(result, "text", "") or "").strip():
            pages.append(result)
    return pages


def _page_line(result: object) -> str:
    title = str(getattr(result, "title", "") or "").strip()
    url = str(getattr(result, "url", "") or "").strip()
    text = " ".join(str(getattr(result, "text", "") or "").split())
    if len(text) > _PAGE_LINE_CAP:
        text = text[:_PAGE_LINE_CAP].rstrip()
    head = title or url or "Wiki"
    return f"{head}. {text}".strip()


def _ground(
    question: str,
    pack: str,
    key: str,
    poster: Callable[..., ChatOut],
) -> str:
    if not pack.strip():
        return ""
    try:
        out = poster(
            [
                {"role": "system", "content": _GROUND_SYSTEM},
                {"role": "user", "content": f"Question: {question}\n\nContext:\n{pack}"},
            ],
            key=key,
            timeout=SEARCH_TIMEOUT,
            max_tokens=200,
        )
    except Exception as exc:
        report("lookup ground failed", exc)
        return ""
    text = (out.text or "").strip()
    if not text or text.lower().startswith("can't find that"):
        return ""
    return text


def _parse_lookup(raw: str | None) -> tuple[str, tuple[str, ...]]:
    from battlebuddy.xai.loop import _json_object

    data = _json_object(raw)
    if not isinstance(data, dict):
        text = (raw or "").strip()
        return text, ()
    answer = " ".join(str(data.get("answer") or data.get("text") or "").split())
    urls: list[str] = []
    rows = data.get("urls") or data.get("sources") or []
    if isinstance(rows, list):
        for item in rows:
            if isinstance(item, str) and item.strip():
                urls.append(item.strip())
            elif isinstance(item, dict):
                href = str(item.get("url") or item.get("href") or "").strip()
                if href:
                    urls.append(href)
    return answer, tuple(urls)


def _is_miss(text: str) -> bool:
    low = (text or "").strip().lower()
    if not low:
        return True
    return low.startswith("can't find that") or "nothing invented" in low


def _on_hosts(url: str, hosts: list[str]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return any(host == item or host.endswith("." + item) for item in hosts)

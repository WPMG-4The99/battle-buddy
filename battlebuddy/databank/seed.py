"""New-game wiki seed. DuckDuckGo HTML search. Public GET. No account."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.error import URLError
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import build_opener

from battlebuddy.databank.fetch import (
    PublicRedirectHandler,
    _request,
    looks_like_login_url,
    normalize_url,
)
from battlebuddy.databank.store import DatabankStore

_SEARCH = "https://html.duckduckgo.com/html/"
_TIMEOUT = 15
_MAX_LINKS = 3
_SKIP_HOSTS = (
    "google.com",
    "www.google.com",
    "accounts.google.com",
    "steamcommunity.com",
    "store.steampowered.com",
    "steampowered.com",
    "store.epicgames.com",
    "www.gog.com",
    "gog.com",
)
_STORE_HINTS = ("/store", "/app/", "/sku/", "/buy")


@dataclass(frozen=True)
class SeedResult:
    started: bool
    saved: int
    message: str


def needs_wiki_seed(store: DatabankStore, game: str | None) -> bool:
    """True when detect named a game and that folder has no saved pages."""
    if not (game or "").strip():
        return False
    return not store.list_sources(game)


def seed_hold_line(game: str) -> str:
    return f"Hold the line. Fetching wiki pages for {game}. Give it a few minutes."


def seed_done_line(game: str, saved: int) -> str:
    if saved:
        return f"Filed {saved} wiki pages for {game}."
    return f"No wiki pages found for {game}. Nothing invented."


def seed_fail_line() -> str:
    return "Could not reach the wikis. Reminders still hold."


def looks_like_wiki_url(url: str) -> bool:
    """Wiki host/path, fandom, or .wiki. Skip login, Steam, store."""
    clean = normalize_url(url)
    if not clean:
        return False
    if looks_like_login_url(clean):
        return False
    parsed = urlparse(clean)
    host = (parsed.hostname or "").lower()
    path = (parsed.path or "").lower()
    if any(host == skip or host.endswith("." + skip) for skip in _SKIP_HOSTS):
        return False
    if any(hint in path for hint in _STORE_HINTS) and "wiki" not in host and "wiki" not in path:
        return False
    if "steam" in host:
        return False
    blob = f"{host}{path}"
    return "wiki" in blob or "fandom" in host or host.endswith(".wiki")


def parse_ddg_links(html: str) -> list[str]:
    """Pull result URLs out of DuckDuckGo HTML. Unwrap uddg= redirects."""
    parser = _HrefParser()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in parser.hrefs:
        url = _unwrap_ddg(raw)
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def pick_wiki_urls(urls: list[str], limit: int = _MAX_LINKS) -> list[str]:
    picked: list[str] = []
    seen: set[str] = set()
    for raw in urls:
        if not looks_like_wiki_url(raw):
            continue
        clean = normalize_url(raw)
        if not clean or clean in seen:
            continue
        seen.add(clean)
        picked.append(clean)
        if len(picked) >= limit:
            break
    return picked


def search_wiki_urls(game: str) -> list[str] | None:
    """No-account DuckDuckGo HTML search for `{game} wiki`. Offline → None."""
    query = f"{(game or '').strip()} wiki".strip()
    if query == "wiki":
        return []
    html = _get_html(f"{_SEARCH}?q={_query(query)}")
    if html is None:
        return None
    return pick_wiki_urls(parse_ddg_links(html))


def seed_new_game(store: DatabankStore, game: str | None) -> SeedResult:
    """Search, fetch top wiki pages, save. Skip if the folder already has sources."""
    name = (game or "").strip()
    if not name:
        return SeedResult(False, 0, "No game.")
    if not needs_wiki_seed(store, name):
        return SeedResult(False, 0, "Already on disk.")
    try:
        urls = search_wiki_urls(name)
    except Exception:
        return SeedResult(True, 0, seed_fail_line())
    if urls is None:
        return SeedResult(True, 0, seed_fail_line())
    if not urls:
        return SeedResult(True, 0, seed_done_line(name, 0))
    saved = 0
    for url in urls:
        try:
            result = store.add_url(name, url)
        except Exception:
            continue
        if getattr(result, "ok", False):
            saved += 1
    if saved:
        return SeedResult(True, saved, seed_done_line(name, saved))
    return SeedResult(True, 0, seed_fail_line())


def _query(text: str) -> str:
    from urllib.parse import quote_plus

    return quote_plus(text)


def _get_html(url: str) -> str | None:
    target = normalize_url(url)
    if not target:
        return None
    try:
        opener = build_opener(PublicRedirectHandler)
        with opener.open(_request(target), timeout=_TIMEOUT) as resp:
            blob = resp.read(1_500_000)
    except (URLError, TimeoutError, OSError, ValueError):
        return None
    try:
        return blob.decode("utf-8", errors="replace")
    except Exception:
        return None


def _unwrap_ddg(raw: str) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    if text.startswith("//"):
        text = "https:" + text
    parsed = urlparse(text)
    query = parse_qs(parsed.query)
    wrapped = query.get("uddg") or query.get("u")
    if wrapped:
        text = unquote(wrapped[0])
    return normalize_url(text)


class _HrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(value)
                return

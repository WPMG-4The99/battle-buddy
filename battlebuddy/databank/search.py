"""Ask saved page text. Keyword retrieve only. No model. No invent."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from battlebuddy.databank.store import DatabankStore

_WORD = re.compile(r"[a-z0-9]+")
_STOP = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "do",
    "does",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "the",
    "to",
    "what",
    "when",
    "where",
    "which",
    "who",
    "with",
}
_MAX_HITS = 3
_SNIP_WORDS = 28
_EMPTY = "No pages on disk for this game. ADD / FETCH a link first."
_NO_MATCH = "No match in the saved pages. Nothing invented."
_NEED_QUESTION = "Type a question about a saved page."


@dataclass(frozen=True)
class Hit:
    title: str
    snippet: str
    score: int


@dataclass(frozen=True)
class AskResult:
    ok: bool
    empty: bool
    message: str
    hits: tuple[Hit, ...] = ()

    def output(self) -> str:
        """One pane. Hits only, or the reason we have none."""
        if self.hits:
            blocks = [f"{hit.title}\n{hit.snippet}" for hit in self.hits]
            return "\n\n".join(blocks)
        return self.message


def page_files(folder: Path) -> list[Path]:
    """Saved page text only. Skip sources.json."""
    if not folder.is_dir():
        return []
    return sorted(path for path in folder.glob("*.txt") if path.is_file())


def query_terms(question: str) -> list[str]:
    """Keywords from the question. Drop noise. Keep game words."""
    seen: set[str] = set()
    terms: list[str] = []
    for raw in _WORD.findall((question or "").lower()):
        if raw in _STOP or len(raw) < 2:
            continue
        if raw in seen:
            continue
        seen.add(raw)
        terms.append(raw)
    return terms


def ask_pages(store: DatabankStore, game: str | None, question: str) -> AskResult:
    """Search the same folder paste/fetch uses. Local files only."""
    return search_folder(store.folder(game), question)


def search_folder(folder: Path, question: str) -> AskResult:
    """Keyword retrieve over on-disk page text. Never fetches. Never invents."""
    text = (question or "").strip()
    if not text:
        return AskResult(ok=False, empty=False, message=_NEED_QUESTION)
    files = page_files(folder)
    if not files:
        return AskResult(ok=True, empty=True, message=_EMPTY)
    terms = query_terms(text)
    if not terms:
        return AskResult(ok=True, empty=False, message=_NO_MATCH)
    hits: list[Hit] = []
    for path in files:
        try:
            body = path.read_text(encoding="utf-8")
        except OSError:
            continue
        hit = _best_hit(body, terms)
        if hit is not None:
            hits.append(hit)
    hits.sort(key=lambda item: item.score, reverse=True)
    kept = tuple(hits[:_MAX_HITS])
    if not kept:
        return AskResult(ok=True, empty=False, message=_NO_MATCH, hits=())
    return AskResult(ok=True, empty=False, message="Match on disk.", hits=kept)


def _best_hit(body: str, terms: list[str]) -> Hit | None:
    lines = body.splitlines()
    title = (lines[0].strip() if lines else "") or "untitled"
    words = _WORD.findall(body.lower())
    if not words:
        return None
    best_score = 0
    best_start = 0
    window = _SNIP_WORDS
    if len(words) <= window:
        score = _score(words, terms)
        if score <= 0:
            return None
        return Hit(title=title, snippet=_clip(body, terms), score=score)
    for start in range(0, len(words) - window + 1, 4):
        score = _score(words[start : start + window], terms)
        if score > best_score:
            best_score = score
            best_start = start
    if best_score <= 0:
        return None
    snippet = " ".join(words[best_start : best_start + window])
    return Hit(title=title, snippet=snippet, score=best_score)


def _score(words: list[str], terms: list[str]) -> int:
    bag = set(words)
    return sum(1 for term in terms if term in bag)


def _clip(body: str, terms: list[str]) -> str:
    words = _WORD.findall(body)
    if not words:
        return ""
    lower = [word.lower() for word in words]
    start = 0
    for index, word in enumerate(lower):
        if word in terms:
            start = max(0, index - 8)
            break
    return " ".join(words[start : start + _SNIP_WORDS])

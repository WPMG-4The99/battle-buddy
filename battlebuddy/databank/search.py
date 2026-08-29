"""Ask saved page text. Keyword retrieve only. No invent."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from battlebuddy.databank.clean import recipe_sentence, strip_markup
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
_WEAK = {
    "get",
    "make",
    "need",
    "please",
    "production",
    "set",
    "setup",
    "start",
    "up",
    "want",
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
    question: str = ""

    def output(self) -> str:
        """One pane. Recipe sentence first when we have one. No markup dump."""
        if not self.hits:
            return self.message
        nouns = content_terms(query_terms(self.question))
        for hit in self.hits:
            snippet = strip_markup(hit.snippet)
            recipe = recipe_sentence(snippet, nouns)
            if recipe:
                return f"{recipe}\n{hit.title}"
        blocks = [f"{hit.title}\n{strip_markup(hit.snippet)}" for hit in self.hits]
        return "\n\n".join(blocks)


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


def content_terms(terms: list[str]) -> list[str]:
    """Distinctive words a hit must contain. Weak verbs cannot carry a hit."""
    return [term for term in terms if term not in _WEAK]


def ask_pages(store: DatabankStore, game: str | None, question: str) -> AskResult:
    """Search the game folder, then any other on-disk folder that matches."""
    result = search_folder(store.folder(game), question)
    if not result.ok or result.hits:
        return result
    other = _ask_other_folders(store, game, question)
    return other if other is not None else result


def _ask_other_folders(
    store: DatabankStore,
    game: str | None,
    question: str,
) -> AskResult | None:
    """When the chosen folder misses, use another databank that has the pages."""
    skip = store.folder(game).resolve()
    folders = [path for path in store.list_saved_folders() if path.resolve() != skip]
    if not folders:
        return None
    if len(folders) == 1:
        found = search_folder(folders[0], question)
        return found if found.ok else None
    matched: list[AskResult] = []
    for folder in folders:
        found = search_folder(folder, question)
        if found.hits:
            matched.append(found)
    if not matched:
        return None
    if len(matched) == 1:
        return matched[0]
    hits: list[Hit] = []
    for item in matched:
        hits.extend(item.hits)
    hits.sort(key=lambda item: item.score, reverse=True)
    kept = tuple(hits[:_MAX_HITS])
    return AskResult(
        ok=True,
        empty=False,
        message="Match on disk.",
        hits=kept,
        question=question,
    )


def search_folder(folder: Path, question: str) -> AskResult:
    """Keyword retrieve over on-disk page text. Never fetches. Never invents."""
    text = (question or "").strip()
    if not text:
        return AskResult(ok=False, empty=False, message=_NEED_QUESTION, question=text)
    files = page_files(folder)
    if not files:
        return AskResult(ok=True, empty=True, message=_EMPTY, question=text)
    terms = query_terms(text)
    needed = content_terms(terms)
    if not needed:
        return AskResult(ok=True, empty=False, message=_NO_MATCH, question=text)
    hits: list[Hit] = []
    for path in files:
        try:
            body = path.read_text(encoding="utf-8")
        except OSError:
            continue
        hit = _best_hit(body, terms, needed)
        if hit is not None:
            hits.append(hit)
    hits.sort(key=lambda item: item.score, reverse=True)
    kept = tuple(hits[:_MAX_HITS])
    if not kept:
        return AskResult(ok=True, empty=False, message=_NO_MATCH, hits=(), question=text)
    return AskResult(ok=True, empty=False, message="Match on disk.", hits=kept, question=text)


def _best_hit(body: str, terms: list[str], needed: list[str]) -> Hit | None:
    lines = body.splitlines()
    title = strip_markup(lines[0] if lines else "") or "untitled"
    cleaned = strip_markup(body)
    words = _WORD.findall(cleaned.lower())
    if not words:
        return None
    recipe = recipe_sentence(cleaned, needed)
    window = _SNIP_WORDS
    if len(words) <= window:
        if not _has_content(words, needed):
            return None
        score = _score(words, terms)
        if score <= 0:
            return None
        return Hit(title=title, snippet=recipe or _clip_cleaned(cleaned, needed), score=score)
    best_score = 0
    for start in range(0, len(words) - window + 1, 4):
        chunk = words[start : start + window]
        if not _has_content(chunk, needed):
            continue
        score = _score(chunk, terms)
        if score > best_score:
            best_score = score
    if best_score <= 0:
        return None
    snippet = recipe or _clip_cleaned(cleaned, needed)
    return Hit(title=title, snippet=snippet, score=best_score)


def _has_content(words: list[str], needed: list[str]) -> bool:
    bag = set(words)
    return any(_term_in(bag, term) for term in needed)


def _score(words: list[str], terms: list[str]) -> int:
    bag = set(words)
    return sum(1 for term in terms if _term_in(bag, term))


def _term_in(bag: set[str], term: str) -> bool:
    """Simple singular/plural. spear on disk matches spears in the question."""
    if term in bag:
        return True
    if term.endswith("s") and len(term) > 1 and term[:-1] in bag:
        return True
    return f"{term}s" in bag


def _clip_cleaned(cleaned: str, needed: list[str]) -> str:
    """Keep original case. Start near the first content word."""
    tokens = cleaned.split()
    if not tokens:
        return ""
    start = 0
    for index, token in enumerate(tokens):
        bag = set(_WORD.findall(token.lower()))
        if any(_term_in(bag, term) for term in needed):
            start = max(0, index - 8)
            break
    return " ".join(tokens[start : start + _SNIP_WORDS])

"""Ask saved page text. Keyword retrieve only. No invent."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from battlebuddy.databank.clean import (
    compile_claim_line,
    compile_howto_line,
    compile_livestock_line,
    expand_search_terms,
    livestock_page_signal,
    is_claim_question,
    is_howto_question,
    is_livestock_question,
    is_patch_title,
    is_start_question,
    page_require_line,
    recipe_sentence,
    start_path_sentence,
    strip_markup,
    term_in,
)
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
    "another",
    "folks",
    "get",
    "into",
    "make",
    "need",
    "people",
    "person",
    "please",
    "plot",
    "plots",
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
_HOWTO_MISS = "Can't find that. Restate the question."
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
        """One pane. Start-path or recipe first. Skip patch-note scraps."""
        if not self.hits:
            return self.message
        texts = [
            f"{hit.title}.\n{strip_markup(hit.snippet)}"
            for hit in self.hits
            if not is_patch_title(hit.title)
        ]
        if not texts:
            texts = [f"{hit.title}.\n{strip_markup(hit.snippet)}" for hit in self.hits]
        extracted = compile_ask_line(self.question, texts)
        if extracted:
            return extracted
        nouns = content_terms(query_terms(self.question))
        for hit in self.hits:
            if is_patch_title(hit.title):
                continue
            snippet = strip_markup(hit.snippet)
            recipe = recipe_sentence(snippet, nouns)
            if recipe:
                return f"{recipe}\n{hit.title}"
        if is_howto_question(self.question):
            return _HOWTO_MISS
        blocks = [
            f"{hit.title}\n{strip_markup(hit.snippet)}"
            for hit in self.hits
            if not is_patch_title(hit.title)
        ]
        if not blocks:
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


def compile_ask_line(question: str, texts: list[str]) -> str | None:
    """Start path, recipe, or enabling how-to. No invent."""
    nouns = content_terms(query_terms(question))
    if is_start_question(question):
        for text in texts:
            path = start_path_sentence(text, nouns)
            if path:
                return path
    recipes: list[str] = []
    for text in texts:
        body = _after_title(text)
        recipe = recipe_sentence(body, nouns) or recipe_sentence(strip_markup(text), nouns)
        if recipe:
            recipes.append(recipe)
    for recipe in recipes:
        if " into " in recipe.lower():
            return recipe
    if recipes:
        return recipes[0]
    if is_claim_question(question):
        claim = compile_claim_line(texts)
        if claim:
            return claim
    if is_livestock_question(question):
        livestock = compile_livestock_line(texts)
        if livestock:
            return livestock
        # How-to livestock with no Animal Pen compile is a miss, not burgage junk.
        if is_howto_question(question):
            return None
    if is_howto_question(question):
        return compile_howto_line(texts, nouns)
    return None


def page_texts_for_hits(
    store: DatabankStore | None,
    game: str | None,
    result: AskResult,
    cap: int | None = None,
) -> list[str]:
    """Full saved pages for hits. Skip patch-note titles. Snippet if missing."""
    texts: list[str] = []
    for hit in result.hits:
        if is_patch_title(hit.title):
            continue
        body = ""
        if store is not None:
            body = page_text_for_title(
                store, game, hit.title, cap, snippet=hit.snippet
            )
        texts.append(body or f"{hit.title}.\n{strip_markup(hit.snippet)}")
    return texts


def livestock_compile_texts(
    store: DatabankStore | None,
    game: str | None,
    result: AskResult,
) -> list[str]:
    """Hit pages plus any saved Animal Pen / livestock-trader page. Extract only."""
    texts = page_texts_for_hits(store, game, result, cap=None)
    if store is None:
        return texts
    seen = {strip_markup(item).lower()[:80] for item in texts}
    folders = [store.folder(game)]
    known = {folders[0].resolve()}
    for extra in store.list_saved_folders():
        key = extra.resolve()
        if key in known:
            continue
        known.add(key)
        folders.append(extra)
    for folder in folders:
        for path in page_files(folder):
            try:
                raw = path.read_text(encoding="utf-8")
            except OSError:
                continue
            first = (raw.splitlines()[0].strip() if raw else "") or "untitled"
            if is_patch_title(first):
                continue
            parts = raw.split("\n", 2)
            body = parts[2] if len(parts) > 2 else raw
            cleaned = strip_markup(body)
            if not livestock_page_signal(cleaned):
                continue
            blob = f"{first}.\n{cleaned}"
            key = strip_markup(blob).lower()[:80]
            if key in seen:
                continue
            seen.add(key)
            texts.append(blob)
    return texts


def page_text_for_title(
    store: DatabankStore,
    game: str | None,
    title: str,
    cap: int | None = None,
    snippet: str | None = None,
) -> str:
    """Saved page body for a hit title. Same title: snippet match, else longest."""
    wanted = (title or "").strip()
    if not wanted:
        return ""
    folders = [store.folder(game)]
    seen = {folders[0].resolve()}
    for extra in store.list_saved_folders():
        key = extra.resolve()
        if key in seen:
            continue
        seen.add(key)
        folders.append(extra)
    matches: list[tuple[str, str]] = []
    for folder in folders:
        for path in page_files(folder):
            try:
                raw = path.read_text(encoding="utf-8")
            except OSError:
                continue
            first = (raw.splitlines()[0].strip() if raw else "") or "untitled"
            if first != wanted:
                continue
            parts = raw.split("\n", 2)
            text = parts[2] if len(parts) > 2 else raw
            cleaned = strip_markup(text)
            capped = cleaned if cap is None else cleaned[:cap]
            matches.append((cleaned, f"{first}.\n{capped}"))
    if not matches:
        return ""
    snip = strip_markup(snippet or "").strip()
    if snip:
        ranked = sorted(
            matches,
            key=lambda item: (_snippet_overlap(item[0], snip), len(item[0])),
            reverse=True,
        )
        if _snippet_overlap(ranked[0][0], snip) > 0:
            return ranked[0][1]
    matches.sort(key=lambda item: len(item[0]), reverse=True)
    return matches[0][1]


def _snippet_overlap(body: str, snippet: str) -> int:
    """How much of the hit snippet is in this body. Stitched lines still score."""
    snip = strip_markup(snippet or "").strip().lower()
    blob = (body or "").lower()
    if not snip or not blob:
        return 0
    if snip in blob:
        return 10_000 + len(snip)
    words = [item for item in _WORD.findall(snip) if len(item) > 1]
    if not words:
        return 0
    bag = set(_WORD.findall(blob))
    return sum(1 for item in words if item in bag)


def _after_title(text: str) -> str:
    raw = text or ""
    if "\n" in raw:
        return raw.split("\n", 1)[1]
    return raw


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
        hit = _best_hit(body, terms, needed, text)
        if hit is not None:
            hits.append(hit)
    hits.sort(key=lambda item: item.score, reverse=True)
    kept = tuple(hits[:_MAX_HITS])
    if not kept:
        return AskResult(ok=True, empty=False, message=_NO_MATCH, hits=(), question=text)
    return AskResult(ok=True, empty=False, message="Match on disk.", hits=kept, question=text)


def _best_hit(body: str, terms: list[str], needed: list[str], question: str = "") -> Hit | None:
    lines = body.splitlines()
    title = strip_markup(lines[0] if lines else "") or "untitled"
    rest = "\n".join(lines[2:]) if len(lines) > 2 else body
    cleaned = strip_markup(rest)
    words = _WORD.findall(f"{title} {cleaned}".lower())
    if not words:
        return None
    combined = f"{title}.\n{cleaned}"
    match_needed = expand_search_terms(question, needed)
    match_terms = expand_search_terms(question, terms)
    path = start_path_sentence(combined, needed) if is_start_question(question) else None
    recipe = recipe_sentence(cleaned, needed)
    livestock = compile_livestock_line([combined]) if is_livestock_question(question) else None
    howto = None
    if livestock is None and not is_livestock_question(question) and is_howto_question(question):
        howto = compile_howto_line([combined], needed)
    claim = compile_claim_line([combined]) if is_claim_question(question) else None
    require = (
        page_require_line(cleaned, needed)
        if howto is None and claim is None and livestock is None
        else None
    )
    snippet = (
        path
        or recipe
        or livestock
        or howto
        or claim
        or require
        or _clip_cleaned(cleaned, match_needed)
    )
    window = _SNIP_WORDS
    if len(words) <= window:
        if not _has_content(words, match_needed):
            return None
        score = _score(words, match_terms)
        if score <= 0:
            return None
        return Hit(
            title=title,
            snippet=snippet,
            score=_adjust_score(
                score,
                title,
                path,
                recipe,
                livestock or howto or claim,
                livestock_signal=is_livestock_question(question) and livestock_page_signal(cleaned),
            ),
        )
    best_score = 0
    for start in range(0, len(words) - window + 1, 4):
        chunk = words[start : start + window]
        if not _has_content(chunk, match_needed):
            continue
        score = _score(chunk, match_terms)
        if score > best_score:
            best_score = score
    if best_score <= 0:
        return None
    return Hit(
        title=title,
        snippet=snippet,
        score=_adjust_score(
            best_score,
            title,
            path,
            recipe,
            livestock or howto or claim,
            livestock_signal=is_livestock_question(question) and livestock_page_signal(cleaned),
        ),
    )


def _adjust_score(
    score: int,
    title: str,
    path: str | None,
    recipe: str | None,
    howto: str | None = None,
    livestock_signal: bool = False,
) -> int:
    """Demote patch notes. Prefer a compiled start path, produce row, or enable line."""
    low = (title or "").lower()
    if is_patch_title(title):
        score -= 10
    if path:
        score += 4
    elif recipe:
        score += 2
    elif howto:
        score += 4
    if livestock_signal and not howto:
        score += 4
    if "official wiki" in low:
        score += 3
    if "fandom" in low:
        score -= 3
    return score


def _has_content(words: list[str], needed: list[str]) -> bool:
    bag = set(words)
    return any(_term_in(bag, term) for term in needed)


def _score(words: list[str], terms: list[str]) -> int:
    bag = set(words)
    return sum(1 for term in terms if _term_in(bag, term))


def _term_in(bag: set[str], term: str) -> bool:
    """Singular/plural and tax/taxing. Weak fillers are dropped before this."""
    return term_in(bag, term)


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

"""Strip wiki scraps. Prefer a recipe sentence. No invent."""

from __future__ import annotations

import html
import re

_ICON = re.compile(r"\{\{\s*Icon\s*\|[^}]*\}\}", re.IGNORECASE)
_HTML = re.compile(r"<[^>]+>")
_WORD = re.compile(r"[a-z0-9]+")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_CRAFT_WORDS = ("obtained", "produced", "backyard")
_CRAFT_PAIRS = (("blacksmiths", "workshop"), ("blacksmith", "workshop"))


def strip_markup(text: str) -> str:
    """Drop {{Icon|...}}, HTML tags, and &#039;-style entities."""
    raw = text or ""
    raw = _ICON.sub(" ", raw)
    raw = _HTML.sub(" ", raw)
    raw = html.unescape(raw)
    return " ".join(raw.split())


def recipe_sentence(text: str, nouns: list[str] | None = None) -> str | None:
    """First sentence with a craft cue. Nouns required when the question has them."""
    cleaned = strip_markup(text)
    if not cleaned:
        return None
    needed = [item.lower() for item in (nouns or []) if item]
    for sent in _sentences(cleaned):
        if _is_recipe(sent, needed):
            return sent
    if _is_recipe(cleaned, needed) and len(cleaned.split()) <= 40:
        return cleaned
    return None


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE.split(text) if part.strip()]


def _is_recipe(text: str, nouns: list[str]) -> bool:
    words = _cue_words(text)
    if not _has_craft(words):
        return False
    if not nouns:
        return True
    bag = set(words)
    return any(_term_in(bag, noun) for noun in nouns)


def _has_craft(words: list[str]) -> bool:
    if set(words) & set(_CRAFT_WORDS):
        return True
    pairs = set(_CRAFT_PAIRS)
    return any((words[i], words[i + 1]) in pairs for i in range(len(words) - 1))


def _cue_words(blob: str) -> list[str]:
    text = (blob or "").lower().replace("'", "").replace("’", "")
    return _WORD.findall(text)


def _term_in(bag: set[str], term: str) -> bool:
    if term in bag:
        return True
    if term.endswith("s") and len(term) > 1 and term[:-1] in bag:
        return True
    return f"{term}s" in bag

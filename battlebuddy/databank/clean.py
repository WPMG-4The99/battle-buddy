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
_MAX_RECIPE_WORDS = 30
# Flattened wiki produce rows: "1 Iron Slab and 1 Plank into 2 Spears"
_PRODUCE = re.compile(
    r"(?P<inputs>\d+\s+[A-Za-z][A-Za-z']*(?:\s+[A-Za-z][A-Za-z']*){0,3}"
    r"(?:\s+and\s+\d+\s+[A-Za-z][A-Za-z']*(?:\s+[A-Za-z][A-Za-z']*){0,3})*)"
    r"\s+into\s+(?P<count>\d+)\s+"
    r"(?P<product>[A-Za-z][A-Za-z']*(?:\s+[A-Za-z][A-Za-z']*){0,2})",
    re.IGNORECASE,
)
# Row header before cost digits: Blacksmith 8 / Blacksmith's Workshop 8
_ROW_BUILDING = re.compile(
    r"\b(?P<name>[A-Z][A-Za-z]+(?:'s(?:\s+Workshop)?)?)\s+\d+"
)
_NOT_BUILDING = {
    "affinities",
    "backyard",
    "backyards",
    "cost",
    "extension",
    "maintenance",
    "perks",
    "plank",
    "planks",
    "produces",
    "requires",
    "rw",
    "tier",
}


def strip_markup(text: str) -> str:
    """Drop {{Icon|...}}, HTML tags, and &#039;-style entities."""
    raw = text or ""
    raw = _ICON.sub(" ", raw)
    raw = _HTML.sub(" ", raw)
    raw = html.unescape(raw)
    return " ".join(raw.split())


def recipe_sentence(text: str, nouns: list[str] | None = None) -> str | None:
    """Short recipe line. Table produce first, then a capped prose sentence."""
    cleaned = strip_markup(text)
    if not cleaned:
        return None
    needed = [item.lower() for item in (nouns or []) if item]
    table = _table_recipe(cleaned, needed)
    if table:
        return table
    for sent in _sentences(cleaned):
        if _is_recipe(sent, needed) and _short_enough(sent):
            return sent
    if _is_recipe(cleaned, needed) and _short_enough(cleaned):
        return cleaned
    return None


def _table_recipe(text: str, nouns: list[str]) -> str | None:
    """Pull `into N <noun>` and the nearest shop before it. Extract, do not invent."""
    matches = list(_PRODUCE.finditer(text))
    if not matches:
        return None
    picked = None
    for match in matches:
        if nouns:
            bag = set(_cue_words(match.group("product")))
            if not any(_term_in(bag, noun) for noun in nouns):
                continue
        picked = match
        break
    if picked is None:
        return None
    # No question nouns: do not pick a random shop out of a backyard dump.
    if not nouns and len(matches) > 1 and not _short_enough(text):
        return None
    building = _nearest_building(text[: picked.start()])
    inputs = " ".join(picked.group("inputs").split())
    count = picked.group("count")
    product = " ".join(picked.group("product").split())
    if building:
        line = f"{building}: {inputs} into {count} {product}."
    else:
        line = f"{inputs} into {count} {product}."
    if not _short_enough(line):
        return None
    return line


def _nearest_building(prefix: str) -> str | None:
    """Last shop-like token before the produce clause (Blacksmith, Workshop)."""
    found: list[str] = []
    for match in _ROW_BUILDING.finditer(prefix):
        name = " ".join(match.group("name").split())
        words = _cue_words(name)
        if not words or any(word in _NOT_BUILDING for word in words):
            continue
        found.append(name)
    if not found:
        return None
    return found[-1]


def _short_enough(text: str) -> bool:
    return 0 < len(text.split()) <= _MAX_RECIPE_WORDS


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
    for index, word in enumerate(words[:-1]):
        if word == "into" and words[index + 1].isdigit():
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

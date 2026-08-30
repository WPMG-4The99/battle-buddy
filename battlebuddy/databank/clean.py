"""Strip wiki scraps. Prefer a recipe sentence. No invent."""

from __future__ import annotations

import html
import re

_ICON = re.compile(r"\{\{\s*Icon\s*\|[^}]*\}\}", re.IGNORECASE)
_HTML = re.compile(r"<[^>]+>")
_WIKI_TICKS = re.compile(r"'{2,}")
_LIST_STAR = re.compile(r"(?m)^\s*\*\s+")
_WORD = re.compile(r"[a-z0-9]+")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
# Prose recipe only. "produced" matches patch notes. Lone "backyard" is a definition.
_CRAFT_WORDS = ("obtained",)
_CRAFT_PAIRS = (("blacksmiths", "workshop"), ("blacksmith", "workshop"))
_MAX_RECIPE_WORDS = 30
_START_WORDS = {"start", "begin", "setup"}
_PROD_WORDS = {"production", "produce", "producing"}
_PATCH_MARKERS = (
    "patch note",
    "patch notes",
    "hotfix",
    "changelog",
    "version history",
    "update notes",
)
_VERSION_TITLE = re.compile(r"^\s*\d+\.\d+(?:\.\d+)?\b")
_TIER_AT = re.compile(
    r"\b(?:tier|t)\s*([123])\s+backyards?\b|\blevel\s+([123])\s+enables\b",
    re.IGNORECASE,
)
_COST_ROW = re.compile(
    r"(?P<planks>\d+)\s+[Pp]lanks?\s+(?P<rw>\d+)\s+(?:RW|[Rr]egional\s+[Ww]ealth)\b"
)
_COST_PAREN = re.compile(
    r"\((?P<planks>\d+)\s+planks?,?\s+(?P<rw>\d+)\s+regional\s+wealth\)",
    re.IGNORECASE,
)
# Flattened wiki produce rows: "1 Iron Slab and 1 Plank into 2 Spears"
# No IGNORECASE — product stays capitalized so trailing "or" is not swallowed.
_PRODUCE = re.compile(
    r"(?P<inputs>\d+\s+[A-Za-z][A-Za-z']*(?:\s+[A-Za-z][A-Za-z']*){0,3}"
    r"(?:\s+(?:and|And|AND)\s+\d+\s+[A-Za-z][A-Za-z']*(?:\s+[A-Za-z][A-Za-z']*){0,3})*)"
    r"\s+(?:into|Into|INTO)\s+(?P<count>\d+)\s+"
    r"(?P<product>[A-Z][A-Za-z']*(?:\s+[A-Z][A-Za-z']*){0,2})"
)
# Row header before cost digits: Blacksmith 8 / Blacksmith's Workshop 8
_ROW_BUILDING = re.compile(
    r"\b(?P<name>[A-Z][A-Za-z]+(?:'s(?:\s+Workshop)?)?)\s+\d+"
)
# Already-extracted line: "Blacksmith: 1 Iron Slab ..."
_LABELED_SHOP = re.compile(
    r"\b(?P<name>[A-Z][A-Za-z]+(?:'s(?:\s+Workshop)?)?):\s*$"
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
    "level",
    "levels",
    "indicates",
    "possibility",
    "changed",
    "order",
    "goods",
    "main",
}


def strip_markup(text: str) -> str:
    """Drop {{Icon|...}}, HTML tags, wiki bold/italic, list stars, and entities."""
    raw = text or ""
    raw = _ICON.sub(" ", raw)
    raw = _HTML.sub(" ", raw)
    raw = html.unescape(raw)
    raw = _WIKI_TICKS.sub(" ", raw)
    raw = _LIST_STAR.sub(" ", raw)
    return " ".join(raw.split())


def is_patch_title(title: str) -> bool:
    """Version-history / patch / hotfix titles. Not a how-to page."""
    raw = title or ""
    text = raw.strip().lower()
    if not text:
        return False
    if any(marker in text for marker in _PATCH_MARKERS):
        return True
    return bool(_VERSION_TITLE.match(raw))


def is_start_question(question: str) -> bool:
    """how + start/set up/begin + production. Wispr '?' is optional."""
    words = set(_WORD.findall((question or "").lower()))
    if "how" not in words:
        return False
    started = bool(words & _START_WORDS) or ("set" in words and "up" in words)
    return started and bool(words & _PROD_WORDS)


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


_ALREADY_PATH = re.compile(
    r"(Upgrade a burgage plot to level [123] and add the [^.]+\. "
    r"[^.]+: \d+ .+ into \d+ [^.]+\.)",
    re.IGNORECASE,
)


def start_path_sentence(text: str, nouns: list[str] | None = None) -> str | None:
    """Burgage level + backyard cost + produce row. Extract, do not invent."""
    cleaned = strip_markup(text)
    if not cleaned:
        return None
    already = _ALREADY_PATH.search(cleaned)
    if already and _short_enough(already.group(1)):
        return already.group(1)
    needed = [item.lower() for item in (nouns or []) if item]
    picked = _picked_produce(cleaned, needed)
    recipe = _format_recipe(cleaned, picked) if picked is not None else None
    if not recipe or ":" not in recipe:
        return None
    building = recipe.split(":", 1)[0].strip()
    if not building or "burgage" not in cleaned.lower():
        return None
    row_pos = picked.start()
    level = _level_for_building(cleaned, building, row_pos)
    if level is None:
        return None
    cost = _extension_cost(cleaned, building, row_pos)
    shop = f"{building} backyard"
    if cost:
        shop = f"{shop} ({cost})"
    line = f"Upgrade a burgage plot to level {level} and add the {shop}. {recipe}"
    if not _short_enough(line):
        return None
    return line


def _table_recipe(text: str, nouns: list[str]) -> str | None:
    """Pull `into N <noun>` and the nearest shop before it. Extract, do not invent."""
    picked = _picked_produce(text, nouns)
    if picked is None:
        return None
    return _format_recipe(text, picked)


def _picked_produce(text: str, nouns: list[str]) -> re.Match[str] | None:
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
    return picked


def _format_recipe(text: str, picked: re.Match[str]) -> str | None:
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


def _level_for_building(text: str, building: str, row_pos: int | None = None) -> int | None:
    """Last Tier/Level header before the produce row. Ignore wiki-nav chrome."""
    raw = text or ""
    pos = row_pos if row_pos is not None else _shop_row_pos(raw, building)
    last: int | None = None
    for match in _TIER_AT.finditer(raw):
        if pos is not None and match.start() > pos:
            break
        digit = match.group(1) or match.group(2)
        if digit:
            last = int(digit)
    if last is not None:
        return last
    if "burgage" not in raw.lower():
        return None
    upgrade = re.search(r"upgrade a burgage plot to level\s+([123])\b", raw, re.IGNORECASE)
    if upgrade:
        return int(upgrade.group(1))
    for match in re.finditer(r"\blevel\s+([123])\s+enables\b", raw, re.IGNORECASE):
        if pos is not None and match.start() > pos:
            break
        last = int(match.group(1))
    return last


def _shop_row_pos(text: str, building: str) -> int | None:
    """Cost or labeled produce row for the shop. Not 'Blacksmith Master' nav."""
    root = (building or "").split("'")[0]
    if not root:
        return None
    escaped = re.escape(root)
    cost = re.compile(
        rf"\b{escaped}(?:'s(?:\s+Workshop)?)?\s+\d+\s+[Pp]lanks?\b",
        re.IGNORECASE,
    )
    found = list(cost.finditer(text or ""))
    if found:
        return found[-1].start()
    labeled = re.compile(
        rf"\b{escaped}(?:'s(?:\s+Workshop)?)?:\s+\d+",
        re.IGNORECASE,
    )
    found = list(labeled.finditer(text or ""))
    if found:
        return found[-1].start()
    return None


def _extension_cost(text: str, building: str, row_pos: int | None = None) -> str | None:
    """`Blacksmith 8 Planks 25 RW` or `(8 planks, 25 regional wealth)`."""
    raw = text or ""
    root = (building or "").split("'")[0]
    if not root:
        return None
    best: str | None = None
    for match in _COST_ROW.finditer(raw):
        if row_pos is not None and match.start() > row_pos:
            break
        prefix = raw[max(0, match.start() - 48) : match.start()]
        if root.lower() in prefix.lower():
            best = f"{match.group('planks')} planks, {match.group('rw')} regional wealth"
    if best:
        return best
    paren = _COST_PAREN.search(raw)
    if paren and root.lower() in raw.lower():
        if row_pos is None or paren.start() <= row_pos:
            return f"{paren.group('planks')} planks, {paren.group('rw')} regional wealth"
    return None


def _nearest_building(prefix: str) -> str | None:
    """Last shop-like token before the produce clause (Blacksmith, Workshop)."""
    labeled = _LABELED_SHOP.search(prefix)
    if labeled:
        name = " ".join(labeled.group("name").split())
        words = _cue_words(name)
        if words and not any(word in _NOT_BUILDING for word in words):
            return name
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

"""Home-roster War Room parse and recall. No account. No wiki dump."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

ROSTER_NAMES: tuple[str, ...] = (
    "Star Citizen",
    "Bellwright",
    "Corsair Cove",
    "ASKA",
    "Clanfolk",
)

ROSTER_REFUSE = (
    "Not on the home roster. War Room stays shut. Say add [title] "
    "to the roster if you want standing state."
)

KINDS: tuple[str, ...] = ("place", "patch", "decision", "trap")

_ALIASES: dict[str, str] = {
    "sc": "Star Citizen",
    "star citizen": "Star Citizen",
    "bellwright": "Bellwright",
    "corsair cove": "Corsair Cove",
    "aska": "ASKA",
    "clanfolk": "Clanfolk",
}

_BY_LOWER: dict[str, str] = {name.lower(): name for name in ROSTER_NAMES}

_KIND_ALT = "|".join(KINDS)

_REMEMBER_KIND = re.compile(
    rf"^remember\s+(?P<kind>{_KIND_ALT})\s+for\s+(?P<game>.+?)\s*:\s*(?P<text>.+)$",
    re.IGNORECASE,
)
_REMEMBER_FOR = re.compile(
    r"^remember\s+for\s+(?P<game>.+?)\s*:\s*(?P<text>.+)$",
    re.IGNORECASE,
)
_REMEMBER_BARE = re.compile(
    r"^remember\s+(?P<text>.+)$",
    re.IGNORECASE,
)
_WHERE_IN = re.compile(
    r"^where\s+was\s+i\s+in\s+(?P<game>.+)$",
    re.IGNORECASE,
)
_WHERE = re.compile(r"^where\s+was\s+i$", re.IGNORECASE)
_WAR_ROOM_GAME = re.compile(
    r"^war\s+room\s+(?P<game>.+)$",
    re.IGNORECASE,
)
_WAR_ROOM = re.compile(r"^war\s+room$", re.IGNORECASE)
_CORRECT = re.compile(
    rf"^correct\s+(?P<game>.+?)\s+(?P<kind>{_KIND_ALT})\s*:\s*(?P<text>.+)$",
    re.IGNORECASE,
)
_WRONG = re.compile(
    rf"^no\s+that'?s\s+wrong\s+(?P<game>.+?)\s+(?P<kind>{_KIND_ALT})"
    r"(?:\s*:\s*(?P<text>.+))?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class WarRoomCommand:
    action: str
    game: str | None
    kind: str | None
    text: str | None


def resolve_roster(title: str) -> tuple[str, str] | None:
    """Display name and slug, or None if not on the home roster."""
    from battlebuddy.databank.slug import game_slug

    raw = " ".join(title.strip().split())
    if not raw:
        return None
    lowered = raw.lower()
    name = _ALIASES.get(lowered) or _BY_LOWER.get(lowered)
    if name is None:
        by_slug = {game_slug(item): item for item in ROSTER_NAMES}
        name = by_slug.get(game_slug(raw))
    if name is None:
        return None
    return name, game_slug(name)


def parse_war_room_line(line: str) -> WarRoomCommand | None:
    raw = " ".join(line.strip().split())
    if not raw:
        return None

    match = _REMEMBER_KIND.match(raw)
    if match:
        return WarRoomCommand(
            action="remember",
            game=match.group("game").strip(),
            kind=match.group("kind").lower(),
            text=match.group("text").strip(),
        )

    match = _REMEMBER_FOR.match(raw)
    if match:
        return WarRoomCommand(
            action="remember",
            game=match.group("game").strip(),
            kind="place",
            text=match.group("text").strip(),
        )

    match = _REMEMBER_BARE.match(raw)
    if match:
        text = match.group("text").strip()
        lowered = text.lower()
        if lowered.startswith("for ") or re.match(
            rf"^(?:{_KIND_ALT})\s+for\s+", lowered
        ):
            return None
        return WarRoomCommand(
            action="remember",
            game=None,
            kind="place",
            text=text,
        )

    match = _WHERE_IN.match(raw)
    if match:
        return WarRoomCommand(
            action="recall",
            game=match.group("game").strip(),
            kind=None,
            text=None,
        )
    if _WHERE.match(raw):
        return WarRoomCommand(action="recall", game=None, kind=None, text=None)

    match = _WAR_ROOM_GAME.match(raw)
    if match:
        return WarRoomCommand(
            action="recall",
            game=match.group("game").strip(),
            kind=None,
            text=None,
        )
    if _WAR_ROOM.match(raw):
        return WarRoomCommand(action="recall", game=None, kind=None, text=None)

    match = _CORRECT.match(raw)
    if match:
        return WarRoomCommand(
            action="correct",
            game=match.group("game").strip(),
            kind=match.group("kind").lower(),
            text=match.group("text").strip(),
        )

    match = _WRONG.match(raw)
    if match:
        replacement = match.group("text")
        return WarRoomCommand(
            action="correct",
            game=match.group("game").strip(),
            kind=match.group("kind").lower(),
            text=replacement.strip() if replacement else None,
        )

    return None


def _date_stamp(iso: str) -> str:
    try:
        parsed = datetime.fromisoformat(iso)
    except ValueError:
        return iso[:10] if iso else ""
    return parsed.date().isoformat()


def format_recall(
    name: str,
    place: str | None,
    patch: str | None,
    decisions: list[tuple[str, str]],
    traps: list[tuple[str, str]],
) -> str:
    lines = [
        name,
        f"place: {place or ''}".rstrip(),
        f"patch: {patch or ''}".rstrip(),
        "decisions:",
    ]
    for created_at, text in decisions:
        lines.append(f"  {_date_stamp(created_at)} {text}")
    lines.append("traps:")
    for created_at, text in traps:
        lines.append(f"  {_date_stamp(created_at)} {text}")
    lines.append("Say if this is wrong.")
    return "\n".join(lines)


def held_line(name: str, kind: str) -> str:
    return f"War Room · {name} · {kind} held. Say if this is wrong."


def corrected_line(name: str, kind: str) -> str:
    return f"War Room · {name} · {kind} corrected. Say if this is wrong."


def empty_line(name: str) -> str:
    return f"War Room empty for {name}."

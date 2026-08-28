"""Parse typed reminder lines. No account. No cloud."""

from __future__ import annotations

import re
from dataclasses import dataclass

_UNIT_SECONDS: dict[str, int] = {
    "second": 1,
    "seconds": 1,
    "sec": 1,
    "secs": 1,
    "minute": 60,
    "minutes": 60,
    "min": 60,
    "mins": 60,
    "hour": 3600,
    "hours": 3600,
    "hr": 3600,
    "hrs": 3600,
}

_UNIT = r"seconds?|secs?|minutes?|mins?|hours?|hrs?"

_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        rf"^\s*remind\s+me\s+in\s+(?P<n>\d+)\s*(?P<unit>{_UNIT})\s+to\s+(?P<text>.+?)\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        rf"^\s*in\s+(?P<n>\d+)\s*(?P<unit>{_UNIT})\s+remind\s+me(?:\s+to)?\s+(?P<text>.+?)\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        rf"^\s*remind\s+me\s+to\s+(?P<text>.+?)\s+in\s+(?P<n>\d+)\s*(?P<unit>{_UNIT})\s*$",
        re.IGNORECASE,
    ),
)


@dataclass(frozen=True)
class ParsedReminder:
    text: str
    delay_seconds: int
    amount: int
    unit: str

    @property
    def delay_label(self) -> str:
        unit = self.unit
        if self.amount == 1 and unit.endswith("s"):
            unit = unit[:-1]
        if self.amount != 1 and not unit.endswith("s"):
            unit = unit + "s"
        return f"{self.amount} {unit}"


def parse_reminder(line: str) -> ParsedReminder | None:
    raw = " ".join(line.strip().split())
    if not raw:
        return None
    for pattern in _PATTERNS:
        match = pattern.match(raw)
        if not match:
            continue
        amount = int(match.group("n"))
        unit_key = match.group("unit").lower()
        text = match.group("text").strip().rstrip(".")
        if amount < 1 or not text:
            return None
        seconds = amount * _UNIT_SECONDS[unit_key]
        return ParsedReminder(
            text=text,
            delay_seconds=seconds,
            amount=amount,
            unit=unit_key,
        )
    return None

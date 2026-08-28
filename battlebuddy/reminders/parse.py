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

_ONES = (
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
)
_TEENS = (
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
)
_TENS = (
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
)

_WORD_NUMBERS: dict[str, int] = {
    "a": 1,
    "an": 1,
    **{word: index for index, word in enumerate(_ONES, start=1)},
    **{word: index for index, word in enumerate(_TEENS, start=10)},
    **{word: (index + 2) * 10 for index, word in enumerate(_TENS)},
}

_ONES_ALT = "|".join(_ONES)
_TEENS_ALT = "|".join(_TEENS)
_TENS_ALT = "|".join(_TENS)
# Longer tokens first so "an" wins over "a" and teens win over "eight"/"nine".
_SPOKEN_AMOUNT = (
    rf"(?:an|a|{_TEENS_ALT}|{_ONES_ALT}|(?:{_TENS_ALT})(?:[\s-](?:{_ONES_ALT}))?)"
)
_AMOUNT = rf"(?:\d+|{_SPOKEN_AMOUNT})"

_UNIT = r"seconds?|secs?|minutes?|mins?|hours?|hrs?"

_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        rf"^\s*remind\s+me\s+in\s+(?P<n>{_AMOUNT})\s*(?P<unit>{_UNIT})\s+to\s+(?P<text>.+?)\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        rf"^\s*in\s+(?P<n>{_AMOUNT})\s*(?P<unit>{_UNIT})\s+remind\s+me(?:\s+to)?\s+(?P<text>.+?)\s*$",
        re.IGNORECASE,
    ),
    re.compile(
        rf"^\s*remind\s+me\s+to\s+(?P<text>.+?)\s+in\s+(?P<n>{_AMOUNT})\s*(?P<unit>{_UNIT})\s*$",
        re.IGNORECASE,
    ),
    # Delay first, no "remind me": "in one minute test wood supply"
    re.compile(
        rf"^\s*in\s+(?P<n>{_AMOUNT})\s*(?P<unit>{_UNIT})\s+(?:to\s+)?(?P<text>.+?)\s*$",
        re.IGNORECASE,
    ),
    # Task first, no "remind me": "test wood supply in one minute"
    re.compile(
        rf"^\s*(?P<text>.+?)\s+in\s+(?P<n>{_AMOUNT})\s*(?P<unit>{_UNIT})\s*$",
        re.IGNORECASE,
    ),
)

_LIST = re.compile(
    r"^\s*(?:list(?:\s+my)?(?:\s+reminders)?|ls|show(?:\s+my)?\s+reminders)\s*$",
    re.IGNORECASE,
)
_CLEAR_ALL = re.compile(r"^\s*clear\s+all\s*$", re.IGNORECASE)
_SNOOZE = re.compile(
    rf"^\s*snooze\s+(?P<query>.+?)\s+(?:for\s+)?(?P<n>{_AMOUNT})\s*(?P<unit>{_UNIT})\s*$",
    re.IGNORECASE,
)
_CLEAR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*clear\s+reminder\s+about\s+(?P<query>.+?)\s*$", re.IGNORECASE),
    re.compile(r"^\s*clear\s+reminder\s+(?P<query>.+?)\s*$", re.IGNORECASE),
    re.compile(r"^\s*clear\s+about\s+(?P<query>.+?)\s*$", re.IGNORECASE),
    re.compile(r"^\s*clear\s+(?P<query>.+?)\s*$", re.IGNORECASE),
)

# Wispr / spoken leftovers. Leading only. Longer phrases first.
_LEADING_FILLER = re.compile(
    r"^(?:i\s+need\s+to|set\s+a\s+reminder|real\s+quick|can\s+you|please)\s+",
    re.IGNORECASE,
)
_LEADING_TO = re.compile(r"^to\s+", re.IGNORECASE)


def _strip_leading_fillers(raw: str) -> str:
    text = raw
    stripped_any = False
    while True:
        updated, count = _LEADING_FILLER.subn("", text, count=1)
        if count == 0:
            break
        stripped_any = True
        text = updated.strip()
    if stripped_any:
        text = _LEADING_TO.sub("", text).strip()
    return text


def _amount_to_int(raw: str) -> int | None:
    token = raw.strip().lower()
    if token.isdigit():
        return int(token)
    parts = re.split(r"[\s-]+", token)
    if len(parts) == 1:
        return _WORD_NUMBERS.get(parts[0])
    if len(parts) == 2:
        tens = _WORD_NUMBERS.get(parts[0])
        ones = _WORD_NUMBERS.get(parts[1])
        if (
            tens is not None
            and ones is not None
            and tens >= 20
            and tens % 10 == 0
            and 1 <= ones <= 9
        ):
            return tens + ones
    return None


def delay_label(amount: int, unit: str) -> str:
    label_unit = unit
    if amount == 1 and label_unit.endswith("s"):
        label_unit = label_unit[:-1]
    if amount != 1 and not label_unit.endswith("s"):
        label_unit = label_unit + "s"
    return f"{amount} {label_unit}"


@dataclass(frozen=True)
class ParsedReminder:
    text: str
    delay_seconds: int
    amount: int
    unit: str

    @property
    def delay_label(self) -> str:
        return delay_label(self.amount, self.unit)


@dataclass(frozen=True)
class ParsedSnooze:
    query: str
    delay_seconds: int
    amount: int
    unit: str

    @property
    def delay_label(self) -> str:
        return delay_label(self.amount, self.unit)


def parse_reminder(line: str) -> ParsedReminder | None:
    raw = " ".join(line.strip().split()).rstrip(".")
    if not raw:
        return None
    raw = _strip_leading_fillers(raw)
    if not raw:
        return None
    if (
        is_list_command(raw)
        or is_clear_all(raw)
        or parse_snooze(raw) is not None
        or parse_clear(raw) is not None
    ):
        return None
    for pattern in _PATTERNS:
        match = pattern.match(raw)
        if not match:
            continue
        amount = _amount_to_int(match.group("n"))
        unit_key = match.group("unit").lower()
        text = match.group("text").strip().rstrip(".")
        if amount is None or amount < 1 or not text:
            return None
        seconds = amount * _UNIT_SECONDS[unit_key]
        return ParsedReminder(
            text=text,
            delay_seconds=seconds,
            amount=amount,
            unit=unit_key,
        )
    return None


def is_list_command(line: str) -> bool:
    return bool(_LIST.match(" ".join(line.strip().split())))


def is_clear_all(line: str) -> bool:
    return bool(_CLEAR_ALL.match(" ".join(line.strip().split())))


def parse_snooze(line: str) -> ParsedSnooze | None:
    raw = " ".join(line.strip().split())
    if not raw:
        return None
    match = _SNOOZE.match(raw)
    if not match:
        return None
    query = match.group("query").strip()
    amount = _amount_to_int(match.group("n"))
    unit_key = match.group("unit").lower()
    if amount is None or amount < 1 or not query:
        return None
    return ParsedSnooze(
        query=query,
        delay_seconds=amount * _UNIT_SECONDS[unit_key],
        amount=amount,
        unit=unit_key,
    )


def parse_clear(line: str) -> str | None:
    raw = " ".join(line.strip().split())
    if not raw or is_clear_all(raw):
        return None
    for pattern in _CLEAR_PATTERNS:
        match = pattern.match(raw)
        if not match:
            continue
        query = match.group("query").strip()
        if query:
            return query
    return None

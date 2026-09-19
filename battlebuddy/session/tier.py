"""Session help tier. Persist under BATTLEBUDDY_HOME. No account. No key."""

from __future__ import annotations

import json
import re
from pathlib import Path

from battlebuddy.memory.store import default_home

TIER_HANDHOLD = "handhold"
TIER_GENTLE = "gentle"
TIER_SOCRATIC = "socratic"
TIERS: tuple[str, ...] = (TIER_HANDHOLD, TIER_GENTLE, TIER_SOCRATIC)
DEFAULT_TIER = TIER_GENTLE
SESSION_NAME = "session.json"

TIER_LABELS: dict[str, str] = {
    TIER_HANDHOLD: "Hand-hold",
    TIER_GENTLE: "Gentle",
    TIER_SOCRATIC: "Socratic",
}

_TIER_ALIASES: dict[str, str] = {
    "handhold": TIER_HANDHOLD,
    "hand-hold": TIER_HANDHOLD,
    "hand hold": TIER_HANDHOLD,
    "hold my hand": TIER_HANDHOLD,
    "gentle": TIER_GENTLE,
    "socratic": TIER_SOCRATIC,
}

_PARSE = re.compile(
    r"^\s*tier(?:\s+is|\s+set)?(?:\s+(?P<tier>.+))?\s*$",
    re.IGNORECASE,
)


def is_tier_command(line: str) -> bool:
    first = (line or "").strip().split()[:1]
    return bool(first) and first[0].lower() == "tier"


def session_path(home: Path | None = None) -> Path:
    base = home if home is not None else default_home()
    return base / SESSION_NAME


def normalize_tier(raw: str | None) -> str | None:
    key = " ".join((raw or "").strip().lower().split())
    if not key:
        return None
    key = key.replace("_", "-")
    return _TIER_ALIASES.get(key)


def parse_tier_line(line: str) -> str | None:
    match = _PARSE.match(" ".join((line or "").split()))
    if not match:
        return None
    return normalize_tier(match.group("tier"))


def load_tier(home: Path | None = None) -> str:
    path = session_path(home)
    if not path.is_file():
        return DEFAULT_TIER
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_TIER
    if not isinstance(blob, dict):
        return DEFAULT_TIER
    found = normalize_tier(str(blob.get("tier") or ""))
    return found if found else DEFAULT_TIER


def save_tier(tier: str, home: Path | None = None) -> str:
    key = normalize_tier(tier) or DEFAULT_TIER
    path = session_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"tier": key}, indent=2) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)
    return key


def set_tier_message(tier: str) -> str:
    label = TIER_LABELS.get(tier, TIER_LABELS[DEFAULT_TIER])
    return f"Help · {label}. Next NEXT uses this."

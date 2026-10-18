"""Session help tier. Persist under BATTLEBUDDY_HOME. No account. No key."""

from __future__ import annotations

import json
import os
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


def _session_blob(home: Path | None = None) -> dict:
    path = session_path(home)
    if not path.is_file():
        return {}
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return blob if isinstance(blob, dict) else {}


def _write_session(blob: dict, home: Path | None = None) -> None:
    path = session_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(blob, indent=2) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


def save_tier(tier: str, home: Path | None = None) -> str:
    key = normalize_tier(tier) or DEFAULT_TIER
    blob = _session_blob(home)
    blob["tier"] = key
    _write_session(blob, home)
    return key


def set_tier_message(tier: str) -> str:
    label = TIER_LABELS.get(tier, TIER_LABELS[DEFAULT_TIER])
    return f"Help · {label}. Next NEXT uses this."


BRAIN_LOCAL = "local"
BRAIN_GROK = "grok"
BRAIN_DARK = "dark"
BRAINS: tuple[str, ...] = (BRAIN_LOCAL, BRAIN_GROK, BRAIN_DARK)
DEFAULT_BRAIN = BRAIN_DARK

_BRAIN_ALIASES: dict[str, str] = {
    "local": BRAIN_LOCAL,
    "sidecar": BRAIN_LOCAL,
    "bundled": BRAIN_LOCAL,
    "grok": BRAIN_GROK,
    "cloud": BRAIN_GROK,
    "dark": BRAIN_DARK,
    "off": BRAIN_DARK,
    "template": BRAIN_DARK,
}

_PARSE_BRAIN = re.compile(
    r"^\s*brain(?:\s+is|\s+set)?(?:\s+(?P<brain>.+))?\s*$",
    re.IGNORECASE,
)


def is_brain_command(line: str) -> bool:
    first = (line or "").strip().split()[:1]
    return bool(first) and first[0].lower() == "brain"


def normalize_brain(raw: str | None) -> str | None:
    key = " ".join((raw or "").strip().lower().split())
    if not key:
        return None
    key = key.replace("_", "-")
    return _BRAIN_ALIASES.get(key)


def parse_brain_line(line: str) -> str | None:
    match = _PARSE_BRAIN.match(" ".join((line or "").split()))
    if not match:
        return None
    return normalize_brain(match.group("brain"))


def load_brain(home: Path | None = None) -> str:
    found = normalize_brain(str(_session_blob(home).get("brain") or ""))
    if found:
        return found
    if (os.environ.get("XAI_API_KEY") or "").strip():
        return BRAIN_GROK
    return DEFAULT_BRAIN


def save_brain(brain: str, home: Path | None = None) -> str:
    key = normalize_brain(brain) or DEFAULT_BRAIN
    blob = _session_blob(home)
    blob["brain"] = key
    _write_session(blob, home)
    return key


def set_brain_message(brain: str) -> str:
    return f"Brain · {brain}. Next NEXT uses this."


def parse_window(raw: object) -> dict[str, int] | None:
    """Accept {width, height} plus optional x/y. Reject junk. Keep negative origin."""
    if not isinstance(raw, dict):
        return None
    try:
        width = int(raw["width"])
        height = int(raw["height"])
    except (KeyError, TypeError, ValueError):
        return None
    if width < 1 or height < 1:
        return None
    out = {"width": width, "height": height}
    try:
        out["x"] = int(raw["x"])
        out["y"] = int(raw["y"])
    except (KeyError, TypeError, ValueError):
        pass
    return out


def load_window(home: Path | None = None) -> dict[str, int] | None:
    return parse_window(_session_blob(home).get("window"))


def save_window(
    width: int,
    height: int,
    x: int | None = None,
    y: int | None = None,
    home: Path | None = None,
) -> None:
    """Merge window size into session.json. Other keys stay put."""
    blob = _session_blob(home)
    win: dict[str, int] = {"width": int(width), "height": int(height)}
    if x is not None and y is not None:
        win["x"] = int(x)
        win["y"] = int(y)
    blob["window"] = win
    _write_session(blob, home)


def window_geometry(
    win: dict[str, int] | None,
    *,
    default: str = "1200x800",
    min_w: int = 720,
    min_h: int = 560,
) -> str:
    """Tk geometry from a saved window blob. Floor at the UI min size."""
    if not win:
        return default
    width = max(int(min_w), int(win["width"]))
    height = max(int(min_h), int(win["height"]))
    if "x" in win and "y" in win:
        return f"{width}x{height}+{int(win['x'])}+{int(win['y'])}"
    return f"{width}x{height}"


_TK_GEO = re.compile(r"^(\d+)x(\d+)(?:([+-]-?\d+)([+-]-?\d+))?$")


def parse_tk_geometry(spec: str) -> dict[str, int] | None:
    """Parse WxH or WxH±X±Y, including a negative virtual-desktop origin."""
    match = _TK_GEO.match((spec or "").strip())
    if match is None:
        return None
    out = {"width": int(match.group(1)), "height": int(match.group(2))}
    if match.group(3) is not None and match.group(4) is not None:
        out["x"] = _signed_int(match.group(3))
        out["y"] = _signed_int(match.group(4))
    return out


def _signed_int(raw: str) -> int:
    text = (raw or "").strip()
    if text.startswith("+"):
        text = text[1:]
    return int(text)


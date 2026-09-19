"""One move from standing War Room fields. Template always. Grok optional."""

from __future__ import annotations

import os
from typing import Any, Callable

from battlebuddy.session.tier import DEFAULT_TIER, TIER_HANDHOLD, TIER_SOCRATIC, normalize_tier

_EMPTY = "Hold a place first."
_BRICK = "Next brick: HOLD after you do it."
_SAY = "Say if this is wrong."
_GROK_DARK = "Grok is dark. Scribe still holds."
_LOCAL_DARK = "Local is dark. Scribe still holds."
_MOVE_WORDS = 12
_WHY_WORDS = 16
_GROK_WORDS = 40
_COACH_TIMEOUT = 8
_COACH_MAX_TOKENS = 80
_COACH_SYSTEM = (
    "One next move from the fields only. Do not invent. Do not cite a wiki. "
    "No Jessica. Match the help tier. Keep it short."
)


def _clip_words(text: str, limit: int) -> str:
    words = [part for part in (text or "").split() if part]
    if not words:
        return ""
    return " ".join(words[:limit])


def _present(value: str | None) -> bool:
    return bool((value or "").strip())


def _pick(
    place: str | None,
    patch: str | None,
    trap: str | None,
    decision: str | None,
) -> tuple[str, str, str]:
    """kind, move, why from stored fields. Trap wins."""
    if trap:
        return "trap", f"check {trap}", "that's the trap you already named."
    if place:
        return (
            "place",
            f"return to {place} and name the next check.",
            "that's where you left it.",
        )
    if decision:
        return "decision", f"act on {decision}", "that's the call you already made."
    return "patch", f"confirm you are on {patch}", "that's the patch on disk."


def format_coach(
    *,
    place: str | None = None,
    patch: str | None = None,
    trap: str | None = None,
    decision: str | None = None,
    tier: str | None = None,
) -> str:
    """Deterministic next brick. Reuse stored fields only."""
    place_text = (place or "").strip() or None
    patch_text = (patch or "").strip() or None
    trap_text = (trap or "").strip() or None
    decision_text = (decision or "").strip() or None
    if not any(
        (
            _present(place_text),
            _present(patch_text),
            _present(trap_text),
            _present(decision_text),
        )
    ):
        return _EMPTY

    kind, move_raw, why_raw = _pick(place_text, patch_text, trap_text, decision_text)
    move = _clip_words(move_raw, _MOVE_WORDS)
    why = _clip_words(why_raw, _WHY_WORDS)
    level = normalize_tier(tier) or DEFAULT_TIER

    if level == TIER_SOCRATIC:
        if kind == "trap":
            question = f"What happens if {trap_text} hits again?"
        elif kind == "place":
            question = f"What's waiting at {place_text}?"
        elif kind == "decision":
            question = f"Does {decision_text} still hold?"
        else:
            question = f"Are you still on {patch_text}?"
        return _clip_words(question, 16)

    if level == TIER_HANDHOLD:
        lines = [f"Action: {move}"]
        if place_text:
            lines.append(f"Where: {place_text}")
        lines.extend((f"Why: {why}", _BRICK, _SAY))
        return "\n".join(lines)

    return "\n".join(
        (
            f"One move: {move}",
            f"Why: {why}",
            _BRICK,
            _SAY,
        )
    )


def _api_key() -> str | None:
    raw = (os.environ.get("XAI_API_KEY") or "").strip()
    return raw or None


def _harvest_line(harvest: Any) -> str:
    if harvest is None:
        return "harvest: none"
    live = getattr(harvest, "live", None)
    if isinstance(harvest, dict):
        live = harvest.get("live")
        count = harvest.get("save_count")
        install = harvest.get("install")
    else:
        count = getattr(harvest, "save_count", None)
        install = getattr(harvest, "install", None)
    state = "live" if live else "dark"
    where = str(install).strip() if install else "missing"
    return f"harvest: {state} · {where} · saves {count or 0}"


def _war_fields(war_room: dict[str, str | None] | None) -> dict[str, str | None]:
    row = war_room or {}
    return {
        "place": (row.get("place") or "").strip() or None,
        "patch": (row.get("patch") or "").strip() or None,
        "trap": (row.get("trap") or "").strip() or None,
        "decision": (row.get("decision") or "").strip() or None,
    }


def _reject_grok(text: str) -> bool:
    low = text.lower()
    if "jessica" in low or "http://" in low or "https://" in low:
        return True
    return "wiki" in low


def _with_dark(body: str, line: str = _GROK_DARK) -> str:
    if body == _EMPTY:
        return body
    if line in body:
        return body
    return f"{body}\n{line}"


def _field_page(
    game: str | None,
    tier: str | None,
    harvest: Any,
    fields: dict[str, str | None],
) -> str:
    level = normalize_tier(tier) or DEFAULT_TIER
    return (
        f"Game: {(game or '').strip() or 'unknown'}\n"
        f"Tier: {level}\n"
        f"{_harvest_line(harvest)}\n"
        f"place: {fields['place'] or '—'}\n"
        f"patch: {fields['patch'] or '—'}\n"
        f"trap: {fields['trap'] or '—'}\n"
        f"decision: {fields['decision'] or '—'}"
    )


def _coach_local(
    body: str,
    page: str,
    local_fn: Callable[..., str | None] | None,
) -> str:
    talker = local_fn
    if talker is None:
        from battlebuddy.databank.reason import local_answer as talker
    try:
        raw = talker("One next move from the fields only.", page)
    except TypeError:
        try:
            raw = talker(page)
        except Exception:
            return _with_dark(body, _LOCAL_DARK)
    except Exception:
        return _with_dark(body, _LOCAL_DARK)
    text = _clip_words((raw or "").strip(), _GROK_WORDS)
    if not text or _reject_grok(text):
        return _with_dark(body, _LOCAL_DARK)
    return text


def coach(
    game: str | None,
    tier: str | None,
    harvest: Any = None,
    war_room: dict[str, str | None] | None = None,
    *,
    brain: str | None = None,
    chat_fn: Callable[..., str | None] | None = None,
    local_fn: Callable[..., str | None] | None = None,
) -> str:
    """Template first. brain=local uses sidecar stub. Grok only when chosen."""
    from battlebuddy.session.tier import BRAIN_DARK, BRAIN_LOCAL, load_brain, normalize_brain

    fields = _war_fields(war_room)
    body = format_coach(tier=tier, **fields)
    chosen = normalize_brain(brain) if brain else load_brain()
    if chosen == BRAIN_LOCAL:
        if body == _EMPTY:
            return body
        return _coach_local(body, _field_page(game, tier, harvest, fields), local_fn)
    key = _api_key()
    if not key or chosen == BRAIN_DARK:
        return _with_dark(body)
    if body == _EMPTY:
        return body
    talker = chat_fn
    if talker is None:
        from battlebuddy.xai.loop import chat as talker
    messages = [
        {"role": "system", "content": _COACH_SYSTEM},
        {"role": "user", "content": _field_page(game, tier, harvest, fields)},
    ]
    try:
        raw = talker(
            messages,
            key=key,
            timeout=_COACH_TIMEOUT,
            max_tokens=_COACH_MAX_TOKENS,
        )
    except TypeError:
        try:
            raw = talker(messages, key=key)
        except Exception:
            return _with_dark(body)
    except Exception:
        return _with_dark(body)
    text = _clip_words((raw or "").strip(), _GROK_WORDS)
    if not text or _reject_grok(text):
        return _with_dark(body)
    return text

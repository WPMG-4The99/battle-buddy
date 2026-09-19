"""One move from standing War Room fields. No wiki. No model. No account."""

from __future__ import annotations

from battlebuddy.session.tier import DEFAULT_TIER, TIER_HANDHOLD, TIER_SOCRATIC, normalize_tier

_EMPTY = "Hold a place first."
_BRICK = "Next brick: HOLD after you do it."
_SAY = "Say if this is wrong."
_MOVE_WORDS = 12
_WHY_WORDS = 16


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

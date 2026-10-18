"""Save the grab, store the snap fact, answer, append the session log."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from battlebuddy.memory.store import default_home
from battlebuddy.snap.answer import DEFAULT_QUESTION, answer_snap
from battlebuddy.snap.config import send_snap_image
from battlebuddy.snap.context import pack_context
from battlebuddy.snap.facts import SnapFact, add_snap_fact
from battlebuddy.snap.shots import prune_snaps, save_snap


@dataclass(frozen=True)
class SnapResult:
    text: str
    answer: str
    fact: SnapFact
    image_path: Path
    game: str | None
    question: str


def log_path(home: Path | None = None) -> Path:
    base = home if home is not None else default_home()
    return base / "snap-log.jsonl"


def append_log(
    result: SnapResult,
    home: Path | None = None,
    *,
    now: datetime | None = None,
) -> None:
    path = log_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "at": (now if now is not None else datetime.now(timezone.utc)).isoformat(),
        "game": result.game,
        "question": result.question,
        "answer": result.answer,
        "fact_id": result.fact.id,
        "source": result.fact.source,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def finish_snap(
    image: object,
    ocr_text: str,
    game: str | None,
    question: str,
    *,
    notes: list[str] | None = None,
    pages: list[str] | None = None,
    home: Path | None = None,
    brain: str | None = None,
    chat_fn: object = None,
    local_fn: object = None,
    key: str | None = None,
    answer: str | None = None,
) -> SnapResult:
    """Persist the frame and the sourced fact, then answer from that pack."""
    path = save_snap(image, home)
    prune_snaps(home)
    fact = add_snap_fact(ocr_text, game, home)
    asked = (question or "").strip() or DEFAULT_QUESTION
    pack = pack_context(ocr_text, list(notes or []), list(pages or []))
    image_png = path.read_bytes() if send_snap_image(home) else None
    ready = (answer or "").strip()
    if ready:
        spoken = ready
    else:
        spoken = answer_snap(
            asked,
            pack,
            brain=brain,
            chat_fn=chat_fn,  # type: ignore[arg-type]
            local_fn=local_fn,  # type: ignore[arg-type]
            image_png=image_png,
            send_image=send_snap_image(home),
            key=key,
        )
    result = SnapResult(
        text=fact.text,
        answer=spoken,
        fact=fact,
        image_path=path,
        game=game,
        question=asked,
    )
    append_log(result, home)
    return result

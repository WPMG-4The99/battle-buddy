"""Answer a snap from the pack. Grok is opt-in. The image stays home unless asked."""

from __future__ import annotations

import base64
from collections.abc import Callable

from battlebuddy.session.tier import BRAIN_GROK, BRAIN_LOCAL, load_brain
from battlebuddy.snap.context import grounded_answer

_SYSTEM = (
    "Answer from the context only. One or two sentences. Do not invent. "
    "If the context does not say, reply exactly: Can't find that in the snap."
)
DEFAULT_QUESTION = "What does this event do?"


def grok_user_content(
    question: str,
    pack: str,
    image_png: bytes | None,
    *,
    send_image: bool,
) -> str | list[dict[str, object]]:
    """Text always. Image bytes only when Captain turned image sending on."""
    text = f"Question: {(question or '').strip()}\n\nContext:\n{pack}"
    if not send_image or not image_png:
        return text
    encoded = base64.b64encode(image_png).decode("ascii")
    return [
        {"type": "text", "text": text},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
    ]


def uses_image(content: object) -> bool:
    if not isinstance(content, list):
        return False
    for part in content:
        if isinstance(part, dict) and part.get("type") == "image_url":
            return True
    return False


def answer_snap(
    question: str,
    pack: str,
    *,
    brain: str | None = None,
    chat_fn: Callable[..., str | None] | None = None,
    local_fn: Callable[..., str | None] | None = None,
    image_png: bytes | None = None,
    send_image: bool = False,
    key: str | None = None,
) -> str:
    """Local extract first. Sidecar or Grok only when that brain is selected."""
    grounded = grounded_answer(question, pack)
    chosen = brain if brain else load_brain()
    if chosen == BRAIN_GROK and chat_fn is not None and (key or "").strip():
        content = grok_user_content(question, pack, image_png, send_image=send_image)
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": content},
        ]
        raw = _call(chat_fn, messages, key or "")
        text = (raw or "").strip()
        if text:
            return text
        return grounded
    if chosen == BRAIN_LOCAL and local_fn is not None:
        try:
            raw = local_fn(question, pack)
        except Exception:
            raw = None
        text = (raw or "").strip()
        if text and _sits_on_pack(text, pack):
            return text
    return grounded


def _call(chat_fn: Callable[..., str | None], messages: list[dict[str, object]], key: str) -> str | None:
    try:
        return chat_fn(messages, key=key)
    except TypeError:
        return chat_fn(messages)


def _sits_on_pack(answer: str, pack: str) -> bool:
    """Drop a sidecar line that names things the pack never said."""
    words = [word.lower() for word in answer.split() if len(word) > 4]
    if not words:
        return True
    blob = (pack or "").lower()
    hits = sum(1 for word in words if word.strip(".,;:!?") in blob)
    return hits * 2 >= len(words)

"""OCR text plus this game's notes and databank. No other game. No network."""

from __future__ import annotations

import re

_WORD = re.compile(r"[a-z0-9']+", re.IGNORECASE)
_STOP = {
    "what",
    "does",
    "this",
    "that",
    "with",
    "from",
    "your",
    "have",
    "about",
    "which",
    "option",
    "better",
    "event",
    "the",
    "and",
    "for",
    "you",
    "are",
}
_CAP = 6000


def pack_context(ocr: str, notes: list[str], pages: list[str]) -> str:
    """One pack the answerer is allowed to use."""
    parts: list[str] = []
    screen = (ocr or "").strip()
    if screen:
        parts.append("Screen:\n" + screen)
    held = [item.strip() for item in notes if (item or "").strip()]
    if held:
        parts.append("Notes:\n" + "\n".join(held))
    saved = [item.strip() for item in pages if (item or "").strip()]
    if saved:
        parts.append("Pages:\n" + "\n".join(saved))
    blob = "\n\n".join(parts).strip()
    if len(blob) > _CAP:
        return blob[:_CAP].rstrip()
    return blob


def grounded_answer(question: str, pack: str) -> str:
    """Sentences from the pack only. No model. No invented noun."""
    blob = (pack or "").strip()
    if not blob:
        return "No text in that snap."
    terms = [
        word.lower()
        for word in _WORD.findall(question or "")
        if word.lower() not in _STOP and len(word) > 2
    ]
    sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+|\n+", blob) if item.strip()]
    picked: list[str] = []
    for sentence in sentences:
        low = sentence.lower()
        if low.startswith(("screen:", "notes:", "pages:")):
            continue
        if terms and any(term in low for term in terms):
            picked.append(sentence)
        if len(picked) >= 2:
            break
    if not picked:
        for sentence in sentences:
            if sentence.lower().startswith(("screen:", "notes:", "pages:")):
                continue
            picked.append(sentence)
            if len(picked) >= 2:
                break
    text = " ".join(picked).strip() or blob
    words = text.split()
    if len(words) > 60:
        text = " ".join(words[:60])
    return text

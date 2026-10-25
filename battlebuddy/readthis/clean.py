"""Turn OCR lines into speech. Join wraps. Keep paragraph breaks. Drop stray marks."""

from __future__ import annotations

import re

# Letters, numbers, and the punctuation game text actually uses.
_DROP = re.compile(r"[^\w\s.,;:'\"?!()/\-&%’“”—–]+", re.UNICODE)
_SPACE = re.compile(r"\s+")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([.,;:?!])")
_HAS_WORD = re.compile(r"[^\W_]", re.UNICODE)


def should_break_paragraph(gap: float, line_height: float) -> bool:
    """A tall gap between OCR lines is a new paragraph, not a wrap."""
    height = line_height if line_height > 0 else 1.0
    return gap > height * 0.75


def join_ocr_lines(rows: list[tuple[str, float | None, float | None]]) -> str:
    """rows are (text, top, height). Close lines stay wrapped. Tall gaps split."""
    chunks: list[str] = []
    prev_bottom: float | None = None
    for text, top, height in rows:
        clean = (text or "").strip()
        if not clean:
            continue
        if (
            prev_bottom is not None
            and top is not None
            and height is not None
            and should_break_paragraph(top - prev_bottom, height)
        ):
            chunks.append("")
        chunks.append(clean)
        if top is not None and height is not None:
            prev_bottom = top + height
    return "\n".join(chunks)


def clean_ocr_text(raw: str) -> str:
    """Join broken lines. Drop symbol-only noise. Keep a blank line between paragraphs."""
    text = (raw or "").replace("\r\n", "\n").replace("\r", "\n")
    paragraphs: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        lines: list[str] = []
        for line in block.split("\n"):
            scrubbed = _scrub_line(line)
            if scrubbed:
                lines.append(scrubbed)
        if not lines:
            continue
        joined = _join_lines(lines)
        if joined:
            paragraphs.append(joined)
    return "\n\n".join(paragraphs)


def _scrub_line(line: str) -> str:
    cleaned = _DROP.sub(" ", line or "")
    cleaned = _SPACE.sub(" ", cleaned).strip()
    cleaned = _SPACE_BEFORE_PUNCT.sub(r"\1", cleaned)
    if not cleaned or _HAS_WORD.search(cleaned) is None:
        return ""
    return cleaned


def _join_lines(lines: list[str]) -> str:
    buf = ""
    for line in lines:
        if not buf:
            buf = line
            continue
        if buf.endswith("-") and len(buf) > 1 and buf[-2].isalnum():
            buf = buf[:-1] + line
        else:
            buf = f"{buf} {line}"
    buf = _SPACE.sub(" ", buf).strip()
    return _SPACE_BEFORE_PUNCT.sub(r"\1", buf)

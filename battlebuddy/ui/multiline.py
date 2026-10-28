"""Entry-shaped text box. Word wrap, Return submits, Shift+Return adds a line."""

from __future__ import annotations

import tkinter as tk


class MultiLineEntry(tk.Text):
    """``tk.Text`` that still accepts Entry indices (``0``, ``"end"``).

    ``get()``, ``insert(0, ...)``, and ``delete(0, "end")`` keep working.
    Return calls ``on_submit`` and does not insert a newline.
    Shift+Return inserts a newline.
    """

    def __init__(self, master: object = None, **kwargs: object) -> None:
        on_submit = kwargs.pop("on_submit", None)
        height = int(kwargs.pop("height", 3))  # type: ignore[arg-type]
        kwargs.setdefault("wrap", "word")
        kwargs.setdefault("height", height)
        kwargs.setdefault("width", 24)
        kwargs.setdefault("undo", True)
        super().__init__(master, **kwargs)  # type: ignore[arg-type]
        self._on_submit = on_submit
        self.bind("<Return>", self._on_return)
        self.bind("<KP_Enter>", self._on_return)
        self.bind("<Shift-Return>", self._on_newline)
        self.bind("<Shift-KP_Enter>", self._on_newline)

    def get(self, index1=None, index2=None) -> str:  # type: ignore[override]
        if index1 is None and index2 is None:
            return str(super().get("1.0", "end-1c"))
        start = _entry_index(index1 if index1 is not None else 0)
        end = "end-1c" if index2 is None else _entry_index(index2)
        return str(super().get(start, end))

    def insert(self, index, chars: str, *args) -> None:  # type: ignore[override]
        super().insert(_entry_index(index), chars, *args)

    def delete(self, first, last=None) -> None:  # type: ignore[override]
        start = _entry_index(first)
        if last is None:
            super().delete(start)
            return
        super().delete(start, _entry_index(last))

    def _on_return(self, _event: object | None = None) -> str:
        submit = self._on_submit
        if submit is not None:
            submit()
        return "break"

    def _on_newline(self, _event: object | None = None) -> str:
        super().insert("insert", "\n")
        return "break"


def _entry_index(index: object) -> str:
    """Map Entry indices (``0``, ``"end"``) onto a Text index."""
    if index == 0 or index == "0":
        return "1.0"
    if isinstance(index, int):
        return f"1.0+{index}c"
    text = str(index)
    if text == "end":
        return "end-1c"
    return text

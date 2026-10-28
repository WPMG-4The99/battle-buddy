"""Right-click Cut / Copy / Paste / Select All for Entry and Text widgets."""

from __future__ import annotations

import tkinter as tk


def attach_context_menu(widget: object, readonly: bool = False) -> object:
    """Attach a right-click menu. Read-only widgets get Copy and Select All."""
    menu = tk.Menu(widget, tearoff=0)
    if not readonly:
        menu.add_command(label="Cut", command=lambda: _cut(widget))
        menu.add_command(label="Copy", command=lambda: _copy(widget, readonly=False))
        menu.add_command(label="Paste", command=lambda: _paste(widget))
        menu.add_separator()
    else:
        menu.add_command(label="Copy", command=lambda: _copy(widget, readonly=True))
    menu.add_command(label="Select All", command=lambda: _select_all(widget, readonly=readonly))

    def _popup(event: object) -> str:
        _place_insert(widget, event)
        try:
            widget.focus_set()  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            menu.tk_popup(int(getattr(event, "x_root", 0)), int(getattr(event, "y_root", 0)))
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass
        return "break"

    widget.bind("<Button-3>", _popup)  # type: ignore[attr-defined]
    return menu


def _place_insert(widget: object, event: object) -> None:
    klass = _class_name(widget)
    try:
        if str(widget.cget("state")) == "disabled":  # type: ignore[attr-defined]
            return
    except Exception:
        return
    try:
        if klass == "Text":
            widget.mark_set("insert", f"@{int(getattr(event, 'x', 0))},{int(getattr(event, 'y', 0))}")  # type: ignore[attr-defined]
        elif klass == "Entry":
            widget.icursor(f"@{int(getattr(event, 'x', 0))}")  # type: ignore[attr-defined]
    except Exception:
        return


def _class_name(widget: object) -> str:
    try:
        return str(widget.winfo_class())  # type: ignore[attr-defined]
    except Exception:
        return ""


def _cut(widget: object) -> None:
    try:
        widget.event_generate("<<Cut>>")  # type: ignore[attr-defined]
    except Exception:
        return


def _paste(widget: object) -> None:
    try:
        widget.event_generate("<<Paste>>")  # type: ignore[attr-defined]
    except Exception:
        return


def _copy(widget: object, *, readonly: bool) -> None:
    klass = _class_name(widget)
    if klass == "Text":
        text = _text_for_copy(widget, readonly=readonly)
        if not text:
            return
        try:
            widget.clipboard_clear()  # type: ignore[attr-defined]
            widget.clipboard_append(text)  # type: ignore[attr-defined]
        except Exception:
            return
        return
    try:
        widget.event_generate("<<Copy>>")  # type: ignore[attr-defined]
    except Exception:
        return


def _text_for_copy(widget: object, *, readonly: bool) -> str:
    try:
        return str(widget.get("sel.first", "sel.last"))  # type: ignore[attr-defined]
    except Exception:
        if not readonly:
            return ""
    try:
        return str(widget.get("1.0", "end-1c"))  # type: ignore[attr-defined]
    except Exception:
        return ""


def _select_all(widget: object, *, readonly: bool) -> None:
    klass = _class_name(widget)
    if klass == "Text":
        _select_all_text(widget, readonly=readonly)
        return
    try:
        widget.focus_set()  # type: ignore[attr-defined]
        widget.selection_range(0, "end")  # type: ignore[attr-defined]
        widget.icursor("end")  # type: ignore[attr-defined]
    except Exception:
        return


def _select_all_text(widget: object, *, readonly: bool) -> None:
    """Select 1.0..end-1c. Disabled text is enabled just long enough to show ``sel``."""
    previous = None
    try:
        previous = str(widget.cget("state"))  # type: ignore[attr-defined]
    except Exception:
        previous = None
    try:
        if previous == "disabled":
            widget.config(state="normal")  # type: ignore[attr-defined]
        widget.tag_remove("sel", "1.0", "end")  # type: ignore[attr-defined]
        widget.tag_add("sel", "1.0", "end-1c")  # type: ignore[attr-defined]
        widget.mark_set("insert", "1.0")  # type: ignore[attr-defined]
        widget.see("insert")  # type: ignore[attr-defined]
    except Exception:
        return
    finally:
        if readonly or previous == "disabled":
            try:
                widget.config(state="disabled")  # type: ignore[attr-defined]
            except Exception:
                pass

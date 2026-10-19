"""Fullscreen dim over the current monitor. Drag a box. Esc cancels."""

from __future__ import annotations

from collections.abc import Callable

from battlebuddy.readthis.region import Rect, selection_rect
from battlebuddy.readthis.screen import (
    cursor_pos,
    monitor_at_cursor,
    pin_topmost,
    widget_hwnd,
    window_origin,
)

_GOLD = "#E6C35C"
_HINT = "Drag a box over the text. Esc cancels."


class RegionOverlay:
    """Semi-transparent Tk layer. Click-drag draws the read box."""

    def __init__(
        self,
        tk: object,
        root: object,
        on_select: Callable[[Rect], None],
        on_cancel: Callable[[], None],
    ) -> None:
        self._tk = tk
        self._on_select = on_select
        self._on_cancel = on_cancel
        self._closed = False
        self._x0: int | None = None
        self._y0: int | None = None
        self._box_id: int | None = None
        self.bounds = monitor_at_cursor(root)
        self.win = tk.Toplevel(root)  # type: ignore[attr-defined]
        self.win.overrideredirect(True)
        self.win.configure(bg="#000000")
        self.win.geometry(self._geometry(self.bounds))
        try:
            self.win.attributes("-topmost", True)
            self.win.attributes("-alpha", 0.4)
        except Exception:
            pass
        self.canvas = tk.Canvas(  # type: ignore[attr-defined]
            self.win,
            bg="#000000",
            highlightthickness=0,
            cursor="crosshair",
        )
        self.canvas.pack(fill="both", expand=True)
        self._hint_id = self.canvas.create_text(
            self.bounds.width // 2,
            28,
            text=_HINT,
            fill=_GOLD,
            font=("Arial", 16, "bold"),
        )
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._motion)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.win.bind("<Escape>", self._esc)
        self.canvas.bind("<Escape>", self._esc)
        self.win.update_idletasks()
        self._pin()
        try:
            self.win.grab_set_global()
        except Exception:
            try:
                self.win.grab_set()
            except Exception:
                pass
        try:
            self.win.focus_force()
        except Exception:
            pass
        self.win.after(60, self._pin)

    def hide(self) -> None:
        """Move the dim layer off the grab before the screenshot."""
        if self._closed:
            return
        try:
            self.win.attributes("-alpha", 0)
        except Exception:
            pass
        self.win.geometry("+%d+%d" % (-12000, -12000))
        try:
            self.win.withdraw()
        except Exception:
            pass
        try:
            self.win.grab_release()
        except Exception:
            pass
        try:
            self.win.update_idletasks()
        except Exception:
            pass

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.win.grab_release()
        except Exception:
            pass
        try:
            self.win.destroy()
        except Exception:
            return

    def cancel(self) -> None:
        if self._closed:
            return
        self.close()
        self._on_cancel()

    def _pin(self) -> None:
        if self._closed:
            return
        try:
            self.win.lift()
            self.win.attributes("-topmost", True)
        except Exception:
            pass
        pin_topmost(widget_hwnd(self.win), self.bounds)

    def _press(self, _event: object) -> None:
        self._x0, self._y0 = cursor_pos(self.win)

    def _motion(self, _event: object) -> None:
        if self._x0 is None or self._y0 is None:
            return
        x1, y1 = cursor_pos(self.win)
        self._draw(self._x0, self._y0, x1, y1)

    def _release(self, _event: object) -> None:
        if self._closed or self._x0 is None or self._y0 is None:
            return
        x1, y1 = cursor_pos(self.win)
        rect = selection_rect(self._x0, self._y0, x1, y1, self.bounds)
        self._x0 = None
        self._y0 = None
        if rect is None:
            return
        self._on_select(rect)

    def _esc(self, _event: object) -> str:
        self.cancel()
        return "break"

    def _draw(self, x0: int, y0: int, x1: int, y1: int) -> None:
        origin = window_origin(widget_hwnd(self.win), self.win)
        ax, ay = x0 - origin[0], y0 - origin[1]
        bx, by = x1 - origin[0], y1 - origin[1]
        if self._box_id is None:
            self._box_id = self.canvas.create_rectangle(
                ax,
                ay,
                bx,
                by,
                outline=_GOLD,
                width=3,
            )
        else:
            self.canvas.coords(self._box_id, ax, ay, bx, by)
        self.canvas.tag_raise(self._box_id)
        self.canvas.tag_raise(self._hint_id)

    @staticmethod
    def _geometry(bounds: Rect) -> str:
        return f"{bounds.width}x{bounds.height}{bounds.left:+d}{bounds.top:+d}"

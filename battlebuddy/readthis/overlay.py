"""Dim every connected monitor. Drag a box on any of them. Esc cancels all."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from battlebuddy.readthis.region import (
    Rect,
    layer_index_at,
    local_rect,
    normalize_drag,
    selection_rect,
    union_rects,
)
from battlebuddy.readthis.screen import (
    capture_mouse,
    cursor_pos,
    enable_dpi_awareness,
    make_clickable,
    overlay_layout,
    pin_topmost,
    release_mouse,
    widget_hwnd,
    window_origin,
)

_GOLD = "#E6C35C"
_HINT = "Drag a box over the text. Esc cancels."
_POINTER_SEQ = ("<ButtonPress-1>", "<B1-Motion>", "<ButtonRelease-1>", "<Escape>")


class SelectionSession:
    """Shared drag across monitors. Virtual-desktop pixels. No Tk."""

    def __init__(self, monitors: list[Rect]) -> None:
        found = list(monitors) if monitors else [Rect(0, 0, 1920, 1080)]
        self.monitors = found
        self.bounds = union_rects(found)
        self.start: tuple[int, int] | None = None

    def press(self, x: int, y: int) -> int | None:
        """Start a drag. Returns the monitor index that owns (x, y)."""
        self.start = (int(x), int(y))
        return layer_index_at(x, y, self.monitors)

    def release(self, x: int, y: int) -> Rect | None:
        if self.start is None:
            return None
        rect = selection_rect(self.start[0], self.start[1], int(x), int(y), self.bounds)
        self.start = None
        return rect


@dataclass
class _Layer:
    bounds: Rect
    win: Any
    canvas: Any
    hint_id: int
    box_id: int | None = None


class RegionOverlay:
    """Semi-transparent Tk layer on each active monitor. Click-drag draws the box."""

    def __init__(
        self,
        tk: object,
        root: object,
        on_select: Callable[[Rect], None],
        on_cancel: Callable[[], None],
        monitors: list[Rect] | None = None,
    ) -> None:
        enable_dpi_awareness()
        self._tk = tk
        self._root = root
        self._on_select = on_select
        self._on_cancel = on_cancel
        self._closed = False
        self._x0: int | None = None
        self._y0: int | None = None
        self._layers: list[_Layer] = []
        screens, desk = overlay_layout(root, monitors)
        self._session = SelectionSession(screens)
        self._session.bounds = desk
        self.bounds = desk
        try:
            for screen in screens:
                self._layers.append(self._open_layer(tk, root, screen))
            if len(screens) != 1 or screens[0] != desk:
                self._layers.append(self._open_layer(tk, root, desk))
        except Exception:
            self.close()
            raise
        if not self._layers:
            raise RuntimeError("Could not open the read overlay.")
        self.win = self._layers[-1].win
        self._bind_app()
        self._focus_input()
        self.win.after(60, self._pin)

    def hide(self) -> None:
        """Move every dim layer off the grab before the screenshot."""
        if self._closed:
            return
        self._unbind_app()
        release_mouse()
        for layer in self._layers:
            try:
                layer.win.attributes("-alpha", 0)
            except Exception:
                pass
            try:
                layer.win.geometry("+%d+%d" % (-12000, -12000))
            except Exception:
                pass
            try:
                layer.win.withdraw()
            except Exception:
                pass
            try:
                layer.win.update_idletasks()
            except Exception:
                pass

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._unbind_app()
        release_mouse()
        layers = self._layers
        self._layers = []
        for layer in layers:
            try:
                layer.win.destroy()
            except Exception:
                pass

    def cancel(self) -> None:
        if self._closed:
            return
        self.close()
        self._on_cancel()

    def _open_layer(self, tk: object, root: object, bounds: Rect) -> _Layer:
        win = tk.Toplevel(root)  # type: ignore[attr-defined]
        try:
            win.withdraw()
        except Exception:
            pass
        win.overrideredirect(True)
        win.configure(bg="#000000")
        win.geometry(self._geometry(bounds))
        try:
            win.attributes("-topmost", True)
            win.attributes("-alpha", 0.4)
        except Exception:
            pass
        canvas = tk.Canvas(  # type: ignore[attr-defined]
            win,
            bg="#000000",
            highlightthickness=0,
            cursor="crosshair",
        )
        canvas.pack(fill="both", expand=True)
        hint_id = canvas.create_text(
            max(1, bounds.width // 2),
            28,
            text=_HINT,
            fill=_GOLD,
            font=("Arial", 16, "bold"),
        )
        self._bind_layer(win, canvas)
        try:
            win.deiconify()
            win.update_idletasks()
        except Exception:
            pass
        hwnd = widget_hwnd(win)
        pin_topmost(hwnd, bounds)
        make_clickable(hwnd)
        return _Layer(bounds=bounds, win=win, canvas=canvas, hint_id=hint_id)

    def _bind_layer(self, win: object, canvas: object) -> None:
        for target in (win, canvas):
            try:
                target.bind("<ButtonPress-1>", self._press, add="+")  # type: ignore[attr-defined]
                target.bind("<B1-Motion>", self._motion, add="+")  # type: ignore[attr-defined]
                target.bind("<ButtonRelease-1>", self._release, add="+")  # type: ignore[attr-defined]
                target.bind("<Escape>", self._esc, add="+")  # type: ignore[attr-defined]
            except Exception:
                continue

    def _bind_app(self) -> None:
        win = getattr(self, "win", None)
        if win is None:
            return
        for sequence, handler in (
            ("<ButtonPress-1>", self._press),
            ("<B1-Motion>", self._motion),
            ("<ButtonRelease-1>", self._release),
            ("<Escape>", self._esc),
        ):
            try:
                win.bind_all(sequence, handler, add="+")
            except Exception:
                continue

    def _unbind_app(self) -> None:
        win = getattr(self, "win", None)
        if win is None and self._layers:
            win = self._layers[-1].win
        if win is None:
            return
        for sequence in _POINTER_SEQ:
            try:
                win.unbind_all(sequence)
            except Exception:
                pass

    def _focus_input(self) -> None:
        win = getattr(self, "win", None)
        if win is None:
            return
        try:
            win.lift()
            win.attributes("-topmost", True)
            win.focus_force()
        except Exception:
            pass
        make_clickable(widget_hwnd(win))

    def _pin(self) -> None:
        if self._closed:
            return
        for layer in self._layers:
            try:
                layer.win.lift()
                layer.win.attributes("-topmost", True)
            except Exception:
                pass
            hwnd = widget_hwnd(layer.win)
            pin_topmost(hwnd, layer.bounds)
            make_clickable(hwnd)
        self._focus_input()

    def _press(self, _event: object) -> str | None:
        if self._closed:
            return "break"
        x, y = cursor_pos(self.win)
        self._x0, self._y0 = x, y
        self._session.press(x, y)
        capture_mouse(widget_hwnd(self.win))
        return "break"

    def _motion(self, _event: object) -> str | None:
        if self._closed or self._x0 is None or self._y0 is None:
            return "break"
        x1, y1 = cursor_pos(self.win)
        self._draw(self._x0, self._y0, x1, y1)
        return "break"

    def _release(self, _event: object) -> str | None:
        if self._closed or self._x0 is None or self._y0 is None:
            return "break"
        x1, y1 = cursor_pos(self.win)
        rect = self._session.release(x1, y1)
        self._x0 = None
        self._y0 = None
        release_mouse()
        if rect is None:
            return "break"
        self._on_select(rect)
        return "break"

    def _esc(self, _event: object) -> str:
        self.cancel()
        return "break"

    def _draw(self, x0: int, y0: int, x1: int, y1: int) -> None:
        drag = normalize_drag(x0, y0, x1, y1)
        for layer in self._layers:
            self._draw_layer(layer, drag)

    def _draw_layer(self, layer: _Layer, drag: Rect) -> None:
        mapped = local_rect(drag, layer.bounds)
        origin = window_origin(widget_hwnd(layer.win), layer.win)
        shift_x = origin[0] - layer.bounds.left
        shift_y = origin[1] - layer.bounds.top
        if mapped is None:
            if layer.box_id is not None:
                layer.canvas.coords(layer.box_id, 0, 0, 0, 0)
            return
        ax, ay, bx, by = mapped
        ax -= shift_x
        ay -= shift_y
        bx -= shift_x
        by -= shift_y
        if layer.box_id is None:
            layer.box_id = layer.canvas.create_rectangle(
                ax,
                ay,
                bx,
                by,
                outline=_GOLD,
                width=3,
            )
        else:
            layer.canvas.coords(layer.box_id, ax, ay, bx, by)
        layer.canvas.tag_raise(layer.box_id)
        layer.canvas.tag_raise(layer.hint_id)

    @staticmethod
    def _geometry(bounds: Rect) -> str:
        return f"{bounds.width}x{bounds.height}{bounds.left:+d}{bounds.top:+d}"

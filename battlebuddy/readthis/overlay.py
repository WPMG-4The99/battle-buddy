"""Dim every connected monitor. Drag a box on any of them. Esc cancels all."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from battlebuddy.readthis.region import (
    Rect,
    contains_point,
    local_rect,
    normalize_drag,
    selection_rect,
)
from battlebuddy.readthis.screen import (
    cursor_pos,
    enable_dpi_awareness,
    overlay_layout,
    pin_topmost,
    widget_hwnd,
    window_origin,
)

_GOLD = "#E6C35C"
_HINT = "Drag a box over the text. Esc cancels."


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
        self._on_select = on_select
        self._on_cancel = on_cancel
        self._closed = False
        self._x0: int | None = None
        self._y0: int | None = None
        self._layers: list[_Layer] = []
        screens, desk = overlay_layout(root, monitors)
        self.bounds = desk
        try:
            for screen in screens:
                self._layers.append(self._open_layer(tk, root, screen))
        except Exception:
            self.close()
            raise
        if not self._layers:
            raise RuntimeError("Could not open the read overlay.")
        focus = self._layer_at(*cursor_pos(root)) or self._layers[0]
        self.win = focus.win
        self._arm(focus)
        self.win.after(60, self._pin)

    def hide(self) -> None:
        """Move every dim layer off the grab before the screenshot."""
        if self._closed:
            return
        self._unbind_pointer()
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
                layer.win.grab_release()
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
        self._unbind_pointer()
        layers = self._layers
        self._layers = []
        for layer in layers:
            try:
                layer.win.grab_release()
            except Exception:
                pass
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
            bounds.width // 2,
            28,
            text=_HINT,
            fill=_GOLD,
            font=("Arial", 16, "bold"),
        )
        canvas.bind("<ButtonPress-1>", self._press)
        canvas.bind("<B1-Motion>", self._motion)
        canvas.bind("<ButtonRelease-1>", self._release)
        win.bind("<Escape>", self._esc)
        canvas.bind("<Escape>", self._esc)
        try:
            win.update_idletasks()
        except Exception:
            pass
        pin_topmost(widget_hwnd(win), bounds)
        return _Layer(bounds=bounds, win=win, canvas=canvas, hint_id=hint_id)

    def _arm(self, focus: _Layer) -> None:
        try:
            focus.win.grab_set_global()
        except Exception:
            try:
                focus.win.grab_set()
            except Exception:
                pass
        try:
            focus.win.focus_force()
        except Exception:
            pass

    def _layer_at(self, x: int, y: int) -> _Layer | None:
        for layer in self._layers:
            if contains_point(layer.bounds, x, y):
                return layer
        return None

    def _pin(self) -> None:
        if self._closed:
            return
        for layer in self._layers:
            try:
                layer.win.lift()
                layer.win.attributes("-topmost", True)
            except Exception:
                pass
            pin_topmost(widget_hwnd(layer.win), layer.bounds)

    def _press(self, _event: object) -> None:
        self._x0, self._y0 = cursor_pos(self.win)
        try:
            self.win.bind_all("<B1-Motion>", self._motion)
            self.win.bind_all("<ButtonRelease-1>", self._release)
        except Exception:
            pass

    def _unbind_pointer(self) -> None:
        win = getattr(self, "win", None)
        if win is None and self._layers:
            win = self._layers[0].win
        if win is None:
            return
        for sequence in ("<B1-Motion>", "<ButtonRelease-1>"):
            try:
                win.unbind_all(sequence)
            except Exception:
                pass

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
        self._unbind_pointer()
        if rect is None:
            return
        self._on_select(rect)

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

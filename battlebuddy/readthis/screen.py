"""Monitor, cursor, and topmost pin. Win32 when present. Tk numbers otherwise."""

from __future__ import annotations

import sys
from typing import Any

from battlebuddy.readthis.region import Rect

_user32: Any = None
if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32


def enable_dpi_awareness() -> None:
    """Call once, before the first Tk window, so drag pixels match the grab."""
    if sys.platform != "win32":
        return
    import ctypes

    try:
        aware = ctypes.windll.user32.SetProcessDpiAwarenessContext
        aware.argtypes = [ctypes.c_void_p]
        aware.restype = ctypes.c_bool
        if aware(ctypes.c_void_p(-4)):
            return
    except (OSError, AttributeError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (OSError, AttributeError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (OSError, AttributeError):
            return


def cursor_pos(root: object | None = None) -> tuple[int, int]:
    if sys.platform == "win32":
        try:
            found = _win_cursor()
        except Exception:
            found = None
        if found is not None:
            return found
    if root is not None:
        try:
            return int(root.winfo_pointerx()), int(root.winfo_pointery())  # type: ignore[attr-defined]
        except Exception:
            return (0, 0)
    return (0, 0)


def monitor_at_cursor(root: object | None = None) -> Rect:
    """Monitor under the pointer. One overlay, the screen the player is on."""
    if sys.platform == "win32":
        try:
            found = _win_monitor()
        except Exception:
            found = None
        if found is not None:
            return found
    if root is not None:
        try:
            return Rect(0, 0, int(root.winfo_screenwidth()), int(root.winfo_screenheight()))  # type: ignore[attr-defined]
        except Exception:
            return Rect(0, 0, 1920, 1080)
    return Rect(0, 0, 1920, 1080)


def window_origin(hwnd: int, widget: object) -> tuple[int, int]:
    if sys.platform == "win32" and hwnd:
        try:
            found = _window_rect(hwnd)
        except Exception:
            found = None
        if found is not None:
            return found[0], found[1]
    try:
        return int(widget.winfo_rootx()), int(widget.winfo_rooty())  # type: ignore[attr-defined]
    except Exception:
        return (0, 0)


def pin_topmost(hwnd: int, bounds: Rect) -> None:
    """Keep a borderless overlay above a borderless game window."""
    if sys.platform != "win32" or not hwnd or _user32 is None:
        return
    try:
        _pin_topmost(hwnd, bounds)
    except Exception:
        return


def _pin_topmost(hwnd: int, bounds: Rect) -> None:
    import ctypes
    from ctypes import wintypes

    user32 = _user32
    root = _root_hwnd(hwnd)
    _force_topmost_style(root)
    user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.SetWindowPos(
        root,
        wintypes.HWND(-1),
        int(bounds.left),
        int(bounds.top),
        int(bounds.width),
        int(bounds.height),
        0x0040,
    )


def widget_hwnd(widget: object) -> int:
    try:
        return int(widget.winfo_id())  # type: ignore[attr-defined]
    except Exception:
        return 0


def _win_cursor() -> tuple[int, int] | None:
    import ctypes
    from ctypes import wintypes

    class POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

    user32 = _user32
    point = POINT()
    user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
    user32.GetCursorPos.restype = wintypes.BOOL
    if not user32.GetCursorPos(ctypes.byref(point)):
        return None
    return int(point.x), int(point.y)


def _win_monitor() -> Rect | None:
    import ctypes
    from ctypes import wintypes

    class POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", RECT),
            ("rcWork", RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    cursor = _win_cursor()
    if cursor is None:
        return None
    user32 = _user32
    user32.MonitorFromPoint.argtypes = [POINT, wintypes.DWORD]
    user32.MonitorFromPoint.restype = wintypes.HMONITOR
    monitor = user32.MonitorFromPoint(POINT(cursor[0], cursor[1]), 2)
    if not monitor:
        return None
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return None
    box = info.rcMonitor
    width = int(box.right - box.left)
    height = int(box.bottom - box.top)
    if width <= 0 or height <= 0:
        return None
    return Rect(int(box.left), int(box.top), width, height)


def _window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    import ctypes
    from ctypes import wintypes

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    user32 = _user32
    rect = RECT()
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    target = _root_hwnd(hwnd)
    if not user32.GetWindowRect(target, ctypes.byref(rect)):
        return None
    return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)


def _root_hwnd(hwnd: int) -> int:
    import ctypes
    from ctypes import wintypes

    user32 = _user32
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    root = user32.GetAncestor(hwnd, 2)
    return int(root or hwnd)


def _force_topmost_style(hwnd: int) -> None:
    import ctypes

    user32 = _user32
    GWL_EXSTYLE = -20
    WS_EX_TOPMOST = 0x00000008
    WS_EX_TOOLWINDOW = 0x00000080
    try:
        get_long = user32.GetWindowLongPtrW
        set_long = user32.SetWindowLongPtrW
    except AttributeError:
        get_long = user32.GetWindowLongW
        set_long = user32.SetWindowLongW
    get_long.argtypes = [ctypes.c_void_p, ctypes.c_int]
    get_long.restype = ctypes.c_ssize_t
    set_long.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    set_long.restype = ctypes.c_ssize_t
    style = int(get_long(hwnd, GWL_EXSTYLE))
    set_long(hwnd, GWL_EXSTYLE, style | WS_EX_TOPMOST | WS_EX_TOOLWINDOW)

"""Monitor list and topmost click-through. Win32 when present. Does not dim the desktop."""

from __future__ import annotations

import sys

from battlebuddy.ui.overlay_model import Monitor, exstyle_bits

_PRIMARY = 1


def enable_dpi_awareness() -> None:
    """Call once, before the first Tk window, so a side monitor keeps its pixels."""
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


def list_monitors(root: object | None = None) -> list[Monitor]:
    found = _platform_monitors()
    if found:
        return _with_primary(found)
    if root is not None:
        try:
            width = int(root.winfo_screenwidth())  # type: ignore[attr-defined]
            height = int(root.winfo_screenheight())  # type: ignore[attr-defined]
            if width > 0 and height > 0:
                return [Monitor("primary", 0, 0, width, height, True)]
        except Exception:
            pass
    return [Monitor("primary", 0, 0, 1920, 1080, True)]


def window_hwnd(widget: object) -> int:
    try:
        hwnd = int(widget.winfo_id())  # type: ignore[attr-defined]
    except Exception:
        return 0
    if sys.platform != "win32" or not hwnd:
        return hwnd
    try:
        return _root_hwnd(hwnd)
    except Exception:
        return hwnd


def apply_window_chrome(hwnd: int, *, click_through: bool, disown: bool) -> None:
    """Topmost tool window. Does not move or resize. Disown so minimize stays on the main window."""
    if sys.platform != "win32" or not hwnd:
        return
    try:
        _apply(hwnd, click_through=click_through, disown=disown)
    except Exception:
        return


def _with_primary(found: list[Monitor]) -> list[Monitor]:
    if any(item.primary for item in found):
        return found
    first = found[0]
    found[0] = Monitor(first.key, first.left, first.top, first.width, first.height, True)
    return found


def _platform_monitors() -> list[Monitor]:
    if sys.platform != "win32":
        return []
    try:
        return _win_monitors()
    except Exception:
        return []


def _win_monitors() -> list[Monitor]:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)

    class _MONITORINFOEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
            ("szDevice", wintypes.WCHAR * 32),
        ]

    monitors: list[Monitor] = []
    seen: set[str] = set()

    def _enum(hmonitor: int, _hdc: int, _lprect: object, _data: int) -> int:
        info = _MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(_MONITORINFOEXW)
        if not user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            return 1
        box = info.rcMonitor
        width = int(box.right - box.left)
        height = int(box.bottom - box.top)
        if width <= 0 or height <= 0:
            return 1
        device = str(info.szDevice or "").strip().strip("\x00")
        key = device or f"{int(box.left)},{int(box.top)},{width}x{height}"
        if key in seen:
            key = f"{key}@{int(box.left)},{int(box.top)}"
        seen.add(key)
        monitors.append(
            Monitor(
                key,
                int(box.left),
                int(box.top),
                width,
                height,
                bool(int(info.dwFlags) & _PRIMARY),
            )
        )
        return 1

    enum_proc = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(wintypes.RECT),
        wintypes.LPARAM,
    )
    callback = enum_proc(_enum)
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.c_void_p]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.EnumDisplayMonitors.argtypes = [
        wintypes.HDC,
        ctypes.c_void_p,
        enum_proc,
        wintypes.LPARAM,
    ]
    user32.EnumDisplayMonitors.restype = wintypes.BOOL
    if not user32.EnumDisplayMonitors(None, None, callback, 0):
        return []
    return monitors


def _root_hwnd(hwnd: int) -> int:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    root = user32.GetAncestor(hwnd, 2)
    return int(root or hwnd)


def _long_pair(user32: object) -> tuple[object, object]:
    import ctypes

    try:
        get_long = user32.GetWindowLongPtrW  # type: ignore[attr-defined]
        set_long = user32.SetWindowLongPtrW  # type: ignore[attr-defined]
    except AttributeError:
        get_long = user32.GetWindowLongW  # type: ignore[attr-defined]
        set_long = user32.SetWindowLongW  # type: ignore[attr-defined]
    get_long.argtypes = [ctypes.c_void_p, ctypes.c_int]
    get_long.restype = ctypes.c_ssize_t
    set_long.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    set_long.restype = ctypes.c_ssize_t
    return get_long, set_long


def _apply(hwnd: int, *, click_through: bool, disown: bool) -> None:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    get_long, set_long = _long_pair(user32)
    style = int(get_long(hwnd, -20))
    set_long(hwnd, -20, exstyle_bits(style, click_through=click_through))
    if disown:
        set_long(hwnd, -8, 0)
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
    # NOSIZE | NOMOVE | NOACTIVATE | FRAMECHANGED. Z-order only.
    user32.SetWindowPos(hwnd, wintypes.HWND(-1), 0, 0, 0, 0, 0x0013 | 0x0020)

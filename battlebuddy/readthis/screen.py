"""Monitor, cursor, and topmost pin. Win32 when present. Tk numbers otherwise."""

from __future__ import annotations

import sys
from typing import Any

from battlebuddy.readthis.region import Rect, contains_point, union_rects

# DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2. Drag pixels match the grab.
PER_MONITOR_AWARE_V2 = -4
_SM_XVIRTUALSCREEN = 76
_SM_YVIRTUALSCREEN = 77
_SM_CXVIRTUALSCREEN = 78
_SM_CYVIRTUALSCREEN = 79

_user32: Any = None
_POINT: Any = None
_RECT: Any = None
_MONITORINFO: Any = None
if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32
    _POINT = wintypes.POINT
    _RECT = wintypes.RECT

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]


def enable_dpi_awareness() -> None:
    """Call once, before the first Tk window, so drag pixels match the grab."""
    if sys.platform != "win32":
        return
    import ctypes

    try:
        aware = ctypes.windll.user32.SetProcessDpiAwarenessContext
        aware.argtypes = [ctypes.c_void_p]
        aware.restype = ctypes.c_bool
        if aware(ctypes.c_void_p(PER_MONITOR_AWARE_V2)):
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
    """Monitor under the pointer. SNAP grabs this screen, not the whole desk."""
    if sys.platform == "win32":
        try:
            found = _win_monitor()
        except Exception:
            found = None
        if found is not None:
            return found
    x, y = cursor_pos(root)
    found = list_monitors(root)
    for monitor in found:
        if contains_point(monitor, x, y):
            return monitor
    return found[0] if found else _tk_screen(root)


def list_monitors(root: object | None = None) -> list[Rect]:
    """Every active display in virtual-desktop pixels. Left/above primary can be negative."""
    found = _platform_monitors()
    if found:
        return found
    desk = _platform_virtual_desktop()
    if desk is not None:
        return [desk]
    return [_tk_screen(root)]


def virtual_desktop(root: object | None = None) -> Rect:
    """Full Windows virtual screen, including negative origins."""
    desk = _platform_virtual_desktop()
    if desk is not None:
        return desk
    return union_rects(list_monitors(root))


def overlay_layout(
    root: object | None = None,
    monitors: list[Rect] | None = None,
) -> tuple[list[Rect], Rect]:
    """One overlay rect per monitor, plus the virtual-desktop clamp box."""
    given = monitors is not None
    found = list(monitors) if given else list_monitors(root)
    if not found:
        found = [monitor_at_cursor(root)]
    if given:
        return found, union_rects(found)
    return found, virtual_desktop(root)


def _tk_screen(root: object | None = None) -> Rect:
    if root is not None:
        try:
            return Rect(0, 0, int(root.winfo_screenwidth()), int(root.winfo_screenheight()))  # type: ignore[attr-defined]
        except Exception:
            return Rect(0, 0, 1920, 1080)
    return Rect(0, 0, 1920, 1080)


def _platform_monitors() -> list[Rect]:
    if sys.platform != "win32":
        return []
    try:
        found = _win_monitors()
    except Exception:
        found = None
    return found or []


def _platform_virtual_desktop() -> Rect | None:
    if sys.platform != "win32":
        return None
    try:
        return _win_virtual_desktop()
    except Exception:
        return None


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


def make_clickable(hwnd: int) -> None:
    """Clear click-through styles so an alpha overlay still takes the mouse."""
    if sys.platform != "win32" or not hwnd or _user32 is None:
        return
    try:
        _make_clickable(hwnd)
    except Exception:
        return


def capture_mouse(hwnd: int) -> None:
    """Win32 SetCapture so a drag keeps moving after it leaves one overlay."""
    if sys.platform != "win32" or not hwnd or _user32 is None:
        return
    try:
        import ctypes

        root = _root_hwnd(hwnd)
        _user32.SetCapture.argtypes = [ctypes.c_void_p]
        _user32.SetCapture.restype = ctypes.c_void_p
        _user32.SetCapture(root)
    except Exception:
        return


def release_mouse() -> None:
    if sys.platform != "win32" or _user32 is None:
        return
    try:
        _user32.ReleaseCapture.argtypes = []
        _user32.ReleaseCapture.restype = ctypes.c_bool
        _user32.ReleaseCapture()
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

    user32 = _user32
    point = _POINT()
    user32.GetCursorPos.argtypes = [ctypes.POINTER(_POINT)]
    user32.GetCursorPos.restype = wintypes.BOOL
    if not user32.GetCursorPos(ctypes.byref(point)):
        return None
    return int(point.x), int(point.y)


def _win_monitor() -> Rect | None:
    import ctypes
    from ctypes import wintypes

    cursor = _win_cursor()
    if cursor is None:
        return None
    user32 = _user32
    user32.MonitorFromPoint.argtypes = [_POINT, wintypes.DWORD]
    user32.MonitorFromPoint.restype = wintypes.HMONITOR
    monitor = user32.MonitorFromPoint(_POINT(cursor[0], cursor[1]), 2)
    if not monitor:
        return None
    info = _MONITORINFO()
    info.cbSize = ctypes.sizeof(_MONITORINFO)
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MONITORINFO)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return None
    box = info.rcMonitor
    width = int(box.right - box.left)
    height = int(box.bottom - box.top)
    if width <= 0 or height <= 0:
        return None
    return Rect(int(box.left), int(box.top), width, height)


def _win_virtual_desktop() -> Rect | None:
    import ctypes

    user32 = _user32
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int
    left = int(user32.GetSystemMetrics(_SM_XVIRTUALSCREEN))
    top = int(user32.GetSystemMetrics(_SM_YVIRTUALSCREEN))
    width = int(user32.GetSystemMetrics(_SM_CXVIRTUALSCREEN))
    height = int(user32.GetSystemMetrics(_SM_CYVIRTUALSCREEN))
    if width <= 0 or height <= 0:
        return None
    return Rect(left, top, width, height)


def _win_monitors() -> list[Rect] | None:
    import ctypes
    from ctypes import wintypes

    user32 = _user32
    monitors: list[Rect] = []

    def _enum(hmonitor: int, _hdc: int, _lprect: object, _lparam: int) -> int:
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            box = info.rcMonitor
            width = int(box.right - box.left)
            height = int(box.bottom - box.top)
            if width > 0 and height > 0:
                monitors.append(Rect(int(box.left), int(box.top), width, height))
        return 1

    MONITORENUMPROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(_RECT),
        wintypes.LPARAM,
    )
    callback = MONITORENUMPROC(_enum)
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MONITORINFO)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.EnumDisplayMonitors.argtypes = [
        wintypes.HDC,
        ctypes.c_void_p,
        MONITORENUMPROC,
        wintypes.LPARAM,
    ]
    user32.EnumDisplayMonitors.restype = wintypes.BOOL
    if not user32.EnumDisplayMonitors(None, None, callback, 0):
        return None
    return monitors or None


def _window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    import ctypes
    from ctypes import wintypes

    user32 = _user32
    rect = _RECT()
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(_RECT)]
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


def _make_clickable(hwnd: int) -> None:
    import ctypes

    user32 = _user32
    root = _root_hwnd(hwnd)
    GWL_EXSTYLE = -20
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_NOACTIVATE = 0x08000000
    WS_EX_LAYERED = 0x00080000
    WS_EX_TOPMOST = 0x00000008
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
    style = int(get_long(root, GWL_EXSTYLE))
    style = (style | WS_EX_LAYERED | WS_EX_TOPMOST) & ~WS_EX_TRANSPARENT & ~WS_EX_NOACTIVATE
    set_long(root, GWL_EXSTYLE, style)
    user32.EnableWindow.argtypes = [ctypes.c_void_p, ctypes.c_bool]
    user32.EnableWindow.restype = ctypes.c_bool
    user32.EnableWindow(root, True)

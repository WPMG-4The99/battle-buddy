"""Notification-area icon. Left click toggles the box. Right click opens the menu."""

from __future__ import annotations

import queue
import sys
import threading
import uuid
from dataclasses import dataclass, field

WM_DESTROY = 0x0002
WM_NULL = 0x0000
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_APP = 0x8000
NIM_ADD = 0x00000000
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
MF_STRING = 0x0000
MF_GRAYED = 0x0001
MF_CHECKED = 0x0008
TPM_RETURNCMD = 0x0100
TPM_RIGHTBUTTON = 0x0002
IDI_APPLICATION = 32512
CMD_TOGGLE = 1
CMD_CLICK = 2


def _icon_data_type() -> type:
    import ctypes
    from ctypes import wintypes

    class _NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("hWnd", wintypes.HWND),
            ("uID", wintypes.UINT),
            ("uFlags", wintypes.UINT),
            ("uCallbackMessage", wintypes.UINT),
            ("hIcon", wintypes.HICON),
            ("szTip", wintypes.WCHAR * 128),
        ]

    return _NOTIFYICONDATAW


_ICON_DATA = _icon_data_type()


@dataclass
class TrayState:
    visible: bool = False
    click_through: bool = False
    click_enabled: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def snapshot(self) -> tuple[bool, bool, bool]:
        with self._lock:
            return self.visible, self.click_through, self.click_enabled

    def update(
        self,
        *,
        visible: bool,
        click_through: bool,
        click_enabled: bool,
    ) -> None:
        with self._lock:
            self.visible = visible
            self.click_through = click_through
            self.click_enabled = click_enabled


class OverlayTray:
    """Windows tray icon. Other platforms no-op. Events land on a queue, not on Tk."""

    def __init__(self, events: queue.Queue[str], state: TrayState) -> None:
        self._events = events
        self._state = state
        self.error: str | None = None
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._hwnd = 0
        self._proc: object | None = None
        self._class = f"BattleBuddyHudTray{uuid.uuid4().hex}"
        self._added = False

    def start(self) -> str | None:
        if sys.platform != "win32":
            self.error = "Tray icon needs Windows. Use the Overlay menu."
            self._ready.set()
            return self.error
        self._thread = threading.Thread(
            target=self._loop,
            name="battlebuddy-overlay-tray",
            daemon=True,
        )
        self._thread.start()
        self._ready.wait(timeout=2.0)
        return self.error

    def stop(self) -> None:
        if sys.platform != "win32" or not self._hwnd:
            return
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.PostMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.PostMessageW(self._hwnd, WM_DESTROY, 0, 0)
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _loop(self) -> None:
        try:
            self._run()
        except Exception as exc:
            self.error = str(exc) or "Tray icon failed."
        finally:
            self._ready.set()

    def _run(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        wndproc_type = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t,
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )

        def _proc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
            if msg == WM_APP:
                mouse = int(lparam) & 0xFFFF
                if mouse in {WM_LBUTTONUP, WM_LBUTTONDBLCLK}:
                    self._events.put("toggle")
                elif mouse == WM_RBUTTONUP:
                    self._popup(user32, hwnd)
                return 0
            if msg == WM_DESTROY:
                try:
                    self._remove_icon(shell32, hwnd)
                except Exception:
                    pass
                user32.PostQuitMessage(0)
                return 0
            return int(user32.DefWindowProcW(hwnd, msg, wparam, lparam))

        self._proc = wndproc_type(_proc)

        class _WNDCLASSW(ctypes.Structure):
            _fields_ = [
                ("style", wintypes.UINT),
                ("lpfnWndProc", wndproc_type),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        user32.DefWindowProcW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.DefWindowProcW.restype = ctypes.c_ssize_t
        user32.PostQuitMessage.argtypes = [ctypes.c_int]
        hinst = kernel32.GetModuleHandleW(None)
        klass = _WNDCLASSW()
        klass.lpfnWndProc = self._proc
        klass.hInstance = hinst
        klass.lpszClassName = self._class
        user32.RegisterClassW.argtypes = [ctypes.POINTER(_WNDCLASSW)]
        user32.RegisterClassW.restype = wintypes.ATOM
        if not user32.RegisterClassW(ctypes.byref(klass)):
            self.error = "Could not register the tray window."
            self._ready.set()
            return
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.HMENU,
            wintypes.HINSTANCE,
            ctypes.c_void_p,
        ]
        user32.CreateWindowExW.restype = wintypes.HWND
        hwnd = user32.CreateWindowExW(
            0,
            self._class,
            "Battle Buddy overlay",
            0,
            0,
            0,
            0,
            0,
            wintypes.HWND(-3),
            None,
            hinst,
            None,
        )
        self._hwnd = int(hwnd or 0)
        if not self._hwnd:
            self.error = "Could not open the tray window."
            self._ready.set()
            return
        user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
        user32.LoadIconW.restype = wintypes.HICON
        icon = user32.LoadIconW(None, wintypes.LPCWSTR(IDI_APPLICATION))
        data = _ICON_DATA()
        data.cbSize = ctypes.sizeof(_ICON_DATA)
        data.hWnd = self._hwnd
        data.uID = 1
        data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        data.uCallbackMessage = WM_APP
        data.hIcon = icon
        data.szTip = "Battle Buddy overlay"
        shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(_ICON_DATA)]
        shell32.Shell_NotifyIconW.restype = wintypes.BOOL
        if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(data)):
            self.error = "Could not add the tray icon."
            self._ready.set()
            return
        self._added = True
        self._ready.set()
        user32.GetMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
        ]
        user32.GetMessageW.restype = ctypes.c_int
        user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        msg = wintypes.MSG()
        while True:
            result = int(user32.GetMessageW(ctypes.byref(msg), None, 0, 0))
            if result in {0, -1}:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        self._remove_icon(shell32, self._hwnd)
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.DestroyWindow(self._hwnd)
        user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
        user32.UnregisterClassW(self._class, hinst)
        self._hwnd = 0

    def _remove_icon(self, shell32: object, hwnd: int) -> None:
        if not self._added or not hwnd:
            return
        import ctypes

        data = _ICON_DATA()
        data.cbSize = ctypes.sizeof(_ICON_DATA)
        data.hWnd = hwnd
        data.uID = 1
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(data))  # type: ignore[attr-defined]
        self._added = False

    def _popup(self, user32: object, hwnd: int) -> None:
        import ctypes
        from ctypes import wintypes

        visible, click_through, click_enabled = self._state.snapshot()
        user32.CreatePopupMenu.argtypes = []  # type: ignore[attr-defined]
        user32.CreatePopupMenu.restype = wintypes.HMENU  # type: ignore[attr-defined]
        menu = user32.CreatePopupMenu()  # type: ignore[attr-defined]
        if not menu:
            return
        user32.AppendMenuW.argtypes = [  # type: ignore[attr-defined]
            wintypes.HMENU,
            wintypes.UINT,
            wintypes.UINT_PTR,
            wintypes.LPCWSTR,
        ]
        show_flags = MF_STRING | (MF_CHECKED if visible else 0)
        click_flags = MF_STRING
        if click_through:
            click_flags |= MF_CHECKED
        if not click_enabled:
            click_flags |= MF_GRAYED
        user32.AppendMenuW(menu, show_flags, CMD_TOGGLE, "Show overlay")  # type: ignore[attr-defined]
        user32.AppendMenuW(menu, click_flags, CMD_CLICK, "Click through")  # type: ignore[attr-defined]
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]  # type: ignore[attr-defined]
        user32.GetCursorPos.restype = wintypes.BOOL  # type: ignore[attr-defined]
        point = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(point))  # type: ignore[attr-defined]
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]  # type: ignore[attr-defined]
        user32.SetForegroundWindow(hwnd)  # type: ignore[attr-defined]
        user32.TrackPopupMenu.argtypes = [  # type: ignore[attr-defined]
            wintypes.HMENU,
            wintypes.UINT,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            ctypes.c_void_p,
        ]
        user32.TrackPopupMenu.restype = wintypes.BOOL  # type: ignore[attr-defined]
        cmd = int(
            user32.TrackPopupMenu(  # type: ignore[attr-defined]
                menu,
                TPM_RETURNCMD | TPM_RIGHTBUTTON,
                int(point.x),
                int(point.y),
                0,
                hwnd,
                None,
            )
            or 0
        )
        user32.PostMessageW.argtypes = [  # type: ignore[attr-defined]
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.PostMessageW(hwnd, WM_NULL, 0, 0)  # type: ignore[attr-defined]
        user32.DestroyMenu.argtypes = [wintypes.HMENU]  # type: ignore[attr-defined]
        user32.DestroyMenu(menu)  # type: ignore[attr-defined]
        if cmd == CMD_TOGGLE:
            self._events.put("toggle")
        elif cmd == CMD_CLICK and click_enabled:
            self._events.put("click")

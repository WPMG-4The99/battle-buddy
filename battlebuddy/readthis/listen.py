"""Global hotkey and Esc-to-stop. Windows message loop. Button still works elsewhere."""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable

from battlebuddy.readthis.hotkey import MOD_NOREPEAT, VK_ESCAPE, display_hotkey, parse_hotkey

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WH_KEYBOARD_LL = 13
_HOTKEY_ID = 0xB0B1

_escape_armed = threading.Event()
_escape_handler: Callable[[], None] | None = None
_listen_user32 = None


def arm_escape(handler: Callable[[], None]) -> None:
    """While speech is up, Esc calls handler and is swallowed."""
    global _escape_handler
    _escape_handler = handler
    _escape_armed.set()


def disarm_escape() -> None:
    _escape_armed.clear()


def win_user32() -> object:
    """Own WinDLL so overlay/screen argtypes on windll.user32 cannot kill this loop."""
    global _listen_user32
    if _listen_user32 is None:
        import ctypes

        _listen_user32 = ctypes.WinDLL("user32", use_last_error=True)
    return _listen_user32


def bind_get_message(user32: object) -> None:
    """Always ctypes.wintypes.MSG. Local MSG classes collide on a shared DLL."""
    import ctypes
    from ctypes import wintypes

    user32.GetMessageW.argtypes = [  # type: ignore[attr-defined]
        ctypes.POINTER(wintypes.MSG),
        wintypes.HWND,
        wintypes.UINT,
        wintypes.UINT,
    ]
    user32.GetMessageW.restype = ctypes.c_int  # type: ignore[attr-defined]


class HotkeyListener:
    """One thread. RegisterHotKey plus a low-level hook that only eats Esc mid-speech."""

    def __init__(
        self,
        spec: str,
        on_fire: Callable[[], None],
        *,
        name: str = "battlebuddy-read-hotkey",
    ) -> None:
        self.spec = spec
        self._on_fire = on_fire
        self._name = name
        self.error: str | None = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._tid = 0
        self._hook = None
        self._callback = None
        self._user32: object | None = None

    def start(self) -> str | None:
        """Return an error string when the global key cannot be claimed."""
        if sys.platform != "win32":
            self.error = "Global hotkey needs Windows. Use the READ THIS button."
            self._ready.set()
            return self.error
        self._thread = threading.Thread(target=self._loop, name=self._name, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=2.0)
        return self.error

    def stop(self) -> None:
        self._stop.set()
        disarm_escape()
        if sys.platform != "win32" or not self._tid:
            return
        import ctypes
        from ctypes import wintypes

        user32 = self._user32 or win_user32()
        user32.PostThreadMessageW.argtypes = [  # type: ignore[attr-defined]
            wintypes.DWORD,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)  # type: ignore[attr-defined]

    def _loop(self) -> None:
        try:
            self._run()
        except Exception as exc:
            sys.stderr.write(f"battlebuddy hotkey loop: {exc}\n")
            if not self.error:
                self.error = "Hotkey loop stopped. Use the READ THIS button."
            self._ready.set()

    def _run(self) -> None:
        from ctypes import wintypes

        user32 = win_user32()
        self._user32 = user32
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        self._tid = int(kernel32.GetCurrentThreadId())
        self._install_hook(user32)
        registered = False
        try:
            try:
                mask, vk = parse_hotkey(self.spec)
            except ValueError as exc:
                self.error = str(exc)
                self._ready.set()
                self._pump(user32, hooked_only=True)
                return
            user32.RegisterHotKey.argtypes = [  # type: ignore[attr-defined]
                wintypes.HWND,
                ctypes.c_int,
                wintypes.UINT,
                wintypes.UINT,
            ]
            user32.RegisterHotKey.restype = wintypes.BOOL  # type: ignore[attr-defined]
            registered = bool(
                user32.RegisterHotKey(None, _HOTKEY_ID, mask | MOD_NOREPEAT, vk)  # type: ignore[attr-defined]
            )
            if not registered:
                shown = display_hotkey(self.spec)
                self.error = (
                    f"{shown} is already taken. Set BATTLEBUDDY_READ_HOTKEY "
                    "or read_hotkey in session.json."
                )
            self._ready.set()
            self._pump(user32, hooked_only=False)
        finally:
            if registered:
                try:
                    user32.UnregisterHotKey(None, _HOTKEY_ID)  # type: ignore[attr-defined]
                except Exception:
                    pass
            self._remove_hook(user32)

    def _pump(self, user32: object, *, hooked_only: bool) -> None:
        import ctypes
        from ctypes import wintypes

        bind_get_message(user32)
        msg = wintypes.MSG()
        while not self._stop.is_set():
            try:
                bind_get_message(user32)
                result = int(user32.GetMessageW(ctypes.byref(msg), None, 0, 0) or 0)  # type: ignore[attr-defined]
            except Exception as exc:
                sys.stderr.write(f"battlebuddy hotkey: {exc}\n")
                if self._stop.wait(0.05):
                    break
                continue
            if result == 0 or result == -1:
                break
            if (
                not hooked_only
                and int(msg.message) == WM_HOTKEY
                and int(msg.wParam) == _HOTKEY_ID
            ):
                self._emit()

    def _emit(self) -> None:
        try:
            self._on_fire()
        except Exception:
            return

    def _install_hook(self, user32: object) -> None:
        import ctypes
        from ctypes import wintypes

        class KBDLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [
                ("vkCode", wintypes.DWORD),
                ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t),
            ]

        hookproc = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )

        def _on_key(code: int, w_param: int, l_param: int) -> int:
            try:
                if code >= 0 and int(w_param) in {WM_KEYDOWN, WM_SYSKEYDOWN}:
                    info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                    if int(info.vkCode) == VK_ESCAPE and _escape_armed.is_set():
                        _escape_armed.clear()
                        handler = _escape_handler
                        if handler is not None:
                            handler()
                        return 1
            except Exception:
                pass
            return int(user32.CallNextHookEx(self._hook, code, w_param, l_param))  # type: ignore[attr-defined]

        self._callback = hookproc(_on_key)
        user32.CallNextHookEx.argtypes = [  # type: ignore[attr-defined]
            ctypes.c_void_p,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.CallNextHookEx.restype = ctypes.c_ssize_t  # type: ignore[attr-defined]
        user32.SetWindowsHookExW.argtypes = [  # type: ignore[attr-defined]
            ctypes.c_int,
            hookproc,
            wintypes.HINSTANCE,
            wintypes.DWORD,
        ]
        user32.SetWindowsHookExW.restype = ctypes.c_void_p  # type: ignore[attr-defined]
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
        module = kernel32.GetModuleHandleW(None)
        self._hook = user32.SetWindowsHookExW(  # type: ignore[attr-defined]
            WH_KEYBOARD_LL,
            self._callback,
            module,
            0,
        )

    def _remove_hook(self, user32: object) -> None:
        if not self._hook:
            return
        try:
            user32.UnhookWindowsHookEx(self._hook)  # type: ignore[attr-defined]
        except Exception:
            return
        self._hook = None

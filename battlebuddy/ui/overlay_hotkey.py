"""Global overlay toggle. Own thread. Does not take Ctrl+1, Ctrl+2, or Ctrl+3."""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable

from battlebuddy.ui.overlay_model import MOD_NOREPEAT, parse_hotkey

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
OVERLAY_HOTKEY_ID = 0xB0B4


class OverlayHotkey:
    """RegisterHotKey on a private thread. The callback must not touch Tk."""

    def __init__(self, spec: str, on_fire: Callable[[], None]) -> None:
        self.spec = spec
        self._on_fire = on_fire
        self.error: str | None = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._tid = 0
        self._user32: object | None = None
        self._registered = False

    def start(self) -> str | None:
        if sys.platform != "win32":
            self.error = "Global hotkey needs Windows. Use the Overlay menu."
            self._ready.set()
            return self.error
        self._thread = threading.Thread(
            target=self._loop,
            name="battlebuddy-overlay-hotkey",
            daemon=True,
        )
        self._thread.start()
        self._ready.wait(timeout=2.0)
        return self.error

    def stop(self) -> None:
        self._stop.set()
        if sys.platform != "win32" or not self._tid:
            return
        import ctypes
        from ctypes import wintypes

        user32 = self._user32
        if user32 is None:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.PostThreadMessageW.argtypes = [  # type: ignore[attr-defined]
            wintypes.DWORD,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)  # type: ignore[attr-defined]
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _loop(self) -> None:
        try:
            self._run()
        except Exception as exc:
            self.error = str(exc) or "Overlay hotkey failed."
        finally:
            self._ready.set()

    def _run(self) -> None:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32 = user32
        self._tid = int(kernel32.GetCurrentThreadId())
        try:
            mods, vk = parse_hotkey(self.spec)
        except ValueError as exc:
            self.error = str(exc)
            self._ready.set()
            return
        user32.RegisterHotKey.argtypes = [
            wintypes.HWND,
            ctypes.c_int,
            wintypes.UINT,
            wintypes.UINT,
        ]
        user32.RegisterHotKey.restype = wintypes.BOOL
        if not user32.RegisterHotKey(None, OVERLAY_HOTKEY_ID, mods | MOD_NOREPEAT, vk):
            err = int(ctypes.get_last_error())
            if err == 1409:
                self.error = (
                    "Overlay hotkey is already in use. "
                    "Set BATTLEBUDDY_OVERLAY_HOTKEY or overlay.hotkey in session.json."
                )
            else:
                self.error = f"Could not register the overlay hotkey ({err})."
            self._ready.set()
            return
        self._registered = True
        self._ready.set()
        user32.GetMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
        ]
        user32.GetMessageW.restype = ctypes.c_int
        msg = wintypes.MSG()
        while not self._stop.is_set():
            result = int(user32.GetMessageW(ctypes.byref(msg), None, 0, 0))
            if result in {0, -1}:
                break
            if int(msg.message) == WM_HOTKEY and int(msg.wParam) == OVERLAY_HOTKEY_ID:
                try:
                    self._on_fire()
                except Exception:
                    continue
        if self._registered:
            user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
            user32.UnregisterHotKey.restype = wintypes.BOOL
            user32.UnregisterHotKey(None, OVERLAY_HOTKEY_ID)
            self._registered = False

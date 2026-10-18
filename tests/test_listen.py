"""Hotkey pump keeps listening. Shared user32 argtypes cannot kill it."""

from __future__ import annotations

import ctypes
import unittest
from ctypes import wintypes
from pathlib import Path
from unittest.mock import patch

from battlebuddy.readthis.listen import (
    WM_HOTKEY,
    _HOTKEY_ID,
    HotkeyListener,
    bind_get_message,
)
from battlebuddy.snap import service as snap_service


class _FakeGetMessage:
    def __init__(self, fires: int = 3) -> None:
        self.argtypes = None
        self.restype = None
        self.calls = 0
        self.fires = fires
        self.errors = 0
        self.raise_on: set[int] = set()

    def __call__(self, ptr: object, *_args: object) -> int:
        expected = None
        if self.argtypes:
            expected = self.argtypes[0]
        obj = getattr(ptr, "_obj", None)
        if expected is not None and obj is not None:
            want = expected._type_
            if type(obj) is not want:
                self.errors += 1
                raise ctypes.ArgumentError(
                    "argument 1: TypeError: expected LP_%s instance instead of pointer to %s"
                    % (want.__name__, type(obj).__name__)
                )
        self.calls += 1
        if self.calls in self.raise_on:
            self.errors += 1
            raise ctypes.ArgumentError(
                "argument 1: TypeError: expected LP_MSG instance instead of pointer to MSG"
            )
        if self.calls <= self.fires:
            if obj is not None:
                obj.message = WM_HOTKEY
                obj.wParam = _HOTKEY_ID
            return 1
        return 0


class _FakeUser32:
    def __init__(self, get_message: _FakeGetMessage) -> None:
        self.GetMessageW = get_message


class _OtherMSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


class HotkeyPumpTest(unittest.TestCase):
    def test_pump_fires_the_handler_more_than_once(self) -> None:
        seen: list[int] = []
        listener = HotkeyListener("ctrl+alt+r", lambda: seen.append(1))
        fake = _FakeGetMessage(fires=3)
        listener._pump(_FakeUser32(fake), hooked_only=False)
        self.assertEqual(seen, [1, 1, 1])
        self.assertGreaterEqual(fake.calls, 4)

    def test_overlay_msg_type_on_another_dll_does_not_kill_listen(self) -> None:
        seen: list[int] = []
        listener = HotkeyListener("ctrl+alt+r", lambda: seen.append(1))
        listen_get = _FakeGetMessage(fires=2)
        overlay_get = _FakeGetMessage(fires=0)
        listen_dll = _FakeUser32(listen_get)
        overlay_dll = _FakeUser32(overlay_get)
        bind_get_message(listen_dll)
        overlay_dll.GetMessageW.argtypes = [
            ctypes.POINTER(_OtherMSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
        ]
        listener._pump(listen_dll, hooked_only=False)
        self.assertEqual(seen, [1, 1])
        self.assertEqual(listen_get.errors, 0)
        self.assertIs(_OtherMSG, overlay_dll.GetMessageW.argtypes[0]._type_)
        self.assertIs(wintypes.MSG, listen_dll.GetMessageW.argtypes[0]._type_)

    def test_rebinding_foreign_msg_on_same_dll_is_repaired(self) -> None:
        seen: list[int] = []
        listener = HotkeyListener("ctrl+alt+r", lambda: seen.append(1))
        fake = _FakeGetMessage(fires=3)

        def _fire() -> None:
            seen.append(1)
            fake.argtypes = [
                ctypes.POINTER(_OtherMSG),
                wintypes.HWND,
                wintypes.UINT,
                wintypes.UINT,
            ]

        listener._on_fire = _fire
        with patch("battlebuddy.readthis.listen.sys.stderr"):
            listener._pump(_FakeUser32(fake), hooked_only=False)
        self.assertEqual(seen, [1, 1, 1])
        self.assertIs(wintypes.MSG, fake.argtypes[0]._type_)

    def test_argumenterror_does_not_kill_the_loop(self) -> None:
        seen: list[int] = []
        listener = HotkeyListener("ctrl+alt+r", lambda: seen.append(1))
        fake = _FakeGetMessage(fires=3)
        fake.raise_on = {2}
        with patch("battlebuddy.readthis.listen.sys.stderr"), patch.object(
            listener._stop, "wait", return_value=False
        ):
            listener._pump(_FakeUser32(fake), hooked_only=False)
        self.assertEqual(seen, [1, 1])
        self.assertEqual(fake.errors, 1)


class HotkeySourceTest(unittest.TestCase):
    def test_listen_uses_isolated_dll_and_wintypes_msg(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "battlebuddy"
            / "readthis"
            / "listen.py"
        ).read_text(encoding="utf-8")
        self.assertIn("WinDLL", source)
        self.assertIn("wintypes.MSG", source)
        self.assertIn("bind_get_message", source)
        self.assertNotIn("class MSG", source)
        pump = source.split("def _pump")[1].split("def ")[0]
        self.assertIn("except Exception", pump)
        self.assertIn("continue", pump)
        snap = Path(snap_service.__file__).read_text(encoding="utf-8")
        self.assertIn("HotkeyListener", snap)
        self.assertIn("battlebuddy-snap-hotkey", snap)
        self.assertIn("SNAP_HOTKEY_ID", snap)
        app = (
            Path(__file__).resolve().parents[1] / "battlebuddy" / "ui" / "app.py"
        ).read_text(encoding="utf-8")
        self.assertIn("battlebuddy-stop-hotkey", app)
        self.assertIn("STOP_HOTKEY_ID", app)
        screen = (
            Path(__file__).resolve().parents[1]
            / "battlebuddy"
            / "readthis"
            / "screen.py"
        ).read_text(encoding="utf-8")
        self.assertIn("wintypes.POINT", screen)
        self.assertIn("wintypes.RECT", screen)
        self.assertNotIn("class POINT", screen)
        self.assertNotIn("class RECT", screen)

"""Overlay box: timers, live text, opacity, per-monitor position. No dimming."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from battlebuddy.session.tier import save_brain, save_tier
from battlebuddy.ui.overlay_model import (
    BOX_H,
    BOX_W,
    DEFAULT_HOTKEY,
    RESERVED_HOTKEYS,
    Monitor,
    active_timer_lines,
    alpha_of,
    click_through_applies,
    clamp_opacity,
    compose_body,
    default_origin,
    exstyle_bits,
    format_countdown,
    launch_monitor,
    load_overlay_prefs,
    normalize_hotkey,
    origin_for,
    output_chunks,
    parse_hotkey,
    save_overlay_prefs,
)
from battlebuddy.ui.overlay_model import OverlayPrefs


class _Reminder:
    def __init__(self, status: str, due_at: str, text: str) -> None:
        self.status = status
        self.due_at = due_at
        self.text = text


class OpacityTest(unittest.TestCase):
    def test_slider_domain_and_click_through(self) -> None:
        self.assertEqual(clamp_opacity(3), 10)
        self.assertEqual(clamp_opacity(140), 100)
        self.assertEqual(clamp_opacity("40"), 40)
        self.assertEqual(clamp_opacity("nope"), 90)
        self.assertAlmostEqual(alpha_of(10), 0.10)
        self.assertAlmostEqual(alpha_of(100), 1.0)
        self.assertFalse(click_through_applies(50, True))
        self.assertFalse(click_through_applies(90, True))
        self.assertFalse(click_through_applies(40, False))
        self.assertTrue(click_through_applies(49, True))
        self.assertTrue(click_through_applies(10, True))

    def test_exstyle_drops_transparent_when_click_through_is_off(self) -> None:
        on = exstyle_bits(0, click_through=True)
        self.assertTrue(on & 0x00000020)
        self.assertTrue(on & 0x00000008)
        off = exstyle_bits(on, click_through=False)
        self.assertFalse(off & 0x00000020)
        self.assertTrue(off & 0x00000008)
        self.assertTrue(off & 0x00080000)


class HotkeyTest(unittest.TestCase):
    def test_default_is_ctrl_4_and_read_snap_stop_stay_free(self) -> None:
        self.assertEqual(DEFAULT_HOTKEY, "ctrl+4")
        self.assertEqual(RESERVED_HOTKEYS, frozenset({"ctrl+1", "ctrl+2", "ctrl+3"}))
        self.assertIsNone(normalize_hotkey("ctrl+1"))
        self.assertIsNone(normalize_hotkey("control+2"))
        self.assertIsNone(normalize_hotkey("ctrl+3"))
        self.assertEqual(normalize_hotkey("ctrl+4"), "ctrl+4")
        self.assertEqual(normalize_hotkey("shift+ctrl+o"), "ctrl+shift+o")
        mods, vk = parse_hotkey("ctrl+4")
        self.assertEqual(vk, ord("4"))
        self.assertTrue(mods)
        with self.assertRaises(ValueError):
            parse_hotkey("ctrl+1")

    def test_env_wins_and_a_reserved_env_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            prefs = OverlayPrefs(hotkey="ctrl+shift+f8")
            save_overlay_prefs(prefs, home)
            old = os.environ.get("BATTLEBUDDY_OVERLAY_HOTKEY")
            try:
                os.environ["BATTLEBUDDY_OVERLAY_HOTKEY"] = "ctrl+1"
                self.assertEqual(load_overlay_prefs(home).hotkey, "ctrl+shift+f8")
                os.environ["BATTLEBUDDY_OVERLAY_HOTKEY"] = "alt+f9"
                self.assertEqual(load_overlay_prefs(home).hotkey, "alt+f9")
            finally:
                if old is None:
                    os.environ.pop("BATTLEBUDDY_OVERLAY_HOTKEY", None)
                else:
                    os.environ["BATTLEBUDDY_OVERLAY_HOTKEY"] = old


class PlaceTest(unittest.TestCase):
    def test_first_show_is_the_main_monitor_and_each_monitor_keeps_its_spot(self) -> None:
        primary = Monitor("DISPLAY1", 0, 0, 1920, 1080, True)
        side = Monitor("DISPLAY2", 1920, 0, 1600, 900, False)
        self.assertEqual(launch_monitor([side, primary], None).key, "DISPLAY1")
        self.assertEqual(default_origin(primary), (1920 - BOX_W - 24, 24))
        positions = {
            "DISPLAY1": (12, 40),
            "DISPLAY2": (80, 100),
        }
        self.assertEqual(origin_for(primary, positions), (12, 40))
        self.assertEqual(origin_for(side, positions), (2000, 100))
        self.assertEqual(launch_monitor([primary, side], "DISPLAY2").key, "DISPLAY2")
        self.assertEqual(launch_monitor([primary], "DISPLAY2").key, "DISPLAY1")
        negative = Monitor("LEFT", -1920, 0, 1920, 1080, False)
        self.assertEqual(origin_for(negative, {"LEFT": (30, 16)}), (-1890, 16))


class TimerAndTextTest(unittest.TestCase):
    def test_pending_timers_and_live_text(self) -> None:
        now = datetime(2026, 10, 22, 18, 0, tzinfo=timezone.utc)
        due = (now + timedelta(seconds=47)).isoformat()
        later = (now + timedelta(seconds=125)).isoformat()
        lines = active_timer_lines(
            [
                _Reminder("fired", due, "already went"),
                _Reminder("pending", later, "scout north"),
                _Reminder("pending", due, "check food stores"),
            ],
            now,
        )
        self.assertEqual(
            lines,
            ["0:47  check food stores", "2:05  scout north"],
        )
        self.assertEqual(format_countdown(47), "0:47")
        self.assertEqual(active_timer_lines([], now), ["No active timers."])
        chunks = output_chunks(
            "Holding the line.",
            "Holding the line.",
            "Mill pond. Next brick.",
            "",
        )
        self.assertEqual(chunks, ["Holding the line.", "Mill pond. Next brick."])
        body = compose_body(lines, chunks)
        self.assertIn("TIMERS", body)
        self.assertIn("0:47  check food stores", body)
        self.assertIn("OUTPUT", body)
        self.assertIn("Mill pond. Next brick.", body)


class SessionMergeTest(unittest.TestCase):
    def test_overlay_save_keeps_tier_and_brain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            save_tier("socratic", home)
            save_brain("local", home)
            prefs = OverlayPrefs(
                opacity=40,
                click_through=True,
                visible=True,
                last_monitor="DISPLAY2",
                positions={"DISPLAY1": (12, 40), "DISPLAY2": (80, 100)},
                hotkey="ctrl+4",
            )
            save_overlay_prefs(prefs, home)
            blob = json.loads((home / "session.json").read_text(encoding="utf-8"))
            self.assertEqual(blob["tier"], "socratic")
            self.assertEqual(blob["brain"], "local")
            loaded = load_overlay_prefs(home)
            self.assertEqual(loaded.opacity, 40)
            self.assertTrue(loaded.click_through)
            self.assertTrue(loaded.visible)
            self.assertEqual(loaded.last_monitor, "DISPLAY2")
            self.assertEqual(loaded.positions["DISPLAY1"], (12, 40))
            self.assertEqual(loaded.positions["DISPLAY2"], (80, 100))
            self.assertNotIn("ctrl+1", json.dumps(blob["overlay"]))


class AppWireTest(unittest.TestCase):
    def test_main_window_hooks_the_box_without_dimming(self) -> None:
        root = Path(__file__).resolve().parents[1]
        app = (root / "battlebuddy" / "ui" / "app.py").read_text(encoding="utf-8")
        hud = (root / "battlebuddy" / "ui" / "hud.py").read_text(encoding="utf-8")
        close = app.split("def _on_close")[1].split("def ")[0]
        self.assertIn("HudOverlay", app)
        self.assertIn("self._hud.start()", app)
        self.assertIn("self._hud.shutdown()", close)
        self.assertNotIn("self._overlay", app)
        self.assertLess(close.index("shutdown"), close.index("destroy"))
        self.assertIn("stop_bundled_server", close)
        self.assertIn('label="Overlay"', hud)
        self.assertIn('label="Show overlay"', hud)
        self.assertIn('label="Click through"', hud)
        self.assertNotIn("overlay_layout", hud)
        self.assertNotIn("RegionOverlay", hud)
        self.assertNotIn("readthis", hud)
        for name in ("hud.py", "overlay_model.py", "overlay_win.py", "overlay_hotkey.py", "tray.py"):
            text = (root / "battlebuddy" / "ui" / name).read_text(encoding="utf-8")
            self.assertNotIn("fullscreen", text.lower())


class WinSmokeTest(unittest.TestCase):
    def test_monitors_and_hotkey_and_tray_start_stop(self) -> None:
        if sys.platform != "win32":
            self.skipTest("windows")
        from battlebuddy.ui.overlay_hotkey import OverlayHotkey
        from battlebuddy.ui.overlay_win import list_monitors
        from battlebuddy.ui.tray import OverlayTray, TrayState
        import queue

        monitors = list_monitors()
        self.assertTrue(monitors)
        self.assertTrue(any(item.primary for item in monitors))
        for monitor in monitors:
            self.assertGreater(monitor.width, 0)
            self.assertGreater(monitor.height, 0)
        hotkey = OverlayHotkey("ctrl+4", lambda: None)
        hotkey_error = hotkey.start()
        hotkey.stop()
        self.assertTrue(hotkey_error is None or "hotkey" in hotkey_error.lower())
        events: queue.Queue[str] = queue.Queue()
        tray = OverlayTray(events, TrayState())
        tray_error = tray.start()
        tray.stop()
        self.assertTrue(tray_error is None or "tray" in tray_error.lower())


class HudLiveTest(unittest.TestCase):
    def test_box_shows_the_timer_and_click_through_follows_opacity(self) -> None:
        if sys.platform != "win32":
            self.skipTest("windows")
        try:
            import tkinter as tk
        except ImportError:
            self.skipTest("no tkinter")
        try:
            probe = tk.Tk()
            probe.destroy()
        except Exception:
            self.skipTest("no display")

        import ctypes

        from battlebuddy.ui.hud import HudOverlay
        from battlebuddy.ui.overlay_win import window_hwnd

        with tempfile.TemporaryDirectory() as tmp:
            old = os.environ.get("BATTLEBUDDY_HOME")
            os.environ["BATTLEBUDDY_HOME"] = tmp
            root = tk.Tk()
            root.withdraw()
            try:
                status = tk.Label(root, text="Holding the line.")
                now = datetime.now(timezone.utc) + timedelta(seconds=47)

                class _Engine:
                    def list_all(self) -> list[_Reminder]:
                        return [_Reminder("pending", now.isoformat(), "check food stores")]

                class _App:
                    pass

                app = _App()
                app.status = status
                app.ask_out = None
                app.war_room_out = None
                hud = HudOverlay(tk, root, _Engine(), app)
                hud.show()
                root.update()
                shown = str(hud._out.get("1.0", "end"))  # type: ignore[attr-defined]
                self.assertIn("TIMERS", shown)
                self.assertIn("check food stores", shown)
                self.assertIn("Holding the line.", shown)
                self.assertEqual(str(hud._click_btn.cget("state")), "disabled")  # type: ignore[attr-defined]
                hud._on_opacity("40")
                root.update()
                self.assertEqual(str(hud._click_btn.cget("state")), "normal")  # type: ignore[attr-defined]
                hud._click_var.set(True)
                hud._on_click()
                root.update()
                hwnd = window_hwnd(hud._win)
                user32 = ctypes.WinDLL("user32", use_last_error=True)
                user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
                user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
                style = int(user32.GetWindowLongPtrW(hwnd, -20))
                self.assertTrue(style & 0x00000020)
                hud._on_opacity("80")
                root.update()
                style = int(user32.GetWindowLongPtrW(hwnd, -20))
                self.assertFalse(style & 0x00000020)
                self.assertTrue(hud.prefs.click_through)
                hud.hide()
                hud.shutdown()
                blob = json.loads((Path(tmp) / "session.json").read_text(encoding="utf-8"))
                self.assertEqual(blob["overlay"]["opacity"], 80)
                self.assertFalse(blob["overlay"]["visible"])
                self.assertTrue(blob["overlay"]["click_through"])
            finally:
                try:
                    root.destroy()
                except Exception:
                    pass
                if old is None:
                    os.environ.pop("BATTLEBUDDY_HOME", None)
                else:
                    os.environ["BATTLEBUDDY_HOME"] = old

"""Click-through unlock, wheel isolation, context menu, one-click submit."""

from __future__ import annotations

import gc
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from battlebuddy.readthis.capture import ReadError, capture_region
from battlebuddy.readthis.hints import grab_help, ocr_help, snap_ocr_failed_help
from battlebuddy.readthis.region import Rect
from battlebuddy.ui.context_menu import attach_context_menu
from battlebuddy.ui.multiline import MultiLineEntry
from battlebuddy.ui.overlay_win import (
    HITTEST_FLUSH_FLAGS,
    SWP_FRAMECHANGED,
    SWP_NOMOVE,
    SWP_NOSIZE,
    SWP_NOZORDER,
)


class HitTestFlushTest(unittest.TestCase):
    def test_unlock_flags_flush_without_moving_or_reordering(self) -> None:
        self.assertEqual(
            HITTEST_FLUSH_FLAGS,
            SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_FRAMECHANGED,
        )
        self.assertEqual(HITTEST_FLUSH_FLAGS, 0x0027)
        self.assertTrue(HITTEST_FLUSH_FLAGS & SWP_NOZORDER)
        self.assertTrue(HITTEST_FLUSH_FLAGS & SWP_FRAMECHANGED)


class PackagedHintTest(unittest.TestCase):
    def test_source_checkout_still_names_pip(self) -> None:
        self.assertIn("pip install mss Pillow", grab_help())
        self.assertIn("pip install pytesseract", ocr_help())
        self.assertIn("requirements-readthis.txt", snap_ocr_failed_help())

    def test_frozen_build_does_not_tell_the_user_to_pip_install(self) -> None:
        with patch.object(sys, "frozen", True, create=True):
            for line in (grab_help(), ocr_help(), snap_ocr_failed_help()):
                self.assertNotIn("pip install", line)
                self.assertIn("bundled", line.lower())

    def test_capture_error_follows_the_same_split(self) -> None:
        with patch("battlebuddy.readthis.capture._capture_mss", side_effect=ImportError("mss")):
            with patch(
                "battlebuddy.readthis.capture._capture_pillow",
                side_effect=ImportError("PIL"),
            ):
                with self.assertRaises(ReadError) as caught:
                    capture_region(Rect(0, 0, 8, 8))
        self.assertIn("pip install mss Pillow", str(caught.exception))
        with patch.object(sys, "frozen", True, create=True):
            with patch("battlebuddy.readthis.capture._capture_mss", side_effect=ImportError("mss")):
                with patch(
                    "battlebuddy.readthis.capture._capture_pillow",
                    side_effect=ImportError("PIL"),
                ):
                    with self.assertRaises(ReadError) as frozen:
                        capture_region(Rect(0, 0, 8, 8))
        self.assertNotIn("pip install", str(frozen.exception))
        self.assertIn("bundled", str(frozen.exception).lower())


class MultiLineEntryTest(unittest.TestCase):
    def _tk(self):
        try:
            import tkinter as tk
        except ImportError:
            self.skipTest("no tkinter")
        try:
            probe = tk.Tk()
            probe.destroy()
        except Exception:
            self.skipTest("no display")
        return tk

    def test_entry_indices_return_and_shift_return(self) -> None:
        tk = self._tk()
        root = tk.Tk()
        root.withdraw()
        submitted: list[str] = []
        try:
            box = MultiLineEntry(root, height=3, width=20, on_submit=lambda: submitted.append(box.get()))
            box.pack()
            self.assertEqual(box.get(), "")
            box.insert(0, "one")
            box.insert("end", " two")
            self.assertEqual(box.get(), "one two")
            box.insert(4, "X")
            self.assertEqual(box.get(), "one Xtwo")
            box.delete(0, "end")
            self.assertEqual(box.get(), "")
            box.insert(0, "where is the granary")
            box.focus_force()
            root.deiconify()
            root.update()
            box.event_generate("<KeyPress-Return>", keysym="Return", state=1)
            root.update()
            self.assertIn("\n", box.get())
            self.assertEqual(submitted, [])
            box.delete(0, "end")
            box.insert(0, "where is food")
            box.event_generate("<KeyPress-Return>", keysym="Return")
            root.update()
            self.assertEqual(submitted, ["where is food"])
            self.assertEqual(box.get(), "where is food")
        finally:
            root.destroy()
            gc.collect()


class ContextMenuTest(unittest.TestCase):
    def _tk(self):
        try:
            import tkinter as tk
        except ImportError:
            self.skipTest("no tkinter")
        try:
            probe = tk.Tk()
            probe.destroy()
        except Exception:
            self.skipTest("no display")
        return tk

    def _labels(self, menu) -> list[str]:
        last = menu.index("end")
        labels = []
        for index in range(int(last) + 1):
            try:
                label = menu.entrycget(index, "label")
            except Exception:
                continue
            if label:
                labels.append(str(label))
        return labels

    def test_editable_and_readonly_menus(self) -> None:
        tk = self._tk()
        root = tk.Tk()
        root.withdraw()
        try:
            entry = tk.Entry(root)
            entry.insert(0, "draft reminder")
            entry_menu = attach_context_menu(entry, readonly=False)
            self.assertEqual(self._labels(entry_menu), ["Cut", "Copy", "Paste", "Select All"])
            entry_menu.invoke("Select All")
            self.assertEqual(entry.selection_get(), "draft reminder")

            text = tk.Text(root, height=3, width=20)
            text.insert("1.0", "hello overlay")
            text.config(state="disabled")
            text_menu = attach_context_menu(text, readonly=True)
            self.assertEqual(self._labels(text_menu), ["Copy", "Select All"])
            text_menu.invoke("Select All")
            self.assertEqual(text.get("sel.first", "sel.last"), "hello overlay")
            self.assertEqual(str(text.cget("state")), "disabled")
            text_menu.invoke("Copy")
            try:
                copied = root.clipboard_get()
            except Exception:
                copied = ""
            if copied:
                self.assertEqual(copied, "hello overlay")
        finally:
            root.destroy()
            gc.collect()


class OverlayFixLiveTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self._old_home = os.environ.get("BATTLEBUDDY_HOME")
        os.environ["BATTLEBUDDY_HOME"] = str(self.home)

    def tearDown(self) -> None:
        gc.collect()
        if self._old_home is None:
            os.environ.pop("BATTLEBUDDY_HOME", None)
        else:
            os.environ["BATTLEBUDDY_HOME"] = self._old_home

    def _tk(self):
        try:
            import tkinter as tk
        except ImportError:
            self.skipTest("no tkinter")
        try:
            probe = tk.Tk()
            probe.destroy()
        except Exception:
            self.skipTest("no display")
        return tk

    def test_reset_from_a_background_thread_clears_click_through(self) -> None:
        tk = self._tk()
        from battlebuddy.ui import app as ui_app

        app = ui_app.BattleBuddyApp(tk)
        try:
            app.root.withdraw()
            hud = app._hud
            hud.show()
            app.root.update()
            hud.set_opacity(40)
            hud.set_click_through(True)
            app.root.update()
            self.assertTrue(hud.prefs.click_through)
            self.assertTrue(hud._tray_state.snapshot()[1])
            self.assertTrue(hud._tray_state.snapshot()[2])
            labels = []
            last = hud._menu.index("end")
            for index in range(int(last) + 1):
                try:
                    labels.append(str(hud._menu.entrycget(index, "label")))
                except Exception:
                    continue
            self.assertIn("Turn off click-through / Reset overlay", labels)

            scheduled: list[object] = []
            real_after = app.root.after
            started = threading.Event()

            def spy(delay, callback=None, *args):
                if delay == 0 and callback is not None:
                    scheduled.append(callback)
                return real_after(delay, callback, *args)

            def worker() -> None:
                started.wait(timeout=2)
                hud.reset_click_through()

            thread = threading.Thread(target=worker)
            thread.start()
            app.root.after = spy  # type: ignore[method-assign]
            real_after(40, started.set)
            real_after(400, app.root.quit)
            app.root.mainloop()
            thread.join(timeout=2)
            app.root.after = real_after  # type: ignore[method-assign]
            self.assertFalse(thread.is_alive())
            self.assertTrue(scheduled)
            self.assertFalse(hud.prefs.click_through)
            visible, click, enabled = hud._tray_state.snapshot()
            self.assertTrue(visible)
            self.assertFalse(click)
            self.assertTrue(enabled)

            hud.set_opacity(80)
            app.root.update()
            self.assertFalse(hud._tray_state.snapshot()[2])
            hud.reset_click_through()
            app.root.update()
            self.assertFalse(hud.prefs.click_through)
            self.assertEqual(str(hud._menu.entrycget("Click through", "state")), "disabled")
            self.assertEqual(
                str(hud._menu.entrycget("Turn off click-through / Reset overlay", "state")),
                "normal",
            )
        finally:
            app._on_close()

    def test_overlay_wheel_does_not_scroll_the_main_page(self) -> None:
        tk = self._tk()
        from battlebuddy.ui import app as ui_app

        app = ui_app.BattleBuddyApp(tk)
        try:
            app.root.geometry("1200x800")
            app.root.deiconify()
            app.root.update()
            hud = app._hud
            app.ask_out.config(state="normal")
            app.ask_out.insert("1.0", "\n".join(f"line {i}" for i in range(80)))
            app.ask_out.config(state="disabled")
            hud.show()
            for _ in range(4):
                app.root.update()
            app.page_canvas.yview_moveto(0.35)
            app.root.update()
            page_before = float(app.page_canvas.yview()[0])
            self.assertGreater(page_before, 0.05)

            class _Event:
                delta = -120
                num = None
                x_root = 0
                y_root = 0

            event = _Event()
            event.widget = hud._out
            hud._out.yview_moveto(0.0)
            app.root.update()
            overlay_before = float(hud._out.yview()[0])
            result = app._wheel(event)
            app.root.update()
            self.assertEqual(result, "break")
            self.assertAlmostEqual(page_before, float(app.page_canvas.yview()[0]), delta=0.02)
            self.assertGreater(float(hud._out.yview()[0]), overlay_before)
            self.assertEqual(hud._on_overlay_wheel(event), "break")
        finally:
            app._on_close()

    def test_submit_clicks_once_and_context_menu_is_attached(self) -> None:
        tk = self._tk()
        from battlebuddy.ui import app as ui_app

        app = ui_app.BattleBuddyApp(tk)
        try:
            app.root.deiconify()
            app.root.update()
            routed: list[str] = []
            app._ask = lambda: routed.append("ask")  # type: ignore[method-assign]
            app.ask_entry.insert(0, "where is food")
            self.assertEqual(app.ask_entry.get(), "where is food")
            app.ask_entry.focus_force()
            app.ask_entry.event_generate("<KeyPress-Return>", keysym="Return")
            app.root.update()
            self.assertEqual(routed, ["ask"])
            self.assertEqual(app.ask_entry.get(), "where is food")

            app.ask_entry.delete(0, "end")
            app.ask_entry.insert(0, "where is the granary")
            app.query_btn.event_generate("<Button-1>", x=8, y=8)
            app.root.update()
            app.query_btn.event_generate("<ButtonRelease-1>", x=8, y=8)
            app.root.update()
            self.assertEqual(routed, ["ask", "ask"])

            app.query_btn.invoke()
            self.assertEqual(routed, ["ask", "ask", "ask"])

            for widget in (app.entry, app.ask_entry, app.hold_entry, app.ask_out, app.war_room_out):
                binding = widget.bind("<Button-3>")
                self.assertTrue(binding)
        finally:
            app._on_close()


class TrayMenuSourceTest(unittest.TestCase):
    def test_pystray_menu_is_dynamic_and_has_reset(self) -> None:
        text = (
            Path(__file__).resolve().parents[1] / "battlebuddy" / "ui" / "tray.py"
        ).read_text(encoding="utf-8")
        self.assertIn("pystray.MenuItem", text)
        self.assertIn("update_menu", text)
        self.assertIn("checked=lambda", text)
        self.assertIn("Turn off click-through / Reset overlay", text)
        self.assertIn("def _emit", text)
        hud = (
            Path(__file__).resolve().parents[1] / "battlebuddy" / "ui" / "hud.py"
        ).read_text(encoding="utf-8")
        self.assertIn("def _apply_click_through", hud)
        self.assertIn("def set_click_through", hud)
        self.assertIn("def set_opacity", hud)
        self.assertIn("root.after(0, self._drain_ui_calls)", hud)
        self.assertIn('return "break"', hud)


if __name__ == "__main__":
    unittest.main()

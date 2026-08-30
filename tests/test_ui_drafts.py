"""Text boxes start empty. Close wipes drafts. Disk stays. No account."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from battlebuddy.reminders.commands import run_line
from battlebuddy.ui import app as ui_app


class CombinedQueryRouteTest(unittest.TestCase):
    def test_http_url_is_fetch_everything_else_is_ask(self) -> None:
        self.assertTrue(ui_app.looks_like_public_url("https://wiki.example.com/Food"))
        self.assertTrue(ui_app.looks_like_public_url("http://example.com/page"))
        self.assertFalse(ui_app.looks_like_public_url("https://"))
        self.assertFalse(ui_app.looks_like_public_url("http://"))
        self.assertFalse(ui_app.looks_like_public_url("where is food"))
        self.assertFalse(ui_app.looks_like_public_url("How do I start a spear production?"))
        self.assertFalse(ui_app.looks_like_public_url("https://example.com/has space"))
        self.assertFalse(ui_app.looks_like_public_url(""))


class DraftBoxesSourceTest(unittest.TestCase):
    def test_launch_does_not_seed_entry_text(self) -> None:
        source = Path(ui_app.__file__).read_text(encoding="utf-8")
        self.assertNotIn("self.entry.insert(0, _EXAMPLE)", source)
        self.assertIn('protocol("WM_DELETE_WINDOW"', source)
        self.assertIn("def _clear_drafts", source)
        self.assertIn("def _on_close", source)
        self.assertIn('text="SUBMIT"', source)
        self.assertIn('text="Submit"', source)
        self.assertIn('"Reminder"', source)
        self.assertIn("Lock a time reminder here", source)
        self.assertIn("Paste a wiki link or ask a game question", source)
        self.assertIn("Wiki or question", source)
        self.assertIn("self.ask_entry", source)
        self.assertIn("self.url_entry = self.ask_entry", source)
        self.assertIn("looks_like_public_url", source)
        self.assertIn("self._submit_query", source)
        self.assertIn("self._tick_clocks()", source)
        self.assertIn("detect_game", source)
        self.assertIn('geometry("1200x800")', source)
        self.assertIn("minsize(1000, 640)", source)
        self.assertNotIn('geometry("760x900")', source)
        self.assertNotIn('geometry("760x1080")', source)
        self.assertNotIn("760x1080", source)
        self.assertNotIn('text="ADD / FETCH"', source)
        self.assertNotIn('"ASK YOUR QUESTION"', source)
        self.assertNotIn('self._overlay.place', source)
        self.assertIn("self._firing", source)
        self.assertIn("spawn_fire_splash", source)
        build = source.split("def _build(self)")[1].split("def _field_caption")[0]
        self.assertLess(build.find("self._build_databank("), build.find("self._build_ask("))
        self.assertIn("self._build_left(", build)
        databank = source.split("def _build_databank")[1].split("def _build_ask")[0]
        self.assertNotIn('side="bottom"', databank)
        self.assertIn('side="bottom"', build)
        self.assertIn("self.ask_entry", databank)
        self.assertNotIn("ASK YOUR QUESTION", databank)


class DraftBoxesLiveTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self._old_home = os.environ.get("BATTLEBUDDY_HOME")
        os.environ["BATTLEBUDDY_HOME"] = str(self.home)

    def tearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop("BATTLEBUDDY_HOME", None)
        else:
            os.environ["BATTLEBUDDY_HOME"] = self._old_home

    def test_entries_start_empty_close_clears_disk_untouched(self) -> None:
        try:
            import tkinter as tk
        except ImportError:
            self.skipTest("no tkinter")
        try:
            probe = tk.Tk()
            probe.destroy()
        except Exception:
            self.skipTest("no display")

        memory = self.home / "memory.json"
        memory.parent.mkdir(parents=True, exist_ok=True)
        memory.write_text('{"reminders": []}', encoding="utf-8")
        sources = self.home / "databanks" / "general" / "sources.json"
        sources.parent.mkdir(parents=True, exist_ok=True)
        sources.write_text("[]", encoding="utf-8")

        app = ui_app.BattleBuddyApp(tk)
        try:
            app.root.withdraw()
            self.assertEqual(app.entry.get(), "")
            self.assertIs(app.url_entry, app.ask_entry)
            self.assertEqual(app.ask_entry.get(), "")
            labels = _visible_label_texts(app.root)
            self.assertIn("Reminder", labels)
            self.assertIn("Lock a time reminder here", labels)
            self.assertIn("Wiki or question", labels)
            self.assertIn("Paste a wiki link or ask a game question", labels)
            self.assertIn("SUBMIT", labels)
            self.assertIn("Submit", labels)
            self.assertNotIn("ASK YOUR QUESTION", labels)
            self.assertNotIn("ADD / FETCH", labels)
            app.root.deiconify()
            app.root.update()
            titles = (
                "Reminder",
                "Wiki or question",
                "Reminders",
                "CLEAR ALL",
            )
            order = _label_root_y(app.root, titles)
            xs = _label_root_x(app.root, titles)
            self.assertEqual(set(order), set(titles))
            self.assertEqual(set(xs), set(titles))
            left_y = [name for name, _y in sorted(
                ((name, order[name]) for name in ("Reminder", "Reminders", "CLEAR ALL")),
                key=lambda item: item[1],
            )]
            self.assertEqual(left_y, ["Reminder", "Reminders", "CLEAR ALL"])
            self.assertLess(xs["Reminder"], xs["Wiki or question"])
            self.assertLess(xs["Reminders"], xs["Wiki or question"])
            self.assertLess(xs["CLEAR ALL"], xs["Wiki or question"])
            self.assertGreater(int(app.ask_out.winfo_rooty()), order["Wiki or question"])
            win_top = int(app.root.winfo_rooty())
            win_bottom = win_top + int(app.root.winfo_height())
            for name, y in order.items():
                self.assertGreaterEqual(y, win_top, name)
                self.assertLess(y, win_bottom, name)
            geo = str(app.root.geometry()).split("+", 1)[0]
            width, height = (int(part) for part in geo.split("x"))
            self.assertGreaterEqual(width, 1000)
            self.assertLessEqual(height, 800)
            app.entry.insert(0, "draft reminder")
            app.ask_entry.insert(0, "where is food")
            self.assertEqual(app.entry.get(), "draft reminder")
            self.assertEqual(app.url_entry.get(), "where is food")
            app._clear_drafts()
            self.assertEqual(app.entry.get(), "")
            self.assertEqual(app.url_entry.get(), "")
            self.assertEqual(app.ask_entry.get(), "")
            routed: list[str] = []
            app._add_fetch = lambda: routed.append("fetch")  # type: ignore[method-assign]
            app._ask = lambda: routed.append("ask")  # type: ignore[method-assign]
            app.ask_entry.insert(0, "https://wiki.example.com/Food")
            app._submit_query()
            app.ask_entry.delete(0, "end")
            app.ask_entry.insert(0, "where is food")
            app._submit_query()
            self.assertEqual(routed, ["fetch", "ask"])
        finally:
            app._on_close()

        self.assertTrue(memory.is_file())
        self.assertEqual(memory.read_text(encoding="utf-8").strip(), '{"reminders": []}')
        self.assertTrue(sources.is_file())
        self.assertEqual(sources.read_text(encoding="utf-8").strip(), "[]")

    def test_visible_fire_paints_that_card_only(self) -> None:
        try:
            import tkinter as tk
        except ImportError:
            self.skipTest("no tkinter")
        try:
            probe = tk.Tk()
            probe.destroy()
        except Exception:
            self.skipTest("no display")

        app = ui_app.BattleBuddyApp(tk)
        try:
            app.root.deiconify()
            app.root.update()
            locked = run_line(app.engine, "remind me in 1 second to check food stores")
            self.assertTrue(locked.ok)
            later = datetime.now(timezone.utc) + timedelta(seconds=2)
            fired = app.engine.fire_due(later)
            self.assertEqual(len(fired), 1)
            with patch("battlebuddy.ui.app._window_is_hidden", return_value=False), patch(
                "battlebuddy.ui.app.spawn_fire_splash"
            ) as splash, patch("battlebuddy.ui.app.speak_async"):
                app._on_fire(fired[0])
                app._refresh_list()
                app.root.update()
                splash.assert_not_called()
            labels = _visible_label_texts(app.root)
            self.assertIn("FIRE", labels)
            self.assertIn("SEEN", labels)
            self.assertIn("check food stores", labels)
            self.assertFalse(hasattr(app, "_overlay"))
            app._seen_item(fired[0])
            app.root.update()
            after = _visible_label_texts(app.root)
            self.assertNotIn("SEEN", after)
            self.assertIn("FIRED", after)
        finally:
            app._on_close()


def _label_root_y(widget: object, titles: tuple[str, ...]) -> dict[str, int]:
    return _label_root_attr(widget, titles, "winfo_rooty")


def _label_root_x(widget: object, titles: tuple[str, ...]) -> dict[str, int]:
    return _label_root_attr(widget, titles, "winfo_rootx")


def _label_root_attr(
    widget: object, titles: tuple[str, ...], attr: str
) -> dict[str, int]:
    found: dict[str, int] = {}

    def walk(node: object) -> None:
        try:
            text = str(node.cget("text"))
        except Exception:
            text = ""
        if text in titles and text not in found:
            try:
                found[text] = int(getattr(node, attr)())
            except Exception:
                pass
        try:
            children = node.winfo_children()
        except Exception:
            return
        for child in children:
            walk(child)

    walk(widget)
    return found


def _visible_label_texts(widget: object) -> list[str]:
    texts: list[str] = []
    try:
        texts.append(str(widget.cget("text")))
    except Exception:
        pass
    try:
        children = widget.winfo_children()
    except Exception:
        return texts
    for child in children:
        texts.extend(_visible_label_texts(child))
    return texts


if __name__ == "__main__":
    unittest.main()

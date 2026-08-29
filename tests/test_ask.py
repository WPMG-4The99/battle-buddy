"""Ask searches local page text only. No model. No invent."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from battlebuddy.databank.search import ask_pages, search_folder
from battlebuddy.databank.store import DatabankStore
from battlebuddy.ui import app as ui_app


class SearchFolderTest(unittest.TestCase):
    def test_empty_folder_says_add_fetch(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        result = search_folder(Path(tmp.name) / "missing", "where is food")
        self.assertTrue(result.ok)
        self.assertTrue(result.empty)
        self.assertEqual(result.hits, ())
        self.assertIn("ADD / FETCH", result.message)
        self.assertIn("ADD / FETCH", result.output())

    def test_returns_snippet_from_saved_text(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DatabankStore(Path(tmp.name))
        store.save_page(
            "Manor Lords",
            "https://example.com/wiki/food",
            "Food",
            "Check the granary before winter. Berries spoil in the rain.",
        )
        result = ask_pages(store, "Manor Lords", "where do I store food")
        self.assertTrue(result.ok)
        self.assertFalse(result.empty)
        self.assertTrue(result.hits)
        blob = result.output().lower()
        self.assertIn("food", blob)
        self.assertTrue("granary" in blob or "berries" in blob)
        self.assertNotIn("I think", result.output())

    def test_no_match_does_not_invent(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DatabankStore(Path(tmp.name))
        store.save_page(
            "Manor Lords",
            "https://example.com/wiki/food",
            "Food",
            "Check the granary before winter.",
        )
        result = ask_pages(store, "Manor Lords", "how do nuclear reactors work")
        self.assertTrue(result.ok)
        self.assertFalse(result.empty)
        self.assertEqual(result.hits, ())
        self.assertIn("Nothing invented", result.output())
        self.assertNotIn("reactor", result.output().lower())

    def test_uses_detected_game_folder_not_general(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DatabankStore(Path(tmp.name))
        store.save_page(None, "https://example.com/general", "General", "Only general oats.")
        store.save_page(
            "Manor Lords",
            "https://example.com/wiki/hunting",
            "Hunting",
            "Hunters bring meat to the camp.",
        )
        general = ask_pages(store, None, "where is hunting meat")
        manor = ask_pages(store, "Manor Lords", "where is hunting meat")
        self.assertTrue(general.empty or "meat" not in general.output().lower())
        self.assertIn("meat", manor.output().lower())

    def test_blank_question_does_not_search(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DatabankStore(Path(tmp.name))
        store.save_page(None, "https://example.com/a", "A", "alpha food")
        result = ask_pages(store, None, "   ")
        self.assertFalse(result.ok)
        self.assertIn("Type a question", result.message)

    def test_does_not_call_fetch_or_a_model(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DatabankStore(Path(tmp.name))
        store.save_page(None, "https://example.com/food", "Food", "Store berries in the granary.")
        with patch("battlebuddy.databank.fetch.fetch_page") as fetch:
            result = ask_pages(store, None, "berries")
        fetch.assert_not_called()
        self.assertIn("berries", result.output().lower())


class AskUiSourceTest(unittest.TestCase):
    def test_ask_box_and_local_search_hooks(self) -> None:
        source = Path(ui_app.__file__).read_text(encoding="utf-8")
        self.assertIn('text="ASK"', source)
        self.assertIn("ask_pages", source)
        self.assertIn("self.ask_entry", source)
        self.assertIn("self.ask_out", source)
        self.assertIn('text="SUBMIT"', source)
        self.assertIn('text="ADD / FETCH"', source)
        self.assertIn("self._tick_clocks()", source)
        self.assertNotIn("openai", source.lower())
        self.assertNotIn("anthropic", source.lower())


class AskUiTest(unittest.TestCase):
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

    def _app(self):
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
        app.root.withdraw()
        return app

    def test_empty_folder_and_clears_box_on_success(self) -> None:
        app = self._app()
        try:
            self.assertEqual(app.ask_entry.get(), "")
            app.ask_entry.insert(0, "where is food")
            app._ask()
            out = app.ask_out.get("1.0", "end-1c")
            self.assertIn("ADD / FETCH", out)
            self.assertEqual(app.ask_entry.get(), "")
            app.ask_entry.insert(0, "   ")
            app._ask()
            self.assertEqual(app.ask_entry.get(), "   ")
            self.assertIn("Type a question", app.ask_out.get("1.0", "end-1c"))
        finally:
            app._on_close()

    def test_match_from_saved_page_no_invent(self) -> None:
        store = DatabankStore(self.home)
        store.save_page(
            None,
            "https://example.com/wiki/food",
            "Food",
            "Check the granary before winter.",
        )
        app = self._app()
        try:
            app.ask_entry.insert(0, "where is the granary")
            app._ask()
            out = app.ask_out.get("1.0", "end-1c").lower()
            self.assertIn("granary", out)
            self.assertEqual(app.ask_entry.get(), "")
            app.ask_entry.insert(0, "nuclear reactor core")
            app._ask()
            miss = app.ask_out.get("1.0", "end-1c")
            self.assertIn("Nothing invented", miss)
            self.assertNotIn("reactor", miss.lower())
        finally:
            app._on_close()


if __name__ == "__main__":
    unittest.main()

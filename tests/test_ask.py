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
from battlebuddy.databank.wiki import ask_or_hunt
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

    def test_spear_question_without_spear_is_no_match(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DatabankStore(Path(tmp.name))
        store.save_page(
            None,
            "https://example.com/wiki",
            "Manor Lords Wiki",
            "Welcome. Start production with ale. Baron Hildebolt holds the manor.",
        )
        result = ask_pages(store, None, "How do I start a spear production?")
        self.assertTrue(result.ok)
        self.assertFalse(result.empty)
        self.assertEqual(result.hits, ())
        self.assertIn("Nothing invented", result.output())
        self.assertNotIn("ale", result.output().lower())
        self.assertNotIn("hildebolt", result.output().lower())
        self.assertNotIn("baron", result.output().lower())

    def test_spear_on_disk_snippet_includes_spear(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DatabankStore(Path(tmp.name))
        store.save_page(
            None,
            "https://example.com/wiki/spear",
            "Spear",
            "A spear is a hunting weapon. Craft a spear at the smithy.",
        )
        result = ask_pages(store, None, "How do I start a spear production?")
        self.assertTrue(result.ok)
        self.assertTrue(result.hits)
        self.assertIn("spear", result.output().lower())
        self.assertNotIn("Nothing invented", result.output())

    def test_does_not_call_fetch_or_a_model(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DatabankStore(Path(tmp.name))
        store.save_page(None, "https://example.com/food", "Food", "Store berries in the granary.")
        with patch("battlebuddy.databank.fetch.fetch_page") as fetch:
            with patch("battlebuddy.databank.wiki.search_wiki_urls") as hunt:
                result = ask_or_hunt(store, None, "berries")
        fetch.assert_not_called()
        hunt.assert_not_called()
        self.assertIn("berries", result.output().lower())

    def test_strips_icon_html_entities_and_leads_with_recipe(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DatabankStore(Path(tmp.name))
        dirty = (
            "{{Icon|Spear}} <b>Spear Militia</b> fills the barracks. "
            "Spears: obtained from Planks and Iron Slabs at the "
            "Blacksmith&#039;s Workshop backyard extension."
        )
        store.save_page(
            "Manor Lords",
            "https://example.com/wiki/military",
            "Military items",
            dirty,
        )
        result = ask_pages(store, "Manor Lords", "How do I start a spear production?")
        out = result.output()
        first = out.splitlines()[0]
        self.assertTrue(result.hits)
        self.assertNotIn("{{Icon", out)
        self.assertNotIn("<b>", out)
        self.assertNotIn("&#039;", out)
        self.assertIn("Blacksmith's", out)
        self.assertIn("obtained", first.lower())
        self.assertIn("spear", first.lower())
        self.assertIn("workshop", first.lower())
        self.assertNotEqual(first, first.lower())
        self.assertLess(len(first.split()), 28)
        self.assertFalse(first.lower().startswith("spear militia"))
        self.assertFalse(first.islower())


class AskUiSourceTest(unittest.TestCase):
    def test_ask_box_and_local_search_hooks(self) -> None:
        source = Path(ui_app.__file__).read_text(encoding="utf-8")
        self.assertIn('text="ASK"', source)
        self.assertIn('"ASK YOUR QUESTION"', source)
        self.assertIn('"REMINDER"', source)
        self.assertIn("Lock a time reminder here", source)
        self.assertIn("Paste a wiki URL here", source)
        self.assertIn("ask_pages", source)
        self.assertIn("ask_or_hunt", source)
        self.assertIn("should_hunt", source)
        self.assertIn("rank_ask_result", source)
        self.assertIn("Looking on the wiki.", source)
        self.assertIn("self.ask_entry", source)
        self.assertIn("self.ask_out", source)
        self.assertIn("self._show_ask", source)
        self.assertIn("ask_visible_message", source)
        self.assertIn("present_ask", source)
        self.assertIn("pack_propagate(False)", source)
        self.assertIn('text="SUBMIT"', source)
        self.assertIn('text="ADD / FETCH"', source)
        self.assertIn("self._tick_clocks()", source)
        self.assertNotIn("openai", source.lower())
        self.assertNotIn("anthropic", source.lower())
        show = source.split("def _show_ask")[1].split("def ")[0]
        self.assertIn("_set_ask_out", show)
        self.assertNotIn("databank_status", show)
        self.assertNotIn("self.status", show)
        apply_src = source.split("def _apply_game")[1].split("def ")[0]
        self.assertNotIn('_set_ask_out("")', apply_src)
        self.assertIn("switched_databank_line", apply_src)
        self.assertIn("databank_status", apply_src)


class AskVisibleMessageTest(unittest.TestCase):
    def test_empty_folder_and_hit_are_the_ui_text(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DatabankStore(Path(tmp.name))
        empty = ask_pages(store, None, "where is food")
        shown = ui_app.ask_visible_message(empty)
        self.assertEqual(shown, empty.output())
        self.assertIn("ADD / FETCH", shown)
        store.save_page(
            None,
            "https://example.com/wiki/food",
            "Food",
            "Check the granary before winter.",
        )
        hit = ask_pages(store, None, "where is the granary")
        shown_hit = ui_app.ask_visible_message(hit)
        self.assertEqual(shown_hit, hit.output())
        self.assertIn("granary", shown_hit.lower())
        miss = ask_pages(store, None, "nuclear reactor core")
        shown_miss = ui_app.ask_visible_message(miss)
        self.assertEqual(shown_miss, miss.output())
        self.assertIn("Nothing invented", shown_miss)


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

    def test_visible_label_shows_empty_folder_and_hit(self) -> None:
        app = self._app()
        try:
            app.ask_entry.insert(0, "where is food")
            expected = ui_app.ask_visible_message(
                ask_pages(app.databank, app._game_name, app.ask_entry.get())
            )
            app._ask()
            self.assertIn("ADD / FETCH", expected)
            self.assertEqual(app.ask_out.get("1.0", "end-1c"), expected)
            self.assertNotEqual(str(app.status.cget("text")), expected)
            self.assertNotEqual(str(app.databank_status.cget("text")), expected)
        finally:
            app._on_close()

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
            expected = ui_app.ask_visible_message(
                ask_pages(app.databank, app._game_name, app.ask_entry.get())
            )
            app._ask()
            self.assertIn("granary", expected.lower())
            self.assertEqual(app.ask_out.get("1.0", "end-1c"), expected)
            self.assertNotEqual(str(app.status.cget("text")), expected)
            self.assertNotEqual(str(app.databank_status.cget("text")), expected)
        finally:
            app._on_close()

    def test_spear_ask_needs_spear_on_disk(self) -> None:
        store = DatabankStore(self.home)
        store.save_page(
            None,
            "https://example.com/wiki",
            "Manor Lords Wiki",
            "Welcome. Start production with ale. Baron Hildebolt holds the manor.",
        )
        app = self._app()
        try:
            app.ask_entry.insert(0, "How do I start a spear production?")
            app._ask()
            miss = app.ask_out.get("1.0", "end-1c")
            self.assertIn("Nothing invented", miss)
            self.assertNotIn("ale", miss.lower())
            self.assertNotIn("hildebolt", miss.lower())
        finally:
            app._on_close()

        store.save_page(
            None,
            "https://example.com/wiki/spear",
            "Spear",
            "A spear is a hunting weapon. Craft a spear at the smithy.",
        )
        app = self._app()
        try:
            app.ask_entry.insert(0, "How do I start a spear production?")
            app._ask()
            hit = app.ask_out.get("1.0", "end-1c").lower()
            self.assertIn("spear", hit)
        finally:
            app._on_close()

    def test_detect_flicker_does_not_wipe_ask(self) -> None:
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
            hit = app.ask_out.get("1.0", "end-1c")
            reminder = str(app.status.cget("text"))
            self.assertIn("granary", hit.lower())
            self.assertNotEqual(reminder, hit)
            app._apply_game("Manor Lords")
            self.assertEqual(app.ask_out.get("1.0", "end-1c"), hit)
            self.assertEqual(str(app.status.cget("text")), reminder)
            self.assertEqual(app._game_name, "Manor Lords")
            app._apply_game(None)
            self.assertEqual(app.ask_out.get("1.0", "end-1c"), hit)
            self.assertEqual(str(app.status.cget("text")), reminder)
            self.assertEqual(app._game_name, "Manor Lords")
            app._apply_game("Manor Lords")
            self.assertEqual(app.ask_out.get("1.0", "end-1c"), hit)
            self.assertEqual(str(app.status.cget("text")), reminder)
            app._apply_game("RimWorld")
            notice = ui_app.switched_databank_line("RimWorld")
            self.assertIn("switched databank", notice.lower())
            self.assertEqual(app.ask_out.get("1.0", "end-1c"), notice)
            self.assertEqual(str(app.databank_status.cget("text")), notice)
            self.assertEqual(str(app.status.cget("text")), reminder)
            self.assertNotEqual(reminder, notice)
        finally:
            app._on_close()


if __name__ == "__main__":
    unittest.main()

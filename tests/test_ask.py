"""Ask searches local page text only. No model. No invent."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from battlebuddy.databank.clean import recipe_sentence, start_path_sentence, strip_markup
from battlebuddy.databank.reason import PAGE_CAP, present_ask
from battlebuddy.databank.search import ask_pages, content_terms, query_terms, search_folder
from battlebuddy.databank.store import DatabankStore
from battlebuddy.databank.wiki import ask_or_hunt
from battlebuddy.ui import app as ui_app

_BURGAGE_BODY = (
    "Indicates the possibility of adding a backyard extension. "
    "Burgage costs 2 timber. One backyard extension. "
    "Level 1 enables T1 backyards. Level 2 enables T2 backyard extensions. "
    "Level 2 upgrade cost: 2 timber + 8 planks. "
    "Tier 2 backyards turn the family into artisans. "
    "Tier 2 Backyards Backyard extension Cost Produces Perks/Affinities "
    "Requires Maintenance Bakery 6 Planks 10 RW 1 Wheat Flour into 4 Wheat Bread "
    "or 1 Rye Flour into 2 Rye Bread -0.2 Weiden Hinterlanders Blacksmith 8 Planks "
    "25 RW 1 Iron Slab and 1 Plank into 2 Spears or 2 Iron Slabs into 1 Sidearm "
    "or 1 Iron Slab and 1 Plank into 1 Polearms or 1 Iron Slab into 1 Tool or "
    "1 Iron Slab into 1 Iron Part +0.2 Smiths of Passau -0.2 Weiden Hinterlanders "
    "Brewery 6 Planks 10 RW 1 Malt into 2 Ale."
)
_MILITARY_BODY = (
    "Spears: obtained from Planks and Iron Slabs at the "
    "Blacksmith's Workshop backyard extension."
)
_PATCH_BODY = (
    "Changed order of goods produced for Blacksmith and Joiner to list Spears "
    "and Large shields first. Start of the production notes for this hotfix."
)
_START_Q = "how do I start spear production?"
_START_Q_BARE = "how do I start spear production"


def _long_burgage_body() -> str:
    """Real-page shape: Hooded Horse chrome first, T2 Blacksmith table last."""
    chrome = (
        "Manor Lords Official Wiki. Other Hooded Horse games: Blacksmith Master, "
        "Songs of Conquest, Terra Invicta. "
        "Indicates the possibility of adding a backyard extension. "
        "Burgage costs 2 timber. Level 1 burgage plots. "
        "Level 1 enables T1 backyards. "
    )
    filler = "See also Marketplace and Approval. " * 250
    table = (
        "Level 2 enables T2 backyard extensions. "
        "Tier 2 backyards turn the family into artisans. "
        "Tier 2 Backyards Backyard extension Cost Produces "
        "Bakery 6 Planks 10 RW 1 Wheat Flour into 4 Wheat Bread "
        "Blacksmith 8 Planks 25 RW 1 Iron Slab and 1 Plank into 2 Spears "
        "or 2 Iron Slabs into 1 Sidearm."
    )
    return chrome + filler + table


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
        manor = ask_pages(store, "Manor Lords", "where is hunting meat")
        self.assertIn("meat", manor.output().lower())
        self.assertNotIn("oats", manor.output().lower())
        unset = ask_pages(store, None, "where is hunting meat")
        self.assertIn("meat", unset.output().lower())

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

    def test_flattened_burgage_table_leads_with_spear_recipe(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DatabankStore(Path(tmp.name))
        dump = (
            "Tier 2 Backyards Backyard extension Cost Produces Perks/Affinities "
            "Requires Maintenance Bakery 6 Planks 10 RW 1 Wheat Flour into 4 Wheat Bread "
            "or 1 Rye Flour into 2 Rye Bread -0.2 Weiden Hinterlanders Blacksmith 8 Planks "
            "25 RW 1 Iron Slab and 1 Plank into 2 Spears or 2 Iron Slabs into 1 Sidearm "
            "or 1 Iron Slab and 1 Plank into 1 Polearms or 1 Iron Slab into 1 Tool or "
            "1 Iron Slab into 1 Iron Part +0.2 Smiths of Passau -0.2 Weiden Hinterlanders "
            "Brewery 6 Planks 10 RW 1 Malt into 2 Ale ..."
        )
        store.save_page(
            "Manor Lords",
            "https://example.com/wiki/Burgage_plot",
            "Burgage plot - Manor Lords Official Wiki",
            dump,
        )
        result = ask_pages(store, "Manor Lords", "How do I start a spear production?")
        out = result.output()
        first = out.splitlines()[0]
        low = first.lower()
        self.assertTrue(result.hits)
        self.assertIn("blacksmith", low)
        self.assertIn("iron", low)
        self.assertIn("plank", low)
        self.assertIn("spear", low)
        self.assertNotIn("bakery", low)
        self.assertNotIn("ale", low)
        self.assertNotIn("tailor", low)
        self.assertNotIn("bread", low)
        self.assertNotIn("hinterlanders", low)
        self.assertLess(len(first.split()), 30)

    def test_burgage_spear_with_game_unset_uses_manor_lords_folder(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DatabankStore(Path(tmp.name))
        dump = (
            "Tier 2 Backyards Backyard extension Cost Produces Perks/Affinities "
            "Requires Maintenance Bakery 6 Planks 10 RW 1 Wheat Flour into 4 Wheat Bread "
            "or 1 Rye Flour into 2 Rye Bread -0.2 Weiden Hinterlanders Blacksmith 8 Planks "
            "25 RW 1 Iron Slab and 1 Plank into 2 Spears or 2 Iron Slabs into 1 Sidearm "
            "or 1 Iron Slab and 1 Plank into 1 Polearms or 1 Iron Slab into 1 Tool or "
            "1 Iron Slab into 1 Iron Part +0.2 Smiths of Passau -0.2 Weiden Hinterlanders "
            "Brewery 6 Planks 10 RW 1 Malt into 2 Ale ..."
        )
        store.save_page(
            "Manor Lords",
            "https://example.com/wiki/Burgage_plot",
            "Burgage plot - Manor Lords Official Wiki",
            dump,
        )
        self.assertEqual(store.list_sources(None), [])
        result = ask_pages(store, None, "How do I start a spear production?")
        out = result.output()
        first = out.splitlines()[0]
        low = first.lower()
        self.assertTrue(result.hits)
        self.assertFalse(result.empty)
        self.assertIn("blacksmith", low)
        self.assertIn("iron", low)
        self.assertIn("plank", low)
        self.assertIn("spear", low)
        self.assertNotIn("No match on the wiki", out)
        self.assertNotIn("ADD / FETCH", out)
        self.assertNotIn("bakery", low)
        hunted = ask_or_hunt(store, None, "How do I start a spear production?")
        hunt_first = hunted.output().splitlines()[0]
        self.assertIn("blacksmith", hunt_first.lower())
        self.assertIn("spear", hunt_first.lower())

    def test_set_up_spear_needed_terms_are_just_spear(self) -> None:
        terms = query_terms("how to set up spear production")
        self.assertEqual(terms, ["set", "up", "spear", "production"])
        self.assertEqual(content_terms(terms), ["spear"])

    def test_tax_people_is_weak_taxing_is_not(self) -> None:
        terms = query_terms("how do I start taxing my people?")
        self.assertEqual(terms, ["start", "taxing", "people"])
        self.assertEqual(content_terms(terms), ["taxing"])
        self.assertNotIn("people", content_terms(terms))
        self.assertEqual(content_terms(query_terms("tax the people")), ["tax"])

    def test_strip_markup_drops_wiki_bold_italic_and_list_stars(self) -> None:
        dirty = "* ''' Spears ''': obtained from Planks and Iron Slabs"
        cleaned = strip_markup(dirty)
        self.assertNotIn("'''", cleaned)
        self.assertNotIn("''", cleaned)
        self.assertFalse(cleaned.lstrip().startswith("*"))
        self.assertIn("Spears", cleaned)
        self.assertIn("obtained", cleaned.lower())

    def test_set_up_spear_production_leads_with_blacksmith_not_homepage(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DatabankStore(Path(tmp.name))
        store.save_page(
            "Manor Lords",
            "https://manorlords.fandom.com/wiki/Amenities",
            "Amenities",
            "Set up a Market Stall on the plaza. Amenities hold up to three families.",
        )
        store.save_page(
            "Manor Lords",
            "https://manorlords.fandom.com/wiki/Clay_furnace",
            "Clay furnace",
            "Clay furnace. Up to three families can work the kiln.",
        )
        store.save_page(
            "Manor Lords",
            "https://manorlords.fandom.com/wiki/Weavers_workshop",
            "Weaver's workshop",
            "Weaver's workshop. Set up yarn, then cloth. Up to three families. "
            "A spear hangs on the wall as decor.",
        )
        store.save_page(
            "Manor Lords",
            "https://manorlords.fandom.com/wiki/Malthouse",
            "Malthouse",
            "Malthouse. Set up malt production. Up to three families.",
        )
        store.save_page(
            "Manor Lords",
            "https://manorlords.fandom.com/wiki/Bakery",
            "Bakery",
            "Bakery. Set up a Market Stall for bread. Up to three families.",
        )
        store.save_page(
            "Manor Lords",
            "https://example.com/wiki/military",
            "Military items",
            "* ''' Spears ''': obtained from Planks and Iron Slabs at the "
            "Blacksmith's Workshop backyard extension.",
        )
        dump = (
            "Tier 2 Backyards Backyard extension Cost Produces Perks/Affinities "
            "Requires Maintenance Bakery 6 Planks 10 RW 1 Wheat Flour into 4 Wheat Bread "
            "or 1 Rye Flour into 2 Rye Bread -0.2 Weiden Hinterlanders Blacksmith 8 Planks "
            "25 RW 1 Iron Slab and 1 Plank into 2 Spears or 2 Iron Slabs into 1 Sidearm "
            "or 1 Iron Slab and 1 Plank into 1 Polearms or 1 Iron Slab into 1 Tool or "
            "1 Iron Slab into 1 Iron Part +0.2 Smiths of Passau -0.2 Weiden Hinterlanders "
            "Brewery 6 Planks 10 RW 1 Malt into 2 Ale ..."
        )
        store.save_page(
            "Manor Lords",
            "https://example.com/wiki/Burgage_plot",
            "Burgage plot - Manor Lords Official Wiki",
            dump,
        )
        result = ask_pages(store, "Manor Lords", "how to set up spear production")
        out = result.output()
        first = out.splitlines()[0]
        low = out.lower()
        first_low = first.lower()
        self.assertTrue(result.hits)
        self.assertIn("blacksmith", first_low)
        self.assertIn("iron", first_low)
        self.assertIn("plank", first_low)
        self.assertIn("spear", first_low)
        self.assertNotIn("'''", out)
        self.assertFalse(first.lstrip().startswith("*"))
        self.assertNotIn("amenities", low)
        self.assertNotIn("market stall", low)
        self.assertNotIn("weaver", low)
        self.assertNotIn("clay", low)
        self.assertNotIn("malthouse", low)
        self.assertNotIn("bakery", low)

    def test_set_up_spear_homepage_without_spear_does_not_invent(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DatabankStore(Path(tmp.name))
        store.save_page(
            "Manor Lords",
            "https://manorlords.fandom.com/wiki/Amenities",
            "Amenities",
            "Set up a Market Stall. Up to three families. Weaver's workshop. "
            "Clay furnace. Malthouse. Bakery.",
        )
        result = ask_pages(store, "Manor Lords", "how to set up spear production")
        self.assertTrue(result.ok)
        self.assertEqual(result.hits, ())
        self.assertIn("Nothing invented", result.output())
        self.assertNotIn("market stall", result.output().lower())
        self.assertNotIn("amenities", result.output().lower())
        self.assertNotIn("weaver", result.output().lower())

    def test_spear_homepage_without_recipe_still_does_not_invent(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DatabankStore(Path(tmp.name))
        store.save_page(
            "Manor Lords",
            "https://example.com/wiki",
            "Manor Lords Wiki",
            "Welcome. Start production with ale. Baron Hildebolt holds the manor.",
        )
        result = ask_pages(store, None, "How do I start a spear production?")
        self.assertTrue(result.ok)
        self.assertEqual(result.hits, ())
        self.assertIn("Nothing invented", result.output())
        self.assertNotIn("No match on the wiki", result.output())
        self.assertNotIn("ale", result.output().lower())
        self.assertNotIn("hildebolt", result.output().lower())


class StartPathAskTest(unittest.TestCase):
    def _store(self) -> DatabankStore:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DatabankStore(Path(tmp.name))
        store.save_page(
            "Manor Lords",
            "https://wiki.hoodedhorse.com/Manor_Lords/0.8.050",
            "0.8.050 - Main - Manor Lords Official Wiki",
            _PATCH_BODY,
        )
        store.save_page(
            "Manor Lords",
            "https://wiki.hoodedhorse.com/Manor_Lords/Military_items",
            "Military items - Manor Lords Official Wiki",
            _MILITARY_BODY,
        )
        store.save_page(
            "Manor Lords",
            "https://wiki.hoodedhorse.com/Manor_Lords/Burgage_plot",
            "Burgage plot - Manor Lords Official Wiki",
            _BURGAGE_BODY,
        )
        return store

    def _assert_start_path(self, text: str) -> None:
        low = text.lower()
        self.assertIn("burgage", low)
        self.assertIn("level 2", low)
        self.assertIn("blacksmith", low)
        self.assertIn("iron slab", low)
        self.assertIn("plank", low)
        self.assertIn("spear", low)
        self.assertNotIn("level 1", low)
        self.assertNotIn("0.8.050", text)
        self.assertNotIn("Changed order of goods", text)
        self.assertNotIn("obtained from", low)
        self.assertLessEqual(len([part for part in text.replace("?", ".").split(".") if part.strip()]), 2)

    def test_start_spear_production_compiles_path_not_patch_notes(self) -> None:
        store = self._store()
        result = ask_or_hunt(store, "manor-lords", _START_Q)
        self.assertTrue(result.hits)
        self.assertIn("burgage", result.hits[0].title.lower())
        self.assertNotIn("0.8.050", result.hits[0].title)
        self._assert_start_path(result.output())
        shown = present_ask(result, _START_Q, store, "manor-lords", ports=(1,))
        self._assert_start_path(shown)

    def test_start_spear_production_without_question_mark(self) -> None:
        store = self._store()
        result = ask_or_hunt(store, "Manor Lords", _START_Q_BARE)
        self._assert_start_path(result.output())
        shown = present_ask(result, _START_Q_BARE, store, "Manor Lords", ports=(1,))
        self._assert_start_path(shown)

    def test_spear_production_still_returns_blacksmith_recipe(self) -> None:
        store = self._store()
        result = ask_or_hunt(store, "Manor Lords", "spear production")
        out = result.output()
        low = out.lower()
        self.assertIn("blacksmith", low)
        self.assertIn("iron slab", low)
        self.assertIn("plank", low)
        self.assertIn("spear", low)
        self.assertNotIn("0.8.050", out)
        self.assertNotIn("Changed order of goods", out)
        self.assertTrue(
            "blacksmith: 1 iron slab and 1 plank into 2 spears" in low
            or "obtained from planks and iron slabs" in low
        )

    def test_patch_notes_do_not_outrank_burgage_in_tmp_folder(self) -> None:
        store = self._store()
        result = ask_or_hunt(store, "Manor Lords", _START_Q)
        titles = [hit.title for hit in result.hits]
        self.assertTrue(titles)
        self.assertIn("burgage", titles[0].lower())
        self.assertFalse(titles[0].startswith("0.8.050"))
        for hit in result.hits:
            if "0.8.050" in hit.title:
                burgage = next(item for item in result.hits if "burgage" in item.title.lower())
                self.assertGreater(burgage.score, hit.score)

    def test_recipe_sentence_skips_backyard_definition(self) -> None:
        line = recipe_sentence(_BURGAGE_BODY, ["spear"])
        self.assertIsNotNone(line)
        assert line is not None
        self.assertIn("Blacksmith", line)
        self.assertIn("Iron Slab", line)
        self.assertIn("Plank", line)
        self.assertIn("Spears", line)
        self.assertNotIn("Indicates", line)
        self.assertNotIn("possibility", line.lower())
        path = start_path_sentence(
            "Burgage plot - Manor Lords Official Wiki\n" + _BURGAGE_BODY,
            ["spear"],
        )
        self.assertIsNotNone(path)
        assert path is not None
        self._assert_start_path(path)
        self.assertIn("8 planks", path.lower())
        self.assertIn("25 regional wealth", path.lower())
        self.assertIn("level 2", path.lower())


class RealWikiStartPathTest(unittest.TestCase):
    def _store(self) -> DatabankStore:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DatabankStore(Path(tmp.name))
        body = _long_burgage_body()
        cleaned = strip_markup(body)
        self.assertGreater(len(cleaned), PAGE_CAP)
        self.assertNotIn("into 2 Spears", cleaned[:PAGE_CAP])
        self.assertIn("Blacksmith Master", body)
        store.save_page(
            "Manor Lords",
            "https://wiki.hoodedhorse.com/Manor_Lords/0.8.050",
            "0.8.050 - Main - Manor Lords Official Wiki",
            _PATCH_BODY,
        )
        store.save_page(
            "Manor Lords",
            "https://wiki.hoodedhorse.com/Manor_Lords/Military_items",
            "Military items - Manor Lords Official Wiki",
            _MILITARY_BODY,
        )
        store.save_page(
            "Manor Lords",
            "https://wiki.hoodedhorse.com/Manor_Lords/Burgage_plot",
            "Burgage plot - Manor Lords Official Wiki",
            body,
        )
        return store

    def _assert_full_start_path(self, text: str) -> None:
        low = text.lower()
        self.assertIn("burgage", low)
        self.assertIn("level 2", low)
        self.assertIn("blacksmith", low)
        self.assertIn("8 planks", low)
        self.assertIn("25 regional wealth", low)
        self.assertIn("1 iron slab", low)
        self.assertIn("1 plank", low)
        self.assertIn("2 spears", low)
        self.assertNotIn("level 1", low)
        self.assertNotIn("0.8.050", text)
        self.assertNotIn("Changed order of goods", text)
        self.assertNotIn("obtained from", low)

    def test_chrome_and_long_page_still_level_2_in_present_ask(self) -> None:
        store = self._store()
        result = ask_or_hunt(store, "Manor Lords", _START_Q)
        path = start_path_sentence(
            "Burgage plot - Manor Lords Official Wiki\n" + _long_burgage_body(),
            ["spear"],
        )
        self.assertIsNotNone(path)
        assert path is not None
        self._assert_full_start_path(path)
        self._assert_full_start_path(result.output())
        shown = present_ask(result, _START_Q, store, "Manor Lords", ports=(1,))
        self._assert_full_start_path(shown)
        self.assertIn("level 2", shown.lower())
        self.assertNotIn("Upgrade a burgage plot to level 1", shown)

    def test_short_spear_production_still_produce_row(self) -> None:
        store = self._store()
        result = ask_or_hunt(store, "Manor Lords", "spear production")
        shown = present_ask(result, "spear production", store, "Manor Lords", ports=(1,))
        low = shown.lower()
        self.assertIn("blacksmith: 1 iron slab and 1 plank into 2 spears", low)
        self.assertNotIn("obtained from", low)
        self.assertNotIn("0.8.050", shown)
        self.assertNotIn("Changed order of goods", shown)


class HuntFailureTest(unittest.TestCase):
    def test_exception_keeps_local_hit_not_fake_wiki_miss(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DatabankStore(Path(tmp.name))
        dump = (
            "Blacksmith 8 Planks 25 RW 1 Iron Slab and 1 Plank into 2 Spears "
            "or 2 Iron Slabs into 1 Sidearm"
        )
        store.save_page(
            "Manor Lords",
            "https://example.com/wiki/Burgage_plot",
            "Burgage plot - Manor Lords Official Wiki",
            dump,
        )
        local = ask_pages(store, None, "How do I start a spear production?")
        self.assertTrue(local.hits)
        shown = ui_app.shown_after_hunt_failure(local)
        self.assertIn("blacksmith", shown.lower())
        self.assertIn("spear", shown.lower())
        self.assertNotIn("No match on the wiki", shown)
        with patch("battlebuddy.ui.app.ask_or_hunt", side_effect=RuntimeError("net")):
            result, pane = ui_app.hunt_or_keep_local(
                store,
                None,
                "How do I start a spear production?",
                local,
            )
        self.assertIs(result, local)
        self.assertIn("blacksmith", pane.lower())
        self.assertIn("spear", pane.lower())
        self.assertNotIn("No match on the wiki", pane)
        with patch("battlebuddy.ui.app.present_ask", side_effect=ValueError("regex")):
            kept, pane2 = ui_app.hunt_or_keep_local(
                store,
                None,
                "How do I start a spear production?",
                local,
            )
        self.assertIsNotNone(kept)
        self.assertTrue(getattr(kept, "hits", ()))
        self.assertNotIn("No match on the wiki", pane2)
        self.assertIn("spear", pane2.lower())
        empty = ui_app.shown_after_hunt_failure(None)
        self.assertIn("ADD / FETCH", empty)
        self.assertNotIn("No match on the wiki", empty)


class AskUiSourceTest(unittest.TestCase):
    def test_ask_box_and_local_search_hooks(self) -> None:
        source = Path(ui_app.__file__).read_text(encoding="utf-8")
        self.assertIn('text="Submit"', source)
        self.assertIn("Wiki or question", source)
        self.assertIn('"Reminder"', source)
        self.assertIn("Lock a time reminder here", source)
        self.assertIn("Paste a wiki link or ask a game question", source)
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
        self.assertIn("start_bundled_server", source)
        self.assertIn("stop_bundled_server", source)
        self.assertIn("_warm_bundled_llm", source)
        self.assertIn("shown_after_hunt_failure", source)
        self.assertIn("hunt_or_keep_local", source)
        self.assertIn("sole_saved_game", source)
        self.assertIn("pack_propagate(False)", source)
        hunt_done = source.split("def _ask_hunt_done")[1].split("def ")[0]
        self.assertNotIn("No match on the wiki. Nothing invented.", hunt_done)
        self.assertIn('text="SUBMIT"', source)
        self.assertIn("looks_like_public_url", source)
        self.assertIn("self._submit_query", source)
        self.assertNotIn('text="ADD / FETCH"', source)
        self.assertNotIn('"ASK YOUR QUESTION"', source)
        self.assertIn("self._tick_clocks()", source)
        self.assertNotIn("openai", source.lower())
        self.assertNotIn("anthropic", source.lower())
        show = source.split("def _show_ask")[1].split("def ")[0]
        self.assertIn("_set_ask_out", show)
        self.assertNotIn("databank_status", show)
        self.assertNotIn("self.status", show)
        close_src = source.split("def _on_close")[1]
        self.assertIn("stop_bundled_server", close_src)
        apply_src = source.split("def _apply_game")[1].split("def ")[0]
        self.assertNotIn('_set_ask_out("")', apply_src)
        self.assertIn("switched_databank_line", apply_src)
        self.assertIn("databank_status", apply_src)
        self.assertIn("_maybe_seed_wiki", apply_src)
        self.assertIn("seed_hold_line", source)
        self.assertIn("sources_count_line", source)
        self.assertIn("self.source_count", source)
        refresh = source.split("def _refresh_sources")[1].split("def ")[0]
        self.assertIn("sources_count_line", refresh)
        self.assertIn("list_sources", refresh)
        self.assertNotIn("item.title", refresh)
        self.assertNotIn("for item in sources", refresh)
        ask_build = source.split("def _build_ask")[1].split("def ")[0]
        self.assertIn("self.ask_out", ask_build)
        self.assertIn("expand=True", ask_build)
        from battlebuddy.databank.seed import seed_hold_line

        self.assertIn("Hold the line. Fetching wiki pages", seed_hold_line("Valheim"))


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

    def test_burgage_ask_before_detect_uses_sole_folder(self) -> None:
        store = DatabankStore(self.home)
        dump = (
            "Blacksmith 8 Planks 25 RW 1 Iron Slab and 1 Plank into 2 Spears "
            "or 2 Iron Slabs into 1 Sidearm"
        )
        store.save_page(
            "Manor Lords",
            "https://example.com/wiki/Burgage_plot",
            "Burgage plot - Manor Lords Official Wiki",
            dump,
        )
        app = self._app()
        try:
            self.assertEqual(app._game_name, "Manor Lords")
            app.ask_entry.insert(0, "How do I start a spear production?")
            app._ask()
            out = app.ask_out.get("1.0", "end-1c")
            first = out.splitlines()[0].lower() if out else ""
            self.assertIn("blacksmith", first)
            self.assertIn("spear", first)
            self.assertNotIn("No match on the wiki", out)
        finally:
            app._on_close()

    def test_detect_flicker_does_not_wipe_ask(self) -> None:
        store = DatabankStore(self.home)
        store.save_page(
            "Manor Lords",
            "https://example.com/wiki/food",
            "Food",
            "Check the granary before winter.",
        )
        app = self._app()
        try:
            app._start_wiki_seed = lambda _game: None  # type: ignore[method-assign]
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
            hold = ui_app.seed_hold_line("RimWorld")
            self.assertIn("Hold the line", hold)
            self.assertEqual(app.ask_out.get("1.0", "end-1c"), hold)
            self.assertEqual(str(app.databank_status.cget("text")), hold)
            self.assertEqual(str(app.status.cget("text")), reminder)
            self.assertNotEqual(reminder, hold)
        finally:
            app._on_close()


_TAX_Q = "how do I start taxing my people?"
_BUILDINGS_TAX = (
    "Manor costs 5 Timber, 20 Planks and 25 Stone. Once constructed it grants 250 "
    "Influence, rises the Administration level by 1 and enables taxing people. "
    "It requires Fuel resources. Only one Manor can be constructed per region. "
    "Provides acces to your retinue and various forms of taxation. "
    "Tax offices cost 4 Timber. At present, this building is purely cosmetic."
)
_FAQ_TAX = (
    "It is generated via Tax (from a regions manor) as well as clearing out Bandit Camps. "
    "For Tax, you need to have regional wealth. No Regional Wealth = no tax income to your Treasury. "
    "Food types: berries, meat, bread."
)
_FAMILY = (
    "A family occupies a burgage plot. People work at assigned workplaces. "
    "Each family has two workers."
)
_FISHERMAN = (
    "Fisherman's hut. Catch fish in the nearby river. Assign a family to work the hut."
)
_DEVELOPMENT = (
    "Annual Royal Tax comes from here. Land tax approval malus. "
    "Treasury grows from royal tax."
)
_BYGGNADER = "Byggnader. Buildings TOC. Family. People. Se även fiskarstuga."


class TaxHowToAskTest(unittest.TestCase):
    def _store(self, *, manor: bool = True) -> DatabankStore:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DatabankStore(Path(tmp.name))
        buildings = _BUILDINGS_TAX if manor else (
            "Provides acces to your retinue and various forms of taxation. "
            "Tax offices cost 4 Timber. At present, this building is purely cosmetic."
        )
        store.save_page(
            "Manor Lords",
            "https://wiki.hoodedhorse.com/Manor_Lords/Buildings",
            "Buildings - Manor Lords Official Wiki",
            buildings,
        )
        store.save_page(
            "Manor Lords",
            "https://wiki.hoodedhorse.com/Manor_Lords/FAQ",
            "FAQ - Manor Lords Official Wiki",
            _FAQ_TAX,
        )
        store.save_page(
            "Manor Lords",
            "https://wiki.hoodedhorse.com/Manor_Lords/Family",
            "Family - Manor Lords Official Wiki",
            _FAMILY,
        )
        store.save_page(
            "Manor Lords",
            "https://wiki.hoodedhorse.com/Manor_Lords/Fishermans_hut",
            "Fisherman's hut - Manor Lords Official Wiki",
            _FISHERMAN,
        )
        store.save_page(
            "Manor Lords",
            "https://wiki.hoodedhorse.com/Manor_Lords/Development",
            "Development - Manor Lords Official Wiki",
            _DEVELOPMENT,
        )
        store.save_page(
            "Manor Lords",
            "https://wiki.hoodedhorse.com/Manor_Lords/0.8.050",
            "0.8.050 - Main - Manor Lords Official Wiki",
            "Changed tax tooltip. Start of the production notes for this hotfix.",
        )
        store.save_page(
            "Manor Lords",
            "https://wiki.hoodedhorse.com/Manor_Lords/Byggnader",
            "Byggnader - Manor Lords Official Wiki",
            _BYGGNADER,
        )
        return store

    def _assert_not_scraps(self, text: str) -> None:
        low = text.lower()
        self.assertNotIn("fisherman", low)
        self.assertNotIn("workplaces", low)
        self.assertNotIn("food types", low)
        self.assertNotIn("berries", low)
        self.assertNotIn("annual royal tax comes from here", low)
        self.assertNotIn("byggnader", low)
        self.assertNotIn("fiskarstuga", low)
        self.assertLessEqual(
            len([part for part in text.replace("?", ".").split(".") if part.strip()]),
            2,
        )

    def test_tax_question_compiles_manor_and_wealth(self) -> None:
        store = self._store()
        result = ask_or_hunt(store, "Manor Lords", _TAX_Q)
        shown = present_ask(result, _TAX_Q, store, "Manor Lords", ports=(1,))
        low = shown.lower()
        self.assertIn("manor", low)
        self.assertIn("enables taxing", low)
        self.assertIn("5", shown)
        self.assertIn("timber", low)
        self.assertIn("20", shown)
        self.assertIn("plank", low)
        self.assertIn("25", shown)
        self.assertIn("stone", low)
        self.assertTrue("regional wealth" in low or "treasury" in low)
        self._assert_not_scraps(shown)
        self.assertEqual(shown, result.output())

    def test_tax_without_manor_paragraph_is_a_miss(self) -> None:
        store = self._store(manor=False)
        store.save_page(
            "Manor Lords",
            "http://127.0.0.1:9/wiki/",
            "Manor Lords Wiki",
            "Welcome.",
        )
        result = ask_or_hunt(store, "Manor Lords", _TAX_Q)
        shown = present_ask(result, _TAX_Q, store, "Manor Lords", ports=(1,))
        low = shown.lower()
        self.assertTrue(
            "can't find that" in low
            or "nothing invented" in low
            or "restate" in low
        )
        self.assertNotIn("fisherman", low)
        self.assertNotIn("workplaces", low)
        self.assertNotIn("food types", low)
        self.assertNotIn("family occupies", low)
        self.assertNotIn("annual royal tax comes from here", low)
        self.assertNotIn("byggnader", low)


class DuplicateBuildingsTaxTest(unittest.TestCase):
    """Real-disk shape: two Buildings titles. Short infobox sorts first."""

    _TITLE = "Buildings - Manor Lords Official Wiki"
    _SHORT = (
        "Buildings infobox. Burgage plot. Marketplace. Granary. "
        "Region cost timber. No manor paragraph here."
    )
    _LONG = (
        "Burgage plot. Marketplace. "
        "Manor costs 5 Timber, 20 Planks and 25 Stone. Once constructed it grants 250 "
        "Influence, rises the Administration level by 1 and enables taxing people. "
        "It requires Fuel resources. Only one Manor can be constructed per region."
    )
    _DEV = "The Annual Royal Tax comes from here, if enabled in game setup."

    def _store(self) -> DatabankStore:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DatabankStore(Path(tmp.name))
        folder = store.folder("Manor Lords")
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "111_buildings.txt").write_text(
            f"{self._TITLE}\nhttps://wiki.hoodedhorse.com/Manor_Lords/Buildings\n\n{self._SHORT}\n",
            encoding="utf-8",
        )
        (folder / "999_buildings.txt").write_text(
            f"{self._TITLE}\nhttps://wiki.hoodedhorse.com/Manor_Lords/Buildings/full\n\n{self._LONG}\n",
            encoding="utf-8",
        )
        store.save_page(
            "Manor Lords",
            "https://wiki.hoodedhorse.com/Manor_Lords/Development",
            "Development - Manor Lords Official Wiki",
            self._DEV,
        )
        return store

    def test_present_ask_uses_long_buildings_not_if_enabled(self) -> None:
        store = self._store()
        result = ask_or_hunt(store, "Manor Lords", _TAX_Q)
        self.assertTrue(result.hits)
        shown = present_ask(result, _TAX_Q, store, "Manor Lords", ports=(1,))
        low = shown.lower()
        self.assertIn("manor", low)
        self.assertIn("5", shown)
        self.assertIn("timber", low)
        self.assertIn("20", shown)
        self.assertIn("plank", low)
        self.assertIn("25", shown)
        self.assertIn("stone", low)
        self.assertIn("enables taxing", low)
        self.assertNotIn("annual royal tax comes from here", low)
        self.assertNotIn("if enabled in game setup", low)
        self.assertNotIn("Can't find that", shown)

    def test_page_text_picks_snippet_or_longest(self) -> None:
        from battlebuddy.databank.search import page_text_for_title

        store = self._store()
        snippet = (
            "Manor costs 5 Timber, 20 Planks and 25 Stone and enables taxing people."
        )
        picked = page_text_for_title(
            store,
            "Manor Lords",
            self._TITLE,
            snippet=snippet,
        )
        self.assertIn("enables taxing people", picked.lower())
        self.assertIn("5 timber", picked.lower())
        self.assertNotIn("no manor paragraph here", picked.lower())


if __name__ == "__main__":
    unittest.main()

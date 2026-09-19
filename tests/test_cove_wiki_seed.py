"""Corsair Cove wiki seed. Hub children only. Mock HTTP. No paste. No invent."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from battlebuddy.databank.fetch import FetchResult
from battlebuddy.databank.seed import (
    pick_cove_child_urls,
    seed_new_game,
)
from battlebuddy.databank.store import DatabankStore
from battlebuddy.databank.wiki import KNOWN_WIKIS
from battlebuddy.memory.store import MemoryStore
from battlebuddy.reminders.commands import run_line
from battlebuddy.reminders.engine import ReminderEngine
from battlebuddy.ui import app as ui_app

_HUB_HTML = """
<html><body>
<a href="/Corsair_Cove/Ships">Ships</a>
<a href="/Corsair_Cove/Crew">Crew</a>
<a href="/Corsair_Cove/Trade">Trade</a>
<a href="/Corsair_Cove/Combat">Combat</a>
<a href="https://store.steampowered.com/app/1368140">Steam</a>
<a href="/Corsair_Cove/">Hub</a>
<a href="/Corsair_Cove/api.php">api</a>
<a href="/Corsair_Cove/Special:Search">special</a>
</body></html>
"""


def _ok(url: str) -> FetchResult:
    return FetchResult(ok=True, url=url, message="Saved on disk.", title="t", text="body")


class CoveChildParseTest(unittest.TestCase):
    def test_three_children_skip_steam_hub_special(self) -> None:
        picked = pick_cove_child_urls(_HUB_HTML)
        self.assertEqual(len(picked), 3)
        self.assertEqual(
            picked,
            [
                "https://wiki.hoodedhorse.com/Corsair_Cove/Ships",
                "https://wiki.hoodedhorse.com/Corsair_Cove/Crew",
                "https://wiki.hoodedhorse.com/Corsair_Cove/Trade",
            ],
        )
        joined = " ".join(picked)
        self.assertNotIn("steampowered", joined)
        self.assertNotIn("Special:", joined)
        self.assertNotIn("api.php", joined)


class CoveWikiHomeTest(unittest.TestCase):
    def test_known_wiki_home(self) -> None:
        home = KNOWN_WIKIS["corsair cove"]
        self.assertEqual(home.origin, "https://wiki.hoodedhorse.com")
        self.assertTrue(home.article_base.endswith("/Corsair_Cove/"))
        self.assertIn("Corsair_Cove/api.php", home.api)


class CoveSeedNewGameTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.store = DatabankStore(Path(self.tmp.name))
        self.saved: list[str] = []

    def test_seeds_hub_and_three_children_no_ddg(self) -> None:
        def add_url(_game: str | None, url: str) -> FetchResult:
            self.saved.append(url)
            return _ok(url)

        with patch("battlebuddy.databank.seed._get_html", return_value=_HUB_HTML):
            with patch("battlebuddy.databank.seed.search_wiki_urls") as ddg:
                with patch.object(self.store, "add_url", side_effect=add_url):
                    result = seed_new_game(self.store, "Corsair Cove")
        ddg.assert_not_called()
        self.assertTrue(result.started)
        self.assertEqual(result.saved, 4)
        self.assertIn("https://wiki.hoodedhorse.com/Corsair_Cove/", self.saved[0])
        children = [url for url in self.saved if url.rstrip("/").split("/")[-1] != "Corsair_Cove"]
        self.assertEqual(len(children), 3)
        self.assertNotIn("steampowered", " ".join(self.saved))
        self.assertNotIn("invent", result.message.lower())

    def test_valheim_still_uses_search(self) -> None:
        urls = ["https://valheim.fandom.com/wiki/Valheim_Wiki"]
        with patch("battlebuddy.databank.seed.search_wiki_urls", return_value=urls) as ddg:
            with patch.object(self.store, "add_url", side_effect=lambda _g, url: _ok(url)):
                result = seed_new_game(self.store, "Valheim")
        ddg.assert_called_once()
        self.assertTrue(result.started)
        self.assertEqual(result.saved, 1)


class CoveSeedCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.home = Path(self.tmp.name)
        self._old_home = os.environ.get("BATTLEBUDDY_HOME")
        os.environ["BATTLEBUDDY_HOME"] = str(self.home)
        os.environ.pop("XAI_API_KEY", None)
        self.addCleanup(self._restore)
        self.engine = ReminderEngine(MemoryStore(self.home / "memory.json"))

    def _restore(self) -> None:
        self.tmp.cleanup()
        if self._old_home is None:
            os.environ.pop("BATTLEBUDDY_HOME", None)
        else:
            os.environ["BATTLEBUDDY_HOME"] = self._old_home

    def test_seed_corsair_command(self) -> None:
        with patch("battlebuddy.databank.seed._get_html", return_value=_HUB_HTML):
            with patch(
                "battlebuddy.databank.store.DatabankStore.add_url",
                side_effect=lambda _self, _game, url: _ok(url),
            ):
                result = run_line(self.engine, "seed corsair")
        self.assertEqual(result.kind, "seed")
        self.assertIn("wiki", result.message.lower())
        self.assertIsNone(result.reminder)


class CoveUiSourceTest(unittest.TestCase):
    def test_no_miss_check_no_jessica(self) -> None:
        source = Path(ui_app.__file__).read_text(encoding="utf-8")
        self.assertNotIn("MISS CHECK", source)
        self.assertNotIn("Jessica", source)

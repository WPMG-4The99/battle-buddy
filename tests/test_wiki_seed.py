"""New-game wiki seed. Mock search+fetch. No Google account. No keys."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from battlebuddy.databank.fetch import FetchResult
from battlebuddy.databank.seed import (
    _SEARCH,
    looks_like_wiki_url,
    needs_wiki_seed,
    parse_ddg_links,
    pick_wiki_urls,
    seed_done_line,
    seed_fail_line,
    seed_hold_line,
    seed_new_game,
)
from battlebuddy.databank.store import DatabankStore
from battlebuddy.ui import app as ui_app


_DDG = """
<html><body>
<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fvalheim.fandom.com%2Fwiki%2FValheim_Wiki">Valheim Wiki</a>
<a href="https://valheim.fandom.com/wiki/Building">Building</a>
<a href="https://en.wikipedia.org/wiki/Valheim">Wikipedia</a>
<a href="https://store.steampowered.com/app/892970/Valheim/">Steam</a>
<a href="https://www.google.com/search?q=valheim">Google</a>
<a href="https://valheim.fandom.com/login">Login</a>
<a href="https://example.com/store/buy">Store</a>
<a href="https://random-site.com/blog">Blog</a>
</body></html>
"""


class WikiUrlFilterTest(unittest.TestCase):
    def test_keeps_wiki_fandom_skips_steam_store_login(self) -> None:
        self.assertTrue(looks_like_wiki_url("https://valheim.fandom.com/wiki/Valheim_Wiki"))
        self.assertTrue(looks_like_wiki_url("https://en.wikipedia.org/wiki/Valheim"))
        self.assertTrue(looks_like_wiki_url("https://wiki.hoodedhorse.com/Manor_Lords/"))
        self.assertTrue(looks_like_wiki_url("https://example.wiki/Valheim"))
        self.assertFalse(looks_like_wiki_url("https://store.steampowered.com/app/892970"))
        self.assertFalse(looks_like_wiki_url("https://steamcommunity.com/app/892970"))
        self.assertFalse(looks_like_wiki_url("https://valheim.fandom.com/login"))
        self.assertFalse(looks_like_wiki_url("https://example.com/store/buy"))
        self.assertFalse(looks_like_wiki_url("https://www.google.com/search?q=valheim"))


class DdgParseTest(unittest.TestCase):
    def test_unwraps_uddg_and_picks_top_three_wikis(self) -> None:
        raw = parse_ddg_links(_DDG)
        picked = pick_wiki_urls(raw)
        self.assertEqual(len(picked), 3)
        self.assertEqual(picked[0], "https://valheim.fandom.com/wiki/Valheim_Wiki")
        self.assertIn("https://valheim.fandom.com/wiki/Building", picked)
        self.assertIn("https://en.wikipedia.org/wiki/Valheim", picked)
        joined = " ".join(picked)
        self.assertNotIn("steampowered", joined)
        self.assertNotIn("google.com", joined)
        self.assertNotIn("/login", joined)


class SeedNewGameTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = DatabankStore(Path(self.tmp.name))
        self.urls = [
            "https://valheim.fandom.com/wiki/Valheim_Wiki",
            "https://valheim.fandom.com/wiki/Building",
            "https://en.wikipedia.org/wiki/Valheim",
        ]

    def _ok(self, game: str | None, url: str) -> FetchResult:
        title = url.rsplit("/", 1)[-1]
        self.store.save_page(game, url, title, f"{title} body")
        return FetchResult(ok=True, url=url, message="Saved on disk.", title=title, text=f"{title} body")

    def test_empty_folder_searches_and_saves_three_pages(self) -> None:
        self.assertTrue(needs_wiki_seed(self.store, "Valheim"))
        with patch("battlebuddy.databank.seed.search_wiki_urls", return_value=self.urls) as search, patch(
            "battlebuddy.databank.store.DatabankStore.add_url",
            side_effect=self._ok,
        ) as add:
            result = seed_new_game(self.store, "Valheim")
        search.assert_called_once_with("Valheim")
        self.assertEqual(add.call_count, 3)
        self.assertTrue(result.started)
        self.assertEqual(result.saved, 3)
        self.assertEqual(len(self.store.list_sources("Valheim")), 3)
        self.assertEqual(result.message, seed_done_line("Valheim", 3))

    def test_pages_already_on_disk_do_not_search(self) -> None:
        self.store.save_page(
            "Manor Lords",
            "https://wiki.hoodedhorse.com/Manor_Lords/Food",
            "Food",
            "Check the granary.",
        )
        self.assertFalse(needs_wiki_seed(self.store, "Manor Lords"))
        with patch("battlebuddy.databank.seed.search_wiki_urls") as search:
            result = seed_new_game(self.store, "Manor Lords")
        search.assert_not_called()
        self.assertFalse(result.started)
        self.assertEqual(len(self.store.list_sources("Manor Lords")), 1)

    def test_offline_search_says_could_not_reach(self) -> None:
        with patch("battlebuddy.databank.seed.search_wiki_urls", return_value=None):
            result = seed_new_game(self.store, "Valheim")
        self.assertTrue(result.started)
        self.assertEqual(result.saved, 0)
        self.assertEqual(result.message, seed_fail_line())
        self.assertEqual(self.store.list_sources("Valheim"), [])


class SeedSourceLawTest(unittest.TestCase):
    def test_no_google_no_keys_no_openai(self) -> None:
        seed = Path(__file__).resolve().parents[1] / "battlebuddy" / "databank" / "seed.py"
        text = seed.read_text(encoding="utf-8")
        self.assertIn("html.duckduckgo.com/html", text)
        self.assertEqual(_SEARCH, "https://html.duckduckgo.com/html/")
        self.assertNotIn("google.com/search", text)
        self.assertNotIn("googleapis", text)
        self.assertNotIn("openai", text.lower())
        self.assertNotIn("api_key", text.lower())
        self.assertNotIn("oauth", text.lower())
        ui = Path(ui_app.__file__).read_text(encoding="utf-8")
        self.assertIn("Hold the line. Fetching wiki pages", text)
        self.assertIn("seed_hold_line", ui)
        self.assertIn("_maybe_seed_wiki", ui)
        self.assertIn("seed_new_game", ui)
        self.assertNotIn("google.com/search", ui)
        self.assertNotIn("openai", ui.lower())


class SeedUiTest(unittest.TestCase):
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

    def test_first_detect_empty_folder_starts_seed(self) -> None:
        app = self._app()
        try:
            started: list[str | None] = []
            app._start_wiki_seed = started.append  # type: ignore[method-assign]
            reminder = str(app.status.cget("text"))
            app._apply_game("Valheim")
            note = seed_hold_line("Valheim")
            self.assertEqual(started, ["Valheim"])
            self.assertEqual(app.ask_out.get("1.0", "end-1c"), note)
            self.assertEqual(str(app.databank_status.cget("text")), note)
            self.assertEqual(str(app.status.cget("text")), reminder)
            self.assertEqual(app._game_name, "Valheim")
        finally:
            app._on_close()

    def test_second_detect_with_pages_does_not_search(self) -> None:
        store = DatabankStore(self.home)
        store.save_page(
            "Manor Lords",
            "https://wiki.hoodedhorse.com/Manor_Lords/Food",
            "Food",
            "Check the granary.",
        )
        app = self._app()
        try:
            started: list[str | None] = []
            app._start_wiki_seed = started.append  # type: ignore[method-assign]
            with patch("battlebuddy.databank.seed.search_wiki_urls") as search:
                app._apply_game("Manor Lords")
                app._apply_game("Manor Lords")
                search.assert_not_called()
            self.assertEqual(started, [])
            self.assertEqual(app._game_name, "Manor Lords")
        finally:
            app._on_close()

    def test_seed_done_files_pages_and_keeps_reminders(self) -> None:
        app = self._app()
        try:
            urls = [
                "https://valheim.fandom.com/wiki/Valheim_Wiki",
                "https://valheim.fandom.com/wiki/Building",
                "https://en.wikipedia.org/wiki/Valheim",
            ]

            def _ok(game: str | None, url: str) -> FetchResult:
                title = url.rsplit("/", 1)[-1]
                app.databank.save_page(game, url, title, f"{title} body")
                return FetchResult(ok=True, url=url, message="ok", title=title, text="body")

            reminder = str(app.status.cget("text"))
            app._start_wiki_seed = lambda _game: None  # type: ignore[method-assign]
            with patch("battlebuddy.databank.seed.search_wiki_urls", return_value=urls), patch(
                "battlebuddy.databank.store.DatabankStore.add_url",
                side_effect=_ok,
            ):
                app._apply_game("Valheim")
                self.assertIn("Hold the line. Fetching wiki pages for Valheim", app.ask_out.get("1.0", "end-1c"))
                result = seed_new_game(app.databank, "Valheim")
                app._seed_done(result, "Valheim")
            self.assertEqual(result.saved, 3)
            self.assertEqual(len(app.databank.list_sources("Valheim")), 3)
            self.assertEqual(app.ask_out.get("1.0", "end-1c"), seed_done_line("Valheim", 3))
            self.assertEqual(str(app.status.cget("text")), reminder)
        finally:
            app._on_close()


if __name__ == "__main__":
    unittest.main()

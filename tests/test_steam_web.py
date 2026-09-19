"""Optional Steam Web API for AppID 1368140. Mock HTTP. Unset key skips."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from battlebuddy.memory.store import MemoryStore
from battlebuddy.reminders.commands import run_line
from battlebuddy.reminders.engine import ReminderEngine
from battlebuddy.steam import web
from battlebuddy.steam.web import fetch_cove_web, steamid_from_path, web_api_key
from battlebuddy.ui import app as ui_app


class SteamWebSkipTest(unittest.TestCase):
    def setUp(self) -> None:
        self._old = os.environ.get("STEAM_WEB_API_KEY")
        os.environ.pop("STEAM_WEB_API_KEY", None)

    def tearDown(self) -> None:
        if self._old is None:
            os.environ.pop("STEAM_WEB_API_KEY", None)
        else:
            os.environ["STEAM_WEB_API_KEY"] = self._old

    def test_unset_key_skips_http(self) -> None:
        called: list[str] = []

        def getter(url: str) -> dict:
            called.append(url)
            return {}

        snap = fetch_cove_web(get_json=getter)
        self.assertIsNone(web_api_key())
        self.assertEqual(snap.state, "dark")
        self.assertIsNone(snap.news)
        self.assertEqual(called, [])

    def test_wrong_appid_skips(self) -> None:
        os.environ["STEAM_WEB_API_KEY"] = "test-key"
        called: list[str] = []
        snap = fetch_cove_web(appid="570", get_json=lambda url: called.append(url) or {})
        self.assertEqual(snap.state, "dark")
        self.assertEqual(called, [])


class SteamWebFetchTest(unittest.TestCase):
    def setUp(self) -> None:
        self._old = os.environ.get("STEAM_WEB_API_KEY")
        os.environ["STEAM_WEB_API_KEY"] = "test-key"

    def tearDown(self) -> None:
        if self._old is None:
            os.environ.pop("STEAM_WEB_API_KEY", None)
        else:
            os.environ["STEAM_WEB_API_KEY"] = self._old

    def test_news_schema_owned_cove_only(self) -> None:
        urls: list[str] = []

        def getter(url: str) -> dict:
            urls.append(url)
            if "ISteamNews" in url:
                return {
                    "appnews": {
                        "appid": 1368140,
                        "newsitems": [{"title": "Patch notes"}],
                    }
                }
            if "GetSchemaForGame" in url:
                return {
                    "game": {
                        "availableGameStats": {
                            "achievements": [{"name": "a"}, {"name": "b"}]
                        }
                    }
                }
            if "GetOwnedGames" in url:
                return {"response": {"games": [{"appid": 1368140}]}}
            return {}

        snap = fetch_cove_web(steamid="76561198000000000", get_json=getter)
        self.assertEqual(snap.state, "live")
        self.assertEqual(snap.news, "Patch notes")
        self.assertEqual(snap.achievements, 2)
        self.assertTrue(snap.owned)
        joined = " ".join(urls)
        self.assertIn("1368140", joined)
        self.assertNotIn("appid=570", joined)
        self.assertTrue(all(item.startswith("https://api.steampowered.com/") for item in urls))
        self.assertEqual(len(urls), 3)

    def test_steamid_from_save_path(self) -> None:
        path = r"C:\Users\x\AppData\Local\CorsairCove\Saved\SaveGames\SteamMain_76561198000000000\AutoSave 02.ccgs"
        self.assertEqual(steamid_from_path(path), "76561198000000000")


class SteamWebHarvestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.home = Path(self.tmp.name)
        self._old = {
            "BATTLEBUDDY_HOME": os.environ.get("BATTLEBUDDY_HOME"),
            "STEAM_WEB_API_KEY": os.environ.get("STEAM_WEB_API_KEY"),
            "XAI_API_KEY": os.environ.get("XAI_API_KEY"),
        }
        os.environ["BATTLEBUDDY_HOME"] = str(self.home)
        os.environ["STEAM_WEB_API_KEY"] = "test-key"
        os.environ.pop("XAI_API_KEY", None)
        self.addCleanup(self._restore)
        self.engine = ReminderEngine(MemoryStore(self.home / "memory.json"))

    def _restore(self) -> None:
        self.tmp.cleanup()
        for key, value in self._old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_harvest_writes_news_not_key(self) -> None:
        def getter(url: str) -> dict:
            if "ISteamNews" in url:
                return {
                    "appnews": {"newsitems": [{"title": "Cove patch"}]}
                }
            if "GetSchemaForGame" in url:
                return {"game": {"availableGameStats": {"achievements": [{}]}}}
            return {}

        with patch("battlebuddy.steam.web._get_json", side_effect=getter):
            result = run_line(self.engine, "harvest")
        self.assertTrue(result.ok)
        self.assertIn("Cove patch", result.message)
        blob = json.loads((self.home / "harvest.json").read_text(encoding="utf-8"))
        self.assertEqual(blob["news"], "Cove patch")
        self.assertEqual(blob["web"], "live")
        packed = json.dumps(blob)
        self.assertNotIn("test-key", packed)
        self.assertNotIn("STEAM_WEB_API_KEY", packed)

    def test_http_fail_does_not_block(self) -> None:
        with patch("battlebuddy.steam.web._get_json", return_value=None):
            result = run_line(self.engine, "harvest")
        self.assertTrue(result.ok)
        self.assertIn("Corsair Cove", result.message)
        blob = json.loads((self.home / "harvest.json").read_text(encoding="utf-8"))
        self.assertEqual(blob.get("web"), "dark")


class SteamWebSourceTest(unittest.TestCase):
    def test_no_ui_field_https_only(self) -> None:
        ui = Path(ui_app.__file__).read_text(encoding="utf-8")
        self.assertNotIn("STEAM_WEB_API_KEY", ui)
        self.assertNotIn("password", ui.lower())
        src = Path(web.__file__).read_text(encoding="utf-8")
        self.assertIn("STEAM_WEB_API_KEY", src)
        self.assertIn("api.steampowered.com", src)
        self.assertIn("1368140", src)
        self.assertNotIn("http://api.steampowered.com", src)


if __name__ == "__main__":
    unittest.main()

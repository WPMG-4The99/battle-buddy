"""ASK hunts the detected game wiki. Local server only. No live wiki."""

from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from battlebuddy.databank.search import ask_pages
from battlebuddy.databank.store import DatabankStore
from battlebuddy.databank.wiki import (
    KNOWN_WIKIS,
    ask_or_hunt,
    infer_wiki_from_url,
    wiki_home_for,
)


class WikiHomeTest(unittest.TestCase):
    def test_manor_lords_known_home(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DatabankStore(Path(tmp.name))
        home = wiki_home_for("Manor Lords", store)
        assert home is not None
        self.assertEqual(home.origin, "https://wiki.hoodedhorse.com")
        self.assertEqual(home.api, "https://wiki.hoodedhorse.com/Manor_Lords/api.php")
        self.assertEqual(home.article_base, "https://wiki.hoodedhorse.com/Manor_Lords/")
        self.assertIn("rimworld", KNOWN_WIKIS)
        self.assertIn("valheim", KNOWN_WIKIS)

    def test_infers_script_path_from_saved_url(self) -> None:
        home = infer_wiki_from_url("https://wiki.hoodedhorse.com/Manor_Lords/Food")
        assert home is not None
        self.assertEqual(home.api, "https://wiki.hoodedhorse.com/Manor_Lords/api.php")
        self.assertEqual(home.article_base, "https://wiki.hoodedhorse.com/Manor_Lords/")

    def test_unknown_game_empty_folder_has_no_wiki(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DatabankStore(Path(tmp.name))
        self.assertIsNone(wiki_home_for(None, store))
        self.assertIsNone(wiki_home_for("Some Mod Game", store))

    def test_saved_localhost_wiki_beats_known_live_home(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DatabankStore(Path(tmp.name))
        store.save_page(
            "Manor Lords",
            "http://127.0.0.1:9/wiki/",
            "Manor Lords Wiki",
            "Welcome. Start production with ale.",
        )
        home = wiki_home_for("Manor Lords", store)
        assert home is not None
        self.assertEqual(home.origin, "http://127.0.0.1:9")
        self.assertEqual(home.api, "http://127.0.0.1:9/api.php")
        self.assertEqual(home.article_base, "http://127.0.0.1:9/wiki/")


class WikiHuntHttpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.hits: list[str] = []
        handler = _make_handler(self.hits)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address[:2]
        self.base = f"http://{host}:{port}"
        self.addCleanup(self._stop_server)
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = DatabankStore(Path(self.tmp.name))

    def _stop_server(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def _save_homepage(self) -> None:
        self.store.save_page(
            "Manor Lords",
            f"{self.base}/wiki/",
            "Manor Lords Wiki",
            "Welcome. Start production with ale. Baron Hildebolt holds the manor.",
        )

    def test_homepage_dump_hunts_warfare_and_shows_spear(self) -> None:
        self._save_homepage()
        local = ask_pages(self.store, "Manor Lords", "How do I start a spear production?")
        self.assertEqual(local.hits, ())
        self.assertNotIn("spear", local.output().lower())
        result = ask_or_hunt(self.store, "Manor Lords", "How do I start a spear production?")
        blob = result.output().lower()
        self.assertTrue(result.hits)
        self.assertIn("spear", blob)
        self.assertNotIn("ale", blob)
        self.assertNotIn("hildebolt", blob)
        urls = [item.url for item in self.store.list_sources("Manor Lords")]
        self.assertTrue(any(item.endswith("/wiki/Warfare") for item in urls))
        self.assertTrue(any("/api.php" in path for path in self.hits))
        self.assertTrue(any("srwhat=text" in path for path in self.hits))

    def test_local_spear_page_does_not_hunt(self) -> None:
        self.store.save_page(
            "Manor Lords",
            f"{self.base}/wiki/Spear",
            "Spear",
            "A spear is a hunting weapon. Craft a spear at the smithy.",
        )
        with patch("battlebuddy.databank.fetch.fetch_page") as fetch:
            with patch("battlebuddy.databank.wiki.search_wiki_urls") as hunt:
                result = ask_or_hunt(
                    self.store,
                    "Manor Lords",
                    "How do I start a spear production?",
                )
        fetch.assert_not_called()
        hunt.assert_not_called()
        self.assertIn("spear", result.output().lower())
        self.assertEqual(self.hits, [])

    def test_unknown_game_empty_folder_does_not_network(self) -> None:
        with patch("battlebuddy.databank.fetch.fetch_page") as fetch:
            result = ask_or_hunt(self.store, None, "How do I start a spear production?")
        fetch.assert_not_called()
        self.assertTrue(result.empty)
        self.assertIn("ADD / FETCH", result.message)
        self.assertEqual(self.hits, [])

    def test_hunt_miss_does_not_invent(self) -> None:
        self._save_homepage()
        result = ask_or_hunt(self.store, "Manor Lords", "how do nuclear reactors work")
        self.assertEqual(result.hits, ())
        self.assertIn("Nothing invented.", result.output())
        self.assertIn("No match on the wiki", result.output())
        self.assertNotIn("reactor", result.output().lower())
        self.assertNotIn("ale", result.output().lower())
        urls = [item.url for item in self.store.list_sources("Manor Lords")]
        self.assertFalse(any("Warfare" in item for item in urls))

    def test_off_host_search_hit_is_ignored(self) -> None:
        self._save_homepage()
        self.server.RequestHandlerClass = _make_handler(self.hits, off_host=True)
        result = ask_or_hunt(self.store, "Manor Lords", "How do I start a spear production?")
        self.assertEqual(result.hits, ())
        self.assertIn("Nothing invented.", result.output())
        self.assertNotIn("spear", result.output().lower())
        urls = [item.url for item in self.store.list_sources("Manor Lords")]
        self.assertFalse(any("evil" in item for item in urls))
        self.assertFalse(any(item.endswith("/wiki/Warfare") for item in urls))
        self.assertFalse(any(path.startswith("/wiki/Warfare") for path in self.hits))

    def test_missing_api_falls_back_to_title_case(self) -> None:
        self._save_homepage()
        self.server.RequestHandlerClass = _make_handler(self.hits, no_api=True)
        result = ask_or_hunt(self.store, "Manor Lords", "How do I start a spear production?")
        self.assertIn("spear", result.output().lower())
        urls = [item.url for item in self.store.list_sources("Manor Lords")]
        self.assertTrue(any(item.endswith("/wiki/Spear") for item in urls))


def _make_handler(hits: list[str], off_host: bool = False, no_api: bool = False):
    class _WikiHuntHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
            hits.append(self.path)
            parsed = urlparse(self.path)
            if parsed.path == "/api.php":
                if no_api:
                    self.send_response(404)
                    self.end_headers()
                    return
                self._api(parsed.query)
                return
            if parsed.path == "/wiki/Spear":
                body = (
                    b"<html><head><title>Spear</title></head><body>"
                    b"<p>Make a spear at the blacksmith. You need an iron slab and planks.</p>"
                    b"</body></html>"
                )
                self._ok(body, "text/html; charset=utf-8")
                return
            if parsed.path == "/wiki/Warfare":
                body = (
                    b"<html><head><title>Warfare</title></head><body>"
                    b"<h1>Warfare</h1>"
                    b"<p>Make a spear at the blacksmith. You need an iron slab and planks.</p>"
                    b"</body></html>"
                )
                self._ok(body, "text/html; charset=utf-8")
                return
            if parsed.path in {"/wiki/", "/wiki"}:
                body = (
                    b"<html><head><title>Manor Lords Wiki</title></head><body>"
                    b"<p>Welcome. Start production with ale.</p>"
                    b"</body></html>"
                )
                self._ok(body, "text/html; charset=utf-8")
                return
            self.send_response(404)
            self.end_headers()

        def _api(self, query: str) -> None:
            qs = parse_qs(query)
            search = (qs.get("srsearch") or [""])[0].lower()
            what = (qs.get("srwhat") or [""])[0]
            if what != "text" or "spear" not in search:
                payload = {"query": {"search": []}}
                self._ok(json.dumps(payload).encode("utf-8"), "application/json")
                return
            if off_host:
                payload = {
                    "query": {
                        "search": [
                            {
                                "title": "Warfare",
                                "fullurl": "https://evil.example/wiki/Warfare",
                            }
                        ]
                    }
                }
            else:
                payload = {"query": {"search": [{"title": "Warfare"}]}}
            self._ok(json.dumps(payload).encode("utf-8"), "application/json")

        def _ok(self, body: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return _WikiHuntHandler


if __name__ == "__main__":
    unittest.main()

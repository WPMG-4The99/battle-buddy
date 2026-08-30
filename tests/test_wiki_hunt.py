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
    fallback_title_urls,
    infer_wiki_from_url,
    rank_search_hits,
    search_variants,
    wiki_home_for,
    wiki_homes_for,
    SearchHit,
)


_SPEAR_Q = "How do I start a spear production?"
_RECIPE = "Spears: obtained from Planks and Iron Slabs at the Blacksmith's Workshop backyard extension."
# Live Approval/Warfare: spear + sidebar blacksmith. iron=0, obtained=0. Not a recipe.
_APPROVAL = (
    "Spear Militia unlocks with an Approval perk. "
    "See also: Blacksmith, Warfare. "
    "Higher approval gives more militia."
)
_WARFARE = (
    "Spear Militia is a unit in the warfare table. "
    "See also: Blacksmith, Burgage Plot, Approval. "
    "The barracks lists spear, bow, and polearm militia. "
    "Related pages: Blacksmith, Militia, Retinue. "
    "Higher approval gives more militia."
)
_LOCAL_RECIPE = (
    "Spears are obtained from planks at the Blacksmith's Workshop backyard extension."
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
        homes = wiki_homes_for("Manor Lords", store)
        self.assertEqual([item.origin for item in homes], ["http://127.0.0.1:9"])


class RankVariantTest(unittest.TestCase):
    def test_search_variants_are_singular_and_plural(self) -> None:
        self.assertEqual(search_variants(["spear"]), ["spear", "spears"])
        self.assertEqual(search_variants(["spears"]), ["spears", "spear"])

    def test_claim_title_fallbacks_when_spoken_ruler_words(self) -> None:
        home = KNOWN_WIKIS["manor lords"]
        urls = fallback_title_urls(home, ["defeat", "ruler"])
        joined = " ".join(urls)
        self.assertIn("/FAQ", joined)
        self.assertIn("Game_setup", joined)
        self.assertIn("/Warfare", joined)
        self.assertIn("/Regions", joined)
        spear = " ".join(fallback_title_urls(home, ["spear"]))
        self.assertNotIn("/FAQ", spear)
        self.assertNotIn("Game_setup", spear)

    def test_livestock_title_fallbacks_when_spoken_animal_words(self) -> None:
        home = KNOWN_WIKIS["manor lords"]
        urls = fallback_title_urls(home, ["livestock", "burgage"])
        joined = " ".join(urls)
        self.assertIn("Burgage_plot", joined)
        self.assertIn("/Buildings", joined)
        self.assertIn("Livestock_trading_post", joined)
        goat = " ".join(fallback_title_urls(home, ["goat", "pig"]))
        self.assertIn("Burgage_plot", goat)
        self.assertIn("Livestock_trading_post", goat)
        spear = " ".join(fallback_title_urls(home, ["spear"]))
        self.assertNotIn("Burgage_plot", spear)
        self.assertNotIn("Livestock_trading_post", spear)

    def test_pack_title_fallbacks_when_spoken_pack_words(self) -> None:
        home = KNOWN_WIKIS["manor lords"]
        urls = fallback_title_urls(home, ["pack", "routes"])
        joined = " ".join(urls)
        self.assertIn("Pack_station", joined)
        self.assertIn("/Buildings", joined)
        self.assertIn("/FAQ", joined)
        mule = " ".join(fallback_title_urls(home, ["mule"]))
        self.assertIn("Pack_station", mule)
        self.assertIn("/FAQ", mule)
        spear = " ".join(fallback_title_urls(home, ["spear"]))
        self.assertNotIn("Pack_station", spear)

    def test_military_items_outranks_translation_and_approval(self) -> None:
        hits = [
            SearchHit("Approval", "Spear Militia unlocks with an Approval perk.", "https://w/Approval"),
            SearchHit("Warfare/nl", "Spear Militia is a unit.", "https://w/Warfare/nl"),
            SearchHit(
                "Military items",
                "Spears: obtained from Planks and Iron Slabs at the Blacksmith's Workshop.",
                "https://w/Military_items",
            ),
        ]
        ranked = rank_search_hits(hits, ["spear", "spears"])
        self.assertEqual(ranked[0].title, "Military items")
        self.assertNotEqual(ranked[0].title, "Warfare/nl")
        self.assertNotEqual(ranked[0].title, "Approval")


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

    def _searches(self) -> list[str]:
        found: list[str] = []
        for path in self.hits:
            parsed = urlparse(path)
            if parsed.path != "/api.php":
                continue
            qs = parse_qs(parsed.query)
            found.append((qs.get("srsearch") or [""])[0])
        return found

    def test_spear_production_saves_military_items_not_approval(self) -> None:
        self._save_homepage()
        local = ask_pages(self.store, "Manor Lords", _SPEAR_Q)
        self.assertEqual(local.hits, ())
        self.assertNotIn("spear", local.output().lower())
        result = ask_or_hunt(self.store, "Manor Lords", _SPEAR_Q)
        blob = result.output().lower()
        self.assertTrue(result.hits)
        self.assertIn("spear", blob)
        self.assertIn("plank", blob)
        self.assertIn("iron", blob)
        self.assertIn("blacksmith", blob)
        self.assertIn("obtained", blob)
        self.assertNotIn("ale", blob)
        self.assertNotIn("hildebolt", blob)
        self.assertFalse(blob.lstrip().startswith("approval"))
        self.assertIn("military", result.hits[0].title.lower())
        self.assertNotIn("approval", result.hits[0].title.lower())
        self.assertIn("obtained", result.hits[0].snippet.lower())
        self.assertIn("blacksmith", result.hits[0].snippet.lower())
        urls = [item.url for item in self.store.list_sources("Manor Lords")]
        self.assertTrue(any(item.endswith("/wiki/Military_items") for item in urls))
        searches = self._searches()
        self.assertIn("spear", searches)
        self.assertIn("spears", searches)
        self.assertFalse(any("production" in item for item in searches))
        self.assertTrue(any("/api.php" in path for path in self.hits))
        self.assertTrue(any("srwhat=text" in path for path in self.hits))

    def test_weak_local_warfare_does_not_block_hunt(self) -> None:
        self._save_homepage()
        self.store.save_page(
            "Manor Lords",
            f"{self.base}/wiki/Warfare",
            "Warfare",
            _WARFARE,
        )
        weak = ask_pages(self.store, "Manor Lords", _SPEAR_Q)
        self.assertTrue(weak.hits)
        weak_blob = " ".join(f"{hit.title} {hit.snippet}" for hit in weak.hits).lower()
        self.assertIn("spear", weak_blob)
        self.assertIn("blacksmith", weak_blob)
        self.assertNotIn("obtained", weak.output().lower())
        self.assertNotIn("blacksmiths workshop", weak.output().lower().replace("'", ""))
        self.assertNotIn("backyard", weak.output().lower())
        result = ask_or_hunt(self.store, "Manor Lords", _SPEAR_Q)
        blob = result.output().lower()
        self.assertIn("spear", blob)
        self.assertIn("plank", blob)
        self.assertIn("iron", blob)
        self.assertIn("blacksmith", blob)
        self.assertIn("obtained", blob)
        self.assertFalse(blob.lstrip().startswith("approval"))
        self.assertIn("military", result.hits[0].title.lower())
        self.assertIn("obtained", result.hits[0].snippet.lower())
        self.assertTrue(any("srsearch=spears" in path for path in self.hits))

    def test_live_shaped_militia_sidebar_blacksmith_still_hunts_recipe(self) -> None:
        self._save_homepage()
        self.store.save_page(
            "Manor Lords",
            f"{self.base}/wiki/Approval",
            "Approval",
            _APPROVAL,
        )
        self.store.save_page(
            "Manor Lords",
            f"{self.base}/wiki/Warfare",
            "Warfare",
            _WARFARE,
        )
        self.store.save_page(
            "Manor Lords",
            f"{self.base}/wiki/Warfare/nl",
            "Warfare/nl",
            _WARFARE,
        )
        local = ask_pages(self.store, "Manor Lords", _SPEAR_Q)
        self.assertTrue(local.hits)
        local_blob = " ".join(f"{hit.title} {hit.snippet}" for hit in local.hits).lower()
        self.assertIn("spear", local_blob)
        self.assertIn("blacksmith", local_blob)
        self.assertNotIn("obtained", local.output().lower())
        self.assertNotIn("iron", local.output().lower())
        titles = {hit.title.lower() for hit in local.hits}
        self.assertTrue(titles & {"approval", "warfare", "warfare/nl"})
        result = ask_or_hunt(self.store, "Manor Lords", _SPEAR_Q)
        blob = result.output().lower()
        self.assertIn("spear", blob)
        self.assertIn("plank", blob)
        self.assertIn("iron", blob)
        self.assertIn("blacksmith", blob)
        self.assertIn("obtained", blob)
        self.assertFalse(blob.lstrip().startswith("approval"))
        self.assertIn("military", result.hits[0].title.lower())
        self.assertIn("obtained", result.hits[0].snippet.lower())
        self.assertIn("blacksmith", result.hits[0].snippet.lower())
        self.assertTrue(any(item.endswith("/wiki/Military_items") for item in [
            source.url for source in self.store.list_sources("Manor Lords")
        ]))
        self.assertTrue(any("srsearch=spears" in path for path in self.hits))

    def test_local_military_items_recipe_does_not_network(self) -> None:
        self.store.save_page(
            "Manor Lords",
            f"{self.base}/wiki/Military_items",
            "Military items",
            _RECIPE,
        )
        with patch("battlebuddy.databank.fetch.fetch_page") as fetch:
            with patch("battlebuddy.databank.wiki.search_wiki_urls") as hunt:
                result = ask_or_hunt(self.store, "Manor Lords", _SPEAR_Q)
        fetch.assert_not_called()
        hunt.assert_not_called()
        blob = result.output().lower()
        self.assertIn("spear", blob)
        self.assertIn("plank", blob)
        self.assertIn("iron", blob)
        self.assertIn("blacksmith", blob)
        self.assertFalse(blob.lstrip().startswith("approval"))
        self.assertEqual(self.hits, [])

    def test_local_spear_page_does_not_hunt(self) -> None:
        self.store.save_page(
            "Manor Lords",
            f"{self.base}/wiki/Spear",
            "Spear",
            _LOCAL_RECIPE,
        )
        with patch("battlebuddy.databank.fetch.fetch_page") as fetch:
            with patch("battlebuddy.databank.wiki.search_wiki_urls") as hunt:
                result = ask_or_hunt(
                    self.store,
                    "Manor Lords",
                    _SPEAR_Q,
                )
        fetch.assert_not_called()
        hunt.assert_not_called()
        self.assertIn("spear", result.output().lower())
        self.assertEqual(self.hits, [])

    def test_translation_warfare_nl_is_not_preferred(self) -> None:
        self._save_homepage()
        self.server.RequestHandlerClass = _make_handler(self.hits, include_nl=True)
        result = ask_or_hunt(self.store, "Manor Lords", _SPEAR_Q)
        blob = result.output().lower()
        self.assertIn("spear", blob)
        self.assertIn("blacksmith", blob)
        self.assertIn("military", result.hits[0].title.lower())
        self.assertFalse(any("/nl" in hit.title.lower() for hit in result.hits))
        urls = [item.url for item in self.store.list_sources("Manor Lords")]
        self.assertTrue(any(item.endswith("/wiki/Military_items") for item in urls))

    def test_unknown_game_empty_folder_does_not_network(self) -> None:
        with patch("battlebuddy.databank.fetch.fetch_page") as fetch:
            result = ask_or_hunt(self.store, None, _SPEAR_Q)
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
        self.assertFalse(any("Military" in item for item in urls))

    def test_off_host_search_hit_is_ignored(self) -> None:
        self._save_homepage()
        self.server.RequestHandlerClass = _make_handler(self.hits, off_host=True)
        result = ask_or_hunt(self.store, "Manor Lords", _SPEAR_Q)
        self.assertEqual(result.hits, ())
        self.assertIn("Nothing invented.", result.output())
        self.assertNotIn("spear", result.output().lower())
        urls = [item.url for item in self.store.list_sources("Manor Lords")]
        self.assertFalse(any("evil" in item for item in urls))
        self.assertFalse(any(item.endswith("/wiki/Warfare") for item in urls))
        self.assertFalse(any(item.endswith("/wiki/Military_items") for item in urls))
        self.assertFalse(any(path.startswith("/wiki/Warfare") for path in self.hits))
        self.assertFalse(any(path.startswith("/wiki/Military_items") for path in self.hits))

    def test_two_saved_origins_hunt_both_homes(self) -> None:
        official_hits: list[str] = []
        fandom_hits: list[str] = []
        official = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(official_hits))
        fandom = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(fandom_hits, off_host=True))
        threads = [
            threading.Thread(target=official.serve_forever, daemon=True),
            threading.Thread(target=fandom.serve_forever, daemon=True),
        ]
        for thread in threads:
            thread.start()
        self.addCleanup(official.shutdown)
        self.addCleanup(official.server_close)
        self.addCleanup(fandom.shutdown)
        self.addCleanup(fandom.server_close)
        official_base = f"http://{official.server_address[0]}:{official.server_address[1]}"
        fandom_base = f"http://{fandom.server_address[0]}:{fandom.server_address[1]}"
        self.store.save_page(
            "Manor Lords",
            f"{official_base}/wiki/",
            "Manor Lords Official Wiki",
            "Welcome to the official wiki.",
        )
        self.store.save_page(
            "Manor Lords",
            f"{fandom_base}/wiki/",
            "Manor Lords Wiki",
            "Welcome to the fandom wiki.",
        )
        homes = wiki_homes_for("Manor Lords", self.store)
        self.assertEqual({home.origin for home in homes}, {official_base, fandom_base})
        result = ask_or_hunt(self.store, "Manor Lords", _SPEAR_Q)
        blob = result.output().lower()
        self.assertIn("spear", blob)
        self.assertIn("plank", blob)
        self.assertIn("blacksmith", blob)
        self.assertIn("military", result.hits[0].title.lower())
        self.assertTrue(any("/api.php" in path for path in official_hits))
        self.assertTrue(any("/api.php" in path for path in fandom_hits))
        urls = [item.url for item in self.store.list_sources("Manor Lords")]
        self.assertTrue(any(item.startswith(official_base) and item.endswith("/wiki/Military_items") for item in urls))
        self.assertFalse(any("evil" in item for item in urls))

    def test_missing_api_falls_back_to_title_case(self) -> None:
        self._save_homepage()
        self.server.RequestHandlerClass = _make_handler(self.hits, no_api=True)
        result = ask_or_hunt(self.store, "Manor Lords", _SPEAR_Q)
        self.assertIn("spear", result.output().lower())
        urls = [item.url for item in self.store.list_sources("Manor Lords")]
        self.assertTrue(any(item.endswith("/wiki/Spear") for item in urls))


def _make_handler(
    hits: list[str],
    off_host: bool = False,
    no_api: bool = False,
    include_nl: bool = False,
):
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
            if parsed.path == "/wiki/Military_items":
                body = (
                    b"<html><head><title>Military items</title></head><body>"
                    b"<p>" + _RECIPE.encode("utf-8") + b"</p>"
                    b"</body></html>"
                )
                self._ok(body, "text/html; charset=utf-8")
                return
            if parsed.path == "/wiki/Approval":
                body = (
                    b"<html><head><title>Approval</title></head><body>"
                    b"<p>" + _APPROVAL.encode("utf-8") + b"</p>"
                    b"</body></html>"
                )
                self._ok(body, "text/html; charset=utf-8")
                return
            if parsed.path == "/wiki/Warfare":
                body = (
                    b"<html><head><title>Warfare</title></head><body>"
                    b"<h1>Warfare</h1>"
                    b"<p>" + _WARFARE.encode("utf-8") + b"</p>"
                    b"</body></html>"
                )
                self._ok(body, "text/html; charset=utf-8")
                return
            if parsed.path == "/wiki/Warfare/nl":
                body = (
                    b"<html><head><title>Warfare/nl</title></head><body>"
                    b"<p>" + _WARFARE.encode("utf-8") + b"</p>"
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
            search = (qs.get("srsearch") or [""])[0].lower().strip()
            what = (qs.get("srwhat") or [""])[0]
            if what != "text" or " " in search or "+" in search:
                payload = {"query": {"search": []}}
                self._ok(json.dumps(payload).encode("utf-8"), "application/json")
                return
            if search == "spears":
                rows = [
                    {
                        "title": "Military items",
                        "snippet": _RECIPE,
                    }
                ]
            elif search == "spear":
                rows = [
                    {"title": "Approval", "snippet": _APPROVAL},
                    {"title": "Warfare", "snippet": _WARFARE},
                ]
                if include_nl:
                    rows = [
                        {"title": "Approval", "snippet": _APPROVAL},
                        {"title": "Warfare/nl", "snippet": _WARFARE},
                    ]
            else:
                rows = []
            if off_host:
                rows = [
                    {
                        "title": row["title"],
                        "snippet": row["snippet"],
                        "fullurl": f"https://evil.example/wiki/{row['title'].replace(' ', '_')}",
                    }
                    for row in rows
                ]
            payload = {"query": {"search": rows}}
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

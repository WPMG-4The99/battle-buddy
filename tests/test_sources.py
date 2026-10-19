"""Per-game wiki hubs and live lookup. xAI and HTTP are mocked."""

from __future__ import annotations

import json
import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from battlebuddy.databank.fetch import FetchResult
from battlebuddy.sources import cache as source_cache
from battlebuddy.sources.cache import fetch_cached, prune_cache
from battlebuddy.sources.discover import discover_sources, maybe_discover, parse_source_list
from battlebuddy.sources.lookup import LOOKING_CUE, format_answer, live_lookup
from battlebuddy.sources.store import (
    WikiSource,
    add_source,
    allowed_hosts,
    load_sources,
    needs_discover,
    pin_source,
    ranked_sources,
    remove_source,
    save_sources,
    sources_path,
)
from battlebuddy.xai.loop import (
    MODEL,
    ChatOut,
    chat,
    chat_out,
    web_search_parameters,
    xai_model,
)


_STELLARIS_JSON = json.dumps(
    {
        "sources": [
            {
                "name": "Stellaris Wiki",
                "url": "https://stellaris.paradoxwikis.com",
                "search": "https://stellaris.paradoxwikis.com/index.php?search={q}",
            },
            {"name": "Stellaris Fandom", "url": "https://stellaris.fandom.com"},
        ]
    }
)


class StoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)

    def test_roundtrip_and_pin_ranks_first(self) -> None:
        self.assertTrue(needs_discover("Stellaris", self.home))
        save_sources(
            "Stellaris",
            [
                WikiSource("Stellaris Wiki", "https://stellaris.paradoxwikis.com"),
                WikiSource("Fandom", "https://stellaris.fandom.com", pinned=True),
            ],
            self.home,
        )
        self.assertFalse(needs_discover("Stellaris", self.home))
        ranked = ranked_sources("Stellaris", self.home)
        self.assertEqual(ranked[0].url, "https://stellaris.fandom.com")
        self.assertEqual(ranked[0].name, "Fandom")
        path = sources_path("Stellaris", self.home)
        self.assertEqual(path, self.home / "games" / "stellaris" / "sources.json")
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(raw["game"], "Stellaris")
        self.assertEqual(len(raw["sources"]), 2)

    def test_add_remove_pin(self) -> None:
        added = add_source("Bellwright", "https://bellwright.wiki.gg", home=self.home)
        assert added is not None
        self.assertEqual(load_sources("Bellwright", self.home)[0].url, added.url)
        self.assertTrue(pin_source("Bellwright", added.url, True, self.home))
        self.assertTrue(ranked_sources("Bellwright", self.home)[0].pinned)
        self.assertTrue(remove_source("Bellwright", added.url, self.home))
        self.assertEqual(load_sources("Bellwright", self.home), [])

    def test_hosts_cap_at_five_pinned_first(self) -> None:
        items = [
            WikiSource(f"W{i}", f"https://wiki{i}.example.wiki")
            for i in range(6)
        ]
        items[4] = WikiSource("Pinned", "https://palworld.wiki.gg", pinned=True)
        save_sources("Palworld", items, self.home)
        hosts = allowed_hosts("Palworld", self.home)
        self.assertEqual(hosts[0], "palworld.wiki.gg")
        self.assertEqual(len(hosts), 5)


class DiscoverTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self._old_key = os.environ.get("XAI_API_KEY")
        os.environ.pop("XAI_API_KEY", None)

    def tearDown(self) -> None:
        if self._old_key is None:
            os.environ.pop("XAI_API_KEY", None)
        else:
            os.environ["XAI_API_KEY"] = self._old_key

    def test_parse_json_and_citations(self) -> None:
        hubs = parse_source_list(
            _STELLARIS_JSON,
            ("https://store.steampowered.com/app/281990",),
            game="Stellaris",
        )
        urls = [item.url for item in hubs]
        self.assertIn("https://stellaris.paradoxwikis.com", urls)
        self.assertIn("https://stellaris.fandom.com", urls)
        self.assertNotIn("https://store.steampowered.com/app/281990", urls)

    def test_no_key_does_not_call_network(self) -> None:
        with patch("battlebuddy.sources.discover.chat_out") as mocked:
            found = discover_sources("Stellaris", home=self.home, key="")
        mocked.assert_not_called()
        self.assertEqual(found, [])
        self.assertTrue(needs_discover("Stellaris", self.home))

    def test_mocked_discover_saves_list_only(self) -> None:
        seen: dict[str, object] = {}

        def fake_chat(messages, *, key, timeout=12, max_tokens=500, search_parameters=None):
            seen["key"] = key
            seen["search"] = search_parameters
            seen["system"] = messages[0]["content"]
            return ChatOut(text=_STELLARIS_JSON, citations=())

        hubs = maybe_discover("Stellaris", self.home, key="test-key", chat_fn=fake_chat)
        self.assertEqual(len(hubs), 2)
        self.assertEqual(seen["key"], "test-key")
        params = seen["search"]
        assert isinstance(params, dict)
        source = params["sources"][0]
        self.assertEqual(source["type"], "web")
        self.assertIn("paradoxwikis.com", source["allowed_websites"])
        saved = load_sources("Stellaris", self.home)
        self.assertEqual(len(saved), 2)
        cache = self.home / "games" / "stellaris" / "cache"
        self.assertFalse(cache.exists())
        text = Path(__file__).resolve().parents[1].joinpath(
            "battlebuddy", "sources", "discover.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("fetch_page", text)
        self.assertIn("Hub or home URLs only", seen["system"])

    def test_existing_list_is_not_rediscovered(self) -> None:
        save_sources(
            "Bellwright",
            [WikiSource("Bellwright Wiki", "https://bellwright.wiki.gg")],
            self.home,
        )
        with patch("battlebuddy.sources.discover.chat_out") as mocked:
            hubs = maybe_discover("Bellwright", self.home, key="test-key")
        mocked.assert_not_called()
        self.assertEqual(hubs[0].url, "https://bellwright.wiki.gg")


class LookupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        save_sources(
            "Stellaris",
            [
                WikiSource(
                    "Stellaris Wiki",
                    "https://stellaris.paradoxwikis.com",
                    pinned=True,
                ),
                WikiSource("Fandom", "https://stellaris.fandom.com"),
            ],
            self.home,
        )

    def test_no_key_speaks_fallback(self) -> None:
        with patch("battlebuddy.sources.lookup.speak_async") as cue:
            looked = live_lookup(
                "What does Adaptive do?",
                "Stellaris",
                ocr="Adaptive trait picked.",
                home=self.home,
                key="",
                cue=True,
            )
        cue.assert_not_called()
        self.assertTrue(looked.local_only)
        self.assertIn("No Grok key", looked.notice)
        self.assertIn("No Grok key", looked.speak)
        self.assertIn("Adaptive", looked.answer)

    def test_live_search_fetches_and_shows_links(self) -> None:
        page_url = "https://stellaris.paradoxwikis.com/Traits"
        calls: list[object] = []

        def fake_chat(messages, *, key, timeout=12, max_tokens=280, search_parameters=None):
            calls.append(search_parameters)
            return ChatOut(
                text=json.dumps(
                    {
                        "answer": "Adaptive gives +10% habitability.",
                        "urls": [page_url],
                    }
                ),
                citations=(page_url,),
            )

        def fake_fetch(url: str) -> FetchResult:
            self.assertEqual(url, page_url)
            return FetchResult(
                ok=True,
                url=url,
                message="ok",
                title="Traits",
                text="Adaptive: +10% habitability.",
            )

        with patch("battlebuddy.sources.lookup.speak_async") as cue:
            looked = live_lookup(
                "What does Adaptive do?",
                "Stellaris",
                ocr="Adaptive",
                home=self.home,
                key="test-key",
                chat_fn=fake_chat,
                fetch_fn=fake_fetch,
                cue=True,
            )
        cue.assert_called_once_with(LOOKING_CUE)
        params = calls[0]
        assert isinstance(params, dict)
        allowed = params["sources"][0]["allowed_websites"]
        self.assertEqual(allowed[0], "stellaris.paradoxwikis.com")
        self.assertIn("Adaptive", looked.speak)
        self.assertIn(page_url, looked.answer)
        self.assertIn("Sources:", looked.answer)
        cached = self.home / "games" / "stellaris" / "cache"
        self.assertTrue(any(cached.glob("page-*.json")))

    def test_network_error_is_spoken(self) -> None:
        def fake_chat(*_a, **_k) -> ChatOut:
            return ChatOut(text=None, error="network")

        looked = live_lookup(
            "What is this event?",
            "Stellaris",
            ocr="The colony has grown.",
            home=self.home,
            key="test-key",
            chat_fn=fake_chat,
            cue=False,
        )
        self.assertTrue(looked.local_only)
        self.assertIn("Could not reach the wiki", looked.speak)
        self.assertIn("colony", looked.answer.lower())


class CacheTest(unittest.TestCase):
    def test_seven_day_prune(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            folder = source_cache.cache_dir("Palworld", home)
            folder.mkdir(parents=True)
            old = folder / "page-old.json"
            fresh = folder / "page-fresh.json"
            old.write_text("{}", encoding="utf-8")
            fresh.write_text("{}", encoding="utf-8")
            moment = time.time()
            os.utime(old, (moment - 8 * 86400, moment - 8 * 86400))
            os.utime(fresh, (moment, moment))
            self.assertEqual(prune_cache("Palworld", home, now=moment, keep_days=7), 1)
            self.assertFalse(old.exists())
            self.assertTrue(fresh.exists())

    def test_fetch_uses_cache_second_time(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            hits = {"n": 0}

            def fake_fetch(url: str) -> FetchResult:
                hits["n"] += 1
                return FetchResult(
                    ok=True,
                    url=url,
                    message="ok",
                    title="Bellwright",
                    text="Build a house.",
                )

            url = "https://bellwright.wiki.gg/wiki/Housing"
            first = fetch_cached(url, "Bellwright", home, fetch_fn=fake_fetch)
            second = fetch_cached(url, "Bellwright", home, fetch_fn=fake_fetch)
            self.assertTrue(first.ok)
            self.assertEqual(second.text, "Build a house.")
            self.assertEqual(hits["n"], 1)


class XaiSearchTest(unittest.TestCase):
    def test_model_env_and_search_payload(self) -> None:
        seen: dict[str, object] = {}

        class _Resp:
            def read(self, _n: int = -1) -> bytes:
                payload = {
                    "choices": [{"message": {"content": "ok"}}],
                    "citations": ["https://stellaris.paradoxwikis.com/Traits"],
                }
                return json.dumps(payload).encode("utf-8")

            def __enter__(self) -> "_Resp":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

        def fake_urlopen(req: object, timeout: object = None) -> _Resp:
            seen["body"] = json.loads(req.data.decode("utf-8"))  # type: ignore[union-attr]
            return _Resp()

        with patch.dict(os.environ, {"BATTLEBUDDY_XAI_MODEL": "grok-4"}):
            self.assertEqual(xai_model(), "grok-4")
            with patch("battlebuddy.xai.loop.urlopen", fake_urlopen):
                out = chat_out(
                    [{"role": "user", "content": "hi"}],
                    key="test-key",
                    search_parameters=web_search_parameters(["stellaris.paradoxwikis.com"]),
                )
        self.assertEqual(xai_model(), MODEL)
        self.assertEqual(out.text, "ok")
        self.assertTrue(out.citations[0].endswith("/Traits"))
        body = seen["body"]
        assert isinstance(body, dict)
        self.assertEqual(body["model"], "grok-4")
        self.assertEqual(body["search_parameters"]["mode"], "on")
        self.assertEqual(
            body["search_parameters"]["sources"][0]["allowed_websites"],
            ["stellaris.paradoxwikis.com"],
        )

    def test_chat_wraps_chat_out(self) -> None:
        with patch(
            "battlebuddy.xai.loop.chat_out",
            return_value=ChatOut(text="mapped"),
        ) as mocked:
            self.assertEqual(chat([{"role": "user", "content": "hi"}], key="k"), "mapped")
        mocked.assert_called()


class FormatAndUiTest(unittest.TestCase):
    def test_format_answer_puts_links_under_sources(self) -> None:
        shown = format_answer(
            "Adaptive gives habitability.",
            ["https://stellaris.paradoxwikis.com/Traits"],
            "",
        )
        self.assertTrue(shown.startswith("Adaptive"))
        self.assertIn("Sources:", shown)

    def test_ui_has_sources_controls_not_the_key(self) -> None:
        from battlebuddy.ui import app as ui_app
        from battlebuddy.snap import service as snap_service

        ui = Path(ui_app.__file__).read_text(encoding="utf-8")
        snap = Path(snap_service.__file__).read_text(encoding="utf-8")
        self.assertIn('text="Sources"', ui)
        self.assertIn('text="ADD"', ui)
        self.assertIn('text="REMOVE"', ui)
        self.assertIn("PIN", ui)
        self.assertIn("_maybe_discover_sources", ui)
        self.assertIn("live_lookup", ui)
        self.assertIn("LOOKING_CUE", ui)
        self.assertNotIn("XAI_API_KEY", ui)
        self.assertNotIn("api.x.ai", ui)
        self.assertIn("live_lookup", snap)
        self.assertIn("LOOKING_CUE", snap)
        refresh = ui.split("def _refresh_sources")[1].split("def ")[0]
        self.assertNotIn("item.title", refresh)
        self.assertNotIn("item.url", refresh)

    def test_snap_worker_uses_live_lookup(self) -> None:
        from battlebuddy.snap.service import SnapAsk
        from battlebuddy.sources.lookup import LookupResult

        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        shown: list[str] = []
        pane: list[str] = []
        snap = SnapAsk(shown.append, lambda: "Stellaris", on_answer=pane.append)
        looked = LookupResult(
            answer="Adaptive gives habitability.\nSources:\nhttps://stellaris.paradoxwikis.com/Traits",
            speak="Adaptive gives habitability.",
            urls=("https://stellaris.paradoxwikis.com/Traits",),
        )
        with patch.dict(os.environ, {"BATTLEBUDDY_HOME": tmp.name}), patch(
            "battlebuddy.snap.service.live_lookup", return_value=looked
        ), patch("battlebuddy.snap.service.speak", return_value=True), patch(
            "battlebuddy.snap.service.stop_speaking"
        ):
            snap._answer_worker("Adaptive trait", "Stellaris", "What does Adaptive do?", 0)
        self.assertEqual(pane[-1], looked.answer)
        self.assertTrue(any("Adaptive" in line for line in shown))


if __name__ == "__main__":
    unittest.main()

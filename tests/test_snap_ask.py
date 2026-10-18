"""Snap & Ask. No screen, no cloud. Section 1 memory is not in here."""

from __future__ import annotations

import json
import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from battlebuddy.readthis.hotkey import MOD_CONTROL, parse_hotkey
from battlebuddy.readthis.region import Rect
from battlebuddy.session.tier import load_tier, save_tier
from battlebuddy.snap.answer import (
    DEFAULT_QUESTION,
    answer_snap,
    grok_user_content,
    uses_image,
)
from battlebuddy.snap.config import (
    DEFAULT_SNAP_HOTKEY,
    load_snap_hotkey,
    save_snap_hotkey,
    send_snap_image,
)
from battlebuddy.snap.context import grounded_answer, pack_context
from battlebuddy.snap.facts import SOURCE_SNAP, add_snap_fact, list_snap_facts
from battlebuddy.snap.pipeline import finish_snap, log_path
from battlebuddy.snap import service as snap_service
from battlebuddy.snap.service import SnapAsk, grab_monitor
from battlebuddy.session.log import log_file, report, setup_logging
from battlebuddy.snap.shots import fitted_size, prune_snaps, snap_dir
from battlebuddy.readthis.config import load_hotkey, save_hotkey


class _FakeImage:
    def __init__(self) -> None:
        self.saved: list[str] = []

    def save(self, path: object, format: str | None = None) -> None:
        target = Path(path)
        target.write_bytes(b"png")
        self.saved.append(str(target))


class HotkeyAndSizeTest(unittest.TestCase):
    def test_default_hotkey_is_ctrl_2(self) -> None:
        self.assertEqual(DEFAULT_SNAP_HOTKEY, "ctrl+2")
        mods, vk = parse_hotkey(DEFAULT_SNAP_HOTKEY)
        self.assertEqual(mods, MOD_CONTROL)
        self.assertEqual(vk, ord("2"))
        self.assertNotIn("alt", DEFAULT_SNAP_HOTKEY.split("+"))

    def test_full_hd_frame_is_capped_before_ocr(self) -> None:
        self.assertEqual(fitted_size(1920, 1080), (1280, 720))
        self.assertEqual(fitted_size(800, 600), (800, 600))

    def test_grab_uses_the_monitor_under_the_pointer(self) -> None:
        bounds = Rect(-1920, 0, 1920, 1080)
        seen: dict[str, Rect] = {}

        def _monitor(_root: object | None) -> Rect:
            return bounds

        def _capture(rect: Rect) -> str:
            seen["rect"] = rect
            return "frame"

        rect, image = grab_monitor(None, capture=_capture, monitor=_monitor)
        self.assertEqual(rect, bounds)
        self.assertEqual(seen["rect"], bounds)
        self.assertEqual(image, "frame")


class SnapStoreTest(unittest.TestCase):
    def test_hotkey_roundtrip_keeps_read_hotkey_and_tier(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            with patch.dict(
                os.environ,
                {"BATTLEBUDDY_SNAP_HOTKEY": "", "BATTLEBUDDY_READ_HOTKEY": ""},
            ):
                save_tier("socratic", home)
                save_hotkey("ctrl+alt+r", home)
                save_snap_hotkey("ctrl+shift+f9", home)
                self.assertEqual(load_tier(home), "socratic")
                self.assertEqual(load_hotkey(home), "ctrl+alt+r")
                self.assertEqual(load_snap_hotkey(home), "ctrl+shift+f9")

    def test_env_hotkey_and_image_flag_default_off(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            save_snap_hotkey("ctrl+shift+f10", home)
            with patch.dict(os.environ, {"BATTLEBUDDY_SNAP_HOTKEY": "ctrl+shift+f8"}):
                self.assertEqual(load_snap_hotkey(home), "ctrl+shift+f8")
            with patch.dict(os.environ, {"BATTLEBUDDY_SNAP_SEND_IMAGE": ""}):
                self.assertFalse(send_snap_image(home))
            with patch.dict(os.environ, {"BATTLEBUDDY_SNAP_SEND_IMAGE": "1"}):
                self.assertTrue(send_snap_image(home))

    def test_snap_fact_stays_on_its_game(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            add_snap_fact("The colony has grown.", "Stellaris", home)
            own = list_snap_facts("Stellaris", home)
            self.assertEqual(len(own), 1)
            self.assertEqual(own[0].source, SOURCE_SNAP)
            self.assertIn("colony", own[0].text)
            self.assertEqual(list_snap_facts("Bellwright", home), [])

    def test_old_shots_are_cleared_after_seven_days(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            folder = snap_dir(home)
            folder.mkdir()
            old = folder / "snap-old.png"
            fresh = folder / "snap-fresh.png"
            old.write_bytes(b"old")
            fresh.write_bytes(b"new")
            moment = time.time()
            os.utime(old, (moment - 8 * 86400, moment - 8 * 86400))
            os.utime(fresh, (moment, moment))
            self.assertEqual(prune_snaps(home, now=moment, keep_days=7), 1)
            self.assertFalse(old.exists())
            self.assertTrue(fresh.exists())


class AnswerTest(unittest.TestCase):
    def test_pack_and_answer_stay_inside_the_snap(self) -> None:
        pack = pack_context(
            "The colony has grown.",
            ["Granary is low."],
            ["Food is stored in the granary."],
        )
        self.assertIn("colony", pack)
        self.assertIn("Granary is low.", pack)
        self.assertIn("granary", pack.lower())
        heard = grounded_answer("where is the granary", pack)
        self.assertIn("granary", heard.lower())
        self.assertNotIn("reactor", heard.lower())

    def test_grok_image_stays_off_unless_asked(self) -> None:
        plain = grok_user_content("What does this event do?", "Screen:\nHello.", b"png", send_image=False)
        self.assertIsInstance(plain, str)
        self.assertFalse(uses_image(plain))
        rich = grok_user_content("What does this event do?", "Screen:\nHello.", b"png", send_image=True)
        self.assertTrue(uses_image(rich))

    def test_grok_brain_sends_text_and_not_the_image(self) -> None:
        seen: dict[str, object] = {}

        def _chat(messages: list[dict[str, object]], key: str = "") -> str:
            seen["messages"] = messages
            seen["key"] = key
            return "The colony has grown."

        pack = "Screen:\nThe colony has grown."
        answer = answer_snap(
            "What does this event do?",
            pack,
            brain="grok",
            chat_fn=_chat,
            image_png=b"png",
            send_image=False,
            key="test-key",
        )
        self.assertIn("colony", answer.lower())
        messages = seen["messages"]
        self.assertIsInstance(messages, list)
        user = messages[1]["content"]  # type: ignore[index]
        self.assertFalse(uses_image(user))

    def test_finish_snap_stores_fact_and_log(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            with patch.dict(os.environ, {"BATTLEBUDDY_SNAP_SEND_IMAGE": "0"}):
                result = finish_snap(
                    _FakeImage(),
                    "The colony has grown.",
                    "Stellaris",
                    "What does this event do?",
                    notes=["Check food."],
                    pages=[],
                    home=home,
                    brain="dark",
                )
            self.assertEqual(result.fact.source, SOURCE_SNAP)
            self.assertTrue(result.image_path.is_file())
            self.assertEqual(list_snap_facts("Bellwright", home), [])
            self.assertEqual(list_snap_facts("Stellaris", home)[0].id, result.fact.id)
            self.assertIn("colony", result.answer.lower())
            row = json.loads(log_path(home).read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(row["question"], "What does this event do?")
            self.assertEqual(row["source"], SOURCE_SNAP)

    def test_ui_has_snap_buttons(self) -> None:
        source = (
            Path(__file__).resolve().parents[1] / "battlebuddy" / "ui" / "app.py"
        ).read_text(encoding="utf-8")
        self.assertIn('text="SNAP"', source)
        self.assertIn('text="SNAP BOX"', source)
        self.assertNotIn("superseded_by", source)
        self.assertNotIn("XAI_API_KEY", source)
        snap_src = Path(snap_service.__file__).read_text(encoding="utf-8")
        self.assertIn("Ask about this screen…", snap_src)
        self.assertIn("Listening…", snap_src)
        self.assertIn("Go ahead", snap_src)
        self.assertIn("Didn't catch that", snap_src)
        self.assertIn("def _prompt_question", snap_src)
        self.assertIn("self.snap_box()", snap_src)
        self.assertIn("def _fail", snap_src)
        self.assertNotIn("Empty Enter describes the screen", snap_src)
        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("SNAP BOX", readme)
        self.assertIn("every connected monitor", readme)
        self.assertIn("monitor under the pointer", readme)
        self.assertIn("battlebuddy.log", readme)
        self.assertIn("Go ahead", readme)
        self.assertIn("Listening", readme)
        self.assertIn("Didn't catch that", readme)

    def test_grok_exception_falls_back_to_the_pack(self) -> None:
        def _chat(*_args: object, **_kwargs: object) -> str:
            raise RuntimeError("network down")

        pack = "Screen:\nThe colony has grown."
        answer = answer_snap(
            DEFAULT_QUESTION,
            pack,
            brain="grok",
            chat_fn=_chat,
            key="test-key",
        )
        self.assertIn("colony", answer.lower())
        self.assertNotEqual(answer, "Snap could not answer.")

    def test_empty_local_brain_falls_back_to_the_pack(self) -> None:
        pack = "Screen:\nThe colony has grown."
        answer = answer_snap(
            DEFAULT_QUESTION,
            pack,
            brain="local",
            local_fn=lambda _q, _p: None,
        )
        self.assertIn("colony", answer.lower())


class SnapFailSurfaceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self._old_home = os.environ.get("BATTLEBUDDY_HOME")
        os.environ["BATTLEBUDDY_HOME"] = str(self.home)
        setup_logging(self.home)

    def tearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop("BATTLEBUDDY_HOME", None)
        else:
            os.environ["BATTLEBUDDY_HOME"] = self._old_home

    def test_empty_followup_does_not_auto_summarize(self) -> None:
        shown: list[str] = []
        snap = SnapAsk(shown.append, lambda: None)
        snap._last_ocr = "The colony has grown."
        seen: list[tuple[object, ...]] = []
        snap._answer_worker = lambda *args, **_kwargs: seen.append(args)  # type: ignore[method-assign]
        snap.ask_followup("")
        self.assertEqual(seen, [])
        self.assertTrue(any("Type a question" in line for line in shown))

    def test_ocr_then_listen_then_answer(self) -> None:
        shown: list[str] = []
        snap = SnapAsk(shown.append, lambda: "Stellaris")
        seen: list[tuple[object, ...]] = []
        snap._answer_worker = lambda *args, **_kwargs: seen.append(args)  # type: ignore[method-assign]
        with patch.object(snap_service, "stt_available", return_value=True), patch.object(
            snap_service, "listen_once", return_value="what is this event"
        ), patch.object(snap_service, "recognize", return_value="The colony has grown."), patch.object(
            snap_service, "shrink_for_ocr", side_effect=lambda image, **_k: image
        ), patch.object(
            snap_service,
            "speak",
            side_effect=lambda phrase, **_k: True,
        ):
            snap._read_image("frame", token=0)
        self.assertEqual(seen[0][2], "what is this event")
        self.assertTrue(any("Listening" in line for line in shown))

    def test_no_speech_falls_back_to_typed_box(self) -> None:
        spoken: list[str] = []
        shown: list[str] = []
        snap = SnapAsk(shown.append, lambda: None)
        with patch.object(snap_service, "stt_available", return_value=True), patch.object(
            snap_service, "listen_once", return_value=None
        ), patch.object(snap_service, "recognize", return_value="The colony has grown."), patch.object(
            snap_service, "shrink_for_ocr", side_effect=lambda image, **_k: image
        ), patch.object(
            snap_service,
            "speak",
            side_effect=lambda phrase, **_k: spoken.append(phrase) or True,
        ):
            snap._read_image("frame", token=0)
        self.assertEqual(spoken[0], "Go ahead")
        self.assertTrue(any("Didn't catch that" in line for line in shown))
        self.assertTrue(any(line == "Didn't catch that" for line in spoken))

    def test_stt_off_falls_back_to_typed_box(self) -> None:
        spoken: list[str] = []
        shown: list[str] = []
        snap = SnapAsk(shown.append, lambda: None)
        seen: list[tuple[object, ...]] = []
        snap._answer_worker = lambda *args, **_kwargs: seen.append(args)  # type: ignore[method-assign]
        with patch.object(snap_service, "stt_available", return_value=False), patch.object(
            snap_service, "recognize", return_value="The colony has grown."
        ), patch.object(
            snap_service, "shrink_for_ocr", side_effect=lambda image, **_k: image
        ), patch.object(
            snap_service,
            "speak",
            side_effect=lambda phrase, **_k: spoken.append(phrase) or True,
        ):
            snap._read_image("frame", token=0)
        self.assertEqual(seen, [])
        self.assertTrue(any("Mic is off" in line for line in shown))
        self.assertTrue(any("Mic is off" in line for line in spoken))

    def test_hotkey_starts_box_or_ends_listen(self) -> None:
        snap = SnapAsk(lambda _text: None, lambda: None)
        boxes: list[str] = []
        snap.snap_box = lambda: boxes.append("box")  # type: ignore[method-assign]
        snap._hotkey_main()
        self.assertEqual(boxes, ["box"])
        snap._listening = True
        snap._hotkey_main()
        self.assertTrue(snap._listen_stop.is_set())
        self.assertEqual(boxes, ["box"])

        class FakeOverlay:
            def __init__(self) -> None:
                self.cancelled = 0

            def cancel(self) -> None:
                self.cancelled += 1

        overlay = FakeOverlay()
        snap._listening = False
        snap._listen_stop.clear()
        snap._overlay = overlay  # type: ignore[assignment]
        snap._hotkey_main()
        self.assertEqual(overlay.cancelled, 1)
        self.assertEqual(boxes, ["box"])

    def test_empty_ocr_speaks_and_shows_an_error(self) -> None:
        spoken: list[str] = []
        shown: list[str] = []
        snap = SnapAsk(shown.append, lambda: None)
        with patch.object(snap_service, "recognize", return_value="   "), patch.object(
            snap_service, "shrink_for_ocr", side_effect=lambda image, **_k: image
        ), patch.object(
            snap_service,
            "speak",
            side_effect=lambda phrase, **_k: spoken.append(phrase) or True,
        ):
            snap._read_image("frame", token=0)
        self.assertTrue(any("No text" in line for line in shown))
        self.assertTrue(any("No text" in line for line in spoken))
        self.assertEqual(snap._follow, None)

    def test_worker_exception_is_spoken_and_logged(self) -> None:
        spoken: list[str] = []
        shown: list[str] = []
        snap = SnapAsk(shown.append, lambda: None)
        with patch.object(
            snap, "_read_image", side_effect=RuntimeError("boom")
        ), patch.object(
            snap_service,
            "speak",
            side_effect=lambda phrase, **_k: spoken.append(phrase) or True,
        ), patch.object(
            snap_service,
            "grab_monitor",
            return_value=(Rect(0, 0, 10, 10), "frame"),
        ):
            snap._monitor_worker(None, 0)
        self.assertTrue(any("Snap" in line for line in shown))
        self.assertTrue(any("Snap" in line for line in spoken))
        blob = log_file(self.home).read_text(encoding="utf-8")
        self.assertIn("boom", blob)

    def test_report_writes_traceback_to_home_log(self) -> None:
        try:
            raise RuntimeError("network down")
        except RuntimeError as exc:
            report("snap grok call failed", exc)
        blob = log_file(self.home).read_text(encoding="utf-8")
        self.assertIn("network down", blob)
        self.assertIn("snap grok call failed", blob)
        self.assertIn("Traceback", blob)


if __name__ == "__main__":
    unittest.main()

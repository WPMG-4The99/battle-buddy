"""Snap & Ask. No screen, no cloud. Section 1 memory is not in here."""

from __future__ import annotations

import json
import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from battlebuddy.readthis.hotkey import MOD_CONTROL, MOD_SHIFT, parse_hotkey
from battlebuddy.readthis.region import Rect
from battlebuddy.session.tier import load_tier, save_tier
from battlebuddy.snap.answer import answer_snap, grok_user_content, uses_image
from battlebuddy.snap.config import (
    DEFAULT_SNAP_HOTKEY,
    load_snap_hotkey,
    save_snap_hotkey,
    send_snap_image,
)
from battlebuddy.snap.context import grounded_answer, pack_context
from battlebuddy.snap.facts import SOURCE_SNAP, add_snap_fact, list_snap_facts
from battlebuddy.snap.pipeline import finish_snap, log_path
from battlebuddy.snap.service import grab_monitor
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
    def test_default_hotkey_is_ctrl_shift_f10(self) -> None:
        mods, vk = parse_hotkey(DEFAULT_SNAP_HOTKEY)
        self.assertEqual(mods, MOD_CONTROL | MOD_SHIFT)
        self.assertEqual(vk, 0x79)
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
        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("SNAP BOX", readme)
        self.assertIn("every connected monitor", readme)
        self.assertIn("monitor under the pointer", readme)


if __name__ == "__main__":
    unittest.main()

"""Local STT. Cancel must not hang. No cloud recognizer."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from battlebuddy.voice.stt import listen_once, stt_available


class ListenOnceTest(unittest.TestCase):
    def test_allow_false_returns_none_without_waiting(self) -> None:
        with patch("battlebuddy.voice.stt._listen_windows") as win, patch(
            "battlebuddy.voice.stt._listen_sphinx"
        ) as sphinx:
            self.assertIsNone(listen_once(allow=lambda: False))
            win.assert_not_called()
            sphinx.assert_not_called()

    def test_available_is_boolean(self) -> None:
        self.assertIn(stt_available(), (True, False))

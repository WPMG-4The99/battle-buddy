"""Local TTS hide-window contract. No cloud. No account."""

from __future__ import annotations

import unittest
from pathlib import Path

from battlebuddy.voice import tts
from battlebuddy.voice.tts import hidden_console_run_kwargs

_CREATE_NO_WINDOW = 0x08000000


class TtsHideConsoleTest(unittest.TestCase):
    def test_hidden_run_kwargs_include_create_no_window(self) -> None:
        kwargs = hidden_console_run_kwargs()
        flags = int(kwargs["creationflags"])
        self.assertEqual(flags & _CREATE_NO_WINDOW, _CREATE_NO_WINDOW)
        self.assertNotIn("startupinfo", kwargs)

    def test_windows_speak_source_hides_console_and_keeps_capture(self) -> None:
        text = Path(tts.__file__).read_text(encoding="utf-8")
        self.assertIn("CREATE_NO_WINDOW", text)
        self.assertIn("0x08000000", text)
        self.assertIn("creationflags", text)
        self.assertIn("capture_output", text)
        self.assertIn("hidden_console_run_kwargs", text)
        speak_win = text.split("def _speak_windows")[1].split("def ")[0]
        self.assertIn("capture_output", speak_win)
        self.assertIn("hidden_console_run_kwargs", speak_win)
        self.assertIn("SpeechSynthesizer", speak_win)
        self.assertNotIn("openai", text.lower())
        self.assertNotIn("anthropic", text.lower())


if __name__ == "__main__":
    unittest.main()

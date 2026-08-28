"""Local fire cue: visual always, audio when the box can speak."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys

from battlebuddy.reminders.engine import Reminder

_BANNER = """
========================================
  FIRE
  {text}
========================================
""".strip()


def announce(reminder: Reminder) -> None:
    """Print a high-contrast fire. Speak locally if a TTS binary exists."""
    text = reminder.text
    sys.stdout.write(_BANNER.format(text=text) + "\n")
    sys.stdout.write("\a")
    sys.stdout.flush()
    speak(f"Battle Buddy. Fire. {text}")


def speak(phrase: str) -> None:
    """Best-effort local TTS. Never calls a cloud. Failure is silent."""
    system = platform.system()
    try:
        if system == "Windows":
            quoted = json.dumps(phrase)
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Add-Type -AssemblyName System.Speech; "
                    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                    f"$s.Speak({quoted})",
                ],
                timeout=30,
                check=False,
                capture_output=True,
            )
            return
        if system == "Darwin":
            subprocess.run(["say", phrase], timeout=30, check=False, capture_output=True)
            return
        for binary in ("espeak-ng", "espeak", "spd-say"):
            if shutil.which(binary):
                subprocess.run(
                    [binary, phrase],
                    timeout=30,
                    check=False,
                    capture_output=True,
                )
                return
    except (OSError, subprocess.SubprocessError):
        return

"""Local fire cue: visual always, audio when the box can speak."""

from __future__ import annotations

import sys

from battlebuddy.reminders.engine import Reminder
from battlebuddy.voice.tts import speak

_BANNER = """
========================================
  FIRE
  {text}
========================================
""".strip()


def fire_banner(text: str) -> str:
    return _BANNER.format(text=text)


def announce(reminder: Reminder) -> None:
    """Print a high-contrast fire. Speak locally if a TTS path exists."""
    text = reminder.text
    sys.stdout.write(fire_banner(text) + "\n")
    sys.stdout.write("\a")
    sys.stdout.flush()
    speak(f"Battle Buddy. Fire. {text}")


def confirm_line(text: str, delay_label: str) -> str:
    return f"Locked. Fires in {delay_label}: {text}"


def confirm(text: str, delay_label: str, due_stamp: str, reminder_id: str) -> str:
    """Immediate confirm. Print always. Speak locally if TTS exists."""
    line = confirm_line(text, delay_label)
    sys.stdout.write(line + "\n")
    sys.stdout.write(f"Due {due_stamp}. Holding the line. id {reminder_id}\n")
    sys.stdout.flush()
    speak(line)
    return line

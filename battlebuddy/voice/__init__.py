"""Local voice. TTS and optional STT. No cloud. No API key."""

from battlebuddy.voice.stt import listen_once, stt_available
from battlebuddy.voice.tts import (
    is_speaking,
    speak,
    speak_async,
    spoken_line,
    stop_speaking,
    tts_available,
)

__all__ = [
    "is_speaking",
    "listen_once",
    "speak",
    "speak_async",
    "spoken_line",
    "stop_speaking",
    "stt_available",
    "tts_available",
]

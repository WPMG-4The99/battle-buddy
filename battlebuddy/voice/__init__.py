"""Local voice. TTS and optional STT. No cloud. No API key."""

from battlebuddy.voice.stt import listen_once, stt_available
from battlebuddy.voice.tts import speak, speak_async, tts_available

__all__ = [
    "listen_once",
    "speak",
    "speak_async",
    "stt_available",
    "tts_available",
]

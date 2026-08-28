"""Local voice. TTS and optional STT. No cloud. No API key."""

from battlebuddy.voice.tts import speak, speak_async, tts_available

__all__ = ["speak", "speak_async", "tts_available"]

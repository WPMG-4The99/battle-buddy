"""Three local ticks. One-minute warning. No cloud. No TTS."""

from __future__ import annotations

import math
import struct
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path

_TICK_COUNT = 3
_FREQ_HZ = 1000
_BEEP_MS = 70
_GAP_MS = 80
_SAMPLE_RATE = 22050
_AMPLITUDE = 0.38


def play_ticks() -> bool:
    """Play tick-tick-tick locally. Failure is silent. Never calls TTS."""
    try:
        if sys.platform == "win32":
            return _ticks_windows()
        return _ticks_wav_command()
    except Exception:
        return False


def play_ticks_async(times: int = 1) -> None:
    """Don't block the UI. Sequential if two reminders warn on the same tick."""
    if times < 1:
        return

    def run() -> None:
        for _ in range(times):
            play_ticks()

    threading.Thread(target=run, daemon=True, name="battlebuddy-ticks").start()


def _ticks_windows() -> bool:
    try:
        import winsound
    except ImportError:
        return False
    try:
        for index in range(_TICK_COUNT):
            winsound.Beep(_FREQ_HZ, _BEEP_MS)
            if index < _TICK_COUNT - 1:
                time.sleep(_GAP_MS / 1000)
        return True
    except RuntimeError:
        return _play_wav_windows()


def _play_wav_windows() -> bool:
    try:
        import winsound
    except ImportError:
        return False
    path = _write_tick_wav()
    try:
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_NODEFAULT)
        return True
    except RuntimeError:
        return False
    finally:
        path.unlink(missing_ok=True)


def _ticks_wav_command() -> bool:
    path = _write_tick_wav()
    try:
        player = _local_wav_player()
        if player is None:
            sys.stdout.write("\a\a\a")
            sys.stdout.flush()
            return False
        subprocess.run(
            player + [str(path)],
            timeout=3,
            check=False,
            capture_output=True,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        try:
            sys.stdout.write("\a\a\a")
            sys.stdout.flush()
        except OSError:
            pass
        return False
    finally:
        path.unlink(missing_ok=True)


def _local_wav_player() -> list[str] | None:
    import shutil

    if sys.platform == "darwin":
        afplay = shutil.which("afplay")
        return [afplay] if afplay else None
    for name, extra in (
        ("aplay", ["-q"]),
        ("paplay", []),
        ("pw-play", []),
        ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"]),
    ):
        found = shutil.which(name)
        if found:
            return [found, *extra]
    return None


def _write_tick_wav() -> Path:
    handle = tempfile.NamedTemporaryFile(prefix="battlebuddy-tick-", suffix=".wav", delete=False)
    handle.close()
    path = Path(handle.name)
    frames = _tick_pcm()
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(_SAMPLE_RATE)
        wav.writeframes(frames)
    return path


def _tick_pcm() -> bytes:
    beep_n = int(_SAMPLE_RATE * _BEEP_MS / 1000)
    gap_n = int(_SAMPLE_RATE * _GAP_MS / 1000)
    chunks: list[bytes] = []
    for index in range(_TICK_COUNT):
        chunks.append(_sine_frames(beep_n))
        if index < _TICK_COUNT - 1:
            chunks.append(b"\x00\x00" * gap_n)
    return b"".join(chunks)


def _sine_frames(count: int) -> bytes:
    peak = int(32767 * _AMPLITUDE)
    out = bytearray()
    for index in range(count):
        # Short cosine fade so the tick is a click, not a pop.
        fade = 1.0
        edge = min(40, count // 4)
        if index < edge:
            fade = index / edge
        elif index > count - edge:
            fade = (count - index) / edge
        sample = int(peak * fade * math.sin(2 * math.pi * _FREQ_HZ * index / _SAMPLE_RATE))
        out.extend(struct.pack("<h", sample))
    return bytes(out)

"""Local tick-tick-tick. No cloud. No TTS. Stdlib only."""

from __future__ import annotations

import unittest
import wave

from battlebuddy.voice.tick import _tick_pcm, _write_tick_wav, play_ticks_async


class TickWavTest(unittest.TestCase):
    def test_wav_is_three_short_ticks(self) -> None:
        pcm = _tick_pcm()
        self.assertGreater(len(pcm), 1000)
        path = _write_tick_wav()
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        with wave.open(str(path), "rb") as wav:
            self.assertEqual(wav.getnchannels(), 1)
            self.assertEqual(wav.getsampwidth(), 2)
            self.assertEqual(wav.getframerate(), 22050)
            frames = wav.getnframes()
        self.assertGreater(frames, 0)
        duration = frames / 22050
        self.assertLess(duration, 1.0)
        self.assertGreater(duration, 0.2)

    def test_async_zero_is_noop(self) -> None:
        play_ticks_async(0)


if __name__ == "__main__":
    unittest.main()

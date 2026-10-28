#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from speech_segmenter import get_segment_cut_reason


class SpeechSegmenterTests(unittest.TestCase):
    sample_rate = 100
    threshold = 0.005

    def _speech_with_silence(self, total_duration, silence_duration):
        audio = np.full(
            int(total_duration * self.sample_rate),
            0.02,
            dtype=np.float32,
        )
        audio[-int(silence_duration * self.sample_rate):] = 0
        return audio

    def test_brief_pause_does_not_cut_with_longer_sentence_pause(self):
        audio = self._speech_with_silence(3.0, 0.5)

        reason = get_segment_cut_reason(
            audio,
            self.sample_rate,
            self.threshold,
            silence_duration=0.8,
            max_phrase_duration=8.0,
        )

        self.assertIsNone(reason)

    def test_configured_sentence_pause_finalizes_segment(self):
        audio = self._speech_with_silence(3.0, 0.8)

        reason = get_segment_cut_reason(
            audio,
            self.sample_rate,
            self.threshold,
            silence_duration=0.8,
            max_phrase_duration=8.0,
        )

        self.assertEqual(reason, "silence")

    def test_soft_limit_keeps_long_speech_responsive(self):
        audio = self._speech_with_silence(6.2, 0.4)

        reason = get_segment_cut_reason(
            audio,
            self.sample_rate,
            self.threshold,
            silence_duration=0.8,
            max_phrase_duration=8.0,
        )

        self.assertEqual(reason, "soft_limit")

    def test_hard_limit_finalizes_without_silence(self):
        audio = np.full(int(8.1 * self.sample_rate), 0.02, dtype=np.float32)

        reason = get_segment_cut_reason(
            audio,
            self.sample_rate,
            self.threshold,
            silence_duration=0.8,
            max_phrase_duration=8.0,
        )

        self.assertEqual(reason, "hard_limit")


if __name__ == "__main__":
    unittest.main(verbosity=2)

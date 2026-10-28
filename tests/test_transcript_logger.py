#!/usr/bin/env python3
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from transcript_logger import TranscriptLogger


class TranscriptLoggerTests(unittest.TestCase):
    def test_records_transcription_and_translation(self):
        temp_root = ROOT / "test_outputs"
        temp_root.mkdir(exist_ok=True)
        paths = [
            temp_root / "transcript_test-session.jsonl",
            temp_root / "transcript_test-session.txt",
        ]
        for path in paths:
            path.unlink(missing_ok=True)

        try:
            logger = TranscriptLogger(log_dir=temp_root, session_id="test-session")

            logger.record(4, original="Hello world", status="transcribed")
            logger.record(4, original="Hello world", translated="你好，世界", status="translated")

            self.assertTrue(logger.jsonl_path.exists())
            self.assertTrue(logger.text_path.exists())

            events = [
                json.loads(line)
                for line in logger.jsonl_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(events), 2)
            self.assertEqual(events[-1]["chunk_id"], 4)
            self.assertEqual(events[-1]["translated"], "你好，世界")

            text_log = logger.text_path.read_text(encoding="utf-8")
            self.assertIn("Original: Hello world", text_log)
            self.assertIn("Translation: 你好，世界", text_log)
            self.assertIn("#4 translated", text_log)
        finally:
            for path in paths:
                path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)

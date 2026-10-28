#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from main import Pipeline


class RecordingSignal:
    def __init__(self, name, events):
        self.name = name
        self.events = events

    def emit(self, *args):
        self.events.append((self.name, args))


class RecordingExecutor:
    def __init__(self, events):
        self.events = events

    def submit(self, function, *args):
        self.events.append(("translation_submitted", args))


class FakeTranscriber:
    def transcribe(self, audio_data, prompt=None):
        return "This source text is ready."


class FakeLogger:
    def record(self, *args, **kwargs):
        return None


class PipelineSourceFirstTests(unittest.TestCase):
    def test_final_source_is_emitted_before_translation_submission(self):
        events = []
        pipeline = Pipeline.__new__(Pipeline)
        pipeline.transcriber = FakeTranscriber()
        pipeline.transcript_logger = FakeLogger()
        pipeline.last_final_text = ""
        pipeline.signals = type(
            "Signals",
            (),
            {
                "update_text": RecordingSignal("update_text", events),
                "status": RecordingSignal("status", events),
            },
        )()
        executor = RecordingExecutor(events)

        pipeline._process_final_chunk(
            audio_data=None,
            chunk_id=7,
            translate_executor=executor,
        )

        source_event = (
            "update_text",
            (7, "This source text is ready.", ""),
        )
        self.assertIn(source_event, events)
        self.assertLess(
            events.index(source_event),
            next(
                index
                for index, event in enumerate(events)
                if event[0] == "translation_submitted"
            ),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

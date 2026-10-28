#!/usr/bin/env python3
import queue
import sys
import threading
import time
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from audio_capture import AudioBufferClosed, AudioChunkBuffer


class AudioChunkBufferTests(unittest.TestCase):
    def test_drops_oldest_chunk_when_full(self):
        buffer = AudioChunkBuffer(max_chunks=2)
        first = np.array([1], dtype=np.float32)
        second = np.array([2], dtype=np.float32)
        third = np.array([3], dtype=np.float32)

        self.assertFalse(buffer.put(first))
        self.assertFalse(buffer.put(second))
        self.assertTrue(buffer.put(third))

        np.testing.assert_array_equal(buffer.get(), second)
        np.testing.assert_array_equal(buffer.get(), third)
        stats = buffer.stats()
        self.assertEqual(stats["dropped"], 1)
        self.assertEqual(stats["high_watermark"], 2)

    def test_consumer_waits_for_producer(self):
        buffer = AudioChunkBuffer(max_chunks=2)
        received = []

        def consume():
            received.append(buffer.get(timeout=1.0))

        thread = threading.Thread(target=consume)
        thread.start()
        time.sleep(0.02)
        buffer.put(np.array([7], dtype=np.float32))
        thread.join(timeout=1.0)

        self.assertFalse(thread.is_alive())
        np.testing.assert_array_equal(received[0], np.array([7], dtype=np.float32))

    def test_close_wakes_waiting_consumer(self):
        buffer = AudioChunkBuffer(max_chunks=2)
        buffer.close()

        with self.assertRaises(AudioBufferClosed):
            buffer.get(timeout=0.1)
        with self.assertRaises(queue.Empty):
            AudioChunkBuffer(max_chunks=1).get(timeout=0.01)


if __name__ == "__main__":
    unittest.main(verbosity=2)

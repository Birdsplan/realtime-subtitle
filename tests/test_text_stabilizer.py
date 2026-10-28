#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from text_stabilizer import remove_repeated_prefix


class TextStabilizerTests(unittest.TestCase):
    def test_removes_repeated_prefix_from_overlap(self):
        previous = "the spring has some kind of natural frequency"
        current = "natural frequency that it wants to oscillate at"

        result = remove_repeated_prefix(current, previous)

        self.assertEqual(result, "that it wants to oscillate at")

    def test_keeps_new_text_without_overlap(self):
        result = remove_repeated_prefix(
            "now I am adding that extra force",
            "the spring has some natural frequency",
        )

        self.assertEqual(result, "now I am adding that extra force")


if __name__ == "__main__":
    unittest.main(verbosity=2)

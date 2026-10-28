#!/usr/bin/env python3
import configparser
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from overlay_window import (
    RESIZE_MARGIN,
    calculate_overlay_geometry,
    detect_resize_edges,
    persist_window_size,
    should_show_translation,
)


class OverlayLayoutTests(unittest.TestCase):
    def test_centers_overlay_near_bottom(self):
        geometry = calculate_overlay_geometry(
            screen_x=0,
            screen_y=0,
            screen_width=1920,
            screen_height=1040,
            requested_width=1000,
            requested_height=320,
            bottom_margin=48,
        )

        self.assertEqual(geometry, (460, 672, 1000, 320))

    def test_clamps_overlay_to_small_screen(self):
        x, y, width, height = calculate_overlay_geometry(
            screen_x=0,
            screen_y=0,
            screen_width=400,
            screen_height=300,
            requested_width=1000,
            requested_height=320,
            bottom_margin=48,
        )

        self.assertGreaterEqual(x, 0)
        self.assertGreaterEqual(y, 0)
        self.assertLessEqual(x + width, 400)
        self.assertLessEqual(y + height, 300)

    def test_supports_bottom_left_and_right_positions(self):
        left = calculate_overlay_geometry(0, 0, 1920, 1040, 1000, 320, 48, "bottom_left")
        right = calculate_overlay_geometry(0, 0, 1920, 1040, 1000, 320, 48, "bottom_right")

        self.assertEqual(left, (20, 672, 1000, 320))
        self.assertEqual(right, (900, 672, 1000, 320))

    def test_hides_pending_translation_until_result_arrives(self):
        self.assertFalse(should_show_translation(""))
        self.assertFalse(should_show_translation("(translating...)"))
        self.assertTrue(should_show_translation("翻译已经完成。"))


class ResizeEdgeDetectionTests(unittest.TestCase):
    def test_detects_each_single_edge(self):
        self.assertEqual(detect_resize_edges(4, 150, 800, 300), {"left"})
        self.assertEqual(detect_resize_edges(796, 150, 800, 300), {"right"})
        self.assertEqual(detect_resize_edges(400, 4, 800, 300), {"top"})
        self.assertEqual(detect_resize_edges(400, 296, 800, 300), {"bottom"})

    def test_detects_corners_as_two_edges(self):
        self.assertEqual(detect_resize_edges(4, 4, 800, 300), {"left", "top"})
        self.assertEqual(detect_resize_edges(797, 297, 800, 300), {"right", "bottom"})

    def test_interior_is_not_an_edge(self):
        self.assertEqual(detect_resize_edges(400, 150, 800, 300), set())

    def test_margin_is_configurable(self):
        self.assertEqual(detect_resize_edges(15, 150, 800, 300, margin=16), {"left"})
        self.assertEqual(detect_resize_edges(15, 150, 800, 300, margin=8), set())

    def test_default_margin_reaches_past_transparent_window_border(self):
        # The outer 12 px of the overlay window is fully transparent and does
        # not reliably get mouse events on Windows; the resize zone must
        # extend onto the visible panel or edge-resizing is unreachable.
        self.assertGreater(RESIZE_MARGIN, 12)


class PersistWindowSizeTests(unittest.TestCase):
    def test_updates_size_and_keeps_other_display_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.ini"
            path.write_text(
                "[display]\n"
                "window_width = 1000\n"
                "window_height = 320\n"
                "position = bottom_center\n",
                encoding="utf-8",
            )

            persist_window_size(str(path), 1280, 400)

            parser = configparser.ConfigParser()
            parser.read(path)
            self.assertEqual(parser.getint("display", "window_width"), 1280)
            self.assertEqual(parser.getint("display", "window_height"), 400)
            self.assertEqual(parser.get("display", "position"), "bottom_center")

    def test_creates_display_section_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.ini"
            path.write_text("[audio]\nsample_rate = 16000\n", encoding="utf-8")

            persist_window_size(str(path), 900, 260)

            parser = configparser.ConfigParser()
            parser.read(path)
            self.assertEqual(parser.getint("display", "window_width"), 900)
            self.assertEqual(parser.getint("display", "window_height"), 260)
            self.assertEqual(parser.getint("audio", "sample_rate"), 16000)


if __name__ == "__main__":
    unittest.main(verbosity=2)

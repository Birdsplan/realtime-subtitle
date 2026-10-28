#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import Config


class ConfigRealtimeAsrTests(unittest.TestCase):
    def test_reads_partial_asr_settings(self):
        temp_root = ROOT / "test_outputs"
        temp_root.mkdir(exist_ok=True)
        config_path = temp_root / "config_realtime_asr_test.ini"
        try:
            config_path.write_text(
                "\n".join(
                    [
                        "[audio]",
                        "silence_duration = 0.8",
                        "partial_transcription = false",
                        "max_partial_duration = 2.5",
                        "final_overlap_duration = 0.75",
                        "capture_buffer_seconds = 9.0",
                        "",
                        "[display]",
                        "window_width = 960",
                        "window_height = 300",
                        "max_visible_items = 3",
                        "bottom_margin = 52",
                        "position = bottom_right",
                        "original_font_size = 17",
                        "translation_font_size = 25",
                        "panel_opacity = 126",
                        "auto_hide_controls = false",
                    ]
                ),
                encoding="utf-8",
            )

            cfg = Config(str(config_path))

            self.assertFalse(cfg.partial_transcription)
            self.assertEqual(cfg.silence_duration, 0.8)
            self.assertEqual(cfg.max_partial_duration, 2.5)
            self.assertEqual(cfg.final_overlap_duration, 0.75)
            self.assertEqual(cfg.capture_buffer_seconds, 9.0)
            self.assertEqual(cfg.window_width, 960)
            self.assertEqual(cfg.window_height, 300)
            self.assertEqual(cfg.max_visible_items, 3)
            self.assertEqual(cfg.overlay_bottom_margin, 52)
            self.assertEqual(cfg.overlay_position, "bottom_right")
            self.assertEqual(cfg.original_font_size, 17)
            self.assertEqual(cfg.translation_font_size, 25)
            self.assertEqual(cfg.panel_opacity, 126)
            self.assertFalse(cfg.auto_hide_controls)
        finally:
            config_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)

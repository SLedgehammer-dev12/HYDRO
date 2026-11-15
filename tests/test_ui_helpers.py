from __future__ import annotations

import unittest

from hidrostatik_test.ui.helpers import (
    FIELD_MESSAGE_PREFIXES,
    PALETTE,
    format_detail_value,
    format_field_message,
    get_palette_colors,
    get_visual_level,
)


class UiHelperTests(unittest.TestCase):
    def test_field_message_prefixes_follow_level(self) -> None:
        self.assertEqual(format_field_message("ok", "success"), "Hazir: ok")
        self.assertEqual(format_field_message("dikkat", "warning"), "Uyari: dikkat")
        self.assertEqual(format_field_message("bozuk", "error"), "Hata: bozuk")
        self.assertEqual(format_field_message("bilgi", "info"), "bilgi")
        self.assertEqual(format_field_message("bilinmeyen", "other"), "bilinmeyen")

    def test_empty_message_stays_empty_for_every_level(self) -> None:
        for level in FIELD_MESSAGE_PREFIXES:
            self.assertEqual(format_field_message("", level), "")

    def test_visual_level_and_palette_have_safe_fallbacks(self) -> None:
        self.assertEqual(get_visual_level("success"), "success")
        self.assertEqual(get_visual_level("unknown"), "neutral")
        self.assertEqual(get_palette_colors("error"), PALETTE["error"])
        self.assertEqual(get_palette_colors("unknown"), PALETTE["neutral"])

    def test_format_detail_value_only_appends_real_units(self) -> None:
        self.assertEqual(format_detail_value("12.5", "bar"), "12.5 bar")
        self.assertEqual(format_detail_value("-", "bar"), "-")
        self.assertEqual(format_detail_value("12.5", ""), "12.5")
        self.assertEqual(format_detail_value("12.5", " "), "12.5")


if __name__ == "__main__":
    unittest.main()

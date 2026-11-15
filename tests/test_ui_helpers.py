from __future__ import annotations

import unittest

from hidrostatik_test.ui.helpers import (
    FIELD_MESSAGE_PREFIXES,
    PALETTE,
    format_detail_value,
    format_field_message,
    format_required_marker,
    get_palette_colors,
    get_visual_level,
    truncate_text,
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

    def test_truncate_text_keeps_short_text_and_cuts_at_word_boundary(self) -> None:
        self.assertEqual(truncate_text("kisa karar", 40), "kisa karar")
        shortened = truncate_text("kelime " * 80, 60)

        self.assertLessEqual(len(shortened), 60)
        self.assertTrue(shortened.endswith("..."))
        self.assertFalse(shortened[:-3].endswith(" "))

    def test_truncate_text_normalizes_whitespace_and_handles_limits(self) -> None:
        self.assertEqual(truncate_text("  cok   bosluklu \n metin  ", 100), "cok bosluklu metin")
        self.assertEqual(truncate_text("metin", 0), "")
        self.assertEqual(truncate_text("abcdef", 3), "abc")

    def test_required_marker_is_added_and_removed_idempotently(self) -> None:
        self.assertEqual(format_required_marker("Vpa (m³)", True), "Vpa (m³) *")
        self.assertEqual(format_required_marker("Vpa (m³)", False), "Vpa (m³)")
        self.assertEqual(format_required_marker("A (10^-6/bar) *", True), "A (10^-6/bar) *")
        self.assertEqual(format_required_marker("A (10^-6/bar) *", False), "A (10^-6/bar)")


if __name__ == "__main__":
    unittest.main()

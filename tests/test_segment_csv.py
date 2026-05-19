from __future__ import annotations

import unittest

from hidrostatik_test.data.segment_csv import (
    ParsedSegment,
    SegmentParseError,
    parse_segment_csv,
)


class SegmentCsvParseTests(unittest.TestCase):
    def test_parses_semicolon_csv_with_header(self) -> None:
        raw = (
            "OD (mm);Et (mm);Uzunluk (m)\n"
            "406.4;8.74;500\n"
            "323.9;6.35;300"
        )
        result = parse_segment_csv(raw)
        self.assertEqual(
            result,
            [
                ParsedSegment(406.4, 8.74, 500.0),
                ParsedSegment(323.9, 6.35, 300.0),
            ],
        )

    def test_parses_comma_delimited_csv(self) -> None:
        raw = "dis cap (mm),et kalinligi (mm),hat uzunlugu (m)\n406.4,8.74,500"
        result = parse_segment_csv(raw)
        self.assertEqual(result, [ParsedSegment(406.4, 8.74, 500.0)])

    def test_parses_tab_delimited_csv(self) -> None:
        raw = "OD\tEt (mm)\tlength_m\n406.4\t8.74\t500"
        result = parse_segment_csv(raw)
        self.assertEqual(result, [ParsedSegment(406.4, 8.74, 500.0)])

    def test_handles_quoted_fields(self) -> None:
        raw = '"OD (mm)";"Et (mm)";"Uzunluk (m)"\n"406,4";"8,74";"500"'
        result = parse_segment_csv(raw)
        self.assertEqual(result, [ParsedSegment(406.4, 8.74, 500.0)])

    def test_handles_english_header_names(self) -> None:
        raw = "outside_diameter_mm,wall_thickness_mm,length_m\n406.4,8.74,500"
        result = parse_segment_csv(raw)
        self.assertEqual(result, [ParsedSegment(406.4, 8.74, 500.0)])

    def test_handles_short_header_names(self) -> None:
        raw = "OD,WT,L\n406.4,8.74,500\n323.9,6.35,300"
        result = parse_segment_csv(raw)
        self.assertEqual(result, [
            ParsedSegment(406.4, 8.74, 500.0),
            ParsedSegment(323.9, 6.35, 300.0),
        ])

    def test_returns_empty_for_empty_input(self) -> None:
        self.assertEqual(parse_segment_csv(""), [])
        self.assertEqual(parse_segment_csv("   "), [])

    def test_skips_invalid_rows(self) -> None:
        raw = "OD;Et;Uzunluk\n406.4;abc;500\n10;6;500\n-1;5;100"
        result = parse_segment_csv(raw)
        self.assertEqual(result, [])

    def test_skips_wall_too_thick(self) -> None:
        raw = "OD;Et;Uzunluk\n406.4;250;500"
        result = parse_segment_csv(raw)
        self.assertEqual(result, [])

    def test_fallback_column_indices_on_unknown_header(self) -> None:
        raw = "A;B;C\n406.4;8.74;500"
        result = parse_segment_csv(raw)
        self.assertEqual(result, [ParsedSegment(406.4, 8.74, 500.0)])

    def test_skips_short_rows(self) -> None:
        raw = "OD;Et;Uzunluk\n406.4;8.74\n406.4"
        result = parse_segment_csv(raw)
        self.assertEqual(result, [])

    def test_rtl_header_with_fewer_columns_sets_indices(self) -> None:
        raw = "OD;Et\n406.4;8.74;500"
        result = parse_segment_csv(raw)
        self.assertEqual(result, [ParsedSegment(406.4, 8.74, 500.0)])

    def test_only_header_no_data(self) -> None:
        raw = "OD (mm);Et (mm);Uzunluk (m)"
        result = parse_segment_csv(raw)
        self.assertEqual(result, [])

    def test_pipe_delimiter(self) -> None:
        raw = "OD (mm)|Et (mm)|Uzunluk (m)\n406.4|8.74|500"
        result = parse_segment_csv(raw)
        self.assertEqual(result, [ParsedSegment(406.4, 8.74, 500.0)])


if __name__ == "__main__":
    unittest.main()

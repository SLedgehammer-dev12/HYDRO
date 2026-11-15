from __future__ import annotations

import unittest
from math import isclose
from pathlib import Path

from hidrostatik_test.data import (
    BOTAS_REFERENCE_OPTION_LABEL,
    BOTAS_REFERENCE_TABLE_CSV_PATH,
    BOTAS_REFERENCE_TABLE_METADATA_PATH,
    DEFAULT_CONTROL_TABLE_CSV_PATH,
    DEFAULT_CONTROL_TABLE_METADATA_PATH,
    ABControlTableError,
    describe_botas_reference_table_range,
    is_botas_reference_option,
    lookup_ab_control_point,
    lookup_botas_reference_point,
    lookup_gail_reference_point,
)
from hidrostatik_test.data.botas_reference_table import compare_reference_b_sources

_DATA_DIR = Path(__file__).resolve().parents[1] / "hidrostatik_test" / "data"


class BotasReferenceTableTests(unittest.TestCase):
    def test_option_label_is_detected(self) -> None:
        self.assertTrue(is_botas_reference_option(BOTAS_REFERENCE_OPTION_LABEL))

    def test_range_description_matches_control_table_grid(self) -> None:
        self.assertEqual(describe_botas_reference_table_range(), "T=1-25 degC ve P=30-120 bar")

    def test_path_constants_alias_the_control_table(self) -> None:
        self.assertEqual(BOTAS_REFERENCE_TABLE_CSV_PATH, DEFAULT_CONTROL_TABLE_CSV_PATH)
        self.assertEqual(BOTAS_REFERENCE_TABLE_METADATA_PATH, DEFAULT_CONTROL_TABLE_METADATA_PATH)

    def test_exact_grid_node_matches_control_table_value(self) -> None:
        point = lookup_botas_reference_point(temp_c=10.0, pressure_bar=50.0)

        self.assertTrue(isclose(point.a_micro_per_bar, 46.775, rel_tol=1e-12))
        self.assertTrue(isclose(point.b_micro_per_c, 64.923, rel_tol=1e-12))
        self.assertIn("BOTA", point.source_note)

    def test_non_grid_point_uses_bilinear_interpolation(self) -> None:
        point = lookup_botas_reference_point(temp_c=3.5, pressure_bar=35.0)

        expected_a = (48.884 + 48.783 + 48.576 + 48.475) / 4.0
        expected_b = (-48.334 - 45.188 - 31.242 - 28.227) / 4.0
        self.assertTrue(isclose(point.a_micro_per_bar, expected_a, rel_tol=1e-12))
        self.assertTrue(isclose(point.b_micro_per_c, expected_b, rel_tol=1e-12))
        self.assertIn("bilinear interpolation", point.source_note)

    def test_botas_lookup_matches_control_table_lookup(self) -> None:
        for temp_c, pressure_bar in ((10.0, 50.0), (1.0, 30.0), (3.5, 35.0), (24.0, 119.0)):
            botas = lookup_botas_reference_point(temp_c=temp_c, pressure_bar=pressure_bar)
            control = lookup_ab_control_point(temp_c=temp_c, pressure_bar=pressure_bar)

            self.assertEqual(botas.temp_c, control.temp_c)
            self.assertEqual(botas.pressure_bar, control.pressure_bar)
            self.assertTrue(isclose(botas.a_micro_per_bar, control.a_micro_per_bar, rel_tol=1e-12))
            self.assertTrue(isclose(botas.b_micro_per_c, control.b_micro_per_c, rel_tol=1e-12))

    def test_botas_rejects_26c_while_gail_still_serves_it(self) -> None:
        with self.assertRaises(ABControlTableError):
            lookup_botas_reference_point(temp_c=26.0, pressure_bar=30.0)

        gail_point = lookup_gail_reference_point(temp_c=26.0, pressure_bar=30.0)
        self.assertEqual(gail_point.temp_c, 26.0)
        self.assertEqual(gail_point.pressure_bar, 30.0)
        self.assertIn("GAIL", gail_point.source_note)
        self.assertTrue(40.0 < gail_point.a_micro_per_bar < 50.0)

    def test_botas_and_gail_are_not_identical(self) -> None:
        comparison = compare_reference_b_sources(temp_c=10.0, pressure_bar=50.0)

        self.assertTrue(isclose(comparison.control_point.b_micro_per_c, 64.923, rel_tol=1e-12))
        self.assertTrue(isclose(comparison.gail_point.b_micro_per_c, 60.45, rel_tol=1e-12))
        self.assertTrue(isclose(comparison.b_delta, 64.923 - 60.45, rel_tol=1e-12))
        self.assertGreater(comparison.b_delta, 1.0)
        self.assertFalse(isclose(comparison.a_delta, 0.0, abs_tol=1e-6))

    def test_comparison_requires_both_tables_in_range(self) -> None:
        with self.assertRaises(ABControlTableError):
            compare_reference_b_sources(temp_c=26.0, pressure_bar=30.0)

    def test_dead_botas_reference_files_are_gone(self) -> None:
        self.assertFalse((_DATA_DIR / "botas_reference_table_v1.csv").exists())
        self.assertFalse((_DATA_DIR / "botas_reference_table_v1.meta.json").exists())
        self.assertNotEqual(
            Path(BOTAS_REFERENCE_TABLE_CSV_PATH).name,
            "botas_reference_table_v1.csv",
        )


if __name__ == "__main__":
    unittest.main()

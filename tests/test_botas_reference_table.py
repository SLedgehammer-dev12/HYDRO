from __future__ import annotations

import unittest
from math import isclose

from hidrostatik_test.data import (
    BOTAS_REFERENCE_OPTION_LABEL,
    describe_botas_reference_table_range,
    is_botas_reference_option,
    lookup_botas_reference_point,
)


class BotasReferenceTableTests(unittest.TestCase):
    def test_option_label_is_detected(self) -> None:
        self.assertTrue(is_botas_reference_option(BOTAS_REFERENCE_OPTION_LABEL))

    def test_range_description_matches_botas_reference_grid(self) -> None:
        self.assertEqual(describe_botas_reference_table_range(), "T=1-25 degC ve P=30-120 bar")

    def test_exact_grid_node_matches_botas_reference_value(self) -> None:
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


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from math import isclose

from hidrostatik_test.data import (
    ABControlTableError,
    describe_ab_control_table_range,
    lookup_ab_control_point,
)


class ABControlTableTests(unittest.TestCase):
    def test_range_description_matches_imported_excel_grid(self) -> None:
        self.assertEqual(describe_ab_control_table_range(), "T=1-25 degC ve P=30-120 bar")

    def test_exact_grid_node_matches_imported_workbook_value(self) -> None:
        point = lookup_ab_control_point(temp_c=10.0, pressure_bar=30.0)

        self.assertTrue(isclose(point.a_micro_per_bar, 46.99, rel_tol=1e-12))
        self.assertTrue(isclose(point.b_micro_per_c, 60.316, rel_tol=1e-12))
        self.assertIn("exact grid", point.source_note)

    def test_midpoint_uses_bilinear_interpolation(self) -> None:
        point = lookup_ab_control_point(temp_c=1.5, pressure_bar=30.5)

        expected_a = (49.54 + 49.205 + 49.53 + 49.195) / 4.0
        expected_b = (-84.373 - 66.032 - 84.0311 - 65.704) / 4.0
        self.assertTrue(isclose(point.a_micro_per_bar, expected_a, rel_tol=1e-12))
        self.assertTrue(isclose(point.b_micro_per_c, expected_b, rel_tol=1e-12))
        self.assertIn("bilinear interpolation", point.source_note)

    def test_out_of_range_lookup_raises_error(self) -> None:
        with self.assertRaises(ABControlTableError):
            lookup_ab_control_point(temp_c=26.0, pressure_bar=30.0)


if __name__ == "__main__":
    unittest.main()

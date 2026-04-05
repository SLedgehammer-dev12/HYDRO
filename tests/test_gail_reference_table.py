from __future__ import annotations

import unittest
from math import isclose

from hidrostatik_test.data import (
    GAIL_REFERENCE_OPTION_LABEL,
    describe_gail_reference_table_range,
    is_gail_reference_option,
    lookup_gail_reference_point,
)


class GailReferenceTableTests(unittest.TestCase):
    def test_option_label_is_detected(self) -> None:
        self.assertTrue(is_gail_reference_option(GAIL_REFERENCE_OPTION_LABEL))

    def test_range_description_matches_gail_reference_grid(self) -> None:
        self.assertEqual(describe_gail_reference_table_range(), "T=2-30 degC ve P=30-120 bar")

    def test_exact_grid_node_matches_gail_reference_value(self) -> None:
        point = lookup_gail_reference_point(temp_c=10.0, pressure_bar=50.0)

        self.assertTrue(isclose(point.a_micro_per_bar, 46.82427, rel_tol=1e-12))
        self.assertTrue(isclose(point.b_micro_per_c, 60.45, rel_tol=1e-12))
        self.assertIn("GAIL", point.source_note)

    def test_midpoint_uses_bilinear_interpolation(self) -> None:
        point = lookup_gail_reference_point(temp_c=3.0, pressure_bar=35.0)

        expected_a = (49.172955 + 49.090833 + 48.565253 + 48.483131) / 4.0
        expected_b = (-70.4 - 67.12 - 35.63 - 32.62) / 4.0
        self.assertTrue(isclose(point.a_micro_per_bar, expected_a, rel_tol=1e-12))
        self.assertTrue(isclose(point.b_micro_per_c, expected_b, rel_tol=1e-12))
        self.assertIn("bilinear interpolation", point.source_note)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from hidrostatik_test.data.coefficient_reference import (
    REFERENCE_POINTS,
    find_reference_point,
    get_reference_option_labels,
)


class CoefficientReferenceTests(unittest.TestCase):
    def test_reference_points_are_unique_and_well_formed(self) -> None:
        self.assertGreaterEqual(len(REFERENCE_POINTS), 3)
        keys = [point.key for point in REFERENCE_POINTS]
        labels = [point.label for point in REFERENCE_POINTS]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(labels), len(set(labels)))
        for point in REFERENCE_POINTS:
            self.assertGreater(point.a_micro_per_bar, 0.0)
            self.assertGreater(point.water_beta_micro_per_c, 0.0)
            self.assertGreater(point.pressure_bar, 0.0)
            self.assertIn("IAPWS", point.source_note)

    def test_lookup_accepts_exact_labels_only(self) -> None:
        labels = get_reference_option_labels()
        self.assertEqual(find_reference_point(labels[0]).key, REFERENCE_POINTS[0].key)
        self.assertIsNone(find_reference_point("olmayan etiket"))
        self.assertIsNone(find_reference_point(""))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from hidrostatik_test.ui import constants


class UiConstantsTests(unittest.TestCase):
    def test_field_checklist_is_canonical_and_unique(self) -> None:
        definitions = constants.FIELD_CHECK_DEFINITIONS
        self.assertEqual(len(definitions), 11)
        keys = [item[0] for item in definitions]
        self.assertEqual(len(keys), len(set(keys)))
        references = {item[2] for item in definitions}
        for expected in ("10.1", "14.2", "14.3", "15.1", "16-17", "21"):
            self.assertIn(expected, references)

    def test_mode_aliases_are_consistent(self) -> None:
        self.assertEqual(constants.REFERENCE_A_MODE, constants.TABLE_A_MODE)
        self.assertEqual(constants.REFERENCE_B_MODE, constants.TABLE_B_MODE)
        self.assertEqual(constants.AUTO_A_MODE, constants.AUTO_B_MODE)
        self.assertEqual(constants.MANUAL_A_MODE, constants.MANUAL_B_MODE)

    def test_field_ranges_are_ordered_and_include_negative_b(self) -> None:
        for field_key, (minimum, maximum) in constants.FIELD_VALUE_RANGES.items():
            self.assertLess(minimum, maximum, field_key)
        b_min, b_max = constants.FIELD_VALUE_RANGES["pressure.b_micro_per_c"]
        self.assertLess(b_min, 0.0)
        self.assertGreater(b_max, 0.0)

    def test_default_decision_is_pending(self) -> None:
        self.assertEqual(constants.DEFAULT_DECISION_STATUS, "BEKLIYOR")
        self.assertTrue(constants.DEFAULT_DECISION_TITLE)
        self.assertTrue(constants.DEFAULT_DECISION_SUMMARY)

    def test_acceptance_rules_are_single_source_of_truth(self) -> None:
        self.assertEqual(constants.AIR_ACCEPTANCE_RULE, "Vpa < 1.06 x Vp")
        self.assertEqual(constants.PRESSURE_ACCEPTANCE_RULE, "(Pa - Pt) <= 0.3 bar")

    def test_required_field_sets_start_with_geometry_and_have_labels(self) -> None:
        for fields in (
            constants.AIR_REQUIRED_FIELDS,
            constants.PRESSURE_REQUIRED_FIELDS,
        ):
            self.assertEqual(
                tuple(fields[: len(constants.GEOMETRY_REQUIRED_FIELDS)]),
                constants.GEOMETRY_REQUIRED_FIELDS,
            )
        self.assertIn("air.actual_added_water_m3", constants.AIR_REQUIRED_FIELDS)
        self.assertIn("pressure.delta_t_c", constants.PRESSURE_REQUIRED_FIELDS)
        self.assertEqual(constants.REQUIRED_FIELD_LABELS["air.a_micro_per_bar"], "A")
        self.assertEqual(constants.REQUIRED_FIELD_LABELS["air.actual_added_water_m3"], "Vpa")
        for field_key in (
            *constants.AIR_REQUIRED_FIELDS,
            *constants.PRESSURE_REQUIRED_FIELDS,
            *constants.PIG_REQUIRED_FIELDS,
        ):
            self.assertIn(field_key, constants.REQUIRED_FIELD_LABELS)
        self.assertEqual(constants.REQUIRED_FIELD_HINT, "* = zorunlu")


if __name__ == "__main__":
    unittest.main()

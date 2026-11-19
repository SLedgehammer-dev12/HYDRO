from __future__ import annotations

import unittest

from hidrostatik_test.domain import ValidationError
from hidrostatik_test.domain.operations import (
    evaluate_fill_temperature,
    evaluate_pig_speed,
    get_pig_speed_limit,
    get_pig_speed_limit_options,
)


class PigSpeedOperationTests(unittest.TestCase):
    def test_cleaning_pig_speed_passes_when_below_limit(self) -> None:
        limit = get_pig_speed_limit(get_pig_speed_limit_options()[0])

        result = evaluate_pig_speed(distance_m=1000, travel_time_min=8, limit=limit)

        self.assertAlmostEqual(result.speed_m_per_s, 2.0833333333)
        self.assertTrue(result.passed)

    def test_final_drying_pig_speed_fails_when_limit_exceeded(self) -> None:
        limit = get_pig_speed_limit(get_pig_speed_limit_options()[2])

        result = evaluate_pig_speed(distance_m=1000, travel_time_min=10, limit=limit)

        self.assertGreater(result.speed_m_per_s, 1.2)
        self.assertFalse(result.passed)

    def test_invalid_pig_speed_inputs_raise_validation_error(self) -> None:
        limit = get_pig_speed_limit(get_pig_speed_limit_options()[0])

        with self.assertRaises(ValidationError):
            evaluate_pig_speed(distance_m=0, travel_time_min=5, limit=limit)


class FillTemperatureOperationTests(unittest.TestCase):
    def test_fill_temperature_passes_at_and_above_two_celsius(self) -> None:
        for temp in (2.0, 12.5):
            result = evaluate_fill_temperature(temp)
            self.assertTrue(result.passed)
            self.assertEqual(result.status, "UYGUN")
            self.assertEqual(result.spec_reference, "Madde 10.1")

    def test_fill_temperature_warns_below_two_celsius(self) -> None:
        for temp in (1.9, -5.0):
            result = evaluate_fill_temperature(temp)
            self.assertFalse(result.passed)
            self.assertEqual(result.status, "UYARI")
            self.assertIn("10.1", result.message)

    def test_fill_temperature_rejects_non_finite_or_unphysical_values(self) -> None:
        for bad in (float("nan"), float("inf"), -274.0):
            with self.assertRaises(ValidationError):
                evaluate_fill_temperature(bad)

    def test_fill_temperature_rejects_booleans(self) -> None:
        for bad in (True, False):
            with self.assertRaises(ValidationError):
                evaluate_fill_temperature(bad)


if __name__ == "__main__":
    unittest.main()

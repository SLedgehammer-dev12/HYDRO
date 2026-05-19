from __future__ import annotations

import unittest

from hidrostatik_test.domain import ValidationError
from hidrostatik_test.domain.operations import evaluate_pig_speed, get_pig_speed_limit, get_pig_speed_limit_options


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


if __name__ == "__main__":
    unittest.main()

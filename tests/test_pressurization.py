from __future__ import annotations

import unittest
from math import isclose

from hidrostatik_test.domain.pressurization import (
    PressurizationInputs,
    PressurizationResult,
    ValidationError,
    evaluate_pressurization,
)


class PressurizationTests(unittest.TestCase):
    def test_pressurization_pass_case(self) -> None:
        inputs = PressurizationInputs(
            initial_volume_m3=100.0,
            added_volume_m3=0.15,
            theoretical_volume_m3=100.15,
            pressure_bar=50.0,
            expected_pressure_bar=50.0,
        )

        result = evaluate_pressurization(inputs)

        self.assertTrue(result.passed)
        self.assertTrue(result.within_volume_limit)
        self.assertTrue(result.within_pressure_limit)
        self.assertTrue(isclose(result.volume_deviation_percent, 0.0, abs_tol=1e-6))
        self.assertTrue(isclose(result.pressure_deviation_bar, 0.0, abs_tol=1e-6))

    def test_pressurization_volume_deviation_exceeds_limit(self) -> None:
        inputs = PressurizationInputs(
            initial_volume_m3=100.0,
            added_volume_m3=0.5,
            theoretical_volume_m3=100.15,
            pressure_bar=50.0,
            expected_pressure_bar=50.0,
        )

        result = evaluate_pressurization(inputs)

        self.assertFalse(result.passed)
        self.assertFalse(result.within_volume_limit)
        self.assertGreater(result.volume_deviation_percent, 0.2)

    def test_pressurization_pressure_deviation(self) -> None:
        inputs = PressurizationInputs(
            initial_volume_m3=100.0,
            added_volume_m3=0.15,
            theoretical_volume_m3=100.15,
            pressure_bar=51.0,
            expected_pressure_bar=50.0,
        )

        result = evaluate_pressurization(inputs)

        self.assertFalse(result.passed)
        self.assertTrue(result.within_volume_limit)
        self.assertFalse(result.within_pressure_limit)
        self.assertTrue(isclose(result.pressure_deviation_bar, 1.0, abs_tol=1e-6))

    def test_invalid_initial_volume_raises_validation_error(self) -> None:
        with self.assertRaises(ValidationError):
            PressurizationInputs(
                initial_volume_m3=0,
                added_volume_m3=0.15,
                theoretical_volume_m3=100.15,
                pressure_bar=50.0,
                expected_pressure_bar=50.0,
            )

    def test_negative_added_volume_raises_validation_error(self) -> None:
        with self.assertRaises(ValidationError):
            PressurizationInputs(
                initial_volume_m3=100.0,
                added_volume_m3=-0.1,
                theoretical_volume_m3=100.15,
                pressure_bar=50.0,
                expected_pressure_bar=50.0,
            )


if __name__ == "__main__":
    unittest.main()

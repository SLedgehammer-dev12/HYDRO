from __future__ import annotations

import unittest
from math import isclose

from hidrostatik_test.domain.pressurization import (
    PressurizationInputs,
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

    def test_exact_point_two_percent_excess_passes(self) -> None:
        inputs = PressurizationInputs(
            initial_volume_m3=99.8,
            added_volume_m3=0.2,
            theoretical_volume_m3=99.8,
            pressure_bar=50.0,
            expected_pressure_bar=50.0,
        )

        result = evaluate_pressurization(inputs)

        self.assertTrue(result.within_volume_limit)
        self.assertTrue(result.passed)
        self.assertTrue(isclose(result.volume_deviation_percent, 0.2, abs_tol=1e-9))
        self.assertFalse(result.underfilled)

    def test_excess_water_above_point_two_percent_fails(self) -> None:
        inputs = PressurizationInputs(
            initial_volume_m3=99.8,
            added_volume_m3=0.25,
            theoretical_volume_m3=99.8,
            pressure_bar=50.0,
            expected_pressure_bar=50.0,
        )

        result = evaluate_pressurization(inputs)

        self.assertFalse(result.within_volume_limit)
        self.assertFalse(result.passed)
        self.assertGreater(result.volume_deviation_percent, 0.2)
        self.assertFalse(result.underfilled)

    def test_underfilled_volume_is_reported_separately(self) -> None:
        inputs = PressurizationInputs(
            initial_volume_m3=100.0,
            added_volume_m3=0.1,
            theoretical_volume_m3=100.5,
            pressure_bar=50.0,
            expected_pressure_bar=50.0,
        )

        result = evaluate_pressurization(inputs)

        # Eksik doldurma "fazla su" limitini ihlal etmez; ayri uyari olarak raporlanir.
        self.assertTrue(result.within_volume_limit)
        self.assertTrue(result.underfilled)
        self.assertGreater(result.volume_shortfall_percent, 0.0)
        self.assertLess(result.volume_deviation_percent, 0.0)
        self.assertTrue(result.passed)

    def test_pressure_tolerance_is_fifty_millibar_at_fifty_bar(self) -> None:
        within = evaluate_pressurization(
            PressurizationInputs(
                initial_volume_m3=100.0,
                added_volume_m3=0.15,
                theoretical_volume_m3=100.15,
                pressure_bar=50.05,
                expected_pressure_bar=50.0,
            )
        )
        outside = evaluate_pressurization(
            PressurizationInputs(
                initial_volume_m3=100.0,
                added_volume_m3=0.15,
                theoretical_volume_m3=100.15,
                pressure_bar=50.0500001,
                expected_pressure_bar=50.0,
            )
        )

        self.assertTrue(isclose(within.pressure_tolerance_bar, 0.05, abs_tol=1e-12))
        self.assertTrue(within.within_pressure_limit)
        self.assertFalse(outside.within_pressure_limit)

    def test_pressure_tolerance_scales_with_expected_pressure(self) -> None:
        within = evaluate_pressurization(
            PressurizationInputs(
                initial_volume_m3=100.0,
                added_volume_m3=0.15,
                theoretical_volume_m3=100.15,
                pressure_bar=200.15,
                expected_pressure_bar=200.0,
            )
        )
        outside = evaluate_pressurization(
            PressurizationInputs(
                initial_volume_m3=100.0,
                added_volume_m3=0.15,
                theoretical_volume_m3=100.15,
                pressure_bar=200.25,
                expected_pressure_bar=200.0,
            )
        )

        self.assertTrue(isclose(within.pressure_tolerance_bar, 0.2, abs_tol=1e-12))
        self.assertTrue(within.within_pressure_limit)
        self.assertFalse(outside.within_pressure_limit)

    def test_non_finite_inputs_are_rejected(self) -> None:
        base_payload = {
            "initial_volume_m3": 100.0,
            "added_volume_m3": 0.15,
            "theoretical_volume_m3": 100.15,
            "pressure_bar": 50.0,
            "expected_pressure_bar": 50.0,
        }
        invalid_values = (
            ("initial_volume_m3", float("nan")),
            ("added_volume_m3", float("inf")),
            ("theoretical_volume_m3", 1e999),
            ("pressure_bar", float("nan")),
            ("expected_pressure_bar", float("inf")),
        )

        for field_name, value in invalid_values:
            payload = dict(base_payload)
            payload[field_name] = value
            with self.subTest(field_name=field_name, value=value):
                with self.assertRaises(ValidationError):
                    PressurizationInputs(**payload)

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

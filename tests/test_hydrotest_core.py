from __future__ import annotations

import unittest
from dataclasses import replace
from math import isclose

from hidrostatik_test.domain.hydrotest_core import (
    AirContentInputs,
    PipeGeometry,
    PipeSection,
    PressureVariationInputs,
    ValidationError,
    calculate_b_coefficient,
    calculate_water_compressibility_a,
    calculate_water_thermal_expansion_beta,
    evaluate_air_content_test,
    evaluate_pressure_variation_test,
    scale_expansion_coefficient_k_to_micro_per_c,
    scale_isothermal_compressibility_pa_to_micro_per_bar,
)


class PipeSectionTests(unittest.TestCase):
    def test_internal_radius_and_volume_use_internal_geometry(self) -> None:
        section = PipeSection(outside_diameter_mm=406.4, wall_thickness_mm=8.74, length_m=1000)

        self.assertTrue(isclose(section.internal_radius_mm, 194.46, rel_tol=1e-6))
        self.assertTrue(isclose(section.internal_volume_m3, 118.79835732832362, rel_tol=1e-9))

    def test_invalid_wall_thickness_raises_validation_error(self) -> None:
        with self.assertRaises(ValidationError):
            PipeSection(outside_diameter_mm=100, wall_thickness_mm=60, length_m=10)

    def test_segmented_geometry_aggregates_length_volume_and_elasticity(self) -> None:
        geometry = PipeGeometry(
            sections=(
                PipeSection(outside_diameter_mm=406.4, wall_thickness_mm=8.74, length_m=500),
                PipeSection(outside_diameter_mm=406.4, wall_thickness_mm=12.7, length_m=500),
            )
        )

        self.assertTrue(isclose(geometry.total_length_m, 1000.0, rel_tol=1e-12))
        self.assertGreater(geometry.internal_volume_m3, 0.0)
        self.assertGreater(geometry.elasticity_term, 0.0)
        self.assertLess(
            geometry.elasticity_term,
            PipeSection(
                outside_diameter_mm=406.4, wall_thickness_mm=8.74, length_m=1000
            ).elasticity_term,
        )

    def test_non_finite_section_inputs_are_rejected(self) -> None:
        invalid_sections = (
            {"outside_diameter_mm": float("nan"), "wall_thickness_mm": 8.74, "length_m": 10.0},
            {"outside_diameter_mm": float("inf"), "wall_thickness_mm": 8.74, "length_m": 10.0},
            {"outside_diameter_mm": 406.4, "wall_thickness_mm": float("nan"), "length_m": 10.0},
            {"outside_diameter_mm": 406.4, "wall_thickness_mm": 8.74, "length_m": 1e999},
        )

        for payload in invalid_sections:
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError):
                    PipeSection(**payload)


class AirContentTests(unittest.TestCase):
    def test_air_content_pass_case(self) -> None:
        inputs = AirContentInputs(
            pipe=PipeSection(outside_diameter_mm=406.4, wall_thickness_mm=8.74, length_m=1000),
            a_micro_per_bar=45.0,
            pressure_rise_bar=1.0,
            k_factor=1.02,
            actual_added_water_m3=0.0079,
        )

        result = evaluate_air_content_test(inputs)

        self.assertTrue(result.passed)
        self.assertTrue(
            isclose(result.theoretical_added_water_m3, 0.00783616110908747, rel_tol=1e-9)
        )
        self.assertTrue(isclose(result.acceptance_limit_m3, 0.008306330775632718, rel_tol=1e-9))

    def test_air_content_fail_case(self) -> None:
        inputs = AirContentInputs(
            pipe=PipeSection(outside_diameter_mm=406.4, wall_thickness_mm=8.74, length_m=1000),
            a_micro_per_bar=45.0,
            pressure_rise_bar=1.0,
            k_factor=1.02,
            actual_added_water_m3=0.0085,
        )

        result = evaluate_air_content_test(inputs)

        self.assertFalse(result.passed)

    def test_air_content_requires_one_bar_pressure_rise(self) -> None:
        with self.assertRaises(ValidationError):
            AirContentInputs(
                pipe=PipeSection(outside_diameter_mm=406.4, wall_thickness_mm=8.74, length_m=1000),
                a_micro_per_bar=45.0,
                pressure_rise_bar=0.8,
                k_factor=1.02,
                actual_added_water_m3=0.0079,
            )

    def test_air_content_exact_six_percent_limit_fails(self) -> None:
        base_inputs = AirContentInputs(
            pipe=PipeSection(outside_diameter_mm=406.4, wall_thickness_mm=8.74, length_m=1000),
            a_micro_per_bar=45.0,
            pressure_rise_bar=1.0,
            k_factor=1.02,
            actual_added_water_m3=0.0,
        )
        acceptance_limit = evaluate_air_content_test(base_inputs).acceptance_limit_m3

        at_limit = evaluate_air_content_test(
            replace(base_inputs, actual_added_water_m3=acceptance_limit)
        )
        just_below_limit = evaluate_air_content_test(
            replace(base_inputs, actual_added_water_m3=acceptance_limit - 1e-6)
        )

        # Sartname "%6 veya daha fazla" ilaveyi reddeder.
        self.assertFalse(at_limit.passed)
        self.assertTrue(isclose(at_limit.ratio, 1.06, rel_tol=1e-12))
        self.assertTrue(just_below_limit.passed)

    def test_non_finite_air_content_inputs_are_rejected(self) -> None:
        base_payload = {
            "pipe": PipeSection(outside_diameter_mm=406.4, wall_thickness_mm=8.74, length_m=1000),
            "a_micro_per_bar": 45.0,
            "pressure_rise_bar": 1.0,
            "k_factor": 1.02,
            "actual_added_water_m3": 0.0079,
        }
        invalid_values = (
            ("a_micro_per_bar", float("nan")),
            ("a_micro_per_bar", float("inf")),
            ("pressure_rise_bar", float("nan")),
            ("pressure_rise_bar", float("inf")),
            ("k_factor", float("nan")),
            ("k_factor", float("inf")),
            ("actual_added_water_m3", float("nan")),
            ("actual_added_water_m3", 1e999),
        )

        for field_name, value in invalid_values:
            payload = dict(base_payload)
            payload[field_name] = value
            with self.subTest(field_name=field_name, value=value):
                with self.assertRaises(ValidationError):
                    AirContentInputs(**payload)


class PressureVariationTests(unittest.TestCase):
    def test_pressure_variation_pass_case(self) -> None:
        inputs = PressureVariationInputs(
            pipe=PipeSection(outside_diameter_mm=406.4, wall_thickness_mm=8.74, length_m=1000),
            a_micro_per_bar=45.0,
            b_micro_per_c=200.0,
            delta_t_c=0.6,
            actual_pressure_change_bar=2.10,
        )

        result = evaluate_pressure_variation_test(inputs)

        self.assertTrue(result.passed)
        self.assertTrue(
            isclose(result.theoretical_pressure_change_bar, 1.8556176595353482, rel_tol=1e-9)
        )
        self.assertTrue(isclose(result.margin_bar, 0.24438234046465192, rel_tol=1e-9))

    def test_pressure_variation_fail_case(self) -> None:
        inputs = PressureVariationInputs(
            pipe=PipeSection(outside_diameter_mm=406.4, wall_thickness_mm=8.74, length_m=1000),
            a_micro_per_bar=45.0,
            b_micro_per_c=200.0,
            delta_t_c=0.6,
            actual_pressure_change_bar=2.30,
        )

        result = evaluate_pressure_variation_test(inputs)

        self.assertFalse(result.passed)

    def test_pressure_variation_exact_three_tenths_margin_passes(self) -> None:
        base_inputs = PressureVariationInputs(
            pipe=PipeSection(outside_diameter_mm=406.4, wall_thickness_mm=8.74, length_m=1000),
            a_micro_per_bar=45.0,
            b_micro_per_c=200.0,
            delta_t_c=0.6,
            actual_pressure_change_bar=0.0,
        )
        theoretical = evaluate_pressure_variation_test(base_inputs).theoretical_pressure_change_bar

        at_limit = evaluate_pressure_variation_test(
            replace(base_inputs, actual_pressure_change_bar=theoretical + 0.3)
        )
        above_limit = evaluate_pressure_variation_test(
            replace(base_inputs, actual_pressure_change_bar=theoretical + 0.3000001)
        )

        self.assertTrue(at_limit.passed)
        self.assertTrue(isclose(at_limit.margin_bar, 0.3, abs_tol=1e-9))
        self.assertFalse(above_limit.passed)

    def test_negative_b_below_four_celsius_is_accepted_and_preserved(self) -> None:
        beta_value = calculate_water_thermal_expansion_beta(temp_c=2.0, pressure_bar=50.0)
        self.assertLess(beta_value, 0.0)

        b_value = calculate_b_coefficient(beta_value, 12.0)
        self.assertLess(b_value, 0.0)
        self.assertTrue(isclose(b_value, beta_value - 12.0, rel_tol=0.0, abs_tol=1e-12))

        inputs = PressureVariationInputs(
            pipe=PipeSection(outside_diameter_mm=406.4, wall_thickness_mm=8.74, length_m=1000),
            a_micro_per_bar=45.0,
            b_micro_per_c=b_value,
            delta_t_c=1.0,
            actual_pressure_change_bar=0.0,
        )
        result = evaluate_pressure_variation_test(inputs)

        self.assertLess(result.theoretical_pressure_change_bar, 0.0)

    def test_non_finite_pressure_variation_inputs_are_rejected(self) -> None:
        base_payload = {
            "pipe": PipeSection(outside_diameter_mm=406.4, wall_thickness_mm=8.74, length_m=1000),
            "a_micro_per_bar": 45.0,
            "b_micro_per_c": 200.0,
            "delta_t_c": 0.6,
            "actual_pressure_change_bar": 2.10,
        }
        invalid_values = (
            ("a_micro_per_bar", float("nan")),
            ("a_micro_per_bar", float("inf")),
            ("b_micro_per_c", float("nan")),
            ("b_micro_per_c", 1e999),
            ("delta_t_c", float("nan")),
            ("delta_t_c", float("inf")),
            ("actual_pressure_change_bar", float("nan")),
            ("actual_pressure_change_bar", 1e999),
        )

        for field_name, value in invalid_values:
            payload = dict(base_payload)
            payload[field_name] = value
            with self.subTest(field_name=field_name, value=value):
                with self.assertRaises(ValidationError):
                    PressureVariationInputs(**payload)


class CompressibilityScaleTests(unittest.TestCase):
    def test_scale_conversion_matches_micro_per_bar_convention(self) -> None:
        scaled = scale_isothermal_compressibility_pa_to_micro_per_bar(4.497199356927445e-10)
        self.assertTrue(isclose(scaled, 44.97199356927445, rel_tol=1e-12))

    def test_thermal_expansion_scale_matches_micro_per_degree_convention(self) -> None:
        scaled = scale_expansion_coefficient_k_to_micro_per_c(2.1829719116700635e-4)
        self.assertTrue(isclose(scaled, 218.29719116700636, rel_tol=1e-12))


class BCoefficientTests(unittest.TestCase):
    def test_b_coefficient_is_water_minus_steel(self) -> None:
        self.assertTrue(
            isclose(calculate_b_coefficient(218.29719116700636, 12.0), 206.29719116700636)
        )

    def test_negative_b_coefficient_is_allowed(self) -> None:
        self.assertEqual(calculate_b_coefficient(-50.0, 12.0), -62.0)
        self.assertEqual(calculate_b_coefficient(0.0, 12.0), -12.0)

    def test_b_coefficient_rejects_non_finite_inputs(self) -> None:
        invalid_pairs = (
            (float("nan"), 12.0),
            (float("inf"), 12.0),
            (1e999, 12.0),
            (100.0, float("nan")),
            (100.0, float("inf")),
        )

        for beta_value, alpha_value in invalid_pairs:
            with self.subTest(beta_value=beta_value, alpha_value=alpha_value):
                with self.assertRaises(ValidationError):
                    calculate_b_coefficient(beta_value, alpha_value)

    def test_b_coefficient_rejects_negative_steel_alpha(self) -> None:
        with self.assertRaises(ValidationError):
            calculate_b_coefficient(100.0, -1.0)

    def test_water_property_reference_points_match_iapws95_cross_check(self) -> None:
        # Reference values were cross-checked against an independent IAPWS-95 implementation.
        reference_points = (
            (10.0, 50.0, 47.193088967078, 99.621630836736, 87.621630836736),
            (15.0, 80.0, 45.786845210898, 165.612819003945, 153.612819003945),
            (20.0, 100.0, 44.744088115012, 221.153338084596, 209.153338084596),
        )

        for temp_c, pressure_bar, expected_a, expected_beta, expected_b in reference_points:
            with self.subTest(temp_c=temp_c, pressure_bar=pressure_bar, backend="coolprop"):
                a_value = calculate_water_compressibility_a(
                    temp_c=temp_c, pressure_bar=pressure_bar
                )
                beta_value = calculate_water_thermal_expansion_beta(
                    temp_c=temp_c, pressure_bar=pressure_bar
                )
                b_value = calculate_b_coefficient(beta_value, 12.0)

                self.assertTrue(isclose(a_value, expected_a, rel_tol=1e-9))
                self.assertTrue(isclose(beta_value, expected_beta, rel_tol=1e-9))
                self.assertTrue(isclose(b_value, expected_b, rel_tol=1e-9))

        try:
            from hidrostatik_test.domain.water_properties import IAPWS95WaterPropertyBackend

            iapws_backend = IAPWS95WaterPropertyBackend()
        except (ImportError, Exception):
            iapws_backend = None

        if iapws_backend is not None:
            for temp_c, pressure_bar, expected_a, expected_beta, expected_b in reference_points:
                with self.subTest(temp_c=temp_c, pressure_bar=pressure_bar, backend="iapws95"):
                    a_value = calculate_water_compressibility_a(
                        temp_c=temp_c, pressure_bar=pressure_bar, backend=iapws_backend
                    )
                    beta_value = calculate_water_thermal_expansion_beta(
                        temp_c=temp_c, pressure_bar=pressure_bar, backend=iapws_backend
                    )
                    b_value = calculate_b_coefficient(beta_value, 12.0)

                    self.assertTrue(isclose(a_value, expected_a, rel_tol=1e-6))
                    self.assertTrue(isclose(beta_value, expected_beta, rel_tol=1e-6))
                    self.assertTrue(isclose(b_value, expected_b, rel_tol=1e-6))


class WaterPropertyValidationTests(unittest.TestCase):
    def test_zero_pressure_is_rejected_for_a_calculation(self) -> None:
        with self.assertRaises(ValidationError):
            calculate_water_compressibility_a(temp_c=20.0, pressure_bar=0.0)

    def test_zero_pressure_is_rejected_for_beta_calculation(self) -> None:
        with self.assertRaises(ValidationError):
            calculate_water_thermal_expansion_beta(temp_c=20.0, pressure_bar=0.0)

    def test_beta_can_be_negative_near_zero_celsius(self) -> None:
        beta_value = calculate_water_thermal_expansion_beta(temp_c=0.01, pressure_bar=1.0)
        self.assertLess(beta_value, 0.0)


if __name__ == "__main__":
    unittest.main()

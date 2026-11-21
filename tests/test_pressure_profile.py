from __future__ import annotations

import unittest
from math import isclose

from hidrostatik_test.domain import (
    MAX_TEST_SECTION_LENGTH_M,
    MAX_TEST_SECTION_VOLUME_M3,
    START_PUMP_LOCATION,
    PipeGeometry,
    PipeSection,
    SectionPressureProfileInputs,
    ValidationError,
    evaluate_section_pressure_profile,
    get_location_class_rule,
)


class PressureProfileTests(unittest.TestCase):
    def test_start_pump_window_uses_location_class_and_hydraulic_head(self) -> None:
        result = evaluate_section_pressure_profile(
            SectionPressureProfileInputs(
                pipe=PipeSection(
                    outside_diameter_mm=406.4, wall_thickness_mm=8.74, length_m=1000.0
                ),
                design_pressure_bar=20.0,
                smys_mpa=100.0,
                location_class=get_location_class_rule("Class 1 - min 1.25 x dizayn basinci"),
                highest_elevation_m=100.0,
                lowest_elevation_m=0.0,
                start_elevation_m=0.0,
                end_elevation_m=100.0,
                selected_pump_location=START_PUMP_LOCATION,
                monitored_pressure_bar=35.0,
            )
        )

        self.assertTrue(
            isclose(result.required_minimum_pressure_at_high_point_bar, 25.0, rel_tol=1e-12)
        )
        self.assertTrue(isclose(result.hydraulic_span_bar, 9.797844, rel_tol=1e-6))
        self.assertTrue(isclose(result.required_pressure_with_span_bar, 34.797844, rel_tol=1e-6))
        self.assertTrue(
            isclose(result.start_window.minimum_required_pressure_bar, 34.797844, rel_tol=1e-6)
        )
        self.assertTrue(
            isclose(result.start_window.maximum_allowable_pressure_bar, 43.011811, rel_tol=1e-6)
        )
        self.assertTrue(result.within_100_smys_span_limit)
        self.assertTrue(result.within_length_limit)
        self.assertTrue(result.within_volume_limit)
        self.assertTrue(result.monitored_meets_minimum)
        self.assertTrue(result.monitored_under_maximum)
        self.assertTrue(result.feasible)

    def test_high_class_can_make_section_window_infeasible(self) -> None:
        result = evaluate_section_pressure_profile(
            SectionPressureProfileInputs(
                pipe=PipeSection(
                    outside_diameter_mm=406.4, wall_thickness_mm=8.74, length_m=1000.0
                ),
                design_pressure_bar=40.0,
                smys_mpa=100.0,
                location_class=get_location_class_rule("Class 3 - min 1.50 x dizayn basinci"),
                highest_elevation_m=100.0,
                lowest_elevation_m=0.0,
                start_elevation_m=0.0,
                end_elevation_m=100.0,
                selected_pump_location=START_PUMP_LOCATION,
            )
        )

        self.assertFalse(result.feasible)
        self.assertFalse(result.within_100_smys_span_limit)
        self.assertGreater(
            result.required_pressure_with_span_bar, result.limiting_pressure_at_100_smys_bar
        )

    def test_invalid_elevation_order_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            evaluate_section_pressure_profile(
                SectionPressureProfileInputs(
                    pipe=PipeSection(
                        outside_diameter_mm=406.4, wall_thickness_mm=8.74, length_m=1000.0
                    ),
                    design_pressure_bar=20.0,
                    smys_mpa=100.0,
                    location_class=get_location_class_rule("Class 2 - min 1.25 x dizayn basinci"),
                    highest_elevation_m=0.0,
                    lowest_elevation_m=100.0,
                    start_elevation_m=0.0,
                    end_elevation_m=100.0,
                    selected_pump_location=START_PUMP_LOCATION,
                )
            )

    def test_length_limit_is_reported(self) -> None:
        result = evaluate_section_pressure_profile(
            SectionPressureProfileInputs(
                pipe=PipeSection(
                    outside_diameter_mm=406.4,
                    wall_thickness_mm=8.74,
                    length_m=MAX_TEST_SECTION_LENGTH_M + 1.0,
                ),
                design_pressure_bar=20.0,
                smys_mpa=245.0,
                location_class=get_location_class_rule("Class 1 - min 1.25 x dizayn basinci"),
                highest_elevation_m=100.0,
                lowest_elevation_m=0.0,
                start_elevation_m=0.0,
                end_elevation_m=100.0,
                selected_pump_location=START_PUMP_LOCATION,
            )
        )

        self.assertFalse(result.within_length_limit)
        self.assertTrue(result.total_length_m > MAX_TEST_SECTION_LENGTH_M)
        self.assertFalse(result.feasible)

    def test_volume_limit_is_reported(self) -> None:
        result = evaluate_section_pressure_profile(
            SectionPressureProfileInputs(
                pipe=PipeSection(
                    outside_diameter_mm=1422.4,
                    wall_thickness_mm=12.7,
                    length_m=9000.0,
                ),
                design_pressure_bar=20.0,
                smys_mpa=485.0,
                location_class=get_location_class_rule("Class 1 - min 1.25 x dizayn basinci"),
                highest_elevation_m=100.0,
                lowest_elevation_m=0.0,
                start_elevation_m=0.0,
                end_elevation_m=100.0,
                selected_pump_location=START_PUMP_LOCATION,
            )
        )

        self.assertFalse(result.within_volume_limit)
        self.assertTrue(result.total_internal_volume_m3 > MAX_TEST_SECTION_VOLUME_M3)
        self.assertFalse(result.feasible)

    def test_segmented_pipe_uses_per_segment_smys_and_identifies_limiting_segment(self) -> None:
        # Segment 1: thinner wall (8.74 mm) but higher SMYS (450 MPa) -> 193.553 bar
        # Segment 2: thicker wall (10.31 mm) but lower SMYS (290 MPa, X42) -> 147.151 bar (governing!)
        pipe = PipeGeometry(
            sections=(
                PipeSection(
                    outside_diameter_mm=406.4,
                    wall_thickness_mm=8.74,
                    length_m=600.0,
                    smys_mpa=450.0,
                    material_grade="API 5L X65",
                ),
                PipeSection(
                    outside_diameter_mm=406.4,
                    wall_thickness_mm=10.31,
                    length_m=400.0,
                    smys_mpa=290.0,
                    material_grade="API 5L X42",
                ),
            )
        )
        result = evaluate_section_pressure_profile(
            SectionPressureProfileInputs(
                pipe=pipe,
                design_pressure_bar=100.0,
                smys_mpa=450.0,
                location_class=get_location_class_rule("Class 1 - min 1.25 x dizayn basinci"),
                highest_elevation_m=50.0,
                lowest_elevation_m=0.0,
                start_elevation_m=0.0,
                end_elevation_m=50.0,
                selected_pump_location=START_PUMP_LOCATION,
            )
        )
        expected_seg2 = 20.0 * 290.0 * 10.31 / 406.4
        self.assertTrue(
            isclose(result.limiting_pressure_at_100_smys_bar, expected_seg2, rel_tol=1e-9)
        )
        self.assertEqual(result.limiting_segment_index, 2)
        self.assertEqual(result.limiting_smys_mpa, 290.0)
        self.assertIn("Limit segment 2", result.limiting_pipe_description)
        self.assertIn("SMYS=290.0 MPa", result.limiting_pipe_description)
        self.assertIn("API 5L X42", result.limiting_pipe_description)

    def test_mixed_override_and_fallback_segment_smys(self) -> None:
        pipe = PipeGeometry(
            sections=(
                PipeSection(outside_diameter_mm=406.4, wall_thickness_mm=8.74, length_m=500.0),
                PipeSection(
                    outside_diameter_mm=406.4,
                    wall_thickness_mm=8.74,
                    length_m=500.0,
                    smys_mpa=320.0,
                ),
            )
        )
        result = evaluate_section_pressure_profile(
            SectionPressureProfileInputs(
                pipe=pipe,
                design_pressure_bar=80.0,
                smys_mpa=450.0,
                location_class=get_location_class_rule("Class 1 - min 1.25 x dizayn basinci"),
                highest_elevation_m=10.0,
                lowest_elevation_m=0.0,
                start_elevation_m=0.0,
                end_elevation_m=10.0,
                selected_pump_location=START_PUMP_LOCATION,
            )
        )
        self.assertEqual(result.limiting_segment_index, 2)
        self.assertEqual(result.limiting_smys_mpa, 320.0)
        self.assertTrue(
            isclose(
                result.limiting_pressure_at_100_smys_bar,
                20.0 * 320.0 * 8.74 / 406.4,
                rel_tol=1e-9,
            )
        )


if __name__ == "__main__":
    unittest.main()

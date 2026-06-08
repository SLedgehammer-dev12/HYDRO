from __future__ import annotations

import unittest

from hidrostatik_test.ui.validators import (
    safe_float,
    validate_elevation_inputs,
    validate_geometry_inputs,
)


class SafeFloatTests(unittest.TestCase):
    def test_float_string_returns_float(self) -> None:
        self.assertEqual(safe_float("42.5"), 42.5)

    def test_integer_string_returns_float(self) -> None:
        self.assertEqual(safe_float("42"), 42.0)

    def test_turkish_comma_returns_float(self) -> None:
        self.assertEqual(safe_float("3,14"), 3.14)

    def test_whitespace_is_stripped(self) -> None:
        self.assertEqual(safe_float("  7.5  "), 7.5)

    def test_negative_number(self) -> None:
        self.assertEqual(safe_float("-5.0"), -5.0)

    def test_empty_string_returns_none(self) -> None:
        self.assertIsNone(safe_float(""))

    def test_whitespace_only_returns_none(self) -> None:
        self.assertIsNone(safe_float("   "))

    def test_non_numeric_returns_none(self) -> None:
        self.assertIsNone(safe_float("abc"))

    def test_mixed_string_returns_none(self) -> None:
        self.assertIsNone(safe_float("12abc"))


class ValidateGeometryInputsTests(unittest.TestCase):
    def test_all_none_returns_incomplete(self) -> None:
        msg, status = validate_geometry_inputs(None, None, None)
        self.assertIsNone(msg)
        self.assertEqual(status, "incomplete")

    def test_partial_none_returns_incomplete(self) -> None:
        msg, status = validate_geometry_inputs(100.0, 5.0, None)
        self.assertIsNone(msg)
        self.assertEqual(status, "incomplete")

    def test_zero_diameter_returns_error(self) -> None:
        msg, status = validate_geometry_inputs(0.0, 5.0, 100.0)
        self.assertIsNotNone(msg)
        self.assertEqual(status, "error")

    def test_negative_diameter_returns_error(self) -> None:
        msg, status = validate_geometry_inputs(-10.0, 5.0, 100.0)
        self.assertIsNotNone(msg)
        self.assertEqual(status, "error")

    def test_zero_wall_thickness_returns_error(self) -> None:
        msg, status = validate_geometry_inputs(100.0, 0.0, 100.0)
        self.assertIsNotNone(msg)
        self.assertEqual(status, "error")

    def test_negative_wall_thickness_returns_error(self) -> None:
        msg, status = validate_geometry_inputs(100.0, -1.0, 100.0)
        self.assertIsNotNone(msg)
        self.assertEqual(status, "error")

    def test_zero_length_returns_error(self) -> None:
        msg, status = validate_geometry_inputs(100.0, 5.0, 0.0)
        self.assertIsNotNone(msg)
        self.assertEqual(status, "error")

    def test_negative_length_returns_error(self) -> None:
        msg, status = validate_geometry_inputs(100.0, 5.0, -20.0)
        self.assertIsNotNone(msg)
        self.assertEqual(status, "error")

    def test_wall_too_large_for_od_returns_error(self) -> None:
        msg, status = validate_geometry_inputs(100.0, 60.0, 100.0)
        self.assertIsNotNone(msg)
        self.assertEqual(status, "error")

    def test_wall_equal_to_half_od_returns_error(self) -> None:
        msg, status = validate_geometry_inputs(100.0, 50.0, 100.0)
        self.assertIsNotNone(msg)
        self.assertEqual(status, "error")

    def test_valid_inputs_returns_valid(self) -> None:
        msg, status = validate_geometry_inputs(100.0, 5.0, 200.0)
        self.assertIsNone(msg)
        self.assertEqual(status, "valid")


class ValidateElevationInputsTests(unittest.TestCase):
    def test_all_none_returns_incomplete(self) -> None:
        msg, status = validate_elevation_inputs(None, None, None, None)
        self.assertIsNone(msg)
        self.assertEqual(status, "incomplete")

    def test_partial_none_returns_incomplete(self) -> None:
        msg, status = validate_elevation_inputs(100.0, 10.0, 50.0, None)
        self.assertIsNone(msg)
        self.assertEqual(status, "incomplete")

    def test_highest_lower_than_lowest_returns_error(self) -> None:
        msg, status = validate_elevation_inputs(10.0, 100.0, 50.0, 60.0)
        self.assertIsNotNone(msg)
        self.assertEqual(status, "error")

    def test_start_below_lowest_returns_error(self) -> None:
        msg, status = validate_elevation_inputs(100.0, 10.0, 5.0, 60.0)
        self.assertIsNotNone(msg)
        self.assertEqual(status, "error")

    def test_start_above_highest_returns_error(self) -> None:
        msg, status = validate_elevation_inputs(100.0, 10.0, 150.0, 60.0)
        self.assertIsNotNone(msg)
        self.assertEqual(status, "error")

    def test_end_below_lowest_returns_error(self) -> None:
        msg, status = validate_elevation_inputs(100.0, 10.0, 50.0, 5.0)
        self.assertIsNotNone(msg)
        self.assertEqual(status, "error")

    def test_end_above_highest_returns_error(self) -> None:
        msg, status = validate_elevation_inputs(100.0, 10.0, 50.0, 150.0)
        self.assertIsNotNone(msg)
        self.assertEqual(status, "error")

    def test_equal_high_and_low_returns_ok_for_same_elevations(self) -> None:
        msg, status = validate_elevation_inputs(50.0, 50.0, 50.0, 50.0)
        self.assertIsNone(msg)
        self.assertEqual(status, "valid")

    def test_valid_inputs_returns_valid(self) -> None:
        msg, status = validate_elevation_inputs(100.0, 10.0, 50.0, 75.0)
        self.assertIsNone(msg)
        self.assertEqual(status, "valid")


if __name__ == "__main__":
    unittest.main()

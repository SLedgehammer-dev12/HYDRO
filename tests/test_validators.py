from __future__ import annotations

import unittest

from hidrostatik_test.ui.validators import (
    A_MICRO_PER_BAR_MAX,
    A_MICRO_PER_BAR_MIN,
    ACTUAL_PRESSURE_CHANGE_BAR_MAX,
    ACTUAL_PRESSURE_CHANGE_BAR_MIN,
    B_MICRO_PER_C_MAX,
    B_MICRO_PER_C_MIN,
    DELTA_T_C_MAX,
    DELTA_T_C_MIN,
    K_FACTOR_MAX,
    K_FACTOR_MIN,
    NumericInputError,
    parse_finite_float,
    safe_float,
    validate_elevation_inputs,
    validate_geometry_inputs,
    validate_geometry_text_inputs,
)


class ParseFiniteFloatTests(unittest.TestCase):
    def test_plain_decimal_returns_float(self) -> None:
        self.assertAlmostEqual(parse_finite_float("42.5", "Deger"), 42.5)

    def test_turkish_comma_decimal_returns_float(self) -> None:
        self.assertAlmostEqual(parse_finite_float("3,14", "Deger"), 3.14)

    def test_whitespace_is_stripped(self) -> None:
        self.assertAlmostEqual(parse_finite_float("  7,5  ", "Deger"), 7.5)

    def test_negative_value_is_accepted(self) -> None:
        self.assertAlmostEqual(parse_finite_float("-5,5", "Deger"), -5.5)

    def test_scientific_notation_is_accepted(self) -> None:
        self.assertAlmostEqual(parse_finite_float("1e3", "Deger"), 1000.0)

    def test_single_dot_is_always_decimal(self) -> None:
        # Sozlesme: tek nokta ondalik ayiricidir; "1.000" = 1.0 (bin degil).
        self.assertAlmostEqual(parse_finite_float("1.000", "Deger"), 1.0)

    def test_multiple_dots_are_thousands_separators(self) -> None:
        self.assertAlmostEqual(parse_finite_float("1.000.000", "Deger"), 1_000_000.0)

    def test_mixed_separators_use_rightmost_as_decimal(self) -> None:
        self.assertAlmostEqual(parse_finite_float("1.234,56", "Deger"), 1234.56)
        self.assertAlmostEqual(parse_finite_float("1,234.56", "Deger"), 1234.56)

    def test_malformed_grouping_is_rejected(self) -> None:
        with self.assertRaises(NumericInputError):
            parse_finite_float("1.23.456", "Deger")

    def test_none_is_rejected(self) -> None:
        with self.assertRaises(NumericInputError) as context:
            parse_finite_float(None, "Dis cap")
        self.assertIn("bos birakilamaz", str(context.exception))

    def test_empty_string_is_rejected(self) -> None:
        for value in ("", "   "):
            with self.subTest(value=value):
                with self.assertRaises(NumericInputError) as context:
                    parse_finite_float(value, "Dis cap")
                self.assertIn("bos birakilamaz", str(context.exception))

    def test_non_numeric_text_is_rejected(self) -> None:
        for value in ("abc", "12abc", "1_000", "1,2,3"):
            with self.subTest(value=value):
                with self.assertRaises(NumericInputError) as context:
                    parse_finite_float(value, "Dis cap")
                self.assertIn("gecerli bir sayi", str(context.exception))

    def test_nan_and_inf_are_rejected(self) -> None:
        for value in ("nan", "NaN", "inf", "-inf", "infinity", "1e999", "-1e999"):
            with self.subTest(value=value):
                with self.assertRaises(NumericInputError) as context:
                    parse_finite_float(value, "Dis cap")
                self.assertIn("sonlu bir sayi", str(context.exception))

    def test_inclusive_range_boundaries_are_accepted(self) -> None:
        self.assertAlmostEqual(
            parse_finite_float("1", "A", A_MICRO_PER_BAR_MIN, A_MICRO_PER_BAR_MAX), 1.0
        )
        self.assertAlmostEqual(
            parse_finite_float("200", "A", A_MICRO_PER_BAR_MIN, A_MICRO_PER_BAR_MAX), 200.0
        )

    def test_out_of_range_value_is_rejected(self) -> None:
        with self.assertRaises(NumericInputError) as context:
            parse_finite_float("0.9", "A", A_MICRO_PER_BAR_MIN, A_MICRO_PER_BAR_MAX)
        self.assertIn("araliginda", str(context.exception))

        with self.assertRaises(NumericInputError):
            parse_finite_float("200.1", "A", A_MICRO_PER_BAR_MIN, A_MICRO_PER_BAR_MAX)

    def test_negative_b_coefficient_is_accepted_in_range(self) -> None:
        self.assertAlmostEqual(
            parse_finite_float("-150", "B", B_MICRO_PER_C_MIN, B_MICRO_PER_C_MAX), -150.0
        )

    def test_below_b_lower_bound_is_rejected(self) -> None:
        with self.assertRaises(NumericInputError) as context:
            parse_finite_float("-250", "B", B_MICRO_PER_C_MIN, B_MICRO_PER_C_MAX)
        self.assertIn("araliginda", str(context.exception))

    def test_delta_t_and_pa_ranges(self) -> None:
        self.assertAlmostEqual(parse_finite_float("20", "dT", DELTA_T_C_MIN, DELTA_T_C_MAX), 20.0)
        with self.assertRaises(NumericInputError):
            parse_finite_float("20.5", "dT", DELTA_T_C_MIN, DELTA_T_C_MAX)
        self.assertAlmostEqual(
            parse_finite_float(
                "-50", "Pa", ACTUAL_PRESSURE_CHANGE_BAR_MIN, ACTUAL_PRESSURE_CHANGE_BAR_MAX
            ),
            -50.0,
        )
        with self.assertRaises(NumericInputError):
            parse_finite_float(
                "60", "Pa", ACTUAL_PRESSURE_CHANGE_BAR_MIN, ACTUAL_PRESSURE_CHANGE_BAR_MAX
            )

    def test_k_factor_range(self) -> None:
        self.assertAlmostEqual(parse_finite_float("1,02", "K", K_FACTOR_MIN, K_FACTOR_MAX), 1.02)
        with self.assertRaises(NumericInputError):
            parse_finite_float("1.2", "K", K_FACTOR_MIN, K_FACTOR_MAX)

    def test_min_only_and_max_only_messages(self) -> None:
        with self.assertRaises(NumericInputError) as context:
            parse_finite_float("0", "Uzunluk", min_value=0.1)
        self.assertIn("en az", str(context.exception))

        with self.assertRaises(NumericInputError) as context:
            parse_finite_float("5", "Ust sinir", max_value=4)
        self.assertIn("en fazla", str(context.exception))


class ValidateGeometryTextInputsTests(unittest.TestCase):
    def test_all_none_returns_incomplete(self) -> None:
        message, status = validate_geometry_text_inputs(None, None, None)
        self.assertIsNone(message)
        self.assertEqual(status, "incomplete")

    def test_partial_input_returns_incomplete(self) -> None:
        message, status = validate_geometry_text_inputs("406,4", "", "1000")
        self.assertIsNone(message)
        self.assertEqual(status, "incomplete")

    def test_comma_decimal_inputs_are_valid(self) -> None:
        message, status = validate_geometry_text_inputs("406,4", "8,74", "1000")
        self.assertIsNone(message)
        self.assertEqual(status, "valid")

    def test_dot_decimal_inputs_are_valid(self) -> None:
        message, status = validate_geometry_text_inputs("406.4", "8.74", "1000")
        self.assertIsNone(message)
        self.assertEqual(status, "valid")

    def test_single_dot_thousand_like_value_is_read_as_decimal(self) -> None:
        message, status = validate_geometry_text_inputs("406,4", "8,74", "1.000")
        self.assertIsNone(message)
        self.assertEqual(status, "valid")

    def test_text_value_returns_error(self) -> None:
        message, status = validate_geometry_text_inputs("abc", "8,74", "1000")
        self.assertEqual(status, "error")
        self.assertIsNotNone(message)
        self.assertIn("gecerli bir sayi", message or "")

    def test_nan_returns_error(self) -> None:
        message, status = validate_geometry_text_inputs("nan", "8,74", "1000")
        self.assertEqual(status, "error")
        self.assertIn("sonlu", message or "")

    def test_zero_value_returns_error(self) -> None:
        message, status = validate_geometry_text_inputs("0", "8,74", "1000")
        self.assertEqual(status, "error")
        self.assertIn("sifirdan buyuk", message or "")

    def test_wall_thickness_too_large_returns_error(self) -> None:
        message, status = validate_geometry_text_inputs("100", "50", "1000")
        self.assertEqual(status, "error")
        self.assertIsNotNone(message)


class GeometryFiniteValueTests(unittest.TestCase):
    def test_nan_diameter_returns_error(self) -> None:
        message, status = validate_geometry_inputs(float("nan"), 8.0, 100.0)
        self.assertEqual(status, "error")
        self.assertIn("sonlu", message or "")

    def test_infinite_length_returns_error(self) -> None:
        message, status = validate_geometry_inputs(406.4, 8.0, float("inf"))
        self.assertEqual(status, "error")
        self.assertIn("sonlu", message or "")

    def test_nan_wall_thickness_returns_error(self) -> None:
        message, status = validate_geometry_inputs(406.4, float("nan"), 100.0)
        self.assertEqual(status, "error")
        self.assertIsNotNone(message)


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

    def test_nan_returns_none(self) -> None:
        self.assertIsNone(safe_float("nan"))

    def test_overflowing_exponent_returns_none(self) -> None:
        self.assertIsNone(safe_float("1e999"))

    def test_single_dot_thousand_like_value_returns_decimal(self) -> None:
        # Kanonik ayristirici ile ayni sozlesme: tek nokta ondaliktir.
        self.assertEqual(safe_float("1.000"), 1.0)

    def test_grouped_thousands_returns_float(self) -> None:
        self.assertEqual(safe_float("1.000.000"), 1_000_000.0)


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

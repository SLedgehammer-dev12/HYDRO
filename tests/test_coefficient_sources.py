from __future__ import annotations

import unittest
from math import isclose, isfinite

from hidrostatik_test.domain import BSource
from hidrostatik_test.domain.coefficient_sources import (
    AUTO_B_LABEL,
    DEFAULT_B_SOURCE,
    GAIL_B_LABEL,
    INSTITUTIONAL_B_LABEL,
    BSourceComparison,
    BSourceResult,
    compare_b_sources,
    normalize_b_source,
    resolve_b_value,
)
from hidrostatik_test.domain.hydrotest_core import ValidationError

_BETA_AT_10C_50BAR = 99.621630836736


class BSourceNormalizationTests(unittest.TestCase):
    def test_default_source_is_institutional(self) -> None:
        self.assertIs(DEFAULT_B_SOURCE, BSource.INSTITUTIONAL)
        self.assertEqual(BSource.INSTITUTIONAL.value, "institutional")

    def test_source_accepts_enum_string_and_case_variants(self) -> None:
        self.assertIs(normalize_b_source(BSource.GAIL), BSource.GAIL)
        self.assertIs(normalize_b_source("gail"), BSource.GAIL)
        self.assertIs(normalize_b_source("  AUTO "), BSource.AUTO)
        self.assertIs(normalize_b_source("institutional"), BSource.INSTITUTIONAL)

    def test_invalid_source_names_raise_validation_error(self) -> None:
        for value in ("workbook", "", "beta-alpha", 3, None):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    normalize_b_source(value)  # type: ignore[arg-type]
                with self.assertRaises(ValidationError):
                    resolve_b_value(value, temp_c=10.0, pressure_bar=50.0)  # type: ignore[arg-type]


class ResolveBValueTests(unittest.TestCase):
    def test_institutional_value_matches_control_table(self) -> None:
        result = resolve_b_value(BSource.INSTITUTIONAL, temp_c=10.0, pressure_bar=50.0)

        self.assertIsInstance(result, BSourceResult)
        self.assertIs(result.source, BSource.INSTITUTIONAL)
        self.assertEqual(result.label, INSTITUTIONAL_B_LABEL)
        self.assertTrue(isclose(result.b_micro_per_c, 64.923, rel_tol=1e-12))
        self.assertFalse(result.repaired_table)
        self.assertIn("Kurum ici", result.note)

    def test_gail_value_matches_gail_table(self) -> None:
        result = resolve_b_value("gail", temp_c=10.0, pressure_bar=50.0)

        self.assertIs(result.source, BSource.GAIL)
        self.assertEqual(result.label, GAIL_B_LABEL)
        self.assertTrue(isclose(result.b_micro_per_c, 60.45, rel_tol=1e-12))
        self.assertFalse(result.repaired_table)

    def test_auto_volumetric_value_uses_three_alpha(self) -> None:
        result = resolve_b_value(BSource.AUTO, temp_c=10.0, pressure_bar=50.0)

        self.assertIs(result.source, BSource.AUTO)
        self.assertEqual(result.label, AUTO_B_LABEL)
        self.assertEqual(result.steel_model, "volumetric")
        self.assertTrue(isclose(result.b_micro_per_c, _BETA_AT_10C_50BAR - 36.0, rel_tol=1e-9))
        self.assertAlmostEqual(result.b_micro_per_c, 63.621630836736, places=6)
        self.assertTrue(
            isclose(result.water_beta_micro_per_c or 0.0, _BETA_AT_10C_50BAR, rel_tol=1e-9)
        )
        self.assertTrue(isfinite(result.b_micro_per_c))

    def test_auto_linear_value_preserves_historic_model(self) -> None:
        result = resolve_b_value(
            BSource.AUTO,
            temp_c=10.0,
            pressure_bar=50.0,
            steel_model="linear",
        )

        self.assertEqual(result.steel_model, "linear")
        self.assertTrue(isclose(result.b_micro_per_c, _BETA_AT_10C_50BAR - 12.0, rel_tol=1e-9))
        self.assertAlmostEqual(result.b_micro_per_c, 87.621630836736, places=6)

    def test_auto_volumetric_temperature_value_uses_alpha_of_temperature(self) -> None:
        result = resolve_b_value(
            BSource.AUTO,
            temp_c=10.0,
            pressure_bar=50.0,
            steel_model="volumetric_temperature",
        )

        expected = _BETA_AT_10C_50BAR - 3.0 * (10.8 + 0.012 * 10.0)
        self.assertTrue(isclose(result.b_micro_per_c, expected, rel_tol=1e-9))

    def test_institutional_reports_repaired_seven_degree_point(self) -> None:
        result = resolve_b_value(BSource.INSTITUTIONAL, temp_c=7.0, pressure_bar=90.0)

        self.assertTrue(result.repaired_table)
        self.assertTrue(isclose(result.b_micro_per_c, 32.663, rel_tol=1e-12))
        self.assertIn("onarilmis", result.note)
        self.assertIn("45.515000", result.note)

    def test_validation_rejects_non_finite_and_out_of_range_states(self) -> None:
        invalid_states = (
            (float("nan"), 50.0),
            (float("inf"), 50.0),
            (10.0, float("nan")),
            (10.0, float("inf")),
            (10.0, 0.0),
            (10.0, -1.0),
        )
        for temp_c, pressure_bar in invalid_states:
            with self.subTest(temp_c=temp_c, pressure_bar=pressure_bar):
                with self.assertRaises(ValidationError):
                    resolve_b_value(BSource.AUTO, temp_c=temp_c, pressure_bar=pressure_bar)

    def test_institutional_range_error_becomes_validation_error(self) -> None:
        with self.assertRaises(ValidationError):
            resolve_b_value(BSource.INSTITUTIONAL, temp_c=26.0, pressure_bar=30.0)

        # GAIL alone still serves 26 degC.
        gail = resolve_b_value(BSource.GAIL, temp_c=26.0, pressure_bar=30.0)
        self.assertTrue(isfinite(gail.b_micro_per_c))

    def test_negative_steel_alpha_and_unknown_model_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            resolve_b_value(
                BSource.AUTO,
                temp_c=10.0,
                pressure_bar=50.0,
                steel_alpha_micro_per_c=-1.0,
            )
        with self.assertRaises(ValidationError):
            resolve_b_value(
                BSource.AUTO,
                temp_c=10.0,
                pressure_bar=50.0,
                steel_model="quadratic",
            )


class CompareBSourcesTests(unittest.TestCase):
    def test_comparison_returns_all_three_sources_and_deltas(self) -> None:
        comparison = compare_b_sources(temp_c=10.0, pressure_bar=50.0)

        self.assertIsInstance(comparison, BSourceComparison)
        self.assertEqual(comparison.temp_c, 10.0)
        self.assertEqual(comparison.pressure_bar, 50.0)
        self.assertTrue(isclose(comparison.institutional.b_micro_per_c, 64.923, rel_tol=1e-12))
        self.assertTrue(isclose(comparison.gail.b_micro_per_c, 60.45, rel_tol=1e-12))
        self.assertTrue(
            isclose(
                comparison.auto.b_micro_per_c,
                _BETA_AT_10C_50BAR - 36.0,
                rel_tol=1e-9,
            )
        )

        self.assertTrue(isclose(comparison.institutional_vs_gail, 64.923 - 60.45, rel_tol=1e-12))
        self.assertTrue(
            isclose(
                comparison.auto_vs_institutional,
                (_BETA_AT_10C_50BAR - 36.0) - 64.923,
                rel_tol=1e-9,
            )
        )
        self.assertTrue(
            isclose(
                comparison.auto_vs_gail,
                (_BETA_AT_10C_50BAR - 36.0) - 60.45,
                rel_tol=1e-9,
            )
        )
        self.assertGreater(comparison.institutional_vs_gail, 4.0)
        self.assertLess(comparison.auto_vs_institutional, 0.0)

    def test_comparison_uses_repaired_institutional_table(self) -> None:
        comparison = compare_b_sources(temp_c=7.0, pressure_bar=90.0)

        self.assertTrue(comparison.institutional.repaired_table)
        self.assertTrue(isclose(comparison.institutional.b_micro_per_c, 32.663, rel_tol=1e-12))
        self.assertTrue(isclose(comparison.gail.b_micro_per_c, 28.0, rel_tol=1e-12))
        self.assertTrue(isclose(comparison.institutional_vs_gail, 32.663 - 28.0, rel_tol=1e-12))

    def test_comparison_rejects_invalid_steel_model(self) -> None:
        with self.assertRaises(ValidationError):
            compare_b_sources(temp_c=10.0, pressure_bar=50.0, steel_model="bilinear")

    def test_comparison_requires_institutional_range(self) -> None:
        with self.assertRaises(ValidationError):
            compare_b_sources(temp_c=26.0, pressure_bar=30.0)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from math import isclose
from unittest.mock import patch

from hidrostatik_test.domain import (
    WaterPropertyBackendInfo,
    WaterPropertyError,
    ValidationError,
    calculate_water_compressibility_a,
    calculate_water_thermal_expansion_beta,
    calculate_water_density,
    get_available_water_property_backends,
    get_default_water_property_backend,
    get_water_property_backend,
)
from hidrostatik_test.domain.water_properties import (
    ABSOLUTE_ZERO_C,
    WATER_DENSITY_DEFAULT_KG_PER_M3,
    _axis_bounds,
    _bilinear_interpolate,
    _linear_interpolate,
    scale_isothermal_compressibility_pa_to_micro_per_bar,
    scale_expansion_coefficient_k_to_micro_per_c,
)


class FakeWaterPropertyBackend:
    info = WaterPropertyBackendInfo(
        key="fake",
        label="Fake backend",
        distribution_ready=True,
        note="Test backend",
    )

    def calculate_water_compressibility_a(self, temp_c: float, pressure_bar: float) -> float:
        return temp_c + pressure_bar

    def calculate_water_thermal_expansion_beta(self, temp_c: float, pressure_bar: float) -> float:
        return (temp_c * 10.0) + pressure_bar


class WaterPropertyBackendTests(unittest.TestCase):
    def test_default_backend_is_coolprop_and_distribution_ready(self) -> None:
        backend = get_default_water_property_backend()

        self.assertEqual(backend.info.key, "coolprop")
        self.assertTrue(backend.info.distribution_ready)

    def test_available_backends_include_coolprop_metadata(self) -> None:
        backend_infos = get_available_water_property_backends()

        self.assertTrue(any(info.key == "coolprop" for info in backend_infos))
        self.assertTrue(any(info.key == "table_v1" for info in backend_infos))

    def test_backend_can_be_resolved_by_key(self) -> None:
        backend = get_water_property_backend("coolprop")

        self.assertEqual(backend.info.label, "CoolProp EOS")

    def test_unknown_backend_key_raises_water_property_error(self) -> None:
        with self.assertRaises(WaterPropertyError):
            get_water_property_backend("missing-backend")

    def test_unknown_backend_key_is_converted_to_validation_error_in_public_calculator(self) -> None:
        with self.assertRaises(ValidationError):
            calculate_water_compressibility_a(10.0, 50.0, backend="missing-backend")

    def test_custom_backend_can_be_injected_for_a_calculation(self) -> None:
        backend = FakeWaterPropertyBackend()

        self.assertTrue(isclose(calculate_water_compressibility_a(10.0, 50.0, backend=backend), 60.0))
        self.assertTrue(isclose(calculate_water_thermal_expansion_beta(10.0, 50.0, backend=backend), 150.0))


class ValidationAndEdgeTests(unittest.TestCase):
    def test_validate_inputs_absolute_zero(self) -> None:
        with self.assertRaises(ValidationError):
            calculate_water_compressibility_a(ABSOLUTE_ZERO_C - 1, 50.0)
        with self.assertRaises(ValidationError):
            calculate_water_thermal_expansion_beta(ABSOLUTE_ZERO_C - 1, 50.0)

    def test_validate_inputs_non_positive_pressure(self) -> None:
        with self.assertRaises(ValidationError):
            calculate_water_compressibility_a(20.0, 0.0)
        with self.assertRaises(ValidationError):
            calculate_water_compressibility_a(20.0, -1.0)

    def test_scale_compressibility_non_positive(self) -> None:
        with self.assertRaises(WaterPropertyError):
            scale_isothermal_compressibility_pa_to_micro_per_bar(0.0)
        with self.assertRaises(WaterPropertyError):
            scale_isothermal_compressibility_pa_to_micro_per_bar(-1e-12)

    def test_scale_expansion_non_finite(self) -> None:
        with self.assertRaises(WaterPropertyError):
            scale_expansion_coefficient_k_to_micro_per_c(float("inf"))
        with self.assertRaises(WaterPropertyError):
            scale_expansion_coefficient_k_to_micro_per_c(float("nan"))

    def test_axis_bounds_below_range(self) -> None:
        points = (10.0, 20.0, 30.0)
        with self.assertRaises(WaterPropertyError):
            _axis_bounds(5.0, points, "test")

    def test_axis_bounds_above_range(self) -> None:
        points = (10.0, 20.0, 30.0)
        with self.assertRaises(WaterPropertyError):
            _axis_bounds(35.0, points, "test")

    def test_axis_bounds_exact_match(self) -> None:
        points = (10.0, 20.0, 30.0)
        lo, hi = _axis_bounds(20.0, points, "test")
        self.assertEqual(lo, 1)
        self.assertEqual(hi, 1)

    def test_axis_bounds_within_range(self) -> None:
        points = (10.0, 20.0, 30.0)
        lo, hi = _axis_bounds(25.0, points, "test")
        self.assertEqual(lo, 1)
        self.assertEqual(hi, 2)

    def test_bilinear_interpolate_exact_corner(self) -> None:
        result = _bilinear_interpolate(10.0, 50.0, 10.0, 20.0, 50.0, 60.0, 1.0, 2.0, 3.0, 4.0)
        self.assertEqual(result, 1.0)

    def test_bilinear_interpolate_same_t(self) -> None:
        result = _bilinear_interpolate(10.0, 55.0, 10.0, 10.0, 50.0, 60.0, 1.0, 2.0, 3.0, 4.0)
        # Linear along pressure: 1.0 + (55-50)/(60-50) * (3-1) = 1.0 + 0.5*2 = 2.0
        self.assertAlmostEqual(result, 2.0)

    def test_bilinear_interpolate_same_p(self) -> None:
        result = _bilinear_interpolate(15.0, 50.0, 10.0, 20.0, 50.0, 50.0, 1.0, 2.0, 3.0, 4.0)
        # Linear along temperature: 1.0 + (15-10)/(20-10) * (2-1) = 1.0 + 0.5 = 1.5
        self.assertAlmostEqual(result, 1.5)

    def test_linear_interpolate_exact(self) -> None:
        self.assertEqual(_linear_interpolate(10.0, 10.0, 20.0, 1.0, 2.0), 1.0)

    def test_linear_interpolate_equal_x(self) -> None:
        self.assertEqual(_linear_interpolate(10.0, 10.0, 10.0, 5.0, 99.0), 5.0)

    def test_linear_interpolate_midpoint(self) -> None:
        self.assertAlmostEqual(_linear_interpolate(15.0, 10.0, 20.0, 1.0, 3.0), 2.0)

    @patch("hidrostatik_test.domain.water_properties._HAS_COOLPROP", False)
    def test_density_fallback_when_no_coolprop(self) -> None:
        backend = get_water_property_backend("table_v1")
        density = backend.calculate_water_density(20.0, 50.0)
        self.assertEqual(density, WATER_DENSITY_DEFAULT_KG_PER_M3)

    def test_resolve_backend_default(self) -> None:
        from hidrostatik_test.domain.water_properties import resolve_water_property_backend
        backend = resolve_water_property_backend()
        self.assertIsNotNone(backend)

    def test_resolve_backend_none_returns_default(self) -> None:
        from hidrostatik_test.domain.water_properties import resolve_water_property_backend
        backend = resolve_water_property_backend(None)
        self.assertIsNotNone(backend)

    def test_resolve_backend_str_returns_specific(self) -> None:
        from hidrostatik_test.domain.water_properties import resolve_water_property_backend
        backend = resolve_water_property_backend("table_v1")
        self.assertEqual(backend.info.key, "table_v1")

    def test_table_backend_exact_grid_point(self) -> None:
        backend = get_water_property_backend("table_v1")
        a = backend.calculate_water_compressibility_a(20.0, 50.0)
        self.assertIsInstance(a, float)
        self.assertGreater(a, 0.0)

    def test_table_backend_resolves_backend_by_key(self) -> None:
        backend = get_water_property_backend("table_v1")
        self.assertEqual(backend.info.key, "table_v1")


try:
    from hidrostatik_test.domain.water_properties import IAPWS95WaterPropertyBackend
    HAS_IAPWS95 = True
except ImportError:
    HAS_IAPWS95 = False


@unittest.skipUnless(HAS_IAPWS95, "iapws kutuphanesi kurulu degil")
class TestIAPWS95Backend(unittest.TestCase):
    def setUp(self):
        self.backend = IAPWS95WaterPropertyBackend()

    def test_iapws95_matches_reference_a_at_t10_p50(self):
        a = self.backend.calculate_water_compressibility_a(10.0, 50.0)
        self.assertAlmostEqual(a, 47.193088967078, places=6)

    def test_iapws95_matches_reference_a_at_t15_p80(self):
        a = self.backend.calculate_water_compressibility_a(15.0, 80.0)
        self.assertAlmostEqual(a, 45.786845210898, places=6)

    def test_iapws95_matches_reference_a_at_t20_p100(self):
        a = self.backend.calculate_water_compressibility_a(20.0, 100.0)
        self.assertAlmostEqual(a, 44.744088115012, places=6)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from math import isclose

from hidrostatik_test.domain import (
    WaterPropertyBackendInfo,
    WaterPropertyError,
    ValidationError,
    calculate_water_compressibility_a,
    calculate_water_thermal_expansion_beta,
    get_available_water_property_backends,
    get_default_water_property_backend,
    get_water_property_backend,
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


if __name__ == "__main__":
    unittest.main()

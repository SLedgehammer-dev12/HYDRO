from __future__ import annotations

import unittest
from math import isclose

from hidrostatik_test.domain.units import (
    convert_length,
    convert_pressure,
    convert_temperature,
    validate_unit,
)


class UnitConversionTests(unittest.TestCase):
    def test_pressure_bar_to_pascal(self) -> None:
        result = convert_pressure(1.0, "bar", "Pa")
        self.assertTrue(isclose(result, 100000.0, rel_tol=1e-9))

    def test_pressure_pascal_to_bar(self) -> None:
        result = convert_pressure(100000.0, "Pa", "bar")
        self.assertTrue(isclose(result, 1.0, rel_tol=1e-9))

    def test_length_mm_to_m(self) -> None:
        result = convert_length(1000.0, "mm", "m")
        self.assertTrue(isclose(result, 1.0, rel_tol=1e-9))

    def test_length_m_to_mm(self) -> None:
        result = convert_length(1.0, "m", "mm")
        self.assertTrue(isclose(result, 1000.0, rel_tol=1e-9))

    def test_temperature_celsius_to_kelvin(self) -> None:
        result = convert_temperature(0.0, "degC", "K")
        self.assertTrue(isclose(result, 273.15, rel_tol=1e-9))

    def test_temperature_kelvin_to_celsius(self) -> None:
        result = convert_temperature(273.15, "K", "degC")
        self.assertTrue(isclose(result, 0.0, abs_tol=1e-9))

    def test_validate_unit_valid(self) -> None:
        self.assertTrue(validate_unit(100.0, "bar"))
        self.assertTrue(validate_unit(25.0, "degC"))
        self.assertTrue(validate_unit(1000.0, "mm"))

    def test_validate_unit_invalid(self) -> None:
        self.assertFalse(validate_unit(100.0, "invalid_unit"))


if __name__ == "__main__":
    unittest.main()

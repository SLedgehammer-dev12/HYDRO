from __future__ import annotations

from typing import Final

import pint

ureg = pint.UnitRegistry()
Q_ = ureg.Quantity

Pressure = ureg.bar
Length = ureg.millimeter
Temperature = ureg.degC
Volume = ureg.meter**3
Density = ureg.kilogram / ureg.meter**3

BAR_TO_PA: Final[float] = 1e5
MM_TO_M: Final[float] = 1e-3
M3_TO_L: Final[float] = 1000.0


def convert_pressure(value: float, from_unit: str, to_unit: str) -> float:
    quantity = Q_(value, from_unit)
    return quantity.to(to_unit).magnitude


def convert_length(value: float, from_unit: str, to_unit: str) -> float:
    quantity = Q_(value, from_unit)
    return quantity.to(to_unit).magnitude


def convert_temperature(value: float, from_unit: str, to_unit: str) -> float:
    quantity = Q_(value, from_unit)
    return quantity.to(to_unit).magnitude


def validate_unit(value: float, unit: str) -> bool:
    try:
        Q_(value, unit)
        return True
    except (pint.UndefinedUnitError, pint.DimensionalityError):
        return False


__all__ = [
    "BAR_TO_PA",
    "Density",
    "Length",
    "MM_TO_M",
    "M3_TO_L",
    "Pressure",
    "Q_",
    "Temperature",
    "Volume",
    "convert_length",
    "convert_pressure",
    "convert_temperature",
    "ureg",
    "validate_unit",
]

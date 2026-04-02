from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Final, Protocol

from CoolProp.CoolProp import PropsSI
from ..data.water_property_table import (
    DEFAULT_TABLE_CSV_PATH,
    DEFAULT_TABLE_METADATA_PATH,
    WaterPropertyTableGrid,
    load_water_property_table,
)

MICRO_BAR_INVERSE_PER_PA_INVERSE: Final[float] = 1e11
MICRO_PER_C_INVERSE_PER_K_INVERSE: Final[float] = 1e6
ABSOLUTE_ZERO_C: Final[float] = -273.15


class WaterPropertyError(ValueError):
    """Raised when a water-property backend cannot produce a valid value."""


@dataclass(frozen=True)
class WaterPropertyBackendInfo:
    key: str
    label: str
    distribution_ready: bool
    note: str


class WaterPropertyBackend(Protocol):
    info: WaterPropertyBackendInfo

    def calculate_water_compressibility_a(self, temp_c: float, pressure_bar: float) -> float:
        ...

    def calculate_water_thermal_expansion_beta(self, temp_c: float, pressure_bar: float) -> float:
        ...


BackendSpecifier = str | WaterPropertyBackend | None


def scale_isothermal_compressibility_pa_to_micro_per_bar(value_pa_inverse: float) -> float:
    if value_pa_inverse <= 0:
        raise WaterPropertyError("Izotermal sikistirilabilirlik pozitif olmalidir.")
    return value_pa_inverse * MICRO_BAR_INVERSE_PER_PA_INVERSE


def scale_expansion_coefficient_k_to_micro_per_c(value_k_inverse: float) -> float:
    if not isfinite(value_k_inverse):
        raise WaterPropertyError("Genlesme katsayisi sonlu bir sayi olmalidir.")
    return value_k_inverse * MICRO_PER_C_INVERSE_PER_K_INVERSE


def _validate_state_inputs(temp_c: float, pressure_bar: float) -> tuple[float, float]:
    if temp_c <= ABSOLUTE_ZERO_C:
        raise WaterPropertyError("Sicaklik mutlak sifirin altinda olamaz.")
    if pressure_bar <= 0:
        raise WaterPropertyError("Basinc sifirdan buyuk olmalidir.")
    return temp_c + 273.15, pressure_bar * 1e5


@dataclass(frozen=True)
class CoolPropWaterPropertyBackend:
    info: WaterPropertyBackendInfo = WaterPropertyBackendInfo(
        key="coolprop",
        label="CoolProp EOS",
        distribution_ready=True,
        note=(
            "Varsayilan backend. Dagitimda kullanilabilir; ikinci dogrulama icin "
            "GPL olmayan baska bir backend eklenebilir."
        ),
    )

    def calculate_water_compressibility_a(self, temp_c: float, pressure_bar: float) -> float:
        kelvin, pascal = _validate_state_inputs(temp_c, pressure_bar)

        try:
            compressibility_pa_inverse = PropsSI(
                "ISOTHERMAL_COMPRESSIBILITY",
                "T",
                kelvin,
                "P",
                pascal,
                "Water",
            )
        except ValueError as exc:
            raise WaterPropertyError(f"A hesaplanamadi: {exc}") from exc

        return scale_isothermal_compressibility_pa_to_micro_per_bar(compressibility_pa_inverse)

    def calculate_water_thermal_expansion_beta(self, temp_c: float, pressure_bar: float) -> float:
        kelvin, pascal = _validate_state_inputs(temp_c, pressure_bar)

        try:
            expansion_k_inverse = PropsSI(
                "ISOBARIC_EXPANSION_COEFFICIENT",
                "T",
                kelvin,
                "P",
                pascal,
                "Water",
            )
        except ValueError as exc:
            raise WaterPropertyError(f"Su genlesme katsayisi hesaplanamadi: {exc}") from exc

        return scale_expansion_coefficient_k_to_micro_per_c(expansion_k_inverse)


@dataclass(frozen=True)
class TableInterpolationWaterPropertyBackend:
    csv_path: Path = DEFAULT_TABLE_CSV_PATH
    metadata_path: Path = DEFAULT_TABLE_METADATA_PATH
    info: WaterPropertyBackendInfo = WaterPropertyBackendInfo(
        key="table_v1",
        label="Table Interpolation v1",
        distribution_ready=True,
        note=(
            "Runtime'da yalnizca CSV grid ve metadata okur. Baslangic grid 0-40 degC ve "
            "1-150 bar araliginda 1x1 adimlarla uretilir."
        ),
    )

    def calculate_water_compressibility_a(self, temp_c: float, pressure_bar: float) -> float:
        _validate_state_inputs(temp_c, pressure_bar)
        return self._interpolate(temp_c, pressure_bar, use_beta=False)

    def calculate_water_thermal_expansion_beta(self, temp_c: float, pressure_bar: float) -> float:
        _validate_state_inputs(temp_c, pressure_bar)
        return self._interpolate(temp_c, pressure_bar, use_beta=True)

    def _grid(self) -> WaterPropertyTableGrid:
        return load_water_property_table(self.csv_path, self.metadata_path)

    def _interpolate(self, temp_c: float, pressure_bar: float, use_beta: bool) -> float:
        grid = self._grid()
        temperature_points = grid.temperature_points
        pressure_points = grid.pressure_points
        temperature_bounds = _axis_bounds(temp_c, temperature_points, "sicaklik")
        pressure_bounds = _axis_bounds(pressure_bar, pressure_points, "basinc")
        source_grid = grid.beta_grid if use_beta else grid.a_grid

        t0_index, t1_index = temperature_bounds
        p0_index, p1_index = pressure_bounds
        t0 = temperature_points[t0_index]
        t1 = temperature_points[t1_index]
        p0 = pressure_points[p0_index]
        p1 = pressure_points[p1_index]

        q11 = source_grid[t0_index][p0_index]
        q21 = source_grid[t1_index][p0_index]
        q12 = source_grid[t0_index][p1_index]
        q22 = source_grid[t1_index][p1_index]

        return _bilinear_interpolate(temp_c, pressure_bar, t0, t1, p0, p1, q11, q21, q12, q22)


def _axis_bounds(value: float, points: tuple[float, ...], label: str) -> tuple[int, int]:
    if value < points[0] or value > points[-1]:
        raise WaterPropertyError(
            f"Table backend aralik disi {label} degeri aldi: {value}. "
            f"Izinli aralik {points[0]} - {points[-1]}."
        )

    insertion = bisect_left(points, value)
    if insertion < len(points) and points[insertion] == value:
        return insertion, insertion
    upper = insertion
    lower = insertion - 1
    return lower, upper


def _bilinear_interpolate(
    temp_c: float,
    pressure_bar: float,
    t0: float,
    t1: float,
    p0: float,
    p1: float,
    q11: float,
    q21: float,
    q12: float,
    q22: float,
) -> float:
    if t0 == t1 and p0 == p1:
        return q11
    if t0 == t1:
        return _linear_interpolate(pressure_bar, p0, p1, q11, q12)
    if p0 == p1:
        return _linear_interpolate(temp_c, t0, t1, q11, q21)

    t_ratio = (temp_c - t0) / (t1 - t0)
    p_ratio = (pressure_bar - p0) / (p1 - p0)
    low = q11 + (q21 - q11) * t_ratio
    high = q12 + (q22 - q12) * t_ratio
    return low + (high - low) * p_ratio


def _linear_interpolate(value: float, lower_x: float, upper_x: float, lower_y: float, upper_y: float) -> float:
    if lower_x == upper_x:
        return lower_y
    ratio = (value - lower_x) / (upper_x - lower_x)
    return lower_y + (upper_y - lower_y) * ratio


COOLPROP_WATER_PROPERTY_BACKEND = CoolPropWaterPropertyBackend()
TABLE_INTERPOLATION_WATER_PROPERTY_BACKEND = TableInterpolationWaterPropertyBackend()
_WATER_PROPERTY_BACKENDS: dict[str, WaterPropertyBackend] = {
    COOLPROP_WATER_PROPERTY_BACKEND.info.key: COOLPROP_WATER_PROPERTY_BACKEND,
    TABLE_INTERPOLATION_WATER_PROPERTY_BACKEND.info.key: TABLE_INTERPOLATION_WATER_PROPERTY_BACKEND,
}


def get_available_water_property_backends() -> tuple[WaterPropertyBackendInfo, ...]:
    return tuple(backend.info for backend in _WATER_PROPERTY_BACKENDS.values())


def get_default_water_property_backend() -> WaterPropertyBackend:
    return COOLPROP_WATER_PROPERTY_BACKEND


def get_water_property_backend(backend_key: str) -> WaterPropertyBackend:
    normalized = backend_key.strip().lower()
    try:
        return _WATER_PROPERTY_BACKENDS[normalized]
    except KeyError as exc:
        raise WaterPropertyError(f"Bilinmeyen su ozelligi backend'i: {backend_key}") from exc


def resolve_water_property_backend(backend: BackendSpecifier = None) -> WaterPropertyBackend:
    if backend is None:
        return get_default_water_property_backend()
    if isinstance(backend, str):
        return get_water_property_backend(backend)
    return backend


def calculate_water_compressibility_a(
    temp_c: float, pressure_bar: float, backend: BackendSpecifier = None
) -> float:
    return resolve_water_property_backend(backend).calculate_water_compressibility_a(temp_c, pressure_bar)


def calculate_water_thermal_expansion_beta(
    temp_c: float, pressure_bar: float, backend: BackendSpecifier = None
) -> float:
    return resolve_water_property_backend(backend).calculate_water_thermal_expansion_beta(temp_c, pressure_bar)

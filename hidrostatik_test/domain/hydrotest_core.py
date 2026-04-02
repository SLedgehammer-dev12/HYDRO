from __future__ import annotations

from dataclasses import dataclass
from math import pi
from typing import Final, TypeAlias

from .water_properties import (
    WaterPropertyError,
    calculate_water_compressibility_a as calculate_water_compressibility_a_with_backend,
    calculate_water_thermal_expansion_beta as calculate_water_thermal_expansion_beta_with_backend,
    scale_expansion_coefficient_k_to_micro_per_c,
    scale_isothermal_compressibility_pa_to_micro_per_bar,
)

AIR_CONTENT_ACCEPTANCE_FACTOR: Final[float] = 1.06
PRESSURE_VARIATION_ACCEPTANCE_BAR: Final[float] = 0.3
SPEC_AIR_PRESSURE_RISE_BAR: Final[float] = 1.0
SPEC_AIR_PRESSURE_RISE_TOLERANCE: Final[float] = 1e-9
SEAMLESS_PIPE_K: Final[float] = 1.00
WELDED_PIPE_K: Final[float] = 1.02
FLOAT_TOLERANCE: Final[float] = 1e-9


class ValidationError(ValueError):
    """Raised when user data is incomplete or physically inconsistent."""


@dataclass(frozen=True)
class PipeSection:
    outside_diameter_mm: float
    wall_thickness_mm: float
    length_m: float

    def __post_init__(self) -> None:
        if self.outside_diameter_mm <= 0:
            raise ValidationError("Dis cap sifirdan buyuk olmalidir.")
        if self.wall_thickness_mm <= 0:
            raise ValidationError("Et kalinligi sifirdan buyuk olmalidir.")
        if self.length_m <= 0:
            raise ValidationError("Hat uzunlugu sifirdan buyuk olmalidir.")
        if self.wall_thickness_mm * 2 >= self.outside_diameter_mm:
            raise ValidationError("Et kalinligi borunun ic capini sifira dusurecek kadar buyuk olamaz.")

    @property
    def internal_radius_mm(self) -> float:
        return (self.outside_diameter_mm / 2) - self.wall_thickness_mm

    @property
    def internal_volume_m3(self) -> float:
        radius_m = self.internal_radius_mm / 1000
        return pi * (radius_m**2) * self.length_m

    @property
    def elasticity_term(self) -> float:
        return 0.884 * self.internal_radius_mm / self.wall_thickness_mm


@dataclass(frozen=True)
class PipeGeometry:
    sections: tuple[PipeSection, ...]

    def __post_init__(self) -> None:
        if not self.sections:
            raise ValidationError("En az bir boru segmenti tanimlanmalidir.")

    @property
    def total_length_m(self) -> float:
        return sum(section.length_m for section in self.sections)

    @property
    def internal_volume_m3(self) -> float:
        return sum(section.internal_volume_m3 for section in self.sections)

    @property
    def internal_radius_mm(self) -> float:
        total_volume = self.internal_volume_m3
        if total_volume <= FLOAT_TOLERANCE:
            raise ValidationError("Segmentlerden toplam hacim hesaplanamadi.")
        return sum(
            section.internal_radius_mm * section.internal_volume_m3 for section in self.sections
        ) / total_volume

    @property
    def elasticity_term(self) -> float:
        total_volume = self.internal_volume_m3
        if total_volume <= FLOAT_TOLERANCE:
            raise ValidationError("Segmentlerden toplam hacim hesaplanamadi.")
        return sum(section.elasticity_term * section.internal_volume_m3 for section in self.sections) / total_volume


PipeModel: TypeAlias = PipeSection | PipeGeometry


def calculate_water_compressibility_a(temp_c: float, pressure_bar: float, backend: object | None = None) -> float:
    try:
        return calculate_water_compressibility_a_with_backend(temp_c, pressure_bar, backend=backend)
    except WaterPropertyError as exc:
        raise ValidationError(str(exc)) from exc


def calculate_water_thermal_expansion_beta(
    temp_c: float, pressure_bar: float, backend: object | None = None
) -> float:
    try:
        return calculate_water_thermal_expansion_beta_with_backend(temp_c, pressure_bar, backend=backend)
    except WaterPropertyError as exc:
        raise ValidationError(str(exc)) from exc


def calculate_b_coefficient(
    water_beta_micro_per_c: float, steel_alpha_micro_per_c: float
) -> float:
    if water_beta_micro_per_c <= 0:
        raise ValidationError("Su genlesme katsayisi pozitif olmalidir.")
    if steel_alpha_micro_per_c < 0:
        raise ValidationError("Celik genlesme katsayisi negatif olamaz.")

    b_micro_per_c = water_beta_micro_per_c - steel_alpha_micro_per_c
    if b_micro_per_c <= 0:
        raise ValidationError("Hesaplanan B katsayisi pozitif cikmadi.")
    return b_micro_per_c


@dataclass(frozen=True)
class AirContentInputs:
    pipe: PipeModel
    a_micro_per_bar: float
    pressure_rise_bar: float
    k_factor: float
    actual_added_water_m3: float

    def __post_init__(self) -> None:
        if self.a_micro_per_bar <= 0:
            raise ValidationError("A degeri sifirdan buyuk olmalidir.")
        if self.pressure_rise_bar <= 0:
            raise ValidationError("Basinc artisi P sifirdan buyuk olmalidir.")
        if abs(self.pressure_rise_bar - SPEC_AIR_PRESSURE_RISE_BAR) > SPEC_AIR_PRESSURE_RISE_TOLERANCE:
            raise ValidationError("Hava icerik testi bu sartnameye gore tam 1.0 bar basinc artisi ile yapilmalidir.")
        if self.k_factor <= 0:
            raise ValidationError("K faktoru sifirdan buyuk olmalidir.")
        if self.actual_added_water_m3 < 0:
            raise ValidationError("Fiili ilave su hacmi negatif olamaz.")


@dataclass(frozen=True)
class AirContentResult:
    theoretical_added_water_m3: float
    acceptance_limit_m3: float
    actual_added_water_m3: float
    ratio: float
    passed: bool


def evaluate_air_content_test(inputs: AirContentInputs) -> AirContentResult:
    deformation_term = inputs.pipe.elasticity_term + inputs.a_micro_per_bar
    if deformation_term <= 0:
        raise ValidationError("Hava icerik hesabi icin payda/carpan pozitif olmalidir.")

    theoretical_added_water_m3 = (
        deformation_term
        * 1e-6
        * inputs.pipe.internal_volume_m3
        * inputs.pressure_rise_bar
        * inputs.k_factor
    )
    if theoretical_added_water_m3 <= FLOAT_TOLERANCE:
        raise ValidationError("Teorik su ilavesi hesaplanamadi.")

    acceptance_limit_m3 = theoretical_added_water_m3 * AIR_CONTENT_ACCEPTANCE_FACTOR
    ratio = inputs.actual_added_water_m3 / theoretical_added_water_m3
    passed = inputs.actual_added_water_m3 <= acceptance_limit_m3 + FLOAT_TOLERANCE

    return AirContentResult(
        theoretical_added_water_m3=theoretical_added_water_m3,
        acceptance_limit_m3=acceptance_limit_m3,
        actual_added_water_m3=inputs.actual_added_water_m3,
        ratio=ratio,
        passed=passed,
    )


@dataclass(frozen=True)
class PressureVariationInputs:
    pipe: PipeModel
    a_micro_per_bar: float
    b_micro_per_c: float
    delta_t_c: float
    actual_pressure_change_bar: float

    def __post_init__(self) -> None:
        if self.a_micro_per_bar <= 0:
            raise ValidationError("A degeri sifirdan buyuk olmalidir.")
        if self.b_micro_per_c <= 0:
            raise ValidationError("B degeri sifirdan buyuk olmalidir.")


@dataclass(frozen=True)
class PressureVariationResult:
    theoretical_pressure_change_bar: float
    allowable_upper_pressure_change_bar: float
    actual_pressure_change_bar: float
    margin_bar: float
    passed: bool


def evaluate_pressure_variation_test(inputs: PressureVariationInputs) -> PressureVariationResult:
    deformation_term = inputs.pipe.elasticity_term + inputs.a_micro_per_bar
    if deformation_term <= 0:
        raise ValidationError("Basinc degisim hesabi icin payda pozitif olmalidir.")

    theoretical_pressure_change_bar = (inputs.b_micro_per_c * inputs.delta_t_c) / deformation_term
    allowable_upper_pressure_change_bar = (
        theoretical_pressure_change_bar + PRESSURE_VARIATION_ACCEPTANCE_BAR
    )
    margin_bar = inputs.actual_pressure_change_bar - theoretical_pressure_change_bar
    passed = margin_bar <= PRESSURE_VARIATION_ACCEPTANCE_BAR + FLOAT_TOLERANCE

    return PressureVariationResult(
        theoretical_pressure_change_bar=theoretical_pressure_change_bar,
        allowable_upper_pressure_change_bar=allowable_upper_pressure_change_bar,
        actual_pressure_change_bar=inputs.actual_pressure_change_bar,
        margin_bar=margin_bar,
        passed=passed,
    )

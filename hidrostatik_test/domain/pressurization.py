from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Final

from .hydrotest_core import ValidationError

PRESSURIZATION_VOLUME_DEVIATION_LIMIT_PERCENT: Final[float] = 0.2
PRESSURIZATION_VOLUME_TOLERANCE_PERCENT: Final[float] = 1e-9
PRESSURIZATION_MIN_PRESSURE_TOLERANCE_BAR: Final[float] = 0.05
PRESSURIZATION_RELATIVE_PRESSURE_TOLERANCE: Final[float] = 0.001
UNDERFILL_TOLERANCE_PERCENT: Final[float] = 1e-9


def _require_finite(value: float, label: str) -> float:
    if not isfinite(value):
        raise ValidationError(f"{label} sonlu bir sayi olmalidir.")
    return value


@dataclass(frozen=True)
class PressurizationInputs:
    initial_volume_m3: float
    added_volume_m3: float
    theoretical_volume_m3: float
    pressure_bar: float
    expected_pressure_bar: float

    def __post_init__(self) -> None:
        _require_finite(self.initial_volume_m3, "Baslangic hacmi")
        _require_finite(self.added_volume_m3, "Ilave su hacmi")
        _require_finite(self.theoretical_volume_m3, "Teorik hacim")
        _require_finite(self.pressure_bar, "Basinc")
        _require_finite(self.expected_pressure_bar, "Beklenen basinc")
        if self.initial_volume_m3 <= 0:
            raise ValidationError("Baslangic hacmi sifirdan buyuk olmalidir.")
        if self.added_volume_m3 < 0:
            raise ValidationError("Ilave su hacmi negatif olamaz.")
        if self.theoretical_volume_m3 <= 0:
            raise ValidationError("Teorik hacim sifirdan buyuk olmalidir.")
        if self.pressure_bar <= 0:
            raise ValidationError("Basinc sifirdan buyuk olmalidir.")
        if self.expected_pressure_bar <= 0:
            raise ValidationError("Beklenen basinc sifirdan buyuk olmalidir.")


@dataclass(frozen=True)
class PressurizationResult:
    volume_deviation_percent: float
    pressure_deviation_bar: float
    within_volume_limit: bool
    within_pressure_limit: bool
    passed: bool
    volume_limit_percent: float = PRESSURIZATION_VOLUME_DEVIATION_LIMIT_PERCENT
    pressure_tolerance_bar: float = PRESSURIZATION_MIN_PRESSURE_TOLERANCE_BAR
    underfilled: bool = False
    volume_shortfall_percent: float = 0.0


def evaluate_pressurization(inputs: PressurizationInputs) -> PressurizationResult:
    # Sartname 14.2: oran, doldurulan toplam su hacmine gore ve yalnizca fazla su yonunde.
    total_filled_volume_m3 = inputs.initial_volume_m3 + inputs.added_volume_m3
    volume_deviation_percent = (
        (total_filled_volume_m3 - inputs.theoretical_volume_m3) / total_filled_volume_m3
    ) * 100.0
    if not isfinite(volume_deviation_percent):
        raise ValidationError("Hacim sapmasi sonlu bir sayi olarak hesaplanamadi.")

    volume_shortfall_percent = max(
        0.0,
        (inputs.theoretical_volume_m3 - total_filled_volume_m3)
        / inputs.theoretical_volume_m3
        * 100.0,
    )
    underfilled = volume_shortfall_percent > UNDERFILL_TOLERANCE_PERCENT

    pressure_deviation_bar = inputs.pressure_bar - inputs.expected_pressure_bar
    pressure_tolerance_bar = max(
        PRESSURIZATION_MIN_PRESSURE_TOLERANCE_BAR,
        PRESSURIZATION_RELATIVE_PRESSURE_TOLERANCE * inputs.expected_pressure_bar,
    )

    within_volume_limit = (
        volume_deviation_percent
        <= PRESSURIZATION_VOLUME_DEVIATION_LIMIT_PERCENT + PRESSURIZATION_VOLUME_TOLERANCE_PERCENT
    )
    within_pressure_limit = abs(pressure_deviation_bar) <= pressure_tolerance_bar

    passed = within_volume_limit and within_pressure_limit

    return PressurizationResult(
        volume_deviation_percent=volume_deviation_percent,
        pressure_deviation_bar=pressure_deviation_bar,
        within_volume_limit=within_volume_limit,
        within_pressure_limit=within_pressure_limit,
        passed=passed,
        volume_limit_percent=PRESSURIZATION_VOLUME_DEVIATION_LIMIT_PERCENT,
        pressure_tolerance_bar=pressure_tolerance_bar,
        underfilled=underfilled,
        volume_shortfall_percent=volume_shortfall_percent,
    )

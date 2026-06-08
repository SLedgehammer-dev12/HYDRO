from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .hydrotest_core import FLOAT_TOLERANCE, ValidationError

PRESSURIZATION_VOLUME_DEVIATION_LIMIT_PERCENT: Final[float] = 0.2


@dataclass(frozen=True)
class PressurizationInputs:
    initial_volume_m3: float
    added_volume_m3: float
    theoretical_volume_m3: float
    pressure_bar: float
    expected_pressure_bar: float

    def __post_init__(self) -> None:
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


def evaluate_pressurization(inputs: PressurizationInputs) -> PressurizationResult:
    total_volume_m3 = inputs.initial_volume_m3 + inputs.added_volume_m3
    volume_deviation_percent = (
        (total_volume_m3 - inputs.theoretical_volume_m3) / inputs.theoretical_volume_m3
    ) * 100.0

    pressure_deviation_bar = inputs.pressure_bar - inputs.expected_pressure_bar

    within_volume_limit = abs(volume_deviation_percent) <= PRESSURIZATION_VOLUME_DEVIATION_LIMIT_PERCENT + FLOAT_TOLERANCE
    within_pressure_limit = abs(pressure_deviation_bar) <= FLOAT_TOLERANCE

    passed = within_volume_limit and within_pressure_limit

    return PressurizationResult(
        volume_deviation_percent=volume_deviation_percent,
        pressure_deviation_bar=pressure_deviation_bar,
        within_volume_limit=within_volume_limit,
        within_pressure_limit=within_pressure_limit,
        passed=passed,
    )

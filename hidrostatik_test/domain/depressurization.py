from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .hydrotest_core import FLOAT_TOLERANCE, ValidationError

MIN_HOLD_MINUTES: Final[float] = 5.0


@dataclass(frozen=True)
class DepressurizationStage:
    stage_label: str
    start_pressure_bar: float
    end_pressure_bar: float
    hold_minutes: float

    def __post_init__(self) -> None:
        if self.start_pressure_bar < 0:
            raise ValidationError(
                f"{self.stage_label}: baslangic basinci negatif olamaz."
            )
        if self.end_pressure_bar < 0:
            raise ValidationError(
                f"{self.stage_label}: bitis basinci negatif olamaz."
            )
        if self.hold_minutes < 0:
            raise ValidationError(
                f"{self.stage_label}: bekleme suresi negatif olamaz."
            )


@dataclass(frozen=True)
class DepressurizationInputs:
    stages: tuple[DepressurizationStage, ...]
    initial_pressure_bar: float

    def __post_init__(self) -> None:
        if self.initial_pressure_bar <= 0:
            raise ValidationError("Baslangic basinci sifirdan buyuk olmalidir.")
        if not self.stages:
            raise ValidationError("En az bir basinclandirma kademesi tanimlanmalidir.")


@dataclass(frozen=True)
class DepressurizationResult:
    total_stages: int
    initial_pressure_bar: float
    final_pressure_bar: float
    total_time_min: float
    gradual_reduction: bool
    all_holds_sufficient: bool
    full_depressurization: bool
    passed: bool


def evaluate_depressurization(
    inputs: DepressurizationInputs,
) -> DepressurizationResult:
    stages = list(inputs.stages)
    total_stages = len(stages)
    final_pressure = stages[-1].end_pressure_bar

    gradual = True
    if stages[0].start_pressure_bar < inputs.initial_pressure_bar - FLOAT_TOLERANCE:
        gradual = False
    for stage in stages:
        if stage.end_pressure_bar > stage.start_pressure_bar + FLOAT_TOLERANCE:
            gradual = False

    total_time = sum(s.hold_minutes for s in stages)

    all_holds_sufficient = all(
        s.hold_minutes >= MIN_HOLD_MINUTES - FLOAT_TOLERANCE for s in stages
    )
    full_depressurization = final_pressure <= FLOAT_TOLERANCE

    passed = gradual and all_holds_sufficient and full_depressurization

    return DepressurizationResult(
        total_stages=total_stages,
        initial_pressure_bar=inputs.initial_pressure_bar,
        final_pressure_bar=final_pressure,
        total_time_min=total_time,
        gradual_reduction=gradual,
        all_holds_sufficient=all_holds_sufficient,
        full_depressurization=full_depressurization,
        passed=passed,
    )

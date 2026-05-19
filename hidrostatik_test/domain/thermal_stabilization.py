from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from .hydrotest_core import FLOAT_TOLERANCE, ValidationError

MIN_THERMAL_STABILIZATION_HOURS: Final[float] = 24.0
MAX_TEMPERATURE_DELTA_C: Final[float] = 0.5
MIN_RECORDS_FOR_AVERAGE = 2


@dataclass(frozen=True)
class ThermalRecord:
    timestamp: datetime
    pipe_temp_c: float
    soil_temp_c: float | None = None


@dataclass(frozen=True)
class ThermalStabilizationInputs:
    records: tuple[ThermalRecord, ...]

    def __post_init__(self) -> None:
        if len(self.records) < 2:
            raise ValidationError("Termal dengeleme degerlendirmesi icin en az 2 kayit gerekli.")
        sorted_records = sorted(self.records, key=lambda r: r.timestamp)
        if sorted_records != list(self.records):
            object.__setattr__(self, "records", tuple(sorted_records))


@dataclass(frozen=True)
class ThermalStabilizationResult:
    total_hours: float
    last_two_average_c: float
    previous_two_average_c: float
    delta_between_averages_c: float
    within_hours: bool
    within_delta: bool
    passed: bool
    record_count: int


def evaluate_thermal_stabilization(inputs: ThermalStabilizationInputs) -> ThermalStabilizationResult:
    records = list(inputs.records)
    first = records[0].timestamp
    last = records[-1].timestamp
    total_hours = (last - first).total_seconds() / 3600.0
    within_hours = total_hours >= MIN_THERMAL_STABILIZATION_HOURS - FLOAT_TOLERANCE

    pipe_temps = [record.pipe_temp_c for record in records]
    last_two = pipe_temps[-2:]
    last_two_avg = sum(last_two) / len(last_two)

    previous_two_avg = last_two_avg
    if len(pipe_temps) >= 4:
        prev_two = pipe_temps[-4:-2]
        previous_two_avg = sum(prev_two) / len(prev_two)
    elif len(pipe_temps) >= 3:
        previous_two_avg = sum(pipe_temps[-3:-1]) / len(pipe_temps[-3:-1])

    delta = abs(last_two_avg - previous_two_avg)
    within_delta = delta <= MAX_TEMPERATURE_DELTA_C + FLOAT_TOLERANCE
    passed = within_hours and within_delta

    return ThermalStabilizationResult(
        total_hours=total_hours,
        last_two_average_c=last_two_avg,
        previous_two_average_c=previous_two_avg,
        delta_between_averages_c=delta,
        within_hours=within_hours,
        within_delta=within_delta,
        passed=passed,
        record_count=len(records),
    )

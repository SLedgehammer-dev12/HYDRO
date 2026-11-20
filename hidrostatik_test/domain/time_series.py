from __future__ import annotations

import csv
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Final

from .hydrotest_core import ValidationError

THERMAL_BALANCE_THRESHOLD_C: Final[float] = 0.5
THERMAL_BALANCE_MIN_HOURS: Final[float] = 24.0
THERMAL_BALANCE_WINDOW_HOURS: Final[float] = 4.0
TEST_RECORDING_MIN_HOURS: Final[float] = 24.0
TEST_RECORDING_MAX_GAP_HOURS: Final[float] = 2.0


def _validate_finite(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{name} gecersiz sayisal deger iceriyor.")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValidationError(f"{name} sonlu bir sayi olmalidir.")
    return numeric


def _validate_positive(name: str, value: float) -> float:
    numeric = _validate_finite(name, value)
    if numeric <= 0:
        raise ValidationError(f"{name} pozitif olmalidir.")
    return numeric


def _comparable_ts(dt: datetime) -> datetime:
    """Normalize aware UTC/offset and naive datetimes to comparable naive UTC."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


@dataclass(frozen=True)
class TimeSeriesRecord:
    timestamp: datetime
    pressure_bar: float
    temperature_c: float
    volume_m3: float | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "pressure_bar", _validate_finite("pressure_bar", self.pressure_bar)
        )
        object.__setattr__(
            self, "temperature_c", _validate_finite("temperature_c", self.temperature_c)
        )
        if self.volume_m3 is not None:
            object.__setattr__(self, "volume_m3", _validate_finite("volume_m3", self.volume_m3))

    def to_dict(self) -> dict[str, str | float | None]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "pressure_bar": self.pressure_bar,
            "temperature_c": self.temperature_c,
            "volume_m3": self.volume_m3,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str | float | None]) -> TimeSeriesRecord:
        timestamp_str = data.get("timestamp", "")
        if isinstance(timestamp_str, str):
            timestamp = datetime.fromisoformat(timestamp_str)
        else:
            timestamp = datetime.now()

        volume_val = data.get("volume_m3")
        volume_m3 = None
        if volume_val is not None and not isinstance(volume_val, bool):
            val_str = str(volume_val).strip()
            if val_str and val_str.lower() != "none":
                try:
                    parsed_vol = float(val_str)
                    if math.isfinite(parsed_vol):
                        volume_m3 = parsed_vol
                except ValueError:
                    pass
        elif isinstance(volume_val, bool):
            raise ValidationError("volume_m3 boolean olamaz.")

        raw_p = data.get("pressure_bar", 0.0)
        raw_t = data.get("temperature_c", 0.0)
        if isinstance(raw_p, bool):
            raise ValidationError("pressure_bar boolean olamaz.")
        if isinstance(raw_t, bool):
            raise ValidationError("temperature_c boolean olamaz.")
        raw_notes = data.get("notes", "")
        return cls(
            timestamp=timestamp,
            pressure_bar=float(raw_p) if raw_p is not None else 0.0,
            temperature_c=float(raw_t) if raw_t is not None else 0.0,
            volume_m3=volume_m3,
            notes=str(raw_notes) if raw_notes is not None else "",
        )


@dataclass(frozen=True)
class TimeSeriesEvaluation:
    """Section 12 (Thermal Balance) and Section 15 (24-Hour Recording) evaluation."""

    record_count: int
    duration_hours: float
    first_timestamp: datetime | None
    last_timestamp: datetime | None
    thermal_duration_ok: bool
    recent_4h_avg_c: float | None
    previous_4h_avg_c: float | None
    thermal_temp_diff_c: float | None
    thermal_balanced: bool
    max_gap_hours: float | None
    recording_duration_ok: bool
    recording_interval_ok: bool
    recording_passed: bool
    initial_pressure_bar: float | None
    final_pressure_bar: float | None
    pressure_change_pa_bar: float | None
    min_pressure_bar: float | None
    max_pressure_bar: float | None
    initial_temperature_c: float | None
    final_temperature_c: float | None
    temperature_change_dt_c: float | None
    min_temperature_c: float | None
    max_temperature_c: float | None
    average_temperature_c: float | None
    initial_volume_m3: float | None
    final_volume_m3: float | None
    volume_delta_m3: float | None


@dataclass
class TimeSeriesStore:
    records: list[TimeSeriesRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {"records": [record.to_dict() for record in self.records]}

    @classmethod
    def from_dict(cls, data: dict[str, object] | None) -> TimeSeriesStore:
        store = cls()
        if not data or "records" not in data:
            return store
        raw_records = data.get("records")
        if not isinstance(raw_records, list):
            return store
        for r_data in raw_records:
            if isinstance(r_data, dict):
                store.records.append(TimeSeriesRecord.from_dict(r_data))
        return store

    def add_record(
        self,
        pressure_bar: float,
        temperature_c: float,
        volume_m3: float | None = None,
        notes: str = "",
        timestamp: datetime | None = None,
    ) -> TimeSeriesRecord:
        if timestamp is None:
            timestamp = datetime.now()

        record = TimeSeriesRecord(
            timestamp=timestamp,
            pressure_bar=pressure_bar,
            temperature_c=temperature_c,
            volume_m3=volume_m3,
            notes=notes,
        )
        self.records.append(record)
        return record

    def get_records(self) -> list[TimeSeriesRecord]:
        return sorted(self.records, key=lambda r: _comparable_ts(r.timestamp))

    def get_duration_hours(self) -> float:
        if len(self.records) < 2:
            return 0.0

        ordered = self.get_records()
        first = _comparable_ts(ordered[0].timestamp)
        last = _comparable_ts(ordered[-1].timestamp)
        delta = last - first
        return max(0.0, delta.total_seconds() / 3600.0)

    def get_average_temperature(
        self,
        last_n_hours: float | None = None,
        reference_time: datetime | None = None,
    ) -> float | None:
        if not self.records:
            return None

        ordered = self.get_records()
        if last_n_hours is not None:
            end = _comparable_ts(
                reference_time if reference_time is not None else ordered[-1].timestamp
            )
            cutoff = end - timedelta(hours=last_n_hours)
            filtered = [r for r in ordered if cutoff <= _comparable_ts(r.timestamp) <= end]
        else:
            filtered = ordered

        if not filtered:
            return None

        return sum(r.temperature_c for r in filtered) / len(filtered)

    def check_thermal_balance(self) -> tuple[bool, float]:
        evaluation = self.evaluate()
        if evaluation.thermal_temp_diff_c is None:
            return False, float("inf")
        return evaluation.thermal_balanced, evaluation.thermal_temp_diff_c

    def evaluate(
        self,
        *,
        min_hours: float = TEST_RECORDING_MIN_HOURS,
        max_gap_hours: float = TEST_RECORDING_MAX_GAP_HOURS,
    ) -> TimeSeriesEvaluation:
        min_h = _validate_positive("min_hours", min_hours)
        max_gap_limit = _validate_positive("max_gap_hours", max_gap_hours)
        ordered = self.get_records()
        count = len(ordered)
        duration_hours = self.get_duration_hours()

        if count == 0:
            return TimeSeriesEvaluation(
                record_count=0,
                duration_hours=0.0,
                first_timestamp=None,
                last_timestamp=None,
                thermal_duration_ok=False,
                recent_4h_avg_c=None,
                previous_4h_avg_c=None,
                thermal_temp_diff_c=None,
                thermal_balanced=False,
                max_gap_hours=None,
                recording_duration_ok=False,
                recording_interval_ok=False,
                recording_passed=False,
                initial_pressure_bar=None,
                final_pressure_bar=None,
                pressure_change_pa_bar=None,
                min_pressure_bar=None,
                max_pressure_bar=None,
                initial_temperature_c=None,
                final_temperature_c=None,
                temperature_change_dt_c=None,
                min_temperature_c=None,
                max_temperature_c=None,
                average_temperature_c=None,
                initial_volume_m3=None,
                final_volume_m3=None,
                volume_delta_m3=None,
            )

        end = _comparable_ts(ordered[-1].timestamp)
        recent_start = end - timedelta(hours=THERMAL_BALANCE_WINDOW_HOURS)
        previous_start = end - timedelta(hours=2 * THERMAL_BALANCE_WINDOW_HOURS)
        recent_records = [r for r in ordered if recent_start <= _comparable_ts(r.timestamp) <= end]
        previous_records = [
            r for r in ordered if previous_start <= _comparable_ts(r.timestamp) < recent_start
        ]

        recent_4h_avg = (
            sum(r.temperature_c for r in recent_records) / len(recent_records)
            if recent_records
            else None
        )
        previous_4h_avg = (
            sum(r.temperature_c for r in previous_records) / len(previous_records)
            if previous_records
            else None
        )

        thermal_duration_ok = count >= 2 and duration_hours >= THERMAL_BALANCE_MIN_HOURS - 1e-9
        thermal_temp_diff: float | None = None
        thermal_balanced = False
        if thermal_duration_ok and recent_4h_avg is not None and previous_4h_avg is not None:
            thermal_temp_diff = abs(recent_4h_avg - previous_4h_avg)
            thermal_balanced = thermal_temp_diff <= THERMAL_BALANCE_THRESHOLD_C + 1e-9

        max_gap: float | None = None
        if count >= 2:
            gaps = [
                max(
                    0.0,
                    (
                        _comparable_ts(ordered[i].timestamp)
                        - _comparable_ts(ordered[i - 1].timestamp)
                    ).total_seconds()
                    / 3600.0,
                )
                for i in range(1, count)
            ]
            max_gap = max(gaps)

        recording_duration_ok = count >= 2 and duration_hours >= min_h - 1e-9
        recording_interval_ok = (
            count >= 2 and max_gap is not None and max_gap <= max_gap_limit + 1e-9
        )
        recording_passed = recording_duration_ok and recording_interval_ok

        pressures = [r.pressure_bar for r in ordered]
        temps = [r.temperature_c for r in ordered]
        volumes = [r.volume_m3 for r in ordered if r.volume_m3 is not None]

        initial_p = pressures[0]
        final_p = pressures[-1]
        initial_t = temps[0]
        final_t = temps[-1]

        return TimeSeriesEvaluation(
            record_count=count,
            duration_hours=duration_hours,
            first_timestamp=ordered[0].timestamp,
            last_timestamp=ordered[-1].timestamp,
            thermal_duration_ok=thermal_duration_ok,
            recent_4h_avg_c=recent_4h_avg,
            previous_4h_avg_c=previous_4h_avg,
            thermal_temp_diff_c=thermal_temp_diff,
            thermal_balanced=thermal_balanced,
            max_gap_hours=max_gap,
            recording_duration_ok=recording_duration_ok,
            recording_interval_ok=recording_interval_ok,
            recording_passed=recording_passed,
            initial_pressure_bar=initial_p,
            final_pressure_bar=final_p,
            pressure_change_pa_bar=(initial_p - final_p) if count >= 2 else None,
            min_pressure_bar=min(pressures),
            max_pressure_bar=max(pressures),
            initial_temperature_c=initial_t,
            final_temperature_c=final_t,
            temperature_change_dt_c=(initial_t - final_t) if count >= 2 else None,
            min_temperature_c=min(temps),
            max_temperature_c=max(temps),
            average_temperature_c=sum(temps) / len(temps),
            initial_volume_m3=volumes[0] if volumes else None,
            final_volume_m3=volumes[-1] if volumes else None,
            volume_delta_m3=(volumes[-1] - volumes[0]) if len(volumes) >= 2 else None,
        )

    def to_csv(self, path: Path) -> None:
        if not self.records:
            return

        fieldnames = ["timestamp", "pressure_bar", "temperature_c", "volume_m3", "notes"]
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for record in self.records:
                writer.writerow(record.to_dict())

    @classmethod
    def from_csv(cls, path: Path) -> TimeSeriesStore:
        store = cls()
        if not path.exists():
            return store

        with path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                record = TimeSeriesRecord.from_dict(row)
                store.records.append(record)

        return store

    def to_json(self, path: Path) -> None:
        data = {
            "records": [record.to_dict() for record in self.records],
            "metadata": {
                "record_count": len(self.records),
                "duration_hours": self.get_duration_hours(),
                "thermal_balanced": self.check_thermal_balance()[0],
            },
        }
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, path: Path) -> TimeSeriesStore:
        store = cls()
        if not path.exists():
            return store

        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        for record_data in data.get("records", []):
            record = TimeSeriesRecord.from_dict(record_data)
            store.records.append(record)

        return store

    def clear(self) -> None:
        self.records.clear()


def evaluate_time_series(
    records: Sequence[TimeSeriesRecord],
    *,
    min_hours: float = TEST_RECORDING_MIN_HOURS,
    max_gap_hours: float = TEST_RECORDING_MAX_GAP_HOURS,
) -> TimeSeriesEvaluation:
    """Evaluate Section 12 thermal balance and Section 15 24-hour recording criteria."""
    return TimeSeriesStore(records=list(records)).evaluate(
        min_hours=min_hours, max_gap_hours=max_gap_hours
    )


__all__ = [
    "TEST_RECORDING_MAX_GAP_HOURS",
    "TEST_RECORDING_MIN_HOURS",
    "THERMAL_BALANCE_MIN_HOURS",
    "THERMAL_BALANCE_THRESHOLD_C",
    "THERMAL_BALANCE_WINDOW_HOURS",
    "TimeSeriesEvaluation",
    "TimeSeriesRecord",
    "TimeSeriesStore",
    "evaluate_time_series",
]

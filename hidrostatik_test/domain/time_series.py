from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Final

THERMAL_BALANCE_THRESHOLD_C: Final[float] = 0.5
THERMAL_BALANCE_MIN_HOURS: Final[float] = 24.0
THERMAL_BALANCE_WINDOW_HOURS: Final[float] = 4.0


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
        if volume_val is not None:
            val_str = str(volume_val).strip()
            if val_str and val_str.lower() != "none":
                try:
                    volume_m3 = float(val_str)
                except ValueError:
                    pass

        raw_p = data.get("pressure_bar", 0.0)
        raw_t = data.get("temperature_c", 0.0)
        raw_notes = data.get("notes", "")
        return cls(
            timestamp=timestamp,
            pressure_bar=float(raw_p) if raw_p is not None else 0.0,
            temperature_c=float(raw_t) if raw_t is not None else 0.0,
            volume_m3=volume_m3,
            notes=str(raw_notes) if raw_notes is not None else "",
        )


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
        if len(self.records) < 2:
            return False, float("inf")

        ordered = self.get_records()
        duration_hours = self.get_duration_hours()
        if duration_hours < THERMAL_BALANCE_MIN_HOURS:
            return False, float("inf")

        # Sartname 12: 4 saatlik araliklarla alinan son iki okuma blogunun ortalamalari.
        # Referans, canli saat degil arsivdeki son kayittir.
        end = _comparable_ts(ordered[-1].timestamp)
        recent_start = end - timedelta(hours=THERMAL_BALANCE_WINDOW_HOURS)
        previous_start = end - timedelta(hours=2 * THERMAL_BALANCE_WINDOW_HOURS)

        recent_records = [r for r in ordered if recent_start <= _comparable_ts(r.timestamp) <= end]
        previous_records = [
            r for r in ordered if previous_start <= _comparable_ts(r.timestamp) < recent_start
        ]

        if not recent_records or not previous_records:
            return False, float("inf")

        recent_avg = sum(r.temperature_c for r in recent_records) / len(recent_records)
        previous_avg = sum(r.temperature_c for r in previous_records) / len(previous_records)

        temp_diff = abs(recent_avg - previous_avg)
        is_balanced = temp_diff <= THERMAL_BALANCE_THRESHOLD_C

        return is_balanced, temp_diff

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


__all__ = [
    "THERMAL_BALANCE_MIN_HOURS",
    "THERMAL_BALANCE_THRESHOLD_C",
    "THERMAL_BALANCE_WINDOW_HOURS",
    "TimeSeriesRecord",
    "TimeSeriesStore",
]

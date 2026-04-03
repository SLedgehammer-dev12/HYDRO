from __future__ import annotations

import csv
import json
from bisect import bisect_left
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

TABLE_SCHEMA_VERSION = 1
DEFAULT_CONTROL_TABLE_KEY = "ab_control_table_1_25c_30_120bar_v1"
DEFAULT_CONTROL_TABLE_CSV_PATH = Path(__file__).with_name("ab_control_table_v1.csv")
DEFAULT_CONTROL_TABLE_METADATA_PATH = Path(__file__).with_name("ab_control_table_v1.meta.json")


class ABControlTableError(ValueError):
    """Raised when the official A/B control table cannot serve the requested point."""


@dataclass(frozen=True)
class ABControlTableAxis:
    key: str
    unit: str
    minimum: float
    maximum: float
    step: float
    count: int

    @property
    def points(self) -> tuple[float, ...]:
        return tuple(self.minimum + (index * self.step) for index in range(self.count))


@dataclass(frozen=True)
class ABControlTableSpec:
    schema_version: int
    table_key: str
    interpolation_method: str
    temperature_axis: ABControlTableAxis
    pressure_axis: ABControlTableAxis
    csv_columns: tuple[str, ...]
    a_unit: str
    b_unit: str


@dataclass(frozen=True)
class ABControlPoint:
    temp_c: float
    pressure_bar: float
    a_micro_per_bar: float
    b_micro_per_c: float
    source_note: str


@dataclass(frozen=True)
class ABControlTableGrid:
    spec: ABControlTableSpec
    source_name: str
    generated_at_utc: str
    row_count: int
    notes: tuple[str, ...]
    a_grid: tuple[tuple[float, ...], ...]
    b_grid: tuple[tuple[float, ...], ...]

    @property
    def temperature_points(self) -> tuple[float, ...]:
        return self.spec.temperature_axis.points

    @property
    def pressure_points(self) -> tuple[float, ...]:
        return self.spec.pressure_axis.points


def default_ab_control_table_spec() -> ABControlTableSpec:
    return ABControlTableSpec(
        schema_version=TABLE_SCHEMA_VERSION,
        table_key=DEFAULT_CONTROL_TABLE_KEY,
        interpolation_method="bilinear",
        temperature_axis=ABControlTableAxis(
            key="temp_c",
            unit="degC",
            minimum=1.0,
            maximum=25.0,
            step=1.0,
            count=25,
        ),
        pressure_axis=ABControlTableAxis(
            key="pressure_bar",
            unit="bar",
            minimum=30.0,
            maximum=120.0,
            step=1.0,
            count=91,
        ),
        csv_columns=("temp_c", "pressure_bar", "a_micro_per_bar", "b_micro_per_c"),
        a_unit="10^-6 / bar",
        b_unit="10^-6 / degC",
    )


def describe_ab_control_table_range(spec: ABControlTableSpec | None = None) -> str:
    active_spec = spec or default_ab_control_table_spec()
    return (
        f"T={active_spec.temperature_axis.minimum:.0f}-{active_spec.temperature_axis.maximum:.0f} degC ve "
        f"P={active_spec.pressure_axis.minimum:.0f}-{active_spec.pressure_axis.maximum:.0f} bar"
    )


def _axis_from_metadata(payload: dict[str, object], key: str) -> ABControlTableAxis:
    axis_payload = payload[key]
    if not isinstance(axis_payload, dict):
        raise ValueError(f"Gecersiz kontrol tablosu axis metadatasi: {key}")

    return ABControlTableAxis(
        key=str(axis_payload["key"]),
        unit=str(axis_payload["unit"]),
        minimum=float(axis_payload["minimum"]),
        maximum=float(axis_payload["maximum"]),
        step=float(axis_payload["step"]),
        count=int(axis_payload["count"]),
    )


@lru_cache(maxsize=4)
def load_ab_control_table(
    csv_path: Path = DEFAULT_CONTROL_TABLE_CSV_PATH,
    metadata_path: Path = DEFAULT_CONTROL_TABLE_METADATA_PATH,
) -> ABControlTableGrid:
    csv_path = Path(csv_path)
    metadata_path = Path(metadata_path)

    if not metadata_path.exists():
        raise FileNotFoundError(f"A/B kontrol tablosu metadata dosyasi bulunamadi: {metadata_path}")
    if not csv_path.exists():
        raise FileNotFoundError(f"A/B kontrol tablosu CSV dosyasi bulunamadi: {csv_path}")

    with metadata_path.open("r", encoding="utf-8") as handle:
        metadata = json.load(handle)

    spec = ABControlTableSpec(
        schema_version=int(metadata["schema_version"]),
        table_key=str(metadata["table_key"]),
        interpolation_method=str(metadata["interpolation_method"]),
        temperature_axis=_axis_from_metadata(metadata, "temperature_axis"),
        pressure_axis=_axis_from_metadata(metadata, "pressure_axis"),
        csv_columns=tuple(str(value) for value in metadata["csv_columns"]),
        a_unit=str(metadata["a_unit"]),
        b_unit=str(metadata["b_unit"]),
    )

    temperature_points = spec.temperature_axis.points
    pressure_points = spec.pressure_axis.points
    a_lookup = {
        temperature: {pressure: None for pressure in pressure_points}
        for temperature in temperature_points
    }
    b_lookup = {
        temperature: {pressure: None for pressure in pressure_points}
        for temperature in temperature_points
    }

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != spec.csv_columns:
            raise ValueError("A/B kontrol tablosu CSV kolonlari beklenen sema ile uyusmuyor.")

        row_count = 0
        for row in reader:
            temp_c = float(row["temp_c"])
            pressure_bar = float(row["pressure_bar"])
            if temp_c not in a_lookup or pressure_bar not in a_lookup[temp_c]:
                raise ValueError(
                    f"A/B kontrol tablosu nokta aralik disi veya yinelenmis: T={temp_c}, P={pressure_bar}"
                )
            a_lookup[temp_c][pressure_bar] = float(row["a_micro_per_bar"])
            b_lookup[temp_c][pressure_bar] = float(row["b_micro_per_c"])
            row_count += 1

    expected_rows = len(temperature_points) * len(pressure_points)
    if row_count != expected_rows:
        raise ValueError(f"A/B kontrol tablosu satir sayisi hatali: {row_count} != {expected_rows}")

    a_grid = tuple(
        tuple(
            _require_value(a_lookup[temperature][pressure], temperature, pressure, "A")
            for pressure in pressure_points
        )
        for temperature in temperature_points
    )
    b_grid = tuple(
        tuple(
            _require_value(b_lookup[temperature][pressure], temperature, pressure, "B")
            for pressure in pressure_points
        )
        for temperature in temperature_points
    )

    return ABControlTableGrid(
        spec=spec,
        source_name=str(metadata["source_name"]),
        generated_at_utc=str(metadata["generated_at_utc"]),
        row_count=int(metadata["row_count"]),
        notes=tuple(str(note) for note in metadata.get("notes", ())),
        a_grid=a_grid,
        b_grid=b_grid,
    )


def lookup_ab_control_point(
    temp_c: float,
    pressure_bar: float,
    csv_path: Path = DEFAULT_CONTROL_TABLE_CSV_PATH,
    metadata_path: Path = DEFAULT_CONTROL_TABLE_METADATA_PATH,
) -> ABControlPoint:
    grid = load_ab_control_table(csv_path=csv_path, metadata_path=metadata_path)
    temperature_points = grid.temperature_points
    pressure_points = grid.pressure_points
    temperature_bounds = _axis_bounds(temp_c, temperature_points, "sicaklik")
    pressure_bounds = _axis_bounds(pressure_bar, pressure_points, "basinc")

    t0_index, t1_index = temperature_bounds
    p0_index, p1_index = pressure_bounds
    t0 = temperature_points[t0_index]
    t1 = temperature_points[t1_index]
    p0 = pressure_points[p0_index]
    p1 = pressure_points[p1_index]

    a_value = _bilinear_interpolate(
        temp_c,
        pressure_bar,
        t0,
        t1,
        p0,
        p1,
        grid.a_grid[t0_index][p0_index],
        grid.a_grid[t1_index][p0_index],
        grid.a_grid[t0_index][p1_index],
        grid.a_grid[t1_index][p1_index],
    )
    b_value = _bilinear_interpolate(
        temp_c,
        pressure_bar,
        t0,
        t1,
        p0,
        p1,
        grid.b_grid[t0_index][p0_index],
        grid.b_grid[t1_index][p0_index],
        grid.b_grid[t0_index][p1_index],
        grid.b_grid[t1_index][p1_index],
    )

    source_note = (
        "Kurum ici A/B kontrol tablosu - exact grid"
        if t0_index == t1_index and p0_index == p1_index
        else "Kurum ici A/B kontrol tablosu - bilinear interpolation"
    )
    return ABControlPoint(
        temp_c=temp_c,
        pressure_bar=pressure_bar,
        a_micro_per_bar=a_value,
        b_micro_per_c=b_value,
        source_note=source_note,
    )


def clear_ab_control_table_cache() -> None:
    load_ab_control_table.cache_clear()


def _axis_bounds(value: float, points: tuple[float, ...], label: str) -> tuple[int, int]:
    if value < points[0] or value > points[-1]:
        raise ABControlTableError(
            f"Kontrol tablosu aralik disi {label} degeri aldi: {value}. "
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


def _require_value(value: float | None, temp_c: float, pressure_bar: float, field_name: str) -> float:
    if value is None:
        raise ValueError(
            f"A/B kontrol tablosu noktasinda eksik deger var: {field_name}, T={temp_c}, P={pressure_bar}"
        )
    return value

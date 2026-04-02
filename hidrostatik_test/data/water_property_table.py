from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

TABLE_SCHEMA_VERSION = 1
DEFAULT_TABLE_KEY = "water_property_grid_0_40c_1_150bar_v1"
DEFAULT_INTERPOLATION_METHOD = "bilinear"
DEFAULT_TABLE_CSV_PATH = Path(__file__).with_name("water_property_table_v1.csv")
DEFAULT_TABLE_METADATA_PATH = Path(__file__).with_name("water_property_table_v1.meta.json")


@dataclass(frozen=True)
class WaterPropertyTableAxis:
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
class WaterPropertyTableSpec:
    schema_version: int
    table_key: str
    interpolation_method: str
    temperature_axis: WaterPropertyTableAxis
    pressure_axis: WaterPropertyTableAxis
    csv_columns: tuple[str, ...]
    a_unit: str
    beta_unit: str


@dataclass(frozen=True)
class WaterPropertyTableGrid:
    spec: WaterPropertyTableSpec
    source_backend_key: str
    source_backend_label: str
    generated_at_utc: str
    row_count: int
    notes: tuple[str, ...]
    a_grid: tuple[tuple[float, ...], ...]
    beta_grid: tuple[tuple[float, ...], ...]

    @property
    def temperature_points(self) -> tuple[float, ...]:
        return self.spec.temperature_axis.points

    @property
    def pressure_points(self) -> tuple[float, ...]:
        return self.spec.pressure_axis.points


def default_water_property_table_spec() -> WaterPropertyTableSpec:
    return WaterPropertyTableSpec(
        schema_version=TABLE_SCHEMA_VERSION,
        table_key=DEFAULT_TABLE_KEY,
        interpolation_method=DEFAULT_INTERPOLATION_METHOD,
        temperature_axis=WaterPropertyTableAxis(
            key="temp_c",
            unit="degC",
            minimum=0.0,
            maximum=40.0,
            step=1.0,
            count=41,
        ),
        pressure_axis=WaterPropertyTableAxis(
            key="pressure_bar",
            unit="bar",
            minimum=1.0,
            maximum=150.0,
            step=1.0,
            count=150,
        ),
        csv_columns=(
            "temp_c",
            "pressure_bar",
            "a_micro_per_bar",
            "water_beta_micro_per_c",
        ),
        a_unit="10^-6 / bar",
        beta_unit="10^-6 / degC",
    )


def _axis_from_metadata(payload: dict[str, object], key: str) -> WaterPropertyTableAxis:
    axis_payload = payload[key]
    if not isinstance(axis_payload, dict):
        raise ValueError(f"Gecersiz axis metadatasi: {key}")

    return WaterPropertyTableAxis(
        key=str(axis_payload["key"]),
        unit=str(axis_payload["unit"]),
        minimum=float(axis_payload["minimum"]),
        maximum=float(axis_payload["maximum"]),
        step=float(axis_payload["step"]),
        count=int(axis_payload["count"]),
    )


@lru_cache(maxsize=8)
def load_water_property_table(
    csv_path: Path = DEFAULT_TABLE_CSV_PATH,
    metadata_path: Path = DEFAULT_TABLE_METADATA_PATH,
) -> WaterPropertyTableGrid:
    csv_path = Path(csv_path)
    metadata_path = Path(metadata_path)

    if not metadata_path.exists():
        raise FileNotFoundError(f"Su ozelligi metadata dosyasi bulunamadi: {metadata_path}")
    if not csv_path.exists():
        raise FileNotFoundError(f"Su ozelligi CSV dosyasi bulunamadi: {csv_path}")

    with metadata_path.open("r", encoding="utf-8") as handle:
        metadata = json.load(handle)

    spec = WaterPropertyTableSpec(
        schema_version=int(metadata["schema_version"]),
        table_key=str(metadata["table_key"]),
        interpolation_method=str(metadata["interpolation_method"]),
        temperature_axis=_axis_from_metadata(metadata, "temperature_axis"),
        pressure_axis=_axis_from_metadata(metadata, "pressure_axis"),
        csv_columns=tuple(str(value) for value in metadata["csv_columns"]),
        a_unit=str(metadata["a_unit"]),
        beta_unit=str(metadata["beta_unit"]),
    )

    temperature_points = spec.temperature_axis.points
    pressure_points = spec.pressure_axis.points
    a_lookup = {
        temperature: {pressure: None for pressure in pressure_points}
        for temperature in temperature_points
    }
    beta_lookup = {
        temperature: {pressure: None for pressure in pressure_points}
        for temperature in temperature_points
    }

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != spec.csv_columns:
            raise ValueError("Su ozelligi CSV kolonlari beklenen sema ile uyusmuyor.")

        row_count = 0
        for row in reader:
            temp_c = float(row["temp_c"])
            pressure_bar = float(row["pressure_bar"])
            if temp_c not in a_lookup or pressure_bar not in a_lookup[temp_c]:
                raise ValueError(
                    f"CSV nokta aralik disi veya yinelenmis: T={temp_c}, P={pressure_bar}"
                )
            a_lookup[temp_c][pressure_bar] = float(row["a_micro_per_bar"])
            beta_lookup[temp_c][pressure_bar] = float(row["water_beta_micro_per_c"])
            row_count += 1

    expected_rows = len(temperature_points) * len(pressure_points)
    if row_count != expected_rows:
        raise ValueError(f"Su ozelligi CSV satir sayisi hatali: {row_count} != {expected_rows}")

    a_grid = tuple(
        tuple(_require_value(a_lookup[temperature][pressure], temperature, pressure, "A") for pressure in pressure_points)
        for temperature in temperature_points
    )
    beta_grid = tuple(
        tuple(
            _require_value(beta_lookup[temperature][pressure], temperature, pressure, "beta")
            for pressure in pressure_points
        )
        for temperature in temperature_points
    )

    return WaterPropertyTableGrid(
        spec=spec,
        source_backend_key=str(metadata["source_backend_key"]),
        source_backend_label=str(metadata["source_backend_label"]),
        generated_at_utc=str(metadata["generated_at_utc"]),
        row_count=int(metadata["row_count"]),
        notes=tuple(str(note) for note in metadata.get("notes", ())),
        a_grid=a_grid,
        beta_grid=beta_grid,
    )


def clear_water_property_table_cache() -> None:
    load_water_property_table.cache_clear()


def _require_value(value: float | None, temp_c: float, pressure_bar: float, field_name: str) -> float:
    if value is None:
        raise ValueError(
            f"Su ozelligi CSV noktasinda eksik deger var: {field_name}, T={temp_c}, P={pressure_bar}"
        )
    return value

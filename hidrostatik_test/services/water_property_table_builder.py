from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..data.water_property_table import (
    DEFAULT_TABLE_CSV_PATH,
    DEFAULT_TABLE_METADATA_PATH,
    WaterPropertyTableAxis,
    WaterPropertyTableSpec,
    clear_water_property_table_cache,
    default_water_property_table_spec,
)
from ..domain.water_properties import WaterPropertyError, resolve_water_property_backend


@dataclass(frozen=True)
class WaterPropertyTableRow:
    temp_c: float
    pressure_bar: float
    a_micro_per_bar: float
    water_beta_micro_per_c: float


def generate_water_property_table_rows(
    spec: WaterPropertyTableSpec | None = None,
    backend: object | None = None,
) -> tuple[WaterPropertyTableRow, ...]:
    spec = spec or default_water_property_table_spec()
    backend_instance = resolve_water_property_backend(backend)
    rows: list[WaterPropertyTableRow] = []

    for temp_c in spec.temperature_axis.points:
        for pressure_bar in spec.pressure_axis.points:
            a_value, beta_value = _sample_backend_row(backend_instance, temp_c, pressure_bar)
            rows.append(
                WaterPropertyTableRow(
                    temp_c=temp_c,
                    pressure_bar=pressure_bar,
                    a_micro_per_bar=a_value,
                    water_beta_micro_per_c=beta_value,
                )
            )

    return tuple(rows)


def write_water_property_table(
    rows: tuple[WaterPropertyTableRow, ...],
    spec: WaterPropertyTableSpec | None = None,
    backend: object | None = None,
    csv_path: Path = DEFAULT_TABLE_CSV_PATH,
    metadata_path: Path = DEFAULT_TABLE_METADATA_PATH,
) -> tuple[Path, Path]:
    spec = spec or default_water_property_table_spec()
    backend_instance = resolve_water_property_backend(backend)
    csv_path = Path(csv_path)
    metadata_path = Path(metadata_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(spec.csv_columns))
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "temp_c": f"{row.temp_c:.1f}",
                    "pressure_bar": f"{row.pressure_bar:.1f}",
                    "a_micro_per_bar": f"{row.a_micro_per_bar:.12f}",
                    "water_beta_micro_per_c": f"{row.water_beta_micro_per_c:.12f}",
                }
            )

    metadata = {
        "schema_version": spec.schema_version,
        "table_key": spec.table_key,
        "interpolation_method": spec.interpolation_method,
        "temperature_axis": _axis_to_payload(spec.temperature_axis),
        "pressure_axis": _axis_to_payload(spec.pressure_axis),
        "csv_columns": list(spec.csv_columns),
        "a_unit": spec.a_unit,
        "beta_unit": spec.beta_unit,
        "source_backend_key": backend_instance.info.key,
        "source_backend_label": backend_instance.info.label,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "row_count": len(rows),
        "notes": [
            "Runtime table backend sadece CSV ve metadata dosyalarini okur.",
            "Bu baslangic grid 0-40 degC ve 1-150 bar araliginda 1x1 adimlarla uretilmistir.",
            "B runtime'da beta_water - celik alpha olarak hesaplanmaya devam eder.",
            "0 degC sirasinda erime sinirina yakin noktalar gerekirse kucuk pozitif sicaklik kaydirma ile uretilir.",
        ],
    }
    with metadata_path.open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, ensure_ascii=True, indent=2)
        handle.write("\n")

    clear_water_property_table_cache()
    return csv_path, metadata_path


def generate_default_water_property_table(backend: object | None = None) -> tuple[Path, Path]:
    spec = default_water_property_table_spec()
    rows = generate_water_property_table_rows(spec=spec, backend=backend)
    return write_water_property_table(rows=rows, spec=spec, backend=backend)


def _axis_to_payload(axis: WaterPropertyTableAxis) -> dict[str, object]:
    return {
        "key": axis.key,
        "unit": axis.unit,
        "minimum": axis.minimum,
        "maximum": axis.maximum,
        "step": axis.step,
        "count": axis.count,
    }


def _sample_backend_row(backend_instance: object, temp_c: float, pressure_bar: float) -> tuple[float, float]:
    try:
        return (
            backend_instance.calculate_water_compressibility_a(temp_c, pressure_bar),
            backend_instance.calculate_water_thermal_expansion_beta(temp_c, pressure_bar),
        )
    except WaterPropertyError as exc:
        for nudge_index in range(1, 26):
            adjusted_temp_c = temp_c + (0.01 * nudge_index)
            try:
                return (
                    backend_instance.calculate_water_compressibility_a(adjusted_temp_c, pressure_bar),
                    backend_instance.calculate_water_thermal_expansion_beta(adjusted_temp_c, pressure_bar),
                )
            except WaterPropertyError:
                continue
        raise WaterPropertyError(
            f"Su ozelligi tablo noktasi uretilemedi: T={temp_c}, P={pressure_bar}. Son hata: {exc}"
        ) from exc

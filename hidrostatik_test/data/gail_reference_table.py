from __future__ import annotations

from pathlib import Path

from .ab_control_table import (
    ABControlPoint,
    ABControlTableError,
    default_ab_control_table_spec,
    load_ab_control_table,
    lookup_ab_control_point,
)

GAIL_REFERENCE_OPTION_LABEL = "GAIL referans tablosu - aktif T/P"
GAIL_REFERENCE_TABLE_LABEL = "GAIL referans tablosu"
GAIL_REFERENCE_TABLE_CSV_PATH = Path(__file__).with_name("gail_reference_table_v1.csv")
GAIL_REFERENCE_TABLE_METADATA_PATH = Path(__file__).with_name("gail_reference_table_v1.meta.json")


def is_gail_reference_option(label: str) -> bool:
    return label.strip() == GAIL_REFERENCE_OPTION_LABEL


def describe_gail_reference_table_range() -> str:
    grid = load_ab_control_table(
        csv_path=GAIL_REFERENCE_TABLE_CSV_PATH,
        metadata_path=GAIL_REFERENCE_TABLE_METADATA_PATH,
    )
    spec = grid.spec or default_ab_control_table_spec()
    return (
        f"T={spec.temperature_axis.minimum:.0f}-{spec.temperature_axis.maximum:.0f} degC ve "
        f"P={spec.pressure_axis.minimum:.0f}-{spec.pressure_axis.maximum:.0f} bar"
    )


def lookup_gail_reference_point(temp_c: float, pressure_bar: float) -> ABControlPoint:
    point = lookup_ab_control_point(
        temp_c=temp_c,
        pressure_bar=pressure_bar,
        csv_path=GAIL_REFERENCE_TABLE_CSV_PATH,
        metadata_path=GAIL_REFERENCE_TABLE_METADATA_PATH,
    )
    if "exact grid" in point.source_note:
        source_note = f"{GAIL_REFERENCE_TABLE_LABEL} - exact grid"
    else:
        source_note = f"{GAIL_REFERENCE_TABLE_LABEL} - bilinear interpolation"
    return ABControlPoint(
        temp_c=point.temp_c,
        pressure_bar=point.pressure_bar,
        a_micro_per_bar=point.a_micro_per_bar,
        b_micro_per_c=point.b_micro_per_c,
        source_note=source_note,
    )


__all__ = [
    "ABControlPoint",
    "ABControlTableError",
    "GAIL_REFERENCE_OPTION_LABEL",
    "GAIL_REFERENCE_TABLE_CSV_PATH",
    "GAIL_REFERENCE_TABLE_LABEL",
    "GAIL_REFERENCE_TABLE_METADATA_PATH",
    "describe_gail_reference_table_range",
    "is_gail_reference_option",
    "lookup_gail_reference_point",
]

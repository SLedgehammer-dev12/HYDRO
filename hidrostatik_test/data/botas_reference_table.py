from __future__ import annotations

from .ab_control_table import (
    ABControlPoint,
    ABControlTableError,
    DEFAULT_CONTROL_TABLE_CSV_PATH,
    DEFAULT_CONTROL_TABLE_METADATA_PATH,
    describe_ab_control_table_range,
    lookup_ab_control_point,
)

BOTAS_REFERENCE_OPTION_LABEL = "BOTA\u015e referans tablosu - aktif T/P"
BOTAS_REFERENCE_TABLE_LABEL = "BOTA\u015e referans tablosu"
BOTAS_REFERENCE_TABLE_CSV_PATH = DEFAULT_CONTROL_TABLE_CSV_PATH
BOTAS_REFERENCE_TABLE_METADATA_PATH = DEFAULT_CONTROL_TABLE_METADATA_PATH


def is_botas_reference_option(label: str) -> bool:
    return label.strip() == BOTAS_REFERENCE_OPTION_LABEL


def describe_botas_reference_table_range() -> str:
    return describe_ab_control_table_range()


def lookup_botas_reference_point(temp_c: float, pressure_bar: float) -> ABControlPoint:
    point = lookup_ab_control_point(
        temp_c=temp_c,
        pressure_bar=pressure_bar,
        csv_path=BOTAS_REFERENCE_TABLE_CSV_PATH,
        metadata_path=BOTAS_REFERENCE_TABLE_METADATA_PATH,
    )
    if "exact grid" in point.source_note:
        source_note = f"{BOTAS_REFERENCE_TABLE_LABEL} - exact grid"
    else:
        source_note = f"{BOTAS_REFERENCE_TABLE_LABEL} - bilinear interpolation"
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
    "BOTAS_REFERENCE_OPTION_LABEL",
    "BOTAS_REFERENCE_TABLE_CSV_PATH",
    "BOTAS_REFERENCE_TABLE_LABEL",
    "BOTAS_REFERENCE_TABLE_METADATA_PATH",
    "describe_botas_reference_table_range",
    "is_botas_reference_option",
    "lookup_botas_reference_point",
]

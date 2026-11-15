"""BOTAS referans tablosu backend'i.

BOTAS secenegi, kurum ici ``A ve B Katsayisi.xlsx`` workbook'undan turetilen
A/B kontrol tablosunu (``ab_control_table_v1.csv``) kullanir. Bu modulun kendi
CSV/metadata dosyasi yoktur; ``BOTAS_REFERENCE_TABLE_*`` sabitleri geriye donuk
API uyumlulugu icin kontrol tablosu yollarina verilmis alias'lardir.

Gecerli aralik: T=1-25 degC, P=30-120 bar. GAIL referans tablosu ayri ve
bagimsiz bir kaynaktir (T=2-30 degC, P=30-120 bar); iki tablo ayni degildir ve
``compare_reference_b_sources`` ile yan yana gorulebilir.
"""

from __future__ import annotations

from dataclasses import dataclass

from .ab_control_table import (
    DEFAULT_CONTROL_TABLE_CSV_PATH,
    DEFAULT_CONTROL_TABLE_METADATA_PATH,
    ABControlPoint,
    ABControlTableError,
    describe_ab_control_table_range,
    lookup_ab_control_point,
)
from .gail_reference_table import lookup_gail_reference_point

BOTAS_REFERENCE_OPTION_LABEL = "BOTA\u015e referans tablosu - aktif T/P"
BOTAS_REFERENCE_TABLE_LABEL = "BOTA\u015e referans tablosu"
# Backwards-compatible names: the BOTAS option has no CSV of its own and reads
# the corporate workbook-derived A/B control table.
BOTAS_REFERENCE_TABLE_CSV_PATH = DEFAULT_CONTROL_TABLE_CSV_PATH
BOTAS_REFERENCE_TABLE_METADATA_PATH = DEFAULT_CONTROL_TABLE_METADATA_PATH


@dataclass(frozen=True)
class ReferenceBComparison:
    """Side-by-side A/B values from the control table and the GAIL table."""

    temp_c: float
    pressure_bar: float
    control_point: ABControlPoint
    gail_point: ABControlPoint

    @property
    def a_delta(self) -> float:
        """Control-table A minus GAIL A (same units, 10^-6 / bar)."""
        return self.control_point.a_micro_per_bar - self.gail_point.a_micro_per_bar

    @property
    def b_delta(self) -> float:
        """Control-table B minus GAIL B (same units, 10^-6 / degC)."""
        return self.control_point.b_micro_per_c - self.gail_point.b_micro_per_c


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


def compare_reference_b_sources(temp_c: float, pressure_bar: float) -> ReferenceBComparison:
    """Return control-table and GAIL A/B values for the same ``(T, P)`` node.

    This intentionally compares table values only; it does not import the
    domain ``beta - alpha`` calculation. Both lookups must be inside the control
    table range (T=1-25 degC), so a comparison at T=26 degC raises
    :class:`ABControlTableError` even though GAIL alone spans up to 30 degC.
    """

    return ReferenceBComparison(
        temp_c=temp_c,
        pressure_bar=pressure_bar,
        control_point=lookup_botas_reference_point(temp_c=temp_c, pressure_bar=pressure_bar),
        gail_point=lookup_gail_reference_point(temp_c=temp_c, pressure_bar=pressure_bar),
    )


__all__ = [
    "ABControlPoint",
    "ABControlTableError",
    "BOTAS_REFERENCE_OPTION_LABEL",
    "BOTAS_REFERENCE_TABLE_CSV_PATH",
    "BOTAS_REFERENCE_TABLE_LABEL",
    "BOTAS_REFERENCE_TABLE_METADATA_PATH",
    "ReferenceBComparison",
    "compare_reference_b_sources",
    "describe_botas_reference_table_range",
    "is_botas_reference_option",
    "lookup_botas_reference_point",
]

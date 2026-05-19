from __future__ import annotations

import csv
from io import StringIO
from typing import NamedTuple


class ParsedSegment(NamedTuple):
    outside_diameter_mm: float
    wall_thickness_mm: float
    length_m: float


class SegmentParseError(ValueError):
    pass


_OD_NAMES = {
    "od", "od (mm)", "dis cap", "dis cap (mm)", "outside_diameter_mm",
    "dış çap", "dış çap (mm)",
}
_WT_NAMES = {
    "et", "et (mm)", "wt", "et kalinligi", "et kalinligi (mm)",
    "wall_thickness_mm", "et kalınlığı", "et kalınlığı (mm)",
}
_LEN_NAMES = {
    "uzunluk", "uzunluk (m)", "l", "length", "length_m",
    "hat uzunlugu", "hat uzunlugu (m)", "hat uzunluğu", "hat uzunluğu (m)",
}


def _sniff_delimiter(raw: str) -> str:
    sniffer = csv.Sniffer()
    sample = "\n".join(raw.splitlines()[:5])
    try:
        dialect = sniffer.sniff(sample, delimiters=";,\t|")
        return dialect.delimiter
    except csv.Error:
        first_line = (raw.splitlines() or [""])[0]
        return ";" if ";" in first_line else ","


def _detect_column_indices(header: list[str], delimiter: str) -> tuple[int, int, int]:
    cleaned = [col.strip().lower().replace('"', "").replace("'", "") for col in header]
    if not cleaned:
        raise SegmentParseError("CSV basligi bos.")
    od_idx = next((i for i, col in enumerate(cleaned) if col in _OD_NAMES), 0)
    wt_idx = next((i for i, col in enumerate(cleaned) if col in _WT_NAMES), max(1, min(1, len(cleaned) - 1)))
    len_idx = next((i for i, col in enumerate(cleaned) if col in _LEN_NAMES), max(2, min(2, len(cleaned) - 1)))
    return od_idx, wt_idx, len_idx


def _clean_number(raw: str) -> str:
    return raw.strip().replace('"', "").replace("'", "").replace(",", ".")


def parse_segment_csv(raw: str) -> list[ParsedSegment]:
    if not raw.strip():
        return []
    delimiter = _sniff_delimiter(raw)
    reader = csv.reader(StringIO(raw), delimiter=delimiter)
    rows = list(reader)
    if len(rows) < 2:
        return []
    header = rows[0]
    od_idx, wt_idx, len_idx = _detect_column_indices(header, delimiter)
    result: list[ParsedSegment] = []
    for line_no, cols in enumerate(rows[1:], start=2):
        if len(cols) < 3:
            continue
        try:
            od = float(_clean_number(cols[od_idx]))
            wt = float(_clean_number(cols[wt_idx]))
            length = float(_clean_number(cols[len_idx]))
        except (ValueError, IndexError):
            continue
        if od > 0 and wt > 0 and length > 0 and (wt * 2) < od:
            result.append(ParsedSegment(od, wt, length))
    return result

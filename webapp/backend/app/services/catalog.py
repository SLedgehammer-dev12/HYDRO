"""Catalog endpoints backed by embedded `hidrostatik_test.data` tables."""

from __future__ import annotations

from typing import Any

from hidrostatik_test.data import (
    REPAIRABLE_A_ISSUE_KINDS,
    count_repaired_ab_control_points,
    find_ab_control_table_issues,
    find_api_5l_psl2_grade,
    find_pipe_size,
    find_schedule,
    get_api_5l_psl2_grade_options,
    get_schedule_options,
    load_ab_control_table,
)
from hidrostatik_test.data.ab_control_table import (
    DEFAULT_CONTROL_TABLE_CSV_PATH,
    DEFAULT_CONTROL_TABLE_METADATA_PATH,
)
from hidrostatik_test.data.gail_reference_table import (
    GAIL_REFERENCE_TABLE_CSV_PATH,
    GAIL_REFERENCE_TABLE_METADATA_PATH,
)
from hidrostatik_test.data.pipe_catalog import API_5L_PSL2_GRADES, PIPE_CATALOG


def _pipe_option_label(item: dict[str, Any]) -> str:
    return f"NPS {item['nps']} (DN {item['dn']}) - OD {float(item['outside_diameter_mm']):.2f} mm"


def _schedules(item: dict[str, Any]) -> list[dict[str, Any]]:
    label = _pipe_option_label(item)
    rows: list[dict[str, Any]] = []
    for formatted in get_schedule_options(label):
        schedule = find_schedule(label, formatted) or {}
        rows.append(
            {
                "label": formatted,
                "wall_thickness_mm": float(schedule.get("wall_thickness_mm", 0.0)),
            }
        )
    return rows


def list_pipes(*, q: str | None = None, limit: int = 200, offset: int = 0) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    needle = (q or "").strip().lower()
    for item in PIPE_CATALOG:
        label = _pipe_option_label(item)
        haystack = f"{item['nps']} {item['dn']} {item['outside_diameter_mm']} {label}".lower()
        if needle and needle not in haystack:
            continue
        items.append(
            {
                "nps": str(item["nps"]),
                "dn": str(item["dn"]),
                "outside_diameter_mm": float(item["outside_diameter_mm"]),
                "option_label": label,
                "schedules": _schedules(item),
            }
        )
    total = len(items)
    page = items[offset : offset + limit]
    return {"items": page, "total": total, "limit": limit, "offset": offset}


def pipe_schedules(nps: str) -> dict[str, Any]:
    from ..core.errors import not_found

    textual = (nps or "").strip()
    match: dict[str, Any] | None = None
    for item in PIPE_CATALOG:
        if textual in {str(item["nps"]), str(item["dn"])}:
            match = item
            break
    if match is None:
        # also accept the full option label
        match = find_pipe_size(textual)
    if match is None:
        raise not_found("pipe_schedule", textual)

    label = _pipe_option_label(match)
    return {
        "nps": str(match["nps"]),
        "dn": str(match["dn"]),
        "outside_diameter_mm": float(match["outside_diameter_mm"]),
        "option_label": label,
        "items": _schedules(match),
    }


def list_grades() -> dict[str, Any]:
    labels = get_api_5l_psl2_grade_options()
    items: list[dict[str, Any]] = []
    for label in labels:
        spec = find_api_5l_psl2_grade(label) or {}
        items.append(
            {
                "grade": str(spec.get("grade", "")),
                "iso_label": str(spec.get("iso_label", "")),
                "smys_mpa": float(spec.get("smys_mpa", 0.0)),
                "option_label": label,
            }
        )
    # Keep the declaration order of the embedded API 5L table.
    order = {str(spec["grade"]): index for index, spec in enumerate(API_5L_PSL2_GRADES)}
    items.sort(key=lambda row: order.get(row["grade"], 999))
    return {"items": items, "total": len(items), "limit": 50, "offset": 0}


def _axis_payload(spec: Any, axis: Any) -> dict[str, Any]:
    return {
        "min": axis.minimum,
        "max": axis.maximum,
        "step": axis.step,
        "count": axis.count,
    }


def _a_repair_payload() -> dict[str, Any]:
    issues = find_ab_control_table_issues(
        csv_path=DEFAULT_CONTROL_TABLE_CSV_PATH,
        metadata_path=DEFAULT_CONTROL_TABLE_METADATA_PATH,
    )
    repairable = [issue for issue in issues if issue.kind in REPAIRABLE_A_ISSUE_KINDS]
    temperatures = sorted({issue.temp_c for issue in repairable if issue.temp_c is not None})
    pressures = [issue.pressure_bar for issue in repairable if issue.pressure_bar is not None]
    pressure_range = [min(pressures), max(pressures)] if pressures else [81.0, 100.0]
    band = (
        temperatures[-1] - temperatures[0]
        if len(temperatures) > 1
        else (temperatures[0] if temperatures else 7.0)
    )
    return {
        "enabled": bool(repairable),
        "band_c": band,
        "temperature_c": temperatures[0] if temperatures else None,
        "pressure_range_bar": pressure_range,
        "repaired_cell_count": count_repaired_ab_control_points(),
    }


def reference_tables() -> dict[str, Any]:
    control_grid = load_ab_control_table(
        csv_path=DEFAULT_CONTROL_TABLE_CSV_PATH,
        metadata_path=DEFAULT_CONTROL_TABLE_METADATA_PATH,
    )
    gail_grid = load_ab_control_table(
        csv_path=GAIL_REFERENCE_TABLE_CSV_PATH,
        metadata_path=GAIL_REFERENCE_TABLE_METADATA_PATH,
    )
    control_spec = control_grid.spec
    gail_spec = gail_grid.spec
    items = [
        {
            "key": "institutional",
            "label": "Kurum ici A/B kontrol tablosu",
            "option_label": "BOTAŞ referans tablosu - aktif T/P",
            "temperature": _axis_payload(control_spec, control_spec.temperature_axis),
            "pressure": _axis_payload(control_spec, control_spec.pressure_axis),
            "a_unit": control_spec.a_unit,
            "b_unit": control_spec.b_unit,
            "source_note": "A ve B Katsayisi.xlsx",
            "a_repair": _a_repair_payload(),
            "row_count": control_grid.row_count,
        },
        {
            "key": "gail",
            "label": "GAIL referans tablosu",
            "option_label": "GAIL referans tablosu - aktif T/P",
            "temperature": _axis_payload(gail_spec, gail_spec.temperature_axis),
            "pressure": _axis_payload(gail_spec, gail_spec.pressure_axis),
            "a_unit": gail_spec.a_unit,
            "b_unit": gail_spec.b_unit,
            "source_note": "GAIL-STD-PL-DOC-TS-012 Table-1 ve Fig.1",
            "a_repair": {"enabled": False},
            "row_count": gail_grid.row_count,
        },
    ]
    return {"items": items, "total": len(items), "limit": 20, "offset": 0}


__all__ = [
    "list_grades",
    "list_pipes",
    "pipe_schedules",
    "reference_tables",
]

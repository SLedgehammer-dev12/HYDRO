"""Desktop-compatible input snapshot (save/load).

The desktop JSON stores every numeric input as a string and modes by their
Turkish UI labels. The API stores canonical numbers/enums internally, so this
module owns the two-way conversion (presentation only, no calculations).
"""

from __future__ import annotations

import math
from typing import Any

from hidrostatik_test import APP_VERSION
from hidrostatik_test.domain import get_available_water_property_backends
from hidrostatik_test.domain.operations import get_pig_speed_limit_options

from ..core.errors import AppError
from ..core.timeutil import as_float, deep_merge, fmt_number, iso_z, utcnow
from ..desktop_labels import (
    B_SOURCE_TO_KEY,
    KEY_TO_B_SOURCE_LABEL,
    KEY_TO_MODE,
    KEY_TO_STEEL_MODEL_LABEL,
    MODE_TO_KEY,
    STEEL_MODEL_TO_KEY,
)

NUMERIC_SECTIONS: dict[str, tuple[str, ...]] = {
    "geometry": ("outside_diameter_mm", "wall_thickness_mm", "length_m"),
    "section_profile": (
        "highest_elevation_m",
        "lowest_elevation_m",
        "start_elevation_m",
        "end_elevation_m",
        "design_pressure_bar",
        "smys_mpa",
    ),
    "air": (
        "temperature_c",
        "pressure_bar",
        "a_micro_per_bar",
        "pressure_rise_bar",
        "k_factor",
        "actual_added_water_m3",
        "ambient_temperature_c",
    ),
    "pressure": (
        "temperature_c",
        "pressure_bar",
        "a_micro_per_bar",
        "b_micro_per_c",
        "delta_t_c",
        "actual_pressure_change_bar",
        "t_initial_c",
        "t_final_c",
    ),
    "field": (
        "ambient_temperature_c",
        "pig_distance_m",
        "pig_travel_time_min",
    ),
    "helper": ("steel_alpha_micro_per_c", "water_beta_micro_per_c"),
}

DERIVED_FIELD_KEYS = ("pig_speed_m_per_s", "pig_speed_km_per_h")


def _backend_labels() -> dict[str, str]:
    return {
        info.key: info.label
        for info in get_available_water_property_backends(include_dev_backends=True)
    }


def backend_label(key: str | None, fallback: str = "") -> str:
    if not key:
        return fallback
    return _backend_labels().get(key, fallback or key)


def resolve_backend_key(label: str | None) -> str | None:
    if not label:
        return None
    text = label.strip()
    folded = text.casefold()
    labels = _backend_labels()
    for key in labels:
        if folded == key.casefold():
            return key
    for key, value in labels.items():
        if folded == value.casefold():
            return key
    if folded == "iapws":
        return "iapws95_dev" if "iapws95_dev" in labels else None
    for key, value in sorted(labels.items(), key=lambda item: len(item[1]), reverse=True):
        if folded.startswith(value.casefold()):
            return key
    return None


def _string_map(values: dict[str, Any], keys: tuple[str, ...], digits: int = 6) -> dict[str, str]:
    return {key: fmt_number(as_float(values.get(key)), digits) for key in keys}


def _segments_payload(segments: Any) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not isinstance(segments, list):
        return rows
    for item in segments:
        if not isinstance(item, dict):
            continue
        raw_smys = item.get("smys_mpa")
        smys_val = None if isinstance(raw_smys, bool) else as_float(raw_smys)
        rows.append(
            {
                "outside_diameter_mm": fmt_number(as_float(item.get("outside_diameter_mm"))),
                "wall_thickness_mm": fmt_number(as_float(item.get("wall_thickness_mm"))),
                "length_m": fmt_number(as_float(item.get("length_m"))),
                "nps_label": str(item.get("nps_label") or "-"),
                "schedule_label": str(item.get("schedule_label") or "Elle giris"),
                "material_grade": str(item.get("material_grade") or ""),
                "smys_mpa": fmt_number(smys_val, 3),
            }
        )
    return rows


def build_snapshot(inputs: dict[str, Any]) -> dict[str, Any]:
    inputs = inputs or {}
    geometry = inputs.get("geometry") or {}
    profile = inputs.get("section_profile") or {}
    catalog = inputs.get("geometry_catalog") or {}
    air = inputs.get("air") or {}
    pressure = inputs.get("pressure") or {}
    field = inputs.get("field") or {}
    helper = inputs.get("helper") or {}
    modes = inputs.get("modes") or {}
    checks = inputs.get("checks") or {}
    raw_report = inputs.get("report")
    raw_report_meta = inputs.get("report_meta")
    report_raw: dict[str, Any] = raw_report if isinstance(raw_report, dict) else {}
    report_meta_raw: dict[str, Any] = raw_report_meta if isinstance(raw_report_meta, dict) else {}
    report_payload = {
        key: str(report_raw.get(key) or report_meta_raw.get(key) or "")
        for key in ("report_no", "operator", "date", "section_id")
    }

    return {
        "schema_version": 1,
        "saved_at_utc": iso_z(utcnow()),
        "app_version": APP_VERSION,
        "active_tab": inputs.get("active_tab") or "air",
        "water_backend_option": backend_label(
            inputs.get("water_backend"), fallback="Table Interpolation v1"
        ),
        "geometry": _string_map(geometry, NUMERIC_SECTIONS["geometry"]),
        "section_profile": _string_map(profile, NUMERIC_SECTIONS["section_profile"]),
        "geometry_catalog": {
            "size_option": str(catalog.get("size_option") or ""),
            "schedule_option": str(catalog.get("schedule_option") or ""),
        },
        "material_grade": str(inputs.get("material_grade") or ""),
        "location_class": str(inputs.get("location_class") or ""),
        "pump_location": str(inputs.get("pump_location") or ""),
        "air": _string_map(air, NUMERIC_SECTIONS["air"]),
        "pressure": {
            **_string_map(
                pressure,
                (
                    "temperature_c",
                    "pressure_bar",
                    "a_micro_per_bar",
                    "b_micro_per_c",
                    "delta_t_c",
                    "actual_pressure_change_bar",
                    "t_initial_c",
                    "t_final_c",
                ),
            ),
            "derive_delta_t": bool(pressure.get("derive_delta_t", False)),
        },
        "field": {
            **_string_map(field, NUMERIC_SECTIONS["field"]),
            "pig_speed_m_per_s": fmt_number(as_float(field.get("pig_speed_m_per_s"))),
            "pig_speed_km_per_h": fmt_number(as_float(field.get("pig_speed_km_per_h"))),
        },
        "helper": _string_map(helper, NUMERIC_SECTIONS["helper"]),
        "modes": {
            "air_a_mode": KEY_TO_MODE.get(str(modes.get("air_a_mode", "auto")), "Otomatik"),
            "pressure_a_mode": KEY_TO_MODE.get(
                str(modes.get("pressure_a_mode", "auto")), "Otomatik"
            ),
            "pressure_b_mode": KEY_TO_MODE.get(str(modes.get("pressure_b_mode", "table")), "Tablo"),
            "pressure_b_source": KEY_TO_B_SOURCE_LABEL.get(
                str(modes.get("pressure_b_source", "institutional")),
                "Kurum ici tablo (varsayilan)",
            ),
            "steel_model": KEY_TO_STEEL_MODEL_LABEL.get(
                str(modes.get("steel_model", "volumetric")),
                "Hacimsel 3*alpha (varsayilan)",
            ),
            "air_a_reference": str(modes.get("air_a_reference") or ""),
            "pressure_a_reference": str(modes.get("pressure_a_reference") or ""),
            "pressure_b_reference": str(modes.get("pressure_b_reference") or ""),
            "k_preset": str(modes.get("k_preset") or ""),
            "steel_preset": str(modes.get("steel_preset") or ""),
            "pig_mode": str(modes.get("pig_mode") or "Temizlik pigi"),
        },
        "checks": {str(key): bool(value) for key, value in checks.items()},
        "geometry_segments": _segments_payload(inputs.get("segments")),
        "report": report_payload,
        "report_entries": [
            str(item) for item in (inputs.get("report_entries") or []) if item is not None
        ],
    }


class _ApplyState:
    def __init__(self) -> None:
        self.converted = 0
        self.skipped: list[str] = []
        self.invalid_fields: list[str] = []
        self.warnings: list[str] = []

    def number(self, raw: Any, field: str, *, required_key: bool = True) -> float | None:
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            return None
        if isinstance(raw, bool):
            self.invalid_fields.append(field)
            return None
        value = as_float(raw)
        if value is None:
            self.invalid_fields.append(field)
            return None
        if not math.isfinite(value):
            self.invalid_fields.append(field)
            return None
        self.converted += 1
        return value

    def text(self, raw: Any, field: str) -> str | None:
        if raw is None:
            return None
        text = str(raw).strip()
        if not text:
            return None
        self.converted += 1
        return text

    def boolean(self, raw: Any, field: str) -> bool | None:
        if raw is None:
            return None
        if isinstance(raw, bool):
            self.converted += 1
            return raw
        if isinstance(raw, (int, float)):
            if raw in (0, 1):
                self.converted += 1
                return bool(raw)
            self.invalid_fields.append(field)
            return None
        if isinstance(raw, str):
            text = raw.strip().lower()
            if not text:
                return None
            if text in {"1", "true", "yes", "on", "evet"}:
                self.converted += 1
                return True
            if text in {"0", "false", "no", "off", "hayir", "hayır"}:
                self.converted += 1
                return False
            self.invalid_fields.append(field)
            return None
        self.invalid_fields.append(field)
        return None


def _prune_none(value: Any) -> Any:
    if isinstance(value, dict):
        pruned: dict[str, Any] = {}
        for key, item in value.items():
            cleaned = _prune_none(item)
            if cleaned is None:
                continue
            pruned[key] = cleaned
        return pruned
    if isinstance(value, list):
        return value
    return value


def apply_snapshot(
    inputs: dict[str, Any],
    snapshot: dict[str, Any],
    *,
    mode: str = "merge",
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(snapshot, dict):
        raise AppError(
            "invalid_snapshot",
            "Snapshot bir JSON nesnesi olmalidir.",
            status_code=400,
            details={"errors": ["body.snapshot must be an object"]},
        )
    schema_version = snapshot.get("schema_version", 1)
    if schema_version not in (1, "1"):
        raise AppError(
            "invalid_snapshot",
            f"Desteklenmeyen snapshot schema_version: {schema_version}",
            status_code=400,
            details={"errors": [f"schema_version={schema_version}"]},
        )

    state = _ApplyState()
    patch: dict[str, Any] = {}

    for section, keys in NUMERIC_SECTIONS.items():
        raw_section = snapshot.get(section)
        if not isinstance(raw_section, dict):
            continue
        converted_section: dict[str, Any] = {}
        for key in keys:
            if key not in raw_section:
                continue
            converted_section[key] = state.number(raw_section.get(key), f"{section}.{key}")
        if converted_section:
            patch[section] = converted_section

    raw_pressure = snapshot.get("pressure")
    if isinstance(raw_pressure, dict) and "derive_delta_t" in raw_pressure:
        derive_val = state.boolean(raw_pressure.get("derive_delta_t"), "pressure.derive_delta_t")
        if derive_val is not None:
            patch.setdefault("pressure", {})["derive_delta_t"] = derive_val

    raw_section_meta = snapshot.get("section_meta")
    if isinstance(raw_section_meta, dict):
        sec_meta_patch: dict[str, str] = {}
        for key in (
            "section_no",
            "description",
            "location",
            "start_kp",
            "end_kp",
            "test_date",
            "test_type",
            "notes",
        ):
            if key in raw_section_meta:
                val_text = state.text(raw_section_meta.get(key), f"section_meta.{key}")
                if val_text is not None:
                    sec_meta_patch[key] = val_text
        if sec_meta_patch:
            patch["section_meta"] = sec_meta_patch

    for section in ("geometry_catalog",):
        raw_section = snapshot.get(section)
        if isinstance(raw_section, dict):
            converted_section = {}
            for key in ("size_option", "schedule_option"):
                if key in raw_section:
                    text_val = state.text(raw_section.get(key), f"{section}.{key}")
                    if text_val is not None:
                        converted_section[key] = text_val
            if converted_section:
                patch[section] = converted_section

    for key in ("material_grade", "location_class", "pump_location"):
        if key in snapshot:
            text_val = state.text(snapshot.get(key), key)
            if text_val is not None:
                patch[key] = text_val

    active_tab = state.text(snapshot.get("active_tab"), "active_tab")
    if active_tab:
        if active_tab not in {"air", "pressure", "field"}:
            state.invalid_fields.append("active_tab")
        else:
            patch["active_tab"] = active_tab

    raw_modes = snapshot.get("modes")
    if isinstance(raw_modes, dict):
        modes_patch: dict[str, Any] = {}
        for key in ("air_a_mode", "pressure_a_mode", "pressure_b_mode"):
            raw_mode = raw_modes.get(key)
            if raw_mode is None or not str(raw_mode).strip():
                continue
            mapped = MODE_TO_KEY.get(str(raw_mode).strip())
            if mapped is None:
                state.invalid_fields.append(f"modes.{key}")
                continue
            modes_patch[key] = mapped
            state.converted += 1

        raw_source = raw_modes.get("pressure_b_source")
        if raw_source is not None and str(raw_source).strip():
            mapped_source = B_SOURCE_TO_KEY.get(str(raw_source).strip())
            if mapped_source is None:
                mode_value = modes_patch.get("pressure_b_mode")
                reference = str(raw_modes.get("pressure_b_reference") or "")
                if mode_value == "auto":
                    mapped_source = "auto"
                elif "GAIL" in reference.upper():
                    mapped_source = "gail"
                else:
                    mapped_source = "institutional"
                state.warnings.append(
                    "B kaynagi etiketi taninmadi; mod ve referans tablosundan turetildi."
                )
            else:
                state.converted += 1
            modes_patch["pressure_b_source"] = mapped_source

        raw_model = raw_modes.get("steel_model")
        if raw_model is not None and str(raw_model).strip():
            mapped_model = STEEL_MODEL_TO_KEY.get(str(raw_model).strip())
            if mapped_model is None:
                state.invalid_fields.append("modes.steel_model")
            else:
                modes_patch["steel_model"] = mapped_model
                state.converted += 1

        for key in (
            "air_a_reference",
            "pressure_a_reference",
            "pressure_b_reference",
            "k_preset",
            "steel_preset",
            "pig_mode",
        ):
            if key in raw_modes:
                value = state.text(raw_modes.get(key), f"modes.{key}")
                if value is not None:
                    modes_patch[key] = value
        if modes_patch:
            patch["modes"] = modes_patch

    raw_checks = snapshot.get("checks")
    if isinstance(raw_checks, dict):
        checks_patch = {
            str(key): state.boolean(value, f"checks.{key}") for key, value in raw_checks.items()
        }
        patch["checks"] = {key: value for key, value in checks_patch.items() if value is not None}

    raw_segments = snapshot.get("geometry_segments")
    if isinstance(raw_segments, list):
        segments: list[dict[str, Any]] = []
        for index, item in enumerate(raw_segments):
            if not isinstance(item, dict):
                state.invalid_fields.append(f"geometry_segments[{index}]")
                continue
            parsed_dims: dict[str, float] = {}
            for dim_key in ("outside_diameter_mm", "wall_thickness_mm", "length_m"):
                raw_dim = item.get(dim_key)
                if (
                    raw_dim is None
                    or (isinstance(raw_dim, str) and not raw_dim.strip())
                    or isinstance(raw_dim, bool)
                ):
                    state.invalid_fields.append(f"geometry_segments[{index}].{dim_key}")
                    continue
                dim_val = as_float(raw_dim)
                if dim_val is None or not math.isfinite(dim_val):
                    state.invalid_fields.append(f"geometry_segments[{index}].{dim_key}")
                    continue
                parsed_dims[dim_key] = dim_val
            if len(parsed_dims) < 3:
                continue
            state.converted += 3
            raw_seg_smys = item.get("smys_mpa")
            seg_smys: float | None = None
            if raw_seg_smys is not None and not (
                isinstance(raw_seg_smys, str) and not raw_seg_smys.strip()
            ):
                if isinstance(raw_seg_smys, bool):
                    state.invalid_fields.append(f"geometry_segments[{index}].smys_mpa")
                else:
                    parsed_seg_smys = as_float(raw_seg_smys)
                    if (
                        parsed_seg_smys is None
                        or not math.isfinite(parsed_seg_smys)
                        or parsed_seg_smys <= 0
                    ):
                        state.invalid_fields.append(f"geometry_segments[{index}].smys_mpa")
                    else:
                        seg_smys = parsed_seg_smys
                        state.converted += 1
            seg_grade = (
                state.text(item.get("material_grade"), f"geometry_segments[{index}].material_grade")
                or ""
            )
            segments.append(
                {
                    "outside_diameter_mm": parsed_dims["outside_diameter_mm"],
                    "wall_thickness_mm": parsed_dims["wall_thickness_mm"],
                    "length_m": parsed_dims["length_m"],
                    "nps_label": str(item.get("nps_label") or "-"),
                    "schedule_label": str(item.get("schedule_label") or "Elle giris"),
                    "material_grade": seg_grade,
                    "smys_mpa": seg_smys,
                }
            )
        patch["segments"] = segments

    raw_entries = snapshot.get("report_entries")
    if isinstance(raw_entries, list):
        patch["report_entries"] = [str(item) for item in raw_entries if item is not None]

    maybe_report = snapshot.get("report")
    maybe_report_meta = snapshot.get("report_meta")
    raw_report: dict[str, Any] = maybe_report if isinstance(maybe_report, dict) else {}
    raw_report_meta: dict[str, Any] = (
        maybe_report_meta if isinstance(maybe_report_meta, dict) else {}
    )
    if raw_report or raw_report_meta:
        report_patch: dict[str, str] = {}
        for key in ("report_no", "operator", "date", "section_id"):
            val = raw_report.get(key)
            if val is None or not str(val).strip():
                val = raw_report_meta.get(key)
            text = state.text(val, f"report.{key}")
            if text is not None:
                report_patch[key] = text
        if report_patch:
            patch["report"] = report_patch
            section_id = report_patch.get("section_id")
            patch_sec_meta = patch.get("section_meta")
            existing_sec_meta = inputs.get("section_meta") if mode != "replace" else None
            has_patch_section_no = isinstance(patch_sec_meta, dict) and bool(
                str(patch_sec_meta.get("section_no") or "").strip()
            )
            has_existing_section_no = isinstance(existing_sec_meta, dict) and bool(
                str(existing_sec_meta.get("section_no") or "").strip()
            )
            if section_id and not has_patch_section_no and not has_existing_section_no:
                patch.setdefault("section_meta", {})["section_no"] = section_id

    backend_option = snapshot.get("water_backend_option")
    if backend_option is None or not str(backend_option).strip():
        backend_option = snapshot.get("water_backend")
    if backend_option is not None and str(backend_option).strip():
        resolved_backend_key = resolve_backend_key(str(backend_option))
        if resolved_backend_key is None:
            state.warnings.append("Su backend'i etiketi taninmadi; mevcut backend korundu.")
        else:
            patch["water_backend"] = resolved_backend_key
            state.converted += 1

    # Sync canonical ambient_temperature_c between field and air inside patch
    # before deep_merge so existing air values never override a new field update.
    patch_air = patch.get("air")
    patch_field = patch.get("field")
    has_patch_air_amb = (
        isinstance(patch_air, dict) and patch_air.get("ambient_temperature_c") is not None
    )
    has_patch_fld_amb = (
        isinstance(patch_field, dict) and patch_field.get("ambient_temperature_c") is not None
    )
    if has_patch_fld_amb and not has_patch_air_amb:
        assert isinstance(patch_field, dict)
        patch.setdefault("air", {})["ambient_temperature_c"] = patch_field["ambient_temperature_c"]
    elif has_patch_air_amb and not has_patch_fld_amb:
        assert isinstance(patch_air, dict)
        patch.setdefault("field", {})["ambient_temperature_c"] = patch_air["ambient_temperature_c"]

    for derived in DERIVED_FIELD_KEYS:
        raw_field = snapshot.get("field")
        if isinstance(raw_field, dict) and derived in raw_field:
            state.skipped.append(f"field.{derived}")
            state.invalid_fields = [
                item for item in state.invalid_fields if item != f"field.{derived}"
            ]

    if mode == "replace":
        next_inputs = deep_merge({}, patch)
    else:
        next_inputs = deep_merge(inputs or {}, _prune_none(patch))

    mapping = {
        "converted": state.converted,
        "skipped": state.skipped,
        "invalid_fields": state.invalid_fields,
        "warnings": state.warnings,
    }
    return next_inputs, mapping


def pig_mode_options() -> list[str]:
    return list(get_pig_speed_limit_options())


__all__ = [
    "DERIVED_FIELD_KEYS",
    "apply_snapshot",
    "backend_label",
    "build_snapshot",
    "pig_mode_options",
    "resolve_backend_key",
]

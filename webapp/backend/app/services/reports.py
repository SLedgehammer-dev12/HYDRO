"""Report generation: TXT, PDF and XLSX."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from hidrostatik_test import APP_NAME, APP_VERSION
from hidrostatik_test.app_metadata import (
    SPEC_DOCUMENT_CODE,
    SPEC_DOCUMENT_TITLE,
)
from hidrostatik_test.services.report_export import (
    export_excel_report,
    export_pdf_report,
)

from ..core.config import Settings
from ..core.errors import AppError
from ..core.timeutil import as_float, fmt_number, iso_z, utcnow
from ..desktop_labels import FIELD_CHECKS, KEY_TO_B_SOURCE_LABEL
from ..models import HydroSession, TestResult
from .snapshot import backend_label

FORMAT_ALIASES = {"pdf": "pdf", "xlsx": "xlsx", "txt": "txt"}
CONTENT_TYPES = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "txt": "text/plain; charset=utf-8",
}
EXTENSIONS = {"pdf": ".pdf", "xlsx": ".xlsx", "txt": ".txt"}


def _latest_by_type(results: Iterable[TestResult]) -> dict[str, TestResult]:
    latest: dict[str, TestResult] = {}
    for row in sorted(results, key=lambda item: item.computed_at):
        latest[row.test_type] = row
    return latest


def _decision(row: TestResult | None) -> dict[str, Any]:
    if row is None:
        return {"status": "BEKLIYOR", "summary": "Kaydedilecek sonuc yok."}
    if isinstance(row.decision, dict) and row.decision:
        return row.decision
    return {
        "status": row.decision_status,
        "title": row.decision_title,
        "summary": row.decision_summary,
        "rule": row.decision_rule,
    }


def _geometry_rows(inputs: dict[str, Any]) -> list[dict[str, Any]]:
    segments = inputs.get("segments") or []
    rows: list[dict[str, Any]] = []
    if isinstance(segments, list):
        for item in segments:
            if not isinstance(item, dict):
                continue
            rows.append(item)
    return rows


def build_context(session: HydroSession, results: Iterable[TestResult]) -> dict[str, Any]:
    inputs = session.inputs or {}
    latest = _latest_by_type(results)
    geometry = inputs.get("geometry") or {}
    profile = inputs.get("section_profile") or {}
    segments = _geometry_rows(inputs)
    if segments:
        total_length = sum(as_float(item.get("length_m")) or 0.0 for item in segments)
        od = as_float(segments[0].get("outside_diameter_mm"))
        wt = as_float(segments[0].get("wall_thickness_mm"))
    else:
        total_length = as_float(geometry.get("length_m"))
        od = as_float(geometry.get("outside_diameter_mm"))
        wt = as_float(geometry.get("wall_thickness_mm"))

    metadata = {
        "Surum": APP_VERSION,
        "Referans sartname": f"{SPEC_DOCUMENT_CODE} - {SPEC_DOCUMENT_TITLE}",
        "Olusturma zamani": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Su backend'i": backend_label(
            str(inputs.get("water_backend") or ""),
            fallback=str(inputs.get("water_backend") or ""),
        ),
        "B kaynagi": KEY_TO_B_SOURCE_LABEL.get(
            str((inputs.get("modes") or {}).get("pressure_b_source") or ""),
            str((inputs.get("modes") or {}).get("pressure_b_source") or ""),
        ),
        "Oturum": session.name,
        "Secili pompa konumu": str(inputs.get("pump_location") or "-"),
    }
    geometry_data = {
        "Dis cap (mm)": fmt_number(od, 2) or "-",
        "Et kalinligi (mm)": fmt_number(wt, 2) or "-",
        "Hat uzunlugu (m)": fmt_number(total_length, 2) or "-",
        "Segment sayisi": str(len(segments) or 1),
        "Location Class": str(inputs.get("location_class") or "-"),
        "Boru malzeme kalitesi": str(inputs.get("material_grade") or "-"),
        "SMYS (MPa)": fmt_number(as_float(profile.get("smys_mpa")), 1) or "-",
        "Dizayn basinci (bar)": fmt_number(as_float(profile.get("design_pressure_bar")), 2) or "-",
        "En yuksek nokta (m)": fmt_number(as_float(profile.get("highest_elevation_m")), 2) or "-",
        "En dusuk nokta (m)": fmt_number(as_float(profile.get("lowest_elevation_m")), 2) or "-",
    }

    def add_test(key: str, title: str) -> None:
        row = latest.get(key)
        decision = _decision(row)
        test_results[f"{title} Karar"] = str(decision.get("status", "BEKLIYOR"))
        test_results[f"{title} Karar Ozeti"] = str(decision.get("summary", ""))

    test_results: dict[str, str] = {}
    add_test("air", "Hava")
    add_test("pressure", "Basinc")
    add_test("profile", "Profil")
    add_test("pig", "Pig")
    add_test("pressurization", "Basinclandirma")
    add_test("thermal_balance", "Termal Denge")

    checks = inputs.get("checks") or {}
    checklist = [
        {
            "checked": bool(checks.get(key)),
            "label": label,
            "ref": reference,
        }
        for key, label, reference in FIELD_CHECKS
    ]

    return {
        "title": "Hidrostatik Test Degerlendirme Raporu",
        "metadata": metadata,
        "geometry_data": geometry_data,
        "test_results": test_results,
        "checklist": checklist,
        "inputs": inputs,
        "latest": latest,
    }


def _checked_line(checked: bool, label: str, ref: str) -> str:
    mark = "X" if checked else " "
    return f"[{mark}] {label} ({ref})"


def build_report_text(context: dict[str, Any], session: HydroSession) -> str:
    inputs = context["inputs"]
    latest: dict[str, TestResult] = context["latest"]
    air = inputs.get("air") or {}
    pressure = inputs.get("pressure") or {}
    field = inputs.get("field") or {}
    helper = inputs.get("helper") or {}
    modes = inputs.get("modes") or {}
    profile = inputs.get("section_profile") or {}

    lines: list[str] = [
        f"{APP_NAME} Raporu",
        f"Surum: {APP_VERSION}",
        f"Referans sartname: {SPEC_DOCUMENT_CODE} - {SPEC_DOCUMENT_TITLE}",
        f"Olusturma zamani: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Oturum: {session.name}",
        "",
        "Boru Kesiti",
        f"Dis cap (mm): {context['geometry_data']['Dis cap (mm)']}",
        f"Et kalinligi (mm): {context['geometry_data']['Et kalinligi (mm)']}",
        f"Hat uzunlugu (m): {context['geometry_data']['Hat uzunlugu (m)']}",
        f"Location Class: {inputs.get('location_class') or '-'}",
        f"Pompa konumu: {inputs.get('pump_location') or '-'}",
        "",
    ]

    segments = _geometry_rows(inputs)
    if segments:
        lines.append("Segment Listesi")
        for index, item in enumerate(segments, start=1):
            lines.append(
                f"{index}. {item.get('nps_label') or '-'} | "
                f"{item.get('schedule_label') or '-'} | "
                f"OD {fmt_number(as_float(item.get('outside_diameter_mm')), 2)} mm | "
                f"Et {fmt_number(as_float(item.get('wall_thickness_mm')), 2)} mm | "
                f"L {fmt_number(as_float(item.get('length_m')), 2)} m"
            )
        lines.append("")

    lines.extend(
        [
            "Hava Icerik Testi Girdileri",
            f"Su sicakligi (°C): {fmt_number(as_float(air.get('temperature_c')))}",
            f"Su basinci (bar): {fmt_number(as_float(air.get('pressure_bar')))}",
            f"A (10^-6/bar): {fmt_number(as_float(air.get('a_micro_per_bar')))}",
            f"Basinc artisi P (bar): {fmt_number(as_float(air.get('pressure_rise_bar')))}",
            f"K faktor: {fmt_number(as_float(air.get('k_factor')))}",
            f"Fiili ilave su Vpa (m³): {fmt_number(as_float(air.get('actual_added_water_m3')))}",
            "",
            "Basinc Degisim Testi Girdileri",
            f"Su sicakligi (°C): {fmt_number(as_float(pressure.get('temperature_c')))}",
            f"Su basinci (bar): {fmt_number(as_float(pressure.get('pressure_bar')))}",
            f"A (10^-6/bar): {fmt_number(as_float(pressure.get('a_micro_per_bar')))}",
            f"B (10^-6/°C): {fmt_number(as_float(pressure.get('b_micro_per_c')))}",
            "Su sicaklik degisimi dT = Tilk - Tson (°C): "
            f"{fmt_number(as_float(pressure.get('delta_t_c')))}",
            "Fiili basinc degisimi Pa = Pilk - Pson (bar): "
            f"{fmt_number(as_float(pressure.get('actual_pressure_change_bar')))}",
            f"Celik alpha (micro/K): {fmt_number(as_float(helper.get('steel_alpha_micro_per_c')))}",
            f"B kaynagi: {modes.get('pressure_b_source') or '-'}",
            "",
            "Operasyon Kontrol Noktalari",
        ]
    )
    for item in context["checklist"]:
        lines.append(_checked_line(item["checked"], item["label"], item["ref"]))

    lines.extend(
        [
            "",
            "Pig Hiz Hesabi",
            f"Pig modu: {modes.get('pig_mode') or '-'}",
            f"Mesafe (m): {fmt_number(as_float(field.get('pig_distance_m')))}",
            f"Varis suresi (dakika): {fmt_number(as_float(field.get('pig_travel_time_min')))}",
            f"Pig hizi (m/s): {fmt_number(as_float(field.get('pig_speed_m_per_s')))}",
            f"Pig hizi (km/sa): {fmt_number(as_float(field.get('pig_speed_km_per_h')))}",
            "",
            "Nihai Karar",
            "Kabul kurali (hava): Vpa < 1.06 x Vp",
            "Kabul kurali (basinc): (Pa - Pt) <= 0.3 bar",
        ]
    )

    for key, title in (
        ("air", "Hava Icerik Testi"),
        ("pressure", "Basinc Degisim Testi"),
        ("profile", "Test Bolumu Basinc Penceresi"),
        ("pig", "Pig Hiz Hesabi"),
        ("pressurization", "Basinclandirma Kontrolu"),
        ("thermal_balance", "Termal Denge"),
    ):
        decision = _decision(latest.get(key))
        lines.extend(
            [
                f"{title} durumu: {decision.get('status', 'BEKLIYOR')}",
                f"{title} kurali: {decision.get('rule', '')}",
                f"{title} ozeti: {decision.get('summary', '')}",
            ]
        )

    lines.extend(["", "Oturum Sonuclari"])
    if latest:
        for row in sorted(latest.values(), key=lambda item: item.computed_at):
            lines.append(
                f"[{iso_z(row.computed_at)}] {row.test_type}: "
                f"{row.decision_status} - {row.decision_summary}"
            )
    else:
        lines.append("Kaydedilecek sonuc yok.")

    lines.extend(
        [
            "",
            "Not",
            "Nihai karar ASME B31.8 ve proje proseduru ile birlikte degerlendirilmelidir.",
            "Isaret sozlesmesi: dT = Tilk - Tson, Pa = Pilk - Pson.",
            f"SMYS (MPa): {fmt_number(as_float(profile.get('smys_mpa')), 1) or '-'}",
            f"Rapor uretim zamani (UTC): {iso_z(utcnow())}",
        ]
    )
    return "\n".join(lines)


def _target_path(settings: Settings, session_id: str, fmt: str) -> Path:
    folder = settings.exports_dir / session_id
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return folder / f"{stamp}-{uuid.uuid4().hex[:8]}-report{EXTENSIONS[fmt]}"


def write_report(
    settings: Settings,
    *,
    fmt: str,
    title: str,
    metadata: dict[str, Any],
    geometry_data: dict[str, Any],
    test_results: dict[str, Any],
    checklist: list[dict[str, Any]],
    text: str | None = None,
    target: Path,
) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "pdf":
        export_pdf_report(target, title, metadata, geometry_data, test_results, checklist)
    elif fmt == "xlsx":
        export_excel_report(target, title, metadata, geometry_data, test_results, checklist)
    elif fmt == "txt":
        target.write_text(text or "", encoding="utf-8")
    else:
        raise AppError(
            "unsupported_format",
            f"Desteklenmeyen rapor formati: {fmt}",
            status_code=422,
            details={"format": fmt, "supported": sorted(FORMAT_ALIASES)},
        )
    return target


def export_session(
    settings: Settings,
    session: HydroSession,
    results: Iterable[TestResult],
    *,
    fmt: str,
) -> tuple[Path, dict[str, Any]]:
    context = build_context(session, results)
    text = build_report_text(context, session) if fmt == "txt" else None
    target = _target_path(settings, session.id, fmt)
    try:
        write_report(
            settings,
            fmt=fmt,
            title=context["title"],
            metadata=context["metadata"],
            geometry_data=context["geometry_data"],
            test_results=context["test_results"],
            checklist=context["checklist"],
            text=text,
            target=target,
        )
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            "report_generation_failed",
            "Rapor olusturulamadi.",
            status_code=500,
            details={"reason": str(exc)},
        ) from exc
    return target, context


def free_export(
    settings: Settings,
    *,
    fmt: str,
    title: str,
    metadata: dict[str, Any],
    geometry_data: dict[str, Any],
    test_results: dict[str, Any],
    checklist: list[dict[str, Any]],
) -> Path:
    if not any((metadata, geometry_data, test_results, checklist)):
        raise AppError(
            "validation_error",
            "Rapor icerigi bos olamaz.",
            status_code=422,
            details={"field": "content"},
        )
    folder = settings.exports_dir / "_adhoc"
    folder.mkdir(parents=True, exist_ok=True)
    target = (
        folder
        / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}-{uuid.uuid4().hex[:8]}{EXTENSIONS[fmt]}"
    )
    text = None
    if fmt == "txt":
        lines = [title, ""]
        for section_name, section in (
            ("Metadata", metadata),
            ("Geometri", geometry_data),
            ("Sonuclar", test_results),
        ):
            if section:
                lines.append(section_name)
                lines.extend(f"{key}: {value}" for key, value in section.items())
                lines.append("")
        if checklist:
            lines.append("Kontrol Noktalari")
            for item in checklist:
                label = item.get("label", "")
                ref = item.get("ref", "")
                lines.append(_checked_line(bool(item.get("checked")), label, str(ref)))
        text = "\n".join(lines)
    try:
        write_report(
            settings,
            fmt=fmt,
            title=title,
            metadata=metadata,
            geometry_data=geometry_data,
            test_results=test_results,
            checklist=checklist,
            text=text,
            target=target,
        )
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            "report_generation_failed",
            "Rapor olusturulamadi.",
            status_code=500,
            details={"reason": str(exc)},
        ) from exc
    return target


def export_filename(fmt: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"hidrostatik_test_raporu_{stamp}{EXTENSIONS[fmt]}"


__all__ = [
    "CONTENT_TYPES",
    "EXTENSIONS",
    "build_context",
    "build_report_text",
    "export_filename",
    "export_session",
    "free_export",
]

"""Report generation: TXT, PDF and XLSX."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from hidrostatik_test import APP_NAME, APP_VERSION
from hidrostatik_test.app_metadata import (
    SPEC_DOCUMENT_CODE,
    SPEC_DOCUMENT_TITLE,
)
from hidrostatik_test.domain import (
    ValidationError,
    evaluate_fill_temperature,
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
from . import coefficients as coefficient_service
from .snapshot import backend_label

logger = logging.getLogger("hydro.web.reports")

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


def _resolve_report_meta(inputs: dict[str, Any]) -> dict[str, str]:
    maybe_report = inputs.get("report")
    maybe_legacy = inputs.get("report_meta")
    raw_report: dict[str, Any] = maybe_report if isinstance(maybe_report, dict) else {}
    raw_legacy: dict[str, Any] = maybe_legacy if isinstance(maybe_legacy, dict) else {}
    resolved: dict[str, str] = {}
    for key in ("report_no", "operator", "date", "section_id"):
        val = raw_report.get(key)
        text = "" if val is None else str(val).strip()
        if not text:
            legacy_val = raw_legacy.get(key)
            if legacy_val is not None:
                text = str(legacy_val).strip()
        resolved[key] = text
    return resolved


def _resolve_ambient_temp(inputs: dict[str, Any]) -> float | None:
    field = inputs.get("field") or {}
    air = inputs.get("air") or {}
    ambient = as_float(field.get("ambient_temperature_c"))
    if ambient is None:
        ambient = as_float(air.get("ambient_temperature_c"))
    return ambient


def build_context(
    session: HydroSession,
    results: Iterable[TestResult],
    *,
    include_backend_comparison: bool = False,
    time_series_rows: Iterable[Any] | None = None,
) -> dict[str, Any]:
    inputs = session.inputs or {}
    latest = _latest_by_type(results)
    geometry = inputs.get("geometry") or {}
    profile = inputs.get("section_profile") or {}
    air = inputs.get("air") or {}
    pressure = inputs.get("pressure") or {}
    segments = _geometry_rows(inputs)
    total_length: float | None
    if segments:
        total_length = sum(as_float(item.get("length_m")) or 0.0 for item in segments)
        od = as_float(segments[0].get("outside_diameter_mm"))
        wt = as_float(segments[0].get("wall_thickness_mm"))
    else:
        total_length = as_float(geometry.get("length_m"))
        od = as_float(geometry.get("outside_diameter_mm"))
        wt = as_float(geometry.get("wall_thickness_mm"))

    report_meta = _resolve_report_meta(inputs)
    section_meta = inputs.get("section_meta") or {}
    ambient_temp = _resolve_ambient_temp(inputs)
    fill_eval = None
    if ambient_temp is not None:
        try:
            fill_eval = evaluate_fill_temperature(ambient_temp)
        except ValidationError:
            fill_eval = None

    metadata: dict[str, Any] = {
        "Surum": APP_VERSION,
        "Referans sartname": f"{SPEC_DOCUMENT_CODE} - {SPEC_DOCUMENT_TITLE}",
        "Olusturma zamani": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Su backend'i": backend_label(
            str(inputs.get("water_backend") or ""),
            fallback=str(inputs.get("water_backend") or "table_v1"),
        ),
        "B kaynagi": KEY_TO_B_SOURCE_LABEL.get(
            str((inputs.get("modes") or {}).get("pressure_b_source") or ""),
            str((inputs.get("modes") or {}).get("pressure_b_source") or ""),
        ),
        "Oturum": session.name,
        "Test Bolumu": str(
            report_meta.get("section_id") or section_meta.get("section_no") or session.name or "-"
        ),
        "Rapor No": str(report_meta.get("report_no") or "-"),
        "Operator": str(report_meta.get("operator") or "-"),
        "Rapor Tarihi": str(report_meta.get("date") or section_meta.get("test_date") or "-"),
        "Secili pompa konumu": str(inputs.get("pump_location") or "-"),
    }
    if ambient_temp is not None and fill_eval is not None:
        metadata["Ortam hava sicakligi (10.1)"] = f"{ambient_temp:.1f} °C ({fill_eval.status})"
        if not fill_eval.passed:
            metadata["Dolum sicaklik uyarisi (10.1)"] = fill_eval.message

    ref_t = as_float(pressure.get("temperature_c"))
    if ref_t is None:
        ref_t = as_float(air.get("temperature_c"))
    ref_p = as_float(pressure.get("pressure_bar"))
    if ref_p is None:
        ref_p = as_float(air.get("pressure_bar"))
    backend_cmp: dict[str, Any] | None = None
    backend_cmp_error: str | None = None
    if include_backend_comparison and ref_t is not None and ref_p is not None and ref_p > 0:
        try:
            backend_cmp = coefficient_service.backend_comparison(
                temperature_c=ref_t,
                pressure_bar=ref_p,
                include_dev_backends=False,
            )
        except Exception:
            logger.exception("Backend comparison failed during report export")
            backend_cmp_error = "Su ozelligi backend karsilastirmasi uretilemedi."
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
    add_test("pressurization_ramp", "Basinclandirma Izleme")
    add_test("pressure_hold", "2 Saatlik Bekleme")
    add_test("depressurization", "Basinc Dusurme")
    add_test("discharge", "Bosaltma")

    ts_summary: dict[str, Any] | None = None
    ts_row_list = list(time_series_rows) if time_series_rows is not None else []
    if ts_row_list:
        from .sessions import time_series_summary

        ts_summary = time_series_summary(ts_row_list)
        rec_dec = ts_summary.get("recording_decision") or {}
        test_results["Zaman Serisi Kayit Sayisi"] = str(ts_summary.get("record_count", 0))
        test_results["Zaman Serisi Sure (sa)"] = (
            fmt_number(as_float(ts_summary.get("duration_hours")), 2) or "-"
        )
        pa_ts = as_float(ts_summary.get("pressure_change_pa_bar"))
        if pa_ts is not None:
            test_results["Zaman Serisi Basinc Pa (bar)"] = (
                f"{fmt_number(pa_ts, 3)} "
                f"(Pilk={fmt_number(as_float(ts_summary.get('initial_pressure_bar')), 2)} -> "
                f"Pson={fmt_number(as_float(ts_summary.get('final_pressure_bar')), 2)})"
            )
        dt_ts = as_float(ts_summary.get("temperature_change_dt_c"))
        if dt_ts is not None:
            test_results["Zaman Serisi Sicaklik dT (°C)"] = (
                f"{fmt_number(dt_ts, 3)} "
                f"(Tilk={fmt_number(as_float(ts_summary.get('initial_temperature_c')), 2)} -> "
                f"Tson={fmt_number(as_float(ts_summary.get('final_temperature_c')), 2)})"
            )
        test_results["24 Saatlik Kayit Kontrolu (15.1)"] = str(rec_dec.get("status", "BEKLIYOR"))

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
        "ambient_temperature_c": ambient_temp,
        "fill_temperature_eval": fill_eval,
        "backend_comparison": backend_cmp,
        "backend_comparison_error": backend_cmp_error,
        "time_series_summary": ts_summary,
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
    ambient_temp: float | None = context.get("ambient_temperature_c")
    fill_eval = context.get("fill_temperature_eval")
    water_backend_text = context["metadata"].get("Su backend'i", "-")

    lines: list[str] = [
        f"{APP_NAME} Raporu",
        f"Surum: {APP_VERSION}",
        f"Referans sartname: {SPEC_DOCUMENT_CODE} - {SPEC_DOCUMENT_TITLE}",
        f"Olusturma zamani: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Oturum: {session.name}",
        f"Test Bolumu: {context['metadata'].get('Test Bolumu', '-')}",
        f"Rapor No: {context['metadata'].get('Rapor No', '-')}",
        f"Operator: {context['metadata'].get('Operator', '-')}",
        f"Rapor Tarihi: {context['metadata'].get('Rapor Tarihi', '-')}",
        f"Su backend'i: {water_backend_text}",
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

    air_lines = [
        "Hava Icerik Testi Girdileri",
        f"Su sicakligi (°C): {fmt_number(as_float(air.get('temperature_c')))}",
        f"Su basinci (bar): {fmt_number(as_float(air.get('pressure_bar')))}",
        f"A (10^-6/bar): {fmt_number(as_float(air.get('a_micro_per_bar')))}",
        f"Basinc artisi P (bar): {fmt_number(as_float(air.get('pressure_rise_bar')))}",
        f"K faktor: {fmt_number(as_float(air.get('k_factor')))}",
        f"Fiili ilave su Vpa (m³): {fmt_number(as_float(air.get('actual_added_water_m3')))}",
        f"Ortam hava sicakligi (10.1, °C): {fmt_number(ambient_temp, 1) if ambient_temp is not None else '-'}",
    ]
    if ambient_temp is not None and fill_eval is not None and not fill_eval.passed:
        air_lines.append(f"UYARI (Sartname 10.1): {fill_eval.message}")

    t_initial = as_float(pressure.get("t_initial_c"))
    t_final = as_float(pressure.get("t_final_c"))
    pressure_lines = [
        "",
        "Basinc Degisim Testi Girdileri",
        f"Su sicakligi (°C): {fmt_number(as_float(pressure.get('temperature_c')))}",
        f"Su basinci (bar): {fmt_number(as_float(pressure.get('pressure_bar')))}",
        f"A (10^-6/bar): {fmt_number(as_float(pressure.get('a_micro_per_bar')))}",
        f"B (10^-6/°C): {fmt_number(as_float(pressure.get('b_micro_per_c')))}",
    ]
    if t_initial is not None or t_final is not None:
        pressure_lines.append(
            f"Baslangic sicakligi Tilk (°C): {fmt_number(t_initial) if t_initial is not None else '-'}"
        )
        pressure_lines.append(
            f"Bitis sicakligi Tson (°C): {fmt_number(t_final) if t_final is not None else '-'}"
        )
    pressure_lines.extend(
        [
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
    lines.extend([*air_lines, *pressure_lines])
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
        ("pressurization_ramp", "Basinclandirma Izleme"),
        ("pressure_hold", "2 Saatlik Bekleme"),
        ("depressurization", "Basinc Dusurme"),
        ("discharge", "Bosaltma"),
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

    ts_summary = context.get("time_series_summary")
    if isinstance(ts_summary, dict) and int(ts_summary.get("record_count") or 0) > 0:
        tb_dec = ts_summary.get("decision") or {}
        rec_dec = ts_summary.get("recording_decision") or {}
        lines.extend(
            [
                "",
                "Zaman Serisi Izleme (Bolum 12 & 15)",
                f"Kayit sayisi: {ts_summary.get('record_count', 0)} | "
                f"Ilk-son zaman: {ts_summary.get('first_timestamp') or '-'} -> "
                f"{ts_summary.get('last_timestamp') or '-'}",
                f"Sure: {fmt_number(as_float(ts_summary.get('duration_hours')), 2) or '-'} sa | "
                f"En uzun okuma araligi: {fmt_number(as_float(ts_summary.get('max_gap_hours')), 2) or '-'} sa",
                f"Basinc: Pilk={fmt_number(as_float(ts_summary.get('initial_pressure_bar')), 2) or '-'} bar -> "
                f"Pson={fmt_number(as_float(ts_summary.get('final_pressure_bar')), 2) or '-'} bar | "
                f"Pa={fmt_number(as_float(ts_summary.get('pressure_change_pa_bar')), 3) or '-'} bar",
                f"Sicaklik: Tilk={fmt_number(as_float(ts_summary.get('initial_temperature_c')), 2) or '-'} °C -> "
                f"Tson={fmt_number(as_float(ts_summary.get('final_temperature_c')), 2) or '-'} °C | "
                f"dT={fmt_number(as_float(ts_summary.get('temperature_change_dt_c')), 3) or '-'} °C",
                f"4 saatlik blok ortalamalari: onceki={fmt_number(as_float(ts_summary.get('previous_4h_avg_c')), 3) or '-'} °C, "
                f"son={fmt_number(as_float(ts_summary.get('average_temperature_last_4h_c')), 3) or '-'} °C, "
                f"|dT_4h|={fmt_number(as_float(ts_summary.get('temp_diff_c')), 3) or '-'} °C",
                f"Termal denge karari (12): {tb_dec.get('status', 'BEKLIYOR')} - {tb_dec.get('summary', '')}",
                f"24 saatlik kayit karari (15.1): {rec_dec.get('status', 'BEKLIYOR')} - {rec_dec.get('summary', '')}",
            ]
        )

    backend_cmp = context.get("backend_comparison")
    if isinstance(backend_cmp, dict) and backend_cmp.get("items"):
        items = backend_cmp["items"]
        ref_item = next(
            (
                i
                for i in items
                if (i.get("backend") or {}).get("key") == "table_v1" and not i.get("error")
            ),
            next((i for i in items if not i.get("error")), None),
        )
        ref_a = as_float(ref_item.get("a_micro_per_bar")) if ref_item else None
        ref_beta = as_float(ref_item.get("beta_micro_per_c")) if ref_item else None
        lines.extend(
            [
                "",
                "Su Ozelligi Backend Karsilastirmasi "
                f"(T={fmt_number(as_float(backend_cmp.get('temperature_c')), 1)} °C, "
                f"P={fmt_number(as_float(backend_cmp.get('pressure_bar')), 1)} bar)",
            ]
        )
        for item in items:
            b_info = item.get("backend") or {}
            label = str(b_info.get("label") or b_info.get("key") or "-")
            err = item.get("error")
            if err:
                lines.append(f"- {label}: HATA - {err}")
                continue
            a_val = as_float(item.get("a_micro_per_bar"))
            beta_val = as_float(item.get("beta_micro_per_c"))
            rho_val = as_float(item.get("density_kg_per_m3"))
            da_str = (
                fmt_number(a_val - ref_a, 6) if a_val is not None and ref_a is not None else "-"
            )
            dbeta_str = (
                fmt_number(beta_val - ref_beta, 6)
                if beta_val is not None and ref_beta is not None
                else "-"
            )
            lines.append(
                f"- {label}: A={fmt_number(a_val, 6)} (dA={da_str}) | "
                f"beta={fmt_number(beta_val, 6)} (dbeta={dbeta_str}) | "
                f"rho={fmt_number(rho_val, 2)} kg/m3"
            )
    elif context.get("backend_comparison_error"):
        lines.extend(
            [
                "",
                f"Su Ozelligi Backend Karsilastirmasi: {context['backend_comparison_error']}",
            ]
        )

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
    time_series_rows: Iterable[Any] | None = None,
) -> tuple[Path, dict[str, Any]]:
    context = build_context(
        session,
        results,
        include_backend_comparison=(fmt == "txt"),
        time_series_rows=time_series_rows,
    )
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
        logger.exception("Report generation failed for session %s (%s)", session.id, fmt)
        raise AppError(
            "report_generation_failed",
            "Rapor olusturulamadi.",
            status_code=500,
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
        logger.exception("Ad-hoc report generation failed (%s)", fmt)
        raise AppError(
            "report_generation_failed",
            "Rapor olusturulamadi.",
            status_code=500,
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

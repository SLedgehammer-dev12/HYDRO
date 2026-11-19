"""Project-level dataset aggregation, Master Excel/PDF/CSV/JSON export, bulk section & form generation."""

from __future__ import annotations

import copy
import csv
import json
import math
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm.attributes import flag_modified

from hidrostatik_test.domain import (
    MAX_TEST_SECTION_LENGTH_M,
    MAX_TEST_SECTION_VOLUME_M3,
    AirContentInputs,
    PipeGeometry,
    PipeSection,
    PressureVariationInputs,
    SectionPressureProfileInputs,
    evaluate_air_content_test,
    evaluate_pig_speed,
    evaluate_pressure_variation_test,
    evaluate_section_pressure_profile,
    get_location_class_rule,
)
from hidrostatik_test.domain.operations import PIG_SPEED_LIMITS
from hidrostatik_test.services.report_export import _report_fonts

from ..core.config import Settings
from ..core.errors import validation_error
from ..core.security import safe_filename
from ..core.timeutil import as_float, iso_z, json_safe, utcnow
from ..domain_adapter import dataclass_dict, geometry_summary
from ..models import (
    HydroSession,
    Project,
    SectionForm,
    TestResult,
    TimeSeriesRecord,
    new_uuid,
)
from . import audit, decisions
from . import dossier as dossier_service
from . import projects as project_service
from . import sessions as session_service
from .coefficients import coefficient_a, coefficient_b

_KP_RE = re.compile(r"^\s*(?:KP\s*)?(\d{1,4})\s*\+\s*(\d{1,3}(?:[.,]\d+)?)\s*$", re.IGNORECASE)
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
EXPORT_CONTENT_TYPES: dict[str, str] = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
    "csv": "text/csv; charset=utf-8",
    "json": "application/json; charset=utf-8",
}


def _safe_cell(val: Any) -> Any:
    if isinstance(val, str) and val and val[0] in _FORMULA_PREFIXES:
        return "'" + val
    return val


def parse_kp_meters(raw: Any) -> float | None:
    text = str(raw or "").strip()
    if not text:
        return None
    m = _KP_RE.match(text)
    if m:
        km = int(m.group(1))
        m_part = float(m.group(2).replace(",", "."))
        return round(km * 1000.0 + m_part, 3)
    try:
        cleaned = text.upper().replace("KP", "").strip().replace(",", ".")
        val = float(cleaned)
        return round(val, 3) if math.isfinite(val) else None
    except ValueError:
        return None


def format_kp(meters: float) -> str:
    safe_m = max(0.0, float(meters))
    km = int(safe_m // 1000)
    rem = safe_m - km * 1000
    if abs(rem - round(rem)) < 0.01:
        return f"{km}+{int(round(rem)):03d}"
    return f"{km}+{rem:06.2f}"


def _geometry_metrics(inputs: dict[str, Any]) -> dict[str, float | int | str | None]:
    raw_segments = inputs.get("segments")
    segments: list[Any] = raw_segments if isinstance(raw_segments, list) else []
    raw_geom = inputs.get("geometry")
    geom: dict[str, Any] = raw_geom if isinstance(raw_geom, dict) else {}
    raw_profile = inputs.get("section_profile")
    profile: dict[str, Any] = raw_profile if isinstance(raw_profile, dict) else {}

    pipe_secs: list[PipeSection] = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        od = as_float(seg.get("outside_diameter_mm"))
        wt = as_float(seg.get("wall_thickness_mm"))
        length = as_float(seg.get("length_m"))
        if od and wt and length and od > 0 and wt > 0 and length > 0 and 2 * wt < od:
            pipe_secs.append(
                PipeSection(
                    outside_diameter_mm=od,
                    wall_thickness_mm=wt,
                    length_m=length,
                )
            )
    if not pipe_secs:
        od = as_float(geom.get("outside_diameter_mm"))
        wt = as_float(geom.get("wall_thickness_mm"))
        length = as_float(geom.get("length_m"))
        if od and wt and length and od > 0 and wt > 0 and length > 0 and 2 * wt < od:
            pipe_secs.append(
                PipeSection(outside_diameter_mm=od, wall_thickness_mm=wt, length_m=length)
            )

    total_len: float | None
    if pipe_secs:
        pipe_model = PipeGeometry(tuple(pipe_secs))
        total_len = sum(s.length_m for s in pipe_secs)
        total_vol: float | None = pipe_model.internal_volume_m3
        od_val: float | None = pipe_secs[0].outside_diameter_mm
        wt_val: float | None = pipe_secs[0].wall_thickness_mm
    else:
        total_len = as_float(geom.get("length_m"))
        total_vol = None
        od_val = as_float(geom.get("outside_diameter_mm"))
        wt_val = as_float(geom.get("wall_thickness_mm"))

    return {
        "length_m": round(total_len, 2) if total_len is not None else None,
        "volume_m3": round(total_vol, 3) if total_vol is not None else None,
        "od_mm": round(od_val, 2) if od_val is not None else None,
        "wt_mm": round(wt_val, 2) if wt_val is not None else None,
        "segment_count": len(segments) if segments else (1 if pipe_secs else 0),
        "design_pressure_bar": as_float(profile.get("design_pressure_bar")),
        "smys_mpa": as_float(profile.get("smys_mpa")),
    }


def _overall_section_status(
    *,
    air_status: str,
    pressure_status: str,
    profile_status: str,
    failed_forms: list[str],
    warning_forms: list[str],
) -> str:
    statuses = {air_status, pressure_status, profile_status}
    if "BASARISIZ" in statuses or failed_forms:
        return "BASARISIZ"
    if "KATSAYI GUNCELLENMELI" in statuses or "DOGRULANAMADI" in statuses or warning_forms:
        return "UYARI"
    if air_status == "BASARILI" and pressure_status == "BASARILI":
        return "BASARILI"
    if "BASARILI" in statuses:
        return "KISMI"
    return "BEKLIYOR"


# ---------------------------------------------------------------------------
# Project Dataset Aggregation
# ---------------------------------------------------------------------------


def build_project_dataset(
    db: OrmSession,
    project: Project,
    workspace_hash: str,
) -> dict[str, Any]:
    """Aggregate project sections, engineering metrics, KP continuity & BOTAŞ form matrix."""

    sessions = (
        db.execute(
            select(HydroSession).where(
                HydroSession.project_id == project.id,
                HydroSession.workspace_id_hash == workspace_hash,
                HydroSession.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    session_ids = [s.id for s in sessions]

    latest_results: dict[tuple[str, str], TestResult] = {}
    forms_by_session: dict[str, dict[str, SectionForm]] = {sid: {} for sid in session_ids}

    if session_ids:
        all_results = (
            db.execute(
                select(TestResult)
                .where(TestResult.session_id.in_(session_ids))
                .order_by(TestResult.computed_at.asc())
            )
            .scalars()
            .all()
        )
        for res in all_results:
            latest_results[(res.session_id, res.test_type)] = res

        all_forms = (
            db.execute(select(SectionForm).where(SectionForm.session_id.in_(session_ids)))
            .scalars()
            .all()
        )
        for form in all_forms:
            forms_by_session.setdefault(form.session_id, {})[form.form_code] = form

    def _sort_key(sess: HydroSession) -> tuple[float, str, str]:
        meta = (sess.inputs or {}).get("section_meta") or {}
        skp = parse_kp_meters(meta.get("start_kp"))
        return (
            skp if skp is not None else float("inf"),
            str(meta.get("section_no") or sess.name),
            sess.id,
        )

    ordered_sessions = sorted(sessions, key=_sort_key)

    kp_items: list[tuple[str, float, float]] = []
    section_rows: list[dict[str, Any]] = []
    matrix_rows: list[dict[str, Any]] = []

    req_total_per_sec = len(dossier_service.REQUIRED_FORM_SPECS)
    total_forms_filled = 0
    total_forms_required = req_total_per_sec * len(ordered_sessions)
    total_len = 0.0
    total_vol = 0.0
    passed_count = 0
    failed_count = 0
    pending_count = 0
    evaluated_count = 0

    for sess in ordered_sessions:
        inputs: dict[str, Any] = sess.inputs if isinstance(sess.inputs, dict) else {}
        raw_meta = inputs.get("section_meta")
        meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
        gm = _geometry_metrics(inputs)

        section_no = str(meta.get("section_no") or sess.name.split("·", 1)[0].strip() or sess.name)
        start_kp = str(meta.get("start_kp") or "")
        end_kp = str(meta.get("end_kp") or "")
        s_m = parse_kp_meters(start_kp)
        e_m = parse_kp_meters(end_kp)
        if s_m is not None and e_m is not None:
            kp_items.append((section_no, s_m, e_m))

        air_res = latest_results.get((sess.id, "air"))
        pres_res = latest_results.get((sess.id, "pressure"))
        prof_res = latest_results.get((sess.id, "profile"))

        air_out: dict[str, Any] = (
            air_res.result if air_res and isinstance(air_res.result, dict) else {}
        )
        pres_out: dict[str, Any] = (
            pres_res.result if pres_res and isinstance(pres_res.result, dict) else {}
        )
        pres_in: dict[str, Any] = (
            pres_res.inputs if pres_res and isinstance(pres_res.inputs, dict) else {}
        )
        prof_out: dict[str, Any] = (
            prof_res.result if prof_res and isinstance(prof_res.result, dict) else {}
        )
        raw_win = prof_out.get("selected_window")
        prof_win: dict[str, Any] = raw_win if isinstance(raw_win, dict) else {}

        air_status = air_res.decision_status if air_res else "BEKLIYOR"
        pres_status = pres_res.decision_status if pres_res else "BEKLIYOR"
        prof_status = prof_res.decision_status if prof_res else "BEKLIYOR"

        sec_forms = forms_by_session.get(sess.id, {})
        filled_req = 0
        failed_forms: list[str] = []
        warning_forms: list[str] = []
        dew_point_c: float | None = None
        matrix_cells: dict[str, dict[str, Any]] = {}

        for spec in dossier_service.BOTAS_FORM_CATALOG:
            f_row = sec_forms.get(spec.code)
            if f_row is None:
                matrix_cells[spec.code] = {
                    "status": "empty",
                    "revision": 0,
                    "page_count": 0,
                    "short_code": spec.botas_code.replace("BOT-FRM-İNB-001-", "").replace(
                        "BOT-FRM-", ""
                    ),
                }
                continue
            ext = f_row.extracted_data if isinstance(f_row.extracted_data, dict) else {}
            if spec.required and f_row.status != "empty":
                filled_req += 1
            if f_row.status == "failed":
                failed_forms.append(spec.code)
            elif f_row.status == "warning":
                warning_forms.append(spec.code)
            if spec.code in {"final_drying", "pre_drying"}:
                raw_dry = ext.get("drying")
                dry: dict[str, Any] = raw_dry if isinstance(raw_dry, dict) else {}
                measured_dew = as_float(dry.get("measured_dew_point_c"))
                if measured_dew is not None:
                    dew_point_c = measured_dew
            matrix_cells[spec.code] = {
                "status": f_row.status,
                "revision": int(f_row.revision or 0),
                "page_count": len(f_row.pages or []),
                "short_code": spec.botas_code.replace("BOT-FRM-İNB-001-", "").replace(
                    "BOT-FRM-", ""
                ),
            }

        total_forms_filled += filled_req
        overall = _overall_section_status(
            air_status=air_status,
            pressure_status=pres_status,
            profile_status=prof_status,
            failed_forms=failed_forms,
            warning_forms=warning_forms,
        )
        if overall == "BASARILI":
            passed_count += 1
            evaluated_count += 1
        elif overall == "BASARISIZ":
            failed_count += 1
            evaluated_count += 1
        elif overall in {"UYARI", "KISMI"}:
            evaluated_count += 1
        else:
            pending_count += 1

        sec_len = gm["length_m"]
        sec_vol = gm["volume_m3"]
        if isinstance(sec_len, (int, float)):
            total_len += float(sec_len)
        if isinstance(sec_vol, (int, float)):
            total_vol += float(sec_vol)

        section_rows.append(
            {
                "session_id": sess.id,
                "section_no": section_no,
                "name": sess.name,
                "status": sess.status,
                "revision": sess.revision,
                "start_kp": start_kp,
                "end_kp": end_kp,
                "length_m": sec_len,
                "outside_diameter_mm": gm["od_mm"],
                "wall_thickness_mm": gm["wt_mm"],
                "material_grade": str(inputs.get("material_grade") or ""),
                "smys_mpa": gm["smys_mpa"],
                "internal_volume_m3": sec_vol,
                "design_pressure_bar": gm["design_pressure_bar"],
                "window_min_bar": as_float(prof_win.get("minimum_required_pressure_bar")),
                "window_max_bar": as_float(prof_win.get("maximum_allowable_pressure_bar")),
                "air_ratio": as_float(air_out.get("ratio")),
                "air_status": air_status,
                "pressure_pt_bar": as_float(pres_out.get("theoretical_pressure_change_bar")),
                "pressure_pa_bar": as_float(pres_in.get("actual_pressure_change_bar")),
                "pressure_margin_bar": as_float(pres_out.get("margin_bar")),
                "delta_t_c": as_float(pres_in.get("delta_t_c")),
                "pressure_status": pres_status,
                "dew_point_c": dew_point_c,
                "forms_filled_required": filled_req,
                "forms_required_total": req_total_per_sec,
                "failed_forms": failed_forms,
                "warning_forms": warning_forms,
                "overall_status": overall,
                "updated_at": iso_z(sess.updated_at),
            }
        )
        matrix_rows.append(
            {
                "session_id": sess.id,
                "section_no": section_no,
                "name": sess.name,
                "cells": matrix_cells,
            }
        )

    continuity_issues: list[str] = []
    for idx in range(1, len(kp_items)):
        prev_no, _prev_s, prev_e = kp_items[idx - 1]
        cur_no, cur_s, _cur_e = kp_items[idx]
        diff = cur_s - prev_e
        if abs(diff) > 0.5:
            kind = "bosluk" if diff > 0 else "cakisma"
            continuity_issues.append(
                f"{prev_no} ({format_kp(prev_e)}) -> {cur_no} ({format_kp(cur_s)}): "
                f"{abs(diff):.1f} m {kind}"
            )

    forms_pct = (
        round((total_forms_filled / total_forms_required) * 100.0, 1)
        if total_forms_required > 0
        else 0.0
    )
    sections_pct = (
        round((evaluated_count / len(ordered_sessions)) * 100.0, 1) if ordered_sessions else 0.0
    )

    return {
        "generated_at": iso_z(utcnow()),
        "project": project_service.serialize_project(project, section_count=len(ordered_sessions)),
        "summary": {
            "section_count": len(ordered_sessions),
            "passed_sections": passed_count,
            "failed_sections": failed_count,
            "pending_sections": pending_count,
            "total_length_m": round(total_len, 2),
            "total_volume_m3": round(total_vol, 3),
            "forms_filled_total": total_forms_filled,
            "forms_required_total": total_forms_required,
            "forms_completion_pct": forms_pct,
            "sections_completion_pct": sections_pct,
            "continuity_ok": len(continuity_issues) == 0,
            "continuity_issues": continuity_issues,
        },
        "sections": section_rows,
        "form_catalog": [
            {
                "form_code": spec.code,
                "botas_code": spec.botas_code,
                "form_title": spec.title,
                "required": spec.required,
                "order": spec.order,
            }
            for spec in dossier_service.BOTAS_FORM_CATALOG
        ],
        "form_matrix": matrix_rows,
    }


# ---------------------------------------------------------------------------
# Project Master Export (XLSX, PDF, CSV, JSON)
# ---------------------------------------------------------------------------


def _status_fill(status: str) -> PatternFill:
    up = str(status or "").upper()
    if up in {"BASARILI", "PASSED"}:
        return PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
    if up in {"BASARISIZ", "FAILED"}:
        return PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
    if up in {"UYARI", "WARNING", "KISMI"}:
        return PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
    if up == "FILLED":
        return PatternFill(start_color="DBEAFE", end_color="DBEAFE", fill_type="solid")
    return PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")


def _auto_fit_worksheet(ws) -> None:  # noqa: ANN001
    for idx, col in enumerate(ws.columns, start=1):
        max_len = 10
        for cell in col:
            val = str(cell.value or "")
            if len(val) > max_len:
                max_len = min(len(val), 48)
        ws.column_dimensions[get_column_letter(idx)].width = max_len + 3


def _write_project_xlsx(target: Path, dataset: dict[str, Any]) -> None:
    wb = Workbook()
    header_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=10)
    title_font = Font(color="0F172A", bold=True, size=13)
    thin = Side(style="thin", color="CBD5E1")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    proj = dataset["project"]
    summary = dataset["summary"]

    # Sheet 1: Project summary & KP continuity
    ws1 = wb.active
    ws1.title = "1_Proje_Ozeti"
    ws1["A1"] = _safe_cell(f"HYDRO - Proje Master Hidrostatik Test Icmali: {proj['name']}")
    ws1["A1"].font = title_font
    meta_rows = [
        ("Proje Kodu", proj.get("code") or "-"),
        ("Musteri / Isveren", proj.get("client") or "-"),
        ("Yuklenici", proj.get("contractor") or "-"),
        ("Kontrol Teskilati", proj.get("supervisor") or "-"),
        ("Proje Durumu", proj.get("status") or "active"),
        ("Planlanan Hat Uzunlugu (m)", proj.get("pipeline_length_m") or "-"),
        ("Kayitli Kesit Sayisi", summary["section_count"]),
        ("Basarili Kesit", summary["passed_sections"]),
        ("Basarisiz Kesit", summary["failed_sections"]),
        ("Bekleyen Kesit", summary["pending_sections"]),
        ("Toplam Kesit Uzunlugu (m)", summary["total_length_m"]),
        ("Toplam Su Hacmi (m3)", summary["total_volume_m3"]),
        (
            "BOTAS Zorunlu Form Tamamlanma (%)",
            f"{summary['forms_completion_pct']} ({summary['forms_filled_total']}/{summary['forms_required_total']})",
        ),
        ("KP Sureklilik Durumu", "UYUMLU" if summary["continuity_ok"] else "UYUSMAZLIK VAR"),
        ("Rapor Olusturma Zamani", dataset.get("generated_at") or "-"),
    ]
    for r_idx, (label, val) in enumerate(meta_rows, start=3):
        c1 = ws1.cell(row=r_idx, column=1, value=_safe_cell(label))
        c2 = ws1.cell(row=r_idx, column=2, value=_safe_cell(val))
        c1.font = Font(bold=True, size=10)
        c1.border = border
        c2.border = border

    if summary["continuity_issues"]:
        start_r = len(meta_rows) + 5
        ws1.cell(row=start_r, column=1, value="KP Sureklilik Bulgulari").font = Font(
            bold=True, color="B91C1C"
        )
        for off, issue in enumerate(summary["continuity_issues"], start=1):
            ws1.cell(row=start_r + off, column=1, value=_safe_cell(issue))
    _auto_fit_worksheet(ws1)

    # Sheet 2: Section engineering register
    ws2 = wb.create_sheet("2_Kesit_Icmali")
    headers2 = [
        "Kesit No",
        "Kesit Adi",
        "Baslangic KP",
        "Bitis KP",
        "Uzunluk (m)",
        "OD (mm)",
        "WT (mm)",
        "Kalite",
        "Hacim (m3)",
        "Dizayn P (bar)",
        "Pmin (bar)",
        "Pmax (bar)",
        "Vpa/Vp",
        "Hava Durum",
        "Pt (bar)",
        "Pa (bar)",
        "Marj (bar)",
        "Delta T (C)",
        "Basinc Durum",
        "Dew Point (C)",
        "Zorunlu Form",
        "Nihai Durum",
    ]
    for c_idx, h in enumerate(headers2, start=1):
        cell = ws2.cell(row=1, column=c_idx, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.border = border
        cell.alignment = Alignment(horizontal="center")

    for r_idx, sec in enumerate(dataset["sections"], start=2):
        vals = [
            sec["section_no"],
            sec["name"],
            sec["start_kp"],
            sec["end_kp"],
            sec["length_m"],
            sec["outside_diameter_mm"],
            sec["wall_thickness_mm"],
            sec["material_grade"],
            sec["internal_volume_m3"],
            sec["design_pressure_bar"],
            sec["window_min_bar"],
            sec["window_max_bar"],
            sec["air_ratio"],
            sec["air_status"],
            sec["pressure_pt_bar"],
            sec["pressure_pa_bar"],
            sec["pressure_margin_bar"],
            sec["delta_t_c"],
            sec["pressure_status"],
            sec["dew_point_c"],
            f"{sec['forms_filled_required']}/{sec['forms_required_total']}",
            sec["overall_status"],
        ]
        for c_idx, val in enumerate(vals, start=1):
            cell = ws2.cell(row=r_idx, column=c_idx, value=_safe_cell(val))
            cell.border = border
            if c_idx in {14, 19, 22}:
                cell.fill = _status_fill(str(val or ""))
                cell.font = Font(bold=True, size=10)
    ws2.freeze_panes = "B2"
    _auto_fit_worksheet(ws2)

    # Sheet 3: BOTAŞ 16 Form matrix
    ws3 = wb.create_sheet("3_BOTAS_Form_Matrisi")
    catalog = dataset["form_catalog"]
    headers3 = ["Kesit No", "Kesit Adi"] + [
        f"{item['botas_code'].replace('BOT-FRM-İNB-001-', '').replace('BOT-FRM-', '')}"
        for item in catalog
    ]
    for c_idx, h in enumerate(headers3, start=1):
        cell = ws3.cell(row=1, column=c_idx, value=_safe_cell(h))
        cell.fill = header_fill
        cell.font = header_font
        cell.border = border
    for r_idx, mrow in enumerate(dataset["form_matrix"], start=2):
        c1 = ws3.cell(row=r_idx, column=1, value=_safe_cell(mrow["section_no"]))
        c2 = ws3.cell(row=r_idx, column=2, value=_safe_cell(mrow["name"]))
        c1.border = border
        c2.border = border
        for c_off, item in enumerate(catalog, start=3):
            info = mrow["cells"].get(item["form_code"]) or {}
            st = str(info.get("status") or "empty")
            cell = ws3.cell(row=r_idx, column=c_off, value=st.upper())
            cell.border = border
            cell.fill = _status_fill(st)
            cell.alignment = Alignment(horizontal="center")
    ws3.freeze_panes = "C2"
    _auto_fit_worksheet(ws3)
    wb.save(str(target))


def _write_project_pdf(target: Path, dataset: dict[str, Any]) -> None:
    font_reg, font_bold = _report_fonts()
    styles = getSampleStyleSheet()
    title_st = ParagraphStyle(
        "ProjTitle", parent=styles["Heading1"], fontName=font_bold, fontSize=14
    )
    h2_st = ParagraphStyle("ProjH2", parent=styles["Heading2"], fontName=font_bold, fontSize=10.5)
    body_st = ParagraphStyle("ProjBody", parent=styles["Normal"], fontName=font_reg, fontSize=8.5)
    cell_st = ParagraphStyle("ProjCell", parent=styles["Normal"], fontName=font_reg, fontSize=7.2)

    proj = dataset["project"]
    summary = dataset["summary"]
    doc = SimpleDocTemplate(
        str(target),
        pagesize=landscape(A4),
        leftMargin=24,
        rightMargin=24,
        topMargin=24,
        bottomMargin=24,
    )
    story: list[Any] = [
        Paragraph(f"HYDRO - Proje Master Hidrostatik Test Icmali: {proj['name']}", title_st),
        Spacer(1, 6),
        Paragraph(
            f"Kod: {proj.get('code') or '-'} | Musteri: {proj.get('client') or '-'} | "
            f"Yuklenici: {proj.get('contractor') or '-'} | Kesit: {summary['section_count']} | "
            f"Toplam Uzunluk: {summary['total_length_m']} m | Toplam Hacim: {summary['total_volume_m3']} m3 | "
            f"Form Tamamlama: %{summary['forms_completion_pct']}",
            body_st,
        ),
        Spacer(1, 8),
        Paragraph("Kesit Muhendislik Ozeti", h2_st),
        Spacer(1, 4),
    ]

    headers = [
        "Kesit",
        "Bas. KP",
        "Bit. KP",
        "L (m)",
        "OD/WT",
        "V (m3)",
        "Vpa/Vp",
        "Hava",
        "Marj (bar)",
        "Basinc",
        "Form",
        "Durum",
    ]
    tbl_data: list[list[Any]] = [[Paragraph(h, cell_st) for h in headers]]
    for sec in dataset["sections"]:
        od_wt = (
            f"{sec['outside_diameter_mm']}/{sec['wall_thickness_mm']}"
            if sec["outside_diameter_mm"]
            else "-"
        )
        row_strs = [
            sec["section_no"],
            sec["start_kp"] or "-",
            sec["end_kp"] or "-",
            str(sec["length_m"] if sec["length_m"] is not None else "-"),
            od_wt,
            str(sec["internal_volume_m3"] if sec["internal_volume_m3"] is not None else "-"),
            f"{sec['air_ratio']:.4f}" if sec["air_ratio"] is not None else "-",
            sec["air_status"],
            f"{sec['pressure_margin_bar']:+.3f}" if sec["pressure_margin_bar"] is not None else "-",
            sec["pressure_status"],
            f"{sec['forms_filled_required']}/{sec['forms_required_total']}",
            sec["overall_status"],
        ]
        tbl_data.append([Paragraph(txt, cell_st) for txt in row_strs])

    t = Table(tbl_data, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), font_bold),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ]
        )
    )
    story.append(t)
    if summary["continuity_issues"]:
        story.append(Spacer(1, 8))
        story.append(
            Paragraph(
                "KP Sureklilik Uyarilari: " + "; ".join(summary["continuity_issues"]),
                body_st,
            )
        )
    doc.build(story)


def export_project_dataset(
    settings: Settings,
    dataset: dict[str, Any],
    *,
    fmt: Literal["xlsx", "pdf", "csv", "json"],
) -> tuple[Path, str, str]:
    settings.exports_dir.mkdir(parents=True, exist_ok=True)
    slug = safe_filename(
        dataset["project"].get("code") or dataset["project"].get("name") or "proje"
    )
    out_path = settings.exports_dir / f"project_{slug}_{uuid.uuid4().hex[:8]}.{fmt}"
    download_name = f"HYDRO_{slug}_icmal.{fmt}"

    if fmt == "xlsx":
        _write_project_xlsx(out_path, dataset)
    elif fmt == "pdf":
        _write_project_pdf(out_path, dataset)
    elif fmt == "csv":
        fieldnames = [
            "section_no",
            "name",
            "start_kp",
            "end_kp",
            "length_m",
            "outside_diameter_mm",
            "wall_thickness_mm",
            "material_grade",
            "internal_volume_m3",
            "design_pressure_bar",
            "air_ratio",
            "air_status",
            "pressure_pt_bar",
            "pressure_pa_bar",
            "pressure_margin_bar",
            "pressure_status",
            "dew_point_c",
            "forms_filled_required",
            "forms_required_total",
            "overall_status",
        ]
        with out_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(fieldnames)
            for sec in dataset["sections"]:
                writer.writerow([_safe_cell(sec.get(col)) for col in fieldnames])
    elif fmt == "json":
        out_path.write_text(
            json.dumps(json_safe(dataset), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    else:
        raise validation_error(f"Desteklenmeyen disari aktarma bicimi: {fmt}", field="format")

    return out_path, EXPORT_CONTENT_TYPES[fmt], download_name


# ---------------------------------------------------------------------------
# Bulk KP Section Generator & Form Metadata Sync
# ---------------------------------------------------------------------------


def generate_project_sections(
    db: OrmSession,
    project: Project,
    workspace_hash: str,
    payload: Any,
) -> dict[str, Any]:
    """Split total pipeline length into contiguous KP sections with optional 12,500 m3 cap."""

    def _p(key: str, default: Any = None) -> Any:
        return (
            payload.get(key, default)
            if isinstance(payload, dict)
            else getattr(payload, key, default)
        )

    total_length_m = float(_p("total_length_m"))
    start_kp_m = float(_p("start_kp_m") or 0.0)
    max_len = min(float(_p("max_section_length_m") or 12_000.0), MAX_TEST_SECTION_LENGTH_M)
    respect_vol = bool(_p("respect_volume_limit", True))
    prefix = str(_p("section_prefix") or "K-").strip() or "K-"

    defaults = project_service.normalize_project_defaults(getattr(project, "defaults", None))
    od = as_float(_p("outside_diameter_mm")) or as_float(defaults.get("outside_diameter_mm"))
    wt = as_float(_p("wall_thickness_mm")) or as_float(defaults.get("wall_thickness_mm"))
    grade = str(_p("material_grade") or defaults.get("material_grade") or "").strip()
    smys = as_float(_p("smys_mpa")) or as_float(defaults.get("smys_mpa"))
    dp = as_float(_p("design_pressure_bar")) or as_float(defaults.get("design_pressure_bar"))
    loc_cls = str(
        _p("location_class")
        or defaults.get("location_class")
        or "Class 1 - min 1.25 x dizayn basinci"
    ).strip()
    base_elev = float(_p("base_elevation_m") if _p("base_elevation_m") is not None else 200.0)
    elev_amp = float(
        _p("elevation_amplitude_m") if _p("elevation_amplitude_m") is not None else 85.0
    )
    test_date = str(_p("test_date") or utcnow().strftime("%Y-%m-%d")).strip()
    init_forms = bool(_p("initialize_forms", True))

    if respect_vol and od and wt and od > 0 and wt > 0 and 2 * wt < od:
        ri_m = (od / 2.0 - wt) / 1000.0
        vol_per_m = math.pi * (ri_m**2)
        if vol_per_m > 0:
            max_vol_len = (MAX_TEST_SECTION_VOLUME_M3 - 50.0) / vol_per_m
            max_len = max(250.0, min(max_len, max_vol_len))

    count = max(1, math.ceil(total_length_m / max_len))
    if count > 50:
        raise validation_error(
            f"Tek seferde en fazla 50 kesit uretilebilir (hesaplanan: {count}). Kesit boyunu artirin.",
            field="max_section_length_m",
        )

    existing_count = project_service.section_count(db, project.id)
    created: list[HydroSession] = []
    cursor_m = start_kp_m
    remaining = total_length_m

    for idx in range(count):
        seg_len = round(min(max_len, remaining), 2)
        remaining = round(remaining - seg_len, 2)
        end_m = round(cursor_m + seg_len, 2)
        sec_num = existing_count + idx + 1
        sec_no = f"{prefix}{sec_num:02d}"
        s_kp = format_kp(cursor_m)
        e_kp = format_kp(end_m)

        # Build 5-point realistic terrain elevation profile for the slice
        pts: list[dict[str, float]] = []
        elev_vals: list[float] = []
        for step_i in range(5):
            frac = step_i / 4.0
            station = round(seg_len * frac, 1)
            elev = round(
                base_elev + math.sin((idx + frac) * 1.4) * elev_amp * 0.5 + elev_amp * 0.5 * frac, 1
            )
            pts.append({"station_m": station, "elevation_m": elev})
            elev_vals.append(elev)

        inputs = session_service.default_inputs()
        inputs["section_meta"] = {
            "section_no": sec_no,
            "description": project.name,
            "location": f"KP {s_kp} – {e_kp}",
            "start_kp": s_kp,
            "end_kp": e_kp,
            "test_date": test_date,
            "test_type": "Hidrostatik test",
            "notes": "",
        }
        inputs["geometry"] = {
            "outside_diameter_mm": od,
            "wall_thickness_mm": wt,
            "length_m": seg_len,
        }
        if od and wt:
            inputs["segments"] = [
                {
                    "outside_diameter_mm": od,
                    "wall_thickness_mm": wt,
                    "length_m": seg_len,
                    "nps_label": defaults.get("size_option") or "",
                    "schedule_label": defaults.get("schedule_option") or "",
                    "start_station_m": 0.0,
                }
            ]
        inputs["section_profile"] = {
            "highest_elevation_m": max(elev_vals),
            "lowest_elevation_m": min(elev_vals),
            "start_elevation_m": elev_vals[0],
            "end_elevation_m": elev_vals[-1],
            "design_pressure_bar": dp,
            "smys_mpa": smys,
        }
        inputs["profile_points"] = pts
        inputs["material_grade"] = grade
        inputs["location_class"] = loc_cls
        inputs["pump_location"] = str(defaults.get("pump_location") or "Baslangic noktasi")
        inputs["report"] = {
            "report_no": f"{project.code or 'PRJ'}-{sec_no}",
            "operator": project.contractor or "",
            "date": test_date,
            "section_id": sec_no,
        }

        sess = session_service.create_session(
            db,
            workspace_hash=workspace_hash,
            name=f"{sec_no} · KP {s_kp}–{e_kp} · {project.code or project.name}",
            project_id=project.id,
            inputs=inputs,
            commit=False,
        )
        if init_forms:
            _upsert_form_header(
                db,
                sess,
                project,
                workspace_hash=workspace_hash,
                form_code="test_data",
                overwrite=True,
                extra_payload={"header": _build_header_from_session(sess, project)},
            )
            _upsert_form_header(
                db,
                sess,
                project,
                workspace_hash=workspace_hash,
                form_code="calculation_sheet",
                overwrite=True,
                extra_payload={"header": _build_header_from_session(sess, project)},
            )
        created.append(sess)
        cursor_m = end_m

    audit.record(
        db,
        action="project.generate_sections",
        entity_type="project",
        entity_id=project.id,
        workspace_hash=workspace_hash,
        after={"created_count": len(created), "total_length_m": total_length_m},
    )
    db.commit()
    for sess in created:
        db.refresh(sess)

    return {
        "project_id": project.id,
        "created_count": len(created),
        "items": [session_service.session_brief(s) for s in created],
    }


def _build_header_from_session(session: HydroSession, project: Project) -> dict[str, Any]:
    inputs: dict[str, Any] = session.inputs if isinstance(session.inputs, dict) else {}
    raw_meta = inputs.get("section_meta")
    meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
    gm = _geometry_metrics(inputs)
    design_p = gm.get("design_pressure_bar")
    test_p = round(float(design_p) * 1.25, 2) if isinstance(design_p, (int, float)) else None
    return {
        "project_name": project.name,
        "project_code": project.code or "",
        "client_name": project.client or "",
        "contractor_name": project.contractor or "",
        "supervisor_name": project.supervisor or "",
        "section_no": str(meta.get("section_no") or session.name.split("·", 1)[0].strip()),
        "start_kp": str(meta.get("start_kp") or ""),
        "end_kp": str(meta.get("end_kp") or ""),
        "outside_diameter_mm": gm.get("od_mm"),
        "wall_thickness_mm": gm.get("wt_mm"),
        "length_m": gm.get("length_m"),
        "section_volume_m3": gm.get("volume_m3"),
        "pipe_grade": str(inputs.get("material_grade") or ""),
        "design_pressure_bar": design_p,
        "test_pressure_bar": test_p,
        "form_date": str(meta.get("test_date") or ""),
    }


def _upsert_form_header(
    db: OrmSession,
    session: HydroSession,
    project: Project,
    *,
    workspace_hash: str,
    form_code: str,
    overwrite: bool,
    extra_payload: dict[str, Any] | None = None,
) -> bool:
    spec = dossier_service.FORM_SPEC_BY_CODE.get(form_code)
    if spec is None:
        return False
    row = db.execute(
        select(SectionForm).where(
            SectionForm.session_id == session.id, SectionForm.form_code == form_code
        )
    ).scalar_one_or_none()
    now = utcnow()
    if row is None:
        row = SectionForm(
            id=new_uuid(),
            workspace_id_hash=workspace_hash,
            project_id=project.id,
            session_id=session.id,
            form_code=spec.code,
            botas_code=spec.botas_code,
            form_title=spec.title,
            required=spec.required,
            status="empty",
            revision=0,
        )
        db.add(row)
        db.flush()

    ext: dict[str, Any] = (
        copy.deepcopy(row.extracted_data) if isinstance(row.extracted_data, dict) else {}
    )
    raw_existing_hdr = ext.get("header")
    existing_hdr: dict[str, Any] = raw_existing_hdr if isinstance(raw_existing_hdr, dict) else {}
    raw_extra_hdr = extra_payload.get("header") if extra_payload else None
    target_hdr: dict[str, Any] = (
        raw_extra_hdr
        if isinstance(raw_extra_hdr, dict)
        else _build_header_from_session(session, project)
    )

    changed = False
    new_hdr = dict(existing_hdr)
    for key, val in target_hdr.items():
        if val is None or val == "":
            continue
        cur = new_hdr.get(key)
        if overwrite or cur is None or cur == "":
            if cur != val:
                new_hdr[key] = val
                changed = True

    if not changed and row.status != "empty":
        return False

    ext["header"] = new_hdr
    if not row.form_date and new_hdr.get("form_date"):
        row.form_date = str(new_hdr["form_date"])
    if row.status == "empty":
        row.status = "filled"
        row.filled_at = now
    row.revision = int(row.revision or 0) + 1
    row.updated_at = now
    row.extracted_data = json_safe(ext)
    flag_modified(row, "extracted_data")
    return True


def sync_project_forms(
    db: OrmSession,
    project: Project,
    workspace_hash: str,
    *,
    overwrite_existing: bool = False,
    form_codes: list[str] | None = None,
) -> dict[str, Any]:
    """Propagate project metadata & section geometry into section forms without overwriting user data."""

    sessions = (
        db.execute(
            select(HydroSession).where(
                HydroSession.project_id == project.id,
                HydroSession.workspace_id_hash == workspace_hash,
                HydroSession.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )

    valid_codes = set(dossier_service.FORM_SPEC_BY_CODE)
    requested_codes: list[str] | None = None
    if form_codes:
        requested_codes = [c for c in form_codes if c in valid_codes]
        if not requested_codes:
            raise validation_error("Gecerli bir BOTAS form kodu secilmedi.", field="form_codes")

    updated_forms = 0
    touched_sessions = 0

    for sess in sessions:
        forms = dossier_service.ensure_section_form_slots(db, sess, commit=False)
        existing_filled = [f.form_code for f in forms if f.status != "empty"]
        targets = requested_codes or sorted({"test_data", *existing_filled})
        sec_changed = False
        for code in targets:
            if _upsert_form_header(
                db,
                sess,
                project,
                workspace_hash=workspace_hash,
                form_code=code,
                overwrite=overwrite_existing,
            ):
                updated_forms += 1
                sec_changed = True
        if sec_changed:
            touched_sessions += 1
            dossier_service.ensure_section_form_slots(db, sess, commit=False)

    audit.record(
        db,
        action="project.sync_forms",
        entity_type="project",
        entity_id=project.id,
        workspace_hash=workspace_hash,
        after={
            "touched_sessions": touched_sessions,
            "updated_forms": updated_forms,
            "overwrite_existing": overwrite_existing,
        },
    )
    db.commit()
    return {
        "project_id": project.id,
        "section_count": len(sessions),
        "touched_sessions": touched_sessions,
        "updated_forms": updated_forms,
    }


# ---------------------------------------------------------------------------
# Sample Project Generator & Project Clone
# ---------------------------------------------------------------------------


def _store_test_result(
    db: OrmSession,
    session_id: str,
    test_type: str,
    req_payload: dict[str, Any],
    res_payload: dict[str, Any],
    decision: dict[str, Any],
) -> None:
    row = TestResult(
        id=new_uuid(),
        session_id=session_id,
        test_type=test_type,
        inputs=json_safe(req_payload),
        result=json_safe(res_payload),
        decision_status=str(decision.get("status") or "BEKLIYOR"),
        decision_title=str(decision.get("title") or ""),
        decision_summary=str(decision.get("summary") or ""),
        decision_rule=str(decision.get("rule") or ""),
        decision=json_safe(decision),
        engine_version=session_service.ENGINE_VERSION,
        computed_at=utcnow(),
    )
    db.add(row)


def generate_sample_project(
    db: OrmSession,
    workspace_hash: str,
    *,
    scenario: Literal["passing", "mixed", "failing"] = "mixed",
    section_count: int = 3,
    name: str | None = None,
    code: str | None = None,
    include_time_series: bool = True,
    include_forms: bool = True,
) -> dict[str, Any]:
    """Create a complete physics-accurate sample pipeline project in DB for demos/testing."""

    od = 1016.0
    wt = 12.7
    grade = "API 5L PSL2 X65 / L450 - SMYS 450 MPa"
    smys = 450.0
    design_p = 75.0
    loc_class = "Class 1 - min 1.25 x dizayn basinci"
    pump_loc = "Baslangic noktasi"
    seg_len = 10_000.0
    test_date = utcnow().strftime("%Y-%m-%d")

    proj_name = (name or "").strip() or f"Örnek BOTAŞ Hattı ({scenario.upper()})"
    proj_code = (code or "").strip() or f"SMP-{uuid.uuid4().hex[:5].upper()}"

    project = project_service.create_project(
        db,
        workspace_hash,
        {
            "name": proj_name,
            "code": proj_code,
            "client": "BOTAŞ",
            "contractor": "Örnek Boru İnşaat A.Ş.",
            "supervisor": "Örnek Denetim Müşavirlik",
            "pipeline_length_m": round(seg_len * section_count, 2),
            "status": "completed" if scenario == "passing" else "active",
            "defaults": {
                "outside_diameter_mm": od,
                "wall_thickness_mm": wt,
                "material_grade": grade,
                "smys_mpa": smys,
                "design_pressure_bar": design_p,
                "location_class": loc_class,
                "pump_location": pump_loc,
                "k_factor": 1.02,
                "steel_alpha_micro_per_c": 12.0,
            },
            "description": "Otomatik üretilmiş örnek hidrostatik test proje verisi.",
        },
        commit=False,
    )

    # Reference geometry & shared domain rules
    temp_c = 15.0
    pipe_section = PipeSection(
        outside_diameter_mm=od,
        wall_thickness_mm=wt,
        length_m=seg_len,
    )
    pipe = PipeGeometry((pipe_section,))
    vt_m3 = round(pipe.internal_volume_m3, 3)

    created_sessions: list[HydroSession] = []
    loc_rule = get_location_class_rule(loc_class)
    base_ts = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(
        hours=24
    )

    for idx in range(section_count):
        if scenario == "passing":
            sec_mode = "pass"
        elif scenario == "failing":
            sec_mode = "fail" if idx == section_count - 1 else "pass"
        else:  # mixed
            if idx == 0:
                sec_mode = "pass"
            elif idx == 1:
                sec_mode = "warn"
            else:
                sec_mode = "fail"

        sec_no = f"K-{idx + 1:02d}"
        s_kp = format_kp(idx * seg_len)
        e_kp = format_kp((idx + 1) * seg_len)
        low_e = 185.0 + idx * 5.0
        high_e = 250.0 + idx * 5.0
        start_e = low_e + 10.0
        end_e = high_e - 8.0

        # Compute feasible pressure window first and pick midpoint test pressure
        prof_probe = evaluate_section_pressure_profile(
            SectionPressureProfileInputs(
                pipe=pipe,
                design_pressure_bar=design_p,
                smys_mpa=smys,
                location_class=loc_rule,
                highest_elevation_m=high_e,
                lowest_elevation_m=low_e,
                start_elevation_m=start_e,
                end_elevation_m=end_e,
                selected_pump_location=pump_loc,
                monitored_pressure_bar=100.0,
            )
        )
        p_win = prof_probe.selected_window
        if (
            p_win.minimum_required_pressure_bar is not None
            and p_win.maximum_allowable_pressure_bar is not None
        ):
            test_p_bar = round(
                (p_win.minimum_required_pressure_bar + p_win.maximum_allowable_pressure_bar) / 2.0,
                2,
            )
        else:
            test_p_bar = 102.0

        a_val = float(coefficient_a(temp_c, test_p_bar, backend=None)["a_micro_per_bar"])
        b_val = float(
            coefficient_b(
                source="institutional",
                temperature_c=temp_c,
                pressure_bar=test_p_bar,
                steel_alpha_micro_per_c=12.0,
                steel_model="volumetric",
            )["b_micro_per_c"]
        )

        # Real air evaluation
        air_in_base = AirContentInputs(
            pipe=pipe,
            a_micro_per_bar=a_val,
            pressure_rise_bar=1.0,
            k_factor=1.02,
            actual_added_water_m3=1.0,
        )
        air_probe = evaluate_air_content_test(air_in_base)
        vpa_factor = 0.96 if sec_mode in {"pass", "warn"} else 1.12
        vpa_val = round(air_probe.theoretical_added_water_m3 * vpa_factor, 4)
        air_res = evaluate_air_content_test(
            AirContentInputs(
                pipe=pipe,
                a_micro_per_bar=a_val,
                pressure_rise_bar=1.0,
                k_factor=1.02,
                actual_added_water_m3=vpa_val,
            )
        )

        # Real pressure variation evaluation
        t_init = 15.0
        t_final = 14.8
        delta_t = round(t_init - t_final, 2)
        pres_probe = evaluate_pressure_variation_test(
            PressureVariationInputs(
                pipe=pipe,
                a_micro_per_bar=a_val,
                b_micro_per_c=b_val,
                delta_t_c=delta_t,
                actual_pressure_change_bar=0.0,
            )
        )
        extra_margin = 0.08 if sec_mode in {"pass", "warn"} else 0.48
        pa_val = round(pres_probe.theoretical_pressure_change_bar + extra_margin, 3)
        pres_res = evaluate_pressure_variation_test(
            PressureVariationInputs(
                pipe=pipe,
                a_micro_per_bar=a_val,
                b_micro_per_c=b_val,
                delta_t_c=delta_t,
                actual_pressure_change_bar=pa_val,
            )
        )

        # Real pressure profile evaluation at exact chosen test_p_bar
        prof_res = evaluate_section_pressure_profile(
            SectionPressureProfileInputs(
                pipe=pipe,
                design_pressure_bar=design_p,
                smys_mpa=smys,
                location_class=loc_rule,
                highest_elevation_m=high_e,
                lowest_elevation_m=low_e,
                start_elevation_m=start_e,
                end_elevation_m=end_e,
                selected_pump_location=pump_loc,
                monitored_pressure_bar=test_p_bar,
            )
        )
        pig_limit = PIG_SPEED_LIMITS[0]
        pig_res = evaluate_pig_speed(seg_len, 100.0, pig_limit)

        pre_dew_val = -21.5 if sec_mode in {"pass", "warn"} else -16.0
        dew_val = -24.0 if sec_mode == "pass" else (-21.0 if sec_mode == "warn" else -15.5)

        inputs = session_service.default_inputs()
        inputs["section_meta"] = {
            "section_no": sec_no,
            "description": proj_name,
            "location": f"KP {s_kp} – {e_kp}",
            "start_kp": s_kp,
            "end_kp": e_kp,
            "test_date": test_date,
            "test_type": "Hidrostatik test",
            "notes": f"Örnek senaryo ({sec_mode})",
        }
        inputs["geometry"] = {
            "outside_diameter_mm": od,
            "wall_thickness_mm": wt,
            "length_m": seg_len,
        }
        inputs["geometry_catalog"] = {
            "size_option": "NPS 40 (DN 1000) - OD 1016.00 mm",
            "schedule_option": "12.70 mm",
        }
        inputs["segments"] = [
            {
                "outside_diameter_mm": od,
                "wall_thickness_mm": wt,
                "length_m": seg_len,
                "nps_label": "NPS 40 (DN 1000) - OD 1016.00 mm",
                "schedule_label": "12.70 mm",
                "start_station_m": 0.0,
            }
        ]
        inputs["section_profile"] = {
            "highest_elevation_m": high_e,
            "lowest_elevation_m": low_e,
            "start_elevation_m": start_e,
            "end_elevation_m": end_e,
            "design_pressure_bar": design_p,
            "smys_mpa": smys,
        }
        inputs["profile_points"] = [
            {"station_m": 0.0, "elevation_m": start_e},
            {"station_m": seg_len * 0.28, "elevation_m": low_e},
            {"station_m": seg_len * 0.65, "elevation_m": high_e},
            {"station_m": seg_len, "elevation_m": end_e},
        ]
        inputs["material_grade"] = grade
        inputs["location_class"] = loc_class
        inputs["pump_location"] = pump_loc
        inputs["air"] = {
            "temperature_c": temp_c,
            "pressure_bar": test_p_bar,
            "a_micro_per_bar": round(a_val, 6),
            "pressure_rise_bar": 1.0,
            "k_factor": 1.02,
            "actual_added_water_m3": vpa_val,
        }
        inputs["pressure"] = {
            "temperature_c": temp_c,
            "pressure_bar": test_p_bar,
            "a_micro_per_bar": round(a_val, 6),
            "b_micro_per_c": round(b_val, 4),
            "delta_t_c": delta_t,
            "actual_pressure_change_bar": pa_val,
            "t_initial_c": t_init,
            "t_final_c": t_final,
        }
        inputs["field"] = {
            "ambient_temperature_c": 14.0,
            "monitored_pressure_bar": test_p_bar,
            "pig_distance_m": seg_len,
            "pig_travel_time_min": 100.0,
            "pig_speed_m_per_s": round(pig_res.speed_m_per_s, 3),
            "pig_speed_km_per_h": round(pig_res.speed_km_per_h, 3),
        }
        inputs["checks"] = {k: True for k in inputs["checks"]}
        inputs["report"] = {
            "report_no": f"{proj_code}-{sec_no}",
            "operator": "Sistem Örnek Üretici",
            "date": test_date,
            "section_id": sec_no,
        }

        sess = session_service.create_session(
            db,
            workspace_hash=workspace_hash,
            name=f"{sec_no} · KP {s_kp}–{e_kp} · {proj_code}",
            project_id=project.id,
            inputs=inputs,
            commit=False,
        )
        sess.status = "completed" if sec_mode == "pass" else "active"

        # Persist formal test results
        geom_req = {
            "sections": [{"outside_diameter_mm": od, "wall_thickness_mm": wt, "length_m": seg_len}]
        }
        _store_test_result(
            db,
            sess.id,
            "air",
            {"geometry": geom_req, "a_micro_per_bar": a_val, "actual_added_water_m3": vpa_val},
            {
                "theoretical_added_water_m3": air_res.theoretical_added_water_m3,
                "acceptance_limit_m3": air_res.acceptance_limit_m3,
                "actual_added_water_m3": air_res.actual_added_water_m3,
                "ratio": air_res.ratio,
                "passed": air_res.passed,
                "geometry": geometry_summary(pipe),
            },
            decisions.air_decision(air_res),
        )
        _store_test_result(
            db,
            sess.id,
            "pressure",
            {
                "geometry": geom_req,
                "a_micro_per_bar": a_val,
                "b_micro_per_c": b_val,
                "delta_t_c": delta_t,
                "actual_pressure_change_bar": pa_val,
            },
            {
                "theoretical_pressure_change_bar": pres_res.theoretical_pressure_change_bar,
                "allowable_upper_pressure_change_bar": pres_res.allowable_upper_pressure_change_bar,
                "actual_pressure_change_bar": pres_res.actual_pressure_change_bar,
                "margin_bar": pres_res.margin_bar,
                "passed": pres_res.passed,
            },
            decisions.pressure_decision(pres_res, negative_b=b_val < 0),
        )
        _store_test_result(
            db,
            sess.id,
            "profile",
            {
                "geometry": geom_req,
                "design_pressure_bar": design_p,
                "smys_mpa": smys,
                "location_class": loc_class,
                "highest_elevation_m": high_e,
                "lowest_elevation_m": low_e,
                "start_elevation_m": start_e,
                "end_elevation_m": end_e,
                "pump_location": pump_loc,
                "monitored_pressure_bar": test_p_bar,
            },
            {
                "location_class": dataclass_dict(prof_res.location_class),
                "selected_window": dataclass_dict(prof_res.selected_window),
                "feasible": prof_res.feasible,
                "total_length_m": prof_res.total_length_m,
                "total_internal_volume_m3": prof_res.total_internal_volume_m3,
            },
            decisions.profile_decision(prof_res),
        )

        # Hourly time-series (25 pts -> 24 hours across midnight)
        mon_rows: list[dict[str, Any]] = []
        for h in range(25):
            ts = base_ts + timedelta(hours=h)
            t_pipe = round(t_init - (t_init - t_final) * (h / 24.0), 2)
            p_cur = round(test_p_bar + (pa_val * (h / 24.0)), 3)
            mon_rows.append(
                {
                    "time_str": f"{(8 + h) % 24:02d}:00",
                    "pressure_bar": p_cur,
                    "ambient_temp_c": 14.0,
                    "soil_1_c": round(t_pipe - 0.3, 2),
                    "pipe_1_c": t_pipe,
                    "avg_soil_c": round(t_pipe - 0.3, 2),
                    "avg_pipe_c": t_pipe,
                }
            )
            if include_time_series:
                db.add(
                    TimeSeriesRecord(
                        id=new_uuid(),
                        session_id=sess.id,
                        timestamp=ts,
                        pressure_bar=p_cur,
                        temperature_c=t_pipe,
                        volume_m3=vt_m3,
                        notes="Otomatik örnek kayıt",
                        source="sample",
                    )
                )

        if include_forms:
            hdr = _build_header_from_session(sess, project)
            hdr["test_pressure_bar"] = test_p_bar
            if sec_mode == "warn":
                filling_rows = [
                    {
                        "time_str": "08:00",
                        "delta_volume_m3": round(vt_m3 * 0.5, 3),
                        "total_volume_m3": round(vt_m3 * 0.5, 3),
                        "water_inlet_temp_c": 14.5,
                        "water_pressure_bar": 8.0,
                    },
                    {
                        "time_str": "12:00",
                        "delta_volume_m3": round(vt_m3 * 0.5, 3),
                        "total_volume_m3": vt_m3,
                        "water_inlet_temp_c": 15.0,
                        "water_pressure_bar": 12.0,
                    },
                ]
            else:
                filling_rows = [
                    {
                        "time_str": f"{8 + step_idx:02d}:00",
                        "delta_volume_m3": round(vt_m3 / 5.0, 3),
                        "total_volume_m3": round(vt_m3 * (step_idx + 1) / 5.0, 3),
                        "water_inlet_temp_c": round(14.5 + step_idx * 0.1, 2),
                        "water_pressure_bar": round(6.0 + step_idx * 1.5, 2),
                    }
                    for step_idx in range(5)
                ]

            strength_rows: list[dict[str, Any]] = []
            cum_water = 0.0
            for q_idx in range(9):
                total_min = 14 * 60 + q_idx * 15
                hh, mm = divmod(total_min, 60)
                step_w = 0.1 if q_idx < 8 else 0.0
                p_prev = round(90.0 + (test_p_bar - 90.0) * min(1.0, q_idx / 4.0), 2)
                p_next = round(90.0 + (test_p_bar - 90.0) * min(1.0, (q_idx + 1) / 4.0), 2)
                if q_idx >= 4:
                    p_prev = test_p_bar
                    p_next = test_p_bar
                cum_water = round(cum_water + step_w, 3)
                strength_rows.append(
                    {
                        "time_str": f"{hh:02d}:{mm:02d}",
                        "p_initial_bar": p_prev,
                        "p_final_bar": p_next,
                        "step_water_m3": step_w,
                        "total_water_m3": cum_water,
                        "water_temp_c": temp_c,
                    }
                )

            form_payloads: dict[str, dict[str, Any]] = {
                "test_data": {"header": hdr, "signatures": {"contractor": True, "botas": True}},
                "cleaning": {
                    "header": hdr,
                    "pig_runs": [
                        {
                            "pig_type": "Köpekbalığı / Temizlik Pigi",
                            "launch_time": "08:00",
                            "receive_time": "09:40",
                            "duration_min": 100.0,
                        }
                    ],
                },
                "filling": {
                    "header": hdr,
                    "rows": filling_rows,
                },
                "leak_stabilization": {"header": hdr, "rows": mon_rows},
                "strength": {
                    "header": hdr,
                    "rows": strength_rows,
                },
                "air_acceptance": {
                    "header": hdr,
                    "air_acceptance": {
                        "vp_m3": round(air_res.theoretical_added_water_m3, 5),
                        "vpa_m3": vpa_val,
                        "pressure_rise_bar": 1.0,
                        "k_factor": 1.02,
                        "excess_pct": round((air_res.ratio - 1.0) * 100.0, 2),
                    },
                },
                "pressure_test": {"header": hdr, "rows": mon_rows},
                "pressure_acceptance": {
                    "header": hdr,
                    "pressure_acceptance": {
                        "pt_bar": round(pres_res.theoretical_pressure_change_bar, 3),
                        "pa_bar": pa_val,
                        "delta_t_c": delta_t,
                        "t_initial_c": t_init,
                        "t_final_c": t_final,
                    },
                },
                "dewatering": {
                    "header": hdr,
                    "pig_runs": [
                        {
                            "pig_type": "Boşaltma Pigi",
                            "launch_time": "09:00",
                            "receive_time": "10:40",
                            "duration_min": 100.0,
                        }
                    ],
                },
                "pre_drying": {
                    "header": hdr,
                    "drying": {"target_dew_point_c": -20.0, "measured_dew_point_c": pre_dew_val},
                },
                "final_drying": {
                    "header": hdr,
                    "drying": {"target_dew_point_c": -20.0, "measured_dew_point_c": dew_val},
                },
            }
            for f_code, f_ext in form_payloads.items():
                spec = dossier_service.FORM_SPEC_BY_CODE[f_code]
                f_row = db.execute(
                    select(SectionForm).where(
                        SectionForm.session_id == sess.id, SectionForm.form_code == f_code
                    )
                ).scalar_one_or_none()
                if f_row is None:
                    f_row = SectionForm(
                        id=new_uuid(),
                        workspace_id_hash=workspace_hash,
                        project_id=project.id,
                        session_id=sess.id,
                        form_code=spec.code,
                        botas_code=spec.botas_code,
                        form_title=spec.title,
                        required=spec.required,
                    )
                    db.add(f_row)
                    db.flush()
                f_row.form_date = test_date
                f_row.source_filename = "sample_generator"
                f_row.pages = [1]
                f_row.revision = 1
                f_row.filled_at = utcnow()
                f_row.extracted_data = json_safe(
                    dossier_service.reconcile_form_extracted_data(f_code, f_ext)
                )
                f_row.status = "filled"
                flag_modified(f_row, "extracted_data")

            db.flush()
            dossier_service.recompute_session_from_inputs_and_forms(db, sess)
            dossier_service.ensure_section_form_slots(db, sess, commit=False)

        sess.result_summary = session_service.session_summary(db, sess)
        created_sessions.append(sess)

    audit.record(
        db,
        action="project.generate_sample",
        entity_type="project",
        entity_id=project.id,
        workspace_hash=workspace_hash,
        after={"scenario": scenario, "section_count": len(created_sessions)},
    )
    db.commit()
    db.refresh(project)

    return {
        "project": project_service.serialize_project(project, len(created_sessions)),
        "sections": [session_service.session_brief(s) for s in created_sessions],
    }


def clone_project(
    db: OrmSession,
    project: Project,
    workspace_hash: str,
    *,
    name: str | None = None,
    code: str | None = None,
    mode: Literal["template", "full"] = "template",
) -> dict[str, Any]:
    """Clone an existing project as an empty KPI/geometry template or as a full copy."""

    new_name = (name or "").strip() or f"{project.name} (Kopya)"
    new_code = (code or "").strip() or (f"{project.code}-COPY" if project.code else "")

    cloned = project_service.create_project(
        db,
        workspace_hash,
        {
            "name": new_name,
            "code": new_code,
            "client": project.client,
            "contractor": getattr(project, "contractor", None),
            "supervisor": getattr(project, "supervisor", None),
            "pipeline_length_m": getattr(project, "pipeline_length_m", None),
            "status": "active",
            "defaults": getattr(project, "defaults", None) or {},
            "description": project.description,
        },
        commit=False,
    )

    sessions = (
        db.execute(
            select(HydroSession).where(
                HydroSession.project_id == project.id,
                HydroSession.workspace_id_hash == workspace_hash,
                HydroSession.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )

    new_sessions: list[HydroSession] = []
    for sess in sessions:
        src_inputs = copy.deepcopy(sess.inputs if isinstance(sess.inputs, dict) else {})
        if mode == "template":
            dst_inputs = session_service.default_inputs()
            dst_inputs["section_meta"] = copy.deepcopy(src_inputs.get("section_meta") or {})
            dst_inputs["geometry"] = copy.deepcopy(src_inputs.get("geometry") or {})
            dst_inputs["geometry_catalog"] = copy.deepcopy(src_inputs.get("geometry_catalog") or {})
            dst_inputs["segments"] = copy.deepcopy(src_inputs.get("segments") or [])
            dst_inputs["section_profile"] = copy.deepcopy(src_inputs.get("section_profile") or {})
            dst_inputs["profile_points"] = copy.deepcopy(src_inputs.get("profile_points") or [])
            dst_inputs["landmarks"] = copy.deepcopy(src_inputs.get("landmarks") or [])
            dst_inputs["equipment"] = copy.deepcopy(src_inputs.get("equipment") or [])
            dst_inputs["material_grade"] = src_inputs.get("material_grade") or ""
            dst_inputs["location_class"] = (
                src_inputs.get("location_class") or dst_inputs["location_class"]
            )
            dst_inputs["pump_location"] = src_inputs.get("pump_location") or ""
            cloned_sess = session_service.create_session(
                db,
                workspace_hash=workspace_hash,
                name=sess.name,
                project_id=cloned.id,
                inputs=dst_inputs,
                commit=False,
            )
        else:
            cloned_sess = HydroSession(
                id=new_uuid(),
                workspace_id_hash=workspace_hash,
                project_id=cloned.id,
                name=sess.name,
                status=sess.status,
                inputs=copy.deepcopy(src_inputs),
                wizard_state=copy.deepcopy(sess.wizard_state),
                result_summary=copy.deepcopy(sess.result_summary or {}),
                revision=1,
                notes=sess.notes or "",
            )
            db.add(cloned_sess)
            db.flush()

            src_forms = (
                db.execute(select(SectionForm).where(SectionForm.session_id == sess.id))
                .scalars()
                .all()
            )
            for form in src_forms:
                db.add(
                    SectionForm(
                        id=new_uuid(),
                        workspace_id_hash=workspace_hash,
                        project_id=cloned.id,
                        session_id=cloned_sess.id,
                        form_code=form.form_code,
                        botas_code=form.botas_code,
                        form_title=form.form_title,
                        required=form.required,
                        status=form.status,
                        source_filename=form.source_filename,
                        pages=list(form.pages or []),
                        form_date=form.form_date,
                        extracted_data=copy.deepcopy(form.extracted_data or {}),
                        warnings=list(form.warnings or []),
                        revision=form.revision,
                        filled_at=form.filled_at,
                    )
                )

            src_results = (
                db.execute(select(TestResult).where(TestResult.session_id == sess.id))
                .scalars()
                .all()
            )
            for res in src_results:
                db.add(
                    TestResult(
                        id=new_uuid(),
                        session_id=cloned_sess.id,
                        test_type=res.test_type,
                        inputs=copy.deepcopy(res.inputs or {}),
                        result=copy.deepcopy(res.result or {}),
                        decision_status=res.decision_status,
                        decision_title=res.decision_title,
                        decision_summary=res.decision_summary,
                        decision_rule=res.decision_rule,
                        decision=copy.deepcopy(res.decision or {}),
                        engine_version=res.engine_version,
                        computed_at=res.computed_at,
                    )
                )

            src_ts = (
                db.execute(select(TimeSeriesRecord).where(TimeSeriesRecord.session_id == sess.id))
                .scalars()
                .all()
            )
            for ts in src_ts:
                db.add(
                    TimeSeriesRecord(
                        id=new_uuid(),
                        session_id=cloned_sess.id,
                        timestamp=ts.timestamp,
                        pressure_bar=ts.pressure_bar,
                        temperature_c=ts.temperature_c,
                        volume_m3=ts.volume_m3,
                        notes=ts.notes,
                        source=ts.source,
                    )
                )

        new_sessions.append(cloned_sess)

    audit.record(
        db,
        action="project.clone",
        entity_type="project",
        entity_id=cloned.id,
        workspace_hash=workspace_hash,
        after={"source_project_id": project.id, "mode": mode, "sections": len(new_sessions)},
    )
    db.commit()
    db.refresh(cloned)
    return {
        "project": project_service.serialize_project(cloned, len(new_sessions)),
        "section_count": len(new_sessions),
    }


__all__ = [
    "build_project_dataset",
    "clone_project",
    "export_project_dataset",
    "format_kp",
    "generate_project_sections",
    "generate_sample_project",
    "parse_kp_meters",
    "sync_project_forms",
]

"""Structured BOTAŞ form extraction, row reconciliation, and per-form specification findings."""

from __future__ import annotations

import copy
import json
import re
import statistics
from datetime import date, datetime, timedelta, timezone
from typing import Any, Sequence

from hidrostatik_test.domain import (
    MAX_TEST_SECTION_LENGTH_M,
    MAX_TEST_SECTION_VOLUME_M3,
    PRESSURE_VARIATION_ACCEPTANCE_BAR,
    ValidationError,
    evaluate_time_series,
)
from hidrostatik_test.domain import TimeSeriesRecord as DomainTimeSeriesRecord
from hidrostatik_test.domain.operations import get_pig_speed_limit
from hidrostatik_test.domain.post_test_operations import (
    DepressurizationInputs,
    DischargeInputs,
    evaluate_depressurization,
    evaluate_discharge,
)
from hidrostatik_test.services.report_ocr import is_dot_decimal_text, parse_number

from ..core.timeutil import ensure_utc, iso_z

MAX_TABLE_ROWS = 300
DEFAULT_TARGET_DEW_POINT_C = -20.0

_TR_FOLD = str.maketrans(
    {
        "ç": "c",
        "Ç": "c",
        "ğ": "g",
        "Ğ": "g",
        "ı": "i",
        "I": "i",
        "İ": "i",
        "ö": "o",
        "Ö": "o",
        "ş": "s",
        "Ş": "s",
        "ü": "u",
        "Ü": "u",
    }
)


def _fold(text: str) -> str:
    return text.translate(_TR_FOLD).lower()


def _finite(val: Any) -> float | None:
    if val is None or isinstance(val, bool):
        return None
    try:
        num = float(val)
    except (TypeError, ValueError):
        return None
    import math

    return num if math.isfinite(num) else None


def _optional_bool(val: Any) -> bool | None:
    return val if isinstance(val, bool) else None


def build_effective_dewatering_payloads(
    form_date: str,
    extracted_data: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Extract active Spec 16/17 payloads from a `dewatering` form, filling missing 17.6 gaps from date & pig runs."""
    data = extracted_data if isinstance(extracted_data, dict) else {}

    dep_payload: dict[str, Any] | None = None
    raw_dep = data.get("depressurization")
    if isinstance(raw_dep, dict):
        cand_dep = {
            "test_passed": _optional_bool(raw_dep.get("test_passed")),
            "release_valve_diameter_in": _finite(raw_dep.get("release_valve_diameter_in")),
            "pipe_equipment_checked": _optional_bool(raw_dep.get("pipe_equipment_checked")),
            "environmental_impact_checked": _optional_bool(
                raw_dep.get("environmental_impact_checked")
            ),
        }
        if any(v is not None for v in cand_dep.values()):
            dep_payload = cand_dep

    dis_payload: dict[str, Any] | None = None
    raw_dis = data.get("discharge")
    if isinstance(raw_dis, dict):
        has_dis_input = (
            any(
                raw_dis.get(k) is not None
                for k in (
                    "used_discharge_pig",
                    "hydraulic_load_measures_taken",
                    "approvals_obtained",
                    "treatment_done",
                    "sample_analysis_done",
                    "erosion_prevented",
                    "duration_min",
                )
            )
            or any(
                str(raw_dis.get(k) or "").strip() != ""
                for k in (
                    "destination",
                    "report_date",
                    "report_time",
                    "pig_name",
                    "discharge_location",
                )
            )
            or bool(raw_dis.get("treatment_requested"))
            or bool(raw_dis.get("sample_analysis_requested"))
        )
        if has_dis_input:
            runs = [r for r in (data.get("pig_runs") or []) if isinstance(r, dict)]
            first_run: dict[str, Any] = runs[0] if runs else {}
            raw_ev = data.get("pig_events")
            pig_ev: dict[str, Any] = raw_ev if isinstance(raw_ev, dict) else {}
            last_dur = next(
                (
                    d
                    for d in (_finite(r.get("duration_min")) for r in reversed(runs))
                    if d is not None and d > 0
                ),
                None,
            )
            used_pig = _optional_bool(raw_dis.get("used_discharge_pig"))
            if used_pig is None and (runs or bool(pig_ev.get("has_events"))):
                used_pig = True

            dest = str(raw_dis.get("destination") or "").strip() or None
            rep_date = (
                str(raw_dis.get("report_date") or "").strip()
                or str(form_date or data.get("form_date") or "").strip()
            )
            rep_time = (
                str(raw_dis.get("report_time") or "").strip()
                or str(first_run.get("launch_time") or "").strip()
                or str(pig_ev.get("first_time") or "").strip()
            )
            pig_name = (
                str(raw_dis.get("pig_name") or "").strip()
                or str(first_run.get("pig_type") or "").strip()
            )
            loc = str(raw_dis.get("discharge_location") or "").strip()
            dur_min = (
                _finite(raw_dis.get("duration_min"))
                or last_dur
                or _finite(pig_ev.get("travel_time_min"))
            )
            dis_payload = {
                "destination": dest,
                "used_discharge_pig": used_pig,
                "hydraulic_load_measures_taken": _optional_bool(
                    raw_dis.get("hydraulic_load_measures_taken")
                ),
                "approvals_obtained": _optional_bool(raw_dis.get("approvals_obtained")),
                "treatment_requested": bool(raw_dis.get("treatment_requested", False)),
                "treatment_done": _optional_bool(raw_dis.get("treatment_done")),
                "sample_analysis_requested": bool(raw_dis.get("sample_analysis_requested", False)),
                "sample_analysis_done": _optional_bool(raw_dis.get("sample_analysis_done")),
                "erosion_prevented": _optional_bool(raw_dis.get("erosion_prevented")),
                "report_date": rep_date,
                "report_time": rep_time,
                "pig_name": pig_name,
                "discharge_location": loc,
                "duration_min": dur_min,
            }

    return dep_payload, dis_payload


def evaluate_dewatering_operations(
    form_date: str,
    extracted_data: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate active Spec 16/17 blocks on a `dewatering` form via domain rules."""
    dep_payload, dis_payload = build_effective_dewatering_payloads(form_date, extracted_data)

    dep_eval: dict[str, Any] | None = None
    if dep_payload is not None:
        try:
            dep_res = evaluate_depressurization(DepressurizationInputs(**dep_payload))
            if dep_res.passed:
                diam = _finite(dep_payload.get("release_valve_diameter_in"))
                diam_txt = f'{diam:g}"' if diam is not None else '≤ 2"'
                dep_eval = {
                    "status": "passed",
                    "violations": [],
                    "missing": [],
                    "payload": dep_payload,
                    "message": f"Basınç düşürme önlemleri ve vana çapı ({diam_txt}) uygun (Md. 16).",
                }
            elif dep_res.violations:
                dep_eval = {
                    "status": "failed",
                    "violations": list(dep_res.violations),
                    "missing": list(dep_res.missing),
                    "payload": dep_payload,
                    "message": " ".join([*dep_res.violations, *dep_res.missing]),
                }
            else:
                dep_eval = {
                    "status": "warning",
                    "violations": [],
                    "missing": list(dep_res.missing),
                    "payload": dep_payload,
                    "message": " ".join(dep_res.missing),
                }
        except ValidationError as exc:
            dep_eval = {
                "status": "failed",
                "violations": [str(exc)],
                "missing": [],
                "payload": dep_payload,
                "message": str(exc),
            }

    dis_eval: dict[str, Any] | None = None
    if dis_payload is not None:
        try:
            dis_res = evaluate_discharge(DischargeInputs(**dis_payload))
            if dis_res.passed:
                dis_eval = {
                    "status": "passed",
                    "violations": [],
                    "missing": [],
                    "payload": dis_payload,
                    "message": (
                        "Boşaltma pigi, önlemler, onaylar ve 17.6 rapor bilgileri uygun "
                        "(BOT-FRM-İNB-001-023 / BOT-FRM-CDB-001-024)."
                    ),
                }
            elif dis_res.violations:
                dis_eval = {
                    "status": "failed",
                    "violations": list(dis_res.violations),
                    "missing": list(dis_res.missing),
                    "payload": dis_payload,
                    "message": " ".join([*dis_res.violations, *dis_res.missing]),
                }
            else:
                dis_eval = {
                    "status": "warning",
                    "violations": [],
                    "missing": list(dis_res.missing),
                    "payload": dis_payload,
                    "message": " ".join(dis_res.missing),
                }
        except ValidationError as exc:
            dis_eval = {
                "status": "failed",
                "violations": [str(exc)],
                "missing": [],
                "payload": dis_payload,
                "message": str(exc),
            }

    return {"depressurization": dep_eval, "discharge": dis_eval}


def _clean_text_value(raw: str) -> str:
    cleaned = " ".join(raw.replace("\xa0", " ").split()).strip(" .:-_|•")
    if not cleaned or all(ch in "._- " for ch in cleaned):
        return ""
    folded = _fold(cleaned)
    if folded in {"adi ve logosu", "ve logosu", "logusu", "logosu", "firma adi", "proje adi"}:
        return ""
    return cleaned[:200]


def _extract_label_text(text: str, patterns: Sequence[str], *, max_lines: int = 45) -> str:
    lines = text.splitlines()[:max_lines]
    for pat in patterns:
        rx = re.compile(pat, re.IGNORECASE)
        for line in lines:
            folded = _fold(line)
            m = rx.search(folded)
            if not m:
                continue
            tail = line[m.end() :]
            # Stop before a second colon-separated field on the same line
            parts = re.split(r"\s{2,}[A-Za-z0-9ÇĞİÖŞÜçğıöşü()./\s-]{2,28}\s*[:=]", tail, maxsplit=1)
            val = _clean_text_value(parts[0].lstrip(" :="))
            if val:
                return val
    return ""


def _parse_hhmm_to_min(time_str: str) -> float | None:
    m = re.match(r"^\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*$", str(time_str or ""))
    if not m:
        return None
    hh, mm, ss = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    if not (0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59):
        return None
    return hh * 60.0 + mm + ss / 60.0


def extract_common_header_extras(text: str) -> dict[str, Any]:
    """Extract common header metadata, notes, and signature status from one form's text."""
    header: dict[str, Any] = {}
    h1_no = _extract_label_text(text, (r"1\s*\.?\s*baslik\s*no",))
    if h1_no:
        header["head_1_no"] = h1_no
    h1_loc = _extract_label_text(text, (r"1\s*\.?\s*baslik\s*yeri", r"atma\s*basligi"))
    if h1_loc:
        header["head_1_location"] = h1_loc
    h2_no = _extract_label_text(text, (r"2\s*\.?\s*baslik\s*no",))
    if h2_no:
        header["head_2_no"] = h2_no
    h2_loc = _extract_label_text(text, (r"2\s*\.?\s*baslik\s*yeri", r"alma\s*basligi"))
    if h2_loc:
        header["head_2_location"] = h2_loc
    cabin = _extract_label_text(text, (r"test\s*kabininin?\s*yeri", r"kabin\s*yeri"))
    if cabin:
        header["cabin_location"] = cabin
    contractor = _extract_label_text(
        text, (r"yuklenici\s*(?:firma)?(?:\s*adi)?", r"muteahhit\s*(?:firma)?(?:\s*adi)?")
    )
    if contractor and "botas" not in _fold(contractor):
        header["contractor_name"] = contractor

    # Notes (`Açıklama` / `Açıklamalar` block)
    lines = [" ".join(ln.split()).strip() for ln in text.splitlines() if ln.strip()]
    note_lines: list[str] = []
    in_notes = False
    for line in lines:
        f = _fold(line)
        if re.match(r"^(?:\d+\s*\.?\s*)?aciklama(?:lar)?\b", f):
            in_notes = True
            after = re.sub(r"^(?:\d+\s*\.?\s*)?aciklama(?:lar)?\s*[:.]?\s*", "", line, flags=re.I)
            cleaned = after.strip(" ._")
            if cleaned:
                note_lines.append(cleaned)
            continue
        if in_notes:
            if any(
                stop in f
                for stop in (
                    "botas",
                    "yuklenici firma",
                    "muteahhit firma",
                    "adi-soyadi",
                    "adi soyadi",
                    "imza",
                    "onay",
                    "form no",
                )
            ):
                break
            cleaned = line.strip(" ._")
            if cleaned and len(note_lines) < 6:
                note_lines.append(cleaned)

    # Signature names across all pages (signatures may sit on page 1 before a trailing annex/table page)
    contractor_person = ""
    botas_person = ""
    contractor_hdr_idx = -100
    botas_hdr_idx = -100
    for idx, line in enumerate(lines):
        f = _fold(line)
        if "muteahhit" in f or "yuklenici" in f:
            contractor_hdr_idx = idx
        if "botas" in f or "boru hatlari" in f:
            botas_hdr_idx = idx
        if "adi-soyadi" in f or "adi soyadi" in f:
            segments = re.split(r"adi[-\s]*soyad[iı]\s*[:=]*", line, flags=re.IGNORECASE)
            cleaned_segs = [_clean_text_value(s) for s in segments[1:] if _clean_text_value(s)]
            has_contractor_hdr = 0 <= (idx - contractor_hdr_idx) <= 6
            has_botas_hdr = 0 <= (idx - botas_hdr_idx) <= 6
            if len(cleaned_segs) >= 2:
                contractor_person = cleaned_segs[0] or contractor_person
                botas_person = cleaned_segs[1] or botas_person
            elif len(cleaned_segs) == 1:
                if has_botas_hdr and (not has_contractor_hdr or botas_hdr_idx > contractor_hdr_idx):
                    botas_person = cleaned_segs[0] or botas_person
                else:
                    contractor_person = cleaned_segs[0] or contractor_person

    return {
        "header_extras": header,
        "notes": "\n".join(note_lines)[:1000],
        "signatures": {
            "contractor_name": contractor_person,
            "contractor_signed": bool(contractor_person),
            "botas_name": botas_person,
            "botas_signed": bool(botas_person),
        },
    }


def _extract_test_data_tables(text: str, *, dot_decimal: bool | None = None) -> dict[str, Any]:
    """Extract segment volumes and point measurements on `015 Hidrostatik Test Verileri`."""
    volume_segments: list[dict[str, Any]] = []
    measurements: list[dict[str, Any]] = []
    use_dot = is_dot_decimal_text(text) if dot_decimal is None else dot_decimal
    lines = [" ".join(ln.split()).strip() for ln in text.splitlines() if ln.strip()]

    in_meas = False
    for line in lines:
        f = _fold(line)
        # Volume row pattern: e.g. `11.1 mm   12000 m   2418.4 m3` or `Et Kalinligi 11.1 Uzunluk 12000 Hacim 2418.4`
        if ("et kalinligi" in f or "boru et" in f) and "hacim" in f and "toplam" not in f:
            nums = [
                _finite(parse_number(tok, dot_decimal=use_dot))
                for tok in re.findall(r"\d[\d.,]*", line)
            ]
            nums_f = [n for n in nums if n is not None]
            if len(nums_f) >= 3:
                volume_segments.append(
                    {
                        "wall_thickness_mm": nums_f[0],
                        "length_m": nums_f[1],
                        "volume_m3": nums_f[2],
                    }
                )
        if "test olcumleri" in f or ("boru ust" in f and "kot" in f):
            in_meas = True
            continue
        if in_meas:
            if (
                "aciklama" in f
                or "botas" in f
                or "yuklenici" in f
                or "muteahhit" in f
                or "sayfa" in f
            ):
                in_meas = False
                continue
            kp_normalized = re.sub(
                r"\b(\d{1,3})\+(\d{3}(?:[.,]\d+)?)\b",
                lambda m: (
                    f"{int(m.group(1)) * 1000.0 + float(m.group(2).replace(',', '.')):g}".replace(
                        ".", "." if use_dot else ","
                    )
                ),
                line,
            )
            nums = [
                _finite(parse_number(tok, dot_decimal=use_dot))
                for tok in re.findall(r"[-+]?\d[\d.,]*", kp_normalized)
            ]
            nums_f = [n for n in nums if n is not None]
            if len(nums_f) >= 3 and 50 <= abs(nums_f[0]) <= 5000:
                measurements.append(
                    {
                        "pipe_top_elev_m": nums_f[0],
                        "station_m": nums_f[1] if len(nums_f) >= 2 else None,
                        "max_pressure_bar": nums_f[2] if len(nums_f) >= 3 else None,
                        "max_smys_pct": nums_f[3] if len(nums_f) >= 4 else None,
                        "min_pressure_bar": nums_f[4] if len(nums_f) >= 5 else None,
                        "min_smys_pct": nums_f[5] if len(nums_f) >= 6 else None,
                        "note": "",
                    }
                )
    return {
        "volume_segments": volume_segments[:25],
        "test_measurements": measurements[:40],
    }


def _extract_pig_runs(text: str) -> list[dict[str, Any]]:
    """Parse detailed pig launch/receive rows from Cleaning (`016`), Dewatering (`023`), Drying."""
    runs: list[dict[str, Any]] = []
    lines = [" ".join(ln.split()).strip() for ln in text.splitlines() if ln.strip()]
    in_table = False
    pig_keywords = (
        "firca",
        "fırça",
        "kopuk",
        "köpük",
        "kalibre",
        "disk",
        "bidir",
        "swab",
        "kurutma",
        "temizlik",
        "bosaltma",
        "pig",
    )
    for line in lines:
        f = _fold(line)
        if (
            "pig izleme" in f
            or "pig tipi" in f
            or ("atilis" in f and ("alis" in f or "tarih" in f))
        ):
            in_table = True
            continue
        if in_table and any(stop in f for stop in ("aciklama", "botas", "muteahhit", "yuklenici")):
            in_table = False
            continue
        times = re.findall(r"\b\d{1,2}:\d{2}\b", line)
        if in_table or (times and any(k in f for k in pig_keywords)):
            if not times:
                continue
            launch_t = times[0]
            receive_t = times[1] if len(times) >= 2 else ""
            dur_min: float | None = None
            if launch_t and receive_t:
                t0 = _parse_hhmm_to_min(launch_t)
                t1 = _parse_hhmm_to_min(receive_t)
                if t0 is not None and t1 is not None:
                    if t1 < t0:
                        t1 += 24 * 60.0
                    dur_min = round(t1 - t0, 1)
            prefix = re.split(r"\d{1,2}:\d{2}|\d{1,2}[./-]\d{1,2}[./-]\d{2,4}", line, maxsplit=1)[0]
            pig_type = _clean_text_value(prefix) or "Pig"
            runs.append(
                {
                    "pig_type": pig_type,
                    "launch_time": launch_t,
                    "receive_time": receive_t,
                    "duration_min": dur_min,
                    "note": "",
                }
            )
    return runs[:30]


def _extract_drying_metrics(text: str) -> dict[str, Any]:
    """Extract Pre-Drying (`KUR-001`) / Final Drying (`KUR-002`) dew point & drying parameters."""
    folded = _fold(text)
    dew_c: float | None = None
    m_dp = re.search(
        r"(?:dew\s*point|cig\s*noktasi|ciy\s*noktasi|nem\s*noktasi|c[iı]g)\s*[:=)]*\s*(-?\d+(?:[.,]\d+)?)",
        folded,
    )
    if m_dp:
        val = _finite(parse_number(m_dp.group(1)))
        if val is not None and -90.0 <= val <= 40.0:
            dew_c = round(val, 2)

    dur_h: float | None = None
    m_dur = re.search(
        r"(?:sure|kurutma\s*suresi|duration)\s*[:=]*\s*(\d+(?:[.,]\d+)?)\s*(?:saat|hr|h\b)?", folded
    )
    if m_dur:
        val = _finite(parse_number(m_dur.group(1)))
        if val is not None and 0 < val <= 500:
            dur_h = round(val, 2)

    reported_passed: bool | None = None
    if "kabul edilmemistir" in folded or "basarisiz" in folded or re.search(r"\bred\b", folded):
        reported_passed = False
    elif "kabul edilmistir" in folded or "uygun" in folded or "tamamlandi" in folded:
        reported_passed = True

    return {
        "target_dew_point_c": DEFAULT_TARGET_DEW_POINT_C,
        "measured_dew_point_c": dew_c,
        "duration_hours": dur_h,
        "reported_passed": reported_passed,
    }


def _map_filling_rows(entries: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    has_meter_col = any(
        len(e.get("nums") or []) >= 5 and float(e["nums"][0]) >= 100.0 for e in entries
    )
    for ent in list(entries)[:MAX_TABLE_ROWS]:
        nums = [float(n) for n in (ent.get("nums") or [])]
        if has_meter_col and len(nums) == 2 and abs(nums[0]) < 1e-6 and abs(nums[1]) < 1e-6:
            row = {
                "time_str": str(ent.get("time_str") or ""),
                "meter_reading_m3": None,
                "delta_volume_m3": 0.0,
                "total_volume_m3": 0.0,
                "water_inlet_temp_c": None,
                "water_pressure_bar": None,
                "note": str(ent.get("notes") or ""),
            }
        elif has_meter_col and len(nums) == 4 and nums[0] < 100.0:
            row = {
                "time_str": str(ent.get("time_str") or ""),
                "meter_reading_m3": None,
                "delta_volume_m3": nums[0],
                "total_volume_m3": nums[1],
                "water_inlet_temp_c": nums[2],
                "water_pressure_bar": nums[3],
                "note": str(ent.get("notes") or ""),
            }
        else:
            row = {
                "time_str": str(ent.get("time_str") or ""),
                "meter_reading_m3": nums[0] if len(nums) >= 1 else None,
                "delta_volume_m3": nums[1] if len(nums) >= 2 else None,
                "total_volume_m3": nums[2]
                if len(nums) >= 3
                else (nums[0] if len(nums) == 1 else None),
                "water_inlet_temp_c": nums[3] if len(nums) >= 4 else None,
                "water_pressure_bar": nums[4] if len(nums) >= 5 else None,
                "note": str(ent.get("notes") or ""),
            }
        rows.append(row)
    return rows


def _map_monitoring_rows(entries: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ent in list(entries)[:MAX_TABLE_ROWS]:
        nums = [float(n) for n in (ent.get("nums") or [])]
        # BOTAŞ 018/021 standard column order:
        # Basınç, Çevre T, Toprak1, Boru1, Toprak2, Boru2, Toprak3, Boru3, Toprak4, Boru4, Avg.Toprak, Avg.Boru
        avg_soil: float | None = None
        avg_pipe: float | None = None
        if len(nums) >= 12:
            if not (abs(nums[-2]) < 1e-6 and abs(nums[-1]) < 1e-6):
                avg_soil, avg_pipe = nums[-2], nums[-1]
        elif len(nums) == 6:
            if not (abs(nums[4]) < 1e-6 and abs(nums[5]) < 1e-6):
                avg_soil, avg_pipe = nums[4], nums[5]
        row = {
            "time_str": str(ent.get("time_str") or ""),
            "pressure_bar": nums[0] if len(nums) >= 1 else None,
            "ambient_temp_c": nums[1] if len(nums) >= 2 else None,
            "soil_1_c": nums[2] if len(nums) >= 3 else None,
            "pipe_1_c": nums[3] if len(nums) >= 4 else None,
            "soil_2_c": nums[4] if len(nums) >= 5 and len(nums) != 6 else None,
            "pipe_2_c": nums[5] if len(nums) >= 6 and len(nums) != 6 else None,
            "soil_3_c": nums[6] if len(nums) >= 7 else None,
            "pipe_3_c": nums[7] if len(nums) >= 8 else None,
            "soil_4_c": nums[8] if len(nums) >= 9 else None,
            "pipe_4_c": nums[9] if len(nums) >= 10 else None,
            "avg_soil_c": avg_soil,
            "avg_pipe_c": avg_pipe,
            "note": str(ent.get("notes") or ""),
        }
        rows.append(row)
    return rows


def _map_pressurization_rows(entries: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ent in list(entries)[:MAX_TABLE_ROWS]:
        nums = [float(n) for n in (ent.get("nums") or [])]
        row = {
            "time_str": str(ent.get("time_str") or ""),
            "p_initial_bar": nums[0] if len(nums) >= 1 else None,
            "p_final_bar": nums[1] if len(nums) >= 2 else None,
            "step_water_m3": nums[2] if len(nums) >= 3 else None,
            "total_water_m3": nums[3] if len(nums) >= 4 else None,
            "water_temp_c": nums[4] if len(nums) >= 5 else None,
            "note": str(ent.get("notes") or ""),
        }
        rows.append(row)
    return rows


def _extract_supplementary_parameters(form_code: str, text: str) -> dict[str, Any]:
    folded = _fold(text)
    params: dict[str, Any] = {}
    if form_code == "chart_recorder":
        m_ch = re.search(r"chart\s*no\s*[:=]*\s*([a-z0-9._/-]+)", folded)
        if m_ch:
            params["chart_no"] = m_ch.group(1).upper()
        m_rng = re.search(r"(\d{2,3})\s*bar", folded)
        if m_rng:
            params["range_bar"] = float(m_rng.group(1))
        m_hr = re.search(r"(\d{1,3})\s*(?:hr|h|saat)", folded)
        if m_hr:
            params["duration_hours"] = float(m_hr.group(1))
    elif form_code == "caliper_pig":
        m_plate = re.search(r"(?:kalibre\s*plakasi|plate|cap)\s*[:=]*\s*(\d+(?:[.,]\d+)?)", folded)
        if m_plate:
            params["plate_diameter_mm"] = _finite(parse_number(m_plate.group(1)))
        m_dent = re.search(
            r"(?:max\.?\s*gocuk|ezilme|dent|ovalite)\s*[:=]*\s*(\d+(?:[.,]\d+)?)", folded
        )
        if m_dent:
            params["max_dent_pct"] = _finite(parse_number(m_dent.group(1)))
    elif form_code == "calculation_sheet":
        for pat, key in (
            (r"\bpmin\s*[:=]\s*(\d+(?:[.,]\d+)?)", "p_min_bar"),
            (r"\bpmax\s*[:=]\s*(\d+(?:[.,]\d+)?)", "p_max_bar"),
            (r"\bvsec\s*[:=]\s*(\d+(?:[.,]\d+)?)", "v_sec_m3"),
            (r"\bshoop\s*[:=]\s*(\d+(?:[.,]\d+)?)", "hoop_stress_pct"),
        ):
            m = re.search(pat, folded)
            if m:
                params[key] = _finite(parse_number(m.group(1)))
    return params


def build_form_structured_payload(
    form_code: str,
    text: str,
    *,
    time_log_entries: Sequence[dict[str, Any]] | None = None,
    dot_decimal: bool | None = None,
) -> dict[str, Any]:
    """Return enriched table rows, notes, signatures, and form-specific sub-blocks."""
    use_dot = is_dot_decimal_text(text) if dot_decimal is None else dot_decimal
    extras = extract_common_header_extras(text)
    out: dict[str, Any] = {
        "header_extras": extras["header_extras"],
        "notes": extras["notes"],
        "signatures": extras["signatures"],
    }
    entries = list(time_log_entries or [])
    if form_code == "test_data":
        out["test_data"] = _extract_test_data_tables(text, dot_decimal=use_dot)
    elif form_code == "filling":
        out["rows"] = _map_filling_rows(entries)
    elif form_code in {"leak_stabilization", "pressure_test"}:
        out["rows"] = _map_monitoring_rows(entries)
    elif form_code in {"strength", "pressurization"}:
        out["rows"] = _map_pressurization_rows(entries)
    elif form_code in {"cleaning", "dewatering"}:
        out["pig_runs"] = _extract_pig_runs(text)
    elif form_code in {"pre_drying", "final_drying"}:
        out["drying"] = _extract_drying_metrics(text)
        out["pig_runs"] = _extract_pig_runs(text)
    else:
        out["parameters"] = _extract_supplementary_parameters(form_code, text)
    return out


def _try_parse_iso_utc(raw: Any) -> datetime | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _monitoring_row_pipe_temp(row: dict[str, Any]) -> float | None:
    avg_p = _finite(row.get("avg_pipe_c"))
    if avg_p is not None:
        return avg_p
    pipes = [
        v
        for k in ("pipe_1_c", "pipe_2_c", "pipe_3_c", "pipe_4_c")
        if (v := _finite(row.get(k))) is not None
    ]
    if pipes:
        return sum(pipes) / len(pipes)
    return None


def _monitoring_row_temperature(row: dict[str, Any]) -> float | None:
    pipe_temp = _monitoring_row_pipe_temp(row)
    if pipe_temp is not None:
        return pipe_temp
    avg_soil = _finite(row.get("avg_soil_c"))
    if avg_soil is not None:
        return avg_soil
    soils = [
        v
        for k in ("soil_1_c", "soil_2_c", "soil_3_c", "soil_4_c")
        if (v := _finite(row.get(k))) is not None
    ]
    if soils:
        return sum(soils) / len(soils)
    return _finite(row.get("ambient_temp_c"))


def parse_base_date(raw: Any) -> date | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    iso_head = text[:10]
    try:
        return date.fromisoformat(iso_head)
    except ValueError:
        pass
    m_ymd = re.match(r"^\s*(\d{4})[./-](\d{1,2})[./-](\d{1,2})\b", text)
    if m_ymd:
        year_val, month_val, day_val = int(m_ymd.group(1)), int(m_ymd.group(2)), int(m_ymd.group(3))
        try:
            return date(year_val, month_val, day_val)
        except ValueError:
            pass
    m = re.match(r"^\s*(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b", text)
    if not m:
        return None
    day_val, month_val, year_val = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(year_val, month_val, day_val)
    except ValueError:
        return None


def monitoring_rows_to_time_series(
    rows: Sequence[dict[str, Any]],
    *,
    default_date: date,
    note_prefix: str = "",
) -> tuple[list[dict[str, Any]], int]:
    """Convert Form 018/021 monitoring rows into UTC time-series record payloads."""
    out: list[dict[str, Any]] = []
    skipped = 0
    day_offset = 0
    prev_abs_min: float | None = None

    for row in rows[:MAX_TABLE_ROWS]:
        if not isinstance(row, dict):
            skipped += 1
            continue
        p_val = _finite(row.get("pressure_bar"))
        t_val = _monitoring_row_temperature(row)
        if p_val is None or t_val is None:
            skipped += 1
            continue

        row_ts = _try_parse_iso_utc(row.get("timestamp"))
        if row_ts is None:
            hhmm_min = _parse_hhmm_to_min(str(row.get("time_str") or ""))
            if hhmm_min is None:
                skipped += 1
                continue
            if prev_abs_min is not None and (hhmm_min + day_offset * 1440.0) < prev_abs_min - 30.0:
                day_offset += 1
            prev_abs_min = hhmm_min + day_offset * 1440.0
            row_ts = datetime(
                default_date.year,
                default_date.month,
                default_date.day,
                tzinfo=timezone.utc,
            ) + timedelta(minutes=prev_abs_min)

        note_parts: list[str] = [note_prefix] if note_prefix else []
        amb = _finite(row.get("ambient_temp_c"))
        if amb is not None:
            note_parts.append(f"Cevre {amb:.1f} °C")
        out.append(
            {
                "timestamp": row_ts,
                "pressure_bar": p_val,
                "temperature_c": t_val,
                "volume_m3": None,
                "notes": "; ".join(note_parts),
            }
        )
    return out, skipped


def time_series_to_monitoring_rows(records: Sequence[Any]) -> list[dict[str, Any]]:
    """Convert persisted ``TimeSeriesRecord`` rows into Form 018/021 monitoring table rows."""
    out: list[dict[str, Any]] = []
    for rec in list(records)[:MAX_TABLE_ROWS]:
        ts = ensure_utc(getattr(rec, "timestamp", None))
        if ts is None:
            continue
        p_val = _finite(getattr(rec, "pressure_bar", None))
        t_val = _finite(getattr(rec, "temperature_c", None))
        if p_val is None or t_val is None:
            continue
        out.append(
            {
                "timestamp": iso_z(ts),
                "time_str": ts.strftime("%H:%M"),
                "pressure_bar": round(p_val, 3),
                "ambient_temp_c": None,
                "soil_1_c": None,
                "pipe_1_c": round(t_val, 3),
                "soil_2_c": None,
                "pipe_2_c": None,
                "avg_soil_c": None,
                "avg_pipe_c": round(t_val, 3),
            }
        )
    return out


def _compute_time_stats(times: Sequence[str]) -> dict[str, Any]:
    abs_mins: list[tuple[str, float]] = []
    day_offset = 0.0
    prev_abs: float | None = None
    for raw_t in times:
        base = _parse_hhmm_to_min(raw_t)
        if base is None:
            continue
        if prev_abs is not None and (base + day_offset) < prev_abs - 30.0:
            day_offset += 24 * 60.0
        cur = base + day_offset
        abs_mins.append((str(raw_t).strip(), cur))
        prev_abs = cur
    if not abs_mins:
        return {
            "row_count": len(times),
            "duration_hours": 0.0,
            "steps_min": [],
            "median_step_min": None,
            "max_gap_min": 0.0,
            "first_time": None,
            "last_time": None,
            "first_abs_min": None,
            "last_abs_min": None,
        }
    steps = [round(abs_mins[i][1] - abs_mins[i - 1][1], 2) for i in range(1, len(abs_mins))]
    pos = [s for s in steps if s > 0]
    dur_h = (abs_mins[-1][1] - abs_mins[0][1]) / 60.0 if len(abs_mins) >= 2 else 0.0
    return {
        "row_count": len(abs_mins),
        "duration_hours": round(dur_h, 2),
        "steps_min": steps,
        "median_step_min": round(statistics.median(pos), 2) if pos else None,
        "max_gap_min": round(max(pos), 2) if pos else 0.0,
        "first_time": abs_mins[0][0],
        "last_time": abs_mins[-1][0],
        "first_abs_min": round(abs_mins[0][1], 2),
        "last_abs_min": round(abs_mins[-1][1], 2),
    }


def reconcile_form_extracted_data(form_code: str, raw_data: dict[str, Any]) -> dict[str, Any]:
    """Recompute form summaries & time-log stats after manual edits to rows or inputs."""
    data = copy.deepcopy(raw_data or {})
    if not isinstance(data.get("header"), dict):
        data["header"] = {}

    if form_code == "filling" and isinstance(data.get("rows"), list):
        rows = data["rows"][:MAX_TABLE_ROWS]
        data["rows"] = rows
        data["time_log"] = _compute_time_stats([str(r.get("time_str") or "") for r in rows])
        if rows:
            total_vols = [
                v for r in rows if (v := _finite(r.get("total_volume_m3"))) is not None and v >= 0
            ]
            deltas = [
                v for r in rows if (v := _finite(r.get("delta_volume_m3"))) is not None and v >= 0
            ]
            meters = [
                v for r in rows if (v := _finite(r.get("meter_reading_m3"))) is not None and v >= 0
            ]
            if total_vols:
                total_filled = round(max(total_vols), 3)
            elif len(meters) >= 2 and meters[-1] > meters[0]:
                total_filled = round(meters[-1] - meters[0], 3)
            elif deltas:
                total_filled = round(sum(deltas), 3)
            elif meters:
                total_filled = round(max(meters), 3)
            else:
                total_filled = None
            temps = [t for r in rows if (t := _finite(r.get("water_inlet_temp_c"))) is not None]
            press = [p for r in rows if (p := _finite(r.get("water_pressure_bar"))) is not None]
            data["filling"] = {
                "total_filled_m3": total_filled,
                "min_temp_c": round(min(temps), 2) if temps else None,
                "max_temp_c": round(max(temps), 2) if temps else None,
                "max_pressure_bar": round(max(press), 2) if press else None,
            }
        else:
            data["filling"] = {
                "total_filled_m3": None,
                "min_temp_c": None,
                "max_temp_c": None,
                "max_pressure_bar": None,
            }

    elif form_code in {"leak_stabilization", "pressure_test"} and isinstance(
        data.get("rows"), list
    ):
        rows = data["rows"][:MAX_TABLE_ROWS]
        data["rows"] = rows
        data["time_log"] = _compute_time_stats([str(r.get("time_str") or "") for r in rows])
        if rows:
            press = [p for r in rows if (p := _finite(r.get("pressure_bar"))) is not None]
            mon_temps: list[float] = []
            pipe_avgs: list[float] = []
            ts_domain_rows: list[DomainTimeSeriesRecord] = []
            has_untimed_with_time_str = False
            probe_pairs = 0
            for r in rows:
                s1, p1 = _finite(r.get("soil_1_c")), _finite(r.get("pipe_1_c"))
                if s1 is not None and p1 is not None:
                    probe_pairs += 1
                for k in ("ambient_temp_c", "soil_1_c", "pipe_1_c", "avg_soil_c", "avg_pipe_c"):
                    val = _finite(r.get(k))
                    if val is not None:
                        mon_temps.append(val)
                row_pipe = _monitoring_row_pipe_temp(r)
                if row_pipe is not None:
                    pipe_avgs.append(row_pipe)
                row_ts = _try_parse_iso_utc(r.get("timestamp"))
                row_p = _finite(r.get("pressure_bar"))
                row_t = row_pipe if row_pipe is not None else _monitoring_row_temperature(r)
                if row_ts is not None and row_p is not None and row_t is not None:
                    try:
                        ts_domain_rows.append(
                            DomainTimeSeriesRecord(
                                timestamp=row_ts,
                                pressure_bar=row_p,
                                temperature_c=row_t,
                            )
                        )
                    except ValidationError:
                        pass
                elif (
                    row_ts is None and _parse_hhmm_to_min(str(r.get("time_str") or "")) is not None
                ):
                    has_untimed_with_time_str = True
            last_4h: float | None = None
            if len(pipe_avgs) >= 2:
                if len(pipe_avgs) >= 8:
                    prev4 = sum(pipe_avgs[-8:-4]) / 4.0
                    last4 = sum(pipe_avgs[-4:]) / 4.0
                    last_4h = round(abs(last4 - prev4), 3)
                else:
                    last_4h = round(abs(pipe_avgs[-1] - pipe_avgs[0]), 3)

            if len(ts_domain_rows) >= 2 and not has_untimed_with_time_str:
                ts_eval = evaluate_time_series(ts_domain_rows)
                data["time_log"]["row_count"] = max(
                    int(data["time_log"].get("row_count") or 0),
                    ts_eval.record_count,
                )
                if ts_eval.first_timestamp is not None and not data["time_log"].get("first_time"):
                    first_utc = ensure_utc(ts_eval.first_timestamp)
                    if first_utc is not None:
                        data["time_log"]["first_time"] = first_utc.strftime("%H:%M")
                if ts_eval.last_timestamp is not None and not data["time_log"].get("last_time"):
                    last_utc = ensure_utc(ts_eval.last_timestamp)
                    if last_utc is not None:
                        data["time_log"]["last_time"] = last_utc.strftime("%H:%M")
                data["time_log"]["duration_hours"] = round(ts_eval.duration_hours, 2)
                if ts_eval.max_gap_hours is not None:
                    data["time_log"]["max_gap_min"] = round(ts_eval.max_gap_hours * 60.0, 2)
                if ts_eval.thermal_temp_diff_c is not None:
                    last_4h = round(ts_eval.thermal_temp_diff_c, 3)

            raw_prev_mon = data.get("monitoring")
            prev_mon: dict[str, Any] = raw_prev_mon if isinstance(raw_prev_mon, dict) else {}
            data["monitoring"] = {
                **prev_mon,
                "min_temp_c": round(min(mon_temps), 2) if mon_temps else prev_mon.get("min_temp_c"),
                "max_temp_c": round(max(mon_temps), 2) if mon_temps else prev_mon.get("max_temp_c"),
                "probe_pair_count": probe_pairs or int(prev_mon.get("probe_pair_count") or 0),
                "block_avg_count": len(pipe_avgs),
                "last_4h_delta_c": last_4h
                if last_4h is not None
                else prev_mon.get("last_4h_delta_c"),
                "pipe_start_c": round(pipe_avgs[0], 3)
                if pipe_avgs
                else prev_mon.get("pipe_start_c"),
                "pipe_end_c": round(pipe_avgs[-1], 3) if pipe_avgs else prev_mon.get("pipe_end_c"),
                "p_start_bar": press[0] if press else prev_mon.get("p_start_bar"),
                "p_end_bar": press[-1] if press else prev_mon.get("p_end_bar"),
            }
        else:
            raw_prev_mon = data.get("monitoring")
            prev_mon = raw_prev_mon if isinstance(raw_prev_mon, dict) else {}
            data["monitoring"] = {
                **prev_mon,
                "min_temp_c": None,
                "max_temp_c": None,
                "probe_pair_count": 0,
                "block_avg_count": 0,
                "last_4h_delta_c": None,
                "pipe_start_c": None,
                "pipe_end_c": None,
                "p_start_bar": None,
                "p_end_bar": None,
            }

    elif form_code in {"strength", "pressurization"} and isinstance(data.get("rows"), list):
        rows = data["rows"][:MAX_TABLE_ROWS]
        data["rows"] = rows
        data["time_log"] = _compute_time_stats([str(r.get("time_str") or "") for r in rows])
        if rows:
            ps = [
                v
                for r in rows
                for v in (_finite(r.get("p_initial_bar")), _finite(r.get("p_final_bar")))
                if v is not None
            ]
            step_vs = [v for r in rows if (v := _finite(r.get("step_water_m3"))) is not None]
            tot_vs = [v for r in rows if (v := _finite(r.get("total_water_m3"))) is not None]
            pr_temps = [v for r in rows if (v := _finite(r.get("water_temp_c"))) is not None]
            raw_prev_pr = data.get("pressurization")
            prev_pr: dict[str, Any] = raw_prev_pr if isinstance(raw_prev_pr, dict) else {}
            data["pressurization"] = {
                **prev_pr,
                "p_min_bar": min(ps) if ps else prev_pr.get("p_min_bar"),
                "p_max_bar": max(ps) if ps else prev_pr.get("p_max_bar"),
                "total_added_water_m3": (
                    round(max(tot_vs), 4)
                    if tot_vs
                    else (
                        round(sum(step_vs), 4) if step_vs else prev_pr.get("total_added_water_m3")
                    )
                ),
                "temp_c": round(statistics.median(pr_temps), 2)
                if pr_temps
                else prev_pr.get("temp_c"),
            }
        else:
            raw_prev_pr = data.get("pressurization")
            prev_pr = raw_prev_pr if isinstance(raw_prev_pr, dict) else {}
            data["pressurization"] = {
                **prev_pr,
                "p_min_bar": None,
                "p_max_bar": None,
                "total_added_water_m3": None,
                "temp_c": None,
            }

    elif form_code in {"cleaning", "dewatering", "pre_drying", "final_drying"}:
        runs = data.get("pig_runs")
        if isinstance(runs, list):
            if runs:
                durations: list[float] = []
                first_t: str | None = None
                last_t: str | None = None
                for idx, r in enumerate(runs):
                    lt = str(r.get("launch_time") or "").strip()
                    rt = str(r.get("receive_time") or "").strip()
                    if idx == 0 and lt:
                        first_t = lt
                    if rt:
                        last_t = rt
                    d_val = _finite(r.get("duration_min"))
                    if d_val is None and lt and rt:
                        t0, t1 = _parse_hhmm_to_min(lt), _parse_hhmm_to_min(rt)
                        if t0 is not None and t1 is not None:
                            if t1 < t0:
                                t1 += 24 * 60.0
                            d_val = round(t1 - t0, 1)
                            r["duration_min"] = d_val
                    if d_val is not None and d_val > 0:
                        durations.append(d_val)
                raw_prev_ev = data.get("pig_events")
                prev_ev: dict[str, Any] = raw_prev_ev if isinstance(raw_prev_ev, dict) else {}
                data["pig_events"] = {
                    **prev_ev,
                    "has_events": True,
                    "event_count": len(runs),
                    "first_time": first_t or prev_ev.get("first_time"),
                    "last_time": last_t or prev_ev.get("last_time"),
                    "travel_time_min": durations[-1]
                    if durations
                    else prev_ev.get("travel_time_min"),
                }
            else:
                raw_prev_ev = data.get("pig_events")
                prev_ev = raw_prev_ev if isinstance(raw_prev_ev, dict) else {}
                data["pig_events"] = {
                    **prev_ev,
                    "has_events": False,
                    "event_count": 0,
                    "first_time": None,
                    "last_time": None,
                    "travel_time_min": None,
                }

    if form_code == "dewatering":
        raw_dep = data.get("depressurization")
        if isinstance(raw_dep, dict):
            raw_dep["release_valve_diameter_in"] = _finite(raw_dep.get("release_valve_diameter_in"))
        raw_dis = data.get("discharge")
        if isinstance(raw_dis, dict):
            raw_dis["duration_min"] = _finite(raw_dis.get("duration_min"))

    return data


def _merge_dict_fill_missing(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in incoming.items():
        if v is None or v == "":
            continue
        cur = out.get(k)
        if cur is None or cur == "":
            out[k] = copy.deepcopy(v)
    return out


def _append_unique_dicts(
    existing: Sequence[Any], incoming: Sequence[Any], *, limit: int
) -> list[dict[str, Any]]:
    combined: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in [*existing, *incoming]:
        if not isinstance(item, dict):
            continue
        fp = json.dumps(item, sort_keys=True, ensure_ascii=False, default=str)
        if fp in seen:
            continue
        seen.add(fp)
        combined.append(copy.deepcopy(item))
        if len(combined) >= limit:
            break
    return combined


def merge_form_extracted_data(
    form_code: str,
    existing_data: dict[str, Any],
    incoming_data: dict[str, Any],
) -> dict[str, Any]:
    """Merge a continuation page's extracted data into an existing SectionForm record."""
    merged = copy.deepcopy(existing_data or {})
    inc = copy.deepcopy(incoming_data or {})

    for dict_key in (
        "header",
        "header_extras",
        "drying",
        "parameters",
        "air",
        "pressure_acceptance",
        "air_acceptance",
        "monitoring",
        "filling",
        "pressurization",
        "pig_events",
        "depressurization",
        "discharge",
    ):
        raw_base_sub = merged.get(dict_key)
        base_sub: dict[str, Any] = raw_base_sub if isinstance(raw_base_sub, dict) else {}
        raw_inc_sub = inc.get(dict_key)
        inc_sub: dict[str, Any] = raw_inc_sub if isinstance(raw_inc_sub, dict) else {}
        if base_sub or inc_sub:
            merged[dict_key] = _merge_dict_fill_missing(base_sub, inc_sub)

    if isinstance(merged.get("rows"), list) or isinstance(inc.get("rows"), list):
        merged["rows"] = _append_unique_dicts(
            merged.get("rows") or [],
            inc.get("rows") or [],
            limit=MAX_TABLE_ROWS,
        )

    if isinstance(merged.get("pig_runs"), list) or isinstance(inc.get("pig_runs"), list):
        merged["pig_runs"] = _append_unique_dicts(
            merged.get("pig_runs") or [],
            inc.get("pig_runs") or [],
            limit=30,
        )

    raw_base_td = merged.get("test_data")
    base_td: dict[str, Any] = raw_base_td if isinstance(raw_base_td, dict) else {}
    raw_inc_td = inc.get("test_data")
    inc_td: dict[str, Any] = raw_inc_td if isinstance(raw_inc_td, dict) else {}
    if base_td or inc_td:
        merged["test_data"] = {
            "volume_segments": _append_unique_dicts(
                base_td.get("volume_segments") or [],
                inc_td.get("volume_segments") or [],
                limit=25,
            ),
            "test_measurements": _append_unique_dicts(
                base_td.get("test_measurements") or [],
                inc_td.get("test_measurements") or [],
                limit=40,
            ),
        }

    existing_notes = str(merged.get("notes") or "").strip()
    incoming_notes = str(inc.get("notes") or "").strip()
    if incoming_notes and incoming_notes not in existing_notes:
        merged["notes"] = (
            f"{existing_notes}\n{incoming_notes}" if existing_notes else incoming_notes
        )[:1000]

    raw_base_sig = merged.get("signatures")
    base_sig: dict[str, Any] = raw_base_sig if isinstance(raw_base_sig, dict) else {}
    raw_inc_sig = inc.get("signatures")
    inc_sig: dict[str, Any] = raw_inc_sig if isinstance(raw_inc_sig, dict) else {}
    if base_sig or inc_sig:
        contractor_name = str(
            base_sig.get("contractor_name") or inc_sig.get("contractor_name") or ""
        ).strip()
        botas_name = str(base_sig.get("botas_name") or inc_sig.get("botas_name") or "").strip()
        merged["signatures"] = {
            "contractor_name": contractor_name,
            "contractor_signed": bool(contractor_name),
            "botas_name": botas_name,
            "botas_signed": bool(botas_name),
        }

    return reconcile_form_extracted_data(form_code, merged)


def _mk_finding(
    code: str,
    title: str,
    status: str,
    message: str,
    ref: str,
    *,
    expected: str = "",
    actual: str = "",
) -> dict[str, Any]:
    return {
        "code": code,
        "title": title,
        "status": status,
        "message": message,
        "ref": ref,
        "expected": expected,
        "actual": actual,
    }


def evaluate_all_form_findings(
    merged_header: dict[str, Any],
    forms_by_code: dict[str, dict[str, Any]],
    calculations: dict[str, Any],
    check_details: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Produce per-form specification findings for all filled forms in the section."""
    findings_by_code: dict[str, list[dict[str, Any]]] = {}
    prof_calc = calculations.get("profile") or {}
    air_calc = calculations.get("air") or {}
    pres_calc = calculations.get("pressure") or {}
    pig_calc = calculations.get("pig") or {}
    len_m = _finite(merged_header.get("length_m"))
    vt_m3 = _finite(merged_header.get("section_volume_m3"))

    def _from_check(ck_key: str, code: str, title: str) -> dict[str, Any]:
        det = check_details.get(ck_key) or {}
        st = str(det.get("status") or "pending")
        if st == "pending":
            st = "info"
        return _mk_finding(
            code,
            title,
            st,
            str(det.get("message") or "Kontrol bekleniyor."),
            f"4-NGTL 0-GN-P-002-5007 R4 · Md. {det.get('ref') or '-'}",
        )

    for form_code, entry in forms_by_code.items():
        ext = entry.get("extracted_data") or {}
        items: list[dict[str, Any]] = []

        if form_code == "test_data":
            if len_m is not None:
                ok_len = len_m <= MAX_TEST_SECTION_LENGTH_M
                items.append(
                    _mk_finding(
                        "td_length",
                        "Test Bölüm Boyu Limiti",
                        "passed" if ok_len else "failed",
                        (
                            f"Test bölüm boyu {len_m:.1f} m ≤ {MAX_TEST_SECTION_LENGTH_M:.0f} m sınırında."
                            if ok_len
                            else f"Test bölüm boyu ({len_m:.1f} m) izin verilen {MAX_TEST_SECTION_LENGTH_M:.0f} m sınırını aşıyor."
                        ),
                        "4-NGTL Md. 7.1",
                        expected=f"≤ {MAX_TEST_SECTION_LENGTH_M:.0f} m",
                        actual=f"{len_m:.1f} m",
                    )
                )
            if vt_m3 is not None:
                ok_vol = vt_m3 <= MAX_TEST_SECTION_VOLUME_M3
                items.append(
                    _mk_finding(
                        "td_volume",
                        "Test Bölüm Hacmi Kontrolü",
                        "passed" if ok_vol else "warning",
                        (
                            f"Geometrik hacim {vt_m3:.2f} m³ ≤ {MAX_TEST_SECTION_VOLUME_M3:.0f} m³."
                            if ok_vol
                            else f"Bölüm hacmi {vt_m3:.2f} m³, referans {MAX_TEST_SECTION_VOLUME_M3:.0f} m³ üstünde; pompa/dolum süresi doğrulanmalı."
                        ),
                        "4-NGTL Md. 7.1",
                        expected=f"≤ {MAX_TEST_SECTION_VOLUME_M3:.0f} m³",
                        actual=f"{vt_m3:.2f} m³",
                    )
                )
            if prof_calc.get("passed") is not None:
                items.append(
                    _mk_finding(
                        "td_profile",
                        "Basınç Penceresi & %100 SMYS Doğrulaması",
                        "passed" if prof_calc["passed"] else "failed",
                        str(prof_calc.get("summary") or ""),
                        "4-NGTL Md. 4.2 / 7.3",
                        expected=f"Pmin={prof_calc.get('p_min_bar')}..Pmax={prof_calc.get('p_max_bar')} bar",
                        actual=str(prof_calc.get("monitored_pressure_bar") or "Tanımlı"),
                    )
                )

        elif form_code == "cleaning":
            pig_ev = ext.get("pig_events") or {}
            t_min = _finite(pig_ev.get("travel_time_min"))
            if pig_ev.get("has_events"):
                if t_min and len_m:
                    spd = len_m / (t_min * 60.0)
                    lim = get_pig_speed_limit("Temizlik pigi | max 2.500 m/sn | Madde 9")
                    ok = spd <= (lim.max_speed_m_per_s or 2.5)
                    items.append(
                        _mk_finding(
                            "cl_speed",
                            "Temizlik Pig Hızı Kontrolü",
                            "passed" if ok else "failed",
                            f"Hesaplanan pig hızı {spd:.2f} m/sn (sınır ≤ {lim.max_speed_m_per_s:.2f} m/sn).",
                            "4-NGTL Md. 9",
                            expected=f"≤ {lim.max_speed_m_per_s:.2f} m/sn",
                            actual=f"{spd:.2f} m/sn",
                        )
                    )
                else:
                    items.append(
                        _mk_finding(
                            "cl_events",
                            "Pig Atılış / Alınış Kayıtları",
                            "passed",
                            f"Temizlik pig hareketleri kaydedildi ({pig_ev.get('first_time') or '?'} → {pig_ev.get('last_time') or '?'}).",
                            "4-NGTL Md. 6",
                        )
                    )
            else:
                items.append(
                    _mk_finding(
                        "cl_missing_times",
                        "Temizlik Pig Saatleri Eksik",
                        "warning",
                        "Formda temizlik pigi atılış/alınış saatleri okunamadı; elle kontrol edin.",
                        "4-NGTL Md. 6",
                    )
                )

        elif form_code == "filling":
            items.append(
                _from_check(
                    "ambient_temp", "fl_temp", "Dolum Sırasında Ortam/Su Sıcaklığı (≥ +2 °C)"
                )
            )
            items.append(
                _from_check(
                    "fill_records", "fl_hourly", "Saatlik Dolum Hacmi ve Sıcaklık Kayıtları"
                )
            )
            filled_m3 = _finite((ext.get("filling") or {}).get("total_filled_m3"))
            if filled_m3 is not None and vt_m3 and vt_m3 > 0:
                diff_pct = ((filled_m3 - vt_m3) / vt_m3) * 100.0
                ok_v = abs(diff_pct) <= 3.0
                items.append(
                    _mk_finding(
                        "fl_vol_match",
                        "Doldurulan Su Hacmi vs Geometrik Hacim",
                        "passed" if ok_v else "warning",
                        f"Doldurulan su {filled_m3:.2f} m³ vs geometrik Vt={vt_m3:.2f} m³ (fark %{diff_pct:+.2f}).",
                        "4-NGTL Md. 11.2",
                        expected=f"{vt_m3:.2f} m³ (±%3)",
                        actual=f"{filled_m3:.2f} m³",
                    )
                )

        elif form_code == "leak_stabilization":
            items.append(
                _from_check(
                    "thermal_balance",
                    "lk_thermal",
                    "24 Saat Termal Dengeleme & Son 4 Saat ΔT ≤ 0,50 °C",
                )
            )
            items.append(
                _from_check("temp_probes", "lk_probes", "Toprak ve Boru Sıcaklık Prob Eşleşmeleri")
            )

        elif form_code in {"strength", "pressurization"}:
            items.append(
                _from_check(
                    "pressurization_volume", "st_pv", "Basınçlandırma P-V & %0,2 İlave Su Kontrolü"
                )
            )
            items.append(
                _from_check("two_hour_hold", "st_hold", "2 Saat Bekleme & 15 Dakikalık Okumalar")
            )
            if prof_calc.get("passed") is not None and form_code == "strength":
                items.append(
                    _mk_finding(
                        "st_window",
                        "Mukavemet Test Basıncı Penceresi",
                        "passed" if prof_calc["passed"] else "failed",
                        str(prof_calc.get("summary") or ""),
                        "4-NGTL Md. 14.1",
                    )
                )

        elif form_code == "air_acceptance":
            air_raw = ext.get("air_acceptance") or {}
            if air_calc.get("passed") is not None:
                items.append(
                    _mk_finding(
                        "air_limit",
                        "Hava İçerik Kabul Kriteri ((VpA/Vp) − 1 ≤ 0,06)",
                        "passed" if air_calc["passed"] else "failed",
                        str(air_calc.get("summary") or ""),
                        "4-NGTL Md. 13 / 8.4.2",
                        expected="Oran ≤ 1,060 (%6)",
                        actual=f"{air_calc.get('ratio')} (%{air_calc.get('excess_pct')})",
                    )
                )
            else:
                items.append(
                    _mk_finding(
                        "air_incomplete",
                        "Hava İçerik Hesap Girdileri Eksik",
                        "warning",
                        "Vp / VpA / A katsayısı veya geometri girdilerinden biri eksik olduğu için doğrulama yapılamadı.",
                        "4-NGTL Md. 13",
                    )
                )
            rep_vp = _finite(air_raw.get("vp_m3"))
            calc_vp = _finite(air_calc.get("vp_m3"))
            if air_calc.get("vp_source") == "program" and rep_vp and calc_vp and calc_vp > 0:
                vp_dev = abs(rep_vp - calc_vp) / calc_vp * 100.0
                items.append(
                    _mk_finding(
                        "air_vp_match",
                        "Rapordaki Vp ile Program Hesabı Karşılaştırması",
                        "passed" if vp_dev <= 2.5 else "warning",
                        f"Raporda Vp={rep_vp:.5f} m³, program hesabı Vp={calc_vp:.5f} m³ (sapma %{vp_dev:.2f}).",
                        "BOT-FRM-020 Çapraz Kontrol",
                        expected=f"{calc_vp:.5f} m³",
                        actual=f"{rep_vp:.5f} m³",
                    )
                )
            rep_a = _finite(air_raw.get("a_micro_per_bar"))
            calc_a = _finite(air_calc.get("a_micro_per_bar"))
            if (
                air_calc.get("a_source") == "program"
                and rep_a is not None
                and calc_a is not None
                and calc_a > 0
            ):
                a_dev = abs(rep_a - calc_a) / calc_a * 100.0
                items.append(
                    _mk_finding(
                        "air_a_match",
                        "Rapordaki A Katsayısı ile Program Hesabı Karşılaştırması",
                        "passed" if a_dev <= 2.0 else "warning",
                        f"Raporda A={rep_a:.3f}, program hesabı A={calc_a:.3f} ×10⁻⁶/bar (sapma %{a_dev:.2f}).",
                        "BOT-FRM-020 Çapraz Kontrol",
                        expected=f"{calc_a:.3f}",
                        actual=f"{rep_a:.3f}",
                    )
                )
            rep_vt = _finite(air_raw.get("vt_m3"))
            calc_vt = _finite(air_calc.get("vt_m3"))
            if rep_vt is not None and calc_vt is not None and calc_vt > 0:
                vt_dev = abs(rep_vt - calc_vt) / calc_vt * 100.0
                items.append(
                    _mk_finding(
                        "air_vt_match",
                        "Rapordaki Vt Hacmi ile Geometri Hesabı Karşılaştırması",
                        "passed" if vt_dev <= 1.0 else "warning",
                        f"Raporda Vt={rep_vt:.2f} m³, program hesabı Vt={calc_vt:.2f} m³ (sapma %{vt_dev:.2f}).",
                        "BOT-FRM-020 Geometri Kontrolü",
                        expected=f"{calc_vt:.2f} m³",
                        actual=f"{rep_vt:.2f} m³",
                    )
                )

        elif form_code == "pressure_test":
            items.append(
                _from_check(
                    "pressure_records", "pt_24h", "24 Saatlik Basınç & Sıcaklık Kayıt Sürekliliği"
                )
            )
            items.append(_from_check("temp_probes", "pt_probes", "Toprak & Boru Prob Okumaları"))
            mon = ext.get("monitoring") or {}
            p0, p1 = _finite(mon.get("p_start_bar")), _finite(mon.get("p_end_bar"))
            pa_022 = _finite(pres_calc.get("pa_bar"))
            if p0 is not None and p1 is not None and pa_022 is not None:
                obs_pa = p0 - p1
                ok_pa = abs(obs_pa - pa_022) <= 0.15
                items.append(
                    _mk_finding(
                        "pt_vs_022",
                        "021 Basınç Farkı ile 022 PA Tutarı",
                        "passed" if ok_pa else "warning",
                        f"021 tablosu ΔP={obs_pa:+.3f} bar (P={p0:.2f}→{p1:.2f}), 022 Kabul formunda PA={pa_022:+.3f} bar.",
                        "BOT-FRM-021 / 022 Çapraz Kontrol",
                        expected=f"{pa_022:+.3f} bar",
                        actual=f"{obs_pa:+.3f} bar",
                    )
                )

        elif form_code == "pressure_acceptance":
            if pres_calc.get("passed") is not None:
                items.append(
                    _mk_finding(
                        "pa_limit",
                        "İzin Verilebilir Basınç Farkı (PA − ΔP ≤ 0,30 bar)",
                        "passed" if pres_calc["passed"] else "failed",
                        str(pres_calc.get("summary") or ""),
                        "4-NGTL Md. 15",
                        expected=f"≤ {PRESSURE_VARIATION_ACCEPTANCE_BAR:.2f} bar",
                        actual=f"{pres_calc.get('margin_bar'):+.3f} bar",
                    )
                )
            else:
                items.append(
                    _mk_finding(
                        "pa_incomplete",
                        "Basınç Değişim Girdileri Eksik",
                        "warning",
                        "PA, ΔT, A, B veya boru geometrisi eksik olduğu için program doğrulaması yapılamadı.",
                        "4-NGTL Md. 15",
                    )
                )
            pr_raw = ext.get("pressure_acceptance") or {}
            rep_pt = _finite(pr_raw.get("pt_bar"))
            calc_pt = _finite(pres_calc.get("pt_bar"))
            if pres_calc.get("pt_source") == "program" and rep_pt is not None and calc_pt is not None:
                ok_pt = abs(rep_pt - calc_pt) <= 0.05
                items.append(
                    _mk_finding(
                        "pa_pt_match",
                        "Rapordaki ΔP (PT) ile Program Hesabı Karşılaştırması",
                        "passed" if ok_pt else "warning",
                        f"Raporda PT={rep_pt:+.3f} bar, program hesabı PT={calc_pt:+.3f} bar (fark {abs(rep_pt - calc_pt):.3f} bar).",
                        "BOT-FRM-022 Formül Doğrulaması",
                        expected=f"{calc_pt:+.3f} bar",
                        actual=f"{rep_pt:+.3f} bar",
                    )
                )
            rep_a = _finite(pr_raw.get("a_micro_per_bar"))
            calc_a = _finite(pres_calc.get("a_micro_per_bar"))
            if (
                pres_calc.get("coeff_source") == "program"
                and rep_a is not None
                and calc_a is not None
                and calc_a > 0
            ):
                a_dev = abs(rep_a - calc_a) / calc_a * 100.0
                items.append(
                    _mk_finding(
                        "pa_a_match",
                        "Rapordaki A Katsayısı ile Program Hesabı Karşılaştırması",
                        "passed" if a_dev <= 2.0 else "warning",
                        f"Raporda A={rep_a:.3f}, program hesabı A={calc_a:.3f} ×10⁻⁶/bar (sapma %{a_dev:.2f}).",
                        "BOT-FRM-022 Çapraz Kontrol",
                        expected=f"{calc_a:.3f}",
                        actual=f"{rep_a:.3f}",
                    )
                )
            rep_b = _finite(pr_raw.get("b_micro_per_c"))
            calc_b = _finite(pres_calc.get("b_micro_per_c"))
            if (
                pres_calc.get("coeff_source") == "program"
                and rep_b is not None
                and calc_b is not None
            ):
                b_tol = max(5.0, abs(calc_b) * 0.05)
                ok_b = abs(rep_b - calc_b) <= b_tol
                items.append(
                    _mk_finding(
                        "pa_b_match",
                        "Rapordaki B Katsayısı ile Program Hesabı Karşılaştırması",
                        "passed" if ok_b else "warning",
                        f"Raporda B={rep_b:.2f}, program hesabı B={calc_b:.2f} ×10⁻⁶/K (fark {abs(rep_b - calc_b):.2f}).",
                        "BOT-FRM-022 Çapraz Kontrol",
                        expected=f"{calc_b:.2f}",
                        actual=f"{rep_b:.2f}",
                    )
                )

        elif form_code == "dewatering":
            items.append(
                _from_check(
                    "depressurize_discharge", "dw_run", "Basınç Düşürme & Boşaltma Pig Kontrolü"
                )
            )
            if pig_calc.get("passed") is not None:
                items.append(
                    _mk_finding(
                        "dw_speed",
                        "Boşaltma Pig Hızı Kontrolü",
                        "passed" if pig_calc["passed"] else "failed",
                        str(pig_calc.get("summary") or ""),
                        "4-NGTL Md. 9 / 16-17",
                    )
                )
            ops_eval = evaluate_dewatering_operations(
                str(entry.get("form_date") or ext.get("form_date") or ""),
                ext,
            )
            dep_eval = ops_eval.get("depressurization")
            if dep_eval is not None:
                items.append(
                    _mk_finding(
                        "dw_depressurization",
                        "Basınç Düşürme Kontrolü (Md. 16)",
                        str(dep_eval["status"]),
                        str(dep_eval["message"]),
                        "4-NGTL Md. 16",
                        expected='Test başarılı, vana ≤ 2", önlemler onaylı',
                    )
                )
            dis_eval = ops_eval.get("discharge")
            if dis_eval is not None:
                items.append(
                    _mk_finding(
                        "dw_discharge",
                        "Boşaltma & Raporlama Kontrolü (Md. 17)",
                        str(dis_eval["status"]),
                        str(dis_eval["message"]),
                        "4-NGTL Md. 17 / BOT-FRM-CDB-001-024",
                        expected="Pig, 17.1–17.5 önlem/onay ve 17.6 raporu tam",
                    )
                )

        elif form_code in {"pre_drying", "final_drying"}:
            dry = ext.get("drying") or {}
            dew = _finite(dry.get("measured_dew_point_c"))
            target = _finite(dry.get("target_dew_point_c")) or DEFAULT_TARGET_DEW_POINT_C
            if dew is not None:
                ok_dew = dew <= target + 1e-6
                items.append(
                    _mk_finding(
                        "dry_dew_point",
                        "Çiğlenme Noktası (Dew Point) Kontrolü",
                        "passed" if ok_dew else "failed",
                        (
                            f"Ölçülen çiğlenme noktası {dew:.1f} °C ≤ {target:.1f} °C hedefini sağlıyor."
                            if ok_dew
                            else f"Ölçülen çiğlenme noktası {dew:.1f} °C > {target:.1f} °C sınırının üzerinde!"
                        ),
                        "4-NGTL Md. 18",
                        expected=f"≤ {target:.1f} °C",
                        actual=f"{dew:.1f} °C",
                    )
                )
            elif form_code == "final_drying":
                items.append(
                    _mk_finding(
                        "dry_dew_missing",
                        "Nihai Kurutma Dew Point Değeri Eksik",
                        "warning",
                        "Nihai kurutma formunda ölçülen çiğlenme noktası (-20 °C hedefi) belirtilmemiş.",
                        "4-NGTL Md. 18",
                    )
                )
            else:
                items.append(
                    _mk_finding(
                        "dry_pre_ok",
                        "Ön Kurutma Süreci Kaydedildi",
                        "info",
                        "Ön kurutma kabul dokümanı bölüm kaydına işlendi; çiğlenme noktası hedefi Nihai Kurutma (KUR-002) formunda doğrulanır.",
                        "4-NGTL Md. 18",
                    )
                )

        else:
            if form_code == "calculation_sheet" and prof_calc.get("passed") is not None:
                items.append(
                    _mk_finding(
                        "calc_profile",
                        "Hesap Tablosu Basınç Penceresi Doğrulaması",
                        "passed" if prof_calc["passed"] else "failed",
                        str(prof_calc.get("summary") or ""),
                        "BOT-FRM-001-027",
                    )
                )
            else:
                items.append(
                    _mk_finding(
                        f"{form_code}_recorded",
                        "Doküman Kaydı Doğrulandı",
                        "info",
                        "Ek doküman veritabanına kaydedildi ve ilgili test bölümüyle ilişkilendirildi.",
                        entry.get("botas_code") or "Ek Doküman",
                    )
                )

        if not items:
            items.append(
                _mk_finding(
                    f"{form_code}_filled",
                    "Form Verileri Kaydedildi",
                    "info",
                    "Form veritabanında kayıtlı.",
                    entry.get("botas_code") or form_code,
                )
            )
        findings_by_code[form_code] = items

    return findings_by_code


def compute_extended_summary(
    forms: Sequence[Any],
    *,
    calculations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build backward-compatible section form summary enriched with finding counts & key metrics."""
    required_rows = [f for f in forms if getattr(f, "required", False)]
    filled_req = 0
    passed_req = 0
    warning_forms: list[str] = []
    failed_forms: list[str] = []
    missing_titles: list[str] = []
    first_issue_code: str | None = None
    findings_counts = {"passed": 0, "warning": 0, "failed": 0}

    ordered = sorted(forms, key=lambda item: getattr(item, "form_code", ""))
    for f in ordered:
        ext = getattr(f, "extracted_data", None) or {}
        f_list = ext.get("findings") if isinstance(ext, dict) else None
        if isinstance(f_list, list):
            for fd in f_list:
                st = str((fd or {}).get("status") or "")
                if st in findings_counts:
                    findings_counts[st] += 1

    for row in required_rows:
        st = getattr(row, "status", "empty")
        title = getattr(row, "form_title", "")
        code = getattr(row, "form_code", "")
        if st != "empty":
            filled_req += 1
            if st == "passed":
                passed_req += 1
            elif st == "warning":
                warning_forms.append(title)
                if first_issue_code is None:
                    first_issue_code = code
            elif st == "failed":
                failed_forms.append(title)
                first_issue_code = code if first_issue_code is None else first_issue_code
        else:
            missing_titles.append(title)

    supp_filled = sum(
        1
        for f in forms
        if not getattr(f, "required", True) and getattr(f, "status", "empty") != "empty"
    )
    req_total = max(11, len(required_rows))

    calcs = calculations or {}
    air_c = calcs.get("air") or {}
    pres_c = calcs.get("pressure") or {}
    key_metrics: dict[str, Any] = {
        "air_excess_pct": air_c.get("excess_pct"),
        "air_passed": air_c.get("passed"),
        "pa_minus_pt_bar": pres_c.get("margin_bar"),
        "pressure_passed": pres_c.get("passed"),
    }
    for row in forms:
        code = getattr(row, "form_code", "")
        ext = getattr(row, "extracted_data", None) or {}
        if code == "leak_stabilization":
            key_metrics["thermal_delta_c"] = (ext.get("monitoring") or {}).get("last_4h_delta_c")
        elif code == "filling":
            key_metrics["filled_volume_m3"] = (ext.get("filling") or {}).get("total_filled_m3")
        elif code == "final_drying":
            key_metrics["dew_point_c"] = (ext.get("drying") or {}).get("measured_dew_point_c")

    return {
        "required_total": req_total,
        "filled_required": filled_req,
        "missing_required": len(missing_titles),
        "missing_titles": missing_titles,
        "supplementary_filled": supp_filled,
        "failed_forms": failed_forms,
        "warning_forms": warning_forms,
        "passed_forms_count": passed_req,
        "warning_forms_count": len(warning_forms),
        "findings_counts": findings_counts,
        "first_issue_form_code": first_issue_code,
        "key_metrics": key_metrics,
        "complete": filled_req == req_total and not failed_forms,
    }


__all__ = [
    "DEFAULT_TARGET_DEW_POINT_C",
    "MAX_TABLE_ROWS",
    "build_effective_dewatering_payloads",
    "build_form_structured_payload",
    "compute_extended_summary",
    "evaluate_all_form_findings",
    "evaluate_dewatering_operations",
    "extract_common_header_extras",
    "monitoring_rows_to_time_series",
    "parse_base_date",
    "reconcile_form_extracted_data",
    "time_series_to_monitoring_rows",
]

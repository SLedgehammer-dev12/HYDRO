"""Plan-Profil (Alignment Sheet) PDF tarayici ve taslak kesit (section) uretici."""

from __future__ import annotations

import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any, BinaryIO

from sqlalchemy.orm import Session as OrmSession

from hidrostatik_test.services.report_ocr import (
    MAX_FILE_SIZE_BYTES,
    SUPPORTED_EXTENSIONS,
    ReportOcrError,
    extract_text,
)

from ..core.errors import AppError
from . import projects as project_service
from . import sessions as session_service

# Chainage: "0+000", "12+345", "12+345,5"
_CHAINAGE_RE = re.compile(r"\b(\d{1,3})\s*\+\s*(\d{3}(?:[.,]\d+)?)\b")

# Açık kesit satırı: "K-01 ... 0+000 ... 12+000" veya "Kesit 1: KP 0+000 - KP 12+000"
_EXPLICIT_SECTION_RE = re.compile(
    r"(?:(?:kesit|section|paket|b[oö]l[uü]m)\s*[:#-]?\s*([A-Za-z0-9_-]{1,16})|\b(K-\d{1,3}|S-\d{1,3})\b)"
    r"[^\n\r]{0,60}?"
    r"(\d{1,3}\s*\+\s*\d{3}(?:[.,]\d+)?)"
    r"\s*(?:--|–|—|-|→|to|ile|/)\s*(?:KP\s*)?"
    r"(\d{1,3}\s*\+\s*\d{3}(?:[.,]\d+)?)",
    re.IGNORECASE,
)

# KP aralığı ("KP 0+000 - KP 12+000")
_KP_RANGE_RE = re.compile(
    r"(?:KP\s*)?(\d{1,3}\s*\+\s*\d{3}(?:[.,]\d+)?)"
    r"\s*(?:--|–|—|-|→|to)\s*(?:KP\s*)?"
    r"(\d{1,3}\s*\+\s*\d{3}(?:[.,]\d+)?)",
    re.IGNORECASE,
)

# Aynı satırda KP + Kot eşleşmesi:
# Ör: "KP 0+000   Kot: 215.4 m" veya "0+500   EL. 240,5" veya "0+000 | 210.0"
_STATION_ELEV_RE = re.compile(
    r"(?:KP\s*)?(\d{1,3}\s*\+\s*\d{3}(?:[.,]\d+)?)"
    r"(?:[^\n\r\d+-]{1,35}?(?:kot|el\.?|elev(?:ation)?|rak[ıi]m|zemin)\s*[:=]?\s*|\s{2,}|\s*[|;]\s*)"
    r"(-?\d{1,4}(?:[.,]\d+)?)\s*(?:m\b)?",
    re.IGNORECASE,
)

_OD_RE = re.compile(
    r"(?:d[ıi][sş]\s*[cç]ap|outside\s*diameter|\bOD\b)\s*[:=]?\s*(\d{2,4}(?:[.,]\d+)?)\s*(?:mm)?",
    re.IGNORECASE,
)
_WT_RE = re.compile(
    r"(?:et\s*kal[ıi]nl[ıi][gğ][ıi]|wall\s*thickness|\bWT\b)\s*[:=]?\s*(\d{1,2}(?:[.,]\d+)?)\s*(?:mm)?",
    re.IGNORECASE,
)
_DESIGN_P_RE = re.compile(
    r"(?:dizayn\s*bas[ıi]nc[ıi]|tasar[ıi]m\s*bas[ıi]nc[ıi]|design\s*pressure|\bDP\b)\s*[:=]?\s*(\d{1,3}(?:[.,]\d+)?)\s*(?:bar)?",
    re.IGNORECASE,
)
_GRADE_RE = re.compile(r"\b(X\d{2}|L\d{3})\b", re.IGNORECASE)

_GRADE_SMYS_MAP: dict[str, tuple[str, float]] = {
    "X42": ("API 5L PSL2 X42 / L290 - SMYS 290 MPa", 290.0),
    "L290": ("API 5L PSL2 X42 / L290 - SMYS 290 MPa", 290.0),
    "X52": ("API 5L PSL2 X52 / L360 - SMYS 360 MPa", 360.0),
    "L360": ("API 5L PSL2 X52 / L360 - SMYS 360 MPa", 360.0),
    "X60": ("API 5L PSL2 X60 / L415 - SMYS 415 MPa", 415.0),
    "L415": ("API 5L PSL2 X60 / L415 - SMYS 415 MPa", 415.0),
    "X65": ("API 5L PSL2 X65 / L450 - SMYS 450 MPa", 450.0),
    "L450": ("API 5L PSL2 X65 / L450 - SMYS 450 MPa", 450.0),
    "X70": ("API 5L PSL2 X70 / L485 - SMYS 485 MPa", 485.0),
    "L485": ("API 5L PSL2 X70 / L485 - SMYS 485 MPa", 485.0),
    "X80": ("API 5L PSL2 X80 / L555 - SMYS 555 MPa", 555.0),
    "L555": ("API 5L PSL2 X80 / L555 - SMYS 555 MPa", 555.0),
}


def parse_kp_meters(raw: str | float | int | None) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if math.isfinite(raw) and raw >= 0 else None
    text = str(raw).strip()
    text = re.sub(r"^kp\s*[:=-]?\s*", "", text, flags=re.IGNORECASE).strip()
    if not text:
        return None
    m = re.match(r"^(\d+)\s*\+\s*(\d+(?:[.,]\d+)?)$", text)
    if m:
        km = float(m.group(1))
        meters = float(m.group(2).replace(",", "."))
        return km * 1000.0 + meters
    m_km = re.match(r"^(\d+(?:[.,]\d+)?)\s*km$", text, flags=re.IGNORECASE)
    if m_km:
        return float(m_km.group(1).replace(",", ".")) * 1000.0
    m_num = re.match(r"^(\d+(?:[.,]\d+)?)\s*m?$", text, flags=re.IGNORECASE)
    if m_num:
        return float(m_num.group(1).replace(",", "."))
    return None


def format_kp(meters: float | None) -> str:
    if meters is None or not math.isfinite(meters) or meters < 0:
        return ""
    rounded = round(float(meters), 1)
    km = int(rounded // 1000)
    rem = rounded - km * 1000
    whole = int(rem)
    frac = int(round((rem - whole) * 10))
    if frac > 0:
        return f"{km}+{whole:03d},{frac}"
    return f"{km}+{whole:03d}"


def _parse_float(raw: str | None) -> float | None:
    if not raw:
        return None
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None


def _interpolate_elevation(
    points: list[tuple[float, float]], station_m: float
) -> float | None:
    if not points:
        return None
    if station_m <= points[0][0]:
        return round(points[0][1], 1)
    if station_m >= points[-1][0]:
        return round(points[-1][1], 1)
    for idx in range(len(points) - 1):
        s0, e0 = points[idx]
        s1, e1 = points[idx + 1]
        if s0 <= station_m <= s1:
            if abs(s1 - s0) < 1e-6:
                return round(e0, 1)
            ratio = (station_m - s0) / (s1 - s0)
            return round(e0 + ratio * (e1 - e0), 1)
    return round(points[-1][1], 1)


def _elevations_for_span(
    points: list[tuple[float, float]], start_m: float, end_m: float
) -> dict[str, float | None]:
    if not points:
        return {
            "start_elevation_m": None,
            "end_elevation_m": None,
            "highest_elevation_m": None,
            "lowest_elevation_m": None,
        }
    start_el = _interpolate_elevation(points, start_m)
    end_el = _interpolate_elevation(points, end_m)
    in_span = [el for st, el in points if start_m <= st <= end_m]
    candidates = [v for v in ([start_el, end_el] + in_span) if v is not None]
    if not candidates:
        return {
            "start_elevation_m": None,
            "end_elevation_m": None,
            "highest_elevation_m": None,
            "lowest_elevation_m": None,
        }
    return {
        "start_elevation_m": start_el,
        "end_elevation_m": end_el,
        "highest_elevation_m": round(max(candidates), 1),
        "lowest_elevation_m": round(min(candidates), 1),
    }


def parse_plan_profile_text(
    text: str,
    *,
    max_section_length_m: float = 12_000.0,
    max_elevation_diff_m: float | None = None,
) -> dict[str, Any]:
    """Plan-profil metninden KP istasyonlarını, kotları ve taslak kesitleri üretir."""
    max_len = max(500.0, min(float(max_section_length_m or 12_000.0), 20_000.0))
    max_elev_diff = (
        float(max_elevation_diff_m)
        if max_elevation_diff_m is not None and max_elevation_diff_m > 0
        else None
    )

    # 1) Boru hattı üst verileri (varsa)
    od_match = _OD_RE.search(text)
    wt_match = _WT_RE.search(text)
    dp_match = _DESIGN_P_RE.search(text)
    grade_match = _GRADE_RE.search(text)

    outside_diameter_mm = _parse_float(od_match.group(1)) if od_match else None
    wall_thickness_mm = _parse_float(wt_match.group(1)) if wt_match else None
    design_pressure_bar = _parse_float(dp_match.group(1)) if dp_match else None
    material_grade = ""
    smys_mpa: float | None = None
    if grade_match:
        key = grade_match.group(1).upper()
        if key in _GRADE_SMYS_MAP:
            material_grade, smys_mpa = _GRADE_SMYS_MAP[key]

    # 2) İstasyon + Kot noktaları
    station_elev_map: dict[float, float] = {}
    for m in _STATION_ELEV_RE.finditer(text):
        kp_m = parse_kp_meters(m.group(1))
        elev = _parse_float(m.group(2))
        if kp_m is not None and elev is not None and -200.0 <= elev <= 5000.0:
            station_elev_map[round(kp_m, 1)] = elev

    profile_points = sorted(station_elev_map.items(), key=lambda item: item[0])

    # 3) Tüm KP istasyonları
    all_stations: set[float] = {st for st, _ in profile_points}
    for m in _CHAINAGE_RE.finditer(text):
        kp_m = parse_kp_meters(f"{m.group(1)}+{m.group(2)}")
        if kp_m is not None:
            all_stations.add(round(kp_m, 1))

    sorted_stations = sorted(all_stations)

    # 4) Açıkça yazılmış kesitler var mı?
    explicit_sections: list[tuple[str, float, float]] = []
    seen_spans: set[tuple[float, float]] = set()
    for m in _EXPLICIT_SECTION_RE.finditer(text):
        raw_no = (m.group(1) or m.group(2) or "").strip()
        s_m = parse_kp_meters(m.group(3))
        e_m = parse_kp_meters(m.group(4))
        if s_m is not None and e_m is not None and e_m > s_m:
            span = (round(s_m, 1), round(e_m, 1))
            if span not in seen_spans:
                seen_spans.add(span)
                explicit_sections.append((raw_no, span[0], span[1]))

    # Eğer açık kesit etiketi yoksa ama birden fazla "KP X+XXX - Y+YYY" pafta/aralık satırı varsa
    if not explicit_sections:
        range_spans: list[tuple[float, float]] = []
        for m in _KP_RANGE_RE.finditer(text):
            s_m = parse_kp_meters(m.group(1))
            e_m = parse_kp_meters(m.group(2))
            if s_m is not None and e_m is not None and e_m > s_m:
                span = (round(s_m, 1), round(e_m, 1))
                if span not in seen_spans:
                    seen_spans.add(span)
                    range_spans.append(span)
        range_spans.sort(key=lambda item: item[0])
        # Yalnızca ardışık kesit aralıkları (veya hedef boya uygun aralıklar) ise doğrudan kullan
        if len(range_spans) >= 2 and all(
            (e - s) <= max_len * 1.05 for s, e in range_spans
        ):
            for idx, (s_m, e_m) in enumerate(range_spans, start=1):
                explicit_sections.append((f"K-{idx:02d}", s_m, e_m))

    warnings: list[str] = []
    strategy = "explicit"

    # 5) Taslak kesit sınırlarının belirlenmesi
    spans: list[tuple[str, float, float]] = []
    if explicit_sections:
        explicit_sections.sort(key=lambda item: item[1])
        for idx, (raw_no, s_m, e_m) in enumerate(explicit_sections, start=1):
            # Eğer tek bir açık kesit tüm hattı kapsıyorsa ve max_len'den uzunsa, alt kesitlere böl
            if len(explicit_sections) == 1 and (e_m - s_m) > max_len:
                strategy = "auto_split"
                break
            sec_no = (
                raw_no.upper()
                if raw_no.upper().startswith(("K-", "S-"))
                else f"K-{idx:02d}"
            )
            spans.append((sec_no, s_m, e_m))

    if not spans:
        strategy = "auto_split"
        if len(sorted_stations) >= 2:
            min_kp = sorted_stations[0]
            max_kp = sorted_stations[-1]
        else:
            min_kp = 0.0
            max_kp = max_len
            warnings.append(
                "PDF içinde standart KP (ör. 0+000) istasyonu bulunamadı; varsayılan taslak aralık üretildi."
            )

        cursor = min_kp
        sec_idx = 1
        while cursor < max_kp - 0.5:
            target_end = min(cursor + max_len, max_kp)

            # Kot farkı sınırı verilmişse ve bu aralıkta kot farkı sınırı aşıyorsa daha erken kes
            if max_elev_diff is not None and profile_points:
                in_window = [
                    (st, el)
                    for st, el in profile_points
                    if cursor < st <= target_end
                ]
                running_min = _interpolate_elevation(profile_points, cursor)
                running_max = running_min
                for st, el in in_window:
                    running_min = el if running_min is None else min(running_min, el)
                    running_max = el if running_max is None else max(running_max, el)
                    if (
                        running_min is not None
                        and running_max is not None
                        and (running_max - running_min) > max_elev_diff
                        and (st - cursor) >= 1000.0
                    ):
                        target_end = st
                        break

            # Kalan kuyruk çok kısaysa (< %15 max_len) ve toplam 20.000 m'yi aşmıyorsa birleştir
            remaining = max_kp - target_end
            if 0 < remaining < max_len * 0.15 and (max_kp - cursor) <= 20_000.0:
                target_end = max_kp

            spans.append((f"K-{sec_idx:02d}", round(cursor, 1), round(target_end, 1)))
            cursor = target_end
            sec_idx += 1

    # 6) Taslak kesit nesnelerini ve ardışık KP süreklilik kontrolünü oluştur
    draft_sections: list[dict[str, Any]] = []
    continuity_issues: list[str] = []

    for idx, (sec_no, s_m, e_m) in enumerate(spans):
        elevs = _elevations_for_span(profile_points, s_m, e_m)
        start_kp_str = format_kp(s_m)
        end_kp_str = format_kp(e_m)
        length_m = round(e_m - s_m, 2)

        prev_end_kp: str | None = None
        continuity_ok = True
        continuity_note = "Başlangıç kesiti"
        if idx > 0:
            prev_s = draft_sections[idx - 1]
            prev_end_m = float(prev_s["end_m"])
            prev_end_kp = str(prev_s["end_kp"])
            delta_m = round(s_m - prev_end_m, 1)
            if abs(delta_m) <= 0.5:
                continuity_ok = True
                continuity_note = f"Önceki kesit ({prev_s['section_no']}) bitiş KP ({prev_end_kp}) ile tam eşleşiyor."
            else:
                continuity_ok = False
                kind = f"+{int(abs(delta_m))} m boşluk" if delta_m > 0 else f"{int(abs(delta_m))} m bindirme"
                continuity_note = (
                    f"{prev_s['section_no']} bitiş KP ({prev_end_kp}) ile "
                    f"{sec_no} başlangıç KP ({start_kp_str}) eşleşmiyor ({kind})."
                )
                continuity_issues.append(continuity_note)

        draft_sections.append(
            {
                "section_no": sec_no,
                "start_kp": start_kp_str,
                "end_kp": end_kp_str,
                "start_m": s_m,
                "end_m": e_m,
                "length_m": length_m,
                "description": f"Plan-Profil Taslak Kesit {sec_no} (KP {start_kp_str} – {end_kp_str})",
                "start_elevation_m": elevs["start_elevation_m"],
                "end_elevation_m": elevs["end_elevation_m"],
                "highest_elevation_m": elevs["highest_elevation_m"],
                "lowest_elevation_m": elevs["lowest_elevation_m"],
                "outside_diameter_mm": outside_diameter_mm,
                "wall_thickness_mm": wall_thickness_mm,
                "design_pressure_bar": design_pressure_bar,
                "material_grade": material_grade,
                "smys_mpa": smys_mpa,
                "prev_end_kp": prev_end_kp,
                "continuity_ok": continuity_ok,
                "continuity_note": continuity_note,
            }
        )

    return {
        "strategy": strategy,
        "station_count": len(sorted_stations),
        "elevation_point_count": len(profile_points),
        "min_kp": format_kp(sorted_stations[0]) if sorted_stations else "0+000",
        "max_kp": format_kp(sorted_stations[-1]) if sorted_stations else format_kp(max_len),
        "total_length_m": (
            round(sorted_stations[-1] - sorted_stations[0], 2)
            if len(sorted_stations) >= 2
            else round(sum(item["length_m"] for item in draft_sections), 2)
        ),
        "pipe_meta": {
            "outside_diameter_mm": outside_diameter_mm,
            "wall_thickness_mm": wall_thickness_mm,
            "design_pressure_bar": design_pressure_bar,
            "material_grade": material_grade,
            "smys_mpa": smys_mpa,
        },
        "profile_points": [
            {"kp": format_kp(st), "station_m": st, "elevation_m": el}
            for st, el in profile_points[:200]
        ],
        "draft_sections": draft_sections,
        "continuity_ok": len(continuity_issues) == 0,
        "continuity_issues": continuity_issues,
        "warnings": warnings,
    }


def scan_plan_profile_upload(
    *,
    file_name: str | None,
    stream: BinaryIO,
    max_section_length_m: float = 12_000.0,
    max_elevation_diff_m: float | None = None,
    language: str | None = None,
) -> dict[str, Any]:
    """Yüklenen Plan-Profil PDF/görsel dosyasını okur ve taslak kesitleri üretir."""
    safe_name = os.path.basename(file_name or "plan_profile.pdf")
    ext = Path(safe_name).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise AppError(
            f"Desteklenmeyen dosya uzantısı: {ext or 'yok'}. PDF veya görsel yükleyin.",
            code="unsupported_format",
            status=415,
        )

    data = stream.read(MAX_FILE_SIZE_BYTES + 1)
    if not data:
        raise AppError("Yüklenen dosya boş.", code="empty_file", status=422)
    if len(data) > MAX_FILE_SIZE_BYTES:
        raise AppError(
            "Dosya boyutu izin verilen sınırı aşıyor.",
            code="file_too_large",
            status=413,
        )

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    try:
        try:
            pages = extract_text(tmp_path)
        except ReportOcrError as exc:
            raise AppError(str(exc), code=exc.code, status=422) from exc
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    full_text = "\n".join(page.text for page in pages)
    parsed = parse_plan_profile_text(
        full_text,
        max_section_length_m=max_section_length_m,
        max_elevation_diff_m=max_elevation_diff_m,
    )
    parsed["file_name"] = safe_name
    parsed["page_count"] = len(pages)
    parsed["extraction_method"] = pages[0].source if pages else "pdf-text-layer"
    return parsed


def create_sections_from_drafts(
    db: OrmSession,
    *,
    workspace_hash: str,
    project_id: str,
    drafts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Onaylanan taslak kesitleri seçili proje altında veritabanına kaydeder."""
    project = project_service.get_project(db, project_id, workspace_hash)
    created_items: list[dict[str, Any]] = []

    for idx, draft in enumerate(drafts, start=1):
        sec_no = str(draft.get("section_no") or f"K-{idx:02d}").strip()
        start_m = parse_kp_meters(draft.get("start_kp"))
        end_m = parse_kp_meters(draft.get("end_kp"))
        start_kp = format_kp(start_m) if start_m is not None else str(draft.get("start_kp") or "").strip()
        end_kp = format_kp(end_m) if end_m is not None else str(draft.get("end_kp") or "").strip()

        if start_m is not None and end_m is not None and end_m <= start_m:
            raise AppError(
                f"{sec_no}: Bitiş KP ({end_kp}), başlangıç KP ({start_kp}) değerinden büyük olmalıdır.",
                code="validation_error",
                status=422,
            )

        length_m = (
            round(end_m - start_m, 2)
            if start_m is not None and end_m is not None
            else _parse_float(str(draft.get("length_m") or "")) or 12_000.0
        )

        description = (
            str(draft.get("description") or "").strip()
            or f"{project.name} · {sec_no}"
        )
        location = (
            f"KP {start_kp} – {end_kp}"
            if start_kp and end_kp
            else str(draft.get("location") or "")
        )

        inputs = session_service.default_inputs()
        inputs["section_meta"] = {
            "section_no": sec_no,
            "description": description,
            "location": location,
            "start_kp": start_kp,
            "end_kp": end_kp,
            "test_date": str(draft.get("test_date") or ""),
            "test_type": "Hidrostatik test",
            "notes": str(draft.get("notes") or "Plan-profil PDF taramasıyla oluşturuldu."),
        }
        inputs["geometry"] = {
            "outside_diameter_mm": draft.get("outside_diameter_mm") or 406.4,
            "wall_thickness_mm": draft.get("wall_thickness_mm") or 8.74,
            "length_m": length_m,
        }
        inputs["section_profile"] = {
            "highest_elevation_m": draft.get("highest_elevation_m"),
            "lowest_elevation_m": draft.get("lowest_elevation_m"),
            "start_elevation_m": draft.get("start_elevation_m"),
            "end_elevation_m": draft.get("end_elevation_m"),
            "design_pressure_bar": draft.get("design_pressure_bar") or 80.0,
            "smys_mpa": draft.get("smys_mpa") or 450.0,
        }
        if draft.get("material_grade"):
            inputs["material_grade"] = str(draft["material_grade"])

        session_name = (
            f"{sec_no} · KP {start_kp}–{end_kp} · {project.code or project.name}"
            if start_kp and end_kp
            else f"{sec_no} · {project.code or project.name}"
        )

        created = session_service.create_session(
            db,
            workspace_hash=workspace_hash,
            name=session_name,
            project_id=project.id,
            inputs=inputs,
        )
        created_items.append(session_service.session_brief(created))

    return {
        "project_id": project.id,
        "created_count": len(created_items),
        "items": created_items,
    }

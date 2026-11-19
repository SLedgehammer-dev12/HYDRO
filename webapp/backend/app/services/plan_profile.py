"""Plan-Profil (Alignment Sheet) PDF tarayici ve taslak kesit (section) uretici."""

from __future__ import annotations

import copy
import importlib.util
import logging
import math
import os
import re
import shutil
import statistics
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, BinaryIO

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from hidrostatik_test.services.report_ocr import (
    SPREADSHEET_EXTENSIONS,
    SUPPORTED_EXTENSIONS,
    ReportOcrError,
    effective_max_file_size_bytes,
    extract_text,
    ocr_pdf_page_rotated,
)

from ..core.errors import AppError
from ..core.timeutil import utcnow
from ..models import HydroSession
from . import dossier as dossier_service
from . import projects as project_service
from . import sessions as session_service

logger = logging.getLogger("hydro.web.plan_profile")

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
_PIPE_SPEC_INCH_RE = re.compile(
    r"(?:[ÖO]L[ÇC][ÜU]LER[İI]|KARATER[İI]ST[İI]K|BORU\s*[ÇC]API)\s*[:=]?\s*"
    r'(4|6|8|10|12|14|16|18|20|22|24|26|28|30|32|34|36|40|42|44|48)\s*(?:"|″|\'\'|\b(?:inch|in[çc])\b)',
    re.IGNORECASE,
)
_INCH_OD_RE = re.compile(
    r"(?<!['′°]\s)(?<!['′°])\b(4|6|8|10|12|14|16|18|20|22|24|26|28|30|32|34|36|40|42|44|48)\s*(?:\"|″|''|\b(?:inch|in[çc])\b)",
    re.IGNORECASE,
)
_INCH_TO_MM: dict[str, float] = {
    "4": 114.3,
    "6": 168.3,
    "8": 219.1,
    "10": 273.1,
    "12": 323.9,
    "14": 355.6,
    "16": 406.4,
    "18": 457.2,
    "20": 508.0,
    "22": 558.8,
    "24": 609.6,
    "26": 660.4,
    "28": 711.2,
    "30": 762.0,
    "32": 812.8,
    "34": 863.6,
    "36": 914.4,
    "40": 1016.0,
    "42": 1066.8,
    "44": 1117.6,
    "48": 1219.2,
}
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

_SINGLE_SECTION_TEXT_RE = re.compile(
    r"(?:(?:TEST\s*)?(?:BOLUM(?:U)?|KESI[MT]|SECTION)\s*(?:NO\.?|NUMARASI)?\s*[:=#-]?\s*([o0-9]{1,3}[a-z]?)\b"
    r"|\b(K-\d{1,3}|S-\d{1,3})\b)",
    re.IGNORECASE,
)
_SINGLE_SECTION_FILENAME_RE = re.compile(
    r"(?:(?:b[oö]l[uü]m|kes[iı][mt]|section)[_\s-]*0*([0-9]{1,3}[A-Za-z]?)(?=$|[^0-9A-Za-z])"
    r"|(?:^|[_\s-])(K-\d{1,3}|S-\d{1,3})(?=$|[_\s-]))",
    re.IGNORECASE,
)


def _normalize_single_section_token(
    num_tok: str | None,
    code_tok: str | None,
) -> str | None:
    if code_tok:
        upper = code_tok.upper()
        if upper.startswith("K-"):
            return dossier_service.normalize_section_no(upper) or upper
        return upper
    if num_tok:
        fixed_num = re.sub(r"[oO](?=\d)|(?<=\d)[oO]", "0", num_tok)
        return dossier_service.normalize_section_no(fixed_num)
    return None


def _extract_single_section_label(
    text: str,
    file_name: str | None = None,
) -> str | None:
    """Tek bölümlü paftadan (metin/antet veya dosya adı) bölüm etiketini çıkarır."""
    folded_text = dossier_service.fold_tr(text or "")
    text_labels: list[str] = []
    seen_text: set[str] = set()
    for match in _SINGLE_SECTION_TEXT_RE.finditer(folded_text):
        label = _normalize_single_section_token(match.group(1), match.group(2))
        if label and label not in seen_text:
            seen_text.add(label)
            text_labels.append(label)
            if len(text_labels) > 1:
                return None
    if len(text_labels) == 1:
        return text_labels[0]

    if file_name:
        stem = Path(file_name).stem
        file_labels: list[str] = []
        seen_file: set[str] = set()
        for match in _SINGLE_SECTION_FILENAME_RE.finditer(stem):
            label = _normalize_single_section_token(match.group(1), match.group(2))
            if label and label not in seen_file:
                seen_file.add(label)
                file_labels.append(label)
                if len(file_labels) > 1:
                    return None
        if len(file_labels) == 1:
            return file_labels[0]
    return None


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


def _interpolate_elevation(points: list[tuple[float, float]], station_m: float) -> float | None:
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


def _extract_pipe_meta(text: str) -> dict[str, Any]:
    """Metinden boru dış çapı, et kalınlığı, tasarım basıncı ve çelik kalitesini çıkarır."""
    od_match = _OD_RE.search(text)
    spec_inch_match = _PIPE_SPEC_INCH_RE.search(text) if not od_match else None
    inch_match = _INCH_OD_RE.search(text) if not od_match and not spec_inch_match else None
    wt_match = _WT_RE.search(text)
    dp_match = _DESIGN_P_RE.search(text)
    grade_match = _GRADE_RE.search(text)

    if od_match:
        outside_diameter_mm = _parse_float(od_match.group(1))
    elif spec_inch_match:
        outside_diameter_mm = _INCH_TO_MM.get(spec_inch_match.group(1))
    elif inch_match:
        outside_diameter_mm = _INCH_TO_MM.get(inch_match.group(1))
    else:
        outside_diameter_mm = None

    wall_thickness_mm = _parse_float(wt_match.group(1)) if wt_match else None
    if wall_thickness_mm is None:
        folded = dossier_service.fold_tr(text or "")
        if any(tok in folded for tok in ("profil", "hidrostatik test", "section", "kesit")):
            wt_weights: dict[float, float] = defaultdict(float)
            lines = text.splitlines()
            for idx, ln in enumerate(lines):
                for m in re.finditer(r"\b(\d{1,2}[.,]\d{1,2})\s*mm\b", ln, re.IGNORECASE):
                    val = _parse_float(m.group(1))
                    if val is None or not (3.0 <= val <= 25.4):
                        continue
                    wt_key = round(val, 2)
                    weight = 100.0
                    # Aynı veya bitişik satırlarda bu kalınlığa ait metre uzunluğu varsa ağırlıklandır
                    window = " ".join(lines[idx : min(len(lines), idx + 3)])
                    len_m = re.search(r"(\d+(?:[.,]\d+)?)\s*m\b", window, re.IGNORECASE)
                    if len_m:
                        parsed_len = _parse_float(len_m.group(1))
                        if parsed_len and parsed_len > 0:
                            weight = parsed_len
                    wt_weights[wt_key] += weight
            if wt_weights:
                wall_thickness_mm = max(wt_weights.items(), key=lambda kv: kv[1])[0]

    design_pressure_bar = _parse_float(dp_match.group(1)) if dp_match else None
    material_grade = ""
    smys_mpa: float | None = None
    if grade_match:
        key = grade_match.group(1).upper()
        if key in _GRADE_SMYS_MAP:
            material_grade, smys_mpa = _GRADE_SMYS_MAP[key]

    return {
        "outside_diameter_mm": outside_diameter_mm,
        "wall_thickness_mm": wall_thickness_mm,
        "design_pressure_bar": design_pressure_bar,
        "material_grade": material_grade,
        "smys_mpa": smys_mpa,
    }


_ACT_CHAINAGE_RE = re.compile(r"(\d{1,3})\s*\+\s*(\d{3}(?:[.,]\d{1,2})?)")


def _extract_activity_profile_elevations(text: str) -> dict[str, float | None]:
    """BOTAŞ Test Aktivitesi Profili etiketlerinden (Hs, He, Hmax, Hmin) kotları çıkarır."""
    folded = dossier_service.fold_tr(text or "")

    def _find_elev(pattern: str) -> float | None:
        for m in re.finditer(pattern, folded):
            raw_num = m.group(1).replace("/", "7").replace(",", ".").rstrip(".")
            try:
                val = float(raw_num)
            except ValueError:
                continue
            if 0.0 <= val <= 5000.0:
                return round(val, 2)
        return None

    hs = _find_elev(r"\b[hi]s\s*[:=.]?\s*(\d{2,4}(?:[.,/][\d/]{0,2})?)")
    he = _find_elev(r"\b[hi]e\s*[:=.]?\s*(\d{2,4}(?:[.,/][\d/]{0,2})?)")
    hmax = _find_elev(r"\bh?max\s*[:=.]?\s*(\d{2,4}(?:[.,/][\d/]{0,2})?)")
    hmin = _find_elev(r"\bh?min\s*[:=.]?\s*(\d{2,4}(?:[.,/][\d/]{0,2})?)")

    for ref in (hs, he):
        if ref is None:
            continue
        if hmin is not None and hmin == float(int(hmin)) and int(hmin) == int(ref):
            hmin = ref
        if hmax is not None and hmax == float(int(hmax)) and int(hmax) == int(ref):
            hmax = ref

    endpoints = [v for v in (hs, he) if v is not None]
    if endpoints:
        if hmax is None:
            hmax = max(endpoints)
        else:
            hmax = max([hmax, *endpoints])
        if hmin is None:
            hmin = min(endpoints)
        else:
            hmin = min([hmin, *endpoints])

    return {
        "start_elevation_m": hs,
        "end_elevation_m": he,
        "highest_elevation_m": hmax,
        "lowest_elevation_m": hmin,
    }


def _extract_activity_profile_kp_span(text: str) -> tuple[float, float] | None:
    """BOTAŞ Aktivite Profilinden YM yerine gerçek EM (eğimli boru) KP aralığını çıkarır."""
    folded = dossier_service.fold_tr(text or "")
    has_activity_markers = any(tok in folded for tok in ("aktivite", "hmax", "hmin", "em:", "ym:"))
    if not has_activity_markers:
        return None

    def _parse_act_kp(raw: str) -> float | None:
        val = parse_kp_meters(raw)
        return round(val, 2) if val is not None else None

    ym_vals: list[float] = []
    for m in re.finditer(
        r"(?:(?<![a-z])(?:ym|tm|sm)|(?<=[\s:;,.|])[/']m)\s*[:=.]?\s*" + _ACT_CHAINAGE_RE.pattern,
        folded,
    ):
        val = _parse_act_kp(f"{m.group(1)}+{m.group(2)}")
        if val is not None:
            ym_vals.append(val)

    em_vals: list[float] = []
    for m in re.finditer(
        r"(?<![yt/'])\b(?:[vt]?em|m)\s*[:=.]?\s*" + _ACT_CHAINAGE_RE.pattern,
        folded,
    ):
        val = _parse_act_kp(f"{m.group(1)}+{m.group(2)}")
        if val is not None:
            em_vals.append(val)

    standalone_vals: list[float] = []
    for ln in folded.splitlines():
        if re.search(r"(?:(?<![a-z])(?:ym|tm|sm)|[/']m)\s*[:=.]", ln):
            continue
        for m in _ACT_CHAINAGE_RE.finditer(ln):
            val = _parse_act_kp(f"{m.group(1)}+{m.group(2)}")
            if val is not None:
                standalone_vals.append(val)

    kp_banner = re.search(
        r"\bk[p]?\s*[:=.]?\s*(\d{1,3}\s*\+\s*\d{3}(?:[.,]\d{1,2})?)\s*"
        r"(?:&|--|–|—|-|to)\s*(?:k[p]?\s*[:=.]?\s*)?(\d{1,3}\s*\+\s*\d{3}(?:[.,]\d{1,2})?)",
        folded,
    )
    if kp_banner:
        bs = _parse_act_kp(kp_banner.group(1))
        be = _parse_act_kp(kp_banner.group(2))
        if bs is not None and be is not None and be > bs:
            # Antette önceki bölümün KP'si kopyalanıp unutulduysa ve tüm EM noktaları be sonrasında ise EM aralığını kullan
            if em_vals and min(em_vals) >= be - 0.5 and max(em_vals) > be + 10.0:
                s_em, e_em = min(em_vals), max(em_vals)
                if e_em > s_em:
                    return (s_em, e_em)
            # Antet başlangıcına yanlışlıkla YM yazıldıysa içteki EM başlangıcını seç
            bs_is_ym = any(abs(bs - yv) <= 1.0 for yv in ym_vals)
            bs_is_em = any(abs(bs - ev) <= 1.0 for ev in em_vals)
            if bs_is_ym and not bs_is_em:
                inner_starts = [ev for ev in em_vals if bs < ev < be]
                if inner_starts:
                    bs = min(inner_starts)
            be_is_ym = any(abs(be - yv) <= 1.0 for yv in ym_vals)
            be_is_em = any(abs(be - ev) <= 1.0 for ev in em_vals)
            if be_is_ym and not be_is_em:
                later_ends = [ev for ev in em_vals if ev > be]
                if later_ends:
                    be = max(later_ends)
            if be > bs:
                return (bs, be)

    cands = sorted(
        set(em_vals) | {v for v in standalone_vals if not any(abs(v - yv) <= 1.0 for yv in ym_vals)}
    )
    if len(cands) >= 2 and cands[-1] > cands[0]:
        return (cands[0], cands[-1])
    return None


def _synthesize_activity_profile_points(
    s_m: float,
    e_m: float,
    elevs: dict[str, float | None],
) -> list[tuple[float, float]]:
    """İstasyon noktası olmayan tek paftada Hs/He/Hmax/Hmin değerlerinden kot profili oluşturur."""
    hs = elevs.get("start_elevation_m")
    he = elevs.get("end_elevation_m")
    hmax = elevs.get("highest_elevation_m")
    hmin = elevs.get("lowest_elevation_m")
    if hs is None and he is None:
        return []
    if hs is None:
        hs = he
    if he is None:
        he = hs
    assert hs is not None and he is not None
    pts: dict[float, float] = {round(s_m, 2): round(hs, 2), round(e_m, 2): round(he, 2)}
    span = e_m - s_m
    if span > 10.0:
        if hmin is not None and hmin < min(hs, he) - 0.1:
            pts[round(s_m + span * 0.35, 2)] = round(hmin, 2)
        if hmax is not None and hmax > max(hs, he) + 0.1:
            t_pos = 0.68 if len(pts) > 2 else 0.5
            pts[round(s_m + span * t_pos, 2)] = round(hmax, 2)
    return sorted(pts.items(), key=lambda item: item[0])


def _apply_activity_elevations_to_single_draft(
    result: dict[str, Any],
    elevs: dict[str, float | None],
) -> None:
    drafts = result.get("draft_sections") or []
    if len(drafts) != 1:
        return
    d0 = drafts[0]
    for key in (
        "start_elevation_m",
        "end_elevation_m",
        "highest_elevation_m",
        "lowest_elevation_m",
    ):
        val = elevs.get(key)
        if val is not None:
            d0[key] = round(val, 2)


def parse_plan_profile_text(
    text: str,
    *,
    max_section_length_m: float = 12_000.0,
    max_elevation_diff_m: float | None = None,
    file_name: str | None = None,
) -> dict[str, Any]:
    """Plan-profil metninden KP istasyonlarını, kotları ve taslak kesitleri üretir."""
    max_len = max(500.0, min(float(max_section_length_m or 12_000.0), 20_000.0))
    max_elev_diff = (
        float(max_elevation_diff_m)
        if max_elevation_diff_m is not None and max_elevation_diff_m > 0
        else None
    )

    # 1) Boru hattı üst verileri (varsa)
    pipe_meta = _extract_pipe_meta(text)
    outside_diameter_mm = pipe_meta["outside_diameter_mm"]
    wall_thickness_mm = pipe_meta["wall_thickness_mm"]
    design_pressure_bar = pipe_meta["design_pressure_bar"]
    material_grade = pipe_meta["material_grade"]
    smys_mpa = pipe_meta["smys_mpa"]

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
        # Yalnızca kesintisiz ardışık kesit aralıkları ise doğrudan kullan (yol/dere geçiş notlarını ele)
        if (
            len(range_spans) >= 2
            and all(250.0 <= (e - s) <= max_len * 1.05 for s, e in range_spans)
            and all(
                abs(range_spans[i + 1][0] - range_spans[i][1]) <= 1.0
                for i in range(len(range_spans) - 1)
            )
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
            # Tek bir açık kesit varsa yalnızca NGTL 5007 üst sınırı (20.000 m) aşıldığında böl
            if len(explicit_sections) == 1 and (e_m - s_m) > 20_000.0:
                strategy = "auto_split"
                break
            sec_no = raw_no.upper() if raw_no.upper().startswith(("K-", "S-")) else f"K-{idx:02d}"
            spans.append((sec_no, s_m, e_m))

    if not spans:
        activity_span = _extract_activity_profile_kp_span(text) if not explicit_sections else None
        single_lbl = (
            _extract_single_section_label(text, file_name) if not explicit_sections else None
        )
        if (
            single_lbl
            and activity_span is not None
            and (activity_span[1] - activity_span[0]) <= 20_000.0
        ):
            strategy = "explicit"
            s_act, e_act = activity_span
            spans = [(single_lbl, s_act, e_act)]
            sorted_stations = sorted(
                {st for st in sorted_stations if s_act - 0.5 <= st <= e_act + 0.5} | {s_act, e_act}
            )
        elif (
            single_lbl
            and len(sorted_stations) >= 2
            and (sorted_stations[-1] - sorted_stations[0]) <= 20_000.0
        ):
            strategy = "explicit"
            spans = [(single_lbl, sorted_stations[0], sorted_stations[-1])]
        else:
            strategy = "auto_split"
            spans, split_warnings = _auto_split_spans(
                sorted_stations=sorted_stations,
                profile_points=profile_points,
                max_len=max_len,
                max_elev_diff=max_elev_diff,
            )
            warnings.extend(split_warnings)

    act_elevs: dict[str, float | None] | None = None
    if len(spans) == 1 and len(profile_points) < 2:
        cand_elevs = _extract_activity_profile_elevations(text)
        if (
            cand_elevs.get("start_elevation_m") is not None
            or cand_elevs.get("end_elevation_m") is not None
        ):
            act_elevs = cand_elevs
            profile_points = _synthesize_activity_profile_points(
                spans[0][1], spans[0][2], cand_elevs
            )

    # 6) Taslak kesit nesnelerini ve ardışık KP süreklilik kontrolünü oluştur
    response = _assemble_scan_response(
        strategy=strategy,
        spans=spans,
        sorted_stations=sorted_stations,
        profile_points=profile_points,
        max_len=max_len,
        outside_diameter_mm=outside_diameter_mm,
        wall_thickness_mm=wall_thickness_mm,
        design_pressure_bar=design_pressure_bar,
        material_grade=material_grade,
        smys_mpa=smys_mpa,
        warnings=warnings,
    )
    if act_elevs is not None:
        _apply_activity_elevations_to_single_draft(response, act_elevs)
    return response


def _auto_split_spans(
    *,
    sorted_stations: list[float],
    profile_points: list[tuple[float, float]],
    max_len: float,
    max_elev_diff: float | None,
) -> tuple[list[tuple[str, float, float]], list[str]]:
    """KP istasyon aralığını max_len ve opsiyonel kot farkı sınırına göre taslak kesitlere böler."""
    warnings: list[str] = []
    if len(sorted_stations) >= 2:
        min_kp = sorted_stations[0]
        max_kp = sorted_stations[-1]
    else:
        min_kp = 0.0
        max_kp = max_len
        warnings.append(
            "Dosya içinde standart KP (ör. 0+000) istasyonu bulunamadı; varsayılan taslak aralık üretildi."
        )

    spans: list[tuple[str, float, float]] = []
    cursor = min_kp
    sec_idx = 1
    while cursor < max_kp - 0.5:
        target_end = min(cursor + max_len, max_kp)

        # Kot farkı sınırı verilmişse ve bu aralıkta kot farkı sınırı aşıyorsa daha erken kes
        if max_elev_diff is not None and profile_points:
            in_window = [(st, el) for st, el in profile_points if cursor < st <= target_end]
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
    return spans, warnings


_LANDMARK_NOISE_PHRASES: tuple[str, ...] = (
    "HIDROSTATIK TEST PROFIL",
    "PLAN PROFIL",
    "BOT-TYP-",
    "TMK-OGP-",
    "BORU HATLARI ILE",
    "MUTEAHHIT",
    "TASIMA A.S",
    "OLCULERI",
    "ZEMIN KOTU",
)


def _fold_ascii(text: str) -> str:
    return (
        text.replace("İ", "i")
        .replace("I", "i")
        .replace("ı", "i")
        .replace("Ş", "s")
        .replace("ş", "s")
        .replace("Ğ", "g")
        .replace("ğ", "g")
        .replace("Ü", "u")
        .replace("ü", "u")
        .replace("Ö", "o")
        .replace("ö", "o")
        .replace("Ç", "c")
        .replace("ç", "c")
        .lower()
    )


def _classify_landmark_text(text: str) -> str | None:
    cleaned = " ".join(text.split()).strip()
    if len(cleaned) < 3 or len(cleaned) > 80:
        return None
    if not any(ch.isalpha() for ch in cleaned):
        return None
    if _CHAINAGE_RE.fullmatch(cleaned) or _CAD_SECTION_LABEL_RE.match(cleaned):
        return None
    folded = _fold_ascii(cleaned)
    folded_upper = folded.upper()
    if any(phrase in folded_upper for phrase in _LANDMARK_NOISE_PHRASES):
        return None
    if any(tok in folded for tok in ("pig", "istasyon", "launcher", "receiver")):
        return "pig"
    if any(tok in folded for tok in ("dere", "nehir", "nehri", "cay", "irmak", "kanal")):
        return "river"
    if any(
        tok in folded for tok in ("kgm", "karayolu", "otoyol", "yol gecis", "demiryolu", "tcdd")
    ):
        return "road"
    if any(tok in folded for tok in ("vana", "bv-")):
        return "valve"
    return None


def _dedupe_landmarks(raw: list[tuple[float, str, str]]) -> list[tuple[float, str, str]]:
    ordered = sorted(raw, key=lambda item: (item[0], item[1], item[2]))
    kept: list[tuple[float, str, str]] = []
    for st_m, kind, label in ordered:
        folded_lbl = label.casefold()
        if any(
            abs(st_m - k_st) <= 150.0 and kind == k_kind and folded_lbl == k_lbl.casefold()
            for k_st, k_kind, k_lbl in kept
        ):
            continue
        kept.append((st_m, kind, label))
    return kept


def _slice_section_profile_points(
    profile_points: list[tuple[float, float]],
    s_m: float,
    e_m: float,
) -> list[dict[str, float]]:
    if len(profile_points) < 2 or e_m <= s_m:
        return []
    length_m = round(e_m - s_m, 2)
    pts_map: dict[float, float] = {}
    start_el = _interpolate_elevation(profile_points, s_m)
    if start_el is not None:
        pts_map[0.0] = round(start_el, 2)
    for st, el in profile_points:
        if s_m < st < e_m:
            pts_map[round(st - s_m, 2)] = round(el, 2)
    end_el = _interpolate_elevation(profile_points, e_m)
    if end_el is not None:
        pts_map[length_m] = round(end_el, 2)

    ordered = sorted(pts_map.items(), key=lambda item: item[0])
    if len(ordered) > 120:
        min_idx = min(range(len(ordered)), key=lambda idx: ordered[idx][1])
        max_idx = max(range(len(ordered)), key=lambda idx: ordered[idx][1])
        keep: set[int] = {0, len(ordered) - 1, min_idx, max_idx}
        slots = 120 - len(keep)
        if slots > 0:
            step = (len(ordered) - 1) / float(slots + 1)
            for slot in range(1, slots + 1):
                keep.add(min(len(ordered) - 1, round(slot * step)))
        ordered = [ordered[idx] for idx in sorted(keep)][:120]
    return [{"station_m": d, "elevation_m": z} for d, z in ordered]


def _slice_section_landmarks(
    landmarks: list[tuple[float, str, str]] | None,
    profile_points: list[tuple[float, float]],
    s_m: float,
    e_m: float,
) -> list[dict[str, Any]]:
    if not landmarks or e_m <= s_m:
        return []
    length_m = round(e_m - s_m, 2)
    result: list[dict[str, Any]] = []
    for st_m, kind, label in landmarks:
        if s_m - 25.0 <= st_m <= e_m + 25.0:
            rel_m = round(max(0.0, min(length_m, st_m - s_m)), 1)
            el = _interpolate_elevation(profile_points, st_m)
            result.append(
                {
                    "station_m": rel_m,
                    "kp": format_kp(st_m),
                    "kind": kind,
                    "label": label,
                    "elevation_m": el,
                }
            )
            if len(result) >= 16:
                break
    return result


def _assemble_scan_response(
    *,
    strategy: str,
    spans: list[tuple[str, float, float]],
    sorted_stations: list[float],
    profile_points: list[tuple[float, float]],
    max_len: float,
    outside_diameter_mm: float | None,
    wall_thickness_mm: float | None,
    design_pressure_bar: float | None,
    material_grade: str,
    smys_mpa: float | None,
    warnings: list[str],
    landmarks: list[tuple[float, str, str]] | None = None,
) -> dict[str, Any]:
    """Taslak kesit listesini, ardışık KP süreklilik kontrolünü ve çıktı sözlüğünü kurar."""
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
                kind = (
                    f"+{int(abs(delta_m))} m boşluk"
                    if delta_m > 0
                    else f"{int(abs(delta_m))} m bindirme"
                )
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
                "profile_points": _slice_section_profile_points(profile_points, s_m, e_m),
                "landmarks": _slice_section_landmarks(landmarks, profile_points, s_m, e_m),
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
            for st, el in profile_points[:500]
        ],
        "draft_sections": draft_sections,
        "continuity_ok": len(continuity_issues) == 0,
        "continuity_issues": continuity_issues,
        "warnings": warnings,
    }


_CAD_SECTION_LABEL_RE = re.compile(
    r"^(?:TEST\s*)?(B[ÖO]L[ÜU]M[ÜU]?|KES[İI][MT]|SECTION)\s*[:#-]?\s*([A-Za-z0-9\-]+)$",
    re.IGNORECASE,
)


def _format_cad_section_label(prefix: str, code: str) -> str:
    upper_prefix = prefix.upper()
    upper_code = code.upper()
    if upper_prefix.startswith("KES"):
        return f"KESİM {upper_code}"
    if upper_code.startswith(("K-", "S-")):
        return upper_code
    return f"BÖLÜM {upper_code}"


def _extract_cad_plan_profile_page(
    page: Any,
    reader: Any,
    *,
    pipe_meta: dict[str, Any],
    file_name: str | None = None,
    max_section_length_m: float = 12_000.0,
) -> dict[str, Any] | None:
    from pypdf.generic import ContentStream

    items: list[tuple[float, float, str]] = []

    def visitor(text: str, _cm: Any, tm: Any, _font_dict: Any, _font_size: Any) -> None:
        cleaned = text.replace("\xa0", " ").replace("\xad", "-").strip()
        if cleaned:
            items.append((float(tm[4]), float(tm[5]), cleaned))

    try:
        page.extract_text(visitor_text=visitor)
    except Exception:
        return None

    # 1) KP ekseni etiketleri (1+000 .. 57+563)
    kp_ticks: list[tuple[float, float, float]] = []
    for x, y, text in items:
        m = re.fullmatch(r"(\d{1,4})\+(\d{3}(?:[.,]\d+)?)", text)
        if m:
            km_m = parse_kp_meters(f"{m.group(1)}+{m.group(2)}")
            if km_m is not None:
                kp_ticks.append((x, y, km_m))
    if len(kp_ticks) < 4:
        return None

    by_y: dict[int, list[tuple[float, float, float]]] = defaultdict(list)
    for x, y, km_m in kp_ticks:
        by_y[round(y / 50.0) * 50].append((x, y, km_m))
    kp_longest = max(by_y.values(), key=len)
    kp_band = sorted(kp_longest, key=lambda item: item[0])
    if len(kp_band) < 4:
        return None

    x0, y_axis, m0 = kp_band[0]
    x1, _, m1 = kp_band[-1]
    if abs(x1 - x0) < 1e-3 or m1 <= m0:
        return None

    has_zero = any(text == "0" and abs(y - y_axis) < 60.0 and x < x0 for x, y, text in items)
    min_kp_m = 0.0 if has_zero else m0
    max_kp_m = m1

    # 2) BÖLÜM / KESİM / SECTION etiketleri
    bolums: list[tuple[float, float, str]] = []
    for x, y, text in items:
        m = _CAD_SECTION_LABEL_RE.match(text)
        if m and y > y_axis + 200.0:
            bolums.append((x, y, _format_cad_section_label(m.group(1), m.group(2))))
    bolums.sort(key=lambda item: item[0])

    # 3) Kot ekseni (isteğe bağlı)
    elev_ticks: list[tuple[float, float, float]] = []
    for x, y, text in items:
        if re.fullmatch(r"\d{3,4}", text):
            val = int(text)
            if val % 100 == 0 and 100 <= val <= 4500:
                elev_ticks.append((x, y, float(val)))

    ey0: float | None = None
    el0: float = 0.0
    el1: float = 0.0
    scale_el_per_px: float | None = None
    max_elev_y = max((y for _, y, _ in elev_ticks), default=0.0)
    elev_x_counts: dict[int, list[float]] = defaultdict(list)
    for x, _y, _val in elev_ticks:
        elev_x_counts[round(x / 100.0) * 100].append(x)
    elev_axis_xs = [sum(xs) / len(xs) for xs in elev_x_counts.values() if len(xs) >= 5]
    if len(elev_ticks) >= 3:
        by_x: dict[int, list[tuple[float, float, float]]] = defaultdict(list)
        for ex_coord, ey_coord, eval_m in elev_ticks:
            by_x[round(ex_coord / 100.0) * 100].append((ex_coord, ey_coord, eval_m))
        elev_longest = max(by_x.values(), key=len)
        elev_band = sorted(elev_longest, key=lambda item: item[1])
        if len(elev_band) >= 3 and abs(elev_band[-1][1] - elev_band[0][1]) > 1e-3:
            ey0, el0 = elev_band[0][1], elev_band[0][2]
            ey1, el1 = elev_band[-1][1], elev_band[-1][2]
            scale_el_per_px = (el1 - el0) / (ey1 - ey0)

    # 4) Vektör içerik akışından dikey sınır, ızgara ve zemin profil çizgileri
    try:
        cs = ContentStream(page.get_contents(), reader)
    except Exception:
        return None

    try:
        page_height = abs(float(page.mediabox.height))
    except Exception:
        page_height = 2000.0
    min_vline_span = min(250.0, max(40.0, (page_height - 300.0) * 0.12))

    vlines: list[tuple[float, float, float]] = []
    cur_x: float | None = None
    cur_y: float | None = None
    for operands, operator in cs.operations:
        op = operator.decode("latin1") if isinstance(operator, bytes) else str(operator)
        if op == "m" and len(operands) == 2:
            cur_x, cur_y = float(operands[0]), float(operands[1])
        elif op == "l" and len(operands) == 2 and cur_x is not None and cur_y is not None:
            nx, ny = float(operands[0]), float(operands[1])
            if abs(nx - cur_x) < 2.0 and abs(ny - cur_y) > min_vline_span:
                vlines.append((cur_x, min(cur_y, ny), max(cur_y, ny)))
            cur_x, cur_y = nx, ny
        elif op in ("S", "s", "f", "F", "B", "b", "n"):
            cur_x, cur_y = None, None

    if not vlines:
        return None

    base_y = ey0 if ey0 is not None else y_axis + 50.0

    # Düzenli dikey CAD ızgara çizgilerinden KP kalibrasyonu (metin genişliği kaymasını önler)
    approx_m_per_px = (m1 - m0) / (x1 - x0)
    approx_km_px = 1000.0 / approx_m_per_px
    slope = approx_m_per_px
    intercept = m0 - slope * x0
    regular_grid_map: dict[float, float] = {}

    raw_grid_xs = sorted(
        x for x, y1, _y2 in vlines if abs(y1 - base_y) < 35.0 and x >= x0 - approx_km_px * 1.5
    )
    grid_xs: list[float] = []
    for gx in raw_grid_xs:
        if not grid_xs or abs(gx - grid_xs[-1]) > 2.0:
            grid_xs.append(gx)

    valid_diffs = [
        grid_xs[i + 1] - grid_xs[i]
        for i in range(len(grid_xs) - 1)
        if approx_km_px * 0.08 <= (grid_xs[i + 1] - grid_xs[i]) <= approx_km_px * 1.2
    ]
    if len(valid_diffs) >= 6:
        bins: dict[int, int] = defaultdict(int)
        for d in valid_diffs:
            bins[round(d / 5.0) * 5] += 1
        mode_bin, mode_count = max(bins.items(), key=lambda kv: kv[1])
        if mode_count >= 6:
            raw_step_px = statistics.median([d for d in valid_diffs if abs(d - mode_bin) <= 5.0])
            step_m = min(
                (100.0, 200.0, 250.0, 500.0, 1000.0),
                key=lambda c: abs(c - raw_step_px * approx_m_per_px),
            )
            if has_zero and abs(m0 - 1000.0) < 1.0:
                origin_cands = [
                    gx
                    for gx in grid_xs
                    if x0 - approx_km_px * 1.25 <= gx <= x0 - approx_km_px * 0.45
                ]
                origin_m_cand = 0.0
            else:
                origin_cands = [
                    gx
                    for gx in grid_xs
                    if x0 - approx_km_px * 0.15 <= gx <= x0 + approx_km_px * 0.40
                ]
                origin_m_cand = m0
            if origin_cands:
                origin_x = origin_cands[0]
                k_cands = [(origin_x, 0)]
                prev_gx, cur_k = origin_x, 0
                for gx in grid_xs:
                    if gx <= origin_x + raw_step_px * 0.5:
                        continue
                    dk = round((gx - prev_gx) / raw_step_px)
                    if (
                        1 <= dk <= 4
                        and abs((gx - prev_gx) - dk * raw_step_px) <= raw_step_px * 0.06
                    ):
                        cur_k += dk
                        prev_gx = gx
                        k_cands.append((gx, cur_k))
                if len(k_cands) >= 6:
                    reg_pairs = [(gx, origin_m_cand + k * step_m) for gx, k in k_cands]
                    regular_grid_map = dict(reg_pairs)
                    mx = sum(px for px, _ in reg_pairs) / len(reg_pairs)
                    mm = sum(pm for _, pm in reg_pairs) / len(reg_pairs)
                    denom = sum((px - mx) ** 2 for px, _ in reg_pairs)
                    if denom > 1e-6:
                        slope = sum((px - mx) * (pm - mm) for px, pm in reg_pairs) / denom
                        intercept = mm - slope * mx

    def x_to_m(x_val: float) -> float:
        if regular_grid_map:
            near = [gx for gx in regular_grid_map if abs(gx - x_val) <= 1.5]
            if near:
                return regular_grid_map[min(near, key=lambda gx: abs(gx - x_val))]
        return intercept + slope * x_val

    min_bolum_y = (
        min(item[1] for item in bolums)
        if bolums
        else ((max_elev_y + 200.0) if elev_ticks else (y_axis + 450.0))
    )
    # Bölüm sınır çizgileri: ara kot eksenlerini dışarıda bırakarak üst bölüm bandına uzanan dikeyler
    divider_y_thresh = max(min_bolum_y, max_elev_y + 200.0) if elev_ticks else min_bolum_y

    # Zemin kotu noktaları (eksen tabanından profil eğrisine uzanan dikey grid çizgileri)
    profile_map: dict[float, float] = {}
    if ey0 is not None and scale_el_per_px is not None:
        for x, y1, y2 in vlines:
            if abs(y1 - ey0) < 35.0 and y2 > base_y + 25.0 and y2 < divider_y_thresh:
                m_val = x_to_m(x)
                if min_kp_m - 100.0 <= m_val <= max_kp_m + 100.0:
                    el_val = el0 + (y2 - ey0) * scale_el_per_px
                    if el0 - 200.0 <= el_val <= el1 + 500.0:
                        st_clamped = round(max(min_kp_m, min(max_kp_m, m_val)), 1)
                        profile_map[st_clamped] = round(el_val, 1)
    profile_points = sorted(profile_map.items(), key=lambda item: item[0])

    raw_landmarks: list[tuple[float, str, str]] = []
    for x, y, text in items:
        if y <= y_axis + 80.0:
            continue
        kind = _classify_landmark_text(text)
        if kind is None:
            continue
        st_m = x_to_m(x)
        if min_kp_m - 150.0 <= st_m <= max_kp_m + 150.0:
            cleaned_label = " ".join(text.split()).strip()
            raw_landmarks.append(
                (round(max(min_kp_m, min(max_kp_m, st_m)), 1), kind, cleaned_label)
            )
    landmarks = _dedupe_landmarks(raw_landmarks)

    sorted_stations = sorted({*(item[2] for item in kp_band), min_kp_m, max_kp_m})
    max_len = max(500.0, min(float(max_section_length_m or 12_000.0), 20_000.0))
    strategy = "cad_profile"
    warnings: list[str] = []
    spans: list[tuple[str, float, float]] = []

    if len(bolums) >= 2:
        dividers = sorted(
            {
                round(x, 1)
                for x, y1, y2 in vlines
                if y1 <= base_y + 150.0
                and y2 >= divider_y_thresh
                and not (
                    any(abs(x - eax) < 80.0 for eax in elev_axis_xs) and y2 <= max_elev_y + 150.0
                )
            }
        )
        if len(dividers) < len(bolums) - 1:
            return None

        # Her BÖLÜM etiketini çevreleyen sol/sağ sınır çizgileriyle eşle
        for idx, (bx, _by, sec_label) in enumerate(bolums):
            left_divs = [dx for dx in dividers if dx < bx]
            right_divs = [dx for dx in dividers if dx > bx]
            sx = left_divs[-1] if left_divs else None
            ex = right_divs[0] if right_divs else None
            if idx == 0:
                s_m = min_kp_m
            elif sx is not None:
                s_m = round(max(min_kp_m, min(max_kp_m, x_to_m(sx))), 0)
            else:
                return None

            if idx == len(bolums) - 1:
                e_m = max_kp_m
            elif ex is not None:
                e_m = round(max(min_kp_m, min(max_kp_m, x_to_m(ex))), 0)
            else:
                return None

            if e_m <= s_m:
                return None
            spans.append((sec_label, s_m, e_m))
    elif len(bolums) == 1:
        spans = [(bolums[0][2], min_kp_m, max_kp_m)]
    else:
        if ey0 is None or scale_el_per_px is None or len(profile_points) < 4:
            return None
        page_text = "\n".join(t for _, _, t in items)
        single_lbl = _extract_single_section_label(page_text, file_name)
        if single_lbl and (max_kp_m - min_kp_m) <= 20_000.0:
            spans = [(single_lbl, min_kp_m, max_kp_m)]
        elif (max_kp_m - min_kp_m) <= max_len * 1.05:
            spans = [("K-01", min_kp_m, max_kp_m)]
        else:
            strategy = "auto_split"
            spans, warnings = _auto_split_spans(
                sorted_stations=sorted_stations,
                profile_points=profile_points,
                max_len=max_len,
                max_elev_diff=None,
            )

    return _assemble_scan_response(
        strategy=strategy,
        spans=spans,
        sorted_stations=sorted_stations,
        profile_points=profile_points,
        max_len=max_len,
        outside_diameter_mm=pipe_meta.get("outside_diameter_mm"),
        wall_thickness_mm=pipe_meta.get("wall_thickness_mm"),
        design_pressure_bar=pipe_meta.get("design_pressure_bar"),
        material_grade=str(pipe_meta.get("material_grade") or ""),
        smys_mpa=pipe_meta.get("smys_mpa"),
        warnings=warnings,
        landmarks=landmarks,
    )


def _extract_cad_plan_profile(
    pdf_path: str,
    *,
    pipe_meta: dict[str, Any],
    file_name: str | None = None,
    max_section_length_m: float = 12_000.0,
) -> dict[str, Any] | None:
    """CAD (vektör) plan-profil paftasından koordinat + dikey bölüm çizgileriyle kesitleri çıkarır."""
    try:
        import pypdf
    except Exception:
        return None

    try:
        reader = pypdf.PdfReader(pdf_path)
    except Exception:
        return None
    if not reader.pages:
        return None

    for page in reader.pages[:5]:
        extracted = _extract_cad_plan_profile_page(
            page,
            reader,
            pipe_meta=pipe_meta,
            file_name=file_name,
            max_section_length_m=max_section_length_m,
        )
        if extracted is not None:
            return extracted
    return None


def _extract_sideways_vector_bars(
    drawings: list[dict[str, Any]],
    *,
    page_width: float,
) -> list[tuple[float, float]]:
    """90 derece yan dönmüş CAD paftasındaki vektör kot çubuklarını (y_rel, uzunluk) olarak çıkarır."""
    vlines: list[tuple[float, float, float]] = []
    hlines: list[tuple[float, float, float]] = []
    for d in drawings:
        for it in d.get("items", []):
            if not it or it[0] != "l":
                continue
            p1, p2 = it[1], it[2]
            dx = abs(float(p2.x) - float(p1.x))
            dy = abs(float(p2.y) - float(p1.y))
            if dx < 1.5 and dy >= 80.0:
                vlines.append(
                    (
                        round((float(p1.x) + float(p2.x)) / 2.0, 2),
                        min(float(p1.y), float(p2.y)),
                        max(float(p1.y), float(p2.y)),
                    )
                )
            elif dy < 1.5 and dx >= 15.0:
                hlines.append(
                    (
                        round((float(p1.y) + float(p2.y)) / 2.0, 2),
                        min(float(p1.x), float(p2.x)),
                        max(float(p1.x), float(p2.x)),
                    )
                )
    if not vlines or not hlines:
        return []

    span_groups: dict[tuple[int, int], list[tuple[float, float, float]]] = {}
    for x, y1, y2 in vlines:
        if x > page_width * 0.65:
            continue
        key = (round(y1 / 15.0) * 15, round(y2 / 15.0) * 15)
        span_groups.setdefault(key, []).append((x, y1, y2))
    if not span_groups:
        return []

    best_group = max(
        span_groups.values(),
        key=lambda g: (len({round(v[0]) for v in g}), g[0][2] - g[0][1]),
    )
    if len({round(v[0]) for v in best_group}) < 2:
        return []

    base_x, y_start, y_end = max(best_group, key=lambda v: v[0])
    span_y = y_end - y_start
    if span_y < 80.0:
        return []

    by_y: dict[float, float] = {}
    for y, x1, x2 in hlines:
        if (
            y_start + 2.0 < y < y_end - 2.0
            and abs(x1 - base_x) <= 3.5
            and base_x + 15.0 < x2 < page_width - 25.0
        ):
            yk = round(y, 1)
            by_y[yk] = max(by_y.get(yk, 0.0), x2 - base_x)

    return [((y - y_start) / span_y, w) for y, w in sorted(by_y.items())]


def _sideways_text_score(text: str) -> int:
    folded = dossier_service.fold_tr(text or "")
    tokens = ("profil", "aktivite", "section", "bolum", "kesit", "hmax", "hmin", "kp:", "em:")
    return sum(1 for tok in tokens if tok in folded)


def _extract_sideways_cad_plan_profile(
    pdf_path: str,
    *,
    safe_name: str,
    max_section_length_m: float = 12_000.0,
    max_elevation_diff_m: float | None = None,
) -> dict[str, Any] | None:
    """Dikey (portre) sayfaya 90 derece yan basılmış vektörel CAD paftasını döndürüp OCR + vektörle okur."""
    drawings: list[Any] = []
    if importlib.util.find_spec("fitz") is not None:
        fitz = importlib.import_module("fitz")
        try:
            doc = fitz.open(pdf_path)
        except Exception:
            return None
        try:
            if len(doc) < 1:
                return None
            page = doc[0]
            rect = page.rect
            if rect.height <= rect.width * 1.1:
                return None
            embedded = (page.get_text("text") or "").strip()
            if len(embedded) >= 40:
                return None
            page_count = len(doc)
            page_width = float(rect.width)
            drawings = page.get_drawings()
        finally:
            doc.close()
    elif importlib.util.find_spec("pypdf") is not None:
        pypdf = importlib.import_module("pypdf")
        try:
            reader = pypdf.PdfReader(pdf_path)
            if len(reader.pages) < 1:
                return None
            page0 = reader.pages[0]
            page_width = float(page0.mediabox.width)
            page_height = float(page0.mediabox.height)
            if page_height <= page_width * 1.1:
                return None
            embedded = (page0.extract_text() or "").strip()
            if len(embedded) >= 40:
                return None
            page_count = len(reader.pages)
        except Exception:
            return None
    else:
        return None

    rotate_deg = 270
    rotated_page = ocr_pdf_page_rotated(pdf_path, page_index=0, rotate_deg=270, zoom=3.2)
    if rotated_page is None or not rotated_page.text.strip():
        alt_page = ocr_pdf_page_rotated(pdf_path, page_index=0, rotate_deg=90, zoom=3.2)
        if alt_page is None or not alt_page.text.strip():
            return None
        rotated_page = alt_page
        rotate_deg = 90
    elif _sideways_text_score(rotated_page.text) < 2:
        alt_page = ocr_pdf_page_rotated(pdf_path, page_index=0, rotate_deg=90, zoom=3.2)
        if alt_page and _sideways_text_score(alt_page.text) > _sideways_text_score(
            rotated_page.text
        ):
            rotated_page = alt_page
            rotate_deg = 90

    parsed = parse_plan_profile_text(
        rotated_page.text,
        max_section_length_m=max_section_length_m,
        max_elevation_diff_m=max_elevation_diff_m,
        file_name=safe_name,
    )
    drafts = parsed.get("draft_sections") or []
    if not drafts:
        return None
    if (
        parsed.get("station_count", 0) < 2
        and len(drafts) == 1
        and drafts[0].get("start_m", 0) == 0
        and drafts[0].get("end_m", 0) == max_section_length_m
    ):
        return None

    if len(drafts) == 1:
        d0 = drafts[0]
        s_m = float(d0["start_m"])
        e_m = float(d0["end_m"])
        sec_no = str(d0["section_no"])
        elevs = _extract_activity_profile_elevations(rotated_page.text)
        hs = elevs.get("start_elevation_m")
        he = elevs.get("end_elevation_m")
        hmax = elevs.get("highest_elevation_m")
        hmin = elevs.get("lowest_elevation_m")
        bars = _extract_sideways_vector_bars(drawings, page_width=page_width)
        if (
            len(bars) >= 4
            and e_m > s_m
            and hmax is not None
            and hmin is not None
            and hmax > hmin + 0.5
        ):
            w_min = min(w for _, w in bars)
            w_max = max(w for _, w in bars)
            if w_max > w_min + 5.0:
                pt_map: dict[float, float] = {}
                for y_rel, w in bars:
                    t = y_rel if rotate_deg == 270 else (1.0 - y_rel)
                    st = round(s_m + t * (e_m - s_m), 1)
                    if st <= s_m + 1.0 or st >= e_m - 1.0:
                        continue
                    el = hmin + ((w - w_min) / (w_max - w_min)) * (hmax - hmin)
                    pt_map[st] = round(max(hmin, min(hmax, el)), 2)
                if hs is not None:
                    pt_map[round(s_m, 2)] = round(hs, 2)
                if he is not None:
                    pt_map[round(e_m, 2)] = round(he, 2)
                if len(pt_map) >= 4:
                    vec_points = sorted(pt_map.items(), key=lambda item: item[0])
                    pipe_meta = parsed.get("pipe_meta") or {}
                    sorted_stations = sorted({s_m, e_m} | {st for st, _ in vec_points})
                    parsed = _assemble_scan_response(
                        strategy="cad_profile",
                        spans=[(sec_no, s_m, e_m)],
                        sorted_stations=sorted_stations,
                        profile_points=vec_points,
                        max_len=max(500.0, min(float(max_section_length_m or 12_000.0), 20_000.0)),
                        outside_diameter_mm=pipe_meta.get("outside_diameter_mm"),
                        wall_thickness_mm=pipe_meta.get("wall_thickness_mm"),
                        design_pressure_bar=pipe_meta.get("design_pressure_bar"),
                        material_grade=str(pipe_meta.get("material_grade") or ""),
                        smys_mpa=pipe_meta.get("smys_mpa"),
                        warnings=[],
                    )
                    _apply_activity_elevations_to_single_draft(parsed, elevs)

    parsed["file_name"] = safe_name
    parsed["page_count"] = page_count
    parsed["extraction_method"] = "pdf-cad-rotated-ocr"
    parsed["detected_project_name"] = dossier_service.extract_project_name_from_text(
        rotated_page.text, max_lines=None
    )
    return parsed


_SUPPORTED_CAD_EXTENSIONS = {".dwg", ".dxf"}
_SUPPORTED_PLAN_PROFILE_EXTENSIONS = (
    set(SUPPORTED_EXTENSIONS) - set(SPREADSHEET_EXTENSIONS)
) | _SUPPORTED_CAD_EXTENSIONS


def _find_dwg2dxf() -> str | None:
    """Sistemdeki LibreDWG dwg2dxf dönüştürücüsünü bulur."""
    found = shutil.which("dwg2dxf")
    if found:
        return found
    for candidate in (
        os.path.expanduser("~/.local/bin/dwg2dxf"),
        "/usr/local/bin/dwg2dxf",
        "/opt/homebrew/bin/dwg2dxf",
    ):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _extract_dxf_plan_profile(
    dxf_path: str,
    *,
    max_section_length_m: float,
    max_elevation_diff_m: float | None,
    file_name: str | None = None,
) -> dict[str, Any]:
    """DXF (veya dwg2dxf ile çevrilmiş DWG) paftasından KP, zemin kotu ve taslak kesitleri çıkarır."""
    try:
        import ezdxf
    except ImportError as exc:
        raise AppError(
            "cad_dependency_missing",
            "CAD (.dxf/.dwg) dosyalarını okumak için 'ezdxf' paketi gerekli.",
            status_code=503,
        ) from exc

    try:
        doc = ezdxf.readfile(dxf_path)
    except Exception as exc:
        logger.warning("DXF parse failed (%s): %s", file_name, exc)
        raise AppError(
            "cad_parse_error",
            "CAD dosyasi okunamadi. Gecerli bir DXF/DWG dosyasi yukleyin.",
            status_code=422,
        ) from exc

    msp = doc.modelspace()
    items: list[tuple[float, float, str, str]] = []
    dxf_vlines: list[tuple[float, float, float]] = []
    for entity in msp:
        etype = entity.dxftype()
        layer = str(getattr(entity.dxf, "layer", "") or "")
        if etype == "TEXT":
            txt = str(entity.dxf.text or "").replace("\xa0", " ").strip()
            if txt:
                items.append((float(entity.dxf.insert.x), float(entity.dxf.insert.y), txt, layer))
        elif etype == "MTEXT":
            txt = str(getattr(entity, "plain_text")() or "").replace("\xa0", " ").strip()
            if txt:
                items.append((float(entity.dxf.insert.x), float(entity.dxf.insert.y), txt, layer))
        elif etype == "INSERT":
            for att in getattr(entity, "attribs", ()):
                txt = str(att.dxf.text or "").replace("\xa0", " ").strip()
                if txt:
                    items.append((float(att.dxf.insert.x), float(att.dxf.insert.y), txt, layer))
        elif etype == "LINE":
            x1, y1 = float(entity.dxf.start.x), float(entity.dxf.start.y)
            x2, y2 = float(entity.dxf.end.x), float(entity.dxf.end.y)
            if abs(x2 - x1) < 2.0 and abs(y2 - y1) > 20.0:
                dxf_vlines.append((0.5 * (x1 + x2), min(y1, y2), max(y1, y2)))
        elif etype == "LWPOLYLINE":
            try:
                pts = list(getattr(entity, "get_points")("xy"))
            except Exception:
                pts = []
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                fx1, fy1, fx2, fy2 = float(x1), float(y1), float(x2), float(y2)
                if abs(fx2 - fx1) < 2.0 and abs(fy2 - fy1) > 20.0:
                    dxf_vlines.append((0.5 * (fx1 + fx2), min(fy1, fy2), max(fy1, fy2)))

    full_text = "\n".join(item[2] for item in items)
    max_len = max(500.0, min(float(max_section_length_m or 12_000.0), 20_000.0))
    max_elev_diff = (
        float(max_elevation_diff_m)
        if max_elevation_diff_m is not None and max_elevation_diff_m > 0
        else None
    )

    # 1) Boru hattı üst verileri
    pipe_meta = _extract_pipe_meta(full_text)
    outside_diameter_mm = pipe_meta["outside_diameter_mm"]
    wall_thickness_mm = pipe_meta["wall_thickness_mm"]
    design_pressure_bar = pipe_meta["design_pressure_bar"]
    material_grade = pipe_meta["material_grade"]
    smys_mpa = pipe_meta["smys_mpa"]

    # 2) KP ekseni bandı (en yoğun yatay KP satırı)
    kp_candidates: list[tuple[float, float, float]] = []
    for x, y, txt, _ in items:
        m = re.fullmatch(r"(\d{1,3})\+(\d{3}(?:[.,]\d+)?)", txt.strip())
        if m:
            km_m = parse_kp_meters(f"{m.group(1)}+{m.group(2)}")
            if km_m is not None:
                kp_candidates.append((x, y, round(km_m, 2)))

    sorted_stations: list[float] = []
    profile_points: list[tuple[float, float]] = []
    kp_x_map: list[tuple[float, float]] = []
    kp_band_y: float | None = None
    dxf_landmarks: list[tuple[float, str, str]] = []

    def _interp_dxf_kp(x_val: float) -> float:
        if x_val <= kp_x_map[0][0]:
            dx = kp_x_map[1][0] - kp_x_map[0][0]
            if abs(dx) > 1e-6:
                return (
                    kp_x_map[0][1]
                    + (x_val - kp_x_map[0][0]) * (kp_x_map[1][1] - kp_x_map[0][1]) / dx
                )
            return kp_x_map[0][1]
        if x_val >= kp_x_map[-1][0]:
            dx = kp_x_map[-1][0] - kp_x_map[-2][0]
            if abs(dx) > 1e-6:
                return (
                    kp_x_map[-1][1]
                    + (x_val - kp_x_map[-1][0]) * (kp_x_map[-1][1] - kp_x_map[-2][1]) / dx
                )
            return kp_x_map[-1][1]
        for idx_k in range(len(kp_x_map) - 1):
            kx0, km0 = kp_x_map[idx_k]
            kx1, km1 = kp_x_map[idx_k + 1]
            if kx0 <= x_val <= kx1 and abs(kx1 - kx0) > 1e-6:
                return km0 + (x_val - kx0) * (km1 - km0) / (kx1 - kx0)
        return kp_x_map[0][1]

    if kp_candidates:
        by_y: dict[int, list[tuple[float, float, float]]] = defaultdict(list)
        for x, y, km_m in kp_candidates:
            by_y[round(y / 25.0) * 25].append((x, y, km_m))
        kp_longest = max(by_y.values(), key=len)
        kp_band = sorted(kp_longest, key=lambda entry: entry[0])
        kp_x_map = [(x, km_m) for x, _, km_m in kp_band]
        kp_band_y = statistics.median([y for _, y, _ in kp_band])
        sorted_stations = sorted({km_m for _, km_m in kp_x_map})

        # 3) Zemin kotu bandı: x koordinatları KP bandıyla hizalı sayısal kot satırını bul
        # Öncelik: ZEMİN etiketine yakın bant veya en yüksek x-hizalamalı sayısal bant
        zemin_y_hints = [
            y
            for x, y, txt, layer in items
            if txt.strip().upper() in {"ZEMİN", "ZEMIN", "ZEMİN KOTU", "GROUND"}
            and ("TABLO" in layer.upper() or x < kp_band[0][0])
        ]

        elev_bands: dict[int, list[tuple[float, float]]] = defaultdict(list)
        for x, y, txt, _ in items:
            m_el = re.fullmatch(r"(-?\d{2,4}(?:[.,]\d{1,3})?)", txt.strip())
            if not m_el:
                continue
            val = _parse_float(m_el.group(1))
            if val is None or not (-200.0 <= val <= 5000.0):
                continue
            # KP bandındaki bir x ile hizalı mı?
            if any(abs(x - kx) <= 5.0 for kx, _ in kp_x_map):
                elev_bands[round(y / 20.0) * 20].append((x, val))

        chosen_elev_band: list[tuple[float, float]] = []
        if elev_bands:
            if zemin_y_hints:
                # ZEMİN etiketine dikey olarak en yakın (en az 10 nokta içeren) bandı seç
                valid_bands = [(yb, pts) for yb, pts in elev_bands.items() if len(pts) >= 10]
                if valid_bands:
                    chosen_elev_band = min(
                        valid_bands,
                        key=lambda kv: min(abs(kv[0] - zy) for zy in zemin_y_hints),
                    )[1]
            if not chosen_elev_band:
                chosen_elev_band = max(elev_bands.values(), key=len)

        if chosen_elev_band:
            station_elev_map: dict[float, float] = {}
            for ex, el_val in chosen_elev_band:
                nearest_kp = min(kp_x_map, key=lambda kp_entry: abs(kp_entry[0] - ex))
                if abs(nearest_kp[0] - ex) <= 5.0:
                    station_elev_map[round(nearest_kp[1], 1)] = round(el_val, 2)
            profile_points = sorted(station_elev_map.items(), key=lambda entry: entry[0])

    if len(kp_x_map) >= 2 and kp_band_y is not None:
        raw_dxf_landmarks: list[tuple[float, str, str]] = []
        min_kp_dxf = sorted_stations[0]
        max_kp_dxf = sorted_stations[-1]
        for x, y, txt, _ in items:
            if y <= kp_band_y + 10.0:
                continue
            kind = _classify_landmark_text(txt)
            if kind is None:
                continue
            st_m = _interp_dxf_kp(x)
            if min_kp_dxf - 150.0 <= st_m <= max_kp_dxf + 150.0:
                cleaned_label = " ".join(txt.split()).strip()
                raw_dxf_landmarks.append(
                    (round(max(min_kp_dxf, min(max_kp_dxf, st_m)), 1), kind, cleaned_label)
                )
        dxf_landmarks = _dedupe_landmarks(raw_dxf_landmarks)

    # Öncelik 1: CAD paftasında BÖLÜM / KESİM etiketleri + dikey sınır çizgileri
    strategy = "auto_split"
    spans: list[tuple[str, float, float]] = []
    warnings: list[str] = []

    if len(kp_x_map) >= 2 and kp_band_y is not None:
        bolums: list[tuple[float, float, str]] = []
        for x, y, txt, _ in items:
            if y > kp_band_y + 10.0:
                m_sec = _CAD_SECTION_LABEL_RE.match(txt)
                if m_sec:
                    bolums.append((x, y, _format_cad_section_label(m_sec.group(1), m_sec.group(2))))
        bolums.sort(key=lambda item: item[0])

        if len(bolums) >= 2 and dxf_vlines:
            min_bolum_y = min(item[1] for item in bolums)
            dividers = sorted(
                {
                    round(x, 1)
                    for x, y1, y2 in dxf_vlines
                    if y1 <= kp_band_y + 50.0 and y2 >= min_bolum_y - 20.0
                }
            )
            if len(dividers) >= len(bolums) - 1:
                min_kp_m = sorted_stations[0]
                max_kp_m = sorted_stations[-1]

                cad_spans: list[tuple[str, float, float]] = []
                valid_cad = True
                for idx_b, (bx, _by, sec_label) in enumerate(bolums):
                    left_divs = [dx for dx in dividers if dx < bx]
                    right_divs = [dx for dx in dividers if dx > bx]
                    cad_sx: float | None = left_divs[-1] if left_divs else None
                    cad_ex: float | None = right_divs[0] if right_divs else None
                    if idx_b == 0:
                        s_m = min_kp_m
                    elif cad_sx is not None:
                        s_m = round(max(min_kp_m, min(max_kp_m, _interp_dxf_kp(cad_sx))), 0)
                    else:
                        valid_cad = False
                        break

                    if idx_b == len(bolums) - 1:
                        e_m = max_kp_m
                    elif cad_ex is not None:
                        e_m = round(max(min_kp_m, min(max_kp_m, _interp_dxf_kp(cad_ex))), 0)
                    else:
                        valid_cad = False
                        break

                    if e_m <= s_m:
                        valid_cad = False
                        break
                    cad_spans.append((sec_label, s_m, e_m))

                if valid_cad and cad_spans:
                    strategy = "cad_profile"
                    spans = cad_spans
        elif (
            len(bolums) == 1
            and len(sorted_stations) >= 2
            and sorted_stations[-1] > sorted_stations[0]
        ):
            strategy = "cad_profile"
            spans = [(bolums[0][2], sorted_stations[0], sorted_stations[-1])]

    # Öncelik 2: Açık kesit metin aralıkları
    if not spans:
        text_check = parse_plan_profile_text(
            full_text,
            max_section_length_m=max_len,
            max_elevation_diff_m=max_elev_diff,
            file_name=file_name,
        )
        if text_check.get("strategy") == "explicit" and text_check.get("draft_sections"):
            strategy = "explicit"
            spans = [
                (str(sec["section_no"]), float(sec["start_m"]), float(sec["end_m"]))
                for sec in text_check["draft_sections"]
            ]

    if (
        not spans
        and len(sorted_stations) >= 2
        and (sorted_stations[-1] - sorted_stations[0]) <= 20_000.0
    ):
        single_lbl = _extract_single_section_label(full_text, file_name)
        if single_lbl:
            strategy = "explicit"
            spans = [(single_lbl, sorted_stations[0], sorted_stations[-1])]

    # Öncelik 3: Otomatik uzunluk bölmesi
    if not spans:
        strategy = "auto_split"
        spans, warnings = _auto_split_spans(
            sorted_stations=sorted_stations,
            profile_points=profile_points,
            max_len=max_len,
            max_elev_diff=max_elev_diff,
        )

    res = _assemble_scan_response(
        strategy=strategy,
        spans=spans,
        sorted_stations=sorted_stations,
        profile_points=profile_points,
        max_len=max_len,
        outside_diameter_mm=outside_diameter_mm,
        wall_thickness_mm=wall_thickness_mm,
        design_pressure_bar=design_pressure_bar,
        material_grade=material_grade,
        smys_mpa=smys_mpa,
        warnings=warnings,
        landmarks=dxf_landmarks,
    )
    res["detected_project_name"] = dossier_service.extract_project_name_from_text(
        full_text, max_lines=None
    )
    return res


def _validate_plan_profile_magic_bytes(ext: str, data: bytes) -> None:
    """Validate uploaded file signature before invoking native/CAD/PDF parsers."""
    head = data[:8192]
    ok = False
    if ext == ".pdf":
        ok = b"%PDF-" in head[:1024]
    elif ext == ".dwg":
        ok = head[:6].startswith(b"AC10")
    elif ext == ".dxf":
        ok = b"SECTION" in head.upper() or head.startswith(b"AutoCAD Binary DXF")
    elif ext == ".png":
        ok = head.startswith(b"\x89PNG\r\n\x1a\n")
    elif ext in {".jpg", ".jpeg"}:
        ok = head.startswith(b"\xff\xd8\xff")
    elif ext in {".tif", ".tiff"}:
        ok = head.startswith((b"II*\x00", b"MM\x00*"))
    elif ext == ".bmp":
        ok = head.startswith(b"BM")
    elif ext == ".webp":
        ok = len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if not ok:
        raise AppError(
            "invalid_file_signature",
            f"Dosya içeriği {ext} başlığı ile uyuşmuyor.",
            status_code=415,
        )


def scan_plan_profile_upload(
    *,
    file_name: str | None,
    stream: BinaryIO,
    max_section_length_m: float = 12_000.0,
    max_elevation_diff_m: float | None = None,
    language: str | None = None,
    max_bytes: int | None = None,
) -> dict[str, Any]:
    """Yüklenen Plan-Profil PDF/CAD/görsel dosyasını okur ve taslak kesitleri üretir."""
    safe_name = os.path.basename(file_name or "plan_profile.pdf")
    ext = Path(safe_name).suffix.lower()
    if ext not in _SUPPORTED_PLAN_PROFILE_EXTENSIONS:
        raise AppError(
            "unsupported_format",
            f"Desteklenmeyen dosya uzantısı: {ext or 'yok'}. PDF, DWG, DXF veya görsel yükleyin.",
            status_code=415,
        )

    env_limit = effective_max_file_size_bytes()
    limit = env_limit if max_bytes is None else min(max_bytes, env_limit)
    chunk_size = 1024 * 1024
    header_buf = bytearray()
    total_written = 0
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp_path = tmp.name
            while True:
                chunk = stream.read(chunk_size)
                if not chunk:
                    break
                total_written += len(chunk)
                if total_written > limit:
                    raise AppError(
                        "file_too_large",
                        "Dosya boyutu izin verilen sınırı aşıyor.",
                        status_code=413,
                    )
                if len(header_buf) < 8192:
                    need = 8192 - len(header_buf)
                    header_buf.extend(chunk[:need])
                tmp.write(chunk)

        if total_written == 0:
            raise AppError("empty_file", "Yüklenen dosya boş.", status_code=422)

        _validate_plan_profile_magic_bytes(ext, bytes(header_buf))
    except Exception:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise

    if ext in _SUPPORTED_CAD_EXTENSIONS:
        dxf_tmp_path: str | None = None
        try:
            if ext == ".dwg":
                dwg2dxf = _find_dwg2dxf()
                if not dwg2dxf:
                    raise AppError(
                        "dwg_converter_missing",
                        "DWG dosyalarını okumak için LibreDWG (dwg2dxf) kurulu olmalıdır.",
                        status_code=503,
                    )
                with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as dxf_out:
                    dxf_tmp_path = dxf_out.name
                proc = subprocess.run(
                    [dwg2dxf, "-y", "-o", dxf_tmp_path, tmp_path],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if (
                    proc.returncode != 0
                    or not os.path.isfile(dxf_tmp_path)
                    or os.path.getsize(dxf_tmp_path) == 0
                ):
                    logger.warning(
                        "dwg2dxf failed rc=%s stderr=%s stdout=%s",
                        proc.returncode,
                        proc.stderr.strip()[:500],
                        proc.stdout.strip()[:500],
                    )
                    raise AppError(
                        "dwg_convert_failed",
                        "DWG dosyasi DXF bicimine donusturulemedi. Dosyayi kontrol edip tekrar deneyin.",
                        status_code=422,
                    )
                target_dxf = dxf_tmp_path
                method = "dwg-libredwg-ezdxf"
            else:
                target_dxf = tmp_path
                method = "dxf-ezdxf"

            parsed = _extract_dxf_plan_profile(
                target_dxf,
                max_section_length_m=max_section_length_m,
                max_elevation_diff_m=max_elevation_diff_m,
                file_name=safe_name,
            )
            parsed["file_name"] = safe_name
            parsed["page_count"] = 1
            parsed["extraction_method"] = method
            return parsed
        finally:
            for p in (tmp_path, dxf_tmp_path):
                if p:
                    try:
                        os.unlink(p)
                    except OSError:
                        pass

    cad_parsed: dict[str, Any] | None = None
    sideways_parsed: dict[str, Any] | None = None
    try:
        if ext == ".pdf":
            sideways_parsed = _extract_sideways_cad_plan_profile(
                tmp_path,
                safe_name=safe_name,
                max_section_length_m=max_section_length_m,
                max_elevation_diff_m=max_elevation_diff_m,
            )
            if sideways_parsed is not None:
                return sideways_parsed

        try:
            pages = extract_text(tmp_path)
        except ReportOcrError as exc:
            raise AppError(exc.code, str(exc), status_code=422) from exc

        full_text = "\n".join(page.text for page in pages)
        text_parsed = parse_plan_profile_text(
            full_text,
            max_section_length_m=max_section_length_m,
            max_elevation_diff_m=max_elevation_diff_m,
            file_name=safe_name,
        )
        if ext == ".pdf":
            cad_parsed = _extract_cad_plan_profile(
                tmp_path,
                pipe_meta=text_parsed.get("pipe_meta", {}),
                file_name=safe_name,
                max_section_length_m=max_section_length_m,
            )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    parsed = cad_parsed if cad_parsed is not None else text_parsed
    parsed["file_name"] = safe_name
    parsed["page_count"] = len(pages)
    parsed["extraction_method"] = (
        "pdf-cad-vector"
        if cad_parsed is not None
        else (pages[0].source if pages else "pdf-text-layer")
    )
    if not parsed.get("detected_project_name"):
        parsed["detected_project_name"] = dossier_service.extract_project_name_from_text(
            full_text, max_lines=None
        )
    return parsed


def create_sections_from_drafts(
    db: OrmSession,
    *,
    workspace_hash: str,
    project_id: str,
    drafts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Onaylanan taslak kesitleri seçili proje altında veritabanına kaydeder veya günceller."""
    project = project_service.get_project(db, project_id, workspace_hash)
    existing_sessions = (
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
    existing_by_no: dict[str, HydroSession] = {}
    for sess in existing_sessions:
        raw_no = str(
            ((sess.inputs or {}).get("section_meta") or {}).get("section_no") or ""
        ).strip()
        norm_no = dossier_service.normalize_section_no(raw_no) or raw_no.upper()
        if norm_no and norm_no not in existing_by_no:
            existing_by_no[norm_no] = sess

    saved_sessions: list[HydroSession] = []
    updated_count = 0

    for idx, draft in enumerate(drafts, start=1):
        raw_sec_no = str(draft.get("section_no") or f"K-{idx:02d}").strip()
        sec_no = raw_sec_no
        start_m = parse_kp_meters(draft.get("start_kp"))
        end_m = parse_kp_meters(draft.get("end_kp"))
        start_kp = (
            format_kp(start_m) if start_m is not None else str(draft.get("start_kp") or "").strip()
        )
        end_kp = format_kp(end_m) if end_m is not None else str(draft.get("end_kp") or "").strip()

        if start_m is not None and end_m is not None and end_m <= start_m:
            db.rollback()
            raise AppError(
                "validation_error",
                f"{sec_no}: Bitiş KP ({end_kp}), başlangıç KP ({start_kp}) değerinden büyük olmalıdır.",
                status_code=422,
            )

        norm_sec_key = dossier_service.normalize_section_no(sec_no) or sec_no.upper()
        existing = existing_by_no.get(norm_sec_key)
        # Jenerik K-01/K-XX etiketi ayrık KP aralıklı ayrı bir paftadan geliyorsa önceki bölümü ezme
        if existing is not None and re.fullmatch(r"K-\d+", norm_sec_key):
            ex_meta = (existing.inputs or {}).get("section_meta") or {}
            ex_s = parse_kp_meters(ex_meta.get("start_kp"))
            ex_e = parse_kp_meters(ex_meta.get("end_kp"))
            if (ex_s is None or ex_e is None) and ex_meta.get("location"):
                loc_kps = [
                    parse_kp_meters(f"{m.group(1)}+{m.group(2)}")
                    for m in _CHAINAGE_RE.finditer(str(ex_meta.get("location")))
                ]
                loc_kps = [val for val in loc_kps if val is not None]
                if len(loc_kps) >= 2:
                    ex_s = ex_s if ex_s is not None else loc_kps[0]
                    ex_e = ex_e if ex_e is not None else loc_kps[1]
            if (
                start_m is not None
                and end_m is not None
                and ex_s is not None
                and ex_e is not None
                and (end_m <= ex_s + 1.0 or start_m >= ex_e - 1.0)
            ):
                existing = None
                seq = 1
                while f"K-{seq:02d}" in existing_by_no:
                    seq += 1
                sec_no = f"K-{seq:02d}"
                norm_sec_key = sec_no

        length_m = (
            round(end_m - start_m, 2)
            if start_m is not None and end_m is not None
            else _parse_float(str(draft.get("length_m") or "")) or 12_000.0
        )

        raw_desc = str(draft.get("description") or "").strip()
        if raw_desc and sec_no != raw_sec_no and raw_sec_no in raw_desc:
            raw_desc = raw_desc.replace(raw_sec_no, sec_no, 1)
        description = raw_desc or f"{project.name} · {sec_no}"
        location = (
            f"KP {start_kp} – {end_kp}" if start_kp and end_kp else str(draft.get("location") or "")
        )

        raw_pts: list[dict[str, float]] = []
        for pt in draft.get("profile_points") or []:
            if not isinstance(pt, dict):
                continue
            st_val = _parse_float(str(pt.get("station_m")))
            el_val = _parse_float(str(pt.get("elevation_m")))
            if st_val is None or el_val is None:
                continue
            raw_pts.append(
                {
                    "station_m": round(max(0.0, min(length_m, st_val)), 2),
                    "elevation_m": round(el_val, 2),
                }
            )
        raw_pts.sort(key=lambda item: item["station_m"])

        raw_lms: list[dict[str, Any]] = []
        for lm in draft.get("landmarks") or []:
            if not isinstance(lm, dict):
                continue
            st_val = _parse_float(str(lm.get("station_m")))
            label_val = str(lm.get("label") or "").strip()
            if st_val is None or not label_val:
                continue
            el_val = (
                _parse_float(str(lm.get("elevation_m")))
                if lm.get("elevation_m") is not None
                else None
            )
            raw_lms.append(
                {
                    "station_m": round(max(0.0, min(length_m, st_val)), 1),
                    "kp": str(lm.get("kp") or ""),
                    "kind": str(lm.get("kind") or "crossing"),
                    "label": label_val,
                    "elevation_m": round(el_val, 1) if el_val is not None else None,
                }
            )

        raw_eq: list[dict[str, Any]] = []
        for idx, eq in enumerate(draft.get("equipment") or [], start=1):
            if not isinstance(eq, dict):
                continue
            st_val = _parse_float(str(eq.get("station_m")))
            label_val = str(eq.get("label") or "").strip()
            if st_val is None or not label_val:
                continue
            el_val = (
                _parse_float(str(eq.get("elevation_m")))
                if eq.get("elevation_m") is not None
                else None
            )
            raw_eq.append(
                {
                    "id": str(eq.get("id") or f"eq-{idx}"),
                    "type": str(eq.get("type") or "valve"),
                    "label": label_val,
                    "station_m": round(max(0.0, min(length_m, st_val)), 1),
                    "elevation_m": round(el_val, 1) if el_val is not None else None,
                    "status": str(eq.get("status") or "pass"),
                }
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
        inputs["segments"] = []
        inputs["profile_points"] = raw_pts
        inputs["landmarks"] = raw_lms
        inputs["equipment"] = raw_eq
        if draft.get("material_grade"):
            inputs["material_grade"] = str(draft["material_grade"])

        session_name = (
            f"{sec_no} · KP {start_kp}–{end_kp} · {project.code or project.name}"
            if start_kp and end_kp
            else f"{sec_no} · {project.code or project.name}"
        )

        if existing is not None:
            merged_inputs = copy.deepcopy(existing.inputs or session_service.default_inputs())
            ex_geom = merged_inputs.get("geometry") or {}
            ex_prof = merged_inputs.get("section_profile") or {}
            merged_inputs["section_meta"] = {
                **(merged_inputs.get("section_meta") or {}),
                **inputs["section_meta"],
            }
            new_geom = dict(inputs["geometry"])
            if draft.get("outside_diameter_mm") is None and ex_geom.get("outside_diameter_mm"):
                new_geom["outside_diameter_mm"] = ex_geom["outside_diameter_mm"]
            if draft.get("wall_thickness_mm") is None and ex_geom.get("wall_thickness_mm"):
                new_geom["wall_thickness_mm"] = ex_geom["wall_thickness_mm"]
            merged_inputs["geometry"] = {
                **ex_geom,
                **new_geom,
            }
            new_prof = dict(inputs["section_profile"])
            if draft.get("design_pressure_bar") is None and ex_prof.get("design_pressure_bar"):
                new_prof["design_pressure_bar"] = ex_prof["design_pressure_bar"]
            if draft.get("smys_mpa") is None and ex_prof.get("smys_mpa"):
                new_prof["smys_mpa"] = ex_prof["smys_mpa"]
            merged_inputs["section_profile"] = {
                **ex_prof,
                **new_prof,
            }
            existing_segments = list(merged_inputs.get("segments") or [])
            existing_seg_total = sum(
                float((seg or {}).get("length_m") or 0.0)
                for seg in existing_segments
                if isinstance(seg, dict)
            )
            if len(existing_segments) > 1 and abs(existing_seg_total - float(length_m)) <= 1.0:
                merged_inputs["segments"] = existing_segments
            else:
                merged_inputs["segments"] = []
            merged_inputs["profile_points"] = raw_pts
            merged_inputs["landmarks"] = raw_lms
            if raw_eq:
                merged_inputs["equipment"] = raw_eq
            if inputs.get("material_grade"):
                merged_inputs["material_grade"] = inputs["material_grade"]
            existing.inputs = session_service.normalize_inputs(merged_inputs)
            existing.name = session_name
            existing.revision = int(existing.revision or 0) + 1
            existing.updated_at = utcnow()
            dossier_service.ensure_section_form_slots(db, existing, commit=False)
            db.flush()
            saved_sessions.append(existing)
            updated_count += 1
        else:
            created = session_service.create_session(
                db,
                workspace_hash=workspace_hash,
                name=session_name,
                project_id=project.id,
                inputs=inputs,
                commit=False,
            )
            existing_by_no[norm_sec_key] = created
            saved_sessions.append(created)

    db.commit()
    created_items: list[dict[str, Any]] = []
    for sess in saved_sessions:
        db.refresh(sess)
        created_items.append(session_service.session_brief(sess))

    return {
        "project_id": project.id,
        "created_count": len(created_items),
        "updated_count": updated_count,
        "items": created_items,
    }

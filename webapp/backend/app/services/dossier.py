"""Multi-section BOTAŞ dossier analysis, form tracking matrix, project fuzzy matching & auto checkpoints."""

from __future__ import annotations

import copy
import logging
import math
import re
import statistics
import unicodedata
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm.attributes import flag_modified

from hidrostatik_test.data.pipe_catalog import API_5L_PSL2_GRADES
from hidrostatik_test.domain import (
    AIR_CONTENT_ACCEPTANCE_FACTOR,
    END_PUMP_LOCATION,
    PRESSURE_VARIATION_ACCEPTANCE_BAR,
    START_PUMP_LOCATION,
    AirContentInputs,
    PipeGeometry,
    PipeSection,
    PressureVariationInputs,
    SectionPressureProfileInputs,
    ValidationError,
    evaluate_air_content_test,
    evaluate_fill_temperature,
    evaluate_pig_speed,
    evaluate_pressure_variation_test,
    evaluate_section_pressure_profile,
    get_location_class_rule,
)
from hidrostatik_test.domain.operations import get_pig_speed_limit
from hidrostatik_test.domain.pressurization import PRESSURIZATION_VOLUME_DEVIATION_LIMIT_PERCENT
from hidrostatik_test.domain.time_series import (
    THERMAL_BALANCE_MIN_HOURS,
    THERMAL_BALANCE_THRESHOLD_C,
)
from hidrostatik_test.services.report_ocr import PageText, parse_number

from ..core.errors import AppError
from ..core.timeutil import as_positive_float, iso_z, json_safe, utcnow
from ..desktop_labels import FIELD_CHECKS
from ..models import HydroSession, OcrAnalysis, Project, SectionForm, TestResult, new_uuid
from . import audit
from . import projects as project_service
from . import sessions as session_service
from .form_details import (
    build_effective_dewatering_payloads,
    build_form_structured_payload,
    compute_extended_summary,
    evaluate_all_form_findings,
    evaluate_dewatering_operations,
    merge_form_extracted_data,
    monitoring_rows_to_time_series,
    parse_base_date,
    reconcile_form_extracted_data,
    time_series_to_monitoring_rows,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical BOTAŞ form catalog (11 mandatory + 5 supplementary forms)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FormSpec:
    code: str
    botas_code: str
    title: str
    required: bool
    order: int


BOTAS_FORM_CATALOG: tuple[FormSpec, ...] = (
    FormSpec("test_data", "BOT-FRM-İNB-001-015_1", "Hidrostatik Test Verileri", True, 1),
    FormSpec("cleaning", "BOT-FRM-İNB-001-016", "Temizlik Kabul Raporu", True, 2),
    FormSpec("filling", "BOT-FRM-İNB-001-017", "Su Dolum Raporu", True, 3),
    FormSpec(
        "leak_stabilization",
        "BOT-FRM-İNB-001-018",
        "Dengeleme İçin Kaçak Test Raporu",
        True,
        4,
    ),
    FormSpec("strength", "BOT-FRM-İNB-001-019", "Mukavemet Test Raporu", True, 5),
    FormSpec(
        "air_acceptance",
        "BOT-FRM-İNB-001-020",
        "Hava İçerik Testi Kabul Raporu",
        True,
        6,
    ),
    FormSpec("pressure_test", "BOT-FRM-İNB-001-021", "Basınç Testi Raporu", True, 7),
    FormSpec(
        "pressure_acceptance",
        "BOT-FRM-İNB-001-022",
        "Basınç Testi Kabul Raporu",
        True,
        8,
    ),
    FormSpec("dewatering", "BOT-FRM-İNB-001-023", "Boşaltma Kabul Raporu", True, 9),
    FormSpec("pre_drying", "BOT-FRM-KUR-001", "Ön Kurutma Kabul Raporu", True, 10),
    FormSpec("final_drying", "BOT-FRM-KUR-002", "Nihai Kurutma Kabul Raporu", True, 11),
    FormSpec("pressurization", "BOT-FRM-EK-014", "Basınçlandırma Test Raporu", False, 12),
    FormSpec("spool_test", "BOT-FRM-EK-SPL", "Spool Test Verileri", False, 13),
    FormSpec("calculation_sheet", "BOT-FRM-001-027", "Hidrostatik Test Hesap Tablosu", False, 14),
    FormSpec(
        "chart_recorder", "BOT-FRM-EK-KRT", "Basınç-Sıcaklık Kayıt Diyagramı (Chart)", False, 15
    ),
    FormSpec("caliper_pig", "BOT-FRM-EK-KLP", "Kalibrasyon / Kaliper Pig Raporu", False, 16),
)

DOSSIER_SCHEMA_VERSION = 3

FORM_SPEC_BY_CODE: dict[str, FormSpec] = {spec.code: spec for spec in BOTAS_FORM_CATALOG}
REQUIRED_FORM_SPECS: tuple[FormSpec, ...] = tuple(s for s in BOTAS_FORM_CATALOG if s.required)

_FOLD_MAP = str.maketrans(
    {
        "ç": "c",
        "Ç": "c",
        "ğ": "g",
        "Ğ": "g",
        "ı": "i",
        "I": "i",
        "İ": "i",
        "Í": "i",
        "í": "i",
        "ö": "o",
        "Ö": "o",
        "ş": "s",
        "Ş": "s",
        "Ș": "s",
        "ș": "s",
        "ü": "u",
        "Ü": "u",
        # Unicode hyphens & minus signs normalized to ASCII '-'
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\xad": "-",
        # Greek delta (ΔP, ΔT) & Cyrillic OCR lookalikes emitted by Vision OCR
        "Δ": "d",
        "δ": "d",
        "А": "a",
        "а": "a",
        "В": "b",
        "в": "b",
        "С": "c",
        "с": "c",
        "Д": "d",
        "д": "d",
        "Е": "e",
        "е": "e",
        "Н": "h",
        "н": "h",
        "І": "i",
        "і": "i",
        "К": "k",
        "к": "k",
        "М": "m",
        "м": "m",
        "О": "o",
        "о": "o",
        "Р": "p",
        "р": "p",
        "Т": "t",
        "т": "t",
        "Х": "x",
        "х": "x",
        "У": "y",
        "у": "y",
        "г": "r",
        "Г": "r",
    }
)


def fold_tr(text: str) -> str:
    translated = text.translate(_FOLD_MAP)
    decomposed = unicodedata.normalize("NFKD", translated)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.lower()


# ---------------------------------------------------------------------------
# Normalization & regex extractors
# ---------------------------------------------------------------------------

_SECTION_REJECT_TOKENS = {
    "TB",
    "TH",
    "BASLIK",
    "TARIH",
    "PROJE",
    "MM",
    "BAR",
    "NA",
    "N/A",
    "YOK",
}

_CHAINAGE_RE = re.compile(r"\b(\d{1,3})\s*\+\s*(\d{3}(?:[.,]\d+)?)\b")
_DATE_RE = re.compile(
    r"\b(\d{1,2}(?:\s*-\s*\d{1,2})?[./-]\d{1,2}[./-]\d{2,4}(?:\s*-\s*\d{1,2}[./-]\d{1,2}[./-]\d{2,4})?)\b"
)
_TIME_TOKEN_RE = re.compile(r"(?<![\d:])(\d{1,2}):(\d{2})(?::(\d{2}))?(?![\d:])")

_COMPANY_HEADER_STOP_KEYWORDS = (
    "boru hatlari ile petrol",
    "tasima a.s",
    "tasima a s",
    "anonim",
    "sirket",
    "muhendislik",
    "insaat",
    "limited",
    "muteahhit firma",
    "yuklenici firma",
    "firma adi",
    "ve logosu",
    "adi-soyadi",
    "imza",
)

_PROJECT_STOP_KEYWORDS = (
    "botas",
    *_COMPANY_HEADER_STOP_KEYWORDS,
    "test bolum",
    "test raporu",
    "kabul raporu",
    "dolum raporu",
    "test verileri",
    "spool test",
    "tarih",
    "baslik",
)

_PROJECT_BOILERPLATE_TOKENS = {
    "yapim",
    "isi",
    "projesi",
    "proje",
    "dogal",
    "gaz",
    "dogalgaz",
    "boru",
    "hatti",
    "hatlari",
    "hat",
    "hidrostatik",
    "test",
    "profili",
    "profil",
    "plan",
    "paftasi",
    "dgbh",
    "bransman",
}

_CORE_STOP_TOKENS = _PROJECT_BOILERPLATE_TOKENS
_TEMPLATE_DATES = ("14.04.2008", "04.03.2005")
_REV_LINE_RE = re.compile(r"\brev(?:[.\s:]|izyon)?\b", re.IGNORECASE)


def _is_revision_line(line: str) -> bool:
    folded = fold_tr(line)
    return bool(_REV_LINE_RE.search(folded)) or any(tmpl in line for tmpl in _TEMPLATE_DATES)


def normalize_section_no(raw: str | None) -> str | None:
    """Normalize diverse section names (`Bölüm-5`, `1. Section`, `K-01`, `HT-01`) into canonical names."""
    if not raw:
        return None
    raw_str = " ".join(str(raw).replace("\xa0", " ").split())
    # Reject explicit negative numbers such as temperature limits (`: -20`) before stripping leading `-`
    if re.match(r"^(?:[:=;#•\t\s]*)?[-−]\s*\d", raw_str):
        return None
    cleaned = raw_str.strip(" :.-#*•\t")
    if not cleaned:
        return None
    folded = fold_tr(cleaned).upper()

    # Reject test heads / dates / ISO dates / form codes / template revisions
    if re.match(r"^(?:TB|TH|REV|FRM|BOT)\s*[-_]?\s*\d*", folded):
        return None
    if any(tok == folded or folded.startswith(f"{tok}-") for tok in _SECTION_REJECT_TOKENS):
        return None
    if re.match(r"^(?:\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2})$", folded):
        return None

    m_pref = re.fullmatch(r"(K|HT|MB|PK)\s*[-_.]?\s*0*(\d{1,3})\s*([A-Z])?", folded)
    if m_pref:
        prefix = m_pref.group(1)
        suffix = m_pref.group(3) or ""
        return f"{prefix}-{int(m_pref.group(2)):02d}{suffix}"

    stripped = re.sub(
        r"^(?:TEST\s*BOLUM(?:U)?(?:\s*NO)?|BOLUM(?:\s*NO)?|PAKET(?:\s*NO)?|SECTION(?:\s*NO)?|KESIT(?:\s*NO)?)\s*[-:#._*]*\s*",
        "",
        folded,
    )
    if re.match(r"^[-−]\s*\d", stripped):
        return None
    stripped = re.sub(
        r"\s*[./-]?\s*(?:TEST\s*BOLUM(?:U)?|BOLUM|PAKET|SECTION|KESIT)\s*$",
        "",
        stripped,
    ).strip(" :-#._*")
    if re.fullmatch(r"(?:19|20)\d{2}", stripped):
        return None
    m_num = re.fullmatch(r"0*(\d{1,3})\s*[-_.]?\s*([A-Z])?", stripped)
    if m_num:
        num = int(m_num.group(1))
        if num <= 0 or num > 200:
            return None
        letter = m_num.group(2) or ""
        return f"BÖLÜM {num}{letter}"

    if (
        len(stripped) <= 12
        and any(ch.isdigit() for ch in stripped)
        and re.fullmatch(r"[A-Z0-9-]+", stripped)
        and not re.fullmatch(r"\d{4,}", stripped)
    ):
        return f"BÖLÜM {stripped}"
    return None


def classify_form_text(text: str, sheet_hint: str = "") -> FormSpec | None:
    """Identify the BOTAŞ form type from page/sheet title first, then unambiguous codes."""
    head = "\n".join(text.splitlines()[:45])
    folded_head = " ".join(fold_tr(head).split())
    folded_all = " ".join(fold_tr(text).split())
    folded_sheet = " ".join(fold_tr(sheet_hint).split())
    combined_title = f"{folded_head}\n{folded_sheet}"

    title_rules: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "pressure_acceptance",
            ("basinc testi kabul", "sizdirmazlik testi kabul", "leak test acceptance"),
        ),
        (
            "air_acceptance",
            ("hava icerik testi kabul", "hava miktari testi kabul", "acceptance air test"),
        ),
        ("leak_stabilization", ("dengeleme icin kacak", "dengeleme kacak", "leak stabili")),
        ("pressurization", ("basinclandirma test raporu", "basinclandirma test")),
        ("strength", ("mukavemet test raporu", "strength test")),
        ("pressure_test", ("basinc testi raporu", "basinc test raporu", "leak test report")),
        ("filling", ("su dolum raporu", "su doldurma raporu", "filling report")),
        ("cleaning", ("temizlik kabul raporu", "hat temizlik raporu", "cleaning report")),
        ("dewatering", ("bosaltma kabul raporu", "su bosaltma raporu", "dewatering report")),
        ("pre_drying", ("on kurutma kabul", "on kurutma raporu", "pre-drying", "pre drying")),
        ("final_drying", ("nihai kurutma", "son kurutma", "final drying", "kurutma kabul raporu")),
        ("test_data", ("hidrostatik test verileri", "hydrostatic test data")),
        ("spool_test", ("spool test verileri", "spool test raporu", "spool test")),
        (
            "caliper_pig",
            (
                "kaliper pig raporu",
                "kalibrasyon pig raporu",
                "geometrik pig",
                "gauging pig",
                "kaliper pig",
            ),
        ),
    )

    # Check title lines / sheet hint first so misprinted footer codes (e.g. CDB-001-019 on Filling) never win
    for form_code, needles in title_rules:
        if any(needle in combined_title for needle in needles):
            return FORM_SPEC_BY_CODE[form_code]

    # Explicit engineering / chart / BOTAŞ form codes before generic body-text phrase matching
    if "bot-frm-001-027" in folded_all or (
        "maksimum basinc hesabi katsayisi" in folded_all
        and "test kabul icin katsayilar" in folded_all
    ):
        return FORM_SPEC_BY_CODE["calculation_sheet"]
    if "chart no" in folded_all or ("160bar" in folded_all and "24hr" in folded_all):
        return FORM_SPEC_BY_CODE["chart_recorder"]
    if "bot-frm-kur-001" in folded_all:
        return FORM_SPEC_BY_CODE["pre_drying"]
    if "bot-frm-kur-002" in folded_all:
        return FORM_SPEC_BY_CODE["final_drying"]

    # Secondary check on entire page text (catches rotated/landscape forms whose title sits deeper)
    for form_code, needles in title_rules:
        if any(needle in folded_all for needle in needles):
            return FORM_SPEC_BY_CODE[form_code]

    m_inb = re.search(r"bot-frm-inb-001-0(15|16|17|18|19|20|21|22|23)", folded_all)
    if m_inb:
        mapping = {
            "15": "test_data",
            "16": "cleaning",
            "17": "filling",
            "18": "leak_stabilization",
            "19": "strength",
            "20": "air_acceptance",
            "21": "pressure_test",
            "22": "pressure_acceptance",
            "23": "dewatering",
        }
        return FORM_SPEC_BY_CODE[mapping[m_inb.group(1)]]
    if "bot-frm-cdb-001-024" in folded_all:
        return FORM_SPEC_BY_CODE["dewatering"]

    # Per-section engineering calculation sheets (e.g. Hizan Section 1..21 calculation pages)
    folded_lines = fold_tr(text)
    is_summary_index_table = (
        len(re.findall(r"(?m)^\s*\d{1,4}\s*(?:\.\s*\d)?\s+\d+\+\d{3}", folded_lines)) >= 3
    )
    has_calc_elevations = (
        "baslangic kotu" in folded_all
        or "en dusuk kotu" in folded_all
        or bool(re.search(r"\bhs\b\s*[:=)]", folded_all))
    ) and (
        "max. kot" in folded_all
        or "max kot farki" in folded_all
        or "en yuksek kotu" in folded_all
        or bool(re.search(r"\bhmax\b\s*[:=)]", folded_all))
    )
    has_calc_pressures = any(
        tok in folded_all for tok in ("pmin", "pmax", "vsec", "shoop", "vpipe")
    )
    if not is_summary_index_table and has_calc_elevations and has_calc_pressures:
        return FORM_SPEC_BY_CODE["calculation_sheet"]

    return None


_SECTION_LABEL_RE = re.compile(
    r"\b(?:test\s*bolum(?:u)?\s*(?:no|n0|numarasi)?|bolum\s*(?:no|n0|numarasi)|kesit\s*(?:no|n0)|section\s*(?:no|n0)|paket\s*(?:no|n0))\b"
)
_STANDALONE_SECTION_LINE_RE = re.compile(
    r"^(?:"
    r"(?:test\s*bolum(?:u)?|bolum|kesit|section|paket)\s*(?:no\s*[:=]?\s*)?[-:#.]?\s*\d{1,3}\s*[-]?[a-z]?"
    r"|\d{1,3}\s*[a-z]?\s*[.-]?\s*(?:test\s*bolum(?:u)?|bolum|kesit|section|paket)"
    r"|(?:k|ht|mb|pk)\s*[-_]?\s*\d{1,3}[a-z]?"
    r")$"
)
_CHART_TYPO_SECTION_RE = re.compile(
    r"\b(?:rest|test|tost)\s+b(?:slun|olum|alem|abm|ol)[a-z]{0,3}\s*n[o0]\s*[:=.\s]*(\d{1,3}\s*[a-z]?)(?!\s*\.\s*baslik)\b"
)


def extract_page_section_no(text: str) -> str | None:
    """Extract normalized Test Section ID (`BÖLÜM 5`, `BÖLÜM 3B`, `K-01`) from one form page."""
    lines = [
        " ".join(ln.replace("\xa0", " ").split()).strip() for ln in text.splitlines() if ln.strip()
    ]

    # Priority 1: explicit "Test Bölüm No : ..." / "Bölüm No : ..." (slice folded string to prevent NFD drift)
    for idx, line in enumerate(lines):
        folded = fold_tr(line)
        m_lbl = _SECTION_LABEL_RE.search(folded)
        if not m_lbl:
            continue
        tail_folded = folded[m_lbl.end() :].lstrip(" :.=;-|")
        if re.match(r"^(?:boyu|hacmi?|uzunlugu|parametreleri|acmi)\b", tail_folded):
            continue

        if tail_folded and not re.match(r"^[-−]\s*\d", tail_folded):
            # Cut off any subsequent column label on the same line (even at index 0, e.g. "1.Başlık No")
            tail_cut = re.split(
                r"(?:^|\s+)(?:tarih|boru|1\s*\.?\s*baslik|2\s*\.?\s*baslik|baslik\s*(?:no|yeri)|test\s*bolum|basinc|bolum\s*uzunlugu|maks|max)\b",
                tail_folded,
                maxsplit=1,
            )[0].strip()
            norm = normalize_section_no(tail_cut)
            if norm:
                return norm
            if m_inline := re.search(
                r"\b(?:bolum|kesit|section|paket)\s*[-:#.]?\s*(\d{1,3}\s*[-]?[a-z]?)\b"
                r"|\b(\d{1,3}\s*[a-z]?)\s*[.-]?\s*(?:bolum|kesit|section|paket)\b",
                tail_cut,
            ):
                tok = m_inline.group(1) or m_inline.group(2)
                norm = normalize_section_no(f"BOLUM {tok}")
                if norm:
                    return norm

        # Search nearby lines when two-column Vision OCR wraps the value above/below the label
        for nb_idx in (idx + 1, idx - 1, idx + 2, idx - 2, idx - 3, idx + 3):
            if not (0 <= nb_idx < len(lines)):
                continue
            nb_fold = fold_tr(lines[nb_idx]).strip(" :=•\t")
            if not nb_fold or re.match(r"^[-−]\s*\d", nb_fold):
                continue
            if re.search(
                r"(?:\b(?:bolum|kesit|section|paket)\s*[-:#]?\s*\d{1,3}|\b\d{1,3}\s*[a-z]?\s*[.-]?\s*(?:bolum|kesit|section|paket)\b)",
                nb_fold,
            ):
                norm = normalize_section_no(nb_fold)
                if norm:
                    return norm
            if (
                nb_idx in (idx + 1, idx + 2)
                and not re.match(r"^(?:boyu|hacmi?|uzunlugu)\b", nb_fold)
                and re.fullmatch(
                    r"0*\d{1,3}\s*[-_]?[a-z]?|(?:k|ht|mb|pk)\s*[-_]?\s*\d{1,3}[a-z]?",
                    nb_fold,
                )
            ):
                norm = normalize_section_no(nb_fold)
                if norm:
                    return norm

    # Priority 2: standalone section line anywhere on the page (captures rotated landscape tables)
    for line in lines:
        cleaned_leading = re.sub(r"^[:=\-•|#.\s]+", "", fold_tr(line)).strip(" :-|#\t")
        if _STANDALONE_SECTION_LINE_RE.fullmatch(cleaned_leading):
            norm = normalize_section_no(cleaned_leading)
            if norm:
                return norm

    # Priority 2b: engineering calc headers ("SECTION 1 0+000.00 - 1+132.21") & activity profile titles ("... SECTION O1")
    for line in lines:
        folded = fold_tr(line)
        m_hdr = re.match(
            r"^(?:test\s*bolum(?:u)?|bolum|kesit|section|paket)\s*[:#.-]?\s*0*(\d{1,3}(?:\s*[-_.]?\s*[a-z])?)\b(?:\s+\d{1,3}\s*\+\s*\d{3}|\s*[-:])",
            folded,
        )
        if m_hdr:
            norm = normalize_section_no(f"BOLUM {m_hdr.group(1)}")
            if norm:
                return norm
        m_prof = re.search(
            r"(?:hidrostatik\s+test\s+aktiv[ie]t[ie]si\s+profili|test\s+aktiv[ie]t[ie]si)\s+(?:section|bolum|kesit)\s+([o0-9]{1,3}[a-z]?)\b",
            folded,
        )
        if m_prof:
            tok = re.sub(r"[oO](?=\d)|(?<=\d)[oO]", "0", m_prof.group(1))
            norm = normalize_section_no(f"BOLUM {tok}")
            if norm:
                return norm

    # Priority 3: handwritten OCR typos on chart recorder disks (`Rest Bslün No:1`, `Test Babm No: 2`, `Tost Balem No:2`)
    for line in lines:
        folded_line = fold_tr(line)
        if _SECTION_LABEL_RE.search(folded_line):
            continue
        m_typo = _CHART_TYPO_SECTION_RE.search(folded_line)
        if m_typo:
            norm = normalize_section_no(f"BOLUM {m_typo.group(1)}")
            if norm:
                return norm

    return None


def _has_real_date(text: str) -> bool:
    for line in text.splitlines():
        if _is_revision_line(line):
            continue
        if _DATE_RE.search(line):
            return True
    return False


def _is_blank_template_page(text: str, section_no: str | None) -> bool:
    if section_no is not None:
        return False
    folded = fold_tr(text)
    has_placeholder = any(
        token in folded for token in ("proje adi", "muteahhit firma", "yuklenici firma")
    )
    has_numeric_geom = bool(
        re.search(
            r"(?:boru\s*dis\s*capi|test\s*bolum\s*boyu|test\s*bolum\s*hacmi)[ \t]*[:=]?[ \t]*\d+(?!\s*\.\s*baslik)",
            folded,
        )
    )
    return has_placeholder and not has_numeric_geom and not _has_real_date(text)


_PROJECT_SUFFIX_TOKENS = {"yapim", "isi", "projesi", "proje"}
_FORM_TITLE_STOP_KEYWORDS = (
    "test raporu",
    "kabul raporu",
    "dolum raporu",
    "test verileri",
    "spool test",
    "test bolum",
    "muteahhit firma",
    "yuklenici firma",
    "firma adi",
)


def extract_project_name_from_text(text: str, *, max_lines: int | None = 100) -> str | None:
    """Extract likely pipeline project name from form headers or Plan-Profil title blocks."""
    lines = [
        " ".join(ln.replace("\xa0", " ").replace("\xad", "-").split()).strip()
        for ln in text.splitlines()
        if ln.strip()
    ]
    scan_lines = lines if max_lines is None else lines[:max_lines]
    candidates: list[tuple[str, int]] = []  # (cleaned_name, explicit_bonus)

    for idx, line in enumerate(scan_lines):
        folded = fold_tr(line)

        if "bot-typ-" in folded or re.match(r"^(?:kgm|tcdd|dsi|botas\s+tip)\s+projesi\b", folded):
            continue

        # Explicit "Proje Adı : <value>"
        if re.match(r"^proje\s*(?:adi|name)\s*[:=]?", folded):
            raw_val = (
                re.split(r"[:=]", line, maxsplit=1)[1].strip()
                if (":" in line or "=" in line)
                else ""
            )
            raw_clean = raw_val.strip(" ._:-•")
            if not raw_clean and idx + 1 < len(scan_lines):
                raw_val = scan_lines[idx + 1]
                raw_clean = raw_val.strip(" ._:-•")
            val_fold = fold_tr(raw_clean)
            if (
                raw_clean
                and len(raw_clean) >= 5
                and not _DATE_RE.search(raw_clean)
                and val_fold not in {"botas", "b.o.t.a.s", "b.o.t.a.s.", "proje adi"}
                and not any(
                    bad in val_fold
                    for bad in (
                        *_FORM_TITLE_STOP_KEYWORDS,
                        *_COMPANY_HEADER_STOP_KEYWORDS,
                        "ve logosu",
                        "adi-soyadi",
                    )
                )
                and any(ch.isalpha() for ch in val_fold)
            ):
                cleaned_val = _clean_project_title(raw_val)
                if cleaned_val:
                    candidates.append((cleaned_val, 1))
                continue

        if any(stop in folded for stop in _FORM_TITLE_STOP_KEYWORDS):
            continue
        if any(stop in folded for stop in _COMPANY_HEADER_STOP_KEYWORDS):
            continue
        if any(stop in folded for stop in _PROJECT_STOP_KEYWORDS) and not any(
            kw in folded for kw in ("dgbh", "projesi", "yapim isi", "boru hatti")
        ):
            continue

        if any(
            kw in folded
            for kw in (
                "dgbh",
                "yapim isi",
                "projesi",
                "boru hatti",
                "boru hatlari",
                "dogalgaz",
                "dogal gaz",
                "hidrostatik test profili",
            )
        ):
            combined = line
            if "projesi" not in folded:
                # Rejoin multi-line wrapped project suffix (e.g., "İŞİ PROJESİ" separated across columns)
                cur_toks = re.findall(r"[a-z0-9]+", folded)
                for nb in scan_lines[idx + 1 : idx + 6]:
                    nb_fold = fold_tr(nb)
                    if any(stop in nb_fold for stop in _FORM_TITLE_STOP_KEYWORDS):
                        break
                    nb_toks = re.findall(r"[a-z0-9]+", nb_fold)
                    if nb_toks and set(nb_toks).issubset(_PROJECT_SUFFIX_TOKENS):
                        if cur_toks[-len(nb_toks) :] != nb_toks:
                            combined = f"{combined} {nb}"
                            cur_toks.extend(nb_toks)
                        if "projesi" in nb_toks:
                            break
            cleaned = _clean_project_title(combined)
            if cleaned and len(cleaned) >= 6:
                core_words = [
                    w
                    for w in re.findall(r"[a-z0-9]+", fold_tr(cleaned))
                    if len(w) >= 3 and w not in _PROJECT_BOILERPLATE_TOKENS
                ]
                if core_words:
                    candidates.append((cleaned, 0))

    if not candidates:
        return None
    counts = Counter(name for name, _ in candidates)
    explicit_set = {name for name, ex in candidates if ex}

    def _score(kv: tuple[str, int]) -> tuple[int, int, int, int]:
        cand, cnt = kv
        cfold = fold_tr(cand)
        domain_bonus = (
            1
            if any(
                k in cfold
                for k in (
                    "dgbh",
                    "boru hatti",
                    "boru hatlari",
                    "yapim isi",
                    "dogalgaz",
                    "dogal gaz",
                )
            )
            else 0
        )
        explicit_bonus = 1 if cand in explicit_set else 0
        return (explicit_bonus, domain_bonus, cnt, len(cand))

    best, _ = max(counts.items(), key=_score)
    return best


def _clean_project_title(raw: str) -> str:
    text = " ".join(
        raw.replace("\xa0", " ")
        .replace("\xad", "-")
        .replace("Ș", "Ş")
        .replace("ș", "ş")
        .replace("Í", "İ")
        .replace("í", "i")
        .split()
    ).strip(" :-|•")
    text = re.sub(
        r"^proje\s*(?:ad[iİıI]|name)\s*[:=]\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip(" :-|•")
    # Remove trailing `: 15,5` or `: EM0-960:00` / `: YM: 33+740.00` / `: KP: ...` column bleed on rotated pages
    text = re.sub(
        r"\s*:\s*(?:(?:[VTY]?EM|YM|KM|KP)\s*[:=.]?\s*)?[-+]?\d[\d.,+:/-]*(?:\s*m)?\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip(" :-|•")
    # Remove trailing "HİDROSTATİK TEST PROFİLİ", "HİDROSTATİK TEST SECTİONLARI-12\"", etc.
    text = re.sub(
        r'\s+(?:h[iİıI]drostat[iİıI]k\s+test\s+(?:prof[iİıI]l[iİıI]|sect[iİıI]onlar[iİıI](?:[-\u2010-\u2014\s]*\d+\s*["″]?)?|akt[iİıI]v[iİıI]t[iİıI]s[iİıI]\s+prof[iİıI]l[iİıI](?:\s+section\s+[a-z0-9]+)?)|plan[-\s]*prof[iİıI]l(?:\s+paftas[iİıI])?|test\s+prof[iİıI]l[iİıI]|test\s+b[oö]l[uü]mler[iİıI]\s+hesaplamalar[iİıI])\s*$',
        "",
        text,
        flags=re.IGNORECASE,
    ).strip(" :-|•")
    return text[:200]


_GENERIC_FILENAME_STEMS = {
    "report",
    "rapor",
    "test",
    "hydro",
    "ocr",
    "smoke",
    "doc",
    "document",
    "scan",
    "file",
    "yeni",
    "deneme",
    "hakedis",
}


def _extract_project_name_from_filename(source_filename: str | None) -> str | None:
    """Last-resort project name fallback from uploaded filename when page text lacks project headers."""
    if not source_filename:
        return None
    stem = Path(source_filename).stem
    folded = fold_tr(stem)
    if "bot-frm-" in folded or "bot_frm_" in folded:
        return None
    cleaned = re.sub(r"[_\s]+", " ", stem).strip()
    cleaned = re.sub(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", " ", cleaned)
    cleaned = re.sub(
        r"\b(?:h(?:idro)?\.?\s*test\s*rapor(?:lar[iİıI]|u)?|hidrostatik\s*test\s*(?:rapor(?:lar[iİıI]|u)?|veriler[iİıI]|hesaplamalar[iİıI])|test\s*rapor(?:lar[iİıI]|u)?|hesaplama(?:lar[iİıI])?|hakedi[sş]|rapor(?:lar[iİıI]|u)?)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = " ".join(cleaned.split()).strip(" -_.")
    if len(cleaned) < 3 or not any(ch.isalpha() for ch in cleaned):
        return None
    toks = [tok for tok in re.findall(r"[a-z0-9]+", fold_tr(cleaned)) if not tok.isdigit()]
    if not toks or all(tok in _GENERIC_FILENAME_STEMS for tok in toks):
        return None
    return cleaned[:200]


def _diacritic_quality(text: str) -> int:
    """Prefer authentic Turkish letters (`ÇĞİÖŞÜ`) over ASCII-stripped OCR spellings."""
    return sum(1 for ch in text if ch in "ÇĞİÖŞÜçğıöşü")


def extract_project_name_from_pages(pages: Sequence[PageText]) -> str | None:
    by_tokens: dict[tuple[str, ...], list[str]] = {}
    for page in pages:
        candidate = extract_project_name_from_text(page.text)
        if candidate:
            toks = tuple(re.findall(r"[a-z0-9]+", fold_tr(candidate)))
            if toks:
                by_tokens.setdefault(toks, []).append(candidate)
    if not by_tokens:
        return None

    # Consolidate truncated prefix variants (e.g. "... YAPIM" -> "... YAPIM İŞİ PROJESİ") into fuller titles
    merged_counts: dict[tuple[str, ...], int] = {
        toks: len(vals) for toks, vals in by_tokens.items()
    }
    ordered = sorted(by_tokens.keys(), key=len)
    for shorter in ordered:
        for longer in reversed(ordered):
            if len(longer) <= len(shorter):
                continue
            if longer[: len(shorter)] == shorter and set(longer[len(shorter) :]).issubset(
                _PROJECT_SUFFIX_TOKENS
            ):
                merged_counts[longer] += merged_counts.pop(shorter, 0)
                break

    best_toks = max(merged_counts.keys(), key=lambda t: (merged_counts[t], len(t)))
    variants = by_tokens[best_toks]
    best_variant = max(
        variants,
        key=lambda v: (variants.count(v), _diacritic_quality(v), len(v)),
    )
    return best_variant


def compute_project_similarity(detected: str, existing: str) -> float:
    """Compute fuzzy project-name similarity in [0.0, 1.0], robust to pipe size/suffixes."""
    a_raw = fold_tr(detected or "")
    b_raw = fold_tr(existing or "")
    a_full = " ".join(re.findall(r"[a-z0-9]+", a_raw))
    b_full = " ".join(re.findall(r"[a-z0-9]+", b_raw))
    if not a_full or not b_full:
        return 0.0
    if a_full == b_full:
        return 1.0

    # Strip inch tokens (e.g. 14", 10") and generic engineering suffix tokens for core comparison
    def _core_tokens(src: str) -> list[str]:
        tokens = re.findall(r"[a-z0-9]+", src)
        return [
            tok
            for tok in tokens
            if tok not in _CORE_STOP_TOKENS and not re.fullmatch(r"\d{1,2}", tok)
        ]

    core_a = _core_tokens(a_raw)
    core_b = _core_tokens(b_raw)
    if not core_a or not core_b:
        return round(SequenceMatcher(None, a_full, b_full).ratio(), 4)

    core_a_str = " ".join(core_a)
    core_b_str = " ".join(core_b)
    if core_a_str == core_b_str:
        return 0.96

    full_ratio = SequenceMatcher(None, a_full, b_full).ratio()
    core_ratio = 0.95 * SequenceMatcher(None, core_a_str, core_b_str).ratio()

    set_a = set(core_a)
    set_b = set(core_b)
    inter = set_a & set_b
    containment = 0.0
    if inter:
        smaller, larger = (set_a, set_b) if len(set_a) <= len(set_b) else (set_b, set_a)
        non_generic_matches = [
            t for t in inter if t not in _PROJECT_BOILERPLATE_TOKENS and len(t) >= 3
        ]
        if non_generic_matches and smaller.issubset(larger):
            containment = 0.90
        elif non_generic_matches:
            union_count = len(set_a | set_b)
            jaccard = len(inter) / union_count if union_count else 0.0
            if len(inter) >= 2 or jaccard >= 0.5:
                containment = 0.72 + 0.22 * jaccard

    return round(min(1.0, max(full_ratio, core_ratio, containment)), 4)


def find_similar_projects(
    db: OrmSession,
    workspace_hash: str,
    detected_name: str | None,
    *,
    threshold: float = 0.70,
) -> list[dict[str, Any]]:
    """Return active projects matching `detected_name` with similarity >= threshold (0.70)."""
    if not detected_name or not detected_name.strip():
        return []

    counts = (
        select(
            HydroSession.project_id.label("project_id"),
            func.count(HydroSession.id).label("section_count"),
        )
        .where(
            HydroSession.project_id.is_not(None),
            HydroSession.deleted_at.is_(None),
        )
        .group_by(HydroSession.project_id)
        .subquery()
    )
    rows = db.execute(
        select(Project, func.coalesce(counts.c.section_count, 0))
        .outerjoin(counts, counts.c.project_id == Project.id)
        .where(
            Project.workspace_id_hash == workspace_hash,
            Project.deleted_at.is_(None),
        )
        .order_by(Project.updated_at.desc())
    ).all()

    matches: list[dict[str, Any]] = []
    for proj, sec_count in rows:
        sim = compute_project_similarity(detected_name, proj.name)
        if sim >= threshold:
            matches.append(
                {
                    "id": proj.id,
                    "name": proj.name,
                    "code": proj.code or "",
                    "section_count": int(sec_count or 0),
                    "similarity": sim,
                    "similarity_pct": round(sim * 100.0, 1),
                    "exact_match": sim >= 0.96,
                }
            )
    matches.sort(key=lambda item: (-item["similarity"], -item["section_count"], item["name"]))
    return matches


# ---------------------------------------------------------------------------
# Numeric, date & time-series extractors for individual BOTAŞ forms
# ---------------------------------------------------------------------------


_NEXT_FIELD_STOP_RE = re.compile(
    r"^(?:vp|vpa|vt|pa|dp|ap|pt|dt|at|pl|ri|k\s*[:=]|rev\b|sayfa\b|form\b|tarih\b|test\s+bolum|1\.baslik|2\.baslik|1\.\s*baslik|2\.\s*baslik|\d+\.\s*(?:kullanilacak|parametreler|kabul|sonuc|aciklama))",
    re.IGNORECASE,
)
_STANDALONE_NUM_WITH_UNIT_RE = re.compile(
    r"^[-+]?\d[\d.,]*(?:\s*(?:mm|cm|m3|m³|m|bar|psi|°?c|c°|%|1/bar|1/k))?$",
    re.IGNORECASE,
)


def _first_valid_num_in_segment(
    segment: str, min_val: float | None, max_val: float | None
) -> float | None:
    # Strip date strings before scanning numeric tokens so dates like 04.10.2026 are never parsed as floats
    scrubbed = _DATE_RE.sub(" ", segment)
    for cand in re.findall(r"[-+]?\d[\d.,]*", scrubbed):
        if re.fullmatch(r"\d+\.", cand):
            continue
        try:
            val = parse_number(cand)
        except ValueError:
            continue
        if min_val is not None and val < min_val:
            continue
        if max_val is not None and val > max_val:
            continue
        return val
    return None


def _parse_num_after_label(
    text: str,
    patterns: Sequence[str],
    *,
    min_val: float | None = None,
    max_val: float | None = None,
) -> float | None:
    raw_lines = text.splitlines()
    folded_lines = [fold_tr(ln) for ln in raw_lines]
    for pat in patterns:
        rx = re.compile(pat, re.IGNORECASE)
        for idx, folded in enumerate(folded_lines):
            m = rx.search(folded)
            if not m:
                continue
            tail = folded[m.end() :]
            # Stop before a second column on the same line (e.g. `A : 45,011   K : 1,02`)
            col_tail = re.split(r"\s{2,}[a-z0-9()./_-]{1,24}\s*[:=]", tail, maxsplit=1)[0]
            # Consume optional leading unit/condition parentheses + assignment delimiter cluster (`:`, `=`, `= :`, `: :`)
            m_delim = re.match(
                r"^(?:[^0-9:=\n]*(?:\([^)]*\)[^0-9:=\n]*)*)(?:[:=]\s*)+",
                col_tail,
            )
            if m_delim:
                rhs = col_tail[m_delim.end() :].strip()
                if rhs:
                    val = _first_valid_num_in_segment(rhs, min_val, max_val)
                    if val is not None:
                        return val
            elif col_tail.strip():
                cleaned_tail = re.sub(r"\([^)]*\)", " ", col_tail)
                val = _first_valid_num_in_segment(cleaned_tail, min_val, max_val)
                if val is not None:
                    return val

            # Two-column / stacked assignment wrap fallback (e.g. `Vp` -> desc -> `(m3)= : 0,126940` or `7,10 mm`)
            checked_nonempty = 0
            for nb_fold_raw in folded_lines[idx + 1 : idx + 6]:
                nb_fold = nb_fold_raw.strip()
                if not nb_fold:
                    continue
                checked_nonempty += 1
                if checked_nonempty > 3:
                    break
                if _NEXT_FIELD_STOP_RE.match(nb_fold) and not nb_fold.startswith("("):
                    break
                nb_col = re.split(r"\s{2,}[a-z0-9()./_-]{1,24}\s*[:=]", nb_fold, maxsplit=1)[0]
                nb_delim = re.match(
                    r"^(?:[^0-9:=\n]*(?:\([^)]*\)[^0-9:=\n]*)*)(?:[:=]\s*)+",
                    nb_col,
                )
                if nb_delim:
                    rhs = nb_col[nb_delim.end() :].strip()
                    if rhs:
                        val = _first_valid_num_in_segment(rhs, min_val, max_val)
                        if val is not None:
                            return val
                elif _STANDALONE_NUM_WITH_UNIT_RE.fullmatch(nb_col):
                    val = _first_valid_num_in_segment(nb_col, min_val, max_val)
                    if val is not None:
                        return val
    return None


def _extract_form_date(text: str) -> str:
    lines = text.splitlines()[:45]
    # Priority 1: explicit "Tarih" line (or adjacent lines on rotated scans)
    for idx, line in enumerate(lines):
        if _is_revision_line(line):
            continue
        if "tarih" in fold_tr(line):
            for probe in lines[max(0, idx - 2) : min(len(lines), idx + 2)]:
                if _is_revision_line(probe):
                    continue
                if m := _DATE_RE.search(probe):
                    return m.group(1).strip()
    # Priority 2: any non-template date on the page
    for line in lines:
        if _is_revision_line(line):
            continue
        if m := _DATE_RE.search(line):
            return m.group(1).strip()
    return ""


def _extract_chainages_for_section(text: str) -> tuple[str, str]:
    pairs: dict[str, str] = {}
    for line in text.splitlines()[:70]:
        folded = fold_tr(line)
        m_ch = _CHAINAGE_RE.search(line)
        if not m_ch:
            continue
        kp_str = f"{int(m_ch.group(1))}+{m_ch.group(2)}"
        if any(
            k in folded
            for k in (
                "1.baslik yeri",
                "1. baslik yeri",
                "baslangic noktasi",
                "baslangic noktasinin kilometresi",
                "kms",
                "atma basligi",
            )
        ):
            pairs.setdefault("start", kp_str)
        elif any(
            k in folded
            for k in (
                "2.baslik yeri",
                "2. baslik yeri",
                "bitis noktasi",
                "bitis noktasinin kilometresi",
                "kme",
                "alma basligi",
            )
        ):
            pairs.setdefault("end", kp_str)
    return pairs.get("start", ""), pairs.get("end", "")


_TIME_PREFIX_RE = re.compile(
    r"^(?:okuma\s*saati|zaman|\(saat\)|saat)\s*[:=]?\s*",
    re.IGNORECASE,
)


def _parse_time_log(text: str) -> dict[str, Any]:
    """Parse sequential timestamped table rows (`HH:MM` or `HH:MM:SS`) with midnight rollover."""
    lines = [" ".join(ln.split()).strip() for ln in text.splitlines() if ln.strip()]
    entries: list[dict[str, Any]] = []

    day_offset_min = 0
    prev_total_min: float | None = None

    i = 0
    n = len(lines)
    while i < n:
        line = _TIME_PREFIX_RE.sub("", lines[i]).strip()
        m_time = _TIME_TOKEN_RE.fullmatch(line) or _TIME_TOKEN_RE.match(line)
        if m_time:
            hh = int(m_time.group(1))
            mm = int(m_time.group(2))
            ss = int(m_time.group(3) or 0)
            if 0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59:
                # Ignore footer signature timestamps (REV.0 : 04.03.2005 etc. won't match HH:MM unless followed/preceded cleanly)
                raw_min = hh * 60.0 + mm + ss / 60.0
                if (
                    prev_total_min is not None
                    and (raw_min + day_offset_min) < prev_total_min - 30.0
                ):
                    day_offset_min += 24 * 60
                abs_min = raw_min + day_offset_min
                # Collect inline numbers on the same line + numeric lines before the next timestamp/footer
                nums: list[float] = []
                tail = line[m_time.end() :].strip()
                row_notes: list[str] = []
                if tail:
                    for tok in tail.split():
                        if re.fullmatch(r"[-+]?\d[\d.,]*", tok):
                            try:
                                nums.append(parse_number(tok))
                            except ValueError:
                                pass
                        else:
                            row_notes.append(tok)

                j = i + 1
                while j < n and j <= i + 12:
                    nxt_raw = lines[j]
                    nxt_time_probe = _TIME_PREFIX_RE.sub("", nxt_raw).strip()
                    if _TIME_TOKEN_RE.match(nxt_time_probe):
                        break
                    if any(
                        stop in fold_tr(nxt_raw)
                        for stop in (
                            "botas",
                            "test formeni",
                            "test bolum",
                            "boru hatlari",
                            "pa (bar)",
                            "pa(bar)",
                            "at (",
                            "not :",
                        )
                    ):
                        break
                    tokens = nxt_raw.replace("|", " ").split()
                    has_non_num = False
                    for tok in tokens:
                        clean_tok = tok.lstrip("•.")
                        if re.fullmatch(r"[-+]?\d[\d.,]*", clean_tok):
                            try:
                                nums.append(parse_number(clean_tok))
                            except ValueError:
                                pass
                        else:
                            has_non_num = True
                    if has_non_num and not any(ch.isdigit() for ch in nxt_raw):
                        row_notes.append(nxt_raw)
                    j += 1

                entries.append(
                    {
                        "time_str": f"{hh:02d}:{mm:02d}"
                        + (f":{ss:02d}" if m_time.group(3) else ""),
                        "abs_min": round(abs_min, 2),
                        "nums": nums,
                        "notes": " ".join(row_notes),
                    }
                )
                prev_total_min = abs_min
                i = j
                continue
        i += 1

    if not entries:
        return {
            "row_count": 0,
            "duration_hours": 0.0,
            "steps_min": [],
            "median_step_min": None,
            "max_gap_min": 0.0,
            "first_time": None,
            "last_time": None,
            "entries": [],
        }

    steps = [
        round(entries[k]["abs_min"] - entries[k - 1]["abs_min"], 2) for k in range(1, len(entries))
    ]
    duration_h = (
        (entries[-1]["abs_min"] - entries[0]["abs_min"]) / 60.0 if len(entries) >= 2 else 0.0
    )
    pos_steps = [s for s in steps if s > 0]
    return {
        "row_count": len(entries),
        "duration_hours": round(duration_h, 2),
        "steps_min": steps,
        "median_step_min": round(statistics.median(pos_steps), 2) if pos_steps else None,
        "max_gap_min": round(max(pos_steps), 2) if pos_steps else 0.0,
        "first_time": entries[0]["time_str"],
        "last_time": entries[-1]["time_str"],
        "first_abs_min": entries[0]["abs_min"],
        "last_abs_min": entries[-1]["abs_min"],
        "entries": entries,
    }


def _extract_pig_events(text: str) -> dict[str, Any]:
    """Extract launch/receive timestamps from Cleaning (`016`), Dewatering (`023`), Pre/Final Drying."""
    lines = [" ".join(ln.split()).strip() for ln in text.splitlines() if ln.strip()]
    times: list[tuple[str, float]] = []
    dates: list[str] = []
    in_table = False
    for line in lines:
        folded = fold_tr(line)
        if (
            "pig izleme formu" in folded
            or "pig tipi" in folded
            or folded in {"atilis", "atis", "alis"}
            or ("pig" in folded and ("atilis" in folded or "atis" in folded or "alis" in folded))
        ):
            in_table = True
            continue
        if in_table and any(stop in folded for stop in ("aciklama", "botas", "test formeni")):
            in_table = False
            continue
        if in_table or "pig" in folded:
            for m_d in _DATE_RE.finditer(line):
                dates.append(m_d.group(1))
            for m_t in _TIME_TOKEN_RE.finditer(line):
                hh, mm = int(m_t.group(1)), int(m_t.group(2))
                if 0 <= hh <= 23 and 0 <= mm <= 59:
                    times.append((f"{hh:02d}:{mm:02d}", hh * 60.0 + mm))

    travel_min: float | None = None
    if len(times) >= 2:
        t0 = times[0][1]
        t1 = times[-1][1]
        if t1 < t0:
            t1 += 24 * 60
        travel_min = round(t1 - t0, 1)

    return {
        "has_events": len(times) >= 2 or len(dates) >= 2,
        "event_count": len(times) // 2 if len(times) >= 2 else (1 if times or dates else 0),
        "first_time": times[0][0] if times else None,
        "last_time": times[-1][0] if times else None,
        "travel_time_min": travel_min,
        "completed_note": "tamamlandi" in fold_tr(text),
    }


def _finite_float(val: Any) -> float | None:
    if val is None or isinstance(val, bool):
        return None
    try:
        num = float(val)
    except (TypeError, ValueError):
        return None
    return num if math.isfinite(num) else None


def _first_finite(*values: Any) -> float | None:
    for val in values:
        num = _finite_float(val)
        if num is not None:
            return num
    return None


def _extract_landscape_monitoring_columns(text: str, row_count: int) -> dict[str, Any]:
    """Recover column-split Basınç, Toprak/Boru temps & Avg. Boru 4h blocks on rotated 018/021 scans."""
    lines = [" ".join(ln.split()).strip() for ln in text.splitlines() if ln.strip()]
    pressures: list[float] = []
    temp_readings: list[float] = []
    block_pipe_avgs: list[float] = []

    in_pressure_col = False
    passed_avg_boru = False
    passed_avg_toprak = False
    passed_company_header = False
    has_avg_boru_label = any(
        "avg. boru" in fold_tr(ln) or "avg boru" in fold_tr(ln) for ln in lines[:45]
    )
    has_soil_and_pipe = any("toprak" in fold_tr(ln) for ln in lines) and any(
        "boru" in fold_tr(ln) for ln in lines
    )
    prev_was_pipe_block = True
    last_added_to_block = False

    _NON_TEMP_LABELS = (
        "test bolum",
        "sayfa",
        "boyu",
        "hacmi",
        "baslik",
        "kalinlik",
        "cap",
    )

    for idx, line in enumerate(lines):
        folded = fold_tr(line)
        if idx <= 2 and re.fullmatch(r"\d{1,2}[.\s]\d{1,2}[.\s]\d{4}", line):
            continue
        if _is_revision_line(line):
            continue

        if "avg. boru" in folded or "avg boru" in folded:
            passed_avg_boru = True
        if (
            "avg. toprak" in folded
            or "avg toprak" in folded
            or (passed_avg_boru and "toprak" in folded)
        ):
            passed_avg_toprak = True
            prev_was_pipe_block = False
        if idx > 0 and any(
            k in folded for k in ("uhendislik", "muhendislik", "anonim", "tarih", "boru hatlari")
        ):
            passed_company_header = True
            if passed_avg_boru:
                prev_was_pipe_block = False

        # Detect start of pressure block (`(Bar)`, `Basınç : 83,95`), never `BASINÇ TESTİ RAPORU`
        if re.match(r"^(?:basinc\s*[:=]|basinc$|\(\s*bar\s*\)(?:\s*[:=]|$))", folded):
            in_pressure_col = True
        elif in_pressure_col:
            if any(
                k in folded
                for k in (
                    "zaman",
                    "saat",
                    "botas",
                    "tasima a",
                    "section",
                    "bolum",
                    "santiye sefi",
                    "yapi denetim",
                    "muhendislik",
                    "uhendislik",
                )
            ):
                in_pressure_col = False

        # Never treat clock-timestamp lines (`18:30`, `Zaman : 14:30`) as pressure/temperature numbers
        if _TIME_TOKEN_RE.search(line):
            last_added_to_block = False
            continue

        if in_pressure_col:
            seg = (
                re.split(r"[:=]", line, maxsplit=1)[1].strip()
                if (":" in line or "=" in line)
                else line
            )
            m_num = re.fullmatch(r"(\d[\d.,]*)", seg.replace(" ", ""))
            if m_num:
                try:
                    p = parse_number(m_num.group(1))
                    if 15.0 <= p <= 400.0:
                        pressures.append(p)
                except ValueError:
                    pass
            last_added_to_block = False
            continue

        # Collect temperature values before pressure/time columns
        if not pressures and not any(lbl in folded for lbl in _NON_TEMP_LABELS):
            seg = (
                re.split(r"[:=]", line, maxsplit=1)[1].strip()
                if (":" in line or "=" in line)
                else line
            )
            m_num = re.fullmatch(r"[-+]?\d+(?:[.,]\d+)?", seg)
            if m_num:
                try:
                    val = parse_number(seg)
                except ValueError:
                    last_added_to_block = False
                    continue
                # If a footer geometry dimension (>200 mm/m) immediately follows wall thickness (<=15 mm), drop both lists consistently
                if val > 200.0 and temp_readings and temp_readings[-1] <= 15.0:
                    temp_readings.pop()
                    if last_added_to_block and block_pipe_avgs:
                        block_pipe_avgs.pop()
                    last_added_to_block = False
                    continue
                if -10.0 <= val <= 45.0:
                    # Skip small ΔT summary diffs (`0,033` / `0,067` °C) sitting inside the Avg. Boru block on Form 021
                    if has_avg_boru_label and prev_was_pipe_block and 0.0 <= abs(val) < 0.8:
                        last_added_to_block = False
                        continue
                    temp_readings.append(val)
                    if (has_avg_boru_label and prev_was_pipe_block and not passed_avg_toprak) or (
                        not has_avg_boru_label and not passed_company_header
                    ):
                        block_pipe_avgs.append(val)
                        last_added_to_block = True
                    else:
                        last_added_to_block = False
                    continue
        last_added_to_block = False

    last_4h_delta: float | None = None
    if len(block_pipe_avgs) >= 2:
        last_4h_delta = round(abs(block_pipe_avgs[-1] - block_pipe_avgs[-2]), 3)

    return {
        "pressures": pressures,
        "min_temp_c": round(min(temp_readings), 2) if temp_readings else None,
        "max_temp_c": round(max(temp_readings), 2) if temp_readings else None,
        "probe_pair_count": row_count if (has_soil_and_pipe and len(temp_readings) >= 6) else 0,
        "block_avg_count": len(block_pipe_avgs),
        "last_4h_delta_c": last_4h_delta,
        "pipe_start_c": block_pipe_avgs[0]
        if block_pipe_avgs
        else (temp_readings[0] if temp_readings else None),
        "pipe_end_c": block_pipe_avgs[-1]
        if block_pipe_avgs
        else (temp_readings[-1] if temp_readings else None),
    }


def _extract_four_hour_temp_delta(entries: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Identify temperatures & last two 4-hour block pipe temperature averages on 018 / 021."""
    all_temps: list[float] = []
    block_pipe_avgs: list[float] = []
    block_soil_avgs: list[float] = []
    toprak_readings: list[float] = []
    boru_readings: list[float] = []

    for ent in entries:
        nums: list[float] = ent.get("nums") or []
        if not nums:
            continue
        # Column layout: Pressure (~30..250 bar), Ambient, Toprak1, Boru1, [optional 4h blocks... AvgToprak, AvgBoru]
        temp_nums = [v for v in nums[1:] if -10.0 <= v <= 55.0]
        if len(temp_nums) >= 3:
            # nums[1]=Ambient, nums[2]=Toprak1, nums[3]=Boru1 (skip blank all-zero filler rows)
            if any(abs(v) > 1e-6 for v in temp_nums[:3]):
                all_temps.extend(temp_nums[:3])
            toprak_readings.append(temp_nums[1])
            boru_readings.append(temp_nums[2])
        elif temp_nums:
            all_temps.extend([v for v in temp_nums if abs(v) > 1e-6])

        # 4-hour probe summary rows have >= 10 numeric values ending with non-zero (Avg.Toprak, Avg.Boru)
        if len(nums) >= 10:
            avg_soil, avg_pipe = nums[-2], nums[-1]
            if 0.1 <= avg_soil <= 50.0 and 0.1 <= avg_pipe <= 50.0:
                block_soil_avgs.append(avg_soil)
                block_pipe_avgs.append(avg_pipe)

    last_4h_delta: float | None = None
    if len(block_pipe_avgs) >= 2:
        last_4h_delta = round(abs(block_pipe_avgs[-1] - block_pipe_avgs[-2]), 3)
    elif len(boru_readings) >= 8:
        # Fallback: compare average of last 4 hourly pipe readings vs previous 4 hours
        prev_avg = sum(boru_readings[-8:-4]) / 4.0
        last_avg = sum(boru_readings[-4:]) / 4.0
        last_4h_delta = round(abs(last_avg - prev_avg), 3)

    return {
        "min_temp_c": round(min(all_temps), 2) if all_temps else None,
        "max_temp_c": round(max(all_temps), 2) if all_temps else None,
        "probe_pair_count": min(len(toprak_readings), len(boru_readings)),
        "block_avg_count": len(block_pipe_avgs),
        "last_4h_delta_c": last_4h_delta,
        "pipe_start_c": block_pipe_avgs[0]
        if block_pipe_avgs
        else (boru_readings[0] if boru_readings else None),
        "pipe_end_c": block_pipe_avgs[-1]
        if block_pipe_avgs
        else (boru_readings[-1] if boru_readings else None),
    }


def _parse_reported_passed(text: str) -> bool | None:
    folded = fold_tr(text)
    if (
        "kabul edilmemistir" in folded
        or "basarisiz" in folded
        or "reddedilmistir" in folded
        or re.search(r"\bred\b", folded)
    ):
        return False
    if "kabul edilmistir" in folded or "sonuc : uygun" in folded:
        return True
    return None


def _slice_after_params_header(text: str) -> str:
    folded = fold_tr(text)
    m_par = re.search(r"parametreler\s+ve\s+veriler", folded)
    return folded[m_par.start() :] if m_par else folded


def _normalize_calc_text(text: str) -> str:
    """Normalize spaced decimals (`5 . 2 -> 5.2`), Unicode dashes, and spaced units (`m m -> mm`)."""
    out = fold_tr(text)
    # Keep raw case for chainage/labels when needed? We use a non-lowercased version for KP/case-sensitive needs:
    cleaned = text.translate(
        str.maketrans("\u00a0\u2010\u2011\u2012\u2013\u2014\u2212\xad", " -------")
    )
    cleaned = re.sub(r"(\d)\s*\.\s*(\d)", r"\1.\2", cleaned)
    cleaned = re.sub(r"\bm\s+m\b", "mm", cleaned, flags=re.IGNORECASE)
    _ = out
    return cleaned


def _kp_to_meters_local(raw: str | None) -> float | None:
    if not raw:
        return None
    m = _CHAINAGE_RE.search(str(raw).strip())
    if not m:
        return None
    km = float(m.group(1))
    meters = float(m.group(2).replace(",", "."))
    return km * 1000.0 + meters


def _format_kp_clean(raw: str) -> str:
    m = _CHAINAGE_RE.search(raw.strip())
    if not m:
        return raw.strip()
    km = int(m.group(1))
    num_str = m.group(2).replace(",", ".")
    try:
        val = float(num_str)
    except ValueError:
        return f"{km}+{m.group(2)}"
    whole = int(val)
    frac = round(val - whole, 2)
    if frac <= 1e-6:
        return f"{km}+{whole:03d}"
    frac_str = f"{val:.2f}".split(".")[1].rstrip("0")
    return f"{km}+{whole:03d},{frac_str}"


def _extract_doc_engineering_defaults(pages: Sequence[PageText]) -> dict[str, Any]:
    """Extract document-level engineering parameters (e.g. SMYS formula/psi, nominal OD) from cover/procedure pages."""
    defaults: dict[str, Any] = {}
    for page in pages[:5]:
        norm = _normalize_calc_text(page.text)
        folded = fold_tr(norm)
        # e.g. `SMYS (52000/14.50377)` or `3585.2747` bar -> 358.53 MPa
        m_psi = re.search(r"smys\s*\(\s*(\d{4,6})\s*/\s*14\.50\d*\s*\)", folded)
        if m_psi:
            psi = float(m_psi.group(1))
            defaults["smys_mpa"] = round(psi / 145.0377, 2)
            break
        m_smys = _parse_num_after_label(
            norm,
            (r"boru\s*akma\s*dayanimi\s*(?:\(\s*smys\s*\))?", r"\bsmys\b\s*[:=]"),
            min_val=150.0,
            max_val=900.0,
        )
        if m_smys:
            defaults["smys_mpa"] = m_smys
            break
    return defaults


def _extract_form_specific_data(form_code: str, text: str) -> dict[str, Any]:
    """Extract parameters, calculation fields and operational log metrics for one BOTAŞ form."""
    norm_text = _normalize_calc_text(text)
    folded_norm = fold_tr(norm_text)
    header: dict[str, Any] = {}
    if od := _parse_num_after_label(
        norm_text,
        (r"boru\s*d[ıi]s\s*capi", r"\bdis\s*capi?\b", r"outside\s*diameter", r"\bOD\b", r"\bD\s*="),
        min_val=40,
        max_val=2500,
    ):
        header["outside_diameter_mm"] = od
    if id_mm := _parse_num_after_label(
        norm_text,
        (r"boru\s*ic\s*capi", r"inside\s*diameter", r"\bDi\s*="),
        min_val=30,
        max_val=2400,
    ):
        header["inside_diameter_mm"] = id_mm
    if wt := _parse_num_after_label(
        norm_text,
        (
            r"boru\s*et\s*kalinligi",
            r"\bet\s*kalinligi\b",
            r"wall\s*thickness",
            r"\bWt\s*=",
            r"\bS\b(?=\s*Boru)",
        ),
        min_val=1.5,
        max_val=100,
    ):
        header["wall_thickness_mm"] = wt
    if length := _parse_num_after_label(
        norm_text,
        (
            r"test\s*bolum\s*boyu",
            r"toplam\s*boru\s*uzunlugu",
            r"bolum\s*uzunlugu",
            r"hat\s*uzunlugu",
            r"\buzunluk\b",
        ),
        min_val=10,
        max_val=200_000,
    ):
        header["length_m"] = length
    if vt := _parse_num_after_label(
        norm_text,
        (
            r"test\s*bolum\s*(?:h)?acmi?",
            r"bolum\s*hacmi?",
            r"geometrik\s*hacmi",
            r"\bVsec\s*=\s*\d",
            r"\bVt\s*[:=]",
        ),
        min_val=0.1,
        max_val=100_000,
    ):
        header["section_volume_m3"] = vt
    elif m_vsec := re.search(r"\bVsec\s*=\s*(\d[\d.,]*)\s*m3", norm_text, re.IGNORECASE):
        try:
            vsec_val = parse_number(m_vsec.group(1))
            if 0.1 <= vsec_val <= 100_000:
                header["section_volume_m3"] = vsec_val
        except ValueError:
            pass
    if max_op := _parse_num_after_label(
        norm_text,
        (
            r"max(?:imum|imum)?\.?\s*isletme\s*basinci",
            r"maks\.?\s*isletme\s*basinci",
            r"isletme\s*basinci\s*(?:po)?",
        ),
        min_val=1,
        max_val=400,
    ):
        header["design_pressure_bar"] = max_op
    if max_tp := _parse_num_after_label(
        norm_text,
        (
            r"max(?:imum)?\.?\s*test\s*basinci",
            r"maks\.?\s*test\s*basinci",
            r"test\s*basinci",
            r"\bPmax\s*=\s*(?=\d)",
        ),
        min_val=1,
        max_val=500,
    ):
        header["test_pressure_bar"] = max_tp
    if min_tp := _parse_num_after_label(
        norm_text, (r"\bPmin\s*[:=]\s*(?=\d)",), min_val=1, max_val=500
    ):
        header["min_test_pressure_bar"] = min_tp
    if ps_val := _parse_num_after_label(norm_text, (r"\bPs\s*=\s*(?=\d)",), min_val=1, max_val=500):
        header["monitored_pressure_bar"] = ps_val

    # Elevations & SMYS & Location Class & Pump location
    if hs := _parse_num_after_label(
        norm_text,
        (r"\(\s*Hs\s*\)\s*[:=]", r"\bHs\s*[:=]", r"baslangic\s*kotu"),
        min_val=-500,
        max_val=6000,
    ):
        header["start_elevation_m"] = hs
    if he := _parse_num_after_label(
        norm_text,
        (r"\(\s*He\s*\)\s*[:=]", r"\bHe\s*[:=]", r"bitis\s*kotu"),
        min_val=-500,
        max_val=6000,
    ):
        header["end_elevation_m"] = he
    if hmax := _parse_num_after_label(
        norm_text,
        (
            r"\(\s*Hmax\s*\)\s*[:=]",
            r"\bHmax\s*[:=]",
            r"test\s*bolumunun\s*en\s*yuksek\s*kotu",
            r"en\s*yuksek\s*kotu?",
            r"\bmax\.?\s*kot\b",
        ),
        min_val=-500,
        max_val=6000,
    ):
        header["highest_elevation_m"] = hmax
    if hmin := _parse_num_after_label(
        norm_text,
        (
            r"\(\s*Hmin\s*\)\s*[:=]",
            r"\bHmin\s*[:=]",
            r"test\s*bolumunun\s*en\s*dusuk\s*kotu",
            r"en\s*dusuk\s*kotu?",
            r"\bmin\.?\s*kot\b",
        ),
        min_val=-500,
        max_val=6000,
    ):
        header["lowest_elevation_m"] = hmin
    if smys_val := _parse_num_after_label(
        norm_text,
        (r"boru\s*akma\s*dayanimi\s*(?:\(\s*smys\s*\))?", r"\bsmys\b\s*[:=]"),
        min_val=150,
        max_val=900,
    ):
        header["smys_mpa"] = smys_val

    m_loc = re.search(
        r"(?:^|\n)\s*=\s*([1-4])(?:\s*\.\s*[1-4])?\b|(?:lokasyon|location)\s*(?:sinifi|class)\s*[:=]?\s*(?:class\s*)?([1-4])\b",
        folded_norm,
    )
    if m_loc:
        cls_num = int(m_loc.group(1) or m_loc.group(2))
        cls_map = {
            1: "Class 1 - min 1.25 x dizayn basinci",
            2: "Class 2 - min 1.25 x dizayn basinci",
            3: "Class 3 - min 1.50 x dizayn basinci",
            4: "Class 4 - min 1.50 x dizayn basinci",
        }
        header["location_class"] = cls_map[cls_num]

    m_pump = re.search(r"basinc\s*pompasi\s*yeri\s*[:=]\s*([^\n]+)", folded_norm)
    if m_pump:
        pump_txt = m_pump.group(1)
        if "bitis" in pump_txt or "end" in pump_txt or "tb-02" in pump_txt or "tb-2" in pump_txt:
            header["pump_location"] = END_PUMP_LOCATION
        elif (
            "baslangic" in pump_txt
            or "start" in pump_txt
            or "tb-01" in pump_txt
            or "tb-1" in pump_txt
        ):
            header["pump_location"] = START_PUMP_LOCATION

    start_kp, end_kp = _extract_chainages_for_section(norm_text)
    if not start_kp or not end_kp:
        # Check engineering header line `SECTION 1 0+000.00 - 1+132.21` or `Ls : 0+000` / `Le : 1+132`
        m_span = re.search(
            r"(?:section|bolum|kesit)\s+\d{1,3}[a-z]?\s+(\d{1,3}\s*\+\s*\d{3}(?:[.,]\d+)?)\s*-\s*(\d{1,3}\s*\+\s*\d{3}(?:[.,]\d+)?)",
            folded_norm,
        )
        if m_span:
            if not start_kp:
                start_kp = _format_kp_clean(m_span.group(1))
            if not end_kp:
                end_kp = _format_kp_clean(m_span.group(2))
            if "length_m" not in header:
                s_m = _kp_to_meters_local(m_span.group(1))
                e_m = _kp_to_meters_local(m_span.group(2))
                if s_m is not None and e_m is not None and e_m > s_m:
                    header["length_m"] = round(e_m - s_m, 2)
        if not start_kp and (
            m_ls := re.search(r"\bLs\s*[:=]\s*(\d{1,3}\s*\+\s*\d{3}(?:[.,]\d+)?)", norm_text)
        ):
            start_kp = _format_kp_clean(m_ls.group(1))
        if not end_kp and (
            m_le := re.search(r"\bLe\s*[:=]\s*(\d{1,3}\s*\+\s*\d{3}(?:[.,]\d+)?)", norm_text)
        ):
            end_kp = _format_kp_clean(m_le.group(1))

    if start_kp:
        header["start_kp"] = start_kp
    if end_kp:
        header["end_kp"] = end_kp

    if "design_pressure_bar" not in header and "min_test_pressure_bar" in header:
        loc_str = str(header.get("location_class") or "")
        factor = 1.5 if ("Class 3" in loc_str or "Class 4" in loc_str) else 1.25
        header["design_pressure_bar"] = round(float(header["min_test_pressure_bar"]) / factor, 4)

    if proj_title := extract_project_name_from_text(text, max_lines=35):
        header.setdefault("project_name", proj_title)
    if sec_id := extract_page_section_no(text):
        header.setdefault("section_no", sec_id)

    payload: dict[str, Any] = {"header": header, "form_date": _extract_form_date(text)}
    log_entries: list[dict[str, Any]] = []

    if form_code == "filling":
        log = _parse_time_log(text)
        log_entries = list(log.get("entries") or [])
        temps: list[float] = []
        volumes: list[float] = []
        meter_readings: list[float] = []
        pressures: list[float] = []
        for ent in log["entries"]:
            nums = ent["nums"]
            # Typical row: Counter (m3), DeltaVol (m3), TotalVol (m3), WaterTemp (C), Pressure (Bar)
            if len(nums) >= 5:
                if nums[0] >= 0:
                    meter_readings.append(nums[0])
                if nums[2] >= 0:
                    volumes.append(nums[2])
                if -5.0 <= nums[3] <= 55.0:
                    temps.append(nums[3])
                if 0.0 <= nums[4] <= 300.0:
                    pressures.append(nums[4])
            elif len(nums) >= 2:
                if nums[0] >= 0:
                    meter_readings.append(nums[0])
                for val in nums:
                    if 0.0 <= val <= 45.0:
                        temps.append(val)
                        break
            elif len(nums) == 1 and nums[0] >= 0:
                volumes.append(nums[0])
        if not volumes and len(meter_readings) >= 2 and meter_readings[-1] > meter_readings[0]:
            volumes = [round(meter_readings[-1] - meter_readings[0], 3)]
        payload["time_log"] = {k: v for k, v in log.items() if k != "entries"}
        payload["filling"] = {
            "total_filled_m3": round(max(volumes), 3) if volumes else None,
            "min_temp_c": round(min(temps), 2) if temps else None,
            "max_temp_c": round(max(temps), 2) if temps else None,
            "max_pressure_bar": round(max(pressures), 2) if pressures else None,
        }

    elif form_code in {"leak_stabilization", "pressure_test"}:
        log = _parse_time_log(text)
        log_entries = list(log.get("entries") or [])
        block_stats = _extract_four_hour_temp_delta(log["entries"])
        pressures = [
            ent["nums"][0]
            for ent in log["entries"]
            if ent["nums"] and 1.0 <= ent["nums"][0] <= 400.0
        ]
        if (
            not pressures
            and not block_stats["probe_pair_count"]
            and int(log.get("row_count") or 0) >= 6
        ):
            col_stats = _extract_landscape_monitoring_columns(text, int(log["row_count"]))
            if col_stats["pressures"]:
                pressures = col_stats["pressures"]
            for stat_k in (
                "min_temp_c",
                "max_temp_c",
                "probe_pair_count",
                "block_avg_count",
                "last_4h_delta_c",
                "pipe_start_c",
                "pipe_end_c",
            ):
                if block_stats.get(stat_k) is None or block_stats.get(stat_k) == 0:
                    block_stats[stat_k] = col_stats[stat_k]

        pa_inline = _parse_num_after_label(
            text, (r"\bPA\s*\(\s*bar\s*\)\s*=?",), min_val=-50, max_val=50
        )
        dt_inline = _parse_num_after_label(
            text,
            (r"\b(?:dT|AT)\s*\(", r"\bOrt\.?\s*T\s*\(\s*°?C\s*\)\s*="),
            min_val=-20,
            max_val=20,
        )
        payload["time_log"] = {k: v for k, v in log.items() if k != "entries"}
        payload["monitoring"] = {
            **block_stats,
            "p_start_bar": pressures[0] if pressures else None,
            "p_end_bar": pressures[-1] if pressures else None,
            "pa_reported_bar": pa_inline,
            "delta_t_reported_c": dt_inline,
        }

    elif form_code in {"strength", "pressurization"}:
        log = _parse_time_log(text)
        log_entries = list(log.get("entries") or [])
        vp = _parse_num_after_label(text, (r"teorik\s*hacim\s*\(?v",), min_val=0.0001, max_val=100)
        vpa = _parse_num_after_label(text, (r"olculen\s*hacim\s*\(?v",), min_val=0.0, max_val=100)
        ratio_excess = _parse_num_after_label(
            text,
            (r"\(\s*v.{1,6}/v.?\s*\)\s*-?\s*1\s*[:=]", r"v.{1,4}/v.{1,4}\)\s*-?\s*1\s*[:=]"),
            min_val=-1.0,
            max_val=5.0,
        )
        # Inspect pressurization step rows
        pressures = []
        step_vols: list[float] = []
        cum_vols: list[float] = []
        pr_temps: list[float] = []
        for ent in log["entries"]:
            nums = ent["nums"]
            p_cands = [v for v in nums[:3] if 5.0 <= v <= 450.0]
            if len(nums) >= 4:
                pressures.extend(p_cands if p_cands else [nums[1]])
                step_vols.append(nums[2])
                cum_vols.append(nums[-2] if len(nums) >= 5 else nums[-1])
                if len(nums) >= 5 and -5.0 <= nums[-1] <= 55.0:
                    pr_temps.append(nums[-1])
            elif len(nums) >= 2:
                pressures.extend(p_cands if p_cands else [nums[1]])
                step_vols.append(nums[2] if len(nums) >= 3 else 0.0)
        payload["time_log"] = {k: v for k, v in log.items() if k != "entries"}
        payload["pressurization"] = {
            "vp_m3": vp,
            "vpa_m3": vpa,
            "excess_ratio": ratio_excess,
            "p_min_bar": min(pressures) if pressures else None,
            "p_max_bar": max(pressures) if pressures else None,
            "total_added_water_m3": max(cum_vols)
            if cum_vols
            else (round(sum(step_vols), 4) if step_vols else None),
            "temp_c": round(statistics.median(pr_temps), 2) if pr_temps else None,
        }

    elif form_code == "air_acceptance":
        param_text = _slice_after_params_header(text)
        vp = _parse_num_after_label(
            param_text,
            (r"\bVp\s*[:=]", r"gerekli\s*teorik\s*su\s*miktari", r"^vp$"),
            min_val=0.0001,
            max_val=100,
        )
        vpa = _parse_num_after_label(
            param_text,
            (r"\bVpa\s*[:=]", r"kullanilan\s*su\s*miktari", r"^vpa$"),
            min_val=0.0,
            max_val=100,
        )
        a_val = _parse_num_after_label(
            param_text,
            (r"\bA\s*[:=]", r"^a$", r"suyun\s*izotermal\s*sikis(?:tiril)?abilirlik\s*katsayisi"),
            min_val=1.0,
            max_val=200.0,
        )
        k_val = _parse_num_after_label(
            param_text,
            (r"\bK\s*[:=]", r"kaynakli\s*borular\s*icin\s*1[.,]02\s*[:=]?"),
            min_val=0.95,
            max_val=1.15,
        )
        p_diff = _parse_num_after_label(
            param_text, (r"olculen\s*basinc\s*degisimi\s*[:=]?",), min_val=0.1, max_val=50.0
        )
        vt = header.get("section_volume_m3") or _parse_num_after_label(
            param_text,
            (r"geometrik\s*hacmi", r"^vt$", r"\bV[t.]?\s*[:=]"),
            min_val=0.1,
            max_val=100_000,
        )
        excess = _parse_num_after_label(
            param_text, (r"\(\s*vpa\s*/\s*vp\s*\)\s*-?\s*1\s*[:=]",), min_val=-1.0, max_val=5.0
        )
        reported_pass = _parse_reported_passed(text)
        payload["air_acceptance"] = {
            "vp_m3": vp,
            "vpa_m3": vpa,
            "a_micro_per_bar": a_val,
            "k_factor": k_val or 1.02,
            "pressure_rise_bar": p_diff or 1.0,
            "vt_m3": vt,
            "excess_ratio": excess,
            "reported_passed": reported_pass,
        }

    elif form_code == "pressure_acceptance":
        param_text = _slice_after_params_header(text)
        pa = _parse_num_after_label(
            param_text,
            (r"olculen\s*basinc\s*degisimi\s*[:=]?", r"\bpa\s*[:=]", r"^pa$"),
            min_val=-50.0,
            max_val=50.0,
        )
        pt = _parse_num_after_label(
            param_text,
            (
                r"\b(?:dp|ap|pt)\s*[:=]",
                r"sicaklik\s*degisiminden\s*kaynaklanan\s*basinc\s*degisimi",
            ),
            min_val=-50.0,
            max_val=50.0,
        )
        dt = _parse_num_after_label(
            param_text,
            (r"\b(?:dt|at)\s*[:=]", r"su\s*sicakliginda\s*olusan\s*degisim\s*[:=]?"),
            min_val=-20.0,
            max_val=20.0,
        )
        b_val = _parse_num_after_label(
            param_text,
            (r"isil\s*genlesme\s*katsayilari\s*arasindaki\s*fark\s*[:=]?", r"\bB\s*[:=]", r"^b$"),
            min_val=-200.0,
            max_val=500.0,
        )
        a_val = _parse_num_after_label(
            param_text,
            (r"\bA\s*[:=]", r"^a$", r"suyun\s*izotermal\s*sikis(?:tiril)?abilirlik\s*katsayisi"),
            min_val=1.0,
            max_val=200.0,
        )
        pl_val = (
            _parse_num_after_label(param_text, (r"\bPL\s*[:=]",), min_val=0.01, max_val=5.0)
            or PRESSURE_VARIATION_ACCEPTANCE_BAR
        )
        diff_val = _parse_num_after_label(
            param_text, (r"\(\s*PA\s*-\s*(?:dp|ap|pt)\s*\)",), min_val=-50.0, max_val=50.0
        )
        # Disambiguate if PA matched ΔP on legacy two-column layouts where PA sat beside ΔP
        if pa is not None and pt is not None and diff_val is not None:
            if abs((pa - pt) - diff_val) > 0.05 and abs((pt - pa) - diff_val) <= 0.05:
                pa, pt = pt, pa
        reported_pass = _parse_reported_passed(text)
        payload["pressure_acceptance"] = {
            "pa_bar": pa,
            "pt_bar": pt,
            "delta_t_c": dt,
            "b_micro_per_c": b_val,
            "a_micro_per_bar": a_val,
            "pl_bar": pl_val,
            "pa_minus_pt_bar": diff_val,
            "reported_passed": reported_pass,
        }

    elif form_code in {"cleaning", "dewatering", "pre_drying", "final_drying"}:
        payload["pig_events"] = _extract_pig_events(text)

    struct_ext = build_form_structured_payload(form_code, text, time_log_entries=log_entries)
    for k, v in (struct_ext.get("header_extras") or {}).items():
        if v:
            header.setdefault(k, v)
    for opt_key in ("notes", "signatures", "test_data", "rows", "pig_runs", "drying", "parameters"):
        if opt_key in struct_ext and struct_ext[opt_key] is not None:
            payload[opt_key] = struct_ext[opt_key]

    return payload


# ---------------------------------------------------------------------------
# Section calculations & all 11 operational checkpoints evaluator
# ---------------------------------------------------------------------------


def evaluate_section_calculations(
    merged_header: dict[str, Any],
    forms_by_code: dict[str, dict[str, Any]],
    *,
    segments: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run domain hydrotest evaluations on extracted form parameters and return Pass/Fail results."""
    od = merged_header.get("outside_diameter_mm")
    wt = merged_header.get("wall_thickness_mm")
    length = merged_header.get("length_m")
    pipe: PipeSection | PipeGeometry | None = None
    valid_segs: list[PipeSection] = []
    if segments:
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            s_od = _finite_float(seg.get("outside_diameter_mm"))
            s_wt = _finite_float(seg.get("wall_thickness_mm"))
            s_len = _finite_float(seg.get("length_m"))
            s_smys = as_positive_float(seg.get("smys_mpa"))
            raw_grade = seg.get("material_grade")
            s_grade = raw_grade.strip() or None if isinstance(raw_grade, str) else None
            if s_od and s_wt and s_len and s_od > 2 * s_wt and s_len > 0:
                try:
                    valid_segs.append(
                        PipeSection(
                            outside_diameter_mm=s_od,
                            wall_thickness_mm=s_wt,
                            length_m=s_len,
                            smys_mpa=s_smys,
                            material_grade=s_grade,
                        )
                    )
                except ValidationError:
                    valid_segs = []
                    break
    if len(valid_segs) >= 2:
        try:
            pipe = PipeGeometry(sections=tuple(valid_segs))
            length = pipe.total_length_m
        except ValidationError:
            pipe = None
    elif len(valid_segs) == 1:
        pipe = valid_segs[0]
        length = pipe.length_m
    elif od and wt and length and od > 2 * wt and length > 0:
        try:
            pipe = PipeSection(
                outside_diameter_mm=float(od), wall_thickness_mm=float(wt), length_m=float(length)
            )
        except ValidationError:
            pipe = None

    # 1) Air Content Test evaluation
    air_data: dict[str, Any] = {}
    for code in ("air_acceptance", "strength", "pressurization"):
        block = (forms_by_code.get(code) or {}).get("extracted_data") or {}
        if "air_acceptance" in block:
            air_data = {**air_data, **block["air_acceptance"]}
        elif "pressurization" in block:
            pr = block["pressurization"]
            if pr.get("vp_m3") is not None:
                air_data.setdefault("vp_m3", pr["vp_m3"])
            if pr.get("vpa_m3") is not None:
                air_data.setdefault("vpa_m3", pr["vpa_m3"])

    air_eval: dict[str, Any] = {
        "status": "pending",
        "passed": None,
        "summary": "Hava içerik verisi henüz yok.",
    }
    vpa = air_data.get("vpa_m3")
    vp_rep = air_data.get("vp_m3")
    a_air = air_data.get("a_micro_per_bar")
    k_val_raw = air_data.get("k_factor")
    k_val = 1.02 if k_val_raw is None else k_val_raw
    if pipe is not None and a_air is not None and vpa is not None:
        try:
            res = evaluate_air_content_test(
                AirContentInputs(
                    pipe=pipe,
                    a_micro_per_bar=float(a_air),
                    pressure_rise_bar=1.0,
                    k_factor=float(k_val),
                    actual_added_water_m3=float(vpa),
                )
            )
            excess = (res.ratio - 1.0) * 100.0
            air_eval = {
                "status": "passed" if res.passed else "failed",
                "passed": res.passed,
                "vp_m3": round(res.theoretical_added_water_m3, 6),
                "vpa_m3": round(res.actual_added_water_m3, 6),
                "acceptance_limit_m3": round(res.acceptance_limit_m3, 6),
                "ratio": round(res.ratio, 6),
                "excess_pct": round(excess, 3),
                "a_micro_per_bar": float(a_air),
                "k_factor": float(k_val),
                "summary": (
                    f"{'BAŞARILI' if res.passed else 'BAŞARISIZ'}: Vpa={res.actual_added_water_m3:.5f} m³ / "
                    f"Vp={res.theoretical_added_water_m3:.5f} m³ (fazla hava %{excess:.2f}; sınır <%6)."
                ),
            }
        except ValidationError as exc:
            air_eval = {"status": "warning", "passed": None, "summary": str(exc)}
    elif vp_rep and vpa is not None and float(vp_rep) > 0:
        ratio = float(vpa) / float(vp_rep)
        limit_v = float(vp_rep) * AIR_CONTENT_ACCEPTANCE_FACTOR
        passed = float(vpa) < limit_v * (1.0 - 1e-9)
        excess = (ratio - 1.0) * 100.0
        air_eval = {
            "status": "passed" if passed else "failed",
            "passed": passed,
            "vp_m3": round(float(vp_rep), 6),
            "vpa_m3": round(float(vpa), 6),
            "acceptance_limit_m3": round(limit_v, 6),
            "ratio": round(ratio, 6),
            "excess_pct": round(excess, 3),
            "summary": (
                f"{'BAŞARILI' if passed else 'BAŞARISIZ'}: Rapor Vpa={float(vpa):.5f} m³ / "
                f"Vp={float(vp_rep):.5f} m³ (fazla hava %{excess:.2f}; sınır <%6)."
            ),
        }

    # 2) Pressure Variation Acceptance evaluation
    pr_acc = ((forms_by_code.get("pressure_acceptance") or {}).get("extracted_data") or {}).get(
        "pressure_acceptance"
    ) or {}
    pr_mon = ((forms_by_code.get("pressure_test") or {}).get("extracted_data") or {}).get(
        "monitoring"
    ) or {}

    pa_val = (
        pr_acc.get("pa_bar") if pr_acc.get("pa_bar") is not None else pr_mon.get("pa_reported_bar")
    )
    dt_val = (
        pr_acc.get("delta_t_c")
        if pr_acc.get("delta_t_c") is not None
        else pr_mon.get("delta_t_reported_c")
    )
    a_pres = pr_acc.get("a_micro_per_bar")
    b_pres = pr_acc.get("b_micro_per_c")
    pt_rep = pr_acc.get("pt_bar")
    pl_bar = float(PRESSURE_VARIATION_ACCEPTANCE_BAR)
    ocr_pl = _finite_float(pr_acc.get("pl_bar"))
    pl_note = (
        f" (rapor PL={ocr_pl:.2f} bar yok sayıldı)"
        if ocr_pl is not None and abs(ocr_pl - pl_bar) > 1e-3
        else ""
    )

    pressure_eval: dict[str, Any] = {
        "status": "pending",
        "passed": None,
        "summary": "Basınç değişim verisi henüz yok.",
    }
    if (
        pipe is not None
        and a_pres
        and b_pres is not None
        and dt_val is not None
        and pa_val is not None
    ):
        try:
            pressure_res = evaluate_pressure_variation_test(
                PressureVariationInputs(
                    pipe=pipe,
                    a_micro_per_bar=float(a_pres),
                    b_micro_per_c=float(b_pres),
                    delta_t_c=float(dt_val),
                    actual_pressure_change_bar=float(pa_val),
                )
            )
            pressure_eval = {
                "status": "passed" if pressure_res.passed else "failed",
                "passed": pressure_res.passed,
                "pa_bar": round(pressure_res.actual_pressure_change_bar, 4),
                "pt_bar": round(pressure_res.theoretical_pressure_change_bar, 4),
                "margin_bar": round(pressure_res.margin_bar, 4),
                "delta_t_c": float(dt_val),
                "a_micro_per_bar": float(a_pres),
                "b_micro_per_c": float(b_pres),
                "pl_bar": pl_bar,
                "summary": (
                    f"{'BAŞARILI' if pressure_res.passed else 'BAŞARISIZ'}: PA={pressure_res.actual_pressure_change_bar:.3f} bar, "
                    f"Pt={pressure_res.theoretical_pressure_change_bar:.3f} bar, (PA−Pt)={pressure_res.margin_bar:+.3f} bar "
                    f"(limit ≤ {pl_bar:.2f} bar){pl_note}."
                ),
            }
        except ValidationError as exc:
            pressure_eval = {"status": "warning", "passed": None, "summary": str(exc)}
    elif pa_val is not None and pt_rep is not None:
        margin = float(pa_val) - float(pt_rep)
        passed = margin <= pl_bar + 1e-9
        pressure_eval = {
            "status": "passed" if passed else "failed",
            "passed": passed,
            "pa_bar": round(float(pa_val), 4),
            "pt_bar": round(float(pt_rep), 4),
            "margin_bar": round(margin, 4),
            "pl_bar": pl_bar,
            "summary": (
                f"{'BAŞARILI' if passed else 'BAŞARISIZ'}: PA={float(pa_val):.3f} bar, "
                f"Pt={float(pt_rep):.3f} bar, (PA−Pt)={margin:+.3f} bar (limit ≤ {pl_bar:.2f} bar){pl_note}."
            ),
        }

    # 3) Pressure Profile & SMYS Feasibility evaluation
    design_p = _finite_float(merged_header.get("design_pressure_bar"))
    smys_mpa = as_positive_float(merged_header.get("smys_mpa"))
    if smys_mpa is None and valid_segs:
        seg_smys = [sec.smys_mpa for sec in valid_segs if sec.smys_mpa is not None]
        if len(seg_smys) == len(valid_segs):
            smys_mpa = min(seg_smys)
    h_high = _finite_float(merged_header.get("highest_elevation_m"))
    h_low = _finite_float(merged_header.get("lowest_elevation_m"))
    h_start = _finite_float(merged_header.get("start_elevation_m"))
    h_end = _finite_float(merged_header.get("end_elevation_m"))
    profile_eval: dict[str, Any] = {
        "status": "pending",
        "passed": None,
        "summary": "Basınç profili (kot/SMYS/dizayn basıncı) verisi henüz tam değil.",
    }
    if (
        pipe is not None
        and design_p
        and smys_mpa
        and all(v is not None for v in (h_high, h_low, h_start, h_end))
    ):
        raw_loc = str(merged_header.get("location_class") or "Class 1 - min 1.25 x dizayn basinci")
        try:
            loc_rule = get_location_class_rule(raw_loc)
        except ValidationError:
            raw_loc = "Class 1 - min 1.25 x dizayn basinci"
            loc_rule = get_location_class_rule(raw_loc)
        pump_loc = merged_header.get("pump_location")
        if pump_loc not in {START_PUMP_LOCATION, END_PUMP_LOCATION}:
            pump_loc = START_PUMP_LOCATION
        mon_p = _finite_float(merged_header.get("monitored_pressure_bar"))
        try:
            prof_res = evaluate_section_pressure_profile(
                SectionPressureProfileInputs(
                    pipe=pipe,
                    design_pressure_bar=float(design_p),
                    smys_mpa=float(smys_mpa),
                    location_class=loc_rule,
                    highest_elevation_m=float(h_high),  # type: ignore[arg-type]
                    lowest_elevation_m=float(h_low),  # type: ignore[arg-type]
                    start_elevation_m=float(h_start),  # type: ignore[arg-type]
                    end_elevation_m=float(h_end),  # type: ignore[arg-type]
                    selected_pump_location=pump_loc,
                    monitored_pressure_bar=mon_p,
                )
            )
            passed = bool(
                prof_res.feasible
                and prof_res.within_length_limit
                and prof_res.within_volume_limit
                and prof_res.within_100_smys_span_limit
                and (prof_res.monitored_meets_minimum is not False)
                and (prof_res.monitored_under_maximum is not False)
            )
            p_min_bar = round(prof_res.selected_window.minimum_required_pressure_bar, 2)
            p_max_bar = round(prof_res.selected_window.maximum_allowable_pressure_bar, 2)
            p_smys_bar = round(prof_res.limiting_pressure_at_100_smys_bar, 2)
            mon_note = f", Ps={mon_p:.2f} bar" if mon_p is not None else ""
            profile_eval = {
                "status": "passed" if passed else "failed",
                "passed": passed,
                "p_min_bar": p_min_bar,
                "p_max_bar": p_max_bar,
                "p_100_smys_bar": p_smys_bar,
                "limiting_pipe_description": prof_res.limiting_pipe_description,
                "limiting_smys_mpa": prof_res.limiting_smys_mpa,
                "hydraulic_span_bar": round(prof_res.hydraulic_span_bar, 2),
                "monitored_pressure_bar": mon_p,
                "location_class": raw_loc,
                "pump_location": pump_loc,
                "summary": (
                    f"{'BAŞARILI' if passed else 'BAŞARISIZ'}: Pmin={p_min_bar:.2f} bar, "
                    f"Pmax={p_max_bar:.2f} bar, %100 SMYS={p_smys_bar:.2f} bar{mon_note} "
                    f"({loc_rule.label.split(' - ')[0]})."
                ),
            }
        except ValidationError as exc:
            profile_eval = {"status": "warning", "passed": None, "summary": str(exc)}

    # 4) Pig Speed evaluation
    pig_eval: dict[str, Any] = {
        "status": "pending",
        "passed": None,
        "summary": "Pig hız verisi henüz yok.",
    }
    pig_t_min: float | None = None
    for code in ("dewatering", "cleaning"):
        pig_ev = ((forms_by_code.get(code) or {}).get("extracted_data") or {}).get(
            "pig_events"
        ) or {}
        cand_t = _finite_float(pig_ev.get("travel_time_min"))
        if cand_t is not None and cand_t > 0:
            pig_t_min = cand_t
            break
    if length and float(length) > 0 and pig_t_min is not None and pig_t_min > 0:
        try:
            pig_limit = get_pig_speed_limit("Temizlik pigi | max 2.500 m/sn | Madde 9")
            pig_res = evaluate_pig_speed(
                distance_m=float(length),
                travel_time_min=float(pig_t_min),
                limit=pig_limit,
            )
            pig_eval = {
                "status": "passed" if pig_res.passed else "failed",
                "passed": pig_res.passed,
                "distance_m": round(pig_res.distance_m, 2),
                "travel_time_min": round(pig_res.travel_time_min, 2),
                "speed_m_per_s": round(pig_res.speed_m_per_s, 3),
                "speed_km_per_h": round(pig_res.speed_km_per_h, 2),
                "mode": "Temizlik pigi",
                "summary": (
                    f"{'BAŞARILI' if pig_res.passed else 'BAŞARISIZ'}: "
                    f"{pig_res.speed_m_per_s:.2f} m/s ({pig_res.speed_km_per_h:.2f} km/h; "
                    f"sınır ≤ {pig_limit.max_speed_m_per_s:.2f} m/s)."
                ),
            }
        except ValidationError as exc:
            pig_eval = {"status": "warning", "passed": None, "summary": str(exc)}

    return {
        "air": air_eval,
        "pressure": pressure_eval,
        "profile": profile_eval,
        "pig": pig_eval,
    }


def evaluate_operational_checks(
    merged_header: dict[str, Any],
    forms_by_code: dict[str, dict[str, Any]],
    calculations: dict[str, Any],
) -> tuple[dict[str, bool], dict[str, dict[str, Any]]]:
    """Automatically evaluate all 11 NGTL 5007 operational checkpoints from scanned forms."""
    fill_form = forms_by_code.get("filling")
    leak_form = forms_by_code.get("leak_stabilization")
    strength_form = forms_by_code.get("strength")
    press_form = forms_by_code.get("pressurization")
    air_form = forms_by_code.get("air_acceptance")
    pt_form = forms_by_code.get("pressure_test")
    dewat_form = forms_by_code.get("dewatering")

    fill_data = (fill_form or {}).get("extracted_data") or {}
    leak_data = (leak_form or {}).get("extracted_data") or {}
    strength_data = (strength_form or {}).get("extracted_data") or {}
    press_data = (press_form or {}).get("extracted_data") or {}
    pt_data = (pt_form or {}).get("extracted_data") or {}
    dewat_data = (dewat_form or {}).get("extracted_data") or {}

    details: dict[str, dict[str, Any]] = {}

    def _set(
        key: str,
        label: str,
        ref: str,
        *,
        checked: bool,
        status: str,
        message: str,
        sources: list[str],
    ) -> None:
        details[key] = {
            "key": key,
            "label": label,
            "ref": ref,
            "checked": checked,
            "status": status,
            "message": message,
            "source_forms": sources,
        }

    meta_by_key = {k: (lbl, ref) for k, lbl, ref in FIELD_CHECKS}

    # 1) ambient_temp (10.1): Dolum / ortam hava sıcaklığı >= +2 °C
    lbl, ref = meta_by_key["ambient_temp"]
    fill_min_t = _finite_float((fill_data.get("filling") or {}).get("min_temp_c"))
    leak_min_t = _finite_float((leak_data.get("monitoring") or {}).get("min_temp_c"))
    manual_ambient_t = _finite_float(merged_header.get("ambient_temperature_c"))
    form_temps = [t for t in (fill_min_t, leak_min_t) if t is not None]
    observed_temps = [t for t in (fill_min_t, leak_min_t, manual_ambient_t) if t is not None]
    if observed_temps:
        min_t = min(observed_temps)
        try:
            fill_eval = evaluate_fill_temperature(min_t)
            ok = fill_eval.passed
            eval_msg = fill_eval.message
        except ValidationError as exc:
            ok = False
            eval_msg = str(exc)
        ambient_sources: list[str] = []
        if fill_min_t is not None and fill_form:
            ambient_sources.append(fill_form["form_code"])
        if leak_min_t is not None and leak_form:
            ambient_sources.append(leak_form["form_code"])
        if manual_ambient_t is not None and (not form_temps or manual_ambient_t <= min(form_temps)):
            ambient_sources.append("manual_input")
        _set(
            "ambient_temp",
            lbl,
            ref,
            checked=ok,
            status="passed" if ok else "failed",
            message=eval_msg,
            sources=ambient_sources,
        )
    else:
        _set(
            "ambient_temp",
            lbl,
            ref,
            checked=False,
            status="pending",
            message="Su Dolum (017), Kaçak Dengeleme (018) veya saha ortam sıcaklığı verisi bulunmadı.",
            sources=[],
        )

    # 2) temp_probes (10.4): Toprak ve boru sıcaklık probları
    lbl, ref = meta_by_key["temp_probes"]
    leak_mon = leak_data.get("monitoring") or {}
    pt_mon = pt_data.get("monitoring") or {}
    pairs_count = max(
        int(leak_mon.get("probe_pair_count") or 0), int(pt_mon.get("probe_pair_count") or 0)
    )
    if pairs_count >= 2:
        _set(
            "temp_probes",
            lbl,
            ref,
            checked=True,
            status="passed",
            message=f"Toprak ve boru sıcaklık prob okumaları doğrulandı ({pairs_count} zaman satırında çift kayıt).",
            sources=[f["form_code"] for f in (leak_form, pt_form) if f],
        )
    elif leak_form or pt_form:
        _set(
            "temp_probes",
            lbl,
            ref,
            checked=False,
            status="warning",
            message="Kaçak/Basınç formunda toprak-boru prob eşleşmesi eksik veya okunamadı; saha kontrolü önerilir.",
            sources=[f["form_code"] for f in (leak_form, pt_form) if f],
        )
    else:
        _set(
            "temp_probes",
            lbl,
            ref,
            checked=False,
            status="pending",
            message="Dengeleme (018) veya Basınç Testi (021) formu yüklenmedi.",
            sources=[],
        )

    # 3) fill_air_entry (11.2): Su dolumunda hava girişi engellendi (dolum pigi + hava < %6)
    lbl, ref = meta_by_key["fill_air_entry"]
    air_calc = calculations.get("air") or {}
    if fill_form and air_calc.get("passed") is True:
        _set(
            "fill_air_entry",
            lbl,
            ref,
            checked=True,
            status="passed",
            message=f"Su Dolum Raporu mevcut ve Hava İçerik Testi %{abs(air_calc.get('excess_pct') or 0):.2f} (<%6) ile geçti.",
            sources=[f["form_code"] for f in (fill_form, air_form) if f],
        )
    elif air_calc.get("passed") is False:
        _set(
            "fill_air_entry",
            lbl,
            ref,
            checked=False,
            status="failed",
            message=f"Hava İçerik Testi sınırı aşıldı ({air_calc.get('summary', '')}); hatta hava kalmış olabilir.",
            sources=[f["form_code"] for f in (fill_form, air_form) if f],
        )
    elif fill_form:
        _set(
            "fill_air_entry",
            lbl,
            ref,
            checked=False,
            status="warning",
            message="Su Dolum Raporu var ancak Hava İçerik Kabul (020) doğrulaması tamamlanmadı.",
            sources=["filling"],
        )
    else:
        _set(
            "fill_air_entry",
            lbl,
            ref,
            checked=False,
            status="pending",
            message="Su Dolum (017) ve Hava İçerik (020) formları bekleniyor.",
            sources=[],
        )

    # 4) fill_records (11.3-11.4): Doldurulan su hacmi ve sıcaklığı saatlik kaydedildi
    lbl, ref = meta_by_key["fill_records"]
    fill_log = fill_data.get("time_log") or {}
    fill_rows = int(fill_log.get("row_count") or 0)
    fill_med = fill_log.get("median_step_min")
    fill_gap = float(fill_log.get("max_gap_min") or 0.0)
    fill_vol = (fill_data.get("filling") or {}).get("total_filled_m3")
    if fill_form and fill_rows >= 2:
        hourly_ok = fill_med is not None and 30.0 <= float(fill_med) <= 75.0 and fill_gap <= 120.0
        if hourly_ok:
            vol_txt = f", toplam {fill_vol:.1f} m³" if fill_vol is not None else ""
            _set(
                "fill_records",
                lbl,
                ref,
                checked=True,
                status="passed",
                message=(
                    f"Su Dolum Raporu'nda {fill_rows} satır ({fill_log.get('first_time')}–{fill_log.get('last_time')}, "
                    f"ort. aralık {fill_med:.0f} dk{vol_txt}) saatlik hacim/sıcaklık kaydı doğrulandı."
                ),
                sources=["filling"],
            )
        else:
            _set(
                "fill_records",
                lbl,
                ref,
                checked=False,
                status="warning",
                message=f"Su Dolum tablosunda {fill_rows} satır okundu ancak okuma aralığı düzensiz (maks boşluk {fill_gap:.0f} dk).",
                sources=["filling"],
            )
    elif fill_form:
        _set(
            "fill_records",
            lbl,
            ref,
            checked=False,
            status="warning",
            message="Su Dolum Raporu (017) yüklendi ancak Okuma Saati sütununda saatlik zaman kaydı okunamadı; saha logunu kontrol edin.",
            sources=["filling"],
        )
    else:
        _set(
            "fill_records",
            lbl,
            ref,
            checked=False,
            status="pending",
            message="Su Dolum Raporu (017) yüklenmedi veya saatlik tablo okunamadı.",
            sources=[],
        )

    # 5) thermal_balance (12): Minimum 24 saat termal dengeleme ve 0,5 °C koşulu
    lbl, ref = meta_by_key["thermal_balance"]
    leak_log = leak_data.get("time_log") or {}
    leak_dur = float(leak_log.get("duration_hours") or 0.0)
    leak_delta = leak_mon.get("last_4h_delta_c")
    if leak_form and int(leak_log.get("row_count") or 0) >= 2:
        dur_ok = leak_dur >= THERMAL_BALANCE_MIN_HOURS - 1e-9
        if (
            dur_ok
            and leak_delta is not None
            and float(leak_delta) <= THERMAL_BALANCE_THRESHOLD_C + 1e-9
        ):
            _set(
                "thermal_balance",
                lbl,
                ref,
                checked=True,
                status="passed",
                message=(
                    f"Dengeleme süresi {leak_dur:.1f} sa (≥24 sa) ve son 4 saatlik blok sıcaklık farkı "
                    f"|ΔT|={float(leak_delta):.2f} °C (≤0,50 °C) koşulunu sağladı."
                ),
                sources=["leak_stabilization"],
            )
        elif not dur_ok:
            _set(
                "thermal_balance",
                lbl,
                ref,
                checked=False,
                status="failed" if leak_dur > 0 else "warning",
                message=f"Dengeleme süresi {leak_dur:.1f} sa; şartname minimumu {THERMAL_BALANCE_MIN_HOURS:.0f} saattir.",
                sources=["leak_stabilization"],
            )
        else:
            msg_delta = (
                f"|ΔT|={float(leak_delta):.2f} °C (>0,50 °C)"
                if leak_delta is not None
                else "4 saatlik ortalama farkı hesaplanamadı"
            )
            _set(
                "thermal_balance",
                lbl,
                ref,
                checked=False,
                status="failed" if leak_delta is not None else "warning",
                message=f"Süre {leak_dur:.1f} sa ancak termal denge farkı: {msg_delta}.",
                sources=["leak_stabilization"],
            )
    else:
        _set(
            "thermal_balance",
            lbl,
            ref,
            checked=False,
            status="pending",
            message="Dengeleme İçin Kaçak Test Raporu (018) yüklenmedi.",
            sources=[],
        )

    # 6) air_content_limit (13): %6 kabul sınırı
    lbl, ref = meta_by_key["air_content_limit"]
    if air_calc.get("passed") is True:
        _set(
            "air_content_limit",
            lbl,
            ref,
            checked=True,
            status="passed",
            message=air_calc["summary"],
            sources=[f["form_code"] for f in (air_form, strength_form) if f],
        )
    elif air_calc.get("passed") is False:
        _set(
            "air_content_limit",
            lbl,
            ref,
            checked=False,
            status="failed",
            message=air_calc["summary"],
            sources=[f["form_code"] for f in (air_form, strength_form) if f],
        )
    else:
        _set(
            "air_content_limit",
            lbl,
            ref,
            checked=False,
            status="pending",
            message="Hava İçerik Testi Kabul Raporu (020) bekleniyor.",
            sources=[],
        )

    # 7) pressurization_volume (14.2): Basınçlandırma P-V logu ve %0,2 ilave su limiti
    lbl, ref = meta_by_key["pressurization_volume"]
    str_log = strength_data.get("time_log") or {}
    pr_log = press_data.get("time_log") or {}
    str_pr = strength_data.get("pressurization") or {}
    pr_pr = press_data.get("pressurization") or {}
    vt_geom = merged_header.get("section_volume_m3")
    filled_m3 = (fill_data.get("filling") or {}).get("total_filled_m3")
    press_added = (
        pr_pr.get("total_added_water_m3")
        if pr_pr.get("total_added_water_m3") is not None
        else str_pr.get("total_added_water_m3")
    )
    if strength_form or press_form:
        has_pv = int(str_log.get("row_count") or 0) >= 3 or int(pr_log.get("row_count") or 0) >= 3
        if (
            has_pv
            and vt_geom
            and float(vt_geom) > 0
            and filled_m3 is not None
            and press_added is not None
            and float(filled_m3) > 0
        ):
            # Verify Madde 14.2: compare pressurized volume against geometric volume (detect both overfill & underfill)
            total_filled = float(filled_m3) + float(press_added)
            signed_dev_pct = ((total_filled - float(vt_geom)) / float(vt_geom)) * 100.0
            excess_dev_pct = (
                ((total_filled - float(vt_geom)) / total_filled) * 100.0
                if total_filled > 0
                else 0.0
            )
            underfill_limit_m3 = float(vt_geom) * (
                1.0 - PRESSURIZATION_VOLUME_DEVIATION_LIMIT_PERCENT / 100.0
            )
            p_span = f"{pr_pr.get('p_min_bar') or str_pr.get('p_min_bar') or '?'}–{pr_pr.get('p_max_bar') or str_pr.get('p_max_bar') or '?'} bar"
            if total_filled < underfill_limit_m3 - 1e-9:
                _set(
                    "pressurization_volume",
                    lbl,
                    ref,
                    checked=False,
                    status="failed" if signed_dev_pct < -5.0 else "warning",
                    message=(
                        f"Basınçlandırılan toplam su hacmi ({total_filled:.2f} m³), geometrik hacmin "
                        f"({float(vt_geom):.2f} m³) altında (sapma %{signed_dev_pct:+.2f}); sayaç/dolum kaydını kontrol edin."
                    ),
                    sources=[f["form_code"] for f in (strength_form, press_form) if f],
                )
            elif excess_dev_pct <= PRESSURIZATION_VOLUME_DEVIATION_LIMIT_PERCENT + 1e-9:
                _set(
                    "pressurization_volume",
                    lbl,
                    ref,
                    checked=True,
                    status="passed",
                    message=(
                        f"Basınç-hacim adım kayıtları ({p_span}, test suyu ilavesi {float(press_added):.3f} m³; "
                        f"geometrik hacim {float(vt_geom):.2f} m³) doğrulandı."
                    ),
                    sources=[f["form_code"] for f in (strength_form, press_form) if f],
                )
            else:
                _set(
                    "pressurization_volume",
                    lbl,
                    ref,
                    checked=False,
                    status="warning",
                    message=(
                        f"Basınç-hacim kaydı okundu (fazla su sapması %{excess_dev_pct:.2f}, limit %{PRESSURIZATION_VOLUME_DEVIATION_LIMIT_PERCENT:.1f}); "
                        "saha sayacı başlangıç/bitiş değerlerini doğrulayın."
                    ),
                    sources=[f["form_code"] for f in (strength_form, press_form) if f],
                )
        elif has_pv:
            _set(
                "pressurization_volume",
                lbl,
                ref,
                checked=False,
                status="warning",
                message="Mukavemet / Basınçlandırma adım-hacim kayıtları mevcut ancak %0,2 hacim kontrolü için dolum sayacı / Vsec eksik.",
                sources=[f["form_code"] for f in (strength_form, press_form) if f],
            )
        else:
            _set(
                "pressurization_volume",
                lbl,
                ref,
                checked=False,
                status="warning",
                message="Mukavemet/Basınçlandırma formunda P-V tablo satırları yetersiz.",
                sources=[f["form_code"] for f in (strength_form, press_form) if f],
            )
    else:
        _set(
            "pressurization_volume",
            lbl,
            ref,
            checked=False,
            status="pending",
            message="Mukavemet (019) / Basınçlandırma formu yüklenmedi.",
            sources=[],
        )

    # 8) two_hour_hold (14.3): 2 saat bekleme ve 15 dakikalık okumalar
    lbl, ref = meta_by_key["two_hour_hold"]
    hold_ok = False
    for log_cand in (pr_log, str_log):
        rows = int(log_cand.get("row_count") or 0)
        dur_h = float(log_cand.get("duration_hours") or 0.0)
        med = log_cand.get("median_step_min")
        if rows >= 7 and dur_h >= 1.8 and med is not None and 10.0 <= float(med) <= 20.0:
            hold_ok = True
            _set(
                "two_hour_hold",
                lbl,
                ref,
                checked=True,
                status="passed",
                message=f"{dur_h:.2f} saat boyunca ~{float(med):.0f} dk aralıklı {rows} adet bekleme okuması doğrulandı.",
                sources=[f["form_code"] for f in (press_form, strength_form) if f],
            )
            break

    if not hold_ok:
        pr_src_log = pr_log if pr_log.get("last_abs_min") is not None else str_log
        pr_end = pr_src_log.get("last_abs_min")
        pt_log_safe = pt_data.get("time_log") or {}
        pt_start = pt_log_safe.get("first_abs_min")
        if pr_end is not None and pt_start is not None:
            gap_min = float(pt_start) - float(pr_end)
            if gap_min < 0:
                gap_min += 24 * 60
            if 105.0 <= gap_min <= 240.0:
                _set(
                    "two_hour_hold",
                    lbl,
                    ref,
                    checked=False,
                    status="warning",
                    message=(
                        f"Basınçlandırma bitişi ({pr_src_log.get('last_time') or '?'}) ile "
                        f"Basınç Testi başlangıcı ({pt_log_safe.get('first_time') or '?'}) arasında {gap_min / 60.0:.2f} saatlik bekleme "
                        "görülüyor; ancak 15 dakikalık ara okuma tablosu dokümanda bulunmadığı için manuel teyit gerekir."
                    ),
                    sources=[f["form_code"] for f in (press_form, strength_form, pt_form) if f],
                )
            else:
                _set(
                    "two_hour_hold",
                    lbl,
                    ref,
                    checked=False,
                    status="warning",
                    message=f"Şartname Madde 14.3 kapsamında 2 saat bekleme + 15 dakikalık okuma kayıtları formlarda tespit edilemedi (aralık {gap_min:.0f} dk).",
                    sources=[f["form_code"] for f in (press_form, strength_form, pt_form) if f],
                )
        elif press_form or strength_form or pt_form:
            _set(
                "two_hour_hold",
                lbl,
                ref,
                checked=False,
                status="warning",
                message="14.3 kapsamındaki 2 saatlik bekleme ve 15 dakikalık ara okuma satırları raporda bulunamadı.",
                sources=[f["form_code"] for f in (press_form, strength_form, pt_form) if f],
            )
        else:
            _set(
                "two_hour_hold",
                lbl,
                ref,
                checked=False,
                status="pending",
                message="Basınçlandırma ve 24 saatlik Basınç Testi (021) formları bekleniyor.",
                sources=[],
            )

    # 9) pressure_records (15.1): 24 saatlik basınç ve sıcaklık kayıtları
    lbl, ref = meta_by_key["pressure_records"]
    pt_log = pt_data.get("time_log") or {}
    pt_rows = int(pt_log.get("row_count") or 0)
    pt_dur = float(pt_log.get("duration_hours") or 0.0)
    pt_gap = float(pt_log.get("max_gap_min") or 0.0)
    if pt_form and pt_rows >= 2:
        ok = pt_dur >= THERMAL_BALANCE_MIN_HOURS - 1e-9 and pt_gap <= 120.0
        _set(
            "pressure_records",
            lbl,
            ref,
            checked=ok,
            status="passed" if ok else "failed",
            message=(
                f"Basınç Testi Raporu'nda {pt_dur:.1f} saat ({pt_log.get('first_time')}–{pt_log.get('last_time')}, "
                f"{pt_rows} okuma; P={pt_mon.get('p_start_bar') or '?'}→{pt_mon.get('p_end_bar') or '?'} bar) doğrulandı."
                if ok
                else f"Basınç Testi kayıt süresi {pt_dur:.1f} sa (≥24 sa ve maks boşluk ≤120 dk olmalı; maks boşluk {pt_gap:.0f} dk)."
            ),
            sources=["pressure_test"],
        )
    else:
        _set(
            "pressure_records",
            lbl,
            ref,
            checked=False,
            status="pending",
            message="Basınç Testi Raporu (021) yüklenmedi.",
            sources=[],
        )

    # 10) depressurize_discharge (16-17): Basınç düşürme ve boşaltma (023)
    lbl, ref = meta_by_key["depressurize_discharge"]
    pig_ev = dewat_data.get("pig_events") or {}
    ops_eval = (
        evaluate_dewatering_operations(
            str((dewat_form or {}).get("form_date") or dewat_data.get("form_date") or ""),
            dewat_data,
        )
        if dewat_form
        else {"depressurization": None, "discharge": None}
    )
    dep_eval = ops_eval.get("depressurization")
    dis_eval = ops_eval.get("discharge")

    if dep_eval is not None or dis_eval is not None:
        speed_ms: float | None = None
        pig_speed_ok: bool | None = None
        if pig_ev.get("has_events"):
            t_min = pig_ev.get("travel_time_min")
            length_m = merged_header.get("length_m")
            if t_min and length_m and float(t_min) > 0 and float(length_m) > 0:
                speed_ms = float(length_m) / (float(t_min) * 60.0)
                limit = get_pig_speed_limit("Temizlik pigi | max 2.500 m/sn | Madde 9")
                pig_speed_ok = speed_ms <= (limit.max_speed_m_per_s or 2.5) + 1e-9

        dep_st = dep_eval["status"] if dep_eval else None
        dis_st = dis_eval["status"] if dis_eval else None
        fail_msgs = [
            ev["message"] for ev in (dep_eval, dis_eval) if ev and ev["status"] == "failed"
        ]
        warn_msgs = [
            ev["message"] for ev in (dep_eval, dis_eval) if ev and ev["status"] == "warning"
        ]
        speed_txt = f"Ortalama pig hızı {speed_ms:.2f} m/s." if speed_ms is not None else ""

        if pig_speed_ok is False or dep_st == "failed" or dis_st == "failed":
            parts = []
            if pig_speed_ok is False and speed_ms is not None:
                parts.append(f"Boşaltma pig hızı sınırı aşıyor ({speed_ms:.2f} m/s).")
            parts.extend(fail_msgs or warn_msgs)
            _set(
                "depressurize_discharge",
                lbl,
                ref,
                checked=False,
                status="failed",
                message=" ".join(p for p in parts if p),
                sources=["dewatering"],
            )
        elif dep_st == "warning" or dis_st == "warning":
            parts = list(warn_msgs)
            if speed_txt:
                parts.append(speed_txt)
            _set(
                "depressurize_discharge",
                lbl,
                ref,
                checked=False,
                status="warning",
                message=" ".join(p for p in parts if p),
                sources=["dewatering"],
            )
        elif pig_speed_ok is True:
            done_tags = [
                tag
                for tag, ev in (("Md. 16", dep_eval), ("Md. 17", dis_eval))
                if ev and ev["status"] == "passed"
            ]
            ops_txt = f" ({' & '.join(done_tags)} uygun)" if done_tags else ""
            _set(
                "depressurize_discharge",
                lbl,
                ref,
                checked=True,
                status="passed",
                message=(
                    f"Boşaltma Kabul Raporu (023) ({pig_ev.get('first_time')}–{pig_ev.get('last_time')}, "
                    f"ortalama pig hızı {speed_ms:.2f} m/s){ops_txt}."
                ),
                sources=["dewatering"],
            )
        elif dep_st == "passed" and dis_st == "passed":
            _set(
                "depressurize_discharge",
                lbl,
                ref,
                checked=True,
                status="passed",
                message="Boşaltma Kabul Raporu (023) Md. 16 basınç düşürme ve Md. 17 boşaltma kontrolleri uygun.",
                sources=["dewatering"],
            )
        else:
            completed = "Md. 16 basınç düşürme" if dep_st == "passed" else "Md. 17 boşaltma"
            other = "Md. 17 boşaltma" if dep_st == "passed" else "Md. 16 basınç düşürme"
            _set(
                "depressurize_discharge",
                lbl,
                ref,
                checked=False,
                status="warning",
                message=f"Boşaltma Kabul Raporu (023): {completed} uygun; {other} veya pig hızı doğrulaması bekleniyor.",
                sources=["dewatering"],
            )
    elif dewat_form and pig_ev.get("has_events"):
        t_min = pig_ev.get("travel_time_min")
        length_m = merged_header.get("length_m")
        if t_min and length_m and float(t_min) > 0 and float(length_m) > 0:
            speed_ms = float(length_m) / (float(t_min) * 60.0)
            limit = get_pig_speed_limit("Temizlik pigi | max 2.500 m/sn | Madde 9")
            ok = speed_ms <= (limit.max_speed_m_per_s or 2.5) + 1e-9
            _set(
                "depressurize_discharge",
                lbl,
                ref,
                checked=ok,
                status="passed" if ok else "failed",
                message=f"Boşaltma Kabul Raporu (023) ({pig_ev.get('first_time')}–{pig_ev.get('last_time')}, ortalama pig hızı {speed_ms:.2f} m/s).",
                sources=["dewatering"],
            )
        else:
            _set(
                "depressurize_discharge",
                lbl,
                ref,
                checked=False,
                status="warning",
                message=f"Boşaltma Kabul Raporu (023) ({pig_ev.get('first_time')}–{pig_ev.get('last_time')}) yüklendi ancak pig hız kontrolü için hat boyu veya seyahat süresi eksik.",
                sources=["dewatering"],
            )
    elif dewat_form:
        _set(
            "depressurize_discharge",
            lbl,
            ref,
            checked=False,
            status="warning",
            message="Boşaltma Kabul Raporu var ancak pig atılış/alış saatleri okunamadı.",
            sources=["dewatering"],
        )
    else:
        _set(
            "depressurize_discharge",
            lbl,
            ref,
            checked=False,
            status="pending",
            message="Boşaltma Kabul Raporu (023) bekleniyor.",
            sources=[],
        )

    # 11) forms (21): Zorunlu 11 formun tamamının doldurulmuş olması
    lbl, ref = meta_by_key["forms"]
    missing_req = [
        f"{spec.title} ({spec.botas_code})"
        for spec in REQUIRED_FORM_SPECS
        if spec.code not in forms_by_code
        or (forms_by_code[spec.code].get("status") or "empty") == "empty"
    ]
    present_count = len(REQUIRED_FORM_SPECS) - len(missing_req)
    if not missing_req:
        _set(
            "forms",
            lbl,
            ref,
            checked=True,
            status="passed",
            message=f"Tüm zorunlu formlar tamamlandı ({present_count}/{len(REQUIRED_FORM_SPECS)}).",
            sources=list(forms_by_code.keys()),
        )
    else:
        preview = ", ".join(missing_req[:3]) + (
            f" (+{len(missing_req) - 3} form)" if len(missing_req) > 3 else ""
        )
        _set(
            "forms",
            lbl,
            ref,
            checked=False,
            status="warning" if present_count > 0 else "pending",
            message=f"{present_count}/{len(REQUIRED_FORM_SPECS)} zorunlu form mevcut. Eksik ({len(missing_req)}): {preview}.",
            sources=list(forms_by_code.keys()),
        )

    checks_bool = {k: bool(v["checked"]) for k, v in details.items()}
    return checks_bool, details


# ---------------------------------------------------------------------------
# Dossier Analyzer (multi-section + multi-form grouping from extracted pages)
# ---------------------------------------------------------------------------


def _merge_section_header(
    forms_by_code: dict[str, dict[str, Any]],
    *,
    doc_defaults: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    # Prefer test_data / air_acceptance / pressure_acceptance / filling / strength / dewatering ordering
    priority = (
        "test_data",
        "air_acceptance",
        "pressure_acceptance",
        "strength",
        "filling",
        "pressure_test",
        "leak_stabilization",
        "pressurization",
        "calculation_sheet",
        "dewatering",
        "cleaning",
        "pre_drying",
        "final_drying",
        "spool_test",
    )
    ordered_codes = [*priority, *[c for c in forms_by_code if c not in priority]]
    for code in ordered_codes:
        entry = forms_by_code.get(code)
        if not entry:
            continue
        hdr = (entry.get("extracted_data") or {}).get("header") or {}
        for k, v in hdr.items():
            if v is not None and v != "" and k not in merged:
                merged[k] = v

    if doc_defaults:
        for k, v in doc_defaults.items():
            if v is not None and v != "" and k not in merged:
                merged[k] = v

    od = _finite_float(merged.get("outside_diameter_mm"))
    id_mm = _finite_float(merged.get("inside_diameter_mm"))
    if not merged.get("wall_thickness_mm") and od and id_mm and od > id_mm > 0:
        merged["wall_thickness_mm"] = round((od - id_mm) / 2.0, 2)

    if not merged.get("design_pressure_bar") and merged.get("min_test_pressure_bar"):
        loc_str = str(merged.get("location_class") or "")
        factor = 1.5 if ("Class 3" in loc_str or "Class 4" in loc_str) else 1.25
        merged["design_pressure_bar"] = round(float(merged["min_test_pressure_bar"]) / factor, 4)

    return merged


def _apply_calc_statuses_to_forms(
    forms_by_code: dict[str, dict[str, Any]],
    calculations: dict[str, Any],
) -> None:
    if "air_acceptance" in forms_by_code:
        st = (calculations.get("air") or {}).get("status")
        if st in {"passed", "failed"}:
            forms_by_code["air_acceptance"]["status"] = st
    if "pressure_acceptance" in forms_by_code:
        st = (calculations.get("pressure") or {}).get("status")
        if st in {"passed", "failed"}:
            forms_by_code["pressure_acceptance"]["status"] = st
    prof_st = (calculations.get("profile") or {}).get("status")
    if prof_st in {"passed", "failed"}:
        if "calculation_sheet" in forms_by_code:
            forms_by_code["calculation_sheet"]["status"] = prof_st
        if "test_data" in forms_by_code and forms_by_code["test_data"].get("status") == "filled":
            forms_by_code["test_data"]["status"] = prof_st


def _apply_findings_and_statuses(
    merged_header: dict[str, Any],
    forms_by_code: dict[str, dict[str, Any]],
    calculations: dict[str, Any],
    check_details: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    findings_by_code = evaluate_all_form_findings(
        merged_header, forms_by_code, calculations, check_details
    )
    for code, entry in forms_by_code.items():
        if entry.get("status") == "empty":
            continue
        ext = dict(entry.get("extracted_data") or {})
        f_list = findings_by_code.get(code, [])
        ext["findings"] = f_list
        entry["extracted_data"] = ext
        statuses = [str((f or {}).get("status") or "") for f in f_list]
        if "failed" in statuses:
            entry["status"] = "failed"
        elif "warning" in statuses:
            if (
                code not in {"air_acceptance", "pressure_acceptance"}
                or entry.get("status") == "filled"
            ):
                entry["status"] = "warning"
        elif "passed" in statuses:
            if entry.get("status") in {"filled", "warning", "passed"}:
                entry["status"] = "passed"
    return findings_by_code


def _synthesize_fallback_section(
    fallback_report: dict[str, Any],
    *,
    source_filename: str,
    page_count: int,
) -> dict[str, Any] | None:
    """Build one normalized dossier section when single-report extraction found numeric metrics without BOTAŞ titles."""

    def _val(path: str) -> Any:
        cur: Any = fallback_report
        for part in path.split("."):
            if not isinstance(cur, dict):
                return None
            cur = cur.get(part)
        if isinstance(cur, dict) and "value" in cur:
            return cur.get("value")
        return None

    def _num(path: str) -> float | None:
        return _finite_float(_val(path))

    numeric_hits = sum(
        1
        for p in (
            "pipe_od_mm",
            "wall_mm",
            "length_m",
            "air_test.vpa",
            "pressure_test.pa",
            "pressure_test.delta_t",
            "test_pressure_bar",
            "max_operating_pressure_bar",
        )
        if _num(p) is not None
    )
    if numeric_hits < 2:
        return None

    raw_sec = str(_val("section_id") or "").strip()
    sec_no = normalize_section_no(raw_sec) or "BÖLÜM 1"
    header: dict[str, Any] = {}
    if (od := _num("pipe_od_mm")) is not None:
        header["outside_diameter_mm"] = od
    if (id_mm := _num("pipe_id_mm")) is not None:
        header["inside_diameter_mm"] = id_mm
    if (wt := _num("wall_mm")) is not None:
        header["wall_thickness_mm"] = wt
    elif od and id_mm and od > id_mm > 0:
        header["wall_thickness_mm"] = round((od - id_mm) / 2.0, 2)
    if (length := _num("length_m")) is not None:
        header["length_m"] = length
    if (vt := _num("section_volume_m3")) is not None:
        header["section_volume_m3"] = vt
    if (dp := _num("max_operating_pressure_bar")) is not None:
        header["design_pressure_bar"] = dp
    if (tp := _num("test_pressure_bar")) is not None:
        header["test_pressure_bar"] = tp
    if (smys := _num("smys_mpa")) is not None:
        header["smys_mpa"] = smys
    if skp := str(_val("start_kp") or "").strip():
        header["start_kp"] = _format_kp_clean(skp)
    if ekp := str(_val("end_kp") or "").strip():
        header["end_kp"] = _format_kp_clean(ekp)

    fdate = str(_val("date") or "").strip()
    pages_list = list(range(1, max(1, page_count) + 1))
    forms_by_code: dict[str, dict[str, Any]] = {}

    if any(
        k in header
        for k in ("outside_diameter_mm", "wall_thickness_mm", "length_m", "test_pressure_bar")
    ):
        spec = FORM_SPEC_BY_CODE["test_data"]
        forms_by_code["test_data"] = {
            "form_code": spec.code,
            "botas_code": spec.botas_code,
            "form_title": spec.title,
            "required": spec.required,
            "order": spec.order,
            "status": "filled",
            "source_filename": source_filename,
            "pages": pages_list,
            "form_date": fdate,
            "extracted_data": {"header": dict(header), "form_date": fdate},
            "warnings": [],
        }

    vpa = _num("air_test.vpa")
    if vpa is not None:
        spec = FORM_SPEC_BY_CODE["air_acceptance"]
        forms_by_code["air_acceptance"] = {
            "form_code": spec.code,
            "botas_code": spec.botas_code,
            "form_title": spec.title,
            "required": spec.required,
            "order": spec.order,
            "status": "filled",
            "source_filename": source_filename,
            "pages": pages_list,
            "form_date": fdate,
            "extracted_data": {
                "header": dict(header),
                "form_date": fdate,
                "air_acceptance": {
                    "vp_m3": _num("air_test.vp"),
                    "vpa_m3": vpa,
                    "a_micro_per_bar": _num("air_test.a"),
                    "k_factor": _num("air_test.k") or 1.02,
                    "pressure_rise_bar": 1.0,
                },
            },
            "warnings": [],
        }

    pa = _num("pressure_test.pa")
    if pa is not None:
        spec = FORM_SPEC_BY_CODE["pressure_acceptance"]
        forms_by_code["pressure_acceptance"] = {
            "form_code": spec.code,
            "botas_code": spec.botas_code,
            "form_title": spec.title,
            "required": spec.required,
            "order": spec.order,
            "status": "filled",
            "source_filename": source_filename,
            "pages": pages_list,
            "form_date": fdate,
            "extracted_data": {
                "header": dict(header),
                "form_date": fdate,
                "pressure_acceptance": {
                    "pa_bar": pa,
                    "pt_bar": _num("pressure_test.p_delta"),
                    "delta_t_c": _num("pressure_test.delta_t"),
                    "b_micro_per_c": _num("pressure_test.b"),
                    "a_micro_per_bar": _num("pressure_test.a"),
                    "pl_bar": _num("pressure_test.pl") or PRESSURE_VARIATION_ACCEPTANCE_BAR,
                },
            },
            "warnings": [],
        }

    if not forms_by_code:
        return None

    calcs = evaluate_section_calculations(header, forms_by_code)
    _apply_calc_statuses_to_forms(forms_by_code, calcs)
    checks_bool, check_details = evaluate_operational_checks(header, forms_by_code, calcs)
    _apply_findings_and_statuses(header, forms_by_code, calcs, check_details)
    present_list = [forms_by_code[s.code] for s in BOTAS_FORM_CATALOG if s.code in forms_by_code]
    missing_required = [
        {"form_code": s.code, "botas_code": s.botas_code, "form_title": s.title}
        for s in REQUIRED_FORM_SPECS
        if s.code not in forms_by_code
    ]
    return {
        "section_no": sec_no,
        "header": header,
        "present_forms": present_list,
        "missing_required_forms": missing_required,
        "filled_required_count": len(REQUIRED_FORM_SPECS) - len(missing_required),
        "required_total": len(REQUIRED_FORM_SPECS),
        "supplementary_count": sum(1 for item in present_list if not item["required"]),
        "calculations": calcs,
        "checks": checks_bool,
        "check_details": check_details,
        "pages": pages_list,
    }


def analyze_dossier_pages(
    pages: Sequence[PageText],
    *,
    source_filename: str = "",
    fallback_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Group multi-page PDF / multi-sheet Excel into test sections, forms, missing forms, calcs & checks."""
    project_name = extract_project_name_from_pages(pages)
    doc_defaults = _extract_doc_engineering_defaults(pages)
    unassigned_pages: list[dict[str, Any]] = []
    blank_template_pages: list[int] = []

    # (section_no, form_code) -> accumulator
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    section_order: list[str] = []
    last_key: tuple[str, str] | None = None
    active_workbook_sec: str | None = None
    orphan_forms: list[tuple[FormSpec, PageText]] = []

    def _add_page_slot(target_sec: str, spec: FormSpec, pg: PageText) -> None:
        if target_sec not in grouped:
            grouped[target_sec] = {}
            section_order.append(target_sec)
        if spec.code not in grouped[target_sec]:
            grouped[target_sec][spec.code] = {
                "spec": spec,
                "pages": [pg.page_number],
                "texts": [pg.text],
            }
        else:
            grouped[target_sec][spec.code]["pages"].append(pg.page_number)
            grouped[target_sec][spec.code]["texts"].append(pg.text)

    for page in pages:
        sheet_hint = ""
        # Handle excel sheet header hints if injected (e.g. "=== SHEET: ...")
        if page.text.startswith("===") and "\n" in page.text:
            sheet_hint = page.text.splitlines()[0]

        form_spec = classify_form_text(page.text, sheet_hint=sheet_hint)
        sec_no = extract_page_section_no(page.text)

        if form_spec is not None and _is_blank_template_page(page.text, sec_no):
            blank_template_pages.append(page.page_number)
            last_key = None
            continue

        # Summary/index cover page check (e.g., Page 1 listing >=4 chainages without a recognized form header)
        if form_spec is None and sec_no is None and len(_CHAINAGE_RE.findall(page.text)) >= 4:
            unassigned_pages.append(
                {"page": page.page_number, "reason": "Özet/indeks sayfası (KP listesi)"}
            )
            last_key = None
            continue

        # Continuation page handling when section_no is missing on trailing (2/2) or signature page
        if sec_no is None and last_key is not None:
            prev_sec, prev_code = last_key
            if form_spec is None or form_spec.code == prev_code:
                slot = grouped[prev_sec][prev_code]
                slot["pages"].append(page.page_number)
                slot["texts"].append(page.text)
                continue

        if sec_no is not None and sheet_hint:
            active_workbook_sec = sec_no

        if sec_no is None:
            if form_spec is not None:
                if sheet_hint and active_workbook_sec is not None:
                    sec_no = active_workbook_sec
                else:
                    orphan_forms.append((form_spec, page))
                    last_key = None
                    continue
            else:
                unassigned_pages.append(
                    {
                        "page": page.page_number,
                        "reason": "Form başlığı veya bölüm no tespit edilemedi",
                    }
                )
                last_key = None
                continue

        if form_spec is None:
            unassigned_pages.append(
                {
                    "page": page.page_number,
                    "section_no": sec_no,
                    "reason": f"{sec_no} algılandı ancak BOTAŞ form türü tanınamadı",
                }
            )
            last_key = None
            continue

        _add_page_slot(sec_no, form_spec, page)
        last_key = (sec_no, form_spec.code)

    if orphan_forms:
        if len(section_order) == 1:
            target_sec = section_order[0]
            for spec, pg in orphan_forms:
                _add_page_slot(target_sec, spec, pg)
        elif len(section_order) == 0:
            raw_rep_sec = str(
                ((fallback_report or {}).get("section_id") or {}).get("value") or ""
            ).strip()
            target_sec = normalize_section_no(raw_rep_sec) or "BÖLÜM 1"
            for spec, pg in orphan_forms:
                _add_page_slot(target_sec, spec, pg)
        else:
            for spec, pg in orphan_forms:
                unassigned_pages.append(
                    {
                        "page": pg.page_number,
                        "reason": f"{spec.title} bulundu ancak Test Bölüm No okunamadı",
                    }
                )

    sections_out: list[dict[str, Any]] = []
    for sec_no in section_order:
        forms_by_code: dict[str, dict[str, Any]] = {}
        for form_code, raw_slot in grouped[sec_no].items():
            slot_spec: FormSpec = raw_slot["spec"]
            combined_text = "\n".join(raw_slot["texts"])
            extracted = _extract_form_specific_data(form_code, combined_text)
            forms_by_code[form_code] = {
                "form_code": slot_spec.code,
                "botas_code": slot_spec.botas_code,
                "form_title": slot_spec.title,
                "required": slot_spec.required,
                "order": slot_spec.order,
                "status": "filled",
                "source_filename": source_filename,
                "pages": raw_slot["pages"],
                "form_date": extracted.get("form_date") or "",
                "extracted_data": extracted,
                "warnings": [],
            }

        header = _merge_section_header(forms_by_code, doc_defaults=doc_defaults)
        calcs = evaluate_section_calculations(header, forms_by_code)
        _apply_calc_statuses_to_forms(forms_by_code, calcs)
        checks_bool, check_details = evaluate_operational_checks(header, forms_by_code, calcs)
        _apply_findings_and_statuses(header, forms_by_code, calcs, check_details)

        present_list = [
            forms_by_code[spec.code] for spec in BOTAS_FORM_CATALOG if spec.code in forms_by_code
        ]
        missing_required = [
            {
                "form_code": spec.code,
                "botas_code": spec.botas_code,
                "form_title": spec.title,
            }
            for spec in REQUIRED_FORM_SPECS
            if spec.code not in forms_by_code
        ]

        sections_out.append(
            {
                "section_no": sec_no,
                "header": header,
                "present_forms": present_list,
                "missing_required_forms": missing_required,
                "filled_required_count": len(REQUIRED_FORM_SPECS) - len(missing_required),
                "required_total": len(REQUIRED_FORM_SPECS),
                "supplementary_count": sum(1 for item in present_list if not item["required"]),
                "calculations": calcs,
                "checks": checks_bool,
                "check_details": check_details,
                "pages": sorted({p for item in present_list for p in item["pages"]}),
            }
        )

    if not sections_out and not blank_template_pages and isinstance(fallback_report, dict):
        synth = _synthesize_fallback_section(
            fallback_report,
            source_filename=source_filename,
            page_count=len(pages),
        )
        if synth is not None:
            sections_out.append(synth)

    if not project_name and sections_out:
        project_name = _extract_project_name_from_filename(source_filename)

    dossier_warnings: list[str] = []
    if not project_name:
        dossier_warnings.append(
            "Taranan dokümandan proje adı okunamadı; kayıt için mevcut projelerden seçim yapın veya yeni proje adı girin."
        )
    if blank_template_pages:
        dossier_warnings.append(
            f"{len(blank_template_pages)} adet boş form şablonu sayfası/sekmesi tespit edildi ve doldurulmuş kayıt olarak sayılmadı."
        )
    if not sections_out:
        dossier_warnings.append(
            "Dokümanda tanımlı Test Bölüm No (BÖLÜM X) içeren doldurulmuş BOTAŞ formu tespit edilemedi."
        )

    return {
        "schema_version": DOSSIER_SCHEMA_VERSION,
        "detected_project_name": project_name,
        "source_filename": source_filename,
        "page_count": len(pages),
        "sections_count": len(sections_out),
        "sections": sections_out,
        "unassigned_pages": unassigned_pages,
        "blank_template_pages": blank_template_pages,
        "required_form_catalog": [
            {"form_code": s.code, "botas_code": s.botas_code, "form_title": s.title}
            for s in REQUIRED_FORM_SPECS
        ],
        "warnings": dossier_warnings,
    }


# ---------------------------------------------------------------------------
# Database form slot management, conflict preview & cumulative commit
# ---------------------------------------------------------------------------


def compute_forms_summary(
    forms: Sequence[SectionForm], *, calculations: dict[str, Any] | None = None
) -> dict[str, Any]:
    return compute_extended_summary(forms, calculations=calculations)


def ensure_section_form_slots(
    db: OrmSession,
    session: HydroSession,
    *,
    commit: bool = False,
) -> list[SectionForm]:
    """Ensure every section under a project has all 11 mandatory BOTAŞ form tracking rows."""
    existing = (
        db.execute(select(SectionForm).where(SectionForm.session_id == session.id)).scalars().all()
    )
    by_code = {row.form_code: row for row in existing}
    changed = False

    for spec in REQUIRED_FORM_SPECS:
        if spec.code not in by_code:
            row = SectionForm(
                id=new_uuid(),
                workspace_id_hash=session.workspace_id_hash,
                project_id=session.project_id,
                session_id=session.id,
                form_code=spec.code,
                botas_code=spec.botas_code,
                form_title=spec.title,
                required=True,
                status="empty",
                revision=0,
            )
            db.add(row)
            by_code[spec.code] = row
            changed = True
        else:
            row = by_code[spec.code]
            if row.project_id != session.project_id:
                row.project_id = session.project_id
                changed = True

    if changed:
        db.flush()

    ordered_rows = [by_code[c] for c in [s.code for s in BOTAS_FORM_CATALOG] if c in by_code]
    summary = compute_forms_summary(ordered_rows)
    inputs = copy.deepcopy(session.inputs or {})
    if inputs.get("forms_summary") != summary:
        inputs["forms_summary"] = summary
        session.inputs = session_service.normalize_inputs(inputs)

    if commit:
        db.commit()
    return ordered_rows


def _index_sessions_by_section_no(sessions: Sequence[HydroSession]) -> dict[str, HydroSession]:
    by_no: dict[str, HydroSession] = {}
    for sess in sessions:
        raw_no = str(
            ((sess.inputs or {}).get("section_meta") or {}).get("section_no") or ""
        ).strip()
        norm = normalize_section_no(raw_no) or raw_no.upper()
        if norm and norm not in by_no:
            by_no[norm] = sess
        head = sess.name.split("·", 1)[0].strip()
        norm_head = normalize_section_no(head)
        if norm_head and norm_head not in by_no:
            by_no[norm_head] = sess
    return by_no


def _list_project_sessions(
    db: OrmSession,
    *,
    workspace_hash: str,
    project_id: str,
) -> list[HydroSession]:
    return list(
        db.execute(
            select(HydroSession).where(
                HydroSession.project_id == project_id,
                HydroSession.workspace_id_hash == workspace_hash,
                HydroSession.deleted_at.is_(None),
            )
        )
        .scalars()
        .all()
    )


def _match_project_sections_by_no(
    db: OrmSession,
    *,
    workspace_hash: str,
    project_id: str,
) -> dict[str, HydroSession]:
    rows = _list_project_sessions(db, workspace_hash=workspace_hash, project_id=project_id)
    return _index_sessions_by_section_no(rows)


def _find_matching_session(
    sec: dict[str, Any],
    by_no: dict[str, HydroSession],
    project_sessions: Sequence[HydroSession],
    claimed_ids: set[str] | None = None,
) -> HydroSession | None:
    sec_no = str(sec.get("section_no") or "").strip()
    norm_no = normalize_section_no(sec_no) or sec_no.upper()
    direct = by_no.get(norm_no)
    if direct is not None and (claimed_ids is None or direct.id not in claimed_ids):
        return direct

    header = sec.get("header") or {}
    s_m = _kp_to_meters_local(header.get("start_kp"))
    e_m = _kp_to_meters_local(header.get("end_kp"))
    if s_m is None or e_m is None or e_m <= s_m:
        return None
    for sess in project_sessions:
        if claimed_ids is not None and sess.id in claimed_ids:
            continue
        s_meta = (sess.inputs or {}).get("section_meta") or {}
        ss_m = _kp_to_meters_local(s_meta.get("start_kp"))
        se_m = _kp_to_meters_local(s_meta.get("end_kp"))
        if (
            ss_m is not None
            and se_m is not None
            and abs(ss_m - s_m) <= 5.0
            and abs(se_m - e_m) <= 5.0
        ):
            return sess
    return None


def _preview_project_conflicts(
    db: OrmSession,
    *,
    workspace_hash: str,
    project_id: str,
    sections: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    project_sessions = _list_project_sessions(
        db, workspace_hash=workspace_hash, project_id=project_id
    )
    if not project_sessions:
        return []
    by_no = _index_sessions_by_section_no(project_sessions)
    session_ids = [sess.id for sess in project_sessions]
    filled_forms = (
        db.execute(
            select(SectionForm).where(
                SectionForm.session_id.in_(session_ids),
                SectionForm.status != "empty",
            )
        )
        .scalars()
        .all()
    )
    forms_by_sess: dict[str, dict[str, SectionForm]] = {}
    for row in filled_forms:
        forms_by_sess.setdefault(row.session_id, {})[row.form_code] = row

    conflicts: list[dict[str, Any]] = []
    claimed_ids: set[str] = set()
    for sec in sections:
        sec_no = str(sec.get("section_no") or "")
        existing_sess = _find_matching_session(sec, by_no, project_sessions, claimed_ids)
        if existing_sess is None:
            continue
        claimed_ids.add(existing_sess.id)
        filled_map = forms_by_sess.get(existing_sess.id) or {}
        for incoming in sec.get("present_forms") or []:
            code = incoming.get("form_code")
            if code in filled_map:
                old = filled_map[code]
                conflicts.append(
                    {
                        "section_no": sec_no,
                        "session_id": existing_sess.id,
                        "session_name": existing_sess.name,
                        "form_code": code,
                        "botas_code": old.botas_code,
                        "form_title": old.form_title,
                        "existing_status": old.status,
                        "existing_filename": old.source_filename or "—",
                        "existing_date": old.form_date or "—",
                        "existing_revision": old.revision,
                        "new_date": incoming.get("form_date") or "—",
                        "new_pages": incoming.get("pages") or [],
                    }
                )
    return conflicts


def build_dossier_view(db: OrmSession, analysis: OcrAnalysis) -> dict[str, Any] | None:
    """Attach live `similar_projects`, existing workspace projects & form conflicts to stored dossier."""
    raw = analysis.dossier
    if not isinstance(raw, dict):
        return None
    view = copy.deepcopy(raw)
    detected_name = view.get("detected_project_name")
    similar = find_similar_projects(db, analysis.workspace_id_hash, detected_name, threshold=0.70)
    view["similar_projects"] = similar

    # Bulk-load workspace sessions & filled forms in 2 queries to avoid per-project N+1 SQL roundtrips
    project_conflicts: dict[str, list[dict[str, Any]]] = {}
    sections = view.get("sections") or []
    if sections:
        active_sessions = (
            db.execute(
                select(HydroSession).where(
                    HydroSession.workspace_id_hash == analysis.workspace_id_hash,
                    HydroSession.project_id.is_not(None),
                    HydroSession.deleted_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        sessions_by_proj: dict[str, list[HydroSession]] = {}
        for sess in active_sessions:
            if sess.project_id:
                sessions_by_proj.setdefault(sess.project_id, []).append(sess)

        if sessions_by_proj:
            filled_forms = (
                db.execute(
                    select(SectionForm).where(
                        SectionForm.workspace_id_hash == analysis.workspace_id_hash,
                        SectionForm.status != "empty",
                    )
                )
                .scalars()
                .all()
            )
            forms_by_sess: dict[str, dict[str, SectionForm]] = {}
            for row in filled_forms:
                forms_by_sess.setdefault(row.session_id, {})[row.form_code] = row

            for pid, p_sessions in sessions_by_proj.items():
                by_no = _index_sessions_by_section_no(p_sessions)
                claimed_ids: set[str] = set()
                c_list: list[dict[str, Any]] = []
                for sec in sections:
                    sec_no = str(sec.get("section_no") or "")
                    existing_sess = _find_matching_session(sec, by_no, p_sessions, claimed_ids)
                    if existing_sess is None:
                        continue
                    claimed_ids.add(existing_sess.id)
                    filled_map = forms_by_sess.get(existing_sess.id) or {}
                    for incoming in sec.get("present_forms") or []:
                        code = incoming.get("form_code")
                        if code in filled_map:
                            old = filled_map[code]
                            c_list.append(
                                {
                                    "section_no": sec_no,
                                    "session_id": existing_sess.id,
                                    "session_name": existing_sess.name,
                                    "form_code": code,
                                    "botas_code": old.botas_code,
                                    "form_title": old.form_title,
                                    "existing_status": old.status,
                                    "existing_filename": old.source_filename or "—",
                                    "existing_date": old.form_date or "—",
                                    "existing_revision": old.revision,
                                    "new_date": incoming.get("form_date") or "—",
                                    "new_pages": incoming.get("pages") or [],
                                }
                            )
                if c_list:
                    project_conflicts[pid] = c_list
    view["project_conflicts"] = project_conflicts
    return view


def _set_if_needed(target: dict[str, Any], key: str, value: Any, overwrite: bool) -> None:
    if value is None or value == "":
        return
    if overwrite or target.get(key) in (None, ""):
        target[key] = value


def _grade_smys_value(entry: dict[str, Any]) -> float:
    raw = entry.get("smys_mpa")
    return float(raw) if isinstance(raw, (int, float, str)) else 0.0


def _match_api_5l_grade_label(smys_mpa: float) -> str | None:
    best = min(API_5L_PSL2_GRADES, key=lambda g: abs(_grade_smys_value(g) - smys_mpa))
    best_smys = _grade_smys_value(best)
    if abs(best_smys - smys_mpa) <= 3.0:
        return f"API 5L PSL2 {best['grade']} / {best['iso_label']} - SMYS {best_smys:.0f} MPa"
    return None


def _cumulative_recompute_section(
    db: OrmSession,
    session: HydroSession,
    *,
    header_hint: dict[str, Any],
    overwrite_values: bool = False,
    prefer_header_hint: bool = False,
    bump_revision: bool = True,
) -> dict[str, Any]:
    """Re-evaluate geometry, calcs, 11 checks & TestResults across ALL filled forms in `session`."""
    all_forms = (
        db.execute(select(SectionForm).where(SectionForm.session_id == session.id)).scalars().all()
    )
    filled_by_code: dict[str, dict[str, Any]] = {
        row.form_code: {
            "form_code": row.form_code,
            "botas_code": row.botas_code,
            "form_title": row.form_title,
            "required": row.required,
            "status": row.status,
            "extracted_data": row.extracted_data or {},
            "pages": row.pages or [],
            "form_date": row.form_date,
        }
        for row in all_forms
        if row.status != "empty"
    }

    inputs = copy.deepcopy(session.inputs or session_service.default_inputs())
    merged_header = _merge_section_header(filled_by_code)
    for k, v in header_hint.items():
        if v is not None and v != "":
            if (
                prefer_header_hint
                or overwrite_values
                or k not in merged_header
                or merged_header.get(k) in (None, "")
            ):
                merged_header[k] = v

    # Fall back to existing section inputs if not present on uploaded forms
    geom = dict(inputs.get("geometry") or {})
    for g_key in ("outside_diameter_mm", "wall_thickness_mm", "length_m"):
        if not merged_header.get(g_key) and geom.get(g_key):
            merged_header[g_key] = geom[g_key]
    od = _finite_float(merged_header.get("outside_diameter_mm"))
    id_mm = _finite_float(merged_header.get("inside_diameter_mm"))
    if not merged_header.get("wall_thickness_mm") and od and id_mm and od > id_mm > 0:
        merged_header["wall_thickness_mm"] = round((od - id_mm) / 2.0, 2)

    sp = dict(inputs.get("section_profile") or {})
    for sp_key in (
        "design_pressure_bar",
        "smys_mpa",
        "highest_elevation_m",
        "lowest_elevation_m",
        "start_elevation_m",
        "end_elevation_m",
    ):
        if merged_header.get(sp_key) is None and sp.get(sp_key) is not None:
            merged_header[sp_key] = sp[sp_key]

    if not merged_header.get("location_class") and inputs.get("location_class"):
        merged_header["location_class"] = inputs["location_class"]
    if not merged_header.get("pump_location") and inputs.get("pump_location"):
        merged_header["pump_location"] = inputs["pump_location"]
    fld = dict(inputs.get("field") or {})
    if (
        merged_header.get("monitored_pressure_bar") is None
        and fld.get("monitored_pressure_bar") is not None
    ):
        merged_header["monitored_pressure_bar"] = fld["monitored_pressure_bar"]
    air_block = dict(inputs.get("air") or {})
    if merged_header.get("ambient_temperature_c") is None:
        ambient_val = _finite_float(fld.get("ambient_temperature_c"))
        if ambient_val is None:
            ambient_val = _finite_float(air_block.get("ambient_temperature_c"))
        if ambient_val is not None:
            merged_header["ambient_temperature_c"] = ambient_val

    calcs = evaluate_section_calculations(
        merged_header,
        filled_by_code,
        segments=inputs.get("segments"),
    )
    _apply_calc_statuses_to_forms(filled_by_code, calcs)

    prev_checks = dict(inputs.get("checks") or {})
    checks_bool, check_details = evaluate_operational_checks(merged_header, filled_by_code, calcs)
    for k, detail in check_details.items():
        if detail.get("status") == "pending" and prev_checks.get(k) is True:
            checks_bool[k] = True
            detail["checked"] = True

    _apply_findings_and_statuses(merged_header, filled_by_code, calcs, check_details)
    # Sync updated calculation pass/fail status & findings back into DB SectionForm rows
    for row in all_forms:
        updated = filled_by_code.get(row.form_code)
        if updated:
            row_ext = dict(row.extracted_data or {})
            new_findings = (updated.get("extracted_data") or {}).get("findings") or []
            if row_ext.get("findings") != new_findings:
                row_ext["findings"] = json_safe(new_findings)
                row.extracted_data = json_safe(row_ext)
                flag_modified(row, "extracted_data")
            if row.status != updated["status"]:
                row.status = updated["status"]

    # Merge header/calc fields into session.inputs while preserving Plan-Profil points & landmarks
    sec_meta = dict(inputs.get("section_meta") or {})
    _set_if_needed(sec_meta, "section_no", merged_header.get("section_no"), overwrite_values)
    _set_if_needed(sec_meta, "start_kp", merged_header.get("start_kp"), overwrite_values)
    _set_if_needed(sec_meta, "end_kp", merged_header.get("end_kp"), overwrite_values)
    if (
        sec_meta.get("start_kp")
        and sec_meta.get("end_kp")
        and (overwrite_values or not sec_meta.get("location"))
    ):
        sec_meta["location"] = f"KP {sec_meta['start_kp']} – {sec_meta['end_kp']}"
    form_dates = [
        str((filled_by_code.get(c) or {}).get("form_date") or "").strip()
        for c in (
            "pressure_acceptance",
            "air_acceptance",
            "test_data",
            "calculation_sheet",
            *filled_by_code.keys(),
        )
        if (filled_by_code.get(c) or {}).get("form_date")
    ]
    if form_dates:
        _set_if_needed(sec_meta, "test_date", form_dates[0], overwrite_values)
    inputs["section_meta"] = sec_meta

    for g_key in ("outside_diameter_mm", "wall_thickness_mm", "length_m"):
        val = _finite_float(merged_header.get(g_key))
        if val is not None:
            _set_if_needed(geom, g_key, float(val), overwrite_values)
    inputs["geometry"] = geom

    for sp_key in (
        "design_pressure_bar",
        "smys_mpa",
        "highest_elevation_m",
        "lowest_elevation_m",
        "start_elevation_m",
        "end_elevation_m",
    ):
        val = _finite_float(merged_header.get(sp_key))
        if val is not None:
            _set_if_needed(sp, sp_key, float(val), overwrite_values)
    inputs["section_profile"] = sp

    if merged_header.get("location_class") and (
        overwrite_values or not inputs.get("location_class")
    ):
        inputs["location_class"] = str(merged_header["location_class"])
    if merged_header.get("pump_location") and (overwrite_values or not inputs.get("pump_location")):
        inputs["pump_location"] = str(merged_header["pump_location"])
    elif not inputs.get("pump_location"):
        inputs["pump_location"] = START_PUMP_LOCATION

    if sp.get("smys_mpa") is not None and (overwrite_values or not inputs.get("material_grade")):
        grade_lbl = _match_api_5l_grade_label(float(sp["smys_mpa"]))
        if grade_lbl:
            inputs["material_grade"] = grade_lbl

    pt_mon = ((filled_by_code.get("pressure_test") or {}).get("extracted_data") or {}).get(
        "monitoring"
    ) or {}
    fill_ext = ((filled_by_code.get("filling") or {}).get("extracted_data") or {}).get(
        "filling"
    ) or {}
    press_ext = ((filled_by_code.get("pressurization") or {}).get("extracted_data") or {}).get(
        "pressurization"
    ) or {}
    leak_mon = ((filled_by_code.get("leak_stabilization") or {}).get("extracted_data") or {}).get(
        "monitoring"
    ) or {}

    air_calc = calcs.get("air") or {}
    air_raw = ((filled_by_code.get("air_acceptance") or {}).get("extracted_data") or {}).get(
        "air_acceptance"
    ) or {}
    air_inp = dict(inputs.get("air") or {})
    _set_if_needed(
        air_inp,
        "a_micro_per_bar",
        air_calc.get("a_micro_per_bar") or air_raw.get("a_micro_per_bar"),
        overwrite_values,
    )
    _set_if_needed(
        air_inp, "k_factor", air_calc.get("k_factor") or air_raw.get("k_factor"), overwrite_values
    )
    vpa_val = (
        air_calc.get("vpa_m3") if air_calc.get("vpa_m3") is not None else air_raw.get("vpa_m3")
    )
    _set_if_needed(air_inp, "actual_added_water_m3", vpa_val, overwrite_values)
    air_p_val = _first_finite(
        merged_header.get("test_pressure_bar"),
        merged_header.get("monitored_pressure_bar"),
        sp.get("design_pressure_bar"),
    )
    _set_if_needed(air_inp, "pressure_bar", air_p_val, overwrite_values)
    air_t_val = _first_finite(
        fill_ext.get("max_temp_c"),
        press_ext.get("temp_c"),
        pt_mon.get("pipe_start_c"),
    )
    _set_if_needed(air_inp, "temperature_c", air_t_val, overwrite_values)
    air_amb = _first_finite(
        leak_mon.get("min_temp_c"),
        fill_ext.get("min_temp_c"),
        pt_mon.get("min_temp_c"),
    )
    _set_if_needed(air_inp, "ambient_temperature_c", air_amb, overwrite_values)
    inputs["air"] = air_inp

    pres_calc = calcs.get("pressure") or {}
    pr_raw = ((filled_by_code.get("pressure_acceptance") or {}).get("extracted_data") or {}).get(
        "pressure_acceptance"
    ) or {}
    pr_inp = dict(inputs.get("pressure") or {})
    _set_if_needed(
        pr_inp,
        "a_micro_per_bar",
        pres_calc.get("a_micro_per_bar")
        if pres_calc.get("a_micro_per_bar") is not None
        else pr_raw.get("a_micro_per_bar"),
        overwrite_values,
    )
    _set_if_needed(
        pr_inp,
        "b_micro_per_c",
        pres_calc.get("b_micro_per_c")
        if pres_calc.get("b_micro_per_c") is not None
        else pr_raw.get("b_micro_per_c"),
        overwrite_values,
    )
    _set_if_needed(
        pr_inp,
        "delta_t_c",
        pres_calc.get("delta_t_c")
        if pres_calc.get("delta_t_c") is not None
        else pr_raw.get("delta_t_c"),
        overwrite_values,
    )
    pa_v = pres_calc.get("pa_bar") if pres_calc.get("pa_bar") is not None else pr_raw.get("pa_bar")
    _set_if_needed(pr_inp, "actual_pressure_change_bar", pa_v, overwrite_values)
    pr_p_val = _first_finite(
        pt_mon.get("p_start_bar"),
        merged_header.get("test_pressure_bar"),
        merged_header.get("monitored_pressure_bar"),
    )
    _set_if_needed(pr_inp, "pressure_bar", pr_p_val, overwrite_values)
    _set_if_needed(
        pr_inp, "t_initial_c", _finite_float(pt_mon.get("pipe_start_c")), overwrite_values
    )
    _set_if_needed(pr_inp, "t_final_c", _finite_float(pt_mon.get("pipe_end_c")), overwrite_values)
    inputs["pressure"] = pr_inp

    pig_calc = calcs.get("pig") or {}
    mon_p_field = _first_finite(
        merged_header.get("monitored_pressure_bar"),
        pt_mon.get("p_start_bar"),
    )
    _set_if_needed(fld, "monitored_pressure_bar", mon_p_field, overwrite_values)
    _set_if_needed(fld, "ambient_temperature_c", air_amb, overwrite_values)
    _set_if_needed(fld, "pig_distance_m", pig_calc.get("distance_m"), overwrite_values)
    _set_if_needed(fld, "pig_travel_time_min", pig_calc.get("travel_time_min"), overwrite_values)
    _set_if_needed(fld, "pig_speed_m_per_s", pig_calc.get("speed_m_per_s"), overwrite_values)
    _set_if_needed(fld, "pig_speed_km_per_h", pig_calc.get("speed_km_per_h"), overwrite_values)
    inputs["field"] = fld

    inputs["checks"] = checks_bool
    inputs["check_details"] = check_details
    summary = compute_forms_summary(all_forms, calculations=calcs)
    inputs["forms_summary"] = summary

    session.inputs = session_service.normalize_inputs(inputs)
    result_summary = dict(session.result_summary or {})
    checked_cnt = sum(1 for v in checks_bool.values() if v)
    result_summary["checklist"] = {"checked": checked_cnt, "total": len(checks_bool)}
    now_iso = iso_z(utcnow())
    for c_key, rs_key in (
        ("air", "air"),
        ("pressure", "pressure"),
        ("profile", "profile"),
        ("pig", "pig"),
    ):
        c_val = calcs.get(c_key) or {}
        if c_val.get("passed") is not None:
            result_summary[rs_key] = {
                "status": "BASARILI" if c_val["passed"] else "BASARISIZ",
                "computed_at": now_iso,
            }
    session.result_summary = json_safe(result_summary)
    prof_calc = calcs.get("profile") or {}
    any_failed = any(c.get("passed") is False for c in (air_calc, pres_calc, prof_calc, pig_calc))
    any_passed = any(
        c.get("passed") is not None for c in (air_calc, pres_calc, prof_calc, pig_calc)
    )
    if summary["complete"] and not any_failed:
        session.status = "completed"
    elif summary["filled_required"] > 0 or summary["supplementary_filled"] > 0 or any_passed:
        session.status = "active"
    if bump_revision:
        session.revision = int(session.revision or 1) + 1
    session.updated_at = utcnow()

    return {
        "session_id": session.id,
        "section_no": sec_meta.get("section_no") or session.name,
        "forms_summary": summary,
        "calculations": calcs,
        "merged_header": merged_header,
        "checked_count": checked_cnt,
    }


def _persist_formal_test_results(
    db: OrmSession,
    session_obj: HydroSession,
    merged_header: dict[str, Any] | None = None,
) -> list[str]:
    """Create formal domain `TestResult` records for all calculable tests in `session_obj`."""
    saved_types: list[str] = []
    s_inputs = session_obj.inputs or {}
    geom = s_inputs.get("geometry") or {}
    sp = s_inputs.get("section_profile") or {}
    air_inp = s_inputs.get("air") or {}
    pr_inp = s_inputs.get("pressure") or {}
    fld_inp = s_inputs.get("field") or {}
    eff_hdr = merged_header or {}

    valid_segs: list[dict[str, Any]] = []
    for seg in s_inputs.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        s_od = _finite_float(seg.get("outside_diameter_mm"))
        s_wt = _finite_float(seg.get("wall_thickness_mm"))
        s_len = _finite_float(seg.get("length_m"))
        if s_od and s_wt and s_len and s_od > 0 and s_wt > 0 and s_len > 0:
            seg_entry: dict[str, Any] = {
                "outside_diameter_mm": float(s_od),
                "wall_thickness_mm": float(s_wt),
                "length_m": float(s_len),
            }
            s_smys = as_positive_float(seg.get("smys_mpa"))
            if s_smys is not None:
                seg_entry["smys_mpa"] = float(s_smys)
            raw_grade = seg.get("material_grade")
            if isinstance(raw_grade, str) and raw_grade.strip():
                seg_entry["material_grade"] = raw_grade.strip()
            valid_segs.append(seg_entry)
    g_od = _finite_float(eff_hdr.get("outside_diameter_mm")) or _finite_float(
        geom.get("outside_diameter_mm")
    )
    g_wt = _finite_float(eff_hdr.get("wall_thickness_mm")) or _finite_float(
        geom.get("wall_thickness_mm")
    )
    g_len = _finite_float(eff_hdr.get("length_m")) or _finite_float(geom.get("length_m"))

    if valid_segs:
        geom_payload: dict[str, Any] | None = {"sections": valid_segs}
    elif g_od and g_wt and g_len:
        geom_payload = {
            "sections": [
                {"outside_diameter_mm": g_od, "wall_thickness_mm": g_wt, "length_m": g_len}
            ]
        }
    else:
        geom_payload = None

    if geom_payload is not None:
        # 1) Profile
        design_p = _finite_float(sp.get("design_pressure_bar"))
        smys_mpa = as_positive_float(sp.get("smys_mpa"))
        if smys_mpa is None and valid_segs:
            seg_smys_list = [
                float(seg["smys_mpa"]) for seg in valid_segs if seg.get("smys_mpa") is not None
            ]
            if len(seg_smys_list) == len(valid_segs):
                smys_mpa = min(seg_smys_list)
        hi_el = _finite_float(sp.get("highest_elevation_m"))
        lo_el = _finite_float(sp.get("lowest_elevation_m"))
        st_el = _finite_float(sp.get("start_elevation_m"))
        en_el = _finite_float(sp.get("end_elevation_m"))
        if design_p and smys_mpa and all(v is not None for v in (hi_el, lo_el, st_el, en_el)):
            try:
                pump_loc = s_inputs.get("pump_location")
                if pump_loc not in {START_PUMP_LOCATION, END_PUMP_LOCATION}:
                    pump_loc = START_PUMP_LOCATION
                with db.begin_nested():
                    session_service.create_result(
                        db,
                        session_obj,
                        test_type="profile",
                        payload={
                            "geometry": geom_payload,
                            "design_pressure_bar": float(design_p),
                            "smys_mpa": float(smys_mpa),
                            "location_class": str(
                                s_inputs.get("location_class")
                                or "Class 1 - min 1.25 x dizayn basinci"
                            ),
                            "highest_elevation_m": float(hi_el),  # type: ignore[arg-type]
                            "lowest_elevation_m": float(lo_el),  # type: ignore[arg-type]
                            "start_elevation_m": float(st_el),  # type: ignore[arg-type]
                            "end_elevation_m": float(en_el),  # type: ignore[arg-type]
                            "pump_location": pump_loc,
                            "monitored_pressure_bar": _finite_float(
                                fld_inp.get("monitored_pressure_bar")
                            ),
                        },
                        commit=False,
                    )
                saved_types.append("profile")
            except Exception as exc:
                logger.warning("Formal profile TestResult skipped for %s: %s", session_obj.id, exc)

        # 2) Air content
        if air_inp.get("a_micro_per_bar") and air_inp.get("actual_added_water_m3") is not None:
            try:
                with db.begin_nested():
                    session_service.create_result(
                        db,
                        session_obj,
                        test_type="air",
                        payload={
                            "geometry": geom_payload,
                            "a_micro_per_bar": float(air_inp["a_micro_per_bar"]),
                            "pressure_rise_bar": float(air_inp.get("pressure_rise_bar") or 1.0),
                            "k_factor": float(air_inp.get("k_factor") or 1.02),
                            "actual_added_water_m3": float(air_inp["actual_added_water_m3"]),
                        },
                        commit=False,
                    )
                saved_types.append("air")
            except Exception as exc:
                logger.warning("Formal air TestResult skipped for %s: %s", session_obj.id, exc)

        # 3) Pressure variation
        if (
            pr_inp.get("a_micro_per_bar")
            and pr_inp.get("b_micro_per_c") is not None
            and pr_inp.get("delta_t_c") is not None
            and pr_inp.get("actual_pressure_change_bar") is not None
        ):
            try:
                with db.begin_nested():
                    session_service.create_result(
                        db,
                        session_obj,
                        test_type="pressure",
                        payload={
                            "geometry": geom_payload,
                            "a_micro_per_bar": float(pr_inp["a_micro_per_bar"]),
                            "b_micro_per_c": float(pr_inp["b_micro_per_c"]),
                            "delta_t_c": float(pr_inp["delta_t_c"]),
                            "actual_pressure_change_bar": float(
                                pr_inp["actual_pressure_change_bar"]
                            ),
                        },
                        commit=False,
                    )
                saved_types.append("pressure")
            except Exception as exc:
                logger.warning("Formal pressure TestResult skipped for %s: %s", session_obj.id, exc)

    # 4) Pig speed
    pig_dist = _finite_float(fld_inp.get("pig_distance_m"))
    pig_min = _finite_float(fld_inp.get("pig_travel_time_min"))
    if pig_dist and pig_min and pig_dist > 0 and pig_min > 0:
        try:
            mode = str((s_inputs.get("modes") or {}).get("pig_mode") or "Temizlik pigi")
            with db.begin_nested():
                session_service.create_result(
                    db,
                    session_obj,
                    test_type="pig",
                    payload={
                        "mode": mode,
                        "distance_m": float(pig_dist),
                        "travel_time_min": float(pig_min),
                    },
                    commit=False,
                )
            saved_types.append("pig")
        except Exception as exc:
            logger.warning("Formal pig TestResult skipped for %s: %s", session_obj.id, exc)

    # 5) Dewatering Spec 16/17 results (depressurization & discharge)
    dewat_row = db.execute(
        select(SectionForm).where(
            SectionForm.session_id == session_obj.id, SectionForm.form_code == "dewatering"
        )
    ).scalar_one_or_none()
    if dewat_row is not None and dewat_row.status != "empty":
        dep_payload, dis_payload = build_effective_dewatering_payloads(
            dewat_row.form_date or "",
            dewat_row.extracted_data or {},
        )
        for t_type, t_payload in (("depressurization", dep_payload), ("discharge", dis_payload)):
            if t_payload is None:
                continue
            latest = db.execute(
                select(TestResult)
                .where(
                    TestResult.session_id == session_obj.id,
                    TestResult.test_type == t_type,
                )
                .order_by(TestResult.computed_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if latest is not None and (latest.inputs or {}).get("payload") == t_payload:
                continue
            try:
                with db.begin_nested():
                    session_service.create_result(
                        db,
                        session_obj,
                        test_type=t_type,
                        payload=t_payload,
                        commit=False,
                    )
                saved_types.append(t_type)
            except Exception as exc:
                logger.warning(
                    "Formal %s TestResult skipped for %s: %s", t_type, session_obj.id, exc
                )

    return saved_types


def sync_operation_result_to_dewatering_form(
    db: OrmSession,
    session: HydroSession,
    *,
    test_type: str,
    payload: dict[str, Any],
) -> None:
    """Mirror a saved `depressurization` / `discharge` result back into the `dewatering` SectionForm."""
    if test_type not in {"depressurization", "discharge"}:
        return

    ensure_section_form_slots(db, session, commit=False)
    row = db.execute(
        select(SectionForm).where(
            SectionForm.session_id == session.id, SectionForm.form_code == "dewatering"
        )
    ).scalar_one_or_none()
    now = utcnow()
    spec = FORM_SPEC_BY_CODE["dewatering"]
    if row is None:
        row = SectionForm(
            id=new_uuid(),
            workspace_id_hash=session.workspace_id_hash,
            project_id=session.project_id,
            session_id=session.id,
            form_code=spec.code,
            botas_code=spec.botas_code,
            form_title=spec.title,
            required=spec.required,
            status="filled",
            revision=0,
            filled_at=now,
        )
        db.add(row)
        db.flush()

    ext = copy.deepcopy(row.extracted_data or {})
    ext[test_type] = copy.deepcopy(payload)
    if test_type == "discharge":
        rep_date = str(payload.get("report_date") or "").strip()
        if rep_date:
            ext["form_date"] = rep_date
            if not str(row.form_date or "").strip():
                row.form_date = rep_date
        if not ext.get("pig_runs"):
            pig_name = str(payload.get("pig_name") or "").strip()
            rep_time = str(payload.get("report_time") or "").strip()
            dur_val = _finite_float(payload.get("duration_min"))
            if pig_name or rep_time or dur_val is not None:
                ext["pig_runs"] = [
                    {
                        "pig_type": pig_name or "Boşaltma Pigi",
                        "launch_time": rep_time,
                        "receive_time": "",
                        "duration_min": dur_val,
                        "note": str(payload.get("discharge_location") or "").strip(),
                    }
                ]

    reconciled = reconcile_form_extracted_data("dewatering", ext)
    row.extracted_data = json_safe(reconciled)
    flag_modified(row, "extracted_data")
    if row.status == "empty":
        row.status = "filled"
    row.filled_at = row.filled_at or now
    row.revision = int(row.revision or 0) + 1
    row.updated_at = now
    db.flush()

    _cumulative_recompute_section(
        db,
        session,
        header_hint={},
        overwrite_values=False,
        prefer_header_hint=False,
        bump_revision=False,
    )


def recompute_session_from_inputs_and_forms(
    db: OrmSession,
    session_obj: HydroSession,
) -> dict[str, Any]:
    """Ensure 11 form slots, recompute cumulative calculations/checks & persist formal TestResults."""
    ensure_section_form_slots(db, session_obj, commit=False)
    s_inputs = session_obj.inputs or {}
    geom = s_inputs.get("geometry") or {}
    sp = s_inputs.get("section_profile") or {}
    sec_meta = s_inputs.get("section_meta") or {}
    fld = s_inputs.get("field") or {}
    header_hint = {
        "section_no": sec_meta.get("section_no"),
        "start_kp": sec_meta.get("start_kp"),
        "end_kp": sec_meta.get("end_kp"),
        "outside_diameter_mm": geom.get("outside_diameter_mm"),
        "wall_thickness_mm": geom.get("wall_thickness_mm"),
        "length_m": geom.get("length_m"),
        "design_pressure_bar": sp.get("design_pressure_bar"),
        "smys_mpa": sp.get("smys_mpa"),
        "highest_elevation_m": sp.get("highest_elevation_m"),
        "lowest_elevation_m": sp.get("lowest_elevation_m"),
        "start_elevation_m": sp.get("start_elevation_m"),
        "end_elevation_m": sp.get("end_elevation_m"),
        "location_class": s_inputs.get("location_class"),
        "pump_location": s_inputs.get("pump_location"),
        "monitored_pressure_bar": fld.get("monitored_pressure_bar"),
    }
    recomp = _cumulative_recompute_section(
        db,
        session_obj,
        header_hint=header_hint,
        overwrite_values=False,
        prefer_header_hint=True,
    )
    saved_types = _persist_formal_test_results(db, session_obj, recomp.get("merged_header"))
    recomp["persisted_result_types"] = saved_types
    db.flush()
    return recomp


def commit_dossier_to_project(
    db: OrmSession,
    analysis: OcrAnalysis,
    *,
    workspace_hash: str,
    target_project_id: str | None,
    create_new_project: bool,
    new_project_name: str | None,
    new_project_code: str | None,
    overwrite_filled: bool,
    selected_sections: list[str] | None,
) -> dict[str, Any]:
    """Persist detected sections and forms into the target project with duplicate confirmation."""
    if analysis.status != "succeeded":
        raise AppError(
            "analysis_not_succeeded",
            "Yalnizca tamamlanmis analiz projeye kaydedilebilir.",
            status_code=409,
        )
    dossier = analysis.dossier
    if not isinstance(dossier, dict) or not dossier.get("sections"):
        raise AppError(
            "no_dossier_sections",
            "Bu analizde projeye kaydedilecek test bolumu veya BOTAŞ formu tespit edilmedi.",
            status_code=422,
        )

    sections = list(dossier["sections"])
    if selected_sections:
        wanted = {
            normalize_section_no(s) or s.strip().upper() for s in selected_sections if s.strip()
        }
        sections = [
            sec
            for sec in sections
            if (normalize_section_no(sec["section_no"]) or sec["section_no"].upper()) in wanted
        ]
    if not sections:
        raise AppError(
            "no_sections_selected",
            "Kaydedilecek en az bir test bolumu secilmelidir.",
            status_code=422,
        )

    # Resolve target project or create a new one
    if create_new_project or not target_project_id:
        pname = (new_project_name or dossier.get("detected_project_name") or "").strip()
        if not pname:
            raise AppError(
                "project_name_required",
                "Dokumandan proje adi okunamadi. Lutfen hedef projeyi secin veya yeni proje adi girin.",
                status_code=422,
            )
        project = project_service.create_project(
            db,
            workspace_hash,
            {"name": pname, "code": (new_project_code or "").strip(), "client": "BOTAŞ"},
            commit=False,
        )
    else:
        project = project_service.get_project(db, target_project_id, workspace_hash)

    # Duplicate non-empty form check
    conflicts = _preview_project_conflicts(
        db,
        workspace_hash=workspace_hash,
        project_id=project.id,
        sections=sections,
    )
    if conflicts and not overwrite_filled:
        sample = ", ".join(f"{c['section_no']} · {c['form_title']}" for c in conflicts[:4])
        extra = f" (+{len(conflicts) - 4} form daha)" if len(conflicts) > 4 else ""
        raise AppError(
            "duplicate_filled_forms",
            (
                f"{project.name} projesinde {len(conflicts)} adet form zaten doldurulmuş: {sample}{extra}. "
                "Mevcut kayıtların üzerine yazmak için onay verin."
            ),
            status_code=409,
            details={
                "project_id": project.id,
                "project_name": project.name,
                "conflicts": conflicts,
            },
        )

    project_sessions = _list_project_sessions(
        db,
        workspace_hash=workspace_hash,
        project_id=project.id,
    )
    existing_by_no = _index_sessions_by_section_no(project_sessions)
    claimed_ids: set[str] = set()

    created_sections: list[dict[str, str]] = []
    updated_sections: list[dict[str, str]] = []
    saved_forms_count = 0
    overwritten_forms_count = 0
    committed_summaries: list[dict[str, Any]] = []

    for sec in sections:
        sec_no = str(sec["section_no"]).strip()
        norm_no = normalize_section_no(sec_no) or sec_no.upper()
        header = sec.get("header") or {}
        session_obj = _find_matching_session(sec, existing_by_no, project_sessions, claimed_ids)

        if session_obj is None:
            init_inputs = session_service.default_inputs()
            start_kp = str(header.get("start_kp") or "").strip()
            end_kp = str(header.get("end_kp") or "").strip()
            raw_dossier = analysis.dossier if isinstance(analysis.dossier, dict) else {}
            init_inputs["section_meta"] = {
                "section_no": sec_no,
                "description": f"{project.name} · {sec_no}",
                "location": f"KP {start_kp} – {end_kp}" if start_kp and end_kp else "",
                "start_kp": start_kp,
                "end_kp": end_kp,
                "test_date": "",
                "test_type": "Hidrostatik test",
                "notes": f"OCR hakediş paketinden oluşturuldu: {raw_dossier.get('source_filename', '')}",
            }
            init_inputs["geometry"] = {
                "outside_diameter_mm": header.get("outside_diameter_mm"),
                "wall_thickness_mm": header.get("wall_thickness_mm"),
                "length_m": header.get("length_m"),
            }
            for sp_key in (
                "design_pressure_bar",
                "smys_mpa",
                "highest_elevation_m",
                "lowest_elevation_m",
                "start_elevation_m",
                "end_elevation_m",
            ):
                if header.get(sp_key) is not None:
                    init_inputs["section_profile"][sp_key] = header[sp_key]
            if header.get("location_class"):
                init_inputs["location_class"] = str(header["location_class"])
            init_inputs["pump_location"] = str(header.get("pump_location") or START_PUMP_LOCATION)
            if header.get("monitored_pressure_bar") is not None:
                init_inputs["field"]["monitored_pressure_bar"] = header["monitored_pressure_bar"]

            sess_name = f"{sec_no} · {project.code or project.name}"
            session_obj = session_service.create_session(
                db,
                workspace_hash=workspace_hash,
                name=sess_name,
                project_id=project.id,
                inputs=init_inputs,
                commit=False,
            )
            project_sessions.append(session_obj)
            existing_by_no[norm_no] = session_obj
            claimed_ids.add(session_obj.id)
            section_record = {
                "session_id": session_obj.id,
                "section_no": sec_no,
                "name": session_obj.name,
            }
            created_sections.append(section_record)
        else:
            claimed_ids.add(session_obj.id)
            existing_by_no[norm_no] = session_obj
            ensure_section_form_slots(db, session_obj, commit=False)
            if "·" in session_obj.name and (overwrite_filled or "KP " not in session_obj.name):
                session_obj.name = f"{sec_no} · {project.code or project.name}"
                s_inputs = copy.deepcopy(session_obj.inputs or {})
                s_meta = dict(s_inputs.get("section_meta") or {})
                s_meta["section_no"] = sec_no
                s_meta["description"] = f"{project.name} · {sec_no}"
                s_inputs["section_meta"] = s_meta
                session_obj.inputs = session_service.normalize_inputs(s_inputs)
            section_record = {
                "session_id": session_obj.id,
                "section_no": sec_no,
                "name": session_obj.name,
            }
            updated_sections.append(section_record)

        existing_forms = (
            db.execute(select(SectionForm).where(SectionForm.session_id == session_obj.id))
            .scalars()
            .all()
        )
        form_map = {f.form_code: f for f in existing_forms}

        for incoming in sec.get("present_forms") or []:
            code = incoming["form_code"]
            row = form_map.get(code)
            now = utcnow()
            if row is None:
                row = SectionForm(
                    id=new_uuid(),
                    workspace_id_hash=workspace_hash,
                    project_id=project.id,
                    session_id=session_obj.id,
                    form_code=code,
                    botas_code=incoming.get("botas_code") or "",
                    form_title=incoming.get("form_title") or code,
                    required=bool(incoming.get("required", False)),
                )
                db.add(row)
                form_map[code] = row
            else:
                if row.status != "empty":
                    overwritten_forms_count += 1

            row.status = str(incoming.get("status") or "filled")
            row.analysis_id = analysis.id
            row.attachment_id = analysis.attachment_id
            row.source_filename = str(incoming.get("source_filename") or "")
            row.pages = list(incoming.get("pages") or [])
            row.form_date = str(incoming.get("form_date") or "")
            row.extracted_data = json_safe(incoming.get("extracted_data") or {})
            row.warnings = list(incoming.get("warnings") or [])
            row.revision = int(row.revision or 0) + 1
            row.filled_at = now
            row.updated_at = now
            saved_forms_count += 1

        db.flush()
        recomp = _cumulative_recompute_section(
            db,
            session_obj,
            header_hint=header,
            overwrite_values=bool(overwrite_filled),
        )
        section_record["name"] = session_obj.name
        _persist_formal_test_results(db, session_obj, recomp.get("merged_header"))

        committed_summaries.append(recomp)

    audit.record(
        db,
        action="ocr.commit_dossier",
        entity_type="project",
        entity_id=project.id,
        workspace_hash=workspace_hash,
        after={
            "analysis_id": analysis.id,
            "created_sections": len(created_sections),
            "updated_sections": len(updated_sections),
            "saved_forms_count": saved_forms_count,
            "overwritten_forms_count": overwritten_forms_count,
        },
    )
    db.commit()

    return {
        "project": project_service.serialize_project(
            project, project_service.section_count(db, project.id)
        ),
        "created_sections": created_sections,
        "updated_sections": updated_sections,
        "created_sections_count": len(created_sections),
        "updated_sections_count": len(updated_sections),
        "saved_forms_count": saved_forms_count,
        "overwritten_forms_count": overwritten_forms_count,
        "sections_summary": committed_summaries,
    }


def _build_session_calc_context(
    session: HydroSession,
    rows: Sequence[SectionForm],
) -> tuple[dict[str, Any], dict[str, Any]]:
    inputs = session.inputs or {}
    filled_by_code = {
        row.form_code: {
            "form_code": row.form_code,
            "botas_code": row.botas_code,
            "form_title": row.form_title,
            "required": row.required,
            "status": row.status,
            "extracted_data": row.extracted_data or {},
            "pages": row.pages or [],
            "form_date": row.form_date,
        }
        for row in rows
        if row.status != "empty"
    }
    merged_header = _merge_section_header(filled_by_code)
    geom = dict(inputs.get("geometry") or {})
    for g_key in ("outside_diameter_mm", "wall_thickness_mm", "length_m"):
        if not merged_header.get(g_key) and geom.get(g_key):
            merged_header[g_key] = geom[g_key]
    sp = dict(inputs.get("section_profile") or {})
    for sp_key in (
        "design_pressure_bar",
        "smys_mpa",
        "highest_elevation_m",
        "lowest_elevation_m",
        "start_elevation_m",
        "end_elevation_m",
    ):
        if merged_header.get(sp_key) is None and sp.get(sp_key) is not None:
            merged_header[sp_key] = sp[sp_key]
    sec_meta = inputs.get("section_meta") or {}
    if sec_meta.get("section_no") and not merged_header.get("section_no"):
        merged_header["section_no"] = sec_meta["section_no"]
    if sec_meta.get("start_kp") and not merged_header.get("start_kp"):
        merged_header["start_kp"] = sec_meta["start_kp"]
    if sec_meta.get("end_kp") and not merged_header.get("end_kp"):
        merged_header["end_kp"] = sec_meta["end_kp"]
    calcs = evaluate_section_calculations(
        merged_header,
        filled_by_code,
        segments=inputs.get("segments"),
    )
    return merged_header, calcs


def _serialize_form_row(
    spec: FormSpec,
    row: SectionForm | None,
    session_id: str,
) -> dict[str, Any]:
    if row is None:
        return {
            "id": f"slot-{session_id}-{spec.code}",
            "form_code": spec.code,
            "botas_code": spec.botas_code,
            "form_title": spec.title,
            "required": spec.required,
            "order": spec.order,
            "status": "empty",
            "analysis_id": None,
            "source_filename": "",
            "pages": [],
            "form_date": "",
            "extracted_data": {},
            "findings": [],
            "warnings": [],
            "revision": 0,
            "filled_at": None,
            "updated_at": None,
        }
    ext = dict(row.extracted_data or {}) if isinstance(row.extracted_data, dict) else {}
    return {
        "id": row.id,
        "form_code": row.form_code,
        "botas_code": row.botas_code,
        "form_title": row.form_title,
        "required": row.required,
        "order": spec.order,
        "status": row.status,
        "analysis_id": row.analysis_id,
        "source_filename": row.source_filename,
        "pages": row.pages or [],
        "form_date": row.form_date,
        "extracted_data": ext,
        "findings": list(ext.get("findings") or []),
        "warnings": row.warnings or [],
        "revision": row.revision,
        "filled_at": iso_z(row.filled_at),
        "updated_at": iso_z(row.updated_at),
    }


def get_session_forms_payload(db: OrmSession, session: HydroSession) -> dict[str, Any]:
    """Return all mandatory + supplementary BOTAŞ form tracking rows and operational checks for one section."""
    rows = ensure_section_form_slots(db, session, commit=True)
    # Upgrade legacy filled rows lazily if findings were not persisted yet
    needs_findings = any(
        row.status != "empty" and not isinstance((row.extracted_data or {}).get("findings"), list)
        for row in rows
    )
    if needs_findings:
        recompute_session_from_inputs_and_forms(db, session)
        db.commit()
        rows = ensure_section_form_slots(db, session, commit=True)

    merged_header, calcs = _build_session_calc_context(session, rows)
    summary = compute_forms_summary(rows, calculations=calcs)
    inputs = session.inputs or {}
    checks = inputs.get("checks") or {}
    check_details = inputs.get("check_details") or {}

    row_by_code = {row.form_code: row for row in rows}
    items = [
        _serialize_form_row(spec, row_by_code.get(spec.code), session.id)
        for spec in BOTAS_FORM_CATALOG
    ]

    checkpoints = []
    for key, label, ref in FIELD_CHECKS:
        detail = check_details.get(key) if isinstance(check_details, dict) else None
        checkpoints.append(
            {
                "key": key,
                "label": label,
                "ref": ref,
                "checked": bool(checks.get(key, False)),
                "status": (detail or {}).get("status")
                or ("passed" if checks.get(key) else "pending"),
                "message": (detail or {}).get("message") or "",
                "source_forms": (detail or {}).get("source_forms") or [],
            }
        )

    sec_meta = inputs.get("section_meta") or {}
    return {
        "session_id": session.id,
        "project_id": session.project_id,
        "section_no": sec_meta.get("section_no") or session.name,
        "session_name": session.name,
        "summary": summary,
        "merged_header": merged_header,
        "calculations": calcs,
        "forms": items,
        "missing_required_forms": [
            {
                "form_code": item["form_code"],
                "botas_code": item["botas_code"],
                "form_title": item["form_title"],
            }
            for item in items
            if item["required"] and item["status"] == "empty"
        ],
        "checkpoints": checkpoints,
    }


def _require_form_spec(form_code: str) -> FormSpec:
    spec = FORM_SPEC_BY_CODE.get(form_code)
    if spec is None:
        raise AppError(
            "form_not_found",
            f"Bilinmeyen BOTAŞ form kodu: {form_code}",
            status_code=404,
            details={"form_code": form_code},
        )
    return spec


def get_single_session_form_payload(
    db: OrmSession,
    session: HydroSession,
    form_code: str,
) -> dict[str, Any]:
    _require_form_spec(form_code)
    payload = get_session_forms_payload(db, session)
    item = next(f for f in payload["forms"] if f["form_code"] == form_code)
    return {
        "form": item,
        "merged_header": payload["merged_header"],
        "calculations": payload["calculations"],
        "summary": payload["summary"],
        "checkpoints": payload["checkpoints"],
    }


def update_session_form(
    db: OrmSession,
    session: HydroSession,
    *,
    workspace_hash: str,
    form_code: str,
    form_date: str | None = None,
    extracted_data: dict[str, Any] | None = None,
    overwrite_session_inputs: bool = True,
) -> dict[str, Any]:
    spec = _require_form_spec(form_code)
    ensure_section_form_slots(db, session, commit=False)
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
            project_id=session.project_id,
            session_id=session.id,
            form_code=spec.code,
            botas_code=spec.botas_code,
            form_title=spec.title,
            required=spec.required,
            status="filled",
            revision=0,
            filled_at=now,
        )
        db.add(row)
        db.flush()

    merged_ext = copy.deepcopy(row.extracted_data or {})
    if extracted_data:
        for k, v in extracted_data.items():
            if k == "findings":
                continue
            if isinstance(v, dict) and isinstance(merged_ext.get(k), dict):
                merged_ext[k] = {**merged_ext[k], **v}
            else:
                merged_ext[k] = v

    reconciled = reconcile_form_extracted_data(form_code, merged_ext)
    if form_date is not None:
        row.form_date = str(form_date).strip()
        reconciled["form_date"] = row.form_date
    elif reconciled.get("form_date") and not row.form_date:
        row.form_date = str(reconciled["form_date"])

    row.extracted_data = json_safe(reconciled)
    flag_modified(row, "extracted_data")
    if row.status == "empty":
        row.status = "filled"
    row.filled_at = row.filled_at or now
    row.revision = int(row.revision or 0) + 1
    row.updated_at = now
    db.flush()

    recomp = _cumulative_recompute_section(
        db,
        session,
        header_hint=reconciled.get("header") or {},
        overwrite_values=bool(overwrite_session_inputs),
        prefer_header_hint=bool(overwrite_session_inputs),
    )
    _persist_formal_test_results(db, session, recomp.get("merged_header"))
    audit.record(
        db,
        action="form.update",
        entity_type="section_form",
        entity_id=row.id,
        session_id=session.id,
        workspace_hash=workspace_hash,
        after={"form_code": form_code, "revision": row.revision, "status": row.status},
    )
    db.commit()
    db.refresh(session)

    forms_payload = get_session_forms_payload(db, session)
    item = next(f for f in forms_payload["forms"] if f["form_code"] == form_code)
    return {
        "form": item,
        "forms_payload": forms_payload,
        "session": session_service.serialize_session(session),
    }


def scan_single_form_upload(
    db: OrmSession,
    settings: Any,
    *,
    workspace_hash: str,
    session: HydroSession,
    form_code: str,
    file_name: str | None = None,
    stream: Any = None,
    uploads: Sequence[tuple[str | None, Any]] | None = None,
    language: str | None = None,
    overwrite: bool = True,
    mode: str = "replace",
) -> dict[str, Any]:
    """Scan single or multi-file form PDFs/images/spreadsheets into the active section's target form."""
    from hidrostatik_test.services.report_ocr import extract_text

    from ..models import Attachment
    from . import ocr as ocr_service
    from .storage import resolve_stored_path

    norm_mode = (mode or "replace").strip().lower()
    if norm_mode not in {"replace", "append"}:
        raise AppError(
            "invalid_scan_mode",
            "Gecersiz tarama modu; 'replace' veya 'append' olmalidir.",
            status_code=422,
        )

    upload_items = (
        list(uploads) if uploads else ([(file_name, stream)] if stream is not None else [])
    )
    if not upload_items:
        raise AppError(
            "missing_file",
            "Taranacak en az bir dokuman secilmelidir.",
            status_code=400,
        )

    spec = _require_form_spec(form_code)
    ensure_section_form_slots(db, session, commit=False)

    sec_meta = (session.inputs or {}).get("section_meta") or {}
    target_sec_norm = normalize_section_no(sec_meta.get("section_no") or "")

    chosen_incoming: dict[str, Any] | None = None
    extra_forms: list[dict[str, Any]] = []
    analysis: Any = None
    src_filename = ""

    if len(upload_items) == 1:
        single_name, single_stream = upload_items[0]
        analysis, _ = ocr_service.analyze_upload(
            db,
            settings,
            workspace_hash,
            file_name=single_name,
            stream=single_stream,
            calculated_raw=None,
            session_id=session.id,
            mapping_profile_id=None,
            language=language,
            force=True,
        )
        dossier = analysis.dossier if isinstance(analysis.dossier, dict) else {}
        sections = list(dossier.get("sections") or [])

        if sections:
            matched_sec = None
            if target_sec_norm:
                for sec in sections:
                    if (
                        normalize_section_no(sec.get("section_no")) or sec.get("section_no")
                    ) == target_sec_norm:
                        matched_sec = sec
                        break
            if matched_sec is None:
                for sec in sections:
                    if any(
                        f.get("form_code") == form_code for f in (sec.get("present_forms") or [])
                    ):
                        matched_sec = sec
                        break
            if matched_sec is None:
                matched_sec = sections[0]

            for f in matched_sec.get("present_forms") or []:
                if f.get("form_code") == form_code:
                    chosen_incoming = f
                else:
                    extra_forms.append(f)

        attachment = db.get(Attachment, analysis.attachment_id)
        src_filename = attachment.filename if attachment else (single_name or "")

        if chosen_incoming is None and attachment is not None:
            cached_pages = getattr(analysis, "_extracted_pages", None)
            if cached_pages is not None:
                pages = list(cached_pages)
            else:
                stored_path = resolve_stored_path(settings.uploads_dir, attachment.stored_path)
                pages = extract_text(stored_path)
            combined_text = "\n".join(pg.text for pg in pages)
            ext_data = _extract_form_specific_data(form_code, combined_text)
            chosen_incoming = {
                "form_code": spec.code,
                "botas_code": spec.botas_code,
                "form_title": spec.title,
                "required": spec.required,
                "status": "filled",
                "source_filename": src_filename,
                "pages": [pg.page_number for pg in pages],
                "form_date": ext_data.get("form_date") or "",
                "extracted_data": ext_data,
                "warnings": [],
            }
    else:
        all_texts: list[str] = []
        total_pages = 0
        first_src = ""
        for fname, fstream in upload_items:
            analysis, _ = ocr_service.analyze_upload(
                db,
                settings,
                workspace_hash,
                file_name=fname,
                stream=fstream,
                calculated_raw=None,
                session_id=session.id,
                mapping_profile_id=None,
                language=language,
                force=True,
            )
            attachment = db.get(Attachment, analysis.attachment_id)
            cur_name = attachment.filename if attachment else (fname or "")
            if not first_src and cur_name:
                first_src = cur_name
            cached_pages = getattr(analysis, "_extracted_pages", None)
            if cached_pages is not None:
                file_pages = list(cached_pages)
            elif attachment is not None:
                stored_path = resolve_stored_path(settings.uploads_dir, attachment.stored_path)
                file_pages = extract_text(stored_path)
            else:
                file_pages = []
            if file_pages:
                total_pages += len(file_pages)
                all_texts.extend(pg.text for pg in file_pages if pg.text.strip())

        if all_texts:
            combined_text = "\n".join(all_texts)
            ext_data = _extract_form_specific_data(form_code, combined_text)
            src_filename = f"{first_src or 'dokuman'} (+{len(upload_items) - 1} dosya)"
            chosen_incoming = {
                "form_code": spec.code,
                "botas_code": spec.botas_code,
                "form_title": spec.title,
                "required": spec.required,
                "status": "filled",
                "source_filename": src_filename,
                "pages": list(range(1, max(total_pages, len(upload_items)) + 1)),
                "form_date": ext_data.get("form_date") or "",
                "extracted_data": ext_data,
                "warnings": [],
            }

    if chosen_incoming is None or analysis is None:
        raise AppError(
            "form_scan_empty",
            "Yuklenen dokumandan forma ait okunabilir veri cikarilamadi.",
            status_code=422,
        )

    existing_rows = {
        r.form_code: r
        for r in db.execute(select(SectionForm).where(SectionForm.session_id == session.id))
        .scalars()
        .all()
    }

    updated_codes: list[str] = []
    now = utcnow()
    if norm_mode == "append":
        to_apply = [chosen_incoming]
    else:
        to_apply = [chosen_incoming] + [
            ef
            for ef in extra_forms
            if (
                ef.get("form_code") not in existing_rows
                or existing_rows[ef["form_code"]].status == "empty"
                or overwrite
            )
        ]

    for incoming in to_apply:
        fcode = str(incoming["form_code"])
        fspec = FORM_SPEC_BY_CODE.get(fcode)
        if not fspec:
            continue
        row = existing_rows.get(fcode)
        if row is None:
            row = SectionForm(
                id=new_uuid(),
                workspace_id_hash=workspace_hash,
                project_id=session.project_id,
                session_id=session.id,
                form_code=fspec.code,
                botas_code=fspec.botas_code,
                form_title=fspec.title,
                required=fspec.required,
            )
            db.add(row)
            existing_rows[fcode] = row
        elif (
            row.status != "empty" and not overwrite and fcode == form_code and norm_mode != "append"
        ):
            # Target form scan always updates when explicitly invoked for that form unless overwrite disabled
            continue

        should_append = (
            norm_mode == "append"
            and fcode == form_code
            and row.status != "empty"
            and isinstance(row.extracted_data, dict)
            and bool(row.extracted_data)
        )
        row.status = str(incoming.get("status") or "filled")
        row.analysis_id = analysis.id
        row.attachment_id = analysis.attachment_id
        incoming_src = str(incoming.get("source_filename") or src_filename)
        incoming_pages = list(incoming.get("pages") or [])
        incoming_date = str(incoming.get("form_date") or "")
        incoming_ext = incoming.get("extracted_data") or {}

        if should_append:
            prev_src = str(row.source_filename or "").strip()
            if prev_src and incoming_src and incoming_src not in prev_src:
                row.source_filename = f"{prev_src} + {incoming_src}"[:240]
            else:
                row.source_filename = (prev_src or incoming_src)[:240]
            prev_pages = list(row.pages or [])
            max_prev = max((int(p) for p in prev_pages if isinstance(p, int)), default=0)
            row.pages = prev_pages + [
                max_prev + idx + 1 for idx in range(max(len(incoming_pages), 1))
            ]
            row.form_date = str(row.form_date or incoming_date)
            ext = merge_form_extracted_data(fcode, row.extracted_data, incoming_ext)
        else:
            row.source_filename = incoming_src[:240]
            row.pages = incoming_pages
            row.form_date = incoming_date
            ext = reconcile_form_extracted_data(fcode, incoming_ext)

        row.extracted_data = json_safe(ext)
        flag_modified(row, "extracted_data")
        row.warnings = list(incoming.get("warnings") or [])
        row.revision = int(row.revision or 0) + 1
        row.filled_at = (row.filled_at or now) if should_append else now
        row.updated_at = now
        updated_codes.append(fcode)

    db.flush()
    recomp = _cumulative_recompute_section(
        db,
        session,
        header_hint=(chosen_incoming.get("extracted_data") or {}).get("header") or {},
        overwrite_values=bool(overwrite),
    )
    _persist_formal_test_results(db, session, recomp.get("merged_header"))
    audit.record(
        db,
        action="form.scan",
        entity_type="section_form",
        entity_id=existing_rows[form_code].id if form_code in existing_rows else session.id,
        session_id=session.id,
        workspace_hash=workspace_hash,
        after={
            "form_code": form_code,
            "mode": norm_mode,
            "file_count": len(upload_items),
            "analysis_id": analysis.id,
            "updated_forms": updated_codes,
        },
    )
    db.commit()
    db.refresh(session)

    forms_payload = get_session_forms_payload(db, session)
    item = next(f for f in forms_payload["forms"] if f["form_code"] == form_code)
    return {
        "analysis_id": analysis.id,
        "updated_form_codes": updated_codes,
        "form": item,
        "forms_payload": forms_payload,
        "session": session_service.serialize_session(session),
    }


def sync_time_series_with_form(
    db: OrmSession,
    session: HydroSession,
    *,
    form_code: str,
    direction: str,
    mode: str = "replace",
    base_date: str | None = None,
) -> dict[str, Any]:
    """Synchronize hourly monitoring rows between Form 018/021 and ``time_series``."""
    if form_code not in {"leak_stabilization", "pressure_test"}:
        raise AppError(
            "validation_error",
            "Zaman serisi senkronizasyonu yalnizca Form 018 veya Form 021 ile yapilabilir.",
            status_code=422,
            details={"form_code": form_code},
        )
    if direction not in {"from_form", "to_form"}:
        raise AppError(
            "validation_error",
            "Gecersiz senkronizasyon yonu.",
            status_code=422,
            details={"direction": direction},
        )

    spec = FORM_SPEC_BY_CODE[form_code]
    short_code = spec.botas_code.rsplit("-", 1)[-1]
    row = db.execute(
        select(SectionForm).where(
            SectionForm.session_id == session.id, SectionForm.form_code == form_code
        )
    ).scalar_one_or_none()

    if direction == "from_form":
        ext = (row.extracted_data or {}) if row is not None else {}
        form_rows = ext.get("rows") if isinstance(ext, dict) else None
        if row is None or not isinstance(form_rows, list) or not form_rows:
            raise AppError(
                "form_rows_empty",
                f"Form {short_code} icinde saatlik izleme satiri bulunamadi.",
                status_code=422,
                details={"form_code": form_code},
            )
        inputs = session.inputs or {}
        resolved_date = (
            parse_base_date(base_date)
            or parse_base_date(row.form_date)
            or parse_base_date((ext.get("header") or {}).get("date"))
            or parse_base_date((inputs.get("report") or {}).get("date"))
            or parse_base_date((inputs.get("section_meta") or {}).get("test_date"))
            or utcnow().date()
        )
        parsed_records, skipped = monitoring_rows_to_time_series(
            form_rows,
            default_date=resolved_date,
            note_prefix=f"Form {short_code}",
        )
        if not parsed_records:
            raise AppError(
                "form_rows_invalid",
                f"Form {short_code} satirlarindan gecerli zaman, basinc ve sicaklik okumasi cikarilamadi.",
                status_code=422,
                details={"form_code": form_code, "skipped_rows": skipped},
            )
        source_tag = f"form_{short_code}"
        batch = session_service.batch_add_time_series(
            db,
            session,
            records=parsed_records,
            mode=mode,
            default_source=source_tag,
            commit=True,
        )
        return {
            "direction": "from_form",
            "form_code": form_code,
            "synced_count": len(parsed_records),
            "skipped_rows": skipped,
            "items": batch["items"],
            "summary": batch["summary"],
        }

    # direction == "to_form"
    ts_rows = session_service.get_ordered_time_series(db, session)
    if not ts_rows:
        raise AppError(
            "time_series_empty",
            "Forma aktarilacak zaman serisi kaydi bulunamadi.",
            status_code=422,
            details={"form_code": form_code},
        )
    ensure_section_form_slots(db, session, commit=False)
    if row is None:
        row = db.execute(
            select(SectionForm).where(
                SectionForm.session_id == session.id, SectionForm.form_code == form_code
            )
        ).scalar_one_or_none()
    now = utcnow()
    if row is None:
        row = SectionForm(
            id=new_uuid(),
            workspace_id_hash=session.workspace_id_hash,
            project_id=session.project_id,
            session_id=session.id,
            form_code=spec.code,
            botas_code=spec.botas_code,
            form_title=spec.title,
            required=spec.required,
            status="filled",
            revision=0,
            filled_at=now,
        )
        db.add(row)
        db.flush()

    ts_summary = session_service.time_series_summary(ts_rows)
    ext = copy.deepcopy(row.extracted_data or {}) if isinstance(row.extracted_data, dict) else {}
    mapped_rows = time_series_to_monitoring_rows(ts_rows)
    truncated_rows = max(0, len(ts_rows) - len(mapped_rows))
    ext["rows"] = mapped_rows
    raw_mon = ext.get("monitoring")
    prev_mon: dict[str, Any] = raw_mon if isinstance(raw_mon, dict) else {}
    mon_patch: dict[str, Any] = dict(prev_mon)
    if ts_summary.get("pressure_change_pa_bar") is not None:
        mon_patch["pa_reported_bar"] = round(float(ts_summary["pressure_change_pa_bar"]), 3)
    if ts_summary.get("temperature_change_dt_c") is not None:
        mon_patch["delta_t_reported_c"] = round(float(ts_summary["temperature_change_dt_c"]), 3)
    ext["monitoring"] = mon_patch

    reconciled = reconcile_form_extracted_data(form_code, ext)
    row.extracted_data = json_safe(reconciled)
    flag_modified(row, "extracted_data")
    if row.status == "empty":
        row.status = "filled"
    row.filled_at = row.filled_at or now
    first_ts = ts_summary.get("first_timestamp")
    if not str(row.form_date or "").strip() and isinstance(first_ts, str) and len(first_ts) >= 10:
        row.form_date = first_ts[:10]
    row.revision = int(row.revision or 0) + 1
    row.updated_at = now
    db.flush()

    _cumulative_recompute_section(
        db,
        session,
        header_hint={},
        overwrite_values=False,
        prefer_header_hint=False,
        bump_revision=True,
    )
    audit.record(
        db,
        action="time_series.sync_to_form",
        entity_type="section_form",
        entity_id=row.id,
        session_id=session.id,
        workspace_hash=session.workspace_id_hash,
        after={
            "form_code": form_code,
            "synced_count": len(mapped_rows),
            "truncated_rows": truncated_rows,
        },
    )
    db.commit()
    db.refresh(row)
    db.refresh(session)

    return {
        "direction": "to_form",
        "form_code": form_code,
        "synced_count": len(mapped_rows),
        "skipped_rows": truncated_rows,
        "summary": ts_summary,
        "session": session_service.serialize_session(session),
    }


__all__ = [
    "BOTAS_FORM_CATALOG",
    "FORM_SPEC_BY_CODE",
    "REQUIRED_FORM_SPECS",
    "analyze_dossier_pages",
    "build_dossier_view",
    "classify_form_text",
    "commit_dossier_to_project",
    "compute_forms_summary",
    "compute_project_similarity",
    "ensure_section_form_slots",
    "evaluate_operational_checks",
    "evaluate_section_calculations",
    "extract_page_section_no",
    "extract_project_name_from_pages",
    "extract_project_name_from_text",
    "find_similar_projects",
    "get_session_forms_payload",
    "get_single_session_form_payload",
    "normalize_section_no",
    "scan_single_form_upload",
    "sync_operation_result_to_dewatering_form",
    "sync_time_series_with_form",
    "update_session_form",
]

"""OCR/alan cikarim servisi ve hesaplanan degerlerle karsilastirma.

Katmanlar:

1. :func:`extract_text` - PDF'te gomulu metin katmanini okur; metin yoksa
   veya cok azsa opsiyonel OCR'a duser. Goruntu dosyalarinda dogrudan OCR
   kullanilir.
2. :func:`parse_report` - etiket/regex tabanli alan cikarimi. Turkce
   ondalik virgul, binlik ayirici, tarih formatlari ve birim ekleri
   desteklenir.
3. :func:`compare_with_calculated` - uygulamanin hesapladigi degerlerle
   toleransli karsilastirma.
4. :func:`analyze_report` - tek giris noktasi; guven skoru, uyarilar ve
   insan onayi bayragi ile :class:`OcrAnalysisResult` dondurur.

Agir OCR bagimliliklari (``pytesseract``, ``ocrmac``, ``Pillow``, ``PyMuPDF``)
zorunlu degildir; yoksa metin katmani ile devam edilir ve anlasilir bir
:class:`ReportOcrError` uretilir.
"""

from __future__ import annotations

import asyncio
import difflib
import importlib
import importlib.util
import io
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from dataclasses import dataclass, replace
from datetime import date as _date
from datetime import datetime as _datetime
from pathlib import Path
from typing import Any, Final, Iterator, Mapping, Sequence

from hidrostatik_test.domain.report_schema import (
    FIELD_ALIASES,
    FIELD_LABELS,
    UNIT_BAR,
    UNIT_CELSIUS,
    UNIT_M3,
    UNIT_MICRO_PER_BAR,
    UNIT_MICRO_PER_C,
    AirTestFields,
    ExtractedField,
    HydrotestReport,
    PressureTestFields,
    ValidationIssue,
    convert_temperature_delta,
    convert_unit,
    validate_report,
)

# ---------------------------------------------------------------------------
# Hata kodlari ve sinirlar
# ---------------------------------------------------------------------------

ERROR_INVALID_PATH: Final[str] = "invalid_path"
ERROR_FILE_NOT_FOUND: Final[str] = "file_not_found"
ERROR_UNSUPPORTED_FORMAT: Final[str] = "unsupported_format"
ERROR_FILE_TOO_LARGE: Final[str] = "file_too_large"
ERROR_EMPTY_FILE: Final[str] = "empty_file"
ERROR_ENCRYPTED_PDF: Final[str] = "encrypted_pdf"
ERROR_CORRUPT_DOCUMENT: Final[str] = "corrupt_document"
ERROR_CORRUPT_IMAGE: Final[str] = "corrupt_image"
ERROR_EMPTY_TEXT: Final[str] = "empty_text"
ERROR_OCR_UNAVAILABLE: Final[str] = "ocr_unavailable"
ERROR_DEPENDENCY_MISSING: Final[str] = "dependency_missing"
ERROR_INVALID_CALCULATED: Final[str] = "invalid_calculated"
ERROR_CANCELLED: Final[str] = "ocr_cancelled"
ERROR_TIMEOUT: Final[str] = "ocr_timeout"

DEFAULT_OCR_TOTAL_TIMEOUT_S: Final[float] = 600.0


def _resolve_ocr_total_timeout_seconds() -> float:
    raw = os.environ.get("HYDRO_OCR_TOTAL_TIMEOUT_S")
    if raw is not None and raw.strip():
        try:
            value = float(raw.strip())
        except ValueError:
            return DEFAULT_OCR_TOTAL_TIMEOUT_S
        if value <= 0:
            return 0.0
        return value
    return DEFAULT_OCR_TOTAL_TIMEOUT_S


def _check_ocr_abort(
    cancel_event: threading.Event | None,
    deadline_monotonic: float | None,
) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise ReportOcrError(
            "OCR analizi kullanici tarafindan iptal edildi.",
            ERROR_CANCELLED,
        )
    if deadline_monotonic is not None and time.monotonic() > deadline_monotonic:
        raise ReportOcrError(
            "OCR analizi toplam zaman asimini asti.",
            ERROR_TIMEOUT,
        )


#: Dosya boyutu guvenlik siniri (500 MB varsayilan; HYDRO_MAX_UPLOAD_MB ile
#: 1..500 MB araliginda yapilandirilabilir).
MAX_FILE_SIZE_BYTES: Final[int] = 500 * 1024 * 1024
MAX_ALLOWED_UPLOAD_MB: Final[int] = 500


def effective_max_file_size_bytes() -> int:
    """Return active upload/file size limit (500 MB default, clamped 1..500 MB)."""

    raw = os.environ.get("HYDRO_MAX_UPLOAD_MB")
    if raw is not None and raw.strip():
        try:
            mb = int(raw.strip())
            return max(1, min(mb, MAX_ALLOWED_UPLOAD_MB)) * 1024 * 1024
        except ValueError:
            pass
    return MAX_FILE_SIZE_BYTES


#: PDF sayfa siniri; OCR maliyetini ve calisma suresini sinirlar.
MAX_PDF_PAGES: Final[int] = 200
#: OCR'a verilecek en fazla sayfa sayisi.
MAX_OCR_PAGES: Final[int] = 200
#: Metin katmani bu karakter sayisinin altindaysa OCR denenir.
MIN_TEXT_LAYER_CHARS: Final[int] = 40
#: Regex/veri isleme icin metin uzunlugu siniri.
MAX_TEXT_CHARS: Final[int] = 2_000_000
#: OCR goruntusunun yeniden olceklenme esigi (piksel).
OCR_MIN_IMAGE_WIDTH: Final[int] = 1200

SPREADSHEET_EXTENSIONS: Final[frozenset[str]] = frozenset({".xlsx", ".xls"})
SUPPORTED_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".xlsx", ".xls"}
)
IMAGE_EXTENSIONS: Final[frozenset[str]] = SUPPORTED_EXTENSIONS - {".pdf"} - SPREADSHEET_EXTENSIONS

STATUS_MATCH: Final[str] = "match"
STATUS_WITHIN_TOLERANCE: Final[str] = "within_tolerance"
STATUS_MISMATCH: Final[str] = "mismatch"
STATUS_MISSING_IN_REPORT: Final[str] = "missing_in_report"
STATUS_MISSING_IN_CALCULATION: Final[str] = "missing_in_calculation"
STATUS_NOT_COMPARABLE: Final[str] = "not_comparable"

TEXT_SOURCE_LAYER: Final[str] = "text-layer"
TEXT_SOURCE_OCR: Final[str] = "ocr"
TEXT_SOURCE_SPREADSHEET: Final[str] = "spreadsheet"


class ReportOcrError(Exception):
    """Kullaniciya gosterilebilir, kodlu OCR/rapor okuma hatasi."""

    def __init__(self, message: str, code: str = "ocr_error", *, detail: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.detail = detail

    def to_dict(self) -> dict[str, str]:
        payload = {"code": self.code, "message": self.message}
        if self.detail:
            payload["detail"] = self.detail
        return payload


@dataclass(frozen=True)
class PageText:
    """Tek bir sayfadan cikarilan metin ve kaynagi."""

    page_number: int
    text: str
    source: str = TEXT_SOURCE_LAYER
    confidence: float | None = None
    warning: str = ""

    @property
    def is_ocr(self) -> bool:
        return self.source == TEXT_SOURCE_OCR


@dataclass(frozen=True)
class Discrepancy:
    """Rapor degeri ile hesaplanan deger arasindaki tek karsilastirma.

    ``status`` "match" olsa bile kayit dondurulur; boylece UI tum alanlari
    tek tabloda gosterebilir. CLI yalnizca ``mismatch`` ve
    ``missing_in_report`` durumlarini uyusmazlik sayar.
    """

    field: str
    label: str
    reported: float | str | None
    calculated: float | str | None
    unit: str
    delta: float | None
    tolerance: str
    status: str
    severity: str
    message: str

    @property
    def is_blocking(self) -> bool:
        return self.status in {STATUS_MISMATCH, STATUS_MISSING_IN_REPORT}

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "label": self.label,
            "reported": self.reported,
            "calculated": self.calculated,
            "unit": self.unit,
            "delta": self.delta,
            "tolerance": self.tolerance,
            "status": self.status,
            "severity": self.severity,
            "message": self.message,
        }


@dataclass(frozen=True)
class OcrAnalysisResult:
    """UI/CLI icin tek bir rapor analizinin tam sonucu."""

    path: str
    source: str
    page_count: int
    character_count: int
    confidence: float
    report: HydrotestReport
    discrepancies: tuple[Discrepancy, ...] = ()
    issues: tuple[ValidationIssue, ...] = ()
    warnings: tuple[str, ...] = ()
    needs_human_review: bool = True
    pages: tuple[PageText, ...] = ()

    @property
    def used_ocr(self) -> bool:
        return self.source in {TEXT_SOURCE_OCR, "mixed"}

    @property
    def has_discrepancies(self) -> bool:
        return any(item.is_blocking for item in self.discrepancies)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "source": self.source,
            "page_count": self.page_count,
            "character_count": self.character_count,
            "confidence": round(self.confidence, 4),
            "needs_human_review": self.needs_human_review,
            "used_ocr": self.used_ocr,
            "warnings": list(self.warnings),
            "issues": [issue.to_dict() for issue in self.issues],
            "report": self.report.to_dict(),
            "discrepancies": [item.to_dict() for item in self.discrepancies],
        }


# ---------------------------------------------------------------------------
# Dosya guvenligi
# ---------------------------------------------------------------------------


def validate_input_path(path: str | os.PathLike[str]) -> Path:
    """Validate and resolve an input report path.

    Yol ``resolve()`` ile normallestirilir; boylece ``..`` ve sembolik
    baglanti karmasasi dosya erisim kapsamini genisletmez. Yalnizca
    desteklenen uzantilar ve makul boyuttaki normal dosyalar kabul edilir.
    """

    if path is None or not str(path).strip():
        raise ReportOcrError("Dosya yolu bos olamaz.", ERROR_INVALID_PATH)
    try:
        candidate = Path(path).expanduser()
    except (TypeError, ValueError) as exc:
        raise ReportOcrError("Gecersiz dosya yolu.", ERROR_INVALID_PATH) from exc

    resolved = candidate.resolve()
    if not resolved.exists():
        raise ReportOcrError(f"Rapor dosyasi bulunamadi: {resolved.name}", ERROR_FILE_NOT_FOUND)
    if not resolved.is_file():
        raise ReportOcrError(
            "Verilen yol bir dosya degil.", ERROR_INVALID_PATH, detail=str(resolved)
        )

    suffix = resolved.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ReportOcrError(
            f"Desteklenmeyen dosya turu: {suffix or '(uzantisiz)'}. Desteklenen: {supported}",
            ERROR_UNSUPPORTED_FORMAT,
        )

    try:
        size = resolved.stat().st_size
    except OSError as exc:
        raise ReportOcrError("Dosya bilgisi okunamadi.", ERROR_INVALID_PATH) from exc
    if size == 0:
        raise ReportOcrError("Rapor dosyasi bos.", ERROR_EMPTY_FILE)
    limit_bytes = effective_max_file_size_bytes()
    if size > limit_bytes:
        raise ReportOcrError(
            (
                "Rapor dosyasi boyut sinirini asiyor "
                f"({size / (1024 * 1024):.1f} MB > "
                f"{limit_bytes / (1024 * 1024):.0f} MB)."
            ),
            ERROR_FILE_TOO_LARGE,
        )
    return resolved


# ---------------------------------------------------------------------------
# Metin cikarimi (PDF text layer + opsiyonel OCR)
# ---------------------------------------------------------------------------


def extract_text(
    path: str | os.PathLike[str],
    *,
    language: str | None = None,
    cancel_event: threading.Event | None = None,
    deadline_monotonic: float | None = None,
) -> list[PageText]:
    """Extract text pages from a PDF or an image report.

    PDF'lerde once gomulu metin katmani okunur. Metin katmani yoksa veya
    esigi gecmiyorsa OCR denenir. OCR bagimliligi yoksa metin varsa
    zayif-metin uyarisiyla donulur, metin de yoksa hata yukseltilir.
    """

    _check_ocr_abort(cancel_event, deadline_monotonic)
    resolved = validate_input_path(path)
    suffix = resolved.suffix.lower()
    if suffix in SPREADSHEET_EXTENSIONS:
        return _extract_spreadsheet_text(resolved)
    if suffix == ".pdf":
        pages = _extract_pdf_text(
            resolved,
            cancel_event=cancel_event,
            deadline_monotonic=deadline_monotonic,
        )
        if _text_char_count(pages) >= MIN_TEXT_LAYER_CHARS:
            return pages

        if not _ocr_prerequisites_available():
            if _text_char_count(pages) > 0:
                return _with_page_warning(
                    pages,
                    "PDF metin katmani cok zayif ve OCR bagimliligi kurulu degil; "
                    "alanlar eksik okunabilir.",
                )
            raise ReportOcrError(
                "PDF'te metin katmani bulunamadi ve OCR bagimliligi kurulu degil. "
                "requirements-ocr.txt kurun veya metin katmanli PDF yukleyin.",
                ERROR_OCR_UNAVAILABLE,
            )

        try:
            ocr_pages = _ocr_pdf_pages(
                resolved,
                language=language,
                cancel_event=cancel_event,
                deadline_monotonic=deadline_monotonic,
            )
        except ReportOcrError as exc:
            if exc.code in {ERROR_CANCELLED, ERROR_TIMEOUT}:
                raise
            if _text_char_count(pages) > 0:
                return _with_page_warning(
                    pages,
                    f"Metin katmani zayif; OCR basarisiz oldu ({exc.message}).",
                )
            raise ReportOcrError(
                f"PDF'ten metin cikarilamadi: {exc.message}",
                ERROR_EMPTY_TEXT,
                detail=exc.code,
            ) from exc

        if _text_char_count(ocr_pages) == 0:
            if _text_char_count(pages) > 0:
                return _with_page_warning(
                    pages, "PDF metin katmani zayif ve OCR bos sonuc dondurdu."
                )
            raise ReportOcrError(
                "PDF'ten metin cikarilamadi (bos metin). Belge taranmis ve okunaksiz olabilir.",
                ERROR_EMPTY_TEXT,
            )
        return ocr_pages

    _check_ocr_abort(cancel_event, deadline_monotonic)
    return [_ocr_image_page(resolved, language=language)]


_EXCEL_MAX_ROWS: Final[int] = 2000
_EXCEL_MAX_COLS: Final[int] = 64
_XLSX_MAX_ENTRIES: Final[int] = 500
_XLSX_MAX_UNCOMPRESSED_BYTES: Final[int] = 64 * 1024 * 1024
_OCR_MAX_UPSCALE_PIXELS: Final[int] = 40_000_000
_EXCEL_ERROR_TOKENS: Final[frozenset[str]] = frozenset(
    {"#DIV/0!", "#VALUE!", "#REF!", "#NAME?", "#N/A", "#NUM!", "#NULL!"}
)
_EXCEL_SEP_ONLY_RE: Final[re.Pattern[str]] = re.compile(r"^[:=\-—\s]+$")
_EXCEL_DOT_PLACEHOLDER_RE: Final[re.Pattern[str]] = re.compile(r"^[._\-—\s]{4,}$")
_EXCEL_UNIT_TOKEN_BODY: Final[str] = (
    r"mm|cm|m|km|in|inch|inç|ft|bar|barg|bara|psi|kpa|mpa|°c|ºc|°f|"
    r"m3|m³|m\^3|l|lt|ml|%|1/bar|1/k|1/°c|10\^-?6/bar|10\^?-?6/°c"
)
_EXCEL_UNIT_CELL_RE: Final[re.Pattern[str]] = re.compile(
    rf"^(?:\(?\s*(?:{_EXCEL_UNIT_TOKEN_BODY})\s*\)?|\(\s*[ck]\s*\))\s*[:=]?\s*$",
    re.IGNORECASE,
)
_EXCEL_TRAILING_UNIT_RE: Final[re.Pattern[str]] = re.compile(
    rf"\s*\(\s*(?P<unit>{_EXCEL_UNIT_TOKEN_BODY}|[ck])\s*\)\s*$",
    re.IGNORECASE,
)
_EXCEL_ITEM_PREFIX_RE: Final[re.Pattern[str]] = re.compile(r"^[3-9]\.\s*")
_EXCEL_TRAILING_OP_RE: Final[re.Pattern[str]] = re.compile(r"\d\s*[xX×*+/]\s*$")
_XLS_OLE2_MAGIC: Final[bytes] = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def _validate_xlsx_zip(path: Path) -> None:
    try:
        if not zipfile.is_zipfile(path):
            raise ReportOcrError(
                "Excel (.xlsx) dosyasi gecersiz veya bozuk.",
                ERROR_CORRUPT_DOCUMENT,
            )
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            if len(infos) > _XLSX_MAX_ENTRIES:
                raise ReportOcrError(
                    "Excel (.xlsx) dosyasi guvenlik sinirini asiyor.",
                    ERROR_CORRUPT_DOCUMENT,
                )
            names_lower = {info.filename.lower() for info in infos}
            if "xl/workbook.xml" not in names_lower:
                raise ReportOcrError(
                    "Excel (.xlsx) dosyasi gecersiz veya bozuk (workbook eksik).",
                    ERROR_CORRUPT_DOCUMENT,
                )
            total_uncompressed = 0
            max_uncompressed = int(
                _XLSX_MAX_UNCOMPRESSED_BYTES
                * max(1.0, effective_max_file_size_bytes() / MAX_FILE_SIZE_BYTES)
            )
            for info in infos:
                with archive.open(info, "r") as entry:
                    while chunk := entry.read(65536):
                        total_uncompressed += len(chunk)
                        if total_uncompressed > max_uncompressed:
                            raise ReportOcrError(
                                "Excel (.xlsx) dosyasi guvenlik sinirini asiyor.",
                                ERROR_CORRUPT_DOCUMENT,
                            )
    except ReportOcrError:
        raise
    except Exception as exc:
        raise ReportOcrError(
            "Excel (.xlsx) dosyasi gecersiz veya bozuk.",
            ERROR_CORRUPT_DOCUMENT,
            detail=str(exc),
        ) from exc


def _excel_normalize_cell(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, (_datetime, _date)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return ""
        if value.is_integer():
            return str(int(value))
        return f"{value:.10g}".replace(".", ",")
    text = " ".join(str(value).split()).strip()
    if not text or text.upper() in _EXCEL_ERROR_TOKENS or _EXCEL_DOT_PLACEHOLDER_RE.fullmatch(text):
        return ""
    return text


def _excel_clean_label(raw: str) -> tuple[str, str]:
    text = raw.strip()
    trailing_unit = ""
    if unit_match := _EXCEL_TRAILING_UNIT_RE.search(text):
        trailing_unit = unit_match.group("unit").strip()
        text = text[: unit_match.start()].strip()
    text = _EXCEL_ITEM_PREFIX_RE.sub("", text).strip()
    text = text.rstrip(":= ").strip()
    return text, trailing_unit


def _excel_match_label_key(label: str) -> str | None:
    cleaned = label.strip()
    if not cleaned:
        return None
    probe = f"{_fold(cleaned)} : __VAL__"
    matched = _match_field_line(probe, _ALIAS_PATTERNS, _FUZZY_ALIASES)
    if matched is None:
        return None
    key, rest_start = matched
    return key if probe[rest_start:].strip() == "__VAL__" else None


def _looks_like_excel_value(token: str) -> bool:
    if _EXCEL_TRAILING_OP_RE.search(token):
        return False
    if _looks_like_value(token) or normalize_result(token) is not None:
        return True
    if match := _NUMBER_RE.match(token):
        tail = token[match.end() :].strip()
        if tail and _EXCEL_UNIT_CELL_RE.fullmatch(tail):
            return True
    if len(token) <= 32 and any(char.isdigit() for char in token):
        try:
            parse_date(token)
            return True
        except ValueError:
            pass
    return False


def _excel_format_unit_join(value_line: str, unit: str) -> str:
    sep = "\t" if unit[0].isdigit() else " "
    return f"{value_line}{sep}{unit}"


def _excel_row_to_lines(cells: Sequence[str]) -> list[str]:
    """Convert one Excel row into ``Etiket : Deger`` lines without merging multi-column pairs."""

    stripped_cells = [raw.strip() for raw in cells if raw and raw.strip()]
    if "(" in stripped_cells and ")" in stripped_cells:
        return [" ".join(stripped_cells)]

    lines: list[str] = []
    pending_labels: list[str] = []
    pending_unit = ""

    for raw in cells:
        token = raw.strip()
        if not token or _EXCEL_SEP_ONLY_RE.fullmatch(token):
            continue

        if _EXCEL_UNIT_CELL_RE.fullmatch(token):
            cleaned_unit = token.rstrip(":= ").strip().strip("()")
            if cleaned_unit:
                if lines and not pending_labels and " : " in lines[-1]:
                    lines[-1] = _excel_format_unit_join(lines[-1], cleaned_unit)
                elif not pending_unit:
                    pending_unit = cleaned_unit
            continue

        has_string_label = any(
            _excel_match_label_key(lbl) in (_STRING_FIELDS | {"result", "date"})
            for lbl in pending_labels
        )
        is_explicit_label = _excel_match_label_key(_excel_clean_label(token)[0]) is not None
        is_value = not is_explicit_label and (
            _looks_like_excel_value(token) or (bool(pending_labels) and has_string_label)
        )

        if is_value:
            if pending_labels:
                chosen = pending_labels[-1]
                for candidate in reversed(pending_labels):
                    if _excel_match_label_key(candidate) is not None:
                        chosen = candidate
                        break
                line = f"{chosen} : {token}"
                if pending_unit:
                    line = _excel_format_unit_join(line, pending_unit)
                lines.append(line)
                pending_labels.clear()
                pending_unit = ""
            else:
                lines.append(token)
            continue

        cleaned, inline_unit = _excel_clean_label(token)
        if not cleaned:
            continue

        new_key = _excel_match_label_key(cleaned)
        if pending_labels:
            existing_keys = {
                k for lbl in pending_labels if (k := _excel_match_label_key(lbl)) is not None
            }
            if pending_unit or (
                new_key is not None and existing_keys and new_key not in existing_keys
            ):
                lines.extend(pending_labels)
                pending_labels.clear()
                pending_unit = ""

        pending_labels.append(cleaned)
        if inline_unit and not pending_unit:
            pending_unit = inline_unit

    for leftover in pending_labels:
        lines.append(leftover)
    return lines


def _extract_xlsx_sheets(path: Path) -> list[tuple[str, list[list[str]]]]:
    _validate_xlsx_zip(path)
    if (
        importlib.util.find_spec("openpyxl") is None
        or importlib.util.find_spec("defusedxml") is None
    ):
        raise ReportOcrError(
            "Excel (.xlsx) okumak icin openpyxl ve defusedxml gerekli.",
            ERROR_DEPENDENCY_MISSING,
        )
    excel_reader_mod = importlib.import_module("openpyxl.reader.excel")
    base_reader_cls: type[Any] = excel_reader_mod.ExcelReader

    class _WorksheetOnlyReader(base_reader_cls):
        """Skip chartsheets while keeping sheet indices aligned for defined names."""

        def read_chartsheet(self, sheet: Any, rel: Any) -> None:
            cs = excel_reader_mod.Chartsheet()
            cs._parent = self.wb
            cs.title = getattr(sheet, "name", "Chart")
            self.wb._add_sheet(cs)

    reader: Any = None
    try:
        reader = _WorksheetOnlyReader(path, read_only=True, data_only=True, keep_links=False)
        reader.read()
        wb = reader.wb
    except Exception as exc:
        if reader is not None and getattr(reader, "archive", None) is not None:
            reader.archive.close()
        raise ReportOcrError(
            "Excel (.xlsx) dosyasi okunamadi veya bozuk.",
            ERROR_CORRUPT_DOCUMENT,
            detail=str(exc),
        ) from exc

    sheets: list[tuple[str, list[list[str]]]] = []
    try:
        for ws in wb.worksheets[:MAX_PDF_PAGES]:
            rows: list[list[str]] = []
            for row_values in ws.iter_rows(
                max_row=_EXCEL_MAX_ROWS, max_col=_EXCEL_MAX_COLS, values_only=True
            ):
                cells = [_excel_normalize_cell(val) for val in row_values]
                if any(cells):
                    rows.append([cell for cell in cells if cell])
            sheets.append((ws.title, rows))
    except Exception as exc:
        raise ReportOcrError(
            "Excel (.xlsx) sayfalari okunamadi.",
            ERROR_CORRUPT_DOCUMENT,
            detail=str(exc),
        ) from exc
    finally:
        wb.close()
    return sheets


def _extract_xls_sheets(path: Path) -> list[tuple[str, list[list[str]]]]:
    try:
        with path.open("rb") as handle:
            head = handle.read(len(_XLS_OLE2_MAGIC))
    except OSError as exc:
        raise ReportOcrError(
            "Excel (.xls) dosyasi okunamadi.",
            ERROR_CORRUPT_DOCUMENT,
            detail=str(exc),
        ) from exc
    if head != _XLS_OLE2_MAGIC:
        raise ReportOcrError(
            "Excel (.xls) dosyasi gecersiz veya bozuk.",
            ERROR_CORRUPT_DOCUMENT,
        )

    if importlib.util.find_spec("xlrd") is None:
        raise ReportOcrError(
            "Eski Excel (.xls) okumak icin xlrd gerekli (requirements-ocr.txt).",
            ERROR_DEPENDENCY_MISSING,
        )
    xlrd = importlib.import_module("xlrd")
    try:
        wb = xlrd.open_workbook(str(path), on_demand=True)
    except Exception as exc:
        raise ReportOcrError(
            "Excel (.xls) dosyasi okunamadi veya bozuk.",
            ERROR_CORRUPT_DOCUMENT,
            detail=str(exc),
        ) from exc

    sheets: list[tuple[str, list[list[str]]]] = []
    try:
        for index in range(min(wb.nsheets, MAX_PDF_PAGES)):
            sh = wb.sheet_by_index(index)
            rows: list[list[str]] = []
            for r in range(min(sh.nrows, _EXCEL_MAX_ROWS)):
                row_cells: list[str] = []
                for c in range(min(sh.ncols, _EXCEL_MAX_COLS)):
                    ctype = sh.cell_type(r, c)
                    if ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK, xlrd.XL_CELL_ERROR):
                        continue
                    val = sh.cell_value(r, c)
                    if ctype == xlrd.XL_CELL_DATE:
                        try:
                            val = xlrd.xldate_as_datetime(val, wb.datemode)
                        except Exception:
                            continue
                    elif ctype == xlrd.XL_CELL_BOOLEAN:
                        continue
                    normalized = _excel_normalize_cell(val)
                    if normalized:
                        row_cells.append(normalized)
                if row_cells:
                    rows.append(row_cells)
            sheets.append((sh.name, rows))
    finally:
        wb.release_resources()
    return sheets


def _extract_spreadsheet_text(path: Path) -> list[PageText]:
    suffix = path.suffix.lower()
    sheets = _extract_xlsx_sheets(path) if suffix == ".xlsx" else _extract_xls_sheets(path)

    pages: list[PageText] = []
    for page_index, (sheet_name, rows) in enumerate(sheets, start=1):
        if not rows:
            continue
        lines: list[str] = [sheet_name] if sheet_name else []
        for row in rows:
            lines.extend(_excel_row_to_lines(row))
        sheet_text = "\n".join(line for line in lines if line.strip())
        if sheet_text.strip():
            pages.append(
                PageText(
                    page_number=page_index,
                    text=sheet_text,
                    source=TEXT_SOURCE_SPREADSHEET,
                    confidence=1.0,
                )
            )
    if not pages:
        raise ReportOcrError(
            "Excel raporunda okunabilir metin bulunamadi.",
            ERROR_EMPTY_TEXT,
        )
    return pages


def _extract_pdf_text(
    path: Path,
    *,
    cancel_event: threading.Event | None = None,
    deadline_monotonic: float | None = None,
) -> list[PageText]:
    _check_ocr_abort(cancel_event, deadline_monotonic)
    reader_pages = _extract_pdf_text_with_pypdf(
        path,
        cancel_event=cancel_event,
        deadline_monotonic=deadline_monotonic,
    )
    if reader_pages is not None:
        return reader_pages
    plumber_pages = _extract_pdf_text_with_pdfplumber(
        path,
        cancel_event=cancel_event,
        deadline_monotonic=deadline_monotonic,
    )
    if plumber_pages is not None:
        return plumber_pages
    raise ReportOcrError(
        "PDF okumak icin pypdf (veya pdfplumber) gerekli. requirements-ocr.txt kurun.",
        ERROR_DEPENDENCY_MISSING,
    )


def _extract_pdf_text_with_pypdf(
    path: Path,
    *,
    cancel_event: threading.Event | None = None,
    deadline_monotonic: float | None = None,
) -> list[PageText] | None:
    if importlib.util.find_spec("pypdf") is None:
        return None
    pypdf = importlib.import_module("pypdf")
    try:
        reader = pypdf.PdfReader(str(path))
        _ensure_pdf_not_encrypted(reader)
        page_count = min(len(reader.pages), MAX_PDF_PAGES)
        pages: list[PageText] = []
        for index in range(page_count):
            _check_ocr_abort(cancel_event, deadline_monotonic)
            try:
                text = reader.pages[index].extract_text() or ""
            except Exception:  # tek sayfa bozuksa digerleri okunmaya devam eder
                text = ""
            pages.append(PageText(page_number=index + 1, text=text))
        return pages
    except ReportOcrError:
        raise
    except Exception as exc:
        raise ReportOcrError(
            "PDF dosyasi okunamadi veya bozuk.",
            ERROR_CORRUPT_DOCUMENT,
            detail=str(exc),
        ) from exc


def _extract_pdf_text_with_pdfplumber(
    path: Path,
    *,
    cancel_event: threading.Event | None = None,
    deadline_monotonic: float | None = None,
) -> list[PageText] | None:
    if importlib.util.find_spec("pdfplumber") is None:
        return None
    pdfplumber = importlib.import_module("pdfplumber")
    try:
        with pdfplumber.open(str(path)) as pdf:
            page_count = min(len(pdf.pages), MAX_PDF_PAGES)
            pages: list[PageText] = []
            for index in range(page_count):
                _check_ocr_abort(cancel_event, deadline_monotonic)
                pages.append(
                    PageText(page_number=index + 1, text=pdf.pages[index].extract_text() or "")
                )
            return pages
    except ReportOcrError:
        raise
    except Exception as exc:
        raise ReportOcrError(
            "PDF dosyasi pdfplumber ile okunamadi.",
            ERROR_CORRUPT_DOCUMENT,
            detail=str(exc),
        ) from exc


def _ensure_pdf_not_encrypted(reader: Any) -> None:
    if not getattr(reader, "is_encrypted", False):
        return
    decrypted = False
    try:
        decrypted = bool(reader.decrypt(""))
    except Exception:
        decrypted = False
    if not decrypted:
        raise ReportOcrError(
            "PDF sifreli; sifre girilmeden rapor okunamaz.",
            ERROR_ENCRYPTED_PDF,
        )


def _text_char_count(pages: Sequence[PageText]) -> int:
    return sum(len(page.text.strip()) for page in pages)


def _with_page_warning(pages: Sequence[PageText], message: str) -> list[PageText]:
    if not pages:
        return [PageText(page_number=1, text="", warning=message)]
    return [replace(page, warning=_join_warning(page.warning, message)) for page in pages]


def _join_warning(existing: str, new: str) -> str:
    if not existing:
        return new
    if new in existing:
        return existing
    return f"{existing} {new}"


def _resolve_tesseract_cmd() -> Path | None:
    """Locate a working Tesseract binary (explicit env, bundled app, standard installs, PATH)."""
    env_cmd = os.environ.get("HYDRO_TESSERACT_CMD", "").strip()
    if env_cmd:
        candidate = Path(env_cmd).expanduser()
        if candidate.is_file():
            return candidate

    exe_name = "tesseract.exe" if sys.platform == "win32" else "tesseract"
    bases: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bases.append(Path(meipass))
    try:
        bases.append(Path(sys.executable).resolve().parent)
    except OSError:
        pass

    for base in bases:
        for candidate in (
            base / "tesseract" / exe_name,
            base / "_internal" / "tesseract" / exe_name,
        ):
            if candidate.is_file():
                return candidate

    if sys.platform == "win32":
        win_candidates = [
            Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
            Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
        ]
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            win_candidates.append(
                Path(local_app_data) / "Programs" / "Tesseract-OCR" / "tesseract.exe"
            )
        for candidate in win_candidates:
            if candidate.is_file():
                return candidate

    found = shutil.which("tesseract")
    return Path(found) if found else None


def _configure_pytesseract(pytesseract_mod: Any) -> None:
    cmd_path = _resolve_tesseract_cmd()
    if cmd_path is None:
        return
    pytesseract_mod.pytesseract.tesseract_cmd = str(cmd_path)
    tessdata_dir = cmd_path.parent / "tessdata"
    if not os.environ.get("TESSDATA_PREFIX") and tessdata_dir.is_dir():
        os.environ["TESSDATA_PREFIX"] = str(tessdata_dir)


_OCR_PROBE_LOCK = threading.Lock()
_TESSERACT_PROBE_CACHE: dict[
    tuple[str, str], tuple[float, tuple[bool, str | None, tuple[str, ...]]]
] = {}
_WINDOWS_OCR_PROBE_CACHE: dict[
    tuple[str, str], tuple[float, tuple[bool, str | None, tuple[str, ...], str]]
] = {}
_OCR_PROBE_SUCCESS_TTL_S: Final[float] = 120.0
_OCR_PROBE_FAILURE_TTL_S: Final[float] = 30.0
_TESSERACT_PROBE_TIMEOUT_S: Final[float] = 4.0
_WIN_OCR_MAX_DIMENSION_FALLBACK: Final[int] = 4096


def clear_ocr_probe_cache() -> None:
    """Clear cached OCR engine probe results (next status check re-probes live)."""

    with _OCR_PROBE_LOCK:
        _TESSERACT_PROBE_CACHE.clear()
        _WINDOWS_OCR_PROBE_CACHE.clear()


def _subprocess_win_kwargs() -> dict[str, Any]:
    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        return {"creationflags": flags}
    return {}


def _tesseract_subprocess_env(cmd_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    tessdata_dir = cmd_path.parent / "tessdata"
    if not env.get("TESSDATA_PREFIX") and tessdata_dir.is_dir():
        env["TESSDATA_PREFIX"] = str(tessdata_dir)
    return env


def _probe_tesseract(*, force_refresh: bool = False) -> tuple[bool, str | None, tuple[str, ...]]:
    """Safely probe Tesseract binary once with strict timeouts and TTL caching."""

    if importlib.util.find_spec("pytesseract") is None or importlib.util.find_spec("PIL") is None:
        return False, None, ()

    cmd_path = _resolve_tesseract_cmd()
    if cmd_path is None:
        return False, None, ()

    env = _tesseract_subprocess_env(cmd_path)
    cache_key = (str(cmd_path), env.get("TESSDATA_PREFIX", ""))
    now = time.monotonic()

    if not force_refresh:
        with _OCR_PROBE_LOCK:
            cached = _TESSERACT_PROBE_CACHE.get(cache_key)
            if cached is not None and cached[0] > now:
                return cached[1]

    result: tuple[bool, str | None, tuple[str, ...]] = (False, None, ())
    try:
        ver_proc = subprocess.run(
            [str(cmd_path), "--version"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=_TESSERACT_PROBE_TIMEOUT_S,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=env,
            **_subprocess_win_kwargs(),
        )
        if ver_proc.returncode == 0:
            first_line = next(
                (line.strip() for line in ver_proc.stdout.splitlines() if line.strip()),
                "",
            )
            match = re.search(r"(\d+(?:\.\d+)+)", first_line)
            version_str = match.group(1) if match else (first_line or None)

            langs: list[str] = []
            try:
                lang_proc = subprocess.run(
                    [str(cmd_path), "--list-langs"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=_TESSERACT_PROBE_TIMEOUT_S,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                    env=env,
                    **_subprocess_win_kwargs(),
                )
                if lang_proc.returncode in (0, 1) and lang_proc.stdout:
                    for raw_line in lang_proc.stdout.splitlines():
                        token = raw_line.strip()
                        if re.fullmatch(r"[A-Za-z_]{2,12}", token):
                            langs.append(token)
            except (Exception, SystemExit):
                langs = []

            result = (True, version_str, tuple(sorted(set(langs))))
    except (Exception, SystemExit):
        result = (False, None, ())

    ttl = _OCR_PROBE_SUCCESS_TTL_S if result[0] else _OCR_PROBE_FAILURE_TTL_S
    with _OCR_PROBE_LOCK:
        _TESSERACT_PROBE_CACHE[cache_key] = (time.monotonic() + ttl, result)
    return result


def _tesseract_available() -> bool:
    return _probe_tesseract()[0]


def _run_winrt_coro(coro_factory: Any, *, timeout: float = 30.0) -> Any:
    """Execute a WinRT async coroutine cleanly inside a dedicated MTA worker thread."""

    box: dict[str, Any] = {}

    def _worker() -> None:
        try:
            box["result"] = asyncio.run(coro_factory())
        except BaseException as exc:  # noqa: BLE001
            box["error"] = exc

    thread = threading.Thread(target=_worker, name="hydro-winrt-ocr", daemon=True)
    thread.start()
    thread.join(timeout=timeout)
    if thread.is_alive():
        raise ReportOcrError(
            "Windows yerlesik OCR/PDF islemi zaman asimina ugradi.",
            ERROR_OCR_UNAVAILABLE,
        )
    if "error" in box:
        exc = box["error"]
        if isinstance(exc, ReportOcrError):
            raise exc
        raise exc
    return box.get("result")


def _select_windows_ocr_engine(
    ocr_mod: Any,
    language_cls: Any,
    *,
    language: str | None = None,
) -> tuple[Any, str, tuple[str, ...]]:
    """Select the best Windows.Media.Ocr engine preferring Turkish then user/English."""

    raw_langs = getattr(ocr_mod.OcrEngine, "available_recognizer_languages", ()) or ()
    avail = tuple(
        str(getattr(item, "language_tag", "") or "")
        for item in raw_langs
        if getattr(item, "language_tag", "")
    )
    candidates: list[str] = []
    env_lang = (language or "").strip() or os.environ.get("HYDRO_OCR_LANG", "").strip()
    if env_lang and "+" not in env_lang:
        candidates.append(env_lang)
    candidates.append("tr-TR")
    for tag in avail:
        if tag.casefold().startswith("tr") and tag not in candidates:
            candidates.append(tag)

    for tag in candidates:
        try:
            engine = ocr_mod.OcrEngine.try_create_from_language(language_cls(tag))
            if engine is not None:
                resolved = str(
                    getattr(getattr(engine, "recognizer_language", None), "language_tag", "") or tag
                )
                return engine, resolved, avail
        except Exception:
            continue

    try:
        profile_engine = ocr_mod.OcrEngine.try_create_from_user_profile_languages()
        if profile_engine is not None:
            resolved = str(
                getattr(getattr(profile_engine, "recognizer_language", None), "language_tag", "")
                or ""
            )
            return profile_engine, resolved, avail
    except Exception:
        pass

    fallback_tags = ["en-US", *(t for t in avail if t.casefold().startswith("en")), *avail]
    seen: set[str] = set()
    for tag in fallback_tags:
        if not tag or tag in seen:
            continue
        seen.add(tag)
        try:
            engine = ocr_mod.OcrEngine.try_create_from_language(language_cls(tag))
            if engine is not None:
                resolved = str(
                    getattr(getattr(engine, "recognizer_language", None), "language_tag", "") or tag
                )
                return engine, resolved, avail
        except Exception:
            continue

    return None, "", avail


def _probe_windows_ocr(
    *, force_refresh: bool = False
) -> tuple[bool, str | None, tuple[str, ...], str]:
    """Probe in-process Windows 10/11 WinRT OCR without spawning child processes."""

    if sys.platform != "win32":
        return False, None, (), ""
    if (
        importlib.util.find_spec("winrt.windows.media.ocr") is None
        or importlib.util.find_spec("winrt.windows.globalization") is None
        or importlib.util.find_spec("PIL") is None
    ):
        return False, None, (), ""

    cache_key = (sys.platform, os.environ.get("HYDRO_OCR_LANG", ""))
    now = time.monotonic()
    if not force_refresh:
        with _OCR_PROBE_LOCK:
            cached = _WINDOWS_OCR_PROBE_CACHE.get(cache_key)
            if cached is not None and cached[0] > now:
                return cached[1]

    result: tuple[bool, str | None, tuple[str, ...], str] = (False, None, (), "")
    try:
        ocr_mod = importlib.import_module("winrt.windows.media.ocr")
        glob_mod = importlib.import_module("winrt.windows.globalization")
        engine, active_lang, avail = _select_windows_ocr_engine(ocr_mod, glob_mod.Language)
        if engine is not None:
            win_ver = platform.version() or "WinRT"
            result = (True, win_ver, avail or ((active_lang,) if active_lang else ()), active_lang)
    except (Exception, SystemExit):
        result = (False, None, (), "")

    ttl = _OCR_PROBE_SUCCESS_TTL_S if result[0] else _OCR_PROBE_FAILURE_TTL_S
    with _OCR_PROBE_LOCK:
        _WINDOWS_OCR_PROBE_CACHE[cache_key] = (time.monotonic() + ttl, result)
    return result


def windows_ocr_available() -> bool:
    """Return ``True`` when Windows 10/11 built-in WinRT OCR is usable in-process."""

    return _probe_windows_ocr()[0]


def _pypdfium2_usable() -> bool:
    """Return ``True`` only if ``pypdfium2`` and its native DLL load cleanly."""

    if importlib.util.find_spec("pypdfium2") is None:
        return False
    try:
        importlib.import_module("pypdfium2")
    except (ImportError, OSError):
        return False
    return True


def windows_pdf_available() -> bool:
    """Return ``True`` when built-in Windows 10/11 ``Windows.Data.Pdf`` WinRT API is usable."""

    if sys.platform != "win32":
        return False
    if (
        importlib.util.find_spec("winrt.windows.data.pdf") is None
        or importlib.util.find_spec("winrt.windows.storage.streams") is None
    ):
        return False
    try:
        importlib.import_module("winrt.windows.data.pdf")
        importlib.import_module("winrt.windows.storage.streams")
    except (ImportError, OSError):
        return False
    return True


def pdf_rasterizer_status() -> tuple[bool, str | None]:
    """Return ``(available, engine_name)`` for rendering scanned PDF pages to images."""
    if importlib.util.find_spec("fitz") is not None:
        return True, "PyMuPDF"
    if _pypdfium2_usable():
        return True, "pypdfium2"
    if (
        sys.platform == "darwin"
        and importlib.util.find_spec("Quartz") is not None
        and importlib.util.find_spec("CoreFoundation") is not None
    ):
        return True, "macOS Quartz"
    if windows_pdf_available():
        return True, "Windows PDF (WinRT)"
    if importlib.util.find_spec("pdf2image") is not None:
        return True, "pdf2image"
    return False, None


def vision_available() -> bool:
    """Return ``True`` when the macOS Vision engine (``ocrmac``) is usable."""

    if sys.platform != "darwin":
        return False
    if importlib.util.find_spec("ocrmac") is None:
        return False
    try:
        import Vision  # noqa: F401  # type: ignore[import-not-found]
        from ocrmac import ocrmac  # noqa: F401  # type: ignore[import-not-found]
    except Exception:
        return False
    return True


def ocr_available() -> bool:
    """Return ``True`` when at least one OCR engine is usable."""

    return bool(_resolve_ocr_engine())


def _resolve_ocr_engine() -> str:
    """Return ``"windows_ocr"``, ``"tesseract"``, ``"vision"`` or ``""``.

    ``HYDRO_OCR_ENGINE`` ile zorlanabilir: ``auto`` (varsayilan),
    ``windows_ocr`` / ``winrt``, ``tesseract`` veya ``vision``.
    """

    requested = os.environ.get("HYDRO_OCR_ENGINE", "auto").strip().casefold()
    if requested in {"windows_ocr", "winrt"}:
        return "windows_ocr" if windows_ocr_available() else ""
    if requested == "tesseract":
        return "tesseract" if _tesseract_available() else ""
    if requested == "vision":
        return "vision" if vision_available() else ""
    if sys.platform == "win32" and windows_ocr_available():
        return "windows_ocr"
    if _tesseract_available():
        return "tesseract"
    if vision_available():
        return "vision"
    return ""


def ocr_engine_name() -> str:
    """Return active engine name: ``windows_ocr``, ``tesseract``, ``vision`` or ``""``."""

    return _resolve_ocr_engine()


def ocr_engine_details(*, force_refresh: bool = False) -> dict[str, Any]:
    """Return normalized engine availability, metadata, languages and status text."""

    if force_refresh:
        clear_ocr_probe_cache()

    engine = _resolve_ocr_engine()
    if engine == "windows_ocr":
        _, win_ver, langs, active_lang = _probe_windows_ocr()
        return {
            "available": True,
            "engine_name": "windows_ocr",
            "version": win_ver,
            "languages": list(langs),
            "default_language": active_lang or "tr-TR",
            "status_text": "OCR hazir (Windows yerlesik WinRT OCR + Pillow).",
        }
    if engine == "tesseract":
        _, ver, langs = _probe_tesseract()
        return {
            "available": True,
            "engine_name": "tesseract",
            "version": ver,
            "languages": list(langs),
            "default_language": os.environ.get("HYDRO_OCR_LANG", "tur+eng"),
            "status_text": "OCR hazir (Tesseract + Pillow).",
        }
    if engine == "vision":
        return {
            "available": True,
            "engine_name": "vision",
            "version": platform.mac_ver()[0] or None,
            "languages": ["tr-TR", "en-US"],
            "default_language": "tr-TR",
            "status_text": "OCR hazir (macOS Vision, ocrmac).",
        }

    if importlib.util.find_spec("PIL") is None:
        status_text = "OCR yok: Pillow kurulu degil (requirements-ocr.txt)."
    elif sys.platform == "win32":
        status_text = "OCR yok: Windows OCR dil paketi (WinRT) veya Tesseract calistirilabilir dosyasi kullanilamadi."
    elif importlib.util.find_spec("pytesseract") is None:
        if sys.platform == "darwin":
            status_text = "OCR yok: pytesseract/ocrmac kurulu degil (requirements-ocr.txt)."
        else:
            status_text = "OCR yok: pytesseract kurulu degil (requirements-ocr.txt)."
    elif sys.platform == "darwin":
        status_text = "OCR yok: tesseract calistirilabilir dosyasi ve macOS Vision kullanilamadi."
    else:
        status_text = "OCR yok: tesseract calistirilabilir dosyasi bulunamadi."

    return {
        "available": False,
        "engine_name": None,
        "version": None,
        "languages": [],
        "default_language": (
            "tr-TR" if sys.platform == "win32" else os.environ.get("HYDRO_OCR_LANG", "tur+eng")
        ),
        "status_text": status_text,
    }


def ocr_status() -> str:
    """Return a short human-readable OCR availability note."""

    return str(ocr_engine_details()["status_text"])


def _ocr_prerequisites_available() -> bool:
    return ocr_available()


def _max_ocr_pages() -> int:
    raw = os.environ.get("HYDRO_OCR_MAX_PAGES", "").strip()
    if raw:
        try:
            value = int(raw)
        except ValueError:
            value = MAX_OCR_PAGES
        return max(1, min(value, MAX_PDF_PAGES))
    return MAX_OCR_PAGES


def _iter_rendered_pdf_pages_with_fitz(
    path: Path,
    *,
    start_page: int,
    max_pages: int,
    dpi: int,
    rotate_deg: int,
    image_mod: Any,
) -> Iterator[Any]:
    fitz = importlib.import_module("fitz")
    try:
        document = fitz.open(str(path))
    except Exception as exc:
        raise ReportOcrError(
            "PDF OCR icin acilamadi.", ERROR_CORRUPT_DOCUMENT, detail=str(exc)
        ) from exc

    scale = dpi / 72.0
    norm_rot = rotate_deg % 360
    try:
        end = min(len(document), start_page + max_pages)
        for index in range(start_page, end):
            page = document[index]
            if norm_rot:
                matrix = fitz.Matrix(scale, scale).prerotate(norm_rot)
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            else:
                pixmap = page.get_pixmap(dpi=dpi, alpha=False)
            yield image_mod.open(io.BytesIO(pixmap.tobytes("png")))
    except ReportOcrError:
        raise
    except Exception as exc:
        raise ReportOcrError(
            "PDF sayfasi goruntuye cevrilemedi.", ERROR_CORRUPT_DOCUMENT, detail=str(exc)
        ) from exc
    finally:
        document.close()


def _iter_rendered_pdf_pages_with_pypdfium2(
    path: Path,
    *,
    start_page: int,
    max_pages: int,
    dpi: int,
    rotate_deg: int,
) -> Iterator[Any]:
    pdfium = importlib.import_module("pypdfium2")
    try:
        document = pdfium.PdfDocument(str(path))
    except OSError:
        raise
    except Exception as exc:
        msg = str(exc).lower()
        code = ERROR_ENCRYPTED_PDF if "password" in msg else ERROR_CORRUPT_DOCUMENT
        raise ReportOcrError("PDF OCR icin acilamadi.", code, detail=str(exc)) from exc

    scale = dpi / 72.0
    norm_rot = rotate_deg % 360
    pdfium_rot = norm_rot if norm_rot in {0, 90, 180, 270} else 0
    try:
        end = min(len(document), start_page + max_pages)
        for index in range(start_page, end):
            page = document[index]
            bitmap = None
            try:
                bitmap = page.render(scale=scale, rotation=pdfium_rot)
                pil_img = bitmap.to_pil().copy()
            finally:
                if bitmap is not None:
                    bitmap.close()
                page.close()
            if norm_rot and norm_rot != pdfium_rot:
                pil_img = pil_img.rotate(-norm_rot, expand=True)
            yield pil_img
    except ReportOcrError:
        raise
    except OSError:
        raise
    except Exception as exc:
        raise ReportOcrError(
            "PDF sayfasi pypdfium2 ile goruntuye cevrilemedi.",
            ERROR_CORRUPT_DOCUMENT,
            detail=str(exc),
        ) from exc
    finally:
        document.close()


def _iter_rendered_pdf_pages_with_quartz(
    path: Path,
    *,
    start_page: int,
    max_pages: int,
    dpi: int,
    rotate_deg: int,
    image_mod: Any,
) -> Iterator[Any]:
    CoreFoundation = importlib.import_module("CoreFoundation")
    Quartz = importlib.import_module("Quartz")

    raw_path = os.fsencode(str(path))
    url = CoreFoundation.CFURLCreateFromFileSystemRepresentation(
        None, raw_path, len(raw_path), False
    )
    if url is None:
        raise ReportOcrError("PDF dosya yolu okunamadi.", ERROR_INVALID_PATH)
    document = Quartz.CGPDFDocumentCreateWithURL(url)
    if document is None:
        raise ReportOcrError("PDF OCR icin acilamadi.", ERROR_CORRUPT_DOCUMENT)
    if not Quartz.CGPDFDocumentIsUnlocked(document) and not Quartz.CGPDFDocumentUnlockWithPassword(
        document, b""
    ):
        raise ReportOcrError("PDF sifreli; sifre girilmeden rapor okunamaz.", ERROR_ENCRYPTED_PDF)

    scale = dpi / 72.0
    norm_rot = rotate_deg % 360
    page_count = int(Quartz.CGPDFDocumentGetNumberOfPages(document))
    end = min(page_count, start_page + max_pages)
    cs = Quartz.CGColorSpaceCreateDeviceRGB()

    for one_based in range(start_page + 1, end + 1):
        page = Quartz.CGPDFDocumentGetPage(document, one_based)
        if page is None:
            continue
        rect = Quartz.CGPDFPageGetBoxRect(page, Quartz.kCGPDFCropBox)
        page_rot = int(Quartz.CGPDFPageGetRotationAngle(page) or 0) % 360
        bw = rect.size.height * scale if page_rot in {90, 270} else rect.size.width * scale
        bh = rect.size.width * scale if page_rot in {90, 270} else rect.size.height * scale
        width = max(1, int(round(bw)))
        height = max(1, int(round(bh)))

        ctx = Quartz.CGBitmapContextCreate(
            None,
            width,
            height,
            8,
            width * 4,
            cs,
            Quartz.kCGImageAlphaPremultipliedLast,
        )
        if ctx is None:
            raise ReportOcrError("Quartz bitmap baglami olusturulamadi.", ERROR_CORRUPT_DOCUMENT)
        Quartz.CGContextSetRGBFillColor(ctx, 1.0, 1.0, 1.0, 1.0)
        Quartz.CGContextFillRect(ctx, Quartz.CGRectMake(0, 0, width, height))
        tx = Quartz.CGPDFPageGetDrawingTransform(
            page,
            Quartz.kCGPDFCropBox,
            Quartz.CGRectMake(0, 0, width, height),
            0,
            True,
        )
        Quartz.CGContextConcatCTM(ctx, tx)
        Quartz.CGContextDrawPDFPage(ctx, page)
        cg_img = Quartz.CGBitmapContextCreateImage(ctx)
        if cg_img is None:
            raise ReportOcrError("Quartz PDF goruntusu uretilemedi.", ERROR_CORRUPT_DOCUMENT)
        data = Quartz.CGDataProviderCopyData(Quartz.CGImageGetDataProvider(cg_img))
        bpr = Quartz.CGImageGetBytesPerRow(cg_img)
        pil_img = image_mod.frombuffer(
            "RGBA", (width, height), bytes(data), "raw", "RGBA", bpr, 1
        ).convert("RGB")
        if norm_rot:
            pil_img = pil_img.rotate(-norm_rot, expand=True)
        yield pil_img


def _iter_rendered_pdf_pages_with_windows_pdf(
    path: Path,
    *,
    start_page: int,
    max_pages: int,
    dpi: int,
    rotate_deg: int,
    image_mod: Any,
) -> Iterator[Any]:
    """Render PDF pages in-process using built-in Windows 10/11 ``Windows.Data.Pdf``."""

    try:
        pdf_bytes = path.read_bytes()
    except OSError as exc:
        raise ReportOcrError(
            "PDF dosyasi okunamadi.", ERROR_FILE_NOT_FOUND, detail=str(exc)
        ) from exc
    if not pdf_bytes:
        raise ReportOcrError("PDF dosyasi bos.", ERROR_EMPTY_FILE)

    async def _render_pages() -> list[bytes]:
        pdf_mod = importlib.import_module("winrt.windows.data.pdf")
        streams_mod = importlib.import_module("winrt.windows.storage.streams")

        white_color = None
        try:
            ui_mod = importlib.import_module("winrt.windows.ui")
            if hasattr(ui_mod, "ColorHelper"):
                white_color = ui_mod.ColorHelper.from_argb(255, 255, 255, 255)
            elif hasattr(ui_mod, "Color"):
                white_color = ui_mod.Color(255, 255, 255, 255)
        except Exception:
            white_color = None

        pdf_stream = streams_mod.InMemoryRandomAccessStream()
        try:
            in_buf = streams_mod.Buffer(len(pdf_bytes))
            in_buf.length = len(pdf_bytes)
            with memoryview(in_buf) as mv:
                mv[:] = pdf_bytes
            await pdf_stream.write_async(in_buf)
            await pdf_stream.flush_async()
            pdf_stream.seek(0)

            try:
                doc = await pdf_mod.PdfDocument.load_from_stream_async(pdf_stream)
            except Exception as exc:
                msg = str(exc).lower()
                code = (
                    ERROR_ENCRYPTED_PDF
                    if "password" in msg or "encrypt" in msg
                    else ERROR_CORRUPT_DOCUMENT
                )
                raise ReportOcrError(
                    "PDF Windows PDF okuyucu ile acilamadi.", code, detail=str(exc)
                ) from exc

            if getattr(doc, "is_password_protected", False):
                raise ReportOcrError(
                    "PDF sifreli; sifre girilmeden rapor okunamaz.",
                    ERROR_ENCRYPTED_PDF,
                )

            page_count = int(getattr(doc, "page_count", 0) or 0)
            end = min(page_count, start_page + max_pages)
            png_pages: list[bytes] = []
            for index in range(start_page, end):
                page = doc.get_page(index)
                out_stream = streams_mod.InMemoryRandomAccessStream()
                try:
                    options = pdf_mod.PdfPageRenderOptions()
                    size = page.size
                    if float(size.width) > 0 and float(size.height) > 0:
                        options.destination_width = max(
                            1, int(round(float(size.width) * dpi / 96.0))
                        )
                        options.destination_height = max(
                            1, int(round(float(size.height) * dpi / 96.0))
                        )
                    if white_color is not None:
                        options.background_color = white_color
                    await page.render_to_stream_async(out_stream, options)
                    out_size = int(out_stream.size)
                    if out_size > 0:
                        reader = streams_mod.DataReader(out_stream.get_input_stream_at(0))
                        try:
                            loaded = await reader.load_async(out_size)
                            out_buf = reader.read_buffer(loaded)
                            png_pages.append(bytes(out_buf))
                        finally:
                            if hasattr(reader, "close"):
                                reader.close()
                finally:
                    if hasattr(out_stream, "close"):
                        out_stream.close()
                    if hasattr(page, "close"):
                        page.close()
            return png_pages
        finally:
            if hasattr(pdf_stream, "close"):
                pdf_stream.close()

    try:
        png_list: list[bytes] = _run_winrt_coro(
            _render_pages,
            timeout=max(45.0, float(max_pages) * 5.0),
        )
    except ReportOcrError:
        raise
    except Exception as exc:
        raise ReportOcrError(
            "PDF sayfasi Windows yerlesik PDF motoru ile goruntuye cevrilemedi.",
            ERROR_CORRUPT_DOCUMENT,
            detail=str(exc),
        ) from exc

    norm_rot = rotate_deg % 360
    for png_bytes in png_list:
        pil_img = image_mod.open(io.BytesIO(png_bytes)).convert("RGB")
        if norm_rot:
            pil_img = pil_img.rotate(-norm_rot, expand=True)
        yield pil_img


def _iter_rendered_pdf_pages(
    path: Path,
    *,
    max_pages: int | None = None,
    dpi: int = 200,
    rotate_deg: int = 0,
    start_page: int = 0,
) -> Iterator[Any]:
    """Stream rasterized PIL pages using the first available PDF rendering backend."""
    if importlib.util.find_spec("PIL") is None:
        raise ReportOcrError(
            "Goruntu/PDF sayfasi islemek icin Pillow gerekli (requirements-ocr.txt).",
            ERROR_DEPENDENCY_MISSING,
        )
    from PIL import Image  # noqa: PLC0415

    limit = max_pages if max_pages is not None else _max_ocr_pages()
    first = max(0, int(start_page))
    norm_rot = rotate_deg % 360

    if importlib.util.find_spec("fitz") is not None:
        yield from _iter_rendered_pdf_pages_with_fitz(
            path,
            start_page=first,
            max_pages=limit,
            dpi=dpi,
            rotate_deg=norm_rot,
            image_mod=Image,
        )
        return

    if _pypdfium2_usable():
        yielded_any = False
        try:
            for pil_img in _iter_rendered_pdf_pages_with_pypdfium2(
                path,
                start_page=first,
                max_pages=limit,
                dpi=dpi,
                rotate_deg=norm_rot,
            ):
                yielded_any = True
                yield pil_img
            return
        except (ImportError, OSError):
            if yielded_any:
                raise

    if (
        sys.platform == "darwin"
        and importlib.util.find_spec("Quartz") is not None
        and importlib.util.find_spec("CoreFoundation") is not None
    ):
        yield from _iter_rendered_pdf_pages_with_quartz(
            path,
            start_page=first,
            max_pages=limit,
            dpi=dpi,
            rotate_deg=norm_rot,
            image_mod=Image,
        )
        return

    if windows_pdf_available():
        yield from _iter_rendered_pdf_pages_with_windows_pdf(
            path,
            start_page=first,
            max_pages=limit,
            dpi=dpi,
            rotate_deg=norm_rot,
            image_mod=Image,
        )
        return

    if importlib.util.find_spec("pdf2image") is not None:
        pdf2image = importlib.import_module("pdf2image")
        try:
            images = list(
                pdf2image.convert_from_path(
                    str(path),
                    dpi=dpi,
                    first_page=first + 1,
                    last_page=first + limit,
                )
            )
        except Exception as exc:
            raise ReportOcrError(
                "PDF sayfalari OCR icin goruntuye cevrilemedi.",
                ERROR_CORRUPT_DOCUMENT,
                detail=str(exc),
            ) from exc
        for image in images:
            yield image.rotate(-norm_rot, expand=True) if norm_rot else image
        return

    raise ReportOcrError(
        "Taranmis PDF'ler icin pypdfium2, PyMuPDF, Windows PDF (WinRT) veya pdf2image gerekli.",
        ERROR_OCR_UNAVAILABLE,
    )


def _render_pdf_pages(path: Path) -> list[Any]:
    """Rasterize PDF pages with the first available optional backend."""
    return list(_iter_rendered_pdf_pages(path, max_pages=_max_ocr_pages(), dpi=200))


def _ocr_pdf_pages(
    path: Path,
    *,
    language: str | None = None,
    cancel_event: threading.Event | None = None,
    deadline_monotonic: float | None = None,
) -> list[PageText]:
    _check_ocr_abort(cancel_event, deadline_monotonic)
    engine = _resolve_ocr_engine()
    if engine == "windows_ocr":
        return _ocr_pdf_pages_with_windows_ocr(
            path,
            language=language,
            cancel_event=cancel_event,
            deadline_monotonic=deadline_monotonic,
        )
    if engine == "vision":
        return _ocr_pdf_pages_with_vision(
            path,
            language=language,
            cancel_event=cancel_event,
            deadline_monotonic=deadline_monotonic,
        )
    if engine != "tesseract":
        raise ReportOcrError(
            "Taranmis PDF icin OCR motoru bulunamadi (Windows OCR, Tesseract veya macOS Vision).",
            ERROR_OCR_UNAVAILABLE,
        )

    pages: list[PageText] = []
    for index, image in enumerate(
        _iter_rendered_pdf_pages(path, max_pages=_max_ocr_pages(), dpi=200)
    ):
        _check_ocr_abort(cancel_event, deadline_monotonic)
        text, confidence, warning = _run_tesseract(image, language=language)
        pages.append(
            PageText(
                page_number=index + 1,
                text=text,
                source=TEXT_SOURCE_OCR,
                confidence=confidence,
                warning=warning,
            )
        )
    return pages


def _ocr_pdf_pages_with_vision(
    path: Path,
    *,
    language: str | None = None,
    cancel_event: threading.Event | None = None,
    deadline_monotonic: float | None = None,
) -> list[PageText]:
    """OCR PDF pages sequentially with the macOS Vision framework."""
    pages: list[PageText] = []
    for index, image in enumerate(
        _iter_rendered_pdf_pages(path, max_pages=_max_ocr_pages(), dpi=200)
    ):
        _check_ocr_abort(cancel_event, deadline_monotonic)
        text, confidence, warning = _run_vision(image, language=language)
        pages.append(
            PageText(
                page_number=index + 1,
                text=text,
                source=TEXT_SOURCE_OCR,
                confidence=confidence,
                warning=warning,
            )
        )
    return pages


def _ocr_pdf_pages_with_windows_ocr(
    path: Path,
    *,
    language: str | None = None,
    cancel_event: threading.Event | None = None,
    deadline_monotonic: float | None = None,
) -> list[PageText]:
    """OCR PDF pages sequentially in-process with Windows 10/11 WinRT OCR."""
    pages: list[PageText] = []
    for index, image in enumerate(
        _iter_rendered_pdf_pages(path, max_pages=_max_ocr_pages(), dpi=200)
    ):
        _check_ocr_abort(cancel_event, deadline_monotonic)
        text, confidence, warning = _run_windows_ocr(image, language=language)
        pages.append(
            PageText(
                page_number=index + 1,
                text=text,
                source=TEXT_SOURCE_OCR,
                confidence=confidence,
                warning=warning,
            )
        )
    return pages


def ocr_pdf_page_rotated(
    path: str | os.PathLike[str],
    *,
    page_index: int = 0,
    rotate_deg: int = 270,
    zoom: float = 3.2,
) -> PageText | None:
    """Dondurulmus (orn. 90/270 derece yan donmus CAD paftasi) PDF sayfasini yuksek cozunurlukle OCR okur."""
    if not ocr_available():
        return None
    engine = _resolve_ocr_engine()
    if engine not in {"windows_ocr", "vision", "tesseract"}:
        return None

    resolved = validate_input_path(path)
    dpi = max(72, int(round(72.0 * zoom)))
    try:
        rendered = list(
            _iter_rendered_pdf_pages(
                resolved,
                start_page=page_index,
                max_pages=1,
                dpi=dpi,
                rotate_deg=rotate_deg,
            )
        )
    except ReportOcrError:
        return None
    if not rendered:
        return None
    image = rendered[0]

    if engine == "windows_ocr":
        text, confidence, warning = _run_windows_ocr(image)
    elif engine == "vision":
        text, confidence, warning = _run_vision(image)
    else:
        text, confidence, warning = _run_tesseract(image)
    return PageText(
        page_number=page_index + 1,
        text=text,
        source=TEXT_SOURCE_OCR,
        confidence=confidence,
        warning=warning,
    )


def _ocr_image_page(path: Path, *, language: str | None = None) -> PageText:
    image = _load_image(path)
    engine = _resolve_ocr_engine()
    if engine == "windows_ocr":
        text, confidence, warning = _run_windows_ocr(image, language=language)
    elif engine == "vision":
        text, confidence, warning = _run_vision(image, language=language)
    elif engine == "tesseract":
        text, confidence, warning = _run_tesseract(image, language=language)
    else:
        has_ocr_pkg = (
            importlib.util.find_spec("pytesseract") is not None
            or (sys.platform == "darwin" and importlib.util.find_spec("ocrmac") is not None)
            or (
                sys.platform == "win32"
                and importlib.util.find_spec("winrt.windows.media.ocr") is not None
            )
        )
        if not has_ocr_pkg:
            raise ReportOcrError(
                "Goruntu OCR icin pytesseract/Pillow, Windows WinRT veya macOS Vision (ocrmac) gerekli "
                "(requirements-ocr.txt).",
                ERROR_DEPENDENCY_MISSING,
            )
        raise ReportOcrError(
            "Goruntu OCR motoru kullanilamiyor (Windows OCR, Tesseract veya macOS Vision bulunamadi).",
            ERROR_OCR_UNAVAILABLE,
        )
    if not text.strip():
        raise ReportOcrError(
            "Goruntuden metin okunamadi; belge okunaksiz veya bos olabilir.",
            ERROR_EMPTY_TEXT,
        )
    return PageText(
        page_number=1,
        text=text,
        source=TEXT_SOURCE_OCR,
        confidence=confidence,
        warning=warning,
    )


def _load_image(path: Path) -> Any:
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:  # pragma: no cover - find_spec ile onceden kontrol edilir
        raise ReportOcrError(
            "Goruntu okumak icin Pillow gerekli.", ERROR_DEPENDENCY_MISSING
        ) from exc

    bomb_errors: tuple[type[BaseException], ...] = tuple(
        cls
        for cls in (
            getattr(Image, "DecompressionBombError", None),
            getattr(Image, "DecompressionBombWarning", None),
        )
        if isinstance(cls, type) and issubclass(cls, BaseException)
    )
    image_errors: tuple[type[BaseException], ...] = (
        UnidentifiedImageError,
        OSError,
        ValueError,
        MemoryError,
        *bomb_errors,
    )
    try:
        with Image.open(path) as image:
            image.load()
            grayscale = image.convert("L")
    except image_errors as exc:
        raise ReportOcrError(
            "Goruntu dosyasi bozuk, cok buyuk veya desteklenmiyor.",
            ERROR_CORRUPT_IMAGE,
            detail=str(exc),
        ) from exc

    if grayscale.width < OCR_MIN_IMAGE_WIDTH:
        scale = 2
        upscaled_pixels = (grayscale.width * scale) * (grayscale.height * scale)
        if upscaled_pixels <= _OCR_MAX_UPSCALE_PIXELS:
            grayscale = grayscale.resize(
                (grayscale.width * scale, grayscale.height * scale),
                Image.Resampling.LANCZOS,
            )
    return grayscale


def _choose_tesseract_language(language: str | None = None) -> tuple[str, str]:
    override = (language or "").strip() or os.environ.get("HYDRO_OCR_LANG", "").strip()
    if override:
        return override, ""

    ok, _, cached_langs = _probe_tesseract()
    available = set(cached_langs) if ok else set()

    selected = [lang for lang in ("tur", "eng") if lang in available]
    if selected:
        return "+".join(selected), ""
    return "eng", "Tesseract 'tur' dil paketi bulunamadi; OCR ingilizce ile yapildi."


def _run_tesseract(image: Any, *, language: str | None = None) -> tuple[str, float | None, str]:
    try:
        pytesseract = importlib.import_module("pytesseract")
        _configure_pytesseract(pytesseract)
    except ImportError as exc:  # pragma: no cover - onceden kontrol edilir
        raise ReportOcrError("OCR icin pytesseract gerekli.", ERROR_OCR_UNAVAILABLE) from exc

    resolved_language, warning = _choose_tesseract_language(language)
    try:
        data = pytesseract.image_to_data(
            image,
            lang=resolved_language,
            output_type=pytesseract.Output.DICT,
            timeout=60,
        )
    except (Exception, SystemExit) as exc:
        raise ReportOcrError(
            "OCR calistirilamadi; tesseract kurulumunu ve dil paketlerini kontrol edin.",
            ERROR_OCR_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    lines: dict[tuple[int, int, int], list[str]] = {}
    confidences: list[float] = []
    for index, word in enumerate(data.get("text", [])):
        cleaned = str(word).strip()
        if not cleaned:
            continue
        key = (
            int(data["block_num"][index]),
            int(data["par_num"][index]),
            int(data["line_num"][index]),
        )
        lines.setdefault(key, []).append(cleaned)
        try:
            confidence = float(data["conf"][index])
        except (TypeError, ValueError, KeyError, IndexError):
            continue
        if confidence >= 0:
            confidences.append(confidence)

    text = "\n".join(" ".join(words) for _, words in sorted(lines.items()))
    mean_confidence = (sum(confidences) / len(confidences) / 100.0) if confidences else None
    return text, mean_confidence, warning


_VISION_LANGUAGES: Final[tuple[str, ...]] = ("tr-TR", "en-US")

#: Vision kutularini ayni form satirinda kabul etmek icin dikey tolerans
#: (sayfa yuksekliginin orani). Form satirlari ~0.011 araliklarla
#: yerlesir; 0.005'ten buyuk bir tolerans komsu satirin degerini
#: etikete baglar (ornegin "Boru Ic Capi" -> bir alt satirdaki "5,20").
_VISION_ROW_TOLERANCE: Final[float] = 0.005
#: Etiket ile deger arasinda kabul edilen en buyuk yatay bosluk. Genis
#: parametre tablolarinda deger sutunu sayfanin sagina yaslanir.
_VISION_MAX_GAP: Final[float] = 0.75
#: Bu uzunluktan kisa etiketler "gercek etiket" sayilir; bir degerin
#: onlarin otesine baglanmasi ayni satirdaki baska alanin degerini
#: calmasina yol acar (ornegin "Test Bolum No" -> "Tarih" degeri).
_VISION_SHORT_LABEL_MAX: Final[int] = 28


_VISION_UNIT_ONLY_RE: Final[re.Pattern[str]] = re.compile(
    r"^\(?\s*(?:mm|cm|m|km|in|inch|ft|bar|barg|bara|psi|kpa|mpa|°c|ºc|c|m3|m³|m\^3|l|lt|ml|%|"
    r"1/bar|1/k|1/°c|10\^-?6/bar|10\^?-?6/°c)\s*\)?$",
    re.IGNORECASE,
)
_VISION_NUMERIC_RE: Final[re.Pattern[str]] = re.compile(r"[\d.,:'+\-/\s]+")
_VISION_CODE_RE: Final[re.Pattern[str]] = re.compile(r"[A-ZÇĞİÖŞÜ]{1,8}[-\s]?\d{1,8}")
_VISION_DATE_RE: Final[re.Pattern[str]] = re.compile(r"\d{1,2}[./]\d{1,2}[./]\d{2,4}")
_VISION_KP_RE: Final[re.Pattern[str]] = re.compile(r"\d{1,4}\+\d{2,3}(?:[.,]\d+)?")
_VISION_WORD_NUMBER_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:[A-Za-z]{2,14}\s+\d{1,6}[A-Za-z]*(?:[-/.\s]+[A-Za-z\d]+)*|\d{1,4}\.?\s*(?:bolum|kesim))[. *]*",
    re.IGNORECASE,
)
_VISION_PAREN_UNIT_RE: Final[re.Pattern[str]] = re.compile(r"^\([^)]{0,10}\)$")
_VISION_PUNCTUATION_ONLY_RE: Final[re.Pattern[str]] = re.compile(r"^[:.\-—_,\s]+$")


def _looks_like_value(text: str) -> bool:
    """True when a Vision block is likely a field value, not a label/description."""

    stripped = text.strip()
    if not stripped or len(stripped) > 30:
        return False
    if _VISION_PUNCTUATION_ONLY_RE.match(stripped):
        return False
    if _VISION_UNIT_ONLY_RE.match(stripped):
        return False
    upper = stripped.upper()
    if upper in {"PASS", "FAIL", "KABUL", "RED"}:
        return True
    if _VISION_DATE_RE.fullmatch(stripped) or _VISION_KP_RE.fullmatch(stripped):
        return True
    if _VISION_CODE_RE.fullmatch(stripped):
        return True
    if _VISION_WORD_NUMBER_RE.fullmatch(_fold(stripped)):
        return True
    if _VISION_NUMERIC_RE.fullmatch(stripped) and any(char.isdigit() for char in stripped):
        return True
    digits = sum(char.isdigit() for char in stripped)
    return bool(digits) and digits / len(stripped) >= 0.5


def _looks_like_label(text: str) -> bool:
    """True when a Vision block is likely a field label."""

    stripped = text.strip()
    if not stripped or len(stripped) > 70:
        return False
    if _VISION_UNIT_ONLY_RE.match(stripped):
        return False
    if _VISION_NUMERIC_RE.fullmatch(stripped):
        return False
    return any(char.isalpha() for char in stripped)


def _vision_row_bands(
    items: Sequence[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    """Group Vision blocks into form rows using tight vertical tolerance."""

    bands: list[list[dict[str, Any]]] = []
    for item in sorted(items, key=lambda entry: -entry["y"]):
        if bands:
            anchor = bands[-1][0]["y"]
            if abs(item["y"] - anchor) <= _VISION_ROW_TOLERANCE:
                bands[-1].append(item)
                continue
        bands.append([item])
    for band in bands:
        band.sort(key=lambda entry: entry["x"])
    return bands


def _vision_pair_row(
    band: Sequence[dict[str, Any]],
) -> list[tuple[dict[str, Any], dict[str, Any] | None]]:
    """Pair labels with their values inside one form row.

    Form satirinda birden fazla etiket/deger cifti olabilir (sol ve sag
    kolon). Her etikete, sagindaki en yakin ve henuz kullanilmamis deger
    atanir. Bir etiketin sagindaki *kisa* baska bir etiketin otesine
    gecen deger aday degildir; aksi halde "Test Bolum No" satirindaki
    "Tarih" degerini calar.
    """

    labels = [
        entry
        for entry in band
        if _looks_like_label(entry["text"]) and not _looks_like_value(entry["text"])
    ]
    values = [entry for entry in band if _looks_like_value(entry["text"])]
    used: set[int] = set()
    pairs: list[tuple[dict[str, Any], dict[str, Any] | None]] = []

    for label in labels:
        label_end = label["x"] + label["w"]
        blockers = [
            other["x"]
            for other in labels
            if other is not label
            and other["x"] > label["x"]
            and len(other["text"]) <= _VISION_SHORT_LABEL_MAX
            and not _VISION_PAREN_UNIT_RE.match(other["text"].strip())
        ]
        limit = min(blockers) if blockers else float("inf")

        best: tuple[float, dict[str, Any]] | None = None
        for value in values:
            if id(value) in used:
                continue
            if value["x"] < label_end - 0.02:
                continue
            if value["x"] >= limit:
                continue
            gap = value["x"] - label_end
            if gap > _VISION_MAX_GAP:
                continue
            if best is None or gap < best[0]:
                best = (gap, value)
        if best is None:
            pairs.append((label, None))
        else:
            used.add(id(best[1]))
            pairs.append((label, best[1]))
    return pairs


def _vision_blocks_to_text(blocks: Sequence[tuple[str, float, Sequence[float]]]) -> str:
    """Build label/value lines from Vision blocks using their bounding boxes.

    Kurumsal formlarda etiket ve deger ayri hucrelerdedir; Vision bunlari
    ayri metin bloklari olarak dondurur. Bloklar once form satirlarina
    (dar dikey tolerans) ayrilir, sonra her satirda etiketler sag
    taraflarindaki degerlerle ``etiket : deger`` biciminde eslesir.
    Boylece mevcut satir tabanli alan ayristirici degismeden calisir.
    """

    items = [
        {
            "text": str(text).strip(),
            "confidence": float(confidence),
            "x": float(box[0]),
            "y": float(box[1]),
            "w": float(box[2]),
            "h": float(box[3]),
        }
        for text, confidence, box in blocks
        if str(text).strip() and len(box) >= 4
    ]
    if not items:
        return ""

    lines: list[str] = []
    for band in _vision_row_bands(items):
        emitted: set[int] = set()
        for label, value in _vision_pair_row(band):
            emitted.add(id(label))
            if value is not None:
                emitted.add(id(value))
                lines.append(f"{label['text']} : {value['text']}")
            else:
                lines.append(label["text"])
        for item in band:
            if id(item) in emitted:
                continue
            lines.append(item["text"])

    return "\n".join(lines)


_VISION_LANGUAGE_ALIASES: Final[dict[str, str]] = {
    "tur": "tr-TR",
    "tr": "tr-TR",
    "eng": "en-US",
    "en": "en-US",
}


def _resolve_vision_languages(language: str | None) -> list[str]:
    raw = (language or "").strip() or os.environ.get("HYDRO_OCR_LANG", "").strip()
    if not raw:
        return list(_VISION_LANGUAGES)
    resolved: list[str] = []
    for part in re.split(r"[+,;\s]+", raw):
        token = part.strip()
        if not token:
            continue
        mapped = _VISION_LANGUAGE_ALIASES.get(token.casefold(), token)
        if mapped not in resolved:
            resolved.append(mapped)
    return resolved or list(_VISION_LANGUAGES)


def _run_vision(image: Any, *, language: str | None = None) -> tuple[str, float | None, str]:
    """OCR one page with the macOS Vision framework (``ocrmac``)."""

    try:
        ocrmac = importlib.import_module("ocrmac.ocrmac")
    except ImportError as exc:  # pragma: no cover - onceden kontrol edilir
        raise ReportOcrError("OCR icin ocrmac gerekli.", ERROR_OCR_UNAVAILABLE) from exc

    from PIL import Image  # noqa: PLC0415 - opsiyonel bagimlilik, tembel import

    if not isinstance(image, Image.Image):
        image = Image.open(image)

    warning = ""
    preferred_languages = _resolve_vision_languages(language)
    try:
        blocks = ocrmac.OCR(
            image,
            recognition_level="accurate",
            language_preference=preferred_languages,
        ).recognize()
    except ValueError:
        # Dil listesi bu macOS surumunde desteklenmiyorsa varsayilanla dene.
        try:
            blocks = ocrmac.OCR(image, recognition_level="accurate").recognize()
        except Exception as exc:
            raise ReportOcrError(
                "macOS Vision OCR calistirilamadi.",
                ERROR_OCR_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        warning = "macOS Vision Turkce dil tercihini kabul etmedi; varsayilan dil kullanildi."
    except Exception as exc:
        raise ReportOcrError(
            "macOS Vision OCR calistirilamadi.",
            ERROR_OCR_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    text = _vision_blocks_to_text(blocks)
    confidences = [float(confidence) for _, confidence, _ in blocks]
    mean_confidence = (sum(confidences) / len(confidences)) if confidences else None
    return text, mean_confidence, warning


def _windows_ocr_words_to_vision_blocks(
    lines_words: Sequence[Sequence[tuple[str, float, float, float, float]]],
    img_w: int,
    img_h: int,
) -> list[tuple[str, float, tuple[float, float, float, float]]]:
    """Convert Windows.Media.Ocr line/word boxes (px) into normalized Vision blocks."""

    if img_w <= 0 or img_h <= 0:
        return []

    blocks: list[tuple[str, float, tuple[float, float, float, float]]] = []
    min_gap_px = 0.022 * float(img_w)

    for raw_line in lines_words:
        words = sorted(
            (
                (str(text).strip(), float(x), float(y), max(0.0, float(w)), max(0.0, float(h)))
                for text, x, y, w, h in raw_line
                if str(text).strip()
            ),
            key=lambda item: item[1],
        )
        if not words:
            continue

        cluster: list[tuple[str, float, float, float, float]] = []

        def _flush_cluster() -> None:
            if not cluster:
                return
            joined = " ".join(part[0] for part in cluster).strip()
            if not joined or joined == ":":
                cluster.clear()
                return
            x0 = min(part[1] for part in cluster)
            y0 = min(part[2] for part in cluster)
            x1 = max(part[1] + part[3] for part in cluster)
            y1 = max(part[2] + part[4] for part in cluster)
            norm_x = max(0.0, min(1.0, x0 / float(img_w)))
            norm_w = max(0.0, min(1.0 - norm_x, (x1 - x0) / float(img_w)))
            norm_y = max(0.0, min(1.0, 1.0 - (y1 / float(img_h))))
            norm_h = max(0.0, min(1.0, (y1 - y0) / float(img_h)))
            blocks.append((joined, 0.90, (norm_x, norm_y, norm_w, norm_h)))
            cluster.clear()

        for word in words:
            wtext, wx, _wy, _ww, wh = word
            if wtext == ":":
                _flush_cluster()
                continue
            if not cluster:
                cluster.append(word)
                continue
            prev_text, px, _py, pw, ph = cluster[-1]
            prev_right = px + pw
            avg_h = max(ph, wh, 1.0)
            threshold = max(1.8 * avg_h, min_gap_px)
            gap = wx - prev_right
            if gap > threshold or prev_text.endswith(":"):
                _flush_cluster()
            cluster.append(word)

        _flush_cluster()

    return blocks


def _run_windows_ocr(image: Any, *, language: str | None = None) -> tuple[str, float | None, str]:
    """OCR one page in-process with Windows 10/11 ``Windows.Media.Ocr``."""

    try:
        ocr_mod = importlib.import_module("winrt.windows.media.ocr")
        glob_mod = importlib.import_module("winrt.windows.globalization")
        img_mod = importlib.import_module("winrt.windows.graphics.imaging")
        streams_mod = importlib.import_module("winrt.windows.storage.streams")
    except ImportError as exc:
        raise ReportOcrError(
            "Windows yerlesik OCR modulu yuklenemedi.",
            ERROR_OCR_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    from PIL import Image  # noqa: PLC0415

    pil_img = image if isinstance(image, Image.Image) else Image.open(image)
    rgb = pil_img.convert("RGB")
    max_dim = _WIN_OCR_MAX_DIMENSION_FALLBACK
    raw_limit = getattr(ocr_mod.OcrEngine, "max_image_dimension", None)
    if isinstance(raw_limit, int) and raw_limit > 0:
        max_dim = raw_limit
    if max(rgb.width, rgb.height) > max_dim:
        scale = float(max_dim) / float(max(rgb.width, rgb.height))
        rgb = rgb.resize(
            (max(1, int(round(rgb.width * scale))), max(1, int(round(rgb.height * scale)))),
            Image.Resampling.LANCZOS,
        )

    png_buf = io.BytesIO()
    rgb.save(png_buf, format="PNG")
    png_bytes = png_buf.getvalue()
    if not png_bytes:
        raise ReportOcrError("Bos goruntu OCR islenemedi.", ERROR_CORRUPT_IMAGE)

    async def _recognize() -> tuple[str, list[list[tuple[str, float, float, float, float]]], str]:
        stream = streams_mod.InMemoryRandomAccessStream()
        bitmap = None
        try:
            ibuf = streams_mod.Buffer(len(png_bytes))
            ibuf.length = len(png_bytes)
            with memoryview(ibuf) as mv:
                mv[:] = png_bytes
            await stream.write_async(ibuf)
            await stream.flush_async()
            stream.seek(0)

            decoder = await img_mod.BitmapDecoder.create_async(stream)
            bitmap = await decoder.get_software_bitmap_async()
            engine, active_lang, _ = _select_windows_ocr_engine(
                ocr_mod,
                glob_mod.Language,
                language=language,
            )
            if engine is None:
                raise ReportOcrError(
                    "Windows yerlesik OCR dil paketi bulunamadi (tr-TR / en-US).",
                    ERROR_OCR_UNAVAILABLE,
                )
            ocr_result = await engine.recognize_async(bitmap)
            raw_text = str(getattr(ocr_result, "text", "") or "")
            extracted_lines: list[list[tuple[str, float, float, float, float]]] = []
            for line in getattr(ocr_result, "lines", ()) or ():
                row_words: list[tuple[str, float, float, float, float]] = []
                for word in getattr(line, "words", ()) or ():
                    wtext = str(getattr(word, "text", "") or "").strip()
                    rect = getattr(word, "bounding_rect", None)
                    if not wtext or rect is None:
                        continue
                    row_words.append(
                        (
                            wtext,
                            float(rect.x),
                            float(rect.y),
                            float(rect.width),
                            float(rect.height),
                        )
                    )
                if row_words:
                    extracted_lines.append(row_words)
            return raw_text, extracted_lines, active_lang
        finally:
            if bitmap is not None and hasattr(bitmap, "close"):
                bitmap.close()
            if hasattr(stream, "close"):
                stream.close()

    try:
        raw_text, lines_words, active_lang = _run_winrt_coro(_recognize, timeout=45.0)
    except ReportOcrError:
        raise
    except (Exception, SystemExit) as exc:
        raise ReportOcrError(
            "Windows yerlesik OCR calistirilamadi.",
            ERROR_OCR_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    blocks = _windows_ocr_words_to_vision_blocks(lines_words, rgb.width, rgb.height)
    structured = _vision_blocks_to_text(blocks) if blocks else ""
    text = structured.strip() and structured or raw_text
    warning = ""
    if active_lang and not active_lang.casefold().startswith("tr"):
        warning = f"Windows OCR 'tr-TR' dil paketi bulunamadi; OCR '{active_lang}' ile yapildi."
    mean_confidence = 0.90 if text.strip() else None
    return text, mean_confidence, warning


# ---------------------------------------------------------------------------
# Metin normalizasyonu ve alan cikarimi
# ---------------------------------------------------------------------------

_FOLD_TABLE = str.maketrans(
    {
        "İ": "I",
        "ı": "i",
        "Ş": "S",
        "ş": "s",
        "Ğ": "G",
        "ğ": "g",
        "Ü": "U",
        "ü": "u",
        "Ö": "O",
        "ö": "o",
        "Ç": "C",
        "ç": "c",
        "Â": "A",
        "â": "a",
        "\u00a0": " ",
        "\u2007": " ",
        "\u202f": " ",
        "\u2212": "-",
        "\u2013": "-",
        "\u2014": "-",
        "º": "°",
        "“": '"',
        "”": '"',
        "″": '"',
        "‘": "'",
        "’": "'",
    }
)

#: Kanonik alan -> (kanonik birim, boyut turu)
_KEY_UNITS: Final[dict[str, tuple[str, str]]] = {
    "pipe_od_mm": ("mm", "length"),
    "pipe_id_mm": ("mm", "length"),
    "wall_mm": ("mm", "length"),
    "length_m": ("m", "length"),
    "section_volume_m3": (UNIT_M3, "volume"),
    "max_operating_pressure_bar": (UNIT_BAR, "pressure"),
    "smys_mpa": ("MPa", "pressure"),
    "test_pressure_bar": (UNIT_BAR, "pressure"),
    "air_test.vp": (UNIT_M3, "volume"),
    "air_test.vpa": (UNIT_M3, "volume"),
    "air_test.vt": (UNIT_M3, "volume"),
    "air_test.k": ("-", "ratio"),
    "air_test.ratio": ("-", "ratio"),
    "air_test.a": (UNIT_MICRO_PER_BAR, "compressibility"),
    "pressure_test.t_initial": (UNIT_CELSIUS, "temperature"),
    "pressure_test.t_final": (UNIT_CELSIUS, "temperature"),
    "pressure_test.delta_t": (UNIT_CELSIUS, "temperature_delta"),
    "pressure_test.p_delta": (UNIT_BAR, "pressure"),
    "pressure_test.pa": (UNIT_BAR, "pressure"),
    "pressure_test.pl": (UNIT_BAR, "pressure"),
    "pressure_test.a": (UNIT_MICRO_PER_BAR, "compressibility"),
    "pressure_test.b": (UNIT_MICRO_PER_C, "expansion"),
}

_STRING_FIELDS: Final[frozenset[str]] = frozenset(
    {"report_no", "operator", "section_id", "start_kp", "end_kp", "notes"}
)

_PLAUSIBLE_RANGES: Final[dict[str, tuple[float, float]]] = {
    "pipe_od_mm": (10.0, 3000.0),
    "pipe_id_mm": (5.0, 3000.0),
    "wall_mm": (0.5, 100.0),
    "length_m": (0.5, 5_000_000.0),
    "section_volume_m3": (0.0, 1_000_000.0),
    "max_operating_pressure_bar": (0.0, 1000.0),
    "smys_mpa": (50.0, 1000.0),
    "test_pressure_bar": (0.0, 1000.0),
    "air_test.vp": (0.0, 100_000.0),
    "air_test.vpa": (0.0, 100_000.0),
    "air_test.vt": (0.0, 1_000_000.0),
    "air_test.k": (0.8, 1.2),
    "air_test.ratio": (0.0, 1.0),
    "air_test.a": (1.0, 200.0),
    "pressure_test.t_initial": (-60.0, 120.0),
    "pressure_test.t_final": (-60.0, 120.0),
    "pressure_test.delta_t": (-60.0, 60.0),
    "pressure_test.p_delta": (-100.0, 100.0),
    "pressure_test.pa": (0.0, 100.0),
    "pressure_test.pl": (0.0, 100.0),
    "pressure_test.a": (1.0, 200.0),
    "pressure_test.b": (-500.0, 500.0),
}

_NUMBER_RE = re.compile(
    r"[-+]?\d(?:[ \u00a0'\u2019]?\d)*(?:[.,]\d+(?:[ \u00a0'\u2019]?\d)*)*(?:[eE][-+]?\d+)?"
)
_EXPONENT_RE = re.compile(r"(?:x|×|\*)?\s*10\s*\^?\s*[-−]\s*(\d+)")
_MICRO_HINT_RE = re.compile(r"micro|µ|μ|\bu\s*/\s*(?:bar|c)\b")

_UNIT_PATTERNS: Final[tuple[tuple[re.Pattern[str], str], ...]] = tuple(
    (re.compile(pattern), unit)
    for pattern, unit in (
        (r"^m\s*[³3](?![0-9])|^m\s*\^\s*3", UNIT_M3),
        (r"^ml\b|^mililitre\b", "mL"),
        (r"^l\b|^lt\b|^litre\b|^liter\b", "L"),
        (r"^bars?\b|^barg\b|^bara\b", UNIT_BAR),
        (r"^psi\b", "psi"),
        (r"^kpa\b", "kPa"),
        (r"^mpa\b", "MPa"),
        (r"^°\s*c\b|^degc\b|^celsius\b", UNIT_CELSIUS),
        (r"^°\s*f\b|^degf\b|^fahrenheit\b", "°F"),
        (r"^k\b|^kelvin\b", "K"),
        (r"^mm\b|^milimetre\b|^millimeter\b", "mm"),
        (r"^cm\b", "cm"),
        (r"^km\b", "km"),
        (r"^inç\b|^inch\b|^in\b|[″\"]", "in"),
        (r"^ft\b|^feet\b", "ft"),
        (r"^m\b|^metre\b|^meter\b", "m"),
        (r"^10\s*\^\s*-\s*6\s*/\s*bar|^micro\s*/\s*bar|^µ\s*/\s*bar", UNIT_MICRO_PER_BAR),
        (r"^10\s*\^\s*-\s*6\s*/\s*°?c|^micro\s*/\s*°?c|^µ\s*/\s*°?c", UNIT_MICRO_PER_C),
        (r"^1\s*/\s*bar|^bar\s*\^\s*-\s*1", "1/bar"),
        (r"^1\s*/\s*°?c|^1\s*/\s*k", "1/°C"),
        (r"^%", "%"),
    )
)

_SECTION_NUMBER_PREFIX = r"(?:\d+(?:\.\d+)*[.)]?\s+)?"
_AIR_SECTION_RE = re.compile(
    rf"^\s*{_SECTION_NUMBER_PREFIX}(?:"
    r"hava(?:\s+icerik)?\s+test(?:i)?"
    r"|air\s+content(?:\s+test)?"
    r"|air\s+test"
    r")\b",
    re.IGNORECASE,
)
_PRESSURE_SECTION_RE = re.compile(
    rf"^\s*{_SECTION_NUMBER_PREFIX}(?:"
    r"(?:hidrostatik\s+)?basinc\s+"
    r"(?:(?:degisim|degisimi|dusus|dusumu|artis|artisi|deney|deneyi|test|testi)\s*)+"
    r"|mukavemet\s+test(?:i)?"
    r"|pressure\s+(?:(?:variation|change|drop|rise|test)\s*)+"
    r"|strength\s+test"
    r")\b",
    re.IGNORECASE,
)

_FAIL_WORDS: Final[tuple[str, ...]] = (
    "kabul edilmemistir",
    "kabul edilmemis",
    "kabul edilmedi",
    "uygun bulunmamistir",
    "uygun bulunmamis",
    "basarisizdir",
    "basarisiz",
    "fail",
    "uygun degil",
    "reddedilmistir",
    "reddedildi",
)
_PASS_WORDS: Final[tuple[str, ...]] = (
    "basarili",
    "pass",
    "kabul",
    "uygun",
    "gecti",
)

_MONTHS: Final[dict[str, int]] = {
    "ocak": 1,
    "january": 1,
    "subat": 2,
    "february": 2,
    "mart": 3,
    "march": 3,
    "nisan": 4,
    "april": 4,
    "mayis": 5,
    "may": 5,
    "haziran": 6,
    "june": 6,
    "temmuz": 7,
    "july": 7,
    "agustos": 8,
    "august": 8,
    "eylul": 9,
    "september": 9,
    "ekim": 10,
    "october": 10,
    "kasim": 11,
    "november": 11,
    "aralik": 12,
    "december": 12,
}


def _fold(text: str) -> str:
    return text.translate(_FOLD_TABLE)


def _alias_pattern(alias: str) -> str:
    escaped = re.escape(_fold(alias))
    return escaped.replace(r"\ ", r"\s+")


def _build_alias_patterns(
    extra: dict[str, Sequence[str]] | None = None,
) -> tuple[tuple[re.Pattern[str], str], ...]:
    entries: list[tuple[int, re.Pattern[str], str]] = []
    seen: set[tuple[str, str]] = set()
    merged: dict[str, Sequence[str]] = {
        key: list(aliases) for key, aliases in FIELD_ALIASES.items()
    }
    for key, aliases in (extra or {}).items():
        merged.setdefault(key, [])
        merged[key] = [*merged[key], *aliases]

    for key, aliases in merged.items():
        for alias in aliases:
            folded = _fold(alias)
            if (key, folded.casefold()) in seen:
                continue
            seen.add((key, folded.casefold()))
            pattern = re.compile(
                rf"^\s*{_alias_pattern(alias)}\s*\.?\s*(?::|=|\s)\s*(?P<rest>.*)$",
                re.IGNORECASE,
            )
            entries.append((len(folded), pattern, key))
    entries.sort(key=lambda item: item[0], reverse=True)
    return tuple((pattern, key) for _, pattern, key in entries)


_ALIAS_PATTERNS: Final[tuple[tuple[re.Pattern[str], str], ...]] = _build_alias_patterns()

#: Uzun etiketler icin bulanik eslesme esigi (OCR yazim hatalari).
_FUZZY_MIN_RATIO: Final[float] = 0.88
_FUZZY_ALIASES: Final[tuple[tuple[str, str], ...]] = tuple(
    (folded, key)
    for key, aliases in FIELD_ALIASES.items()
    for alias in aliases
    for folded in (_fold(alias).casefold(),)
    if len(folded) >= 10
)


def _build_fuzzy_aliases(
    extra: dict[str, Sequence[str]] | None = None,
) -> tuple[tuple[str, str], ...]:
    if not extra:
        return _FUZZY_ALIASES
    merged = [(folded, key) for folded, key in _FUZZY_ALIASES]
    for key, aliases in extra.items():
        for alias in aliases:
            folded = _fold(alias).casefold()
            if len(folded) >= 10:
                merged.append((folded, key))
    return tuple(merged)


def parse_number(raw: str) -> float:
    """Parse a Turkish/English formatted number from ``raw``.

    Kurallar:

    - Hem ``.`` hem ``,`` varsa en sagdaki ondalik ayiricidir.
    - Tek ``,`` Turkce gelenegi geregi ondalik kabul edilir (``45,515``).
    - Tek ``.`` ve tam 3 hane ondalik + 1-3 haneli tam kismi binlik kabul
      edilir (``1.000`` -> 1000); ``0.884`` gibi basi sifirli degerler
      ondalik kalir.
    - Bosluk ve kesme isareti binlik ayirici sayilir.
    """

    value, _ambiguous = _parse_number_detail(raw)
    return value


def _parse_number_detail(raw: str) -> tuple[float, bool]:
    match = _NUMBER_RE.search(str(raw))
    if match is None:
        raise ValueError(f"Sayi bulunamadi: {raw!r}")

    token = (
        match.group(0).replace("\u00a0", "").replace(" ", "").replace("'", "").replace("\u2019", "")
    )
    token = token.strip().rstrip(".,")
    negative = token.startswith("-")
    if token[:1] in "+-":
        token = token[1:]
    if not token:
        raise ValueError(f"Sayi bulunamadi: {raw!r}")

    exponent = 0
    exponent_match = re.match(r"^(.*?)[eE]([-+]?\d+)$", token)
    if exponent_match:
        token = exponent_match.group(1)
        exponent = int(exponent_match.group(2))

    ambiguous = False
    has_comma = "," in token
    has_dot = "." in token

    if has_comma and has_dot:
        if token.rfind(",") > token.rfind("."):
            token = token.replace(".", "").replace(",", ".")
        else:
            token = token.replace(",", "")
    elif has_comma:
        parts = token.split(",")
        if len(parts) > 2:
            token = "".join(parts)
            ambiguous = True
        else:
            integer_part, fraction = parts
            if not fraction:
                raise ValueError(f"Gecersiz sayi: {raw!r}")
            # Tek virgul Turkce ondalik ayiricidir; "45,515" => 45.515.
            token = f"{integer_part or '0'}.{fraction}"
    elif has_dot:
        parts = token.split(".")
        if len(parts) > 2:
            token = "".join(parts)
            ambiguous = True
        else:
            integer_part, fraction = parts
            if fraction and len(fraction) == 3 and 1 <= len(integer_part) <= 3:
                if integer_part == "0":
                    token = f"0.{fraction}"
                else:
                    token = integer_part + fraction
                    ambiguous = True
            else:
                token = f"{integer_part or '0'}.{fraction or '0'}"

    try:
        value = float(token) * (10.0**exponent)
    except ValueError as exc:
        raise ValueError(f"Gecersiz sayi: {raw!r}") from exc
    return (-value if negative else value), ambiguous


def parse_date(raw: str) -> str:
    """Parse common Turkish/English date formats to ISO ``YYYY-MM-DD``."""

    text = _fold(str(raw)).strip()
    iso_match = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", text)
    if iso_match:
        return _make_iso_date(
            int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3))
        )

    numeric_match = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b", text)
    if numeric_match:
        day = int(numeric_match.group(1))
        month = int(numeric_match.group(2))
        year = int(numeric_match.group(3))
        if year < 100:
            year += 2000 if year < 70 else 1900
        return _make_iso_date(year, month, day)

    named_match = re.search(r"\b(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\b", text)
    if named_match:
        month_from_name = _MONTHS.get(named_match.group(2).casefold())
        if month_from_name is not None:
            return _make_iso_date(
                int(named_match.group(3)),
                month_from_name,
                int(named_match.group(1)),
            )

    raise ValueError(f"Tarih taninamadi: {raw!r}")


def _make_iso_date(year: int, month: int, day: int) -> str:
    try:
        return _date(year, month, day).isoformat()
    except ValueError as exc:
        raise ValueError(f"Gecersiz tarih: {year}-{month}-{day}") from exc


def normalize_result(raw: str) -> str | None:
    """Return ``"PASS"``/``"FAIL"`` for a free-text result, else ``None``."""

    folded = _fold(str(raw)).casefold()
    if any(word in folded for word in _FAIL_WORDS) or re.search(r"\bred\b", folded):
        return "FAIL"
    if any(word in folded for word in _PASS_WORDS):
        return "PASS"
    return None


def _detect_unit(text: str) -> str:
    folded = _fold(text).casefold().lstrip()
    for pattern, unit in _UNIT_PATTERNS:
        if pattern.search(folded):
            return unit
    return ""


def _scale_micro(value: float, raw: str) -> float:
    exponent_match = _EXPONENT_RE.search(_fold(raw))
    if exponent_match:
        exponent = int(exponent_match.group(1))
        return value * (10.0 ** (6 - exponent))
    if _MICRO_HINT_RE.search(_fold(raw)):
        return value
    if value and abs(value) < 1e-3:
        return value * 1e6
    return value


def _section_heading(folded_line: str) -> str:
    """Return ``"air"``/``"pressure"`` when the line is a section heading.

    Baslik satirlarinda deger ayirici iki nokta (``:``) bulunmamalidir;
    boylece "Basinc Degisimi: 0.4 bar" gibi alan satirlari baslik sanilmaz.
    """

    stripped = folded_line.strip()
    if len(stripped) > 80:
        return ""
    if ":" in stripped.rstrip(":"):
        return ""
    if _AIR_SECTION_RE.match(stripped):
        return "air"
    if _PRESSURE_SECTION_RE.match(stripped):
        return "pressure"
    return ""


@dataclass
class _Candidate:
    key: str
    field: Any
    order: int
    section: str


def parse_report(
    text_pages: Sequence[PageText] | str,
    *,
    extra_aliases: dict[str, Sequence[str]] | None = None,
) -> HydrotestReport:
    """Parse a hydrostatic test report from text pages.

    ``text_pages`` yerine dogrudan bir metin de verilebilir; bu gelistirme
    ve test kolayligi icindir. ``extra_aliases`` ile harici bir esleme
    profili (ornegin web uygulamasindaki ``pre_extract`` profili) ek
    etiket adlari tanimlayabilir.
    """

    patterns = _build_alias_patterns(extra_aliases) if extra_aliases else _ALIAS_PATTERNS
    fuzzy_aliases = _build_fuzzy_aliases(extra_aliases)

    pages = (
        [PageText(page_number=1, text=text_pages, source=TEXT_SOURCE_LAYER)]
        if isinstance(text_pages, str)
        else list(text_pages)
    )
    if not any(page.text.strip() for page in pages):
        raise ReportOcrError("Rapor metni bos; alan cikarimi yapilamadi.", ERROR_EMPTY_TEXT)

    warnings: list[str] = []
    total_chars = _text_char_count(pages)
    if total_chars > MAX_TEXT_CHARS:
        warnings.append(
            f"Rapor metni {MAX_TEXT_CHARS} karakterle sinirlandi (toplam {total_chars})."
        )

    candidates: list[_Candidate] = []
    order = 0
    a_seen = {"air": 0, "pressure": 0}
    remaining_chars = MAX_TEXT_CHARS

    for page in pages:
        if remaining_chars <= 0:
            break
        section = ""
        pa_seen = 0
        start_kp_seen = False
        page_text = page.text[:remaining_chars]
        remaining_chars -= len(page_text)
        for raw_line in page_text.splitlines():
            folded = _fold(raw_line)
            stripped = folded.strip()
            if not stripped:
                continue

            if section_kind := _section_heading(stripped):
                section = section_kind
                continue

            matched = _match_field_line(folded, patterns, fuzzy_aliases)
            if matched is None:
                continue
            key, rest_start = matched
            rest = raw_line[rest_start:].strip()
            if not rest:
                continue
            if key not in _STRING_FIELDS:
                rest = _trailing_value(rest)
                if not rest:
                    continue

            # Hava icerik formunda "Olculen Basinc Degisimi" farkli bir
            # buyukluktur (testin basinc adimi); basinc testi alanlarina
            # yazilmamalidir.
            if section == "air" and key.startswith("pressure_test."):
                continue

            if key in {"air_test.a", "pressure_test.a"}:
                effective_section = section
                if not effective_section:
                    effective_section = "air" if a_seen["air"] == 0 else "pressure"
                if effective_section == "pressure":
                    key = "pressure_test.a"
                else:
                    key = "air_test.a"
                a_seen[effective_section] += 1

            if key == "pressure_test.pa":
                # Resmi basinc testi formunda once "Olculen Basinc
                # Degisimi" (PA), ardindan sicaklik kaynakli "dP" satiri
                # gelir. Ikinci "Pa/PA" satiri dP olarak yorumlanir.
                if pa_seen:
                    key = "pressure_test.p_delta"
                pa_seen += 1

            if key == "start_kp" and start_kp_seen:
                key = "end_kp"

            order += 1
            extracted = _build_field(key, rest, page, warnings, source=page.source)
            if extracted is None:
                continue
            if key == "start_kp":
                start_kp_seen = True
            candidates.append(_Candidate(key=key, field=extracted, order=order, section=section))

    if page_warnings := [page.warning for page in pages if page.warning]:
        for warning in page_warnings:
            if warning not in warnings:
                warnings.append(warning)

    if not candidates:
        warnings.append("Raporda taninabilir alan bulunamadi.")

    grouped: dict[str, list[_Candidate]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.key, []).append(candidate)

    values: dict[str, Any] = {}
    for key, group in grouped.items():
        values[key] = _resolve_candidates(key, group, warnings)

    if "result" not in values:
        verdict = _find_verdict(pages)
        if verdict is not None:
            values["result"] = verdict
            warnings.append(
                "Rapor sonucu serbest metinden cikarildi (kabul/red cumlesi); insan onayi gerekli."
            )

    if "report_no" not in values:
        form_no = _find_form_number(pages)
        if form_no is not None:
            values["report_no"] = form_no

    if "section_id" not in values:
        section_id = _find_section_id(pages)
        if section_id is not None:
            values["section_id"] = section_id

    report = HydrotestReport(
        report_no=values.get("report_no"),
        date=values.get("date"),
        operator=values.get("operator"),
        section_id=values.get("section_id"),
        start_kp=values.get("start_kp"),
        end_kp=values.get("end_kp"),
        pipe_od_mm=values.get("pipe_od_mm"),
        pipe_id_mm=values.get("pipe_id_mm"),
        wall_mm=values.get("wall_mm"),
        length_m=values.get("length_m"),
        section_volume_m3=values.get("section_volume_m3"),
        max_operating_pressure_bar=values.get("max_operating_pressure_bar"),
        smys_mpa=values.get("smys_mpa"),
        test_pressure_bar=values.get("test_pressure_bar"),
        air_test=AirTestFields(
            vp=values.get("air_test.vp"),
            vpa=values.get("air_test.vpa"),
            vt=values.get("air_test.vt"),
            k=values.get("air_test.k"),
            ratio=values.get("air_test.ratio"),
            a=values.get("air_test.a"),
        ),
        pressure_test=PressureTestFields(
            t_initial=values.get("pressure_test.t_initial"),
            t_final=values.get("pressure_test.t_final"),
            delta_t=values.get("pressure_test.delta_t"),
            p_delta=values.get("pressure_test.p_delta"),
            pa=values.get("pressure_test.pa"),
            pl=values.get("pressure_test.pl"),
            a=values.get("pressure_test.a"),
            b=values.get("pressure_test.b"),
        ),
        result=values.get("result"),
        notes=values.get("notes"),
        warnings=tuple(dict.fromkeys(warnings)),
    )
    return report


_VERDICT_PASS_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:test\s+)?kabul\s+(?:edilmistir|edildi)\b", re.IGNORECASE
)
_VERDICT_FAIL_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:test\s+)?(?:kabul\s+edilmemistir|kabul\s+edilmedi|reddedilmistir|reddedildi|basarisiz)\b",
    re.IGNORECASE,
)
_FORM_NO_RE: Final[re.Pattern[str]] = re.compile(
    r"\bBOT[-\s]?FRM[-\s]?[A-Z]{2,4}[-\s]?\d{3}[-\s]?\d{3}\b", re.IGNORECASE
)


def _find_verdict(pages: Sequence[PageText]) -> ExtractedField | None:
    """Find a PASS/FAIL verdict written as a sentence instead of a label."""

    for page in pages:
        for raw_line in page.text.splitlines():
            folded = _fold(raw_line).casefold()
            if _VERDICT_FAIL_RE.search(folded):
                return ExtractedField(
                    value="FAIL",
                    unit="",
                    confidence=0.55,
                    raw_text=_clean_text(raw_line),
                    page=page.page_number,
                )
            if _VERDICT_PASS_RE.search(folded):
                return ExtractedField(
                    value="PASS",
                    unit="",
                    confidence=0.55,
                    raw_text=_clean_text(raw_line),
                    page=page.page_number,
                )
    return None


def _find_form_number(pages: Sequence[PageText]) -> ExtractedField | None:
    """Use the printed form number (``BOT-FRM-...``) as a fallback report no."""

    for page in pages:
        match = _FORM_NO_RE.search(page.text)
        if match is not None:
            return ExtractedField(
                value=_clean_text(match.group(0)).upper(),
                unit="",
                confidence=0.6,
                raw_text=match.group(0),
                page=page.page_number,
            )
    return None


_SECTION_ID_FALLBACK_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?P<prefix>BOLUM|KESIM)\s+(?P<code>\d{1,4}(?:\s*[-/]\s*[A-Za-z\d]{1,6}|[A-Za-z]{1,3})?)\b",
    re.IGNORECASE,
)
_SECTION_ID_FALLBACK_REV_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?P<code>\d{1,4})\.?\s*(?P<prefix>bolum|kesim)\b",
    re.IGNORECASE,
)


def _find_section_id(pages: Sequence[PageText]) -> ExtractedField | None:
    """Find a section designation (e.g. 'BÖLÜM 11-A', '14.bölüm') in report text."""

    for page in pages:
        for line in page.text.splitlines():
            stripped = line.strip()
            if not stripped or len(stripped) > 60:
                continue
            folded = _fold(stripped)
            if match := _SECTION_ID_FALLBACK_RE.search(folded):
                prefix = "KESİM" if match.group("prefix").upper() == "KESIM" else "BÖLÜM"
                code = _clean_text(match.group("code")).upper().replace(" ", "")
                return ExtractedField(
                    value=f"{prefix} {code}",
                    unit="",
                    confidence=0.7,
                    raw_text=stripped,
                    page=page.page_number,
                )
            if match_rev := _SECTION_ID_FALLBACK_REV_RE.search(folded):
                prefix = "KESİM" if match_rev.group("prefix").lower() == "kesim" else "BÖLÜM"
                sec_num = match_rev.group("code")
                return ExtractedField(
                    value=f"{prefix} {sec_num}",
                    unit="",
                    confidence=0.7,
                    raw_text=match_rev.group(0),
                    page=page.page_number,
                )
    return None


_FORMULA_OPERATORS: Final[tuple[str, ...]] = ("x", "X", "×", "*", "+", "/")


def _looks_like_expression(text: str) -> bool:
    """True for formula fragments like ``( 0.884 x (ri/S) +A)``."""

    stripped = text.strip()
    # KP ("25+404"), tarih ve negatif ondalik degerler ifade degildir.
    if _VISION_KP_RE.fullmatch(stripped) or _VISION_DATE_RE.fullmatch(stripped):
        return False
    if "(" not in text or ")" not in text:
        return False
    if not _NUMBER_RE.findall(text):
        return False
    return any(op in text for op in _FORMULA_OPERATORS)


def _trailing_value(rest: str) -> str:
    """Form satirinda aciklama ile deger ayni satirdayken degeri ayikla.

    Ornek: ``Vp = Basinci 1 Bar Degistirmek Icin Gerekli ... (m3) = 0,0625``
    veya ``(PA-ΔP) = -0,035``. Yalnizca son ``=`` isaretinden sonra tek bir
    sayi varsa ve bu parca kisaysa deger kabul edilir; formül satirlari
    (``Vp = (0,884 x ...)``) elenir.
    """

    if "=" in rest:
        head, _, tail = rest.rpartition("=")
        tail = tail.strip()
        if not tail or len(tail) > 32 or len(head.strip()) < 3:
            return ""
        if len(_NUMBER_RE.findall(tail)) != 1:
            return ""
        return tail

    if _looks_like_expression(rest):
        return ""
    return rest


def _match_field_line(
    folded_line: str,
    patterns: Sequence[tuple[re.Pattern[str], str]] | None = None,
    fuzzy_aliases: Sequence[tuple[str, str]] | None = None,
) -> tuple[str, int] | None:
    for pattern, key in patterns or _ALIAS_PATTERNS:
        match = pattern.match(folded_line)
        if match is not None:
            return key, match.start("rest")

    # OCR kaynakli kucuk yazim hatalari (ornegin "Test Bölüm acmi" ->
    # "Test Bölüm Hacmi") icin uzun etiketlerde sinirli bulanik eslesme.
    fuzzy_match = re.match(r"^\s*(?P<label>[^:=]{8,70}?)\s*[:=]\s*(?P<rest>.*)$", folded_line)
    if fuzzy_match is None:
        return None
    label = fuzzy_match.group("label").strip().casefold()
    best: tuple[float, str] | None = None
    for alias, key in fuzzy_aliases or _FUZZY_ALIASES:
        ratio = difflib.SequenceMatcher(None, label, alias).ratio()
        if ratio >= _FUZZY_MIN_RATIO and (best is None or ratio > best[0]):
            best = (ratio, key)
    if best is None:
        return None
    return best[1], fuzzy_match.start("rest")


def _build_field(
    key: str,
    rest: str,
    page: PageText,
    warnings: list[str],
    *,
    source: str,
) -> ExtractedField | None:
    if source == TEXT_SOURCE_SPREADSHEET:
        base_confidence = 0.96
    elif source == TEXT_SOURCE_LAYER:
        base_confidence = 0.9
    else:
        base_confidence = 0.55
    if page.confidence is not None and source == TEXT_SOURCE_OCR:
        base_confidence = min(base_confidence, 0.45 + 0.4 * page.confidence)

    if key in _STRING_FIELDS:
        value = _clean_text(rest)
        if not value:
            return None
        return ExtractedField(
            value=value,
            unit="",
            confidence=_clamp_confidence(base_confidence + 0.02),
            raw_text=rest,
            page=page.page_number,
        )

    if key == "result":
        cleaned = _clean_text(rest)
        normalized = normalize_result(cleaned)
        if normalized is None:
            warnings.append(f"Rapor sonucu taninmadi ({cleaned!r}); insan onayi gerekli.")
            return ExtractedField(
                value=cleaned,
                unit="",
                confidence=_clamp_confidence(base_confidence - 0.4),
                raw_text=rest,
                page=page.page_number,
            )
        return ExtractedField(
            value=normalized,
            unit="",
            confidence=_clamp_confidence(base_confidence + 0.02),
            raw_text=rest,
            page=page.page_number,
        )

    if key == "date":
        try:
            iso = parse_date(rest)
        except ValueError:
            cleaned = _clean_text(rest)
            warnings.append(f"Tarih formati taninmadi ({cleaned!r}); ham deger saklandi.")
            return ExtractedField(
                value=cleaned,
                unit="",
                confidence=_clamp_confidence(base_confidence - 0.5),
                raw_text=rest,
                page=page.page_number,
            )
        return ExtractedField(
            value=iso,
            unit="",
            confidence=_clamp_confidence(base_confidence + 0.03),
            raw_text=rest,
            page=page.page_number,
        )

    return _build_numeric_field(key, rest, page, warnings, base_confidence=base_confidence)


def _build_numeric_field(
    key: str,
    rest: str,
    page: PageText,
    warnings: list[str],
    *,
    base_confidence: float,
) -> ExtractedField | None:
    match = _NUMBER_RE.search(rest)
    if match is None:
        return None
    try:
        value, ambiguous = _parse_number_detail(match.group(0))
    except ValueError:
        return None

    canonical_unit, kind = _KEY_UNITS[key]
    tail = rest[match.end() : match.end() + 24]
    detected_unit = _detect_unit(tail)
    confidence = base_confidence
    unit = canonical_unit

    if kind in {"compressibility", "expansion"}:
        value = _scale_micro(value, rest)
        if kind == "compressibility" and detected_unit in {"1/°C", UNIT_MICRO_PER_C}:
            warnings.append(
                "A katsayisi 1/K olarak etiketlenmis; NGTL 5007 madde 15.2'ye "
                "gore 1/bar kabul edildi (sartname icindeki birim celiskisi)."
            )
        if value >= 1.0 and detected_unit in {"1/bar", "1/K", "1/k"}:
            warnings.append(
                f"{FIELD_LABELS.get(key, key)} formda 1/bar veya 1/K yazilmis ancak "
                f"deger mikro olcekte ({value:g}); 10^-6 biriminde kabul edildi."
            )
        confidence += 0.02
    elif kind == "ratio":
        confidence += 0.02
    elif kind == "temperature_delta":
        if detected_unit:
            try:
                value = convert_temperature_delta(value, detected_unit, UNIT_CELSIUS)
            except ValueError:
                warnings.append(f"dT birimi taninmadi ({detected_unit!r}); °C varsayildi.")
                confidence -= 0.2
        else:
            confidence -= 0.1
    elif detected_unit:
        try:
            value = convert_unit(value, detected_unit, canonical_unit)
            confidence += 0.03
        except ValueError:
            warnings.append(
                f"{FIELD_LABELS.get(key, key)} icin birim uyumsuz "
                f"({detected_unit!r}); {canonical_unit} varsayildi."
            )
            confidence -= 0.25
    else:
        confidence -= 0.1

    if ambiguous:
        confidence -= 0.2
        warnings.append(
            f"{FIELD_LABELS.get(key, key)} icin ondalik/binlik ayirici belirsiz "
            f"({match.group(0)!r}); deger insan onayi gerektirir."
        )

    low, high = _PLAUSIBLE_RANGES.get(key, (float("-inf"), float("inf")))
    if not low <= value <= high:
        confidence -= 0.25
        warnings.append(
            f"{FIELD_LABELS.get(key, key)} fiziksel olarak beklenen araligin "
            f"disinda: {value:g} {unit}."
        )

    return ExtractedField(
        value=value,
        unit=unit,
        confidence=_clamp_confidence(confidence),
        raw_text=rest,
        page=page.page_number,
    )


def _resolve_candidates(key: str, group: list[_Candidate], warnings: list[str]) -> Any:
    if not group:
        return None
    best = max(group, key=lambda candidate: (candidate.field.confidence, -candidate.order))
    distinct = _distinct_values(group, key)
    if len(distinct) > 1:
        alternatives = ", ".join(f"{value:g}" for value in distinct[:4])
        warnings.append(
            f"{FIELD_LABELS.get(key, key)} icin birden fazla farkli deger bulundu "
            f"({alternatives}); en guvenilir aday secildi."
        )
        best.field = replace(best.field, confidence=_clamp_confidence(best.field.confidence * 0.75))
    return best.field


def _distinct_values(group: list[_Candidate], key: str) -> list[float]:
    values: list[float] = []
    if key in _KEY_UNITS:
        for candidate in group:
            numeric = candidate.field.as_float()
            if numeric is None:
                continue
            if not any(
                abs(numeric - existing) <= max(1e-9, abs(existing) * 1e-9) for existing in values
            ):
                values.append(numeric)
        return values

    texts: list[str] = []
    for candidate in group:
        text = str(candidate.field.value or "").strip().casefold()
        if text and text not in texts:
            texts.append(text)
    return [float(index) for index, _ in enumerate(texts)]


def _clean_text(raw: str) -> str:
    text = " ".join(str(raw).replace("\u00a0", " ").split())
    text = text.strip(" ;,:")
    return text[:200]


def _clamp_confidence(value: float) -> float:
    return max(0.05, min(0.99, value))


# ---------------------------------------------------------------------------
# Hesaplanan degerlerle karsilastirma
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ComparisonSpec:
    key: str
    label: str
    unit: str
    calculated_path: tuple[str, ...]
    abs_tolerance: float | None
    rel_tolerance: float | None
    tolerance_text: str
    mismatch_severity: str


_COMPARISONS: Final[tuple[_ComparisonSpec, ...]] = (
    _ComparisonSpec(
        "pipe_od_mm", "Dis cap", "mm", ("pipe_od_mm",), 0.5, None, "±0.5 mm", "warning"
    ),
    _ComparisonSpec("wall_mm", "Et kalinligi", "mm", ("wall_mm",), 0.1, None, "±0.1 mm", "warning"),
    _ComparisonSpec("length_m", "Hat uzunlugu", "m", ("length_m",), 1.0, None, "±1.0 m", "warning"),
    _ComparisonSpec(
        "test_pressure_bar",
        "Test basinci",
        "bar",
        ("test_pressure_bar",),
        0.05,
        None,
        "±0.05 bar",
        "critical",
    ),
    _ComparisonSpec(
        "air_test.vp",
        "Hava testi Vp",
        UNIT_M3,
        ("air_test", "vp_m3"),
        1e-6,
        0.02,
        "%2 veya 1 mL",
        "warning",
    ),
    _ComparisonSpec(
        "air_test.vpa",
        "Hava testi Vpa",
        UNIT_M3,
        ("air_test", "vpa_m3"),
        1e-6,
        0.01,
        "%1 veya 1 mL",
        "critical",
    ),
    _ComparisonSpec(
        "air_test.a",
        "Hava testi A",
        UNIT_MICRO_PER_BAR,
        ("air_test", "a_micro_per_bar"),
        2.0,
        0.02,
        "%2 veya 2 micro/bar",
        "warning",
    ),
    _ComparisonSpec(
        "pressure_test.t_initial",
        "Baslangic sicakligi",
        UNIT_CELSIUS,
        ("pressure_test", "t_initial_c"),
        0.5,
        None,
        "±0.5 °C",
        "critical",
    ),
    _ComparisonSpec(
        "pressure_test.t_final",
        "Bitis sicakligi",
        UNIT_CELSIUS,
        ("pressure_test", "t_final_c"),
        0.5,
        None,
        "±0.5 °C",
        "critical",
    ),
    _ComparisonSpec(
        "pressure_test.delta_t",
        "Sicaklik farki (dT)",
        UNIT_CELSIUS,
        ("pressure_test", "delta_t_c"),
        0.5,
        None,
        "±0.5 °C",
        "critical",
    ),
    _ComparisonSpec(
        "pressure_test.pa",
        "Basinc dususu (Pa)",
        UNIT_BAR,
        ("pressure_test", "pa_bar"),
        0.05,
        None,
        "±0.05 bar",
        "critical",
    ),
    _ComparisonSpec(
        "pressure_test.a",
        "Basinc testi A",
        UNIT_MICRO_PER_BAR,
        ("pressure_test", "a_micro_per_bar"),
        2.0,
        0.02,
        "%2 veya 2 micro/bar",
        "warning",
    ),
    _ComparisonSpec(
        "pressure_test.b",
        "Basinc testi B",
        UNIT_MICRO_PER_C,
        ("pressure_test", "b_micro_per_c"),
        2.0,
        0.02,
        "%2 veya 2 micro/°C",
        "warning",
    ),
)


def compare_with_calculated(
    report: HydrotestReport, calculated: dict[str, Any]
) -> list[Discrepancy]:
    """Compare extracted report fields with application-calculated values.

    ``calculated`` semasi (eksik anahtarlar sorun degildir)::

        {
          "pipe_od_mm": 406.4,
          "wall_mm": 8.74,
          "length_m": 1000.0,
          "test_pressure_bar": 80.0,
          "air_test": {
            "vp_m3": 0.0076825, "vpa_m3": 0.00775, "a_micro_per_bar": 45.3
          },
          "pressure_test": {
            "t_initial_c": 20.0, "t_final_c": 21.0, "delta_t_c": 1.0,
            "pa_bar": 0.4, "a_micro_per_bar": 45.3, "b_micro_per_c": 65.0
          },
          "result": "PASS"
        }
    """

    if not isinstance(calculated, dict):
        raise ReportOcrError(
            "Hesaplanan degerler JSON nesnesi (dict) olmalidir.",
            ERROR_INVALID_CALCULATED,
        )

    discrepancies: list[Discrepancy] = []
    for spec in _COMPARISONS:
        field = report.get_field(spec.key)
        reported = field.value if field is not None else None
        calculated_value = _lookup_calculated(calculated, spec)

        if reported is None:
            discrepancies.append(
                Discrepancy(
                    field=spec.key,
                    label=spec.label,
                    reported=None,
                    calculated=calculated_value,
                    unit=spec.unit,
                    delta=None,
                    tolerance=spec.tolerance_text,
                    status=STATUS_MISSING_IN_REPORT,
                    severity="warning",
                    message=(
                        f"{spec.label} raporda okunamadi; hesaplanan degerle karsilastirilamadi."
                    ),
                )
            )
            continue
        if calculated_value is None:
            discrepancies.append(
                Discrepancy(
                    field=spec.key,
                    label=spec.label,
                    reported=reported,
                    calculated=None,
                    unit=spec.unit,
                    delta=None,
                    tolerance=spec.tolerance_text,
                    status=STATUS_MISSING_IN_CALCULATION,
                    severity="info",
                    message=(
                        f"{spec.label} icin hesaplanan deger verilmedi; yalnizca "
                        "rapor degeri gosteriliyor."
                    ),
                )
            )
            continue

        reported_number = field.as_float() if field is not None else None
        try:
            calculated_number = float(calculated_value)
        except (TypeError, ValueError):
            calculated_number = None

        if reported_number is None or calculated_number is None:
            discrepancies.append(
                Discrepancy(
                    field=spec.key,
                    label=spec.label,
                    reported=reported,
                    calculated=calculated_value,
                    unit=spec.unit,
                    delta=None,
                    tolerance=spec.tolerance_text,
                    status=STATUS_NOT_COMPARABLE,
                    severity="warning",
                    message=f"{spec.label} sayisal degil; karsilastirma yapilamadi.",
                )
            )
            continue

        delta = reported_number - calculated_number
        within = _within_tolerance(delta, calculated_number, spec)
        if abs(delta) <= 1e-12:
            status, severity = STATUS_MATCH, "info"
        elif within:
            status, severity = STATUS_WITHIN_TOLERANCE, "info"
        else:
            status, severity = STATUS_MISMATCH, spec.mismatch_severity

        discrepancies.append(
            Discrepancy(
                field=spec.key,
                label=spec.label,
                reported=reported_number,
                calculated=calculated_number,
                unit=spec.unit,
                delta=delta,
                tolerance=spec.tolerance_text,
                status=status,
                severity=severity,
                message=_comparison_message(
                    spec, reported_number, calculated_number, delta, status
                ),
            )
        )

    discrepancies.append(_compare_result(report, calculated))
    return discrepancies


def _compare_result(report: HydrotestReport, calculated: dict[str, Any]) -> Discrepancy:
    reported_field = report.get_field("result")
    reported = reported_field.value if reported_field is not None else None
    calculated_value = calculated.get("result")
    label = FIELD_LABELS["result"]

    if reported is None:
        return Discrepancy(
            field="result",
            label=label,
            reported=None,
            calculated=calculated_value,
            unit="",
            delta=None,
            tolerance="birebir",
            status=STATUS_MISSING_IN_REPORT,
            severity="critical",
            message="Rapor sonucu okunamadi; kabul karari dogrulanamaz.",
        )
    if calculated_value is None:
        return Discrepancy(
            field="result",
            label=label,
            reported=str(reported),
            calculated=None,
            unit="",
            delta=None,
            tolerance="birebir",
            status=STATUS_MISSING_IN_CALCULATION,
            severity="info",
            message="Hesaplanan sonuc verilmedi; yalnizca rapor sonucu gosteriliyor.",
        )

    reported_text = str(reported).strip().upper()
    calculated_text = str(calculated_value).strip().upper()
    if reported_text == calculated_text:
        status, severity = STATUS_MATCH, "info"
        message = f"Sonuc uyusuyor ({reported_text})."
    else:
        status, severity = STATUS_MISMATCH, "critical"
        message = f"Sonuc uyusmuyor: rapor {reported_text}, hesaplanan {calculated_text}."
    return Discrepancy(
        field="result",
        label=label,
        reported=reported_text,
        calculated=calculated_text,
        unit="",
        delta=None,
        tolerance="birebir",
        status=status,
        severity=severity,
        message=message,
    )


def _lookup_calculated(calculated: dict[str, Any], spec: _ComparisonSpec) -> Any:
    node: Any = calculated
    for part in spec.calculated_path:
        if not isinstance(node, dict) or part not in node:
            node = None
            break
        node = node[part]
    if node is not None:
        return node

    flat_candidates = (".".join(spec.calculated_path), spec.key)
    for candidate in flat_candidates:
        if candidate in calculated:
            return calculated[candidate]
    return None


def _within_tolerance(delta: float, calculated: float, spec: _ComparisonSpec) -> bool:
    absolute = abs(delta)
    if spec.abs_tolerance is not None and absolute <= spec.abs_tolerance:
        return True
    if spec.rel_tolerance is not None:
        return absolute <= spec.rel_tolerance * abs(calculated)
    return False


def _comparison_message(
    spec: _ComparisonSpec,
    reported: float,
    calculated: float,
    delta: float,
    status: str,
) -> str:
    if status == STATUS_MATCH:
        return f"{spec.label} uyusuyor ({reported:g} {spec.unit})."
    if status == STATUS_WITHIN_TOLERANCE:
        return (
            f"{spec.label} tolerans icinde: rapor {reported:g}, hesaplanan "
            f"{calculated:g} {spec.unit} (fark {delta:+g}; tolerans {spec.tolerance_text})."
        )
    return (
        f"{spec.label} uyusmuyor: rapor {reported:g}, hesaplanan {calculated:g} "
        f"{spec.unit} (fark {delta:+g}; tolerans {spec.tolerance_text})."
    )


def has_blocking_discrepancies(discrepancies: Sequence[Discrepancy]) -> bool:
    return any(item.is_blocking for item in discrepancies)


# ---------------------------------------------------------------------------
# Tek giris noktasi
# ---------------------------------------------------------------------------


def analyze_report(
    path: str | os.PathLike[str],
    calculated: dict[str, Any] | None = None,
    *,
    extra_aliases: Mapping[str, Sequence[str]] | None = None,
    language: str | None = None,
    cancel_event: threading.Event | None = None,
    deadline_monotonic: float | None = None,
    timeout_seconds: float | None = None,
) -> OcrAnalysisResult:
    """Extract, parse, validate and (optionally) compare one report."""

    effective_deadline = deadline_monotonic
    if effective_deadline is None:
        budget = (
            timeout_seconds if timeout_seconds is not None else _resolve_ocr_total_timeout_seconds()
        )
        if budget > 0:
            effective_deadline = time.monotonic() + budget
    _check_ocr_abort(cancel_event, effective_deadline)
    resolved = validate_input_path(path)
    pages = extract_text(
        resolved,
        language=language,
        cancel_event=cancel_event,
        deadline_monotonic=effective_deadline,
    )
    _check_ocr_abort(cancel_event, effective_deadline)
    report = parse_report(
        pages,
        extra_aliases=dict(extra_aliases) if extra_aliases is not None else None,
    )

    issues = tuple(validate_report(report))
    warnings = list(report.warnings)
    for issue in issues:
        if issue.message not in warnings:
            warnings.append(issue.message)

    discrepancies: tuple[Discrepancy, ...] = ()
    if calculated is not None:
        discrepancies = tuple(compare_with_calculated(report, calculated))

    sources = {page.source for page in pages}
    if sources == {TEXT_SOURCE_OCR}:
        source = TEXT_SOURCE_OCR
    elif sources == {TEXT_SOURCE_SPREADSHEET}:
        source = TEXT_SOURCE_SPREADSHEET
    elif sources == {TEXT_SOURCE_LAYER}:
        source = "pdf-text-layer"
    else:
        source = "mixed"

    confidence = report.average_confidence()
    if source in {TEXT_SOURCE_OCR, "mixed"}:
        message = "OCR kullanildi; tum alanlar insan onayindan gecmelidir."
        if message not in warnings:
            warnings.append(message)

    # Resmi kabul her zaman yetkili personel onayina tabidir. Guven skoru
    # yalnizca otomatik doldurma ve alan bazli inceleme seviyesini belirler.
    return OcrAnalysisResult(
        path=str(resolved),
        source=source,
        page_count=len(pages),
        character_count=_text_char_count(pages),
        confidence=confidence,
        report=report,
        discrepancies=discrepancies,
        issues=issues,
        warnings=tuple(warnings),
        needs_human_review=True,
        pages=tuple(pages),
    )


__all__ = [
    "ERROR_CANCELLED",
    "ERROR_CORRUPT_DOCUMENT",
    "ERROR_CORRUPT_IMAGE",
    "ERROR_DEPENDENCY_MISSING",
    "ERROR_EMPTY_FILE",
    "ERROR_EMPTY_TEXT",
    "ERROR_ENCRYPTED_PDF",
    "ERROR_FILE_NOT_FOUND",
    "ERROR_FILE_TOO_LARGE",
    "ERROR_INVALID_CALCULATED",
    "ERROR_INVALID_PATH",
    "ERROR_OCR_UNAVAILABLE",
    "ERROR_TIMEOUT",
    "ERROR_UNSUPPORTED_FORMAT",
    "MAX_ALLOWED_UPLOAD_MB",
    "MAX_FILE_SIZE_BYTES",
    "OcrAnalysisResult",
    "PageText",
    "Discrepancy",
    "ReportOcrError",
    "SPREADSHEET_EXTENSIONS",
    "SUPPORTED_EXTENSIONS",
    "TEXT_SOURCE_SPREADSHEET",
    "analyze_report",
    "clear_ocr_probe_cache",
    "compare_with_calculated",
    "effective_max_file_size_bytes",
    "extract_text",
    "has_blocking_discrepancies",
    "normalize_result",
    "ocr_available",
    "ocr_engine_details",
    "ocr_engine_name",
    "ocr_pdf_page_rotated",
    "ocr_status",
    "parse_date",
    "parse_number",
    "parse_report",
    "pdf_rasterizer_status",
    "validate_input_path",
    "vision_available",
    "windows_ocr_available",
    "windows_pdf_available",
]

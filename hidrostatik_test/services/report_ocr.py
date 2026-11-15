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

Agir OCR bagimliliklari (``pytesseract``, ``Pillow``, ``PyMuPDF``) zorunlu
degildir; yoksa metin katmani ile devam edilir ve anlasilir bir
:class:`ReportOcrError` uretilir.
"""

from __future__ import annotations

import importlib
import importlib.util
import io
import os
import re
from dataclasses import dataclass, replace
from datetime import date as _date
from pathlib import Path
from typing import Any, Final, Sequence

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

#: Dosya boyutu guvenlik siniri (25 MB). Taranmis raporlar tipik olarak
#: 1-10 MB araligindadir; buyuk dosyalar bellek tuketimini sinirlamak icin
#: reddedilir.
MAX_FILE_SIZE_BYTES: Final[int] = 25 * 1024 * 1024
#: PDF sayfa siniri; OCR maliyetini ve calisma suresini sinirlar.
MAX_PDF_PAGES: Final[int] = 200
#: OCR'a verilecek en fazla sayfa sayisi.
MAX_OCR_PAGES: Final[int] = 30
#: Metin katmani bu karakter sayisinin altindaysa OCR denenir.
MIN_TEXT_LAYER_CHARS: Final[int] = 40
#: Regex/veri isleme icin metin uzunlugu siniri.
MAX_TEXT_CHARS: Final[int] = 2_000_000
#: OCR goruntusunun yeniden olceklenme esigi (piksel).
OCR_MIN_IMAGE_WIDTH: Final[int] = 1200

SUPPORTED_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
)
IMAGE_EXTENSIONS: Final[frozenset[str]] = SUPPORTED_EXTENSIONS - {".pdf"}

STATUS_MATCH: Final[str] = "match"
STATUS_WITHIN_TOLERANCE: Final[str] = "within_tolerance"
STATUS_MISMATCH: Final[str] = "mismatch"
STATUS_MISSING_IN_REPORT: Final[str] = "missing_in_report"
STATUS_MISSING_IN_CALCULATION: Final[str] = "missing_in_calculation"
STATUS_NOT_COMPARABLE: Final[str] = "not_comparable"

TEXT_SOURCE_LAYER: Final[str] = "text-layer"
TEXT_SOURCE_OCR: Final[str] = "ocr"


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
    if size > MAX_FILE_SIZE_BYTES:
        raise ReportOcrError(
            (
                "Rapor dosyasi boyut sinirini asiyor "
                f"({size / (1024 * 1024):.1f} MB > "
                f"{MAX_FILE_SIZE_BYTES / (1024 * 1024):.0f} MB)."
            ),
            ERROR_FILE_TOO_LARGE,
        )
    return resolved


# ---------------------------------------------------------------------------
# Metin cikarimi (PDF text layer + opsiyonel OCR)
# ---------------------------------------------------------------------------


def extract_text(path: str | os.PathLike[str]) -> list[PageText]:
    """Extract text pages from a PDF or an image report.

    PDF'lerde once gomulu metin katmani okunur. Metin katmani yoksa veya
    esigi gecmiyorsa OCR denenir. OCR bagimliligi yoksa metin varsa
    zayif-metin uyarisiyla donulur, metin de yoksa hata yukseltilir.
    """

    resolved = validate_input_path(path)
    if resolved.suffix.lower() == ".pdf":
        pages = _extract_pdf_text(resolved)
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
            ocr_pages = _ocr_pdf_pages(resolved)
        except ReportOcrError as exc:
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

    return [_ocr_image_page(resolved)]


def _extract_pdf_text(path: Path) -> list[PageText]:
    reader_pages = _extract_pdf_text_with_pypdf(path)
    if reader_pages is not None:
        return reader_pages
    plumber_pages = _extract_pdf_text_with_pdfplumber(path)
    if plumber_pages is not None:
        return plumber_pages
    raise ReportOcrError(
        "PDF okumak icin pypdf (veya pdfplumber) gerekli. requirements-ocr.txt kurun.",
        ERROR_DEPENDENCY_MISSING,
    )


def _extract_pdf_text_with_pypdf(path: Path) -> list[PageText] | None:
    if importlib.util.find_spec("pypdf") is None:
        return None
    pypdf = importlib.import_module("pypdf")
    try:
        reader = pypdf.PdfReader(str(path))
        _ensure_pdf_not_encrypted(reader)
        page_count = min(len(reader.pages), MAX_PDF_PAGES)
        pages: list[PageText] = []
        for index in range(page_count):
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


def _extract_pdf_text_with_pdfplumber(path: Path) -> list[PageText] | None:
    if importlib.util.find_spec("pdfplumber") is None:
        return None
    pdfplumber = importlib.import_module("pdfplumber")
    try:
        with pdfplumber.open(str(path)) as pdf:
            page_count = min(len(pdf.pages), MAX_PDF_PAGES)
            return [
                PageText(page_number=index + 1, text=pdf.pages[index].extract_text() or "")
                for index in range(page_count)
            ]
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


def ocr_available() -> bool:
    """Return ``True`` when Tesseract and Pillow are usable.

    ``pytesseract`` paketi kurulu olsa bile ``tesseract`` calistirilabilir
    dosyasi yoksa ``False`` doner. Testler bu fonksiyonla skip karari verir.
    """

    if importlib.util.find_spec("pytesseract") is None:
        return False
    if importlib.util.find_spec("PIL") is None:
        return False
    try:
        pytesseract = importlib.import_module("pytesseract")
        pytesseract.get_tesseract_version()
    except Exception:
        return False
    return True


def ocr_status() -> str:
    """Return a short human-readable OCR availability note."""

    if ocr_available():
        return "OCR hazir (Tesseract + Pillow)."
    if importlib.util.find_spec("pytesseract") is None:
        return "OCR yok: pytesseract kurulu degil (requirements-ocr.txt)."
    if importlib.util.find_spec("PIL") is None:
        return "OCR yok: Pillow kurulu degil (requirements-ocr.txt)."
    return "OCR yok: tesseract calistirilabilir dosyasi bulunamadi."


def _ocr_prerequisites_available() -> bool:
    return (
        importlib.util.find_spec("pytesseract") is not None
        and importlib.util.find_spec("PIL") is not None
    )


def _ocr_pdf_pages(path: Path) -> list[PageText]:
    images = _render_pdf_pages(path)
    pages: list[PageText] = []
    for index, image in enumerate(images):
        text, confidence, warning = _run_tesseract(image)
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


def _render_pdf_pages(path: Path) -> list[Any]:
    """Rasterize PDF pages with the first available optional backend."""

    if importlib.util.find_spec("fitz") is not None:
        return _render_pdf_pages_with_fitz(path)

    if importlib.util.find_spec("pdf2image") is not None:
        pdf2image = importlib.import_module("pdf2image")
        try:
            return list(
                pdf2image.convert_from_path(
                    str(path), dpi=200, first_page=1, last_page=MAX_OCR_PAGES
                )
            )
        except Exception as exc:
            raise ReportOcrError(
                "PDF sayfalari OCR icin goruntuye cevrilemedi.",
                ERROR_CORRUPT_DOCUMENT,
                detail=str(exc),
            ) from exc

    raise ReportOcrError(
        "Taranmis PDF'ler icin PyMuPDF veya pdf2image gerekli (requirements-ocr.txt).",
        ERROR_OCR_UNAVAILABLE,
    )


def _render_pdf_pages_with_fitz(path: Path) -> list[Any]:
    fitz = importlib.import_module("fitz")
    from PIL import Image  # noqa: PLC0415 - opsiyonel bagimlilik, tembel import

    try:
        document = fitz.open(str(path))
    except Exception as exc:
        raise ReportOcrError(
            "PDF OCR icin acilamadi.", ERROR_CORRUPT_DOCUMENT, detail=str(exc)
        ) from exc

    images: list[Any] = []
    try:
        page_count = min(len(document), MAX_OCR_PAGES)
        for index in range(page_count):
            pixmap = document[index].get_pixmap(dpi=200)
            images.append(Image.open(io.BytesIO(pixmap.tobytes("png"))))
    except Exception as exc:
        raise ReportOcrError(
            "PDF sayfasi goruntuye cevrilemedi.", ERROR_CORRUPT_DOCUMENT, detail=str(exc)
        ) from exc
    finally:
        document.close()
    return images


def _ocr_image_page(path: Path) -> PageText:
    if importlib.util.find_spec("PIL") is None or importlib.util.find_spec("pytesseract") is None:
        raise ReportOcrError(
            "Goruntu OCR icin pytesseract ve Pillow gerekli (requirements-ocr.txt).",
            ERROR_DEPENDENCY_MISSING,
        )
    image = _load_image(path)
    text, confidence, warning = _run_tesseract(image)
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

    try:
        with Image.open(path) as image:
            image.load()
            grayscale = image.convert("L")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ReportOcrError(
            "Goruntu dosyasi bozuk veya desteklenmiyor.",
            ERROR_CORRUPT_IMAGE,
            detail=str(exc),
        ) from exc

    if grayscale.width < OCR_MIN_IMAGE_WIDTH:
        scale = 2
        grayscale = grayscale.resize(
            (grayscale.width * scale, grayscale.height * scale),
            Image.Resampling.LANCZOS,
        )
    return grayscale


def _choose_tesseract_language() -> tuple[str, str]:
    override = os.environ.get("HYDRO_OCR_LANG", "").strip()
    if override:
        return override, ""

    try:
        pytesseract = importlib.import_module("pytesseract")
        available = set(pytesseract.get_languages(config=""))
    except Exception:
        available = set()

    selected = [language for language in ("tur", "eng") if language in available]
    if selected:
        return "+".join(selected), ""
    return "eng", "Tesseract 'tur' dil paketi bulunamadi; OCR ingilizce ile yapildi."


def _run_tesseract(image: Any) -> tuple[str, float | None, str]:
    try:
        pytesseract = importlib.import_module("pytesseract")
    except ImportError as exc:  # pragma: no cover - onceden kontrol edilir
        raise ReportOcrError("OCR icin pytesseract gerekli.", ERROR_OCR_UNAVAILABLE) from exc

    language, warning = _choose_tesseract_language()
    try:
        data = pytesseract.image_to_data(
            image,
            lang=language,
            output_type=pytesseract.Output.DICT,
        )
    except Exception as exc:
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
    "wall_mm": ("mm", "length"),
    "length_m": ("m", "length"),
    "test_pressure_bar": (UNIT_BAR, "pressure"),
    "air_test.vp": (UNIT_M3, "volume"),
    "air_test.vpa": (UNIT_M3, "volume"),
    "air_test.a": (UNIT_MICRO_PER_BAR, "compressibility"),
    "pressure_test.t_initial": (UNIT_CELSIUS, "temperature"),
    "pressure_test.t_final": (UNIT_CELSIUS, "temperature"),
    "pressure_test.delta_t": (UNIT_CELSIUS, "temperature_delta"),
    "pressure_test.pa": (UNIT_BAR, "pressure"),
    "pressure_test.a": (UNIT_MICRO_PER_BAR, "compressibility"),
    "pressure_test.b": (UNIT_MICRO_PER_C, "expansion"),
}

_STRING_FIELDS: Final[frozenset[str]] = frozenset({"report_no", "operator", "section_id", "notes"})

_PLAUSIBLE_RANGES: Final[dict[str, tuple[float, float]]] = {
    "pipe_od_mm": (10.0, 3000.0),
    "wall_mm": (0.5, 100.0),
    "length_m": (0.5, 5_000_000.0),
    "test_pressure_bar": (0.0, 1000.0),
    "air_test.vp": (0.0, 100_000.0),
    "air_test.vpa": (0.0, 100_000.0),
    "air_test.a": (1.0, 200.0),
    "pressure_test.t_initial": (-60.0, 120.0),
    "pressure_test.t_final": (-60.0, 120.0),
    "pressure_test.delta_t": (-60.0, 60.0),
    "pressure_test.pa": (0.0, 100.0),
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
    "basarisiz",
    "fail",
    "kabul edilmedi",
    "uygun degil",
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


def _build_alias_patterns() -> tuple[tuple[re.Pattern[str], str], ...]:
    entries: list[tuple[int, re.Pattern[str], str]] = []
    seen: set[tuple[str, str]] = set()

    for key, aliases in FIELD_ALIASES.items():
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
    if any(word in folded for word in _FAIL_WORDS):
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


def parse_report(text_pages: Sequence[PageText] | str) -> HydrotestReport:
    """Parse a hydrostatic test report from text pages.

    ``text_pages`` yerine dogrudan bir metin de verilebilir; bu gelistirme
    ve test kolayligi icindir.
    """

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

    for page in pages:
        section = ""
        page_text = page.text[:MAX_TEXT_CHARS]
        for raw_line in page_text.splitlines():
            folded = _fold(raw_line)
            stripped = folded.strip()
            if not stripped:
                continue

            if section_kind := _section_heading(stripped):
                section = section_kind
                continue

            matched = _match_field_line(folded)
            if matched is None:
                continue
            key, rest_start = matched
            rest = raw_line[rest_start:].strip()
            if not rest:
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

            order += 1
            extracted = _build_field(key, rest, page, warnings, source=page.source)
            if extracted is None:
                continue
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

    report = HydrotestReport(
        report_no=values.get("report_no"),
        date=values.get("date"),
        operator=values.get("operator"),
        section_id=values.get("section_id"),
        pipe_od_mm=values.get("pipe_od_mm"),
        wall_mm=values.get("wall_mm"),
        length_m=values.get("length_m"),
        test_pressure_bar=values.get("test_pressure_bar"),
        air_test=AirTestFields(
            vp=values.get("air_test.vp"),
            vpa=values.get("air_test.vpa"),
            a=values.get("air_test.a"),
        ),
        pressure_test=PressureTestFields(
            t_initial=values.get("pressure_test.t_initial"),
            t_final=values.get("pressure_test.t_final"),
            delta_t=values.get("pressure_test.delta_t"),
            pa=values.get("pressure_test.pa"),
            a=values.get("pressure_test.a"),
            b=values.get("pressure_test.b"),
        ),
        result=values.get("result"),
        notes=values.get("notes"),
        warnings=tuple(dict.fromkeys(warnings)),
    )
    return report


def _match_field_line(folded_line: str) -> tuple[str, int] | None:
    for pattern, key in _ALIAS_PATTERNS:
        match = pattern.match(folded_line)
        if match is not None:
            return key, match.start("rest")
    return None


def _build_field(
    key: str,
    rest: str,
    page: PageText,
    warnings: list[str],
    *,
    source: str,
) -> ExtractedField | None:
    base_confidence = 0.9 if source == TEXT_SOURCE_LAYER else 0.55
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
) -> OcrAnalysisResult:
    """Extract, parse, validate and (optionally) compare one report."""

    resolved = validate_input_path(path)
    pages = extract_text(resolved)
    report = parse_report(pages)

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
    )


__all__ = [
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
    "ERROR_UNSUPPORTED_FORMAT",
    "MAX_FILE_SIZE_BYTES",
    "OcrAnalysisResult",
    "PageText",
    "Discrepancy",
    "ReportOcrError",
    "SUPPORTED_EXTENSIONS",
    "analyze_report",
    "compare_with_calculated",
    "extract_text",
    "has_blocking_discrepancies",
    "normalize_result",
    "ocr_available",
    "ocr_status",
    "parse_date",
    "parse_number",
    "parse_report",
    "validate_input_path",
]

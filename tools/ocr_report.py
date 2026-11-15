"""Hidrostatik test raporu OCR/alan cikarim CLI araci.

Kullanim::

    python3 tools/ocr_report.py <rapor.pdf|jpg> [--json] [--calculated calculated.json]

Cikis kodlari:

- ``0``: rapor okundu, uyusmazlik yok.
- ``1``: rapor okundu ancak hesaplanan degerlerle uyusmazlik var.
- ``2``: giris hatasi (dosya yok, desteklenmeyen tur, sifreli PDF, bos
  metin, gecersiz JSON vb.).

``--calculated`` dosyasinin semasi (eksik anahtarlar sorun degildir; araç
yalnizca verilen alanlari karsilastirir)::

    {
      "pipe_od_mm": 406.4,
      "wall_mm": 8.74,
      "length_m": 1000.0,
      "test_pressure_bar": 80.0,
      "air_test": {
        "vp_m3": 0.0076825,
        "vpa_m3": 0.00775,
        "a_micro_per_bar": 45.3
      },
      "pressure_test": {
        "t_initial_c": 21.0,
        "t_final_c": 20.0,
        "delta_t_c": 1.0,
        "pa_bar": 0.4,
        "a_micro_per_bar": 45.3,
        "b_micro_per_c": 65.0
      },
      "result": "PASS"
    }

Ornek::

    python3 tools/ocr_report.py saha_raporu.pdf --json
    python3 tools/ocr_report.py tarama.jpg --calculated calc.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hidrostatik_test.domain.report_schema import (  # noqa: E402
    FIELD_LABELS,
    REQUIRED_FIELDS,
)
from hidrostatik_test.services.report_ocr import (  # noqa: E402
    ERROR_INVALID_CALCULATED,
    MAX_FILE_SIZE_BYTES,
    OcrAnalysisResult,
    ReportOcrError,
    analyze_report,
    has_blocking_discrepancies,
    ocr_status,
)

_STATUS_LABELS = {
    "match": "UYUYOR",
    "within_tolerance": "TOLERANS ICINDE",
    "mismatch": "UYUSMUYOR",
    "missing_in_report": "RAPORDA YOK",
    "missing_in_calculation": "HESAPLANAN YOK",
    "not_comparable": "KARSILASTIRILAMAZ",
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Hidrostatik test raporunu (PDF/gorsel) okur, alanlari cikarir ve "
            "uygulamanin hesapladigi degerlerle karsilastirir."
        )
    )
    parser.add_argument("report", help="Rapor dosyasi (.pdf, .png, .jpg, .tif ...)")
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Insan okunur ozet yerine makine okunur JSON yaz.",
    )
    parser.add_argument(
        "--calculated",
        metavar="CALCULATED_JSON",
        help="Uygulamanin hesapladigi degerleri iceren JSON dosyasi.",
    )
    return parser


def _load_calculated(path_text: str) -> dict[str, Any]:
    path = Path(path_text).expanduser().resolve()
    if not path.is_file():
        raise ReportOcrError(
            f"Hesaplanan deger dosyasi bulunamadi: {path.name}",
            ERROR_INVALID_CALCULATED,
        )
    if path.stat().st_size > MAX_FILE_SIZE_BYTES:
        raise ReportOcrError(
            "Hesaplanan deger dosyasi boyut sinirini asiyor.",
            ERROR_INVALID_CALCULATED,
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReportOcrError(
            "Hesaplanan deger dosyasi gecerli UTF-8 JSON degil.",
            ERROR_INVALID_CALCULATED,
            detail=str(exc),
        ) from exc
    if not isinstance(payload, dict):
        raise ReportOcrError(
            "Hesaplanan deger dosyasi bir JSON nesnesi (dict) olmalidir.",
            ERROR_INVALID_CALCULATED,
        )
    return payload


def _format_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        magnitude = abs(value)
        if magnitude != 0 and (magnitude < 1e-3 or magnitude >= 1e6):
            return f"{value:.6g}"
        return f"{value:g}"
    return str(value)


def _human_summary(result: OcrAnalysisResult) -> str:
    lines: list[str] = []
    lines.append("Hidrostatik Test Raporu OCR Analizi")
    lines.append("=" * 38)
    lines.append(f"Dosya       : {result.path}")
    lines.append(f"Kaynak      : {result.source}")
    lines.append(f"Sayfa       : {result.page_count}")
    lines.append(f"Metin       : {result.character_count} karakter")
    lines.append(f"Guven       : {result.confidence:.0%}")
    lines.append("Insan onayi : " + ("gerekli" if result.needs_human_review else "gerekmiyor"))
    lines.append(f"OCR         : {ocr_status()}")
    lines.append("")

    lines.append("Cikarilan alanlar")
    lines.append("-" * 17)
    fields = dict(result.report.iter_fields())
    for key, label in FIELD_LABELS.items():
        extracted = fields.get(key)
        if extracted is None:
            continue
        unit = f" {extracted.unit}" if extracted.unit else ""
        lines.append(
            f"{label:<24}: {_format_value(extracted.value)}{unit} "
            f"(guven {extracted.confidence:.0%}, sayfa {extracted.page or '-'})"
        )
    if not fields:
        lines.append("(alan bulunamadi)")

    missing_required = [
        FIELD_LABELS.get(key, key)
        for key in REQUIRED_FIELDS
        if result.report.get_field(key) is None
    ]
    if missing_required:
        lines.append("")
        lines.append("Eksik zorunlu alanlar: " + ", ".join(missing_required))

    if result.discrepancies:
        lines.append("")
        lines.append("Hesaplanan degerlerle karsilastirma")
        lines.append("-" * 35)
        for item in result.discrepancies:
            status = _STATUS_LABELS.get(item.status, item.status.upper())
            lines.append(
                f"[{status}] {item.label}: rapor {_format_value(item.reported)}, "
                f"hesaplanan {_format_value(item.calculated)} {item.unit}".rstrip()
            )
            lines.append(f"    {item.message}")

    if result.warnings:
        lines.append("")
        lines.append("Uyarilar")
        lines.append("-" * 8)
        for warning in result.warnings:
            lines.append(f"- {warning}")

    lines.append("")
    lines.append(
        "Not: Bu cikti otomatik alan cikarimidir; resmi kabul icin yetkili "
        "personel tarafindan dogrulanmalidir."
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        calculated = _load_calculated(args.calculated) if args.calculated else None
        result = analyze_report(args.report, calculated)
    except ReportOcrError as exc:
        if args.json_output:
            payload = {"ok": False, "error": exc.to_dict()}
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Hata: {exc.message}", file=sys.stderr)
            if exc.detail:
                print(f"Detay: {exc.detail}", file=sys.stderr)
        return 2

    exit_code = 1 if has_blocking_discrepancies(result.discrepancies) else 0

    if args.json_output:
        payload = {"ok": True, "exit_code": exit_code, **result.to_dict()}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(_human_summary(result))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

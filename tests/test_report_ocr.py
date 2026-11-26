from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from hidrostatik_test.domain.report_schema import (
    UNIT_BAR,
    UNIT_M3,
    UNIT_MM,
    AirTestFields,
    ExtractedField,
    HydrotestReport,
    PressureTestFields,
    convert_temperature_delta,
    convert_unit,
    normalize_unit,
    validate_report,
)
from hidrostatik_test.services import report_ocr as ocr

HAVE_PYPDF = importlib.util.find_spec("pypdf") is not None
HAVE_PYMUPDF = importlib.util.find_spec("fitz") is not None
HAVE_REPORTLAB = importlib.util.find_spec("reportlab") is not None
HAVE_PIL = importlib.util.find_spec("PIL") is not None
HAVE_PYTESSERACT = importlib.util.find_spec("pytesseract") is not None
HAVE_PYPDFIUM2 = importlib.util.find_spec("pypdfium2") is not None
HAVE_QUARTZ = (
    sys.platform == "darwin"
    and importlib.util.find_spec("Quartz") is not None
    and importlib.util.find_spec("CoreFoundation") is not None
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = PROJECT_ROOT / "tools" / "ocr_report.py"

TURKISH_REPORT = """HIDROSTATIK TEST VERILERI
Rapor No: BOT-FRM-CDB-001-021 / 2026-041
Tarih: 15.11.2026
Operatör: M. Yılmaz
Bölüm No: H-07
Dış Çap: 16" (406,4 mm)
Et Kalınlığı: 8,74 mm
Uzunluk: 1.000 m
Test Basıncı: 80 bar

HAVA İÇERİK TESTİ
Vp: 7,6825 L
Vpa: 7,75 L
A: 45,3 x10^-6/bar

BASINÇ TESTİ
Tilk: 21,0 °C
Tson: 20,0 °C
dT: 1,0 °C
Pa: 0,40 bar
A: 45,3
B: 65,0
Sonuç: BAŞARILI
Not: Test sorunsuz tamamlandi.
"""

ENGLISH_REPORT = """HYDROSTATIC TEST REPORT
Report No: R-2026-001
Date: 2026-11-15
Outside Diameter: 16 in
Wall Thickness: 8.74 mm
Length: 1000 m
Test Pressure: 80 bar
AIR CONTENT TEST
Vp: 7.6825 L
Vpa: 7.75 L
A: 45.3
PRESSURE TEST
Tilk: 21.0 C
Tson: 20.0 C
dT: 1.0 C
Pa: 0.40 bar
A: 45.3
B: 65.0
Result: PASS
"""

MATCHING_CALCULATED = {
    "pipe_od_mm": 406.4,
    "wall_mm": 8.74,
    "length_m": 1000.0,
    "test_pressure_bar": 80.0,
    "air_test": {
        "vp_m3": 0.0076825,
        "vpa_m3": 0.00775,
        "a_micro_per_bar": 45.3,
    },
    "pressure_test": {
        "t_initial_c": 21.0,
        "t_final_c": 20.0,
        "delta_t_c": 1.0,
        "pa_bar": 0.40,
        "a_micro_per_bar": 45.3,
        "b_micro_per_c": 65.0,
    },
    "result": "PASS",
}


def _write_text_pdf(path: Path, lines: list[str]) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    pdf = canvas.Canvas(str(path), pagesize=A4)
    y_position = 800
    for line in lines:
        pdf.drawString(40, y_position, line)
        y_position -= 16
    pdf.save()


def _write_blank_pdf(path: Path) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    pdf = canvas.Canvas(str(path), pagesize=A4)
    pdf.showPage()
    pdf.save()


class ReportSchemaTests(unittest.TestCase):
    def test_to_dict_from_dict_roundtrip(self) -> None:
        report = HydrotestReport(
            report_no=ExtractedField("R-1", confidence=0.9, raw_text="Rapor No: R-1"),
            pipe_od_mm=ExtractedField(406.4, unit="mm", confidence=0.9),
            air_test=AirTestFields(vp=ExtractedField(0.0076825, unit="m³", confidence=0.8)),
            result=ExtractedField("PASS", confidence=0.95),
            warnings=("ornek uyari",),
        )

        payload = report.to_dict()
        restored = HydrotestReport.from_dict(payload)

        self.assertEqual(restored.report_no.value, "R-1")
        self.assertEqual(restored.pipe_od_mm.value, 406.4)
        self.assertEqual(restored.air_test.vp.unit, "m³")
        self.assertEqual(restored.result.value, "PASS")
        self.assertEqual(restored.warnings, ("ornek uyari",))
        self.assertEqual(restored.to_dict(), payload)

    def test_validation_reports_missing_required_fields(self) -> None:
        issues = validate_report(HydrotestReport())
        codes = {issue.code for issue in issues}
        self.assertIn("missing_required", codes)
        self.assertIn("no_fields", codes)
        self.assertEqual(len([i for i in issues if i.code == "missing_required"]), 4)

    def test_validation_flags_air_test_limit(self) -> None:
        report = HydrotestReport(
            pipe_od_mm=ExtractedField(406.4, unit="mm", confidence=0.9),
            wall_mm=ExtractedField(8.74, unit="mm", confidence=0.9),
            length_m=ExtractedField(1000.0, unit="m", confidence=0.9),
            test_pressure_bar=ExtractedField(80.0, unit="bar", confidence=0.9),
            air_test=AirTestFields(
                vp=ExtractedField(0.0076825, unit="m³", confidence=0.9),
                vpa=ExtractedField(0.0082, unit="m³", confidence=0.9),
            ),
        )
        issues = validate_report(report)
        self.assertTrue(any(issue.code == "air_test_limit_exceeded" for issue in issues))

    def test_validation_flags_delta_t_mismatch(self) -> None:
        report = HydrotestReport(
            pressure_test=PressureTestFields(
                t_initial=ExtractedField(20.0, unit="°C", confidence=0.9),
                t_final=ExtractedField(21.0, unit="°C", confidence=0.9),
                delta_t=ExtractedField(2.0, unit="°C", confidence=0.9),
            )
        )
        issues = validate_report(report)
        self.assertTrue(any(issue.code == "delta_t_mismatch" for issue in issues))

    def test_unit_normalization_and_conversion(self) -> None:
        self.assertEqual(normalize_unit("M3"), "m³")
        self.assertEqual(normalize_unit("m³"), "m³")
        self.assertEqual(normalize_unit("bar"), UNIT_BAR)
        self.assertEqual(normalize_unit("° C"), "°C")
        self.assertAlmostEqual(convert_unit(7.6825, "L", UNIT_M3), 0.0076825)
        self.assertAlmostEqual(convert_unit(7750, "mL", UNIT_M3), 0.00775)
        self.assertAlmostEqual(convert_unit(16, "in", UNIT_MM), 406.4)
        self.assertAlmostEqual(convert_unit(1.0, "km", "m"), 1000.0)
        self.assertAlmostEqual(convert_unit(80.0, "bar", UNIT_BAR), 80.0)
        self.assertAlmostEqual(convert_temperature_delta(1.8, "°F", "°C"), 1.0)
        with self.assertRaises(ValueError):
            convert_unit(1.0, "bar", "mm")


class ReportParsingTests(unittest.TestCase):
    def test_parse_turkish_report(self) -> None:
        report = ocr.parse_report(TURKISH_REPORT)

        self.assertEqual(report.report_no.value, "BOT-FRM-CDB-001-021 / 2026-041")
        self.assertEqual(report.date.value, "2026-11-15")
        self.assertEqual(report.operator.value, "M. Yılmaz")
        self.assertEqual(report.section_id.value, "H-07")
        self.assertAlmostEqual(report.pipe_od_mm.as_float(), 406.4)
        self.assertEqual(report.pipe_od_mm.unit, "mm")
        self.assertAlmostEqual(report.wall_mm.as_float(), 8.74)
        self.assertAlmostEqual(report.length_m.as_float(), 1000.0)
        self.assertAlmostEqual(report.test_pressure_bar.as_float(), 80.0)
        self.assertAlmostEqual(report.air_test.vp.as_float(), 0.0076825)
        self.assertAlmostEqual(report.air_test.vpa.as_float(), 0.00775)
        self.assertAlmostEqual(report.air_test.a.as_float(), 45.3)
        self.assertAlmostEqual(report.pressure_test.t_initial.as_float(), 21.0)
        self.assertAlmostEqual(report.pressure_test.t_final.as_float(), 20.0)
        self.assertAlmostEqual(report.pressure_test.delta_t.as_float(), 1.0)
        self.assertAlmostEqual(report.pressure_test.pa.as_float(), 0.40)
        self.assertAlmostEqual(report.pressure_test.a.as_float(), 45.3)
        self.assertAlmostEqual(report.pressure_test.b.as_float(), 65.0)
        self.assertEqual(report.result.value, "PASS")
        self.assertIn("sorunsuz", report.notes.value)
        self.assertTrue(report.is_complete())
        self.assertGreater(report.average_confidence(), 0.7)

    def test_parse_english_report_with_dot_decimals_and_inches(self) -> None:
        report = ocr.parse_report(ENGLISH_REPORT)

        self.assertAlmostEqual(report.pipe_od_mm.as_float(), 406.4)
        self.assertAlmostEqual(report.wall_mm.as_float(), 8.74)
        self.assertAlmostEqual(report.length_m.as_float(), 1000.0)
        self.assertAlmostEqual(report.air_test.vp.as_float(), 0.0076825)
        self.assertAlmostEqual(report.air_test.vpa.as_float(), 0.00775)
        self.assertAlmostEqual(report.pressure_test.pa.as_float(), 0.4)
        self.assertEqual(report.result.value, "PASS")

    def test_number_formats(self) -> None:
        cases = {
            "1.234,56": 1234.56,
            "0,40": 0.40,
            "1.000": 1000.0,
            "0.884": 0.884,
            "80.5": 80.5,
            "45,515": 45.515,
            "7 682,5": 7682.5,
            "4,53E-05": 4.53e-05,
            "-12,5": -12.5,
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertAlmostEqual(ocr.parse_number(raw), expected)

    def test_dot_decimal_detection_and_three_digit_decimals(self) -> None:
        self.assertAlmostEqual(ocr.parse_number("1.000"), 1000.0)
        self.assertAlmostEqual(ocr.parse_number("105.250", dot_decimal=True), 105.25)
        self.assertAlmostEqual(ocr.parse_number("102.009", dot_decimal=True), 102.009)
        self.assertAlmostEqual(ocr.parse_number("1,952.77", dot_decimal=True), 1952.77)

        tr_text = (
            "Tarih: 28.09.2026\n"
            "Dış Çap: 355,60 mm\n"
            "Et Kalınlığı: 5,20 mm\n"
            "Uzunluk: 1.000 m\n"
            "BOT-FRM-İNB-001-017 REV.0\n"
        )
        en_text = (
            "Date: 28.09.2026\n"
            "KP 9+650.00\n"
            "1. Test Bolumu\n"
            "Boru Dış Çapı : 323.90 mm\n"
            "Boru Et Kalınlığı : 5.20 mm\n"
            "Basınç : 105.250 bar\n"
            "BOT-FRM-İNB-001-018 REV.0\n"
        )
        self.assertFalse(ocr.is_dot_decimal_text(tr_text))
        self.assertTrue(ocr.is_dot_decimal_text(en_text))

    def test_date_formats(self) -> None:
        self.assertEqual(ocr.parse_date("15.11.2026"), "2026-11-15")
        self.assertEqual(ocr.parse_date("15/11/2026"), "2026-11-15")
        self.assertEqual(ocr.parse_date("2026-11-15"), "2026-11-15")
        self.assertEqual(ocr.parse_date("15 Kasım 2026"), "2026-11-15")
        self.assertEqual(ocr.parse_date("15 November 2026"), "2026-11-15")
        with self.assertRaises(ValueError):
            ocr.parse_date("gecersiz tarih")

    def test_unit_suffixes_are_converted(self) -> None:
        report = ocr.parse_report(
            "Dış Çap: 0,4064 m\n"
            "Et Kalınlığı: 0,874 cm\n"
            "Uzunluk: 1 km\n"
            "Test Basıncı: 1160,3 psi\n"
            "Vp: 7682,5 mL\n"
            "Tilk: 68 °F\n"
            "Tson: 69,8 °F\n"
        )
        self.assertAlmostEqual(report.pipe_od_mm.as_float(), 406.4, places=3)
        self.assertAlmostEqual(report.wall_mm.as_float(), 8.74, places=3)
        self.assertAlmostEqual(report.length_m.as_float(), 1000.0)
        self.assertAlmostEqual(report.test_pressure_bar.as_float(), 80.0, places=2)
        self.assertAlmostEqual(report.air_test.vp.as_float(), 0.0076825)
        self.assertAlmostEqual(report.pressure_test.t_initial.as_float(), 20.0, places=2)
        self.assertAlmostEqual(report.pressure_test.t_final.as_float(), 21.0, places=2)

    def test_incompatible_unit_produces_warning(self) -> None:
        report = ocr.parse_report("Et Kalınlığı: 8,74 bar\n")
        self.assertIsNotNone(report.wall_mm)
        self.assertTrue(any("birim uyumsuz" in warning for warning in report.warnings))

    def test_missing_fields_stay_none(self) -> None:
        report = ocr.parse_report("Rapor No: R-9\nDış Çap: 406,4 mm\n")
        self.assertIsNone(report.wall_mm)
        self.assertIsNone(report.air_test.vp)
        self.assertIsNone(report.pressure_test.b)
        self.assertFalse(report.is_complete())

    def test_empty_text_raises(self) -> None:
        with self.assertRaises(ocr.ReportOcrError) as context:
            ocr.parse_report("   \n\t ")
        self.assertEqual(context.exception.code, ocr.ERROR_EMPTY_TEXT)

    def test_result_normalization(self) -> None:
        self.assertEqual(ocr.normalize_result("BAŞARILI"), "PASS")
        self.assertEqual(ocr.normalize_result("PASSED"), "PASS")
        self.assertEqual(ocr.normalize_result("BAŞARISIZ"), "FAIL")
        self.assertEqual(ocr.normalize_result("FAILED"), "FAIL")
        self.assertIsNone(ocr.normalize_result("beklemede"))

    def test_single_a_without_sections_is_ambiguous_but_parsed(self) -> None:
        report = ocr.parse_report("A: 45,3\nB: 65,0\n")
        self.assertAlmostEqual(report.air_test.a.as_float(), 45.3)
        self.assertIsNone(report.pressure_test.a)

    def test_a_assignment_is_section_scoped(self) -> None:
        report = ocr.parse_report(
            "Hava icerik testi\n"
            "Vp: 7.6825 L\n"
            "Vpa: 7.75 L\n"
            "A: 45.3 micro/bar\n"
            "Basinc degisim testi\n"
            "Tilk: 21 C\n"
            "Tson: 20 C\n"
            "dT: 1.0 C\n"
            "Pa: 0.4 bar\n"
            "A: 45.3 micro/bar\n"
            "B: 65.0 micro/K\n"
        )

        self.assertIsNotNone(report.air_test.a)
        self.assertIsNotNone(report.pressure_test.a)
        self.assertAlmostEqual(report.air_test.a.as_float(), 45.3)
        self.assertAlmostEqual(report.pressure_test.a.as_float(), 45.3)
        self.assertAlmostEqual(report.air_test.vp.as_float(), 0.0076825)
        self.assertAlmostEqual(report.air_test.vpa.as_float(), 0.00775)
        self.assertAlmostEqual(report.pressure_test.delta_t.as_float(), 1.0)
        self.assertAlmostEqual(report.pressure_test.pa.as_float(), 0.4)
        self.assertAlmostEqual(report.pressure_test.b.as_float(), 65.0)

    def test_section_heading_variants_scope_a_fields(self) -> None:
        variants = (
            ("Hava İçerik Testi", "Basınç Değişimi Testi"),
            ("2. Hava İçerik Testi", "3. Basınç Değişim Testi"),
            ("AIR CONTENT TEST", "PRESSURE VARIATION TEST"),
            ("Hava Testi", "Pressure Test"),
        )
        for air_heading, pressure_heading in variants:
            with self.subTest(air=air_heading, pressure=pressure_heading):
                report = ocr.parse_report(
                    f"{air_heading}\nA: 45,3\n{pressure_heading}\nA: 45,3\nB: 65,0\n"
                )
                self.assertIsNotNone(report.air_test.a)
                self.assertIsNotNone(report.pressure_test.a)

    def test_second_a_in_air_section_does_not_leak_to_pressure(self) -> None:
        report = ocr.parse_report("HAVA ICERIK TESTI\nA: 45,3\nA: 45,3\nBASINC TESTI\nB: 65,0\n")
        self.assertIsNotNone(report.air_test.a)
        self.assertIsNone(report.pressure_test.a)


class CompareWithCalculatedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.report = ocr.parse_report(TURKISH_REPORT)

    def test_all_fields_match(self) -> None:
        discrepancies = ocr.compare_with_calculated(self.report, MATCHING_CALCULATED)
        self.assertEqual(len(discrepancies), 14)
        blocking = [item for item in discrepancies if item.is_blocking]
        self.assertEqual(blocking, [])
        self.assertTrue(all(item.status == ocr.STATUS_MATCH for item in discrepancies))

    def test_within_tolerance_is_not_blocking(self) -> None:
        calculated = json.loads(json.dumps(MATCHING_CALCULATED))
        calculated["test_pressure_bar"] = 80.04
        calculated["pressure_test"]["t_initial_c"] = 21.4

        discrepancies = ocr.compare_with_calculated(self.report, calculated)
        pressure = next(item for item in discrepancies if item.field == "test_pressure_bar")
        temperature = next(
            item for item in discrepancies if item.field == "pressure_test.t_initial"
        )

        self.assertEqual(pressure.status, ocr.STATUS_WITHIN_TOLERANCE)
        self.assertEqual(temperature.status, ocr.STATUS_WITHIN_TOLERANCE)
        self.assertFalse(pressure.is_blocking)
        self.assertFalse(temperature.is_blocking)

    def test_outside_tolerance_is_critical(self) -> None:
        calculated = json.loads(json.dumps(MATCHING_CALCULATED))
        calculated["test_pressure_bar"] = 80.2

        discrepancies = ocr.compare_with_calculated(self.report, calculated)
        pressure = next(item for item in discrepancies if item.field == "test_pressure_bar")

        self.assertEqual(pressure.status, ocr.STATUS_MISMATCH)
        self.assertEqual(pressure.severity, "critical")
        self.assertTrue(pressure.is_blocking)
        self.assertAlmostEqual(pressure.delta, -0.2)

    def test_vpa_relative_tolerance(self) -> None:
        calculated = json.loads(json.dumps(MATCHING_CALCULATED))
        calculated["air_test"]["vpa_m3"] = 0.00778

        discrepancies = ocr.compare_with_calculated(self.report, calculated)
        vpa = next(item for item in discrepancies if item.field == "air_test.vpa")
        self.assertEqual(vpa.status, ocr.STATUS_WITHIN_TOLERANCE)

        calculated["air_test"]["vpa_m3"] = 0.0082
        discrepancies = ocr.compare_with_calculated(self.report, calculated)
        vpa = next(item for item in discrepancies if item.field == "air_test.vpa")
        self.assertEqual(vpa.status, ocr.STATUS_MISMATCH)

    def test_missing_field_in_report(self) -> None:
        report = ocr.parse_report(
            "Dış Çap: 406,4 mm\nEt Kalınlığı: 8,74 mm\nUzunluk: 1000 m\n"
            "Test Basıncı: 80 bar\nSonuç: PASS\n"
        )
        discrepancies = ocr.compare_with_calculated(report, MATCHING_CALCULATED)
        pa = next(item for item in discrepancies if item.field == "pressure_test.pa")
        self.assertEqual(pa.status, ocr.STATUS_MISSING_IN_REPORT)
        self.assertTrue(pa.is_blocking)
        self.assertIsNone(pa.reported)

    def test_missing_calculated_field_is_informational(self) -> None:
        calculated = dict(MATCHING_CALCULATED)
        calculated.pop("wall_mm")

        discrepancies = ocr.compare_with_calculated(self.report, calculated)
        wall = next(item for item in discrepancies if item.field == "wall_mm")
        self.assertEqual(wall.status, ocr.STATUS_MISSING_IN_CALCULATION)
        self.assertEqual(wall.severity, "info")
        self.assertFalse(wall.is_blocking)

    def test_result_mismatch_is_critical(self) -> None:
        calculated = json.loads(json.dumps(MATCHING_CALCULATED))
        calculated["result"] = "FAIL"

        discrepancies = ocr.compare_with_calculated(self.report, calculated)
        result = next(item for item in discrepancies if item.field == "result")
        self.assertEqual(result.status, ocr.STATUS_MISMATCH)
        self.assertEqual(result.severity, "critical")
        self.assertTrue(result.is_blocking)

    def test_invalid_calculated_payload(self) -> None:
        with self.assertRaises(ocr.ReportOcrError) as context:
            ocr.compare_with_calculated(self.report, ["not", "a", "dict"])  # type: ignore[arg-type]
        self.assertEqual(context.exception.code, ocr.ERROR_INVALID_CALCULATED)


class InputValidationTests(unittest.TestCase):
    def test_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(ocr.ReportOcrError) as context:
                ocr.extract_text(Path(tmp_dir) / "yok.pdf")
        self.assertEqual(context.exception.code, ocr.ERROR_FILE_NOT_FOUND)

    def test_unsupported_extension(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "rapor.txt"
            path.write_text("Rapor No: R-1", encoding="utf-8")
            with self.assertRaises(ocr.ReportOcrError) as context:
                ocr.extract_text(path)
        self.assertEqual(context.exception.code, ocr.ERROR_UNSUPPORTED_FORMAT)

    def test_empty_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "bos.pdf"
            path.touch()
            with self.assertRaises(ocr.ReportOcrError) as context:
                ocr.extract_text(path)
        self.assertEqual(context.exception.code, ocr.ERROR_EMPTY_FILE)

    def test_oversized_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "buyuk.pdf"
            with path.open("wb") as handle:
                handle.truncate(ocr.MAX_FILE_SIZE_BYTES + 1)
            with self.assertRaises(ocr.ReportOcrError) as context:
                ocr.extract_text(path)
        self.assertEqual(context.exception.code, ocr.ERROR_FILE_TOO_LARGE)

    def test_directory_is_not_a_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(ocr.ReportOcrError) as context:
                ocr.extract_text(Path(tmp_dir))
        self.assertEqual(context.exception.code, ocr.ERROR_INVALID_PATH)

    @unittest.skipUnless(
        HAVE_PIL and HAVE_PYTESSERACT, "Pillow/pytesseract yok: gorsel testi atlandi"
    )
    def test_corrupt_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "bozuk.png"
            path.write_bytes(b"bu bir png degil")
            with self.assertRaises(ocr.ReportOcrError) as context:
                ocr.extract_text(path)
        self.assertEqual(context.exception.code, ocr.ERROR_CORRUPT_IMAGE)


class OcrAvailabilityTests(unittest.TestCase):
    def test_ocr_status_is_descriptive(self) -> None:
        self.assertIn("OCR", ocr.ocr_status())

    @unittest.skipUnless(
        HAVE_PYTESSERACT and HAVE_PIL, "pytesseract/Pillow yok: OCR entegrasyonu atlandi"
    )
    def test_ocr_availability_reports_boolean(self) -> None:
        self.assertIsInstance(ocr.ocr_available(), bool)

    @unittest.skipIf(ocr.ocr_available(), "Tesseract kurulu: gercek OCR cagrisi testte yapilmaz")
    @unittest.skipUnless(HAVE_PIL and HAVE_PYTESSERACT, "pytesseract/Pillow yok: test atlandi")
    def test_missing_tesseract_binary_is_reported(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "tarama.png"
            Image.new("L", (200, 100), color=255).save(path)
            with self.assertRaises(ocr.ReportOcrError) as context:
                ocr.extract_text(path)
        self.assertIn(context.exception.code, {ocr.ERROR_OCR_UNAVAILABLE, ocr.ERROR_EMPTY_TEXT})

    @unittest.skipUnless(
        HAVE_PIL and HAVE_PYTESSERACT, "pytesseract/Pillow yok: gorsel testi atlandi"
    )
    def test_image_pipeline_with_patched_tesseract(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "tarama.png"
            Image.new("L", (400, 200), color=255).save(path)
            with (
                mock.patch.object(
                    ocr,
                    "_resolve_ocr_engine",
                    return_value="tesseract",
                ),
                mock.patch.object(
                    ocr,
                    "_run_tesseract",
                    return_value=("Report No: R-77\nTest Pressure: 80 bar\n", 0.9, ""),
                ),
            ):
                pages = ocr.extract_text(path)

        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].source, ocr.TEXT_SOURCE_OCR)
        self.assertIn("R-77", pages[0].text)

    @unittest.skipUnless(
        HAVE_PIL and HAVE_PYTESSERACT, "Pillow/pytesseract yok: gorsel OCR testi atlandi"
    )
    def test_image_validation_and_missing_engine_distinguished(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp_dir:
            corrupt = Path(tmp_dir) / "bozuk.png"
            corrupt.write_bytes(b"gecersiz")
            valid = Path(tmp_dir) / "gecerli.png"
            Image.new("L", (200, 100), color=255).save(valid)

            with mock.patch.object(ocr, "_resolve_ocr_engine", return_value=""):
                with self.assertRaises(ocr.ReportOcrError) as corrupt_ctx:
                    ocr.extract_text(corrupt)
                self.assertEqual(corrupt_ctx.exception.code, ocr.ERROR_CORRUPT_IMAGE)

                with self.assertRaises(ocr.ReportOcrError) as unavail_ctx:
                    ocr.extract_text(valid)
                self.assertEqual(unavail_ctx.exception.code, ocr.ERROR_OCR_UNAVAILABLE)


@unittest.skipUnless(HAVE_PYPDF and HAVE_REPORTLAB, "pypdf/reportlab yok: PDF testleri atlandi")
class PdfPipelineTests(unittest.TestCase):
    def test_pdf_text_layer_is_extracted_and_parsed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "rapor.pdf"
            _write_text_pdf(path, ENGLISH_REPORT.splitlines())

            pages = ocr.extract_text(path)
            self.assertEqual(len(pages), 1)
            self.assertEqual(pages[0].source, ocr.TEXT_SOURCE_LAYER)
            self.assertIn("HYDROSTATIC TEST REPORT", pages[0].text)

            result = ocr.analyze_report(path, MATCHING_CALCULATED)
            self.assertEqual(result.source, "pdf-text-layer")
            self.assertAlmostEqual(result.report.pipe_od_mm.as_float(), 406.4)
            self.assertAlmostEqual(result.report.pressure_test.pa.as_float(), 0.4)
            self.assertFalse(result.has_discrepancies)
            self.assertGreater(result.confidence, 0.7)

    def test_pdf_section_scoped_a_fields(self) -> None:
        lines = [
            "HYDROSTATIC TEST REPORT",
            "Outside Diameter: 16 in",
            "Wall Thickness: 8.74 mm",
            "Length: 1000 m",
            "Test Pressure: 80 bar",
            "Hava icerik testi",
            "Vp: 7.6825 L",
            "Vpa: 7.75 L",
            "A: 45.3 micro/bar",
            "Basinc degisim testi",
            "Tilk: 21 C",
            "Tson: 20 C",
            "dT: 1.0 C",
            "Pa: 0.4 bar",
            "A: 45.3 micro/bar",
            "B: 65.0 micro/K",
            "Result: PASS",
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "iki-bolum.pdf"
            _write_text_pdf(path, lines)
            result = ocr.analyze_report(path)

        self.assertIsNotNone(result.report.air_test.a)
        self.assertIsNotNone(result.report.pressure_test.a)
        self.assertAlmostEqual(result.report.air_test.a.as_float(), 45.3)
        self.assertAlmostEqual(result.report.pressure_test.a.as_float(), 45.3)
        self.assertAlmostEqual(result.report.pressure_test.pa.as_float(), 0.4)
        self.assertAlmostEqual(result.report.pressure_test.b.as_float(), 65.0)

    def test_blank_pdf_without_ocr_backend_raises_empty_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "bos.pdf"
            _write_blank_pdf(path)
            with (
                mock.patch.object(ocr, "_ocr_prerequisites_available", return_value=True),
                mock.patch.object(
                    ocr,
                    "_ocr_pdf_pages",
                    side_effect=ocr.ReportOcrError("OCR backend yok", ocr.ERROR_OCR_UNAVAILABLE),
                ),
            ):
                with self.assertRaises(ocr.ReportOcrError) as context:
                    ocr.extract_text(path)
        self.assertEqual(context.exception.code, ocr.ERROR_EMPTY_TEXT)

    def test_encrypted_pdf_is_rejected(self) -> None:
        from pypdf import PdfWriter

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "sifreli.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=612, height=792)
            writer.encrypt(user_password="secret", owner_password="secret")
            writer.write(str(path))

            with self.assertRaises(ocr.ReportOcrError) as context:
                ocr.extract_text(path)
        self.assertEqual(context.exception.code, ocr.ERROR_ENCRYPTED_PDF)

    def test_analyze_missing_required_fields_still_returns_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "kismi.pdf"
            _write_text_pdf(path, ["Report No: R-5", "Test Pressure: 80 bar"])
            result = ocr.analyze_report(path)

        self.assertEqual(result.report.report_no.value, "R-5")
        self.assertTrue(result.report.missing_required_fields())
        self.assertTrue(result.needs_human_review)

    @unittest.skipUnless(
        HAVE_PYMUPDF and HAVE_REPORTLAB, "PyMuPDF/reportlab yok: gorsel sira testi atlandi"
    )
    def test_pdf_visual_row_ordering_preserves_out_of_order_columns(self) -> None:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "out_of_order_cols.pdf"
            pdf = canvas.Canvas(str(path), pagesize=A4)
            # Draw right/middle columns BEFORE left time column at identical y coordinates
            pdf.drawString(160, 760, "105.800 22.0 15.950")
            pdf.drawString(160, 740, "105.750 21.0 15.803")
            pdf.drawString(50, 760, "12:10")
            pdf.drawString(50, 740, "13:10")
            pdf.showPage()
            pdf.save()

            pages = ocr.extract_text(path)
            self.assertEqual(len(pages), 1)
            lines = [ln.strip() for ln in pages[0].text.splitlines() if ln.strip()]
            self.assertTrue(
                any(ln.startswith("12:10") and "105.800" in ln for ln in lines),
                f"Beklenen gorsel satir siralama bulunamadi: {lines}",
            )
            self.assertTrue(
                any(ln.startswith("13:10") and "105.750" in ln for ln in lines),
                f"Beklenen ikinci gorsel satir bulunamadi: {lines}",
            )

    @staticmethod
    def _write_image_only_pdf(path: Path, text: str = "HIDROSTATIK TEST\n80 BAR") -> None:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", (1000, 360), "white")
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.load_default(size=42)
        except TypeError:  # pragma: no cover
            font = ImageFont.load_default()
        draw.text((60, 100), text, fill="black", font=font)
        img.save(path, "PDF", resolution=200.0)

    @unittest.skipUnless(
        HAVE_PIL and HAVE_PYPDFIUM2, "Pillow/pypdfium2 yok: rasterizer testi atlandi"
    )
    def test_pypdfium2_rasterizer_renders_scanned_and_rotated_pdf(self) -> None:
        real_find_spec = importlib.util.find_spec

        def hide_fitz(name: str, *args: object, **kwargs: object) -> object:
            if name == "fitz":
                return None
            return real_find_spec(name, *args, **kwargs)  # type: ignore[arg-type]

        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_path = Path(tmp_dir) / "scan.pdf"
            self._write_image_only_pdf(pdf_path)

            with mock.patch.object(ocr.importlib.util, "find_spec", side_effect=hide_fitz):
                avail, engine = ocr.pdf_rasterizer_status()
                self.assertTrue(avail)
                self.assertEqual(engine, "pypdfium2")

                upright = list(ocr._iter_rendered_pdf_pages(pdf_path, max_pages=1, dpi=150))
                rotated = list(
                    ocr._iter_rendered_pdf_pages(pdf_path, max_pages=1, dpi=150, rotate_deg=270)
                )
                self.assertEqual(len(upright), 1)
                self.assertEqual(len(rotated), 1)
                self.assertGreater(upright[0].width, upright[0].height)
                self.assertGreater(rotated[0].height, rotated[0].width)

                if ocr.ocr_available():
                    extracted = ocr.extract_text(pdf_path)
                    self.assertEqual(extracted[0].source, ocr.TEXT_SOURCE_OCR)
                    self.assertIn("80", extracted[0].text)

    @unittest.skipUnless(
        HAVE_QUARTZ and HAVE_PIL and ocr.ocr_available(),
        "macOS Quartz/OCR hazir degil: Quartz rasterizer testi atlandi",
    )
    def test_macos_quartz_fallback_rasterizer_extracts_scanned_pdf(self) -> None:
        real_find_spec = importlib.util.find_spec

        def hide_fitz_and_pdfium(name: str, *args: object, **kwargs: object) -> object:
            if name in {"fitz", "pypdfium2"}:
                return None
            return real_find_spec(name, *args, **kwargs)  # type: ignore[arg-type]

        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_path = Path(tmp_dir) / "quartz_scan.pdf"
            self._write_image_only_pdf(pdf_path, "TEST BASINCI: 80 BAR")

            with mock.patch.object(
                ocr.importlib.util, "find_spec", side_effect=hide_fitz_and_pdfium
            ):
                avail, engine = ocr.pdf_rasterizer_status()
                self.assertTrue(avail)
                self.assertEqual(engine, "macOS Quartz")
                extracted = ocr.extract_text(pdf_path)

            self.assertEqual(len(extracted), 1)
            self.assertEqual(extracted[0].source, ocr.TEXT_SOURCE_OCR)
            self.assertIn("80", extracted[0].text)

    def test_resolve_bundled_tesseract_cmd_when_frozen_windows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir) / "HydroWeb"
            tess_dir = base / "tesseract"
            tessdata_dir = tess_dir / "tessdata"
            tessdata_dir.mkdir(parents=True)
            fake_exe = tess_dir / "tesseract.exe"
            fake_exe.write_bytes(b"MZ")

            fake_pytess = types.SimpleNamespace(
                pytesseract=types.SimpleNamespace(tesseract_cmd="tesseract")
            )
            env_patch = {
                k: v
                for k, v in os.environ.items()
                if k not in {"HYDRO_TESSERACT_CMD", "TESSDATA_PREFIX"}
            }
            with (
                mock.patch.dict(os.environ, env_patch, clear=True),
                mock.patch.object(sys, "platform", "win32"),
                mock.patch.object(sys, "frozen", True, create=True),
                mock.patch.object(sys, "_MEIPASS", str(base / "_internal"), create=True),
                mock.patch.object(sys, "executable", str(base / "HydroWeb.exe")),
            ):
                resolved = ocr._resolve_tesseract_cmd()
                self.assertEqual(resolved, fake_exe.resolve())
                ocr._configure_pytesseract(fake_pytess)
                self.assertEqual(fake_pytess.pytesseract.tesseract_cmd, str(fake_exe.resolve()))
                self.assertEqual(os.environ.get("TESSDATA_PREFIX"), str(tessdata_dir.resolve()))


@unittest.skipUnless(HAVE_PYPDF and HAVE_REPORTLAB, "pypdf/reportlab yok: CLI testleri atlandi")
class CliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp_dir = tempfile.TemporaryDirectory()
        cls.tmp_path = Path(cls._tmp_dir.name)
        cls.pdf_path = cls.tmp_path / "rapor.pdf"
        _write_text_pdf(cls.pdf_path, ENGLISH_REPORT.splitlines())
        cls.calculated_path = cls.tmp_path / "calculated.json"
        cls.calculated_path.write_text(
            json.dumps(MATCHING_CALCULATED, ensure_ascii=False), encoding="utf-8"
        )
        cls.mismatch_path = cls.tmp_path / "mismatch.json"
        mismatched = json.loads(json.dumps(MATCHING_CALCULATED))
        mismatched["test_pressure_bar"] = 90.0
        cls.mismatch_path.write_text(json.dumps(mismatched), encoding="utf-8")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp_dir.cleanup()

    def _run(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI_PATH), *arguments],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

    def test_json_output_success(self) -> None:
        completed = self._run(str(self.pdf_path), "--json")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["source"], "pdf-text-layer")
        self.assertEqual(payload["report"]["result"]["value"], "PASS")

    def test_calculated_match_returns_zero(self) -> None:
        completed = self._run(
            str(self.pdf_path), "--json", "--calculated", str(self.calculated_path)
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["exit_code"], 0)
        self.assertFalse(
            [item for item in payload["discrepancies"] if item["status"] == "mismatch"]
        )

    def test_calculated_mismatch_returns_one(self) -> None:
        completed = self._run(str(self.pdf_path), "--json", "--calculated", str(self.mismatch_path))
        self.assertEqual(completed.returncode, 1, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["exit_code"], 1)
        pressure = next(
            item for item in payload["discrepancies"] if item["field"] == "test_pressure_bar"
        )
        self.assertEqual(pressure["status"], "mismatch")

    def test_missing_input_returns_two(self) -> None:
        completed = self._run(str(self.tmp_path / "yok.pdf"), "--json")
        self.assertEqual(completed.returncode, 2)
        payload = json.loads(completed.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "file_not_found")

    def test_invalid_calculated_json_returns_two(self) -> None:
        broken = self.tmp_path / "bozuk.json"
        broken.write_text("{bozuk", encoding="utf-8")
        completed = self._run(str(self.pdf_path), "--calculated", str(broken))
        self.assertEqual(completed.returncode, 2)
        self.assertIn("Hata", completed.stderr)

    def test_human_readable_output(self) -> None:
        completed = self._run(str(self.pdf_path))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Hidrostatik Test Raporu OCR Analizi", completed.stdout)
        self.assertIn("Insan onayi", completed.stdout)


class CliOutsidePdfDependencyTests(unittest.TestCase):
    def test_missing_input_returns_two_without_pdf_dependencies(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(CLI_PATH),
                str(PROJECT_ROOT / "olmayan-rapor.pdf"),
                "--json",
            ],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["error"]["code"], "file_not_found")


class RealFormOcrFixtureTests(unittest.TestCase):
    """Gerçek ERCİŞ formlarından alınan OCR satırlarıyla kalibrasyon testleri.

    Metinler macOS Vision çıktısının etiket/değer eşlemesinden sonraki
    halidir; sayı ve etiket biçimi sahayla birebir aynıdır.
    """

    AIR_PAGE = """HAVA IÇERIK TESTI KABUL RAPORU
Test Bölüm No : BÖLÜM 5
Tarih : 05.10.2026
Test Bölüm Boyu : 8.802,34
m
Test Bölüm acmi : 823,66
1.Başlık Yeri : 25+404
Boru Dış Çapı : 355,60
mm
Boru İç Çapı : 345,20
2.Başlık Yeri : 34+203
mm
Boru Et Kalınlığı : 5,20
mm
Vp : 0,0625
Vpa : 0,0640
Test Bölümünün Geometrik Hacmi : 823,66
Ölçülen Basınç Değişimi : 1,00
Boru Iç Yarıçapı : 172,60
Boru Et Kalınlığı : 5,20
Suyun İzotermal Sıkışabilirlik Katsayısı : 45,106
[Katsayı, Dikişsiz Borular İçin 1, Kaynaklı Borular için 1,02 : 1,02
(Vpa/Vp)-1 = : 0,023
Testin Kabul edilebilmesi için (Vpa/Vp)-1 değeri 0,06'ya eşit yada ondan düşük olmalıdır.
(Vpa/Vp) -1 değeri 0,06'dan küçük olduğu için test kabul edilmiştir.
BOT-FRM-CDB-001-023
"""

    PRESSURE_PAGE = """BASINÇ TESTI KABUL RAPORU
Test Bölüm No : BÖLÜM 5
Tarih : 07.10.2026
Test Bölüm Boyu : 8.802,34
1.Başlık Yeri : 25+404
Boru Dış Çapı : 355,60
2.Başlık Yeri : 34+203
Boru İç Çapı : 345,20
Boru Et Kalınlığı : 5,20
Ölçülen Basınç Değişimi : 0,400
PA : 0,435
Testin Başı ve Sonunda su su sıcaklığında oluşan değişim : 0,200
Su ve Çeliğin Isıl Genleşme Katsayıları Arasındaki Fark : 161,497
A : 44,892
Boru Iç Yarıçapı : 172,6
Boru Et Kalınlığı : 5,20
PL : 0,300
(PA-AP) = : -0,035
TEST KABUL EDİLMİŞTİR.
BOT-FRM-CDB-001-024
"""

    def test_air_form_values(self) -> None:
        report = ocr.parse_report(self.AIR_PAGE)

        self.assertEqual(report.section_id.value, "BÖLÜM 5")
        self.assertEqual(report.start_kp.value, "25+404")
        self.assertEqual(report.end_kp.value, "34+203")
        self.assertAlmostEqual(report.length_m.as_float(), 8802.34)
        self.assertAlmostEqual(report.pipe_od_mm.as_float(), 355.60)
        self.assertAlmostEqual(report.pipe_id_mm.as_float(), 345.20)
        self.assertAlmostEqual(report.wall_mm.as_float(), 5.20)
        self.assertAlmostEqual(report.section_volume_m3.as_float(), 823.66)
        self.assertAlmostEqual(report.air_test.vp.as_float(), 0.0625)
        self.assertAlmostEqual(report.air_test.vpa.as_float(), 0.0640)
        self.assertAlmostEqual(report.air_test.vt.as_float(), 823.66)
        self.assertAlmostEqual(report.air_test.k.as_float(), 1.02)
        self.assertAlmostEqual(report.air_test.ratio.as_float(), 0.023)
        self.assertAlmostEqual(report.air_test.a.as_float(), 45.106)
        self.assertEqual(report.result.value, "PASS")
        # Hava formundaki "Ölçülen Basınç Değişimi" PA'ya yazılmamalı.
        self.assertIsNone(report.pressure_test.pa)

    def test_pressure_form_values(self) -> None:
        report = ocr.parse_report(self.PRESSURE_PAGE)

        self.assertEqual(report.start_kp.value, "25+404")
        self.assertEqual(report.end_kp.value, "34+203")
        self.assertAlmostEqual(report.pressure_test.pa.as_float(), 0.400)
        self.assertAlmostEqual(report.pressure_test.p_delta.as_float(), 0.435)
        self.assertAlmostEqual(report.pressure_test.delta_t.as_float(), 0.200)
        self.assertAlmostEqual(report.pressure_test.b.as_float(), 161.497)
        self.assertAlmostEqual(report.pressure_test.a.as_float(), 44.892)
        self.assertAlmostEqual(report.pressure_test.pl.as_float(), 0.300)
        self.assertEqual(report.result.value, "PASS")

    def test_formula_lines_do_not_leak_values(self) -> None:
        text = "\n".join(
            [
                "HAVA İÇERİK TESTİ",
                "Vp = ( 0.884 x (ri/S) +A) x 10(-6) x V,x K",
                "Vp : 0,0625",
            ]
        )
        report = ocr.parse_report(text)
        self.assertAlmostEqual(report.air_test.vp.as_float(), 0.0625)


class VisionBlockPairingTests(unittest.TestCase):
    """Vision bbox'larından etiket/değer eşlemesi (satır/kolon mantığı)."""

    def test_label_pairs_with_same_row_value_not_adjacent_row(self) -> None:
        blocks = [
            ("Boru İç Çapı", 1.0, [0.185, 0.6872, 0.074, 0.0122]),
            ("345,20", 1.0, [0.390, 0.6890, 0.039, 0.0087]),
            ("Boru Et Kalınlığı", 1.0, [0.185, 0.6773, 0.099, 0.0087]),
            ("5,20", 1.0, [0.390, 0.6773, 0.027, 0.0087]),
            ("mm", 0.5, [0.458, 0.6875, 0.023, 0.0087]),
            ("mm", 0.5, [0.458, 0.6977, 0.023, 0.0102]),
        ]
        text = ocr._vision_blocks_to_text(blocks)
        report = ocr.parse_report(text)
        self.assertAlmostEqual(report.pipe_id_mm.as_float(), 345.20)
        self.assertAlmostEqual(report.wall_mm.as_float(), 5.20)

    def test_column_pair_does_not_steal_right_column_value(self) -> None:
        blocks = [
            ("Test Bölüm No", 1.0, [0.183, 0.7355, 0.088, 0.0087]),
            ("BÖLÜM 5", 1.0, [0.390, 0.7364, 0.056, 0.0097]),
            ("Tarih", 1.0, [0.595, 0.7369, 0.035, 0.0073]),
            ("05.10.2026", 1.0, [0.801, 0.7369, 0.064, 0.0073]),
        ]
        report = ocr.parse_report(ocr._vision_blocks_to_text(blocks))
        self.assertEqual(report.section_id.value, "BÖLÜM 5")
        self.assertEqual(report.date.value, "2026-10-05")

    def test_unit_blocks_are_never_values(self) -> None:
        blocks = [
            ("Boru Dış Çapı", 1.0, [0.185, 0.6986, 0.080, 0.0111]),
            ("mm", 0.5, [0.458, 0.6977, 0.023, 0.0102]),
            ("355,60", 1.0, [0.390, 0.7006, 0.041, 0.0087]),
        ]
        report = ocr.parse_report(ocr._vision_blocks_to_text(blocks))
        self.assertAlmostEqual(report.pipe_od_mm.as_float(), 355.60)

    def test_alphanumeric_and_reverse_section_ids_pair_and_fallback(self) -> None:
        blocks = [
            ("Test Bölüm No", 1.0, [0.186, 0.7382, 0.088, 0.009]),
            ("BÖLÜM 3B", 1.0, [0.394, 0.7382, 0.063, 0.010]),
        ]
        report = ocr.parse_report(ocr._vision_blocks_to_text(blocks))
        self.assertEqual(report.section_id.value, "BÖLÜM 3B")

        report_rev = ocr.parse_report("Test Bölüm No\n14.bölüm\n")
        self.assertEqual(report_rev.section_id.value, "BÖLÜM 14")

        report_dash = ocr.parse_report("BÖLÜM 11-A\nTest Bölüm No : :\n")
        self.assertEqual(report_dash.section_id.value, "BÖLÜM 11-A")

        report_prose = ocr.parse_report("BÖLÜM 5 Basınç Testi\nTest Bölüm No : :\n")
        self.assertEqual(report_prose.section_id.value, "BÖLÜM 5")

    def test_truncated_second_head_location_maps_to_end_kp(self) -> None:
        text = (
            "1.Başlık No : TB-01\n"
            "1.Başlık Yeri : 25+404\n"
            "2.Başlık No : TB-02\n"
            ".Başlık Yeri : 34+203\n"
        )
        report = ocr.parse_report(text)
        self.assertEqual(report.start_kp.value, "25+404")
        self.assertEqual(report.end_kp.value, "34+203")

    def test_punctuation_only_blocks_are_rejected_as_values(self) -> None:
        self.assertFalse(ocr._looks_like_value(":"))
        self.assertFalse(ocr._looks_like_value(": :"))
        self.assertFalse(ocr._looks_like_value(".. .."))
        self.assertTrue(ocr._looks_like_value("BÖLÜM 11-A"))
        self.assertTrue(ocr._looks_like_value("14.bölüm"))


class SpreadsheetExtractionTests(unittest.TestCase):
    """Excel (.xlsx / .xls) test raporu okuma ve alan cikarimi testleri."""

    def test_xlsx_multi_sheet_extraction_and_comparison(self) -> None:
        import datetime as dt

        import openpyxl

        wb = openpyxl.Workbook()
        ws1 = wb.active
        ws1.title = "hydrostatic test data"
        ws1.append(["HİDROSTATİK TEST VERİLERİ"])
        ws1.append(["Test Bölüm No", ":", "BÖLÜM 5", "Tarih", ":", dt.date(2026, 10, 5)])
        ws1.append(["1.Başlık Yeri", ":", "25+404", "2.Başlık Yeri", ":", "34+203"])
        # Sol sutun etiketi birim tasisa da degeri bossa sag sutun (355.6) m'ye cevrilmemeli
        ws1.append(["Test Bölüm Boyu (m)", ":", "", "Boru Dış Çapı", ":", 355.6])
        ws1.append(["Boru Et Kalınlığı", ":", "5,2 mm"])
        ws1.append(["Test Bölüm Boyu", ":", 8802.34, "m"])
        ws1.append(["Maximum İşletme Basıncı(Bar)", ":", 75.0])
        ws1.append(["Maks. Test Basıncı", ":", "131,68 bar"])
        ws1.append(["Operatör", ":", "A Yılmaz"])
        ws1.append(["Hata Hücresi", ":", "#DIV/0!"])
        ws1.append(["............"])

        ws2 = wb.create_sheet("acceptance air test report")
        ws2.append(["HAVA İÇERİK TESTİ KABUL RAPORU"])
        ws2.append(["Vp (L)", "=", 62.5])
        ws2.append(
            ["VpA", "=", "Basıncı 1 Bar Değiştirmek İçin Kullanılan Su Miktarı", "(m³) =", 0.0640]
        )
        ws2.append(
            ["K", "=", "Katsayı,Dikişsiz Borular İçin 1,Kaynaklı Borular İçin 1,02", "-", 1.02]
        )
        ws2.append(["A", "=", "Suyun İzotermal Sıkıştırılabilirlik Katsayısı", "(1/Bar) =", 45.106])

        ws3 = wb.create_sheet("leak test acceptance report")
        ws3.append(["BASINÇ TESTİ KABUL RAPORU"])
        ws3.append(["Tilk", ":", 20.0, "°C", "Tson", ":", 20.2, "°C"])
        ws3.append(["PA", "=", "Ölçülen Basınç Değişimi", 0.400, "(Bar)"])
        ws3.append(
            ["T", "=", "Testin Başı ve Sonunda su sıcaklığında oluşan değişim", 0.200, "(°C)"]
        )
        ws3.append(
            ["B", "=", "Su ve Çeliğin Isıl Genleşme Katsayıları Arasındaki Fark", 161.497, "(1/K)"]
        )
        ws3.append(["A", "=", "Suyun İzotermal Sıkıştırılabilirlik Katsayısı", 44.892, "(1/Bar)"])
        ws3.append(["PL", "=", "Test Boyunca İzin Verilebilir Basınç Değişimi", 0.300, "(Bar)"])
        ws3.append(["4.Sonuç:", "KABUL"])
        ws3.append(["5.Açıklamalar", ":", "Sızıntı görülmedi"])

        # Grafik sayfasi (iter_rows yok) atlanabilmeli
        wb.create_chartsheet("Grafik")

        with tempfile.TemporaryDirectory() as td:
            xlsx_path = Path(td) / "rapor.xlsx"
            wb.save(xlsx_path)

            calculated = {
                "pipe_od_mm": 355.6,
                "wall_mm": 5.2,
                "length_m": 8802.34,
                "test_pressure_bar": 131.68,
                "air_test": {"vp_m3": 0.0625, "vpa_m3": 0.0640, "a_micro_per_bar": 45.106},
                "pressure_test": {
                    "t_initial_c": 20.0,
                    "t_final_c": 20.2,
                    "delta_t_c": 0.200,
                    "pa_bar": 0.400,
                    "a_micro_per_bar": 44.892,
                    "b_micro_per_c": 161.497,
                },
                "result": "PASS",
            }
            result = ocr.analyze_report(xlsx_path, calculated=calculated)
            self.assertEqual(result.source, "spreadsheet")
            self.assertGreaterEqual(result.confidence, 0.9)
            self.assertFalse(any("OCR kullanildi" in w for w in result.warnings))
            self.assertGreater(len(result.discrepancies), 0)
            self.assertFalse(ocr.has_blocking_discrepancies(result.discrepancies))
            self.assertTrue(all(d.status == "match" for d in result.discrepancies))

            rep = result.report
            self.assertEqual(rep.section_id.value, "BÖLÜM 5")
            self.assertEqual(rep.date.value, "2026-10-05")
            self.assertEqual(rep.start_kp.value, "25+404")
            self.assertEqual(rep.end_kp.value, "34+203")
            self.assertAlmostEqual(rep.pipe_od_mm.as_float(), 355.6)
            self.assertAlmostEqual(rep.wall_mm.as_float(), 5.2)
            self.assertAlmostEqual(rep.length_m.as_float(), 8802.34)
            self.assertAlmostEqual(rep.max_operating_pressure_bar.as_float(), 75.0)
            self.assertAlmostEqual(rep.test_pressure_bar.as_float(), 131.68)
            self.assertEqual(rep.operator.value, "A Yılmaz")
            self.assertAlmostEqual(rep.air_test.vp.as_float(), 0.0625)
            self.assertAlmostEqual(rep.air_test.vpa.as_float(), 0.0640)
            self.assertAlmostEqual(rep.air_test.k.as_float(), 1.02)
            self.assertAlmostEqual(rep.air_test.a.as_float(), 45.106)
            self.assertAlmostEqual(rep.pressure_test.t_initial.as_float(), 20.0)
            self.assertAlmostEqual(rep.pressure_test.t_final.as_float(), 20.2)
            self.assertAlmostEqual(rep.pressure_test.pa.as_float(), 0.400)
            self.assertAlmostEqual(rep.pressure_test.delta_t.as_float(), 0.200)
            self.assertAlmostEqual(rep.pressure_test.a.as_float(), 44.892)
            self.assertAlmostEqual(rep.pressure_test.b.as_float(), 161.497)
            self.assertAlmostEqual(rep.pressure_test.pl.as_float(), 0.300)
            self.assertEqual(rep.result.value, "PASS")
            self.assertEqual(rep.notes.value, "Sızıntı görülmedi")

    def test_xlsx_zip_bomb_stream_cap_and_empty_workbook(self) -> None:
        from unittest import mock

        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Test Bölüm No", ":", "BÖLÜM 5"])
        wb_empty = openpyxl.Workbook()

        with tempfile.TemporaryDirectory() as td:
            xlsx_path = Path(td) / "rapor.xlsx"
            empty_path = Path(td) / "bos.xlsx"
            wb.save(xlsx_path)
            wb_empty.save(empty_path)

            with mock.patch.object(ocr, "_XLSX_MAX_UNCOMPRESSED_BYTES", 128):
                with self.assertRaises(ocr.ReportOcrError) as ctx:
                    ocr.extract_text(xlsx_path)
                self.assertEqual(ctx.exception.code, ocr.ERROR_CORRUPT_DOCUMENT)

            with self.assertRaises(ocr.ReportOcrError) as empty_ctx:
                ocr.extract_text(empty_path)
            self.assertEqual(empty_ctx.exception.code, ocr.ERROR_EMPTY_TEXT)

    def test_portable_xls_extraction_and_ole2_validation(self) -> None:
        import datetime as dt
        import types
        from unittest import mock

        with tempfile.TemporaryDirectory() as td:
            bad_xls = Path(td) / "bozuk.xls"
            bad_xls.write_bytes(b"not an ole2 file")
            with self.assertRaises(ocr.ReportOcrError) as bad_ctx:
                ocr.extract_text(bad_xls)
            self.assertEqual(bad_ctx.exception.code, ocr.ERROR_CORRUPT_DOCUMENT)

            valid_header_xls = Path(td) / "rapor.xls"
            valid_header_xls.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 32)

            rows = [
                [
                    (1, "Test Bölüm No"),
                    (1, ":"),
                    (1, "BÖLÜM 7"),
                    (1, "Tarih"),
                    (1, ":"),
                    (3, 46341.0),
                ],
                [(1, "Boru Dış Çapı"), (1, ":"), (2, 406.4), (1, "mm")],
                [(1, "Hata"), (5, 0x07)],
                [(1, "Test Tarihi"), (1, ":"), (1, "15 Kasım 2026")],
            ]

            class _FakeSheet:
                name = "hydrostatic test data"
                nrows = len(rows)
                ncols = 6

                def cell_type(self, r: int, c: int) -> int:
                    return rows[r][c][0] if c < len(rows[r]) else 0

                def cell_value(self, r: int, c: int) -> object:
                    return rows[r][c][1] if c < len(rows[r]) else ""

            class _FakeWorkbook:
                nsheets = 1
                datemode = 0
                released = False

                def sheet_by_index(self, _idx: int) -> _FakeSheet:
                    return _FakeSheet()

                def release_resources(self) -> None:
                    self.released = True

            fake_wb = _FakeWorkbook()
            fake_xlrd = types.SimpleNamespace(
                XL_CELL_EMPTY=0,
                XL_CELL_TEXT=1,
                XL_CELL_NUMBER=2,
                XL_CELL_DATE=3,
                XL_CELL_BOOLEAN=4,
                XL_CELL_ERROR=5,
                XL_CELL_BLANK=6,
                open_workbook=lambda *_args, **_kwargs: fake_wb,
                xldate_as_datetime=lambda *_args: dt.datetime(2026, 11, 15),
            )

            with (
                mock.patch.object(ocr.importlib.util, "find_spec", return_value=object()),
                mock.patch.object(ocr.importlib, "import_module", return_value=fake_xlrd),
            ):
                result = ocr.analyze_report(valid_header_xls)
            self.assertTrue(fake_wb.released)
            self.assertEqual(result.source, "spreadsheet")
            self.assertEqual(result.report.section_id.value, "BÖLÜM 7")
            self.assertAlmostEqual(result.report.pipe_od_mm.as_float(), 406.4)
            self.assertEqual(result.report.date.value, "2026-11-15")

    def test_vision_value_helpers_turkish_and_redos_safe(self) -> None:
        import time

        self.assertFalse(ocr._looks_like_value("5.Açıklamalar"))
        self.assertTrue(ocr._looks_like_value("14.KESİM"))
        self.assertEqual(
            ocr._find_section_id([ocr.PageText(1, "14.kesim\n")]).value,
            "KESİM 14",
        )
        t0 = time.monotonic()
        self.assertFalse(ocr._looks_like_value("AB 1" + "*" * 24 + "!"))
        self.assertLess(time.monotonic() - t0, 0.1)

    def test_non_workbook_zip_rejected_as_corrupt_xlsx(self) -> None:
        import zipfile

        with tempfile.TemporaryDirectory() as td:
            fake_xlsx = Path(td) / "sahte.xlsx"
            with zipfile.ZipFile(fake_xlsx, "w") as zf:
                zf.writestr("hello.txt", "not a workbook")

            with self.assertRaises(ocr.ReportOcrError) as ctx:
                ocr.extract_text(fake_xlsx)
            self.assertEqual(ctx.exception.code, ocr.ERROR_CORRUPT_DOCUMENT)

    def test_real_botas_xls_templates_parse_without_error(self) -> None:
        xls_files = sorted(Path("/Users/macbook/Documents/Kodlama/HYDRO").glob("BOT-FRM-*.xls"))
        if not xls_files:
            self.skipTest("BOTAS .xls şablonları klasörde yok.")
        for xls_path in xls_files:
            pages = ocr.extract_text(xls_path)
            self.assertGreater(len(pages), 0, xls_path.name)
            self.assertTrue(all(p.source == "spreadsheet" for p in pages))
            rep = ocr.parse_report(pages)
            self.assertIsNone(rep.air_test.vp, xls_path.name)

    def test_windows_ocr_word_clustering_and_multi_column_pairing(self) -> None:
        lines_words = [
            [
                ("Boru", 40, 20, 42, 14),
                ("Dış", 88, 20, 28, 14),
                ("Çapı", 122, 20, 40, 14),
                ("406,4", 260, 20, 46, 14),
                ("Test", 560, 20, 38, 14),
                ("Basıncı", 604, 20, 66, 14),
                ("80", 780, 20, 24, 14),
            ],
            [
                ("Et", 40, 52, 20, 14),
                ("Kalınlığı", 66, 52, 74, 14),
                ("8,74", 260, 52, 38, 14),
            ],
        ]
        blocks = ocr._windows_ocr_words_to_vision_blocks(lines_words, img_w=1000, img_h=1000)
        self.assertEqual(
            [b[0] for b in blocks],
            ["Boru Dış Çapı", "406,4", "Test Basıncı", "80", "Et Kalınlığı", "8,74"],
        )
        self.assertGreater(blocks[0][2][1], blocks[-1][2][1])

        report = ocr.parse_report(ocr._vision_blocks_to_text(blocks))
        self.assertIsNotNone(report.pipe_od_mm)
        self.assertAlmostEqual(report.pipe_od_mm.as_float(), 406.4)
        self.assertIsNotNone(report.wall_mm)
        self.assertAlmostEqual(report.wall_mm.as_float(), 8.74)
        self.assertIsNotNone(report.test_pressure_bar)
        self.assertAlmostEqual(report.test_pressure_bar.as_float(), 80.0)

    @unittest.skipUnless(HAVE_PIL, "Pillow yok: Windows OCR boyut testi atlandi")
    def test_run_windows_ocr_downscales_and_parses_winrt_lines(self) -> None:
        from PIL import Image

        class _FakeRect:
            def __init__(self, x: float, y: float, w: float, h: float) -> None:
                self.x = x
                self.y = y
                self.width = w
                self.height = h

        class _FakeWord:
            def __init__(self, text: str, x: float, y: float, w: float, h: float) -> None:
                self.text = text
                self.bounding_rect = _FakeRect(x, y, w, h)

        class _FakeLine:
            def __init__(self, words: list[_FakeWord]) -> None:
                self.words = words

        class _FakeEngine:
            def __init__(self, tag: str) -> None:
                self.recognizer_language = types.SimpleNamespace(language_tag=tag)

            async def recognize_async(self, bitmap: Any) -> Any:
                self.seen_bitmap = bitmap
                return types.SimpleNamespace(
                    text="Test Basıncı 80",
                    lines=[
                        _FakeLine(
                            [
                                _FakeWord("Test", 40, 20, 40, 14),
                                _FakeWord("Basıncı", 86, 20, 68, 14),
                                _FakeWord("80", 300, 20, 28, 14),
                            ]
                        )
                    ],
                )

        fake_engine = _FakeEngine("en-US")

        captured_png: list[bytes] = []

        class _FakeStream:
            async def write_async(self, buf: Any) -> int:
                raw = bytes(memoryview(buf)[: buf.length])
                captured_png.append(raw)
                return len(raw)

            async def flush_async(self) -> bool:
                return True

            def seek(self, _pos: int) -> None:
                return None

            def close(self) -> None:
                return None

        class _FakeBuffer:
            def __init__(self, cap: int) -> None:
                self._buf = bytearray(cap)
                self.length = 0

            def __buffer__(self, flags: int) -> memoryview:
                return memoryview(self._buf)

        class _FakeDecoder:
            async def get_software_bitmap_async(self) -> Any:
                return types.SimpleNamespace(closed=False, close=lambda: None)

        fake_ocr_mod = types.SimpleNamespace(
            OcrEngine=types.SimpleNamespace(
                max_image_dimension=4096,
                available_recognizer_languages=[types.SimpleNamespace(language_tag="en-US")],
                try_create_from_language=lambda lang: fake_engine if lang.tag == "en-US" else None,
                try_create_from_user_profile_languages=lambda: fake_engine,
            )
        )
        fake_glob_mod = types.SimpleNamespace(Language=lambda tag: types.SimpleNamespace(tag=tag))
        fake_img_mod = types.SimpleNamespace(
            BitmapDecoder=types.SimpleNamespace(
                create_async=lambda _stream: _async_val(_FakeDecoder())
            )
        )
        fake_streams_mod = types.SimpleNamespace(
            InMemoryRandomAccessStream=_FakeStream,
            Buffer=_FakeBuffer,
        )

        async def _async_val(v: Any) -> Any:
            return v

        mod_map = {
            "winrt.windows.media.ocr": fake_ocr_mod,
            "winrt.windows.globalization": fake_glob_mod,
            "winrt.windows.graphics.imaging": fake_img_mod,
            "winrt.windows.storage.streams": fake_streams_mod,
        }
        large_img = Image.new("RGB", (5000, 2500), "white")
        with mock.patch.object(ocr.importlib, "import_module", side_effect=lambda n: mod_map[n]):
            text, conf, warn = ocr._run_windows_ocr(large_img)

        self.assertEqual(len(captured_png), 1)
        import io

        with Image.open(io.BytesIO(captured_png[0])) as sent_img:
            self.assertEqual(sent_img.size, (4096, 2048))
        self.assertIn("Test Basıncı : 80", text)
        self.assertAlmostEqual(conf, 0.90)
        self.assertIn("tr-TR", warn)

    def test_probe_tesseract_handles_timeout_oserror_systemexit_and_caches(self) -> None:
        ocr.clear_ocr_probe_cache()
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                fake_tess = Path(tmp_dir) / "tesseract.exe"
                fake_tess.write_bytes(b"MZ")
                with (
                    mock.patch.object(ocr.importlib.util, "find_spec", return_value=object()),
                    mock.patch.object(ocr, "_resolve_tesseract_cmd", return_value=fake_tess),
                ):
                    for err in (
                        subprocess.TimeoutExpired(cmd="tesseract", timeout=4.0),
                        OSError("blocked by policy"),
                        SystemExit(1),
                    ):
                        ocr.clear_ocr_probe_cache()
                        with mock.patch.object(ocr.subprocess, "run", side_effect=err) as run_mock:
                            self.assertFalse(ocr._probe_tesseract()[0])
                            self.assertFalse(ocr._probe_tesseract()[0])
                            self.assertEqual(run_mock.call_count, 1)
                            kwargs = run_mock.call_args.kwargs
                            self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
                            self.assertEqual(kwargs["timeout"], ocr._TESSERACT_PROBE_TIMEOUT_S)
        finally:
            ocr.clear_ocr_probe_cache()

    def test_windows_prefers_windows_ocr_and_pypdfium2_oserror_falls_back(self) -> None:
        ocr.clear_ocr_probe_cache()
        try:
            with (
                mock.patch.object(sys, "platform", "win32"),
                mock.patch.dict(os.environ, {"HYDRO_OCR_ENGINE": "auto"}),
                mock.patch.object(ocr, "windows_ocr_available", return_value=True),
                mock.patch.object(ocr, "_tesseract_available", return_value=True) as tess_mock,
            ):
                self.assertEqual(ocr._resolve_ocr_engine(), "windows_ocr")
                self.assertEqual(tess_mock.call_count, 0)

            with (
                mock.patch.object(ocr.importlib.util, "find_spec", return_value=object()),
                mock.patch.object(
                    ocr.importlib,
                    "import_module",
                    side_effect=OSError("Blocked by AppLocker"),
                ),
            ):
                self.assertFalse(ocr._pypdfium2_usable())
        finally:
            ocr.clear_ocr_probe_cache()

    def test_result_normalization_turkish_fail_negations_and_red(self) -> None:
        self.assertEqual(ocr.normalize_result("KABUL EDİLMEMİŞTİR"), "FAIL")
        self.assertEqual(ocr.normalize_result("Kabul edilmemiş"), "FAIL")
        self.assertEqual(ocr.normalize_result("Uygun bulunmamıştır"), "FAIL")
        self.assertEqual(ocr.normalize_result("RED"), "FAIL")
        self.assertEqual(ocr.normalize_result("KABUL EDİLMİŞTİR"), "PASS")
        self.assertIsNone(ocr.normalize_result("Redüktör kontrolü yapıldı"))

    def test_analyze_report_respects_cancel_event_and_timeout_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            sample = Path(tmp_dir) / "sample.png"
            sample.write_bytes(b"\x89PNG\r\n\x1a\n")

            cancelled = threading.Event()
            cancelled.set()
            with self.assertRaises(ocr.ReportOcrError) as cancel_ctx:
                ocr.analyze_report(sample, cancel_event=cancelled)
            self.assertEqual(cancel_ctx.exception.code, ocr.ERROR_CANCELLED)

            with self.assertRaises(ocr.ReportOcrError) as timeout_ctx:
                ocr.analyze_report(sample, deadline_monotonic=0.0)
            self.assertEqual(timeout_ctx.exception.code, ocr.ERROR_TIMEOUT)

    def test_language_parameter_overrides_without_env_mutation(self) -> None:
        with mock.patch.dict(os.environ, {"HYDRO_OCR_LANG": "tur"}, clear=False):
            lang, warning = ocr._choose_tesseract_language(language="eng")
            self.assertEqual(lang, "eng")
            self.assertEqual(warning, "")
            self.assertEqual(os.environ.get("HYDRO_OCR_LANG"), "tur")
            self.assertEqual(ocr._resolve_vision_languages("eng"), ["en-US"])
            self.assertEqual(ocr._resolve_vision_languages("tur+eng"), ["tr-TR", "en-US"])


class DocumentReadingImprovementsTests(unittest.TestCase):
    def test_hybrid_pdf_ocrs_only_sparse_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_path = Path(tmp_dir) / "hybrid.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n%fake\n")

            digital_p1 = ocr.PageText(
                page_number=1,
                text="HYDROSTATIC TEST REPORT\nReport No: BOT-HYB-01\nTest Pressure: 80 bar\n",
                source=ocr.TEXT_SOURCE_LAYER,
            )
            sparse_p2 = ocr.PageText(page_number=2, text="", source=ocr.TEXT_SOURCE_LAYER)
            ocr_p2 = ocr.PageText(
                page_number=2,
                text="Basinc degisim testi\nA: 44.97 micro/bar\nB: 185.2 micro/K",
                source=ocr.TEXT_SOURCE_OCR,
                confidence=0.92,
            )

            with (
                mock.patch.object(ocr, "_extract_pdf_text", return_value=[digital_p1, sparse_p2]),
                mock.patch.object(ocr, "_ocr_prerequisites_available", return_value=True),
                mock.patch.object(ocr, "_ocr_single_pdf_page", return_value=ocr_p2) as single_mock,
            ):
                pages = ocr.extract_text(pdf_path)
                result = ocr.analyze_report(pdf_path)

            self.assertEqual(single_mock.call_count, 2)
            self.assertEqual(pages[0].source, ocr.TEXT_SOURCE_LAYER)
            self.assertEqual(pages[1].source, ocr.TEXT_SOURCE_OCR)
            self.assertEqual(result.source, "mixed")
            self.assertTrue(result.used_ocr)
            self.assertIsNotNone(result.report.pressure_test.a)
            self.assertAlmostEqual(result.report.pressure_test.a.as_float(), 44.97)

    @unittest.skipUnless(HAVE_PIL, "Pillow yok: goruntu on isleme testi atlandi")
    def test_preprocess_image_and_orientation_retry(self) -> None:
        from PIL import Image

        rgb = Image.new("RGB", (60, 40), color=(200, 200, 200))
        processed = ocr._preprocess_image_for_ocr(rgb)
        self.assertIsInstance(processed, Image.Image)
        self.assertEqual(processed.mode, "L")

        def _fake_tess(img: Any, *, language: str | None = None) -> tuple[str, float | None, str]:
            if img.size == (40, 60):
                return ("Test Basinci: 96.5 bar\nA: 44.97\nB: 185.2", 0.94, "")
            return ("", 0.1, "")

        with mock.patch.object(ocr, "_run_tesseract", side_effect=_fake_tess):
            text, conf, warn = ocr._ocr_image_with_orientation_retry(rgb, "tesseract")

        self.assertIn("96.5", text)
        self.assertAlmostEqual(conf, 0.94)
        self.assertIn("90°", warn)

    def test_pdfplumber_table_extraction_preserves_columns_without_duplication(self) -> None:
        rows = ocr._format_pdfplumber_tables(
            [
                [
                    ["A", "44.97", None],
                    ["", None],
                    ["K", "1.02"],
                ]
            ]
        )
        self.assertEqual(rows, ["A  44.97", "K  1.02"])

    def test_suggest_field_fixes_detects_decimal_drop_and_ignores_valid(self) -> None:
        report = HydrotestReport(
            air_test=AirTestFields(
                a=ExtractedField(value=4497.0),
                k=ExtractedField(value=102.0),
            ),
            pressure_test=PressureTestFields(
                t_initial=ExtractedField(value=684.0),
                t_final=ExtractedField(value=16.2),
                b=ExtractedField(value=1852.0),
            ),
        )
        fixes = ocr.suggest_field_fixes(report)
        by_field = {fix.field: fix for fix in fixes}
        self.assertEqual(
            set(by_field),
            {"air_test.a", "air_test.k", "pressure_test.t_initial", "pressure_test.b"},
        )
        self.assertAlmostEqual(by_field["air_test.a"].suggested_value, 44.97)
        self.assertAlmostEqual(by_field["air_test.k"].suggested_value, 1.02)
        self.assertAlmostEqual(by_field["pressure_test.t_initial"].suggested_value, 6.84)
        self.assertAlmostEqual(by_field["pressure_test.b"].suggested_value, 185.2)

    @unittest.skipUnless(HAVE_PIL, "Pillow yok: DPI/goruntu iyilestirme testleri atlandi")
    def test_orientation_retry_handles_180_and_dpi_escalation_improves_low_conf(self) -> None:
        from PIL import Image

        img = Image.new("L", (120, 80), color=220)

        def _fake_tess(
            target: Any, *, language: str | None = None
        ) -> tuple[str, float | None, str]:
            # Check pixel signature at corner or mock call sequence via size/rotate
            return ("", 0.2, "")

        # Verify 180 deg recovery via side_effect sequence: 0->empty, 90->empty, 270->empty, 180->full
        seq = [
            ("", 0.15, ""),
            ("", 0.15, ""),
            ("", 0.15, ""),
            ("Basinc Testi Rapor No: BOT-180\nTest Basinci: 95 bar", 0.91, ""),
        ]
        with mock.patch.object(ocr, "_run_tesseract", side_effect=seq):
            text, conf, warn = ocr._ocr_image_with_orientation_retry(img, "tesseract")
        self.assertIn("BOT-180", text)
        self.assertAlmostEqual(conf, 0.91)
        self.assertIn("180°", warn)

        # Verify 300 DPI escalation when 200 DPI returns low confidence
        hi_img = Image.new("L", (180, 120), color=220)
        with (
            mock.patch.object(
                ocr,
                "_ocr_image_with_orientation_retry",
                side_effect=[
                    ("Test Basinci: 95 bar\nA: 44.97", 0.40, ""),
                    ("Test Basinci: 95 bar\nA: 44.97\nB: 185.2", 0.93, ""),
                ],
            ),
            mock.patch.object(ocr, "_iter_rendered_pdf_pages", return_value=iter([hi_img])) as ren,
        ):
            page = ocr._ocr_pdf_page_with_dpi_escalation(Path("dummy.pdf"), 0, img, "tesseract")
        ren.assert_called_once()
        self.assertEqual(ren.call_args.kwargs.get("dpi"), 300)
        self.assertAlmostEqual(page.confidence, 0.93)
        self.assertIn("300 DPI", page.warning)

    def test_ocr_numeric_and_date_confusion_normalization(self) -> None:
        self.assertAlmostEqual(ocr.parse_number("44,9O"), 44.9)
        self.assertAlmostEqual(ocr.parse_number("1,O2"), 1.02)
        self.assertAlmostEqual(ocr.parse_number("l5.4"), 15.4)
        self.assertAlmostEqual(ocr.parse_number("B0,5 bar"), 80.5)
        self.assertAlmostEqual(ocr.parse_number("1e-6"), 1e-6)
        self.assertEqual(ocr.parse_date("15.ll.2026"), "2026-11-15")

    def test_cross_field_physics_suggested_fixes(self) -> None:
        report = HydrotestReport(
            pipe_od_mm=ExtractedField(value=406.4),
            wall_mm=ExtractedField(value=8.74),
            pipe_id_mm=ExtractedField(value=350.0),
            air_test=AirTestFields(
                vp=ExtractedField(value=10.0),
                vpa=ExtractedField(value=10.2),
                ratio=ExtractedField(value=0.2),
            ),
            pressure_test=PressureTestFields(
                t_initial=ExtractedField(value=20.0),
                t_final=ExtractedField(value=21.5),
                delta_t=ExtractedField(value=4.5),
            ),
        )
        by_field = {fix.field: fix for fix in ocr.suggest_field_fixes(report)}
        self.assertEqual(set(by_field), {"pressure_test.delta_t", "pipe_id_mm", "air_test.ratio"})
        self.assertAlmostEqual(by_field["pressure_test.delta_t"].suggested_value, -1.5)
        self.assertAlmostEqual(by_field["pipe_id_mm"].suggested_value, 388.92)
        self.assertAlmostEqual(by_field["air_test.ratio"].suggested_value, 0.02)

        dict_fixes = ocr.suggest_field_fixes_from_report_dict(report.to_dict())
        self.assertEqual(
            {item["field"] for item in dict_fixes},
            {"pressure_test.delta_t", "pipe_id_mm", "air_test.ratio"},
        )

        # Cylindrical volume cross-check suggests expected Vt on mismatch
        vol_report = HydrotestReport(
            pipe_od_mm=ExtractedField(value=1219.2),
            wall_mm=ExtractedField(value=15.9),
            length_m=ExtractedField(value=10000.0),
            section_volume_m3=ExtractedField(value=500.0),
        )
        vol_fixes = {fix.field: fix for fix in ocr.suggest_field_fixes(vol_report)}
        self.assertIn("section_volume_m3", vol_fixes)
        self.assertAlmostEqual(vol_fixes["section_volume_m3"].suggested_value, 11073.476, places=1)

    @unittest.skipUnless(HAVE_PIL, "Pillow yok: golge/egiklik testi atlandi")
    def test_shadow_flattening_and_deskew_preserve_clean_grayscale_output(self) -> None:
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (320, 220), color=(235, 235, 235))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, 160, 220], fill=(110, 110, 110))
        for y in range(25, 200, 25):
            draw.rectangle([20, y, 300, y + 6], fill=(30, 30, 30))

        flattened = ocr._normalize_uneven_lighting(img.convert("L"))
        self.assertEqual(flattened.mode, "L")
        processed = ocr._preprocess_image_for_ocr(img)
        self.assertEqual(processed.mode, "L")
        self.assertEqual(processed.size, img.size)

    def test_multiline_label_value_lookahead_extracts_next_line_value(self) -> None:
        report = ocr.parse_report(
            "\n".join(
                [
                    "Hidrostatik Test Raporu",
                    "Test Basinci:",
                    "92,5 bar",
                    "Teorik Ilave Su:",
                    "0,8893 m3",
                    "Sonuc:",
                    "BASARILI",
                ]
            )
        )
        self.assertAlmostEqual(report.test_pressure_bar.value, 92.5)
        self.assertAlmostEqual(report.air_test.vp.value, 0.8893)
        self.assertEqual(report.result.value, "PASS")

    @unittest.skipUnless(HAVE_PIL, "Pillow yok: kase/olcekleme testi atlandi")
    def test_stamp_suppression_upscale_and_preferred_angle(self) -> None:
        from PIL import Image, ImageDraw

        # Red wet stamp should brighten toward paper while dark black ink stays dark
        stamp_img = Image.new("RGB", (120, 120), color=(248, 248, 248))
        draw = ImageDraw.Draw(stamp_img)
        draw.rectangle([10, 10, 40, 40], fill=(20, 20, 20))
        draw.rectangle([60, 10, 100, 50], fill=(215, 35, 35))
        suppressed = ocr._suppress_colored_stamps(stamp_img)
        self.assertLess(suppressed.getpixel((25, 25)), 60)
        self.assertGreater(suppressed.getpixel((80, 30)), 220)

        # Small standalone scan is upscaled cleanly
        small = Image.new("RGB", (800, 600), color=(255, 255, 255))
        upscaled = ocr._upscale_small_image_for_ocr(small)
        self.assertEqual(upscaled.size, (1600, 1200))

        # preferred_angle=90 tries -90 deg first and stops immediately on strong read
        rot_probe = Image.new("L", (120, 80), color=240)
        calls: list[tuple[int, int]] = []

        def _fake_tess(im: Any, *, language: str | None = None) -> tuple[str, float | None, str]:
            calls.append(im.size)
            return ("Test Basinci: 95 bar\nA: 44.97\nB: 185.2", 0.92, "")

        with mock.patch.object(ocr, "_run_tesseract", side_effect=_fake_tess):
            text, conf, warn = ocr._ocr_image_with_orientation_retry(
                rot_probe, "tesseract", preferred_angle=90
            )
        self.assertEqual(calls, [(80, 120)])
        self.assertAlmostEqual(conf, 0.92)
        self.assertIn("90°", warn)
        self.assertIn("95 bar", text)

    def test_unit_ocr_noise_normalization_and_page_telemetry(self) -> None:
        self.assertEqual(ocr._detect_unit("rn3"), "m³")
        self.assertEqual(ocr._detect_unit("har"), "bar")
        self.assertEqual(ocr._detect_unit("b4r"), "bar")
        self.assertEqual(ocr._detect_unit("mrn"), "mm")
        self.assertEqual(ocr._detect_unit("°G"), "°C")

        if HAVE_PIL:
            import tempfile

            from PIL import Image, ImageDraw

            # Synthetic degraded scan: shaded paper + red stamp + dark ink -> clean L output
            degraded = Image.new("RGB", (360, 240), color=(238, 238, 238))
            draw = ImageDraw.Draw(degraded)
            draw.rectangle([0, 0, 180, 240], fill=(135, 135, 135))
            draw.rectangle([30, 50, 140, 80], fill=(18, 18, 18))
            draw.rectangle([200, 40, 320, 100], fill=(220, 35, 45))

            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_png = Path(tmp_dir) / "degraded_stamp.png"
                degraded.save(tmp_png, "PNG")
                loaded = ocr._load_image(tmp_png)
                self.assertEqual(loaded.mode, "L")
                self.assertEqual(loaded.size, (720, 480))

                with mock.patch.object(
                    ocr,
                    "_ocr_image_with_orientation_retry",
                    return_value=("Test Basinci: 85 bar\nA: 45,7", 0.91, ""),
                ):
                    page = ocr._ocr_pdf_page_with_dpi_escalation(tmp_png, 0, degraded, "tesseract")
                self.assertEqual(page.dpi_used, 200)
                self.assertIsNotNone(page.duration_ms)
                self.assertGreaterEqual(page.duration_ms or 0.0, 0.0)

    def test_phase1_binarization_psm6_retry_border_pipe_and_fallback(self) -> None:
        # 1) Table border pipe stripping vs interior '|' digit
        self.assertAlmostEqual(ocr.parse_number("| 12,45"), 12.45)
        self.assertAlmostEqual(ocr.parse_number("|12,45"), 12.45)
        self.assertAlmostEqual(ocr.parse_number("|45,515|"), 45.515)
        self.assertAlmostEqual(ocr.parse_number("│ 185,2 │"), 185.2)
        self.assertAlmostEqual(ocr.parse_number("1|2,5"), 112.5)

        if HAVE_PIL:
            from PIL import Image, ImageDraw

            # 2) Otsu binarization yields pure black/white 'L' pixels
            img = Image.new("L", (160, 80), color=235)
            draw = ImageDraw.Draw(img)
            draw.rectangle([20, 20, 100, 60], fill=35)
            binary = ocr._binarize_for_ocr(img)
            self.assertEqual(binary.mode, "L")
            self.assertEqual(binary.getpixel((50, 40)), 0)
            self.assertEqual(binary.getpixel((5, 5)), 255)

            # 3) Low-conf Tesseract triggers --psm 6 binarized secondary pass
            configs: list[str] = []

            def _tess_with_psm(
                target: Any, *, language: str | None = None, config: str = ""
            ) -> tuple[str, float | None, str]:
                configs.append(config)
                if config == "--psm 6":
                    return ("Test Basinci: 96,5 bar\nA: 45,12\nB: 185,4\nPa: 0,18 bar", 0.92, "")
                return ("Test Basinci: 96,5 bar\nA: 45,12\nB: 185,4", 0.48, "")

            with mock.patch.object(ocr, "_run_tesseract", side_effect=_tess_with_psm):
                txt, conf, warn = ocr._ocr_image_with_orientation_retry(img, "tesseract")
            self.assertEqual(configs, ["", "--psm 6"])
            self.assertAlmostEqual(conf, 0.92)
            self.assertIn("--psm 6", warn)
            self.assertIn("Pa: 0,18", txt)

            # 4) Cross-engine fallback: weak Vision -> Tesseract rescues page
            with (
                mock.patch.object(
                    ocr,
                    "_ocr_image_with_orientation_retry",
                    side_effect=[
                        ("", 0.10, ""),
                        ("Basinc Testi Rapor No: YEDEK-1\nTest Basinci: 92 bar", 0.89, ""),
                    ],
                ),
                mock.patch.object(ocr, "_iter_rendered_pdf_pages", return_value=iter([])),
                mock.patch.object(ocr, "_tesseract_available", return_value=True),
            ):
                fb_page = ocr._ocr_pdf_page_with_dpi_escalation(
                    Path("dummy.pdf"), 0, img, "vision"
                )
            self.assertIn("YEDEK-1", fb_page.text)
            self.assertIn("Tesseract yedek", fb_page.warning)

            # 5) Multi-page parallel Tesseract preserves page order and emits progress callbacks
            pages_img = [Image.new("L", (40, 40), color=240) for _ in range(3)]
            progress_events: list[tuple[int, int]] = []

            def _fake_page_ocr(
                _p: Path,
                idx: int,
                _im: Any,
                _eng: str,
                **_kw: Any,
            ) -> ocr.PageText:
                return ocr.PageText(
                    page_number=idx + 1,
                    text=f"Sayfa {idx + 1} icerigi",
                    source=ocr.TEXT_SOURCE_OCR,
                    confidence=0.9,
                )

            with (
                mock.patch.object(ocr, "_resolve_ocr_engine", return_value="tesseract"),
                mock.patch.object(ocr, "_iter_rendered_pdf_pages", return_value=iter(pages_img)),
                mock.patch.object(ocr, "_ocr_pdf_page_with_dpi_escalation", side_effect=_fake_page_ocr),
            ):
                out = ocr._ocr_pdf_pages(
                    Path("multi.pdf"),
                    progress_callback=lambda done, total: progress_events.append((done, total)),
                )
            self.assertEqual([p.page_number for p in out], [1, 2, 3])
            self.assertEqual(len(progress_events), 3)
            self.assertEqual(progress_events[-1], (3, 3))


if __name__ == "__main__":
    unittest.main()

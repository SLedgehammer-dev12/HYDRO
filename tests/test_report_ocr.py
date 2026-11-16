from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
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
HAVE_REPORTLAB = importlib.util.find_spec("reportlab") is not None
HAVE_PIL = importlib.util.find_spec("PIL") is not None
HAVE_PYTESSERACT = importlib.util.find_spec("pytesseract") is not None

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
            with mock.patch.object(
                ocr,
                "_resolve_ocr_engine",
                return_value="tesseract",
            ), mock.patch.object(
                ocr,
                "_run_tesseract",
                return_value=("Report No: R-77\nTest Pressure: 80 bar\n", 0.9, ""),
            ):
                pages = ocr.extract_text(path)

        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].source, ocr.TEXT_SOURCE_OCR)
        self.assertIn("R-77", pages[0].text)


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


if __name__ == "__main__":
    unittest.main()

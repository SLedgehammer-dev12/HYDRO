from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

from hidrostatik_test.services.report_export import (
    _escape_paragraph_text,
    _neutralize_excel_text,
    export_excel_report,
    export_pdf_report,
)

try:  # PDF metnini dogrulamak icin opsiyonel bagimlilik
    from pypdf import PdfReader

    HAVE_PYPDF = True
except ImportError:  # pragma: no cover
    HAVE_PYPDF = False


def _pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


class ReportExportTests(unittest.TestCase):
    def test_export_pdf_and_excel(self) -> None:
        title = "Hydrostatic Test Evaluation Report"
        metadata = {
            "Date": "2026-06-01",
            "Inspector": "John Doe",
            "Specification": "NGTL 5007 R4",
        }
        geometry = {
            "Diameter": "406.4 mm",
            "Wall Thickness": "8.74 mm",
            "Length": "1000 m",
        }
        results = {
            "Test Type": "Air Content Test",
            "Result": "PASSED",
            "Vp": "0.0078 m3",
            "Vpa": "0.0079 m3",
        }
        checklist = [
            {"checked": True, "label": "Temp checked", "ref": "10.1"},
            {"checked": False, "label": "Pressure logged", "ref": "14.2"},
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            pdf_file = tmp_path / "report.pdf"
            xlsx_file = tmp_path / "report.xlsx"

            # Export PDF
            export_pdf_report(pdf_file, title, metadata, geometry, results, checklist)
            self.assertTrue(pdf_file.exists())
            self.assertGreater(pdf_file.stat().st_size, 0)

            # Export Excel
            export_excel_report(xlsx_file, title, metadata, geometry, results, checklist)
            self.assertTrue(xlsx_file.exists())
            self.assertGreater(xlsx_file.stat().st_size, 0)

    def test_escape_paragraph_text_neutralizes_markup(self) -> None:
        escaped = _escape_paragraph_text("<b>bold</b> & =cmd")
        self.assertEqual(escaped, "&lt;b&gt;bold&lt;/b&gt; &amp; =cmd")
        self.assertEqual(_escape_paragraph_text("line1\nline2"), "line1<br/>line2")

    def test_pdf_renders_user_markup_as_literal_text(self) -> None:
        title = "=1+1 <script>alert(1)</script>"
        metadata = {"Note": "<b>bold</b> & =cmd|' /C calc'!A0"}
        geometry = {"Pipe": "Ø 406.4 mm"}
        results = {"Result": "<i>PASSED</i>", "Margin": 0.15}
        checklist = [{"checked": True, "label": "<u>Temp</u> & checked", "ref": "10.1"}]

        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_file = Path(tmp_dir) / "report.pdf"
            export_pdf_report(pdf_file, title, metadata, geometry, results, checklist)
            self.assertTrue(pdf_file.exists())
            self.assertGreater(pdf_file.stat().st_size, 0)
            # Gecici dosya birakilmadan atomik yazim yapilmali.
            leftovers = [
                path.name
                for path in Path(tmp_dir).iterdir()
                if path.name.startswith(".") and path.name.endswith(".pdf")
            ]
            self.assertEqual(leftovers, [])

            if not HAVE_PYPDF:
                self.skipTest("pypdf yok; PDF metin dogrulamasi atlandi.")

            text = _pdf_text(pdf_file)
            self.assertIn("<b>bold</b>", text)
            self.assertIn("<script>alert(1)</script>", text)
            self.assertIn("& =cmd", text)

    def test_pdf_handles_empty_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_file = Path(tmp_dir) / "empty.pdf"
            export_pdf_report(pdf_file, "Empty", {}, {}, {}, [])
            self.assertTrue(pdf_file.exists())
            self.assertGreater(pdf_file.stat().st_size, 0)
            if HAVE_PYPDF:
                text = _pdf_text(pdf_file)
                self.assertIn("Kayit yok", text)

    def test_excel_neutralizes_formula_injection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            xlsx_file = Path(tmp_dir) / "report.xlsx"
            export_excel_report(
                xlsx_file,
                "=cmd|' /C calc'!A0",
                {
                    "Note": "=cmd|' /C calc'!A0",
                    "Inspector": "+Ali",
                    "Company": "@evil",
                    "Delta": "-12",
                    "Html": "<b>Ali</b> & Co",
                    "Count": 42,
                    "Ratio": 0.5,
                },
                {},
                {},
                [{"checked": True, "label": '=HYPERLINK("http://x")', "ref": "10.1"}],
            )

            workbook = load_workbook(str(xlsx_file))
            worksheet = workbook.active
            all_cells = [cell for row in worksheet.iter_rows() for cell in row]
            cells = {cell.value: cell for cell in all_cells if cell.value is not None}

            self.assertEqual(cells["'=cmd|' /C calc'!A0"].data_type, "s")
            self.assertIn("'=cmd|' /C calc'!A0", cells)
            self.assertIn("'+Ali", cells)
            self.assertIn("'@evil", cells)
            self.assertIn("'-12", cells)
            self.assertIn("<b>Ali</b> & Co", cells)
            self.assertEqual(cells[42].value, 42)
            self.assertEqual(cells[42].data_type, "n")
            self.assertEqual(cells[0.5].value, 0.5)
            self.assertEqual(cells[0.5].data_type, "n")
            self.assertIn('\'=HYPERLINK("http://x") (10.1)', cells)

            formula_cells = [cell for cell in all_cells if getattr(cell, "data_type", None) == "f"]
            self.assertEqual(formula_cells, [])

    def test_neutralize_excel_text_only_prefixes_dangerous_values(self) -> None:
        self.assertEqual(_neutralize_excel_text("=cmd"), "'=cmd")
        self.assertEqual(_neutralize_excel_text("+1"), "'+1")
        self.assertEqual(_neutralize_excel_text("-1"), "'-1")
        self.assertEqual(_neutralize_excel_text("@ref"), "'@ref")
        self.assertEqual(_neutralize_excel_text("normal"), "normal")
        self.assertEqual(_neutralize_excel_text("<b>bold</b>"), "<b>bold</b>")


if __name__ == "__main__":
    unittest.main()

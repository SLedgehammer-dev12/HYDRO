from __future__ import annotations

import unittest
from pathlib import Path
import tempfile

from hidrostatik_test.services.report_export import export_excel_report, export_pdf_report


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


if __name__ == "__main__":
    unittest.main()

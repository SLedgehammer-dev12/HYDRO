from __future__ import annotations

import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from hidrostatik_test.domain.report_schema import (
    AirTestFields,
    ExtractedField,
    HydrotestReport,
    ValidationIssue,
)
from hidrostatik_test.services.report_ocr import (
    Discrepancy,
    OcrAnalysisResult,
    ReportOcrError,
)
from hidrostatik_test.ui.report_ocr_dialog import (
    CRITICAL_CONFIDENCE_THRESHOLD,
    LOW_CONFIDENCE_THRESHOLD,
    ReportOcrDialog,
)

CALCULATED_PAYLOAD = {
    "pipe_od_mm": 406.4,
    "wall_mm": 8.74,
    "length_m": 1000.0,
    "test_pressure_bar": 80.0,
    "result": "PASS",
}


def _build_result() -> OcrAnalysisResult:
    report = HydrotestReport(
        report_no=ExtractedField("RPR-2026-001", "", 0.96, "RPR-2026-001"),
        pipe_od_mm=ExtractedField(406.4, "mm", 0.92, "406,4 mm"),
        wall_mm=ExtractedField(8.74, "mm", 0.55, "8,74 mm"),
        length_m=ExtractedField(1000.0, "m", 0.35, "1.000 m"),
        test_pressure_bar=ExtractedField(80.0, "bar", 0.9, "80 bar"),
        air_test=AirTestFields(
            vp=ExtractedField(0.0076, "m³", 0.72, "0,0076 m³"),
        ),
        result=ExtractedField("PASS", "", 0.9, "Kabul"),
    )
    discrepancies = (
        Discrepancy(
            field="test_pressure_bar",
            label="Test basinci",
            reported=80.0,
            calculated=90.0,
            unit="bar",
            delta=-10.0,
            tolerance="±0.05 bar",
            status="mismatch",
            severity="critical",
            message="Test basinci uyusmuyor: rapor 80, hesaplanan 90 bar.",
        ),
        Discrepancy(
            field="pipe_od_mm",
            label="Dis cap",
            reported=406.4,
            calculated=406.4,
            unit="mm",
            delta=0.0,
            tolerance="±0.5 mm",
            status="match",
            severity="info",
            message="Dis cap uyusuyor.",
        ),
        Discrepancy(
            field="wall_mm",
            label="Et kalinligi",
            reported=8.74,
            calculated=None,
            unit="mm",
            delta=None,
            tolerance="±0.1 mm",
            status="missing_in_calculation",
            severity="warning",
            message="Et kalinligi icin hesaplanan deger verilmedi.",
        ),
    )
    issues = (
        ValidationIssue(
            field="wall_mm",
            code="low_confidence",
            message="Et kalinligi dusuk guvenle okundu (%55); insan onayi gerekli.",
            severity="warning",
        ),
    )
    return OcrAnalysisResult(
        path="/tmp/saha_raporu.pdf",
        source="pdf-text-layer",
        page_count=2,
        character_count=1234,
        confidence=0.75,
        report=report,
        discrepancies=discrepancies,
        issues=issues,
        warnings=(
            "Raporda taninabilir alan bulunamadi.",
            "Et kalinligi dusuk guvenle okundu; insan onayi gerekli.",
        ),
        needs_human_review=True,
    )


class FakeThread:
    instances: list[FakeThread] = []

    def __init__(
        self,
        *,
        target: object,
        args: tuple[object, ...],
        name: str = "",
        daemon: bool = False,
    ) -> None:
        self.target = target
        self.args = args
        self.name = name
        self.daemon = daemon
        self.started = False
        FakeThread.instances.append(self)

    def start(self) -> None:
        self.started = True


class ReportOcrDialogTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk kullanilamiyor, OCR diyalog testi atlandi: {exc}")
        self.root.withdraw()
        self.dialog = ReportOcrDialog(
            self.root,
            calculated_payload=CALCULATED_PAYLOAD,
        )
        self.result = _build_result()

    def tearDown(self) -> None:
        self.dialog._close_dialog()
        self.root.destroy()

    def test_apply_result_populates_summary_and_review_banner(self) -> None:
        self.dialog._apply_result(self.result)

        summary = self.dialog.summary_vars
        self.assertEqual(summary["file"].get(), self.result.path)
        self.assertEqual(summary["source"].get(), "PDF metin katmani")
        self.assertEqual(summary["pages"].get(), "2")
        self.assertEqual(summary["characters"].get(), "1234")
        self.assertEqual(summary["confidence"].get(), "75%")
        self.assertIn("EVET", summary["needs_review"].get())
        self.assertIn("1 engelleyici", summary["discrepancies"].get())
        self.assertEqual(self.dialog.review_banner.cget("bg"), "#FDEAEA")
        self.assertEqual(str(self.dialog.save_json_button.cget("state")), "normal")
        self.assertIn("Analiz tamamlandi", self.dialog.analysis_status_var.get())

    def test_fields_tree_shows_values_and_confidence_tags(self) -> None:
        self.dialog._apply_result(self.result)

        rows = self.dialog.fields_tree.get_children()
        self.assertEqual(len(rows), 7)

        wall_values = self.dialog.fields_tree.item("wall_mm")["values"]
        self.assertEqual(wall_values[0], "Et kalinligi")
        self.assertEqual(wall_values[1], "8.74")
        self.assertEqual(wall_values[2], "mm")
        self.assertEqual(wall_values[3], "0.55")
        self.assertEqual(wall_values[4], "8,74 mm")
        self.assertIn("low_confidence", self.dialog.fields_tree.item("wall_mm")["tags"])

        self.assertIn("critical_confidence", self.dialog.fields_tree.item("length_m")["tags"])
        self.assertEqual(self.dialog.fields_tree.item("pipe_od_mm")["tags"], "")
        self.assertLess(
            CRITICAL_CONFIDENCE_THRESHOLD,
            LOW_CONFIDENCE_THRESHOLD,
        )

    def test_discrepancies_tree_marks_blocking_and_warning_rows(self) -> None:
        self.dialog._apply_result(self.result)

        rows = self.dialog.discrepancies_tree.get_children()
        self.assertEqual(len(rows), 3)

        blocking_values = self.dialog.discrepancies_tree.item("0")["values"]
        self.assertEqual(blocking_values[0], "Test basinci")
        self.assertEqual(blocking_values[1], 80)
        self.assertEqual(blocking_values[2], 90)
        self.assertEqual(blocking_values[3], -10)
        self.assertEqual(blocking_values[5], "Uyusmuyor")
        self.assertIn("blocking", self.dialog.discrepancies_tree.item("0")["tags"])

        self.assertEqual(self.dialog.discrepancies_tree.item("1")["tags"], "")
        self.assertIn("warning", self.dialog.discrepancies_tree.item("2")["tags"])
        self.assertEqual(self.dialog.discrepancies_tree.item("2")["values"][5], "Hesap yok")

    def test_warnings_text_contains_warnings_and_issues(self) -> None:
        self.dialog._apply_result(self.result)

        content = self.dialog.warnings_text.get("1.0", "end")

        self.assertIn("Raporda taninabilir alan bulunamadi.", content)
        self.assertIn("low_confidence", content)
        self.assertIn("Et kalinligi dusuk guvenle okundu", content)
        self.assertIn("resmi kabul raporu degildir", content)

    def test_save_json_writes_result_dict(self) -> None:
        self.dialog._apply_result(self.result)
        target = Path(tempfile.mkdtemp()) / "kontrol.json"

        with (
            patch(
                "hidrostatik_test.ui.report_ocr_dialog.filedialog.asksaveasfilename",
                return_value=str(target),
            ) as ask,
            patch("hidrostatik_test.ui.report_ocr_dialog.messagebox.showinfo") as showinfo,
            patch("hidrostatik_test.ui.report_ocr_dialog.messagebox.showerror") as showerror,
        ):
            self.dialog._save_json()

        self.assertTrue(target.exists())
        saved = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(saved["path"], self.result.path)
        self.assertEqual(saved["source"], "pdf-text-layer")
        self.assertEqual(len(saved["discrepancies"]), 3)
        self.assertEqual(saved["report"]["pipe_od_mm"]["value"], 406.4)
        ask.assert_called_once()
        showinfo.assert_called_once()
        showerror.assert_not_called()
        self.assertEqual(self.dialog.analysis_status_var.get(), "JSON kaydedildi.")

    def test_save_json_cancel_does_not_write(self) -> None:
        self.dialog._apply_result(self.result)

        with (
            patch(
                "hidrostatik_test.ui.report_ocr_dialog.filedialog.asksaveasfilename",
                return_value="",
            ),
            patch("hidrostatik_test.ui.report_ocr_dialog.messagebox.showinfo") as showinfo,
        ):
            self.dialog._save_json()

        showinfo.assert_not_called()

    def test_save_json_without_result_warns_and_does_not_open_dialog(self) -> None:
        with (
            patch("hidrostatik_test.ui.report_ocr_dialog.filedialog.asksaveasfilename") as ask,
            patch("hidrostatik_test.ui.report_ocr_dialog.messagebox.showwarning") as showwarning,
        ):
            self.dialog._save_json()

        ask.assert_not_called()
        showwarning.assert_called_once()
        self.assertEqual(str(self.dialog.save_json_button.cget("state")), "disabled")

    def test_report_ocr_error_is_shown_and_dialog_stays_open(self) -> None:
        error = ReportOcrError(
            "PDF sifreli; sifre girilmeden rapor okunamaz.",
            "encrypted_pdf",
            detail="reader.is_encrypted=True",
        )

        with patch("hidrostatik_test.ui.report_ocr_dialog.messagebox.showerror") as showerror:
            self.dialog._apply_error(error)

        showerror.assert_called_once()
        message = showerror.call_args.args[1]
        self.assertIn("PDF sifreli", message)
        self.assertIn("encrypted_pdf", message)
        self.assertIn("reader.is_encrypted=True", message)
        self.assertTrue(self.dialog._dialog_exists())
        self.assertIsNone(self.dialog._result)
        self.assertIn("basarisiz", self.dialog.analysis_status_var.get())
        self.assertEqual(str(self.dialog.analysis_button.cget("state")), "normal")

    def test_worker_only_queues_and_drain_applies_result_on_main_thread(self) -> None:
        self.dialog.path_var.set("/tmp/saha_raporu.pdf")

        with patch(
            "hidrostatik_test.ui.report_ocr_dialog.analyze_report",
            return_value=self.result,
        ) as analyzer:
            self.dialog._analyzer = analyzer
            self.dialog._worker(self.dialog._generation, "/tmp/saha_raporu.pdf", None)

        self.assertEqual(self.dialog._events.qsize(), 1)
        self.assertIsNone(self.dialog._result)

        self.dialog._drain_events()

        self.assertIs(self.dialog._result, self.result)
        self.assertEqual(self.dialog._events.qsize(), 0)
        analyzer.assert_called_once_with("/tmp/saha_raporu.pdf", None)

    def test_start_analysis_disables_controls_and_passes_calculated_payload(self) -> None:
        self.dialog.path_var.set("/tmp/saha_raporu.pdf")
        FakeThread.instances.clear()

        with patch("hidrostatik_test.ui.report_ocr_dialog.threading.Thread", FakeThread):
            self.dialog._start_analysis()

        self.assertTrue(self.dialog._analysis_running)
        self.assertEqual(str(self.dialog.analysis_button.cget("state")), "disabled")
        self.assertEqual(str(self.dialog.browse_button.cget("state")), "disabled")
        self.assertIn("Analiz ediliyor", self.dialog.analysis_status_var.get())
        self.assertEqual(len(FakeThread.instances), 1)
        worker = FakeThread.instances[0]
        self.assertTrue(worker.started)
        self.assertEqual(worker.args[1], "/tmp/saha_raporu.pdf")
        self.assertEqual(worker.args[2], CALCULATED_PAYLOAD)

    def test_start_analysis_without_comparison_passes_no_payload(self) -> None:
        self.dialog.path_var.set("/tmp/saha_raporu.pdf")
        self.dialog.compare_var.set(False)
        FakeThread.instances.clear()

        with patch("hidrostatik_test.ui.report_ocr_dialog.threading.Thread", FakeThread):
            self.dialog._start_analysis()

        self.assertIsNone(FakeThread.instances[0].args[2])

    def test_start_analysis_rejects_unsupported_extension(self) -> None:
        self.dialog.path_var.set("/tmp/saha_raporu.docx")
        FakeThread.instances.clear()

        with (
            patch("hidrostatik_test.ui.report_ocr_dialog.threading.Thread") as thread_cls,
            patch("hidrostatik_test.ui.report_ocr_dialog.messagebox.showwarning") as showwarning,
        ):
            self.dialog._start_analysis()

        thread_cls.assert_not_called()
        showwarning.assert_called_once()
        self.assertFalse(self.dialog._analysis_running)

    def test_close_while_analysis_running_asks_and_ignores_late_result(self) -> None:
        self.dialog.path_var.set("/tmp/saha_raporu.pdf")
        FakeThread.instances.clear()
        with patch("hidrostatik_test.ui.report_ocr_dialog.threading.Thread", FakeThread):
            self.dialog._start_analysis()
        stale_token = self.dialog._generation

        with patch(
            "hidrostatik_test.ui.report_ocr_dialog.messagebox.askyesno",
            return_value=False,
        ) as ask:
            self.dialog._on_close()

        ask.assert_called_once()
        self.assertTrue(self.dialog._dialog_exists())
        self.assertTrue(self.dialog._analysis_running)

        with patch(
            "hidrostatik_test.ui.report_ocr_dialog.messagebox.askyesno",
            return_value=True,
        ):
            self.dialog._on_close()

        self.assertFalse(self.dialog._dialog_exists())

        # Kapanistan sonra kuyruga dusen eski sonuc yoksayilir.
        self.dialog._events.put(("result", stale_token, self.result))
        self.dialog._drain_events()
        self.assertIsNone(self.dialog._result)


if __name__ == "__main__":
    unittest.main()

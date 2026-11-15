"""End-to-end operator workflow tests.

These tests drive a real Tk application through the complete sequence:
geometry -> coefficients -> air test -> pressure test -> decision -> report
export -> session persistence. They complement the unit suites by checking the
seams between the UI, domain, services and data layers.
"""

from __future__ import annotations

import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from hidrostatik_test.domain.coefficient_manager import CoefficientState
from hidrostatik_test.domain.hydrotest_core import (
    AirContentInputs,
    evaluate_air_content_test,
)
from hidrostatik_test.domain.session_manager import SessionManager
from hidrostatik_test.services.updater import _extract_asset
from hidrostatik_test.ui.app import HydrostaticTestApp
from hidrostatik_test.ui.constants import MANUAL_A_MODE, MANUAL_B_MODE


class EndToEndWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk kullanilamiyor: {exc}")
        self.root.withdraw()
        self.app = HydrostaticTestApp(self.root)
        self.tmp = Path(tempfile.mkdtemp(prefix="hydro-e2e-"))
        self.addCleanup(self.root.destroy)

    def _fill_geometry(self) -> None:
        self.app.geometry_vars["outside_diameter_mm"].set("406.4")
        self.app.geometry_vars["wall_thickness_mm"].set("8.74")
        self.app.geometry_vars["length_m"].set("1000")

    def _prepare_air_pass(self) -> None:
        self._fill_geometry()
        self.app.air_vars["temperature_c"].set("20")
        self.app.air_vars["pressure_bar"].set("80")
        self.assertTrue(self.app._calculate_air_a(log_result=False))
        pipe = self.app._build_pipe_section("air")
        a_value = float(self.app.air_vars["a_micro_per_bar"].get())
        theoretical = evaluate_air_content_test(
            AirContentInputs(
                pipe=pipe,
                a_micro_per_bar=a_value,
                pressure_rise_bar=1.0,
                k_factor=1.02,
                actual_added_water_m3=0.0,
            )
        ).theoretical_added_water_m3
        self.app.air_vars["k_factor"].set("1.02")
        self.app.air_vars["actual_added_water_m3"].set(f"{theoretical:.9f}")

    def _prepare_pressure_pass(self) -> None:
        self.app.pressure_vars["temperature_c"].set("20")
        self.app.pressure_vars["pressure_bar"].set("80")
        self.app.pressure_vars["delta_t_c"].set("0.6")
        self.assertTrue(self.app._calculate_pressure_a(log_result=False))
        # Varsayilan B kaynagi kurum ici A/B tablosudur; B helper gerekmez.
        self.assertTrue(self.app._ensure_coefficient_ready("pressure_b"))
        pipe = self.app._build_pipe_section("pressure")
        a_value = float(self.app.pressure_vars["a_micro_per_bar"].get())
        b_value = float(self.app.pressure_vars["b_micro_per_c"].get())
        theoretical = (b_value * 0.6) / (pipe.elasticity_term + a_value)
        self.app.pressure_vars["actual_pressure_change_bar"].set(f"{theoretical + 0.1:.9f}")

    def test_full_operator_workflow_air_pressure_report(self) -> None:
        self._prepare_air_pass()
        self.app._run_air_test()
        self.assertEqual(self.app._decisions["air"]["status"], "BASARILI")

        self._prepare_pressure_pass()
        self.assertFalse(self.app.use_b_helper_var.get())
        self.assertEqual(self.app.coefficient_manager.get("pressure_b"), CoefficientState.REFERENCE)
        self.app._run_pressure_test()
        self.assertEqual(self.app._decisions["pressure"]["status"], "BASARILI")

        # Switching tabs must not erase the other test's decision.
        self.app._select_tab_by_key("air")
        self.assertEqual(self.app._decisions["pressure"]["status"], "BASARILI")
        self.app._select_tab_by_key("pressure")
        self.assertEqual(self.app._decisions["air"]["status"], "BASARILI")

        self.app._flush_pending_live_result()
        report_text = self.app._build_report_text()
        self.assertIn("Hava Icerik Testi", report_text)
        self.assertIn("Basinc Degisim Testi", report_text)
        self.assertIn("1.06", report_text)
        self.assertIn("0.3 bar", report_text)
        self.assertIn("B kaynagi: Kurum ici tablo (varsayilan)", report_text)
        self.assertIn("A/B kontrol tablosu (onarilmis hucre:", report_text)

        for suffix, signature in (("txt", b"Hidrostatik"), ("pdf", b"%PDF"), ("xlsx", b"PK")):
            target = self.tmp / f"e2e.{suffix}"
            with (
                patch(
                    "hidrostatik_test.ui.app.filedialog.asksaveasfilename",
                    return_value=str(target),
                ),
                patch("hidrostatik_test.ui.app.messagebox.showinfo"),
                patch("hidrostatik_test.ui.app.messagebox.showerror") as showerror,
            ):
                self.app._save_report()
            showerror.assert_not_called()
            self.assertTrue(target.exists(), f"{suffix} raporu olusmadi")
            self.assertTrue(target.read_bytes().startswith(signature), f"{suffix} imzasi yanlis")

    def test_negative_b_coefficient_workflow(self) -> None:
        self._fill_geometry()
        self.app.pressure_a_mode_var.set(MANUAL_A_MODE)
        self.app._on_pressure_a_mode_changed()
        self.app.pressure_b_mode_var.set(MANUAL_B_MODE)
        self.app._on_pressure_b_mode_changed()
        self.app.use_b_helper_var.set(False)
        self.app.pressure_vars["temperature_c"].set("2")
        self.app.pressure_vars["pressure_bar"].set("50")
        self.app.pressure_vars["a_micro_per_bar"].set("45")
        self.app.pressure_vars["b_micro_per_c"].set("-63.84")
        self.app.pressure_vars["delta_t_c"].set("-1.0")
        self.app.pressure_vars["actual_pressure_change_bar"].set("1.05")

        self.app._run_pressure_test()

        self.assertEqual(self.app._decisions["pressure"]["status"], "BASARILI")
        self.assertNotIn("pozitif olmalidir", self.app.banner_var.get().lower())
        self.assertIn("buzulme", self.app._build_report_text())

    def test_session_persistence_with_sqlite(self) -> None:
        sessions_dir = self.tmp / "sessions"
        db_path = self.tmp / "hydro.db"
        manager = SessionManager(sessions_dir=sessions_dir, use_db=True, db_path=db_path)
        self.addCleanup(lambda: manager._db and manager._db.close())

        first = manager.create_session("E2E-1")
        manager.update_inputs({"air.temperature_c": "20", "air.pressure_bar": "80"})
        manager.add_result({"title": "Hava Icerik Testi", "content": "BASARILI"})
        manager.add_test_entry(
            "air",
            {"temperature_c": 20.0, "pressure_bar": 80.0},
            {"passed": True},
            decision_status="BASARILI",
            decision_title="Hava Icerik Testi",
            decision_summary="E2E",
        )
        manager.add_time_series_record(80.0, 20.0, 1.0, "e2e")

        entries = manager.get_session_entries(first.id)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["decision_status"], "BASARILI")
        stats = manager.get_statistics()
        self.assertGreaterEqual(stats["total_tests"], 1)

        manager.create_session("E2E-2")
        manager.switch_session(first.id)
        restored = manager.get_active_session()
        self.assertIsNotNone(restored)
        self.assertEqual(restored.inputs["air.temperature_c"], "20")
        self.assertEqual(len(restored.results), 1)

    def test_update_asset_contract_is_strict(self) -> None:
        release = {
            "assets": [
                {
                    "name": "HidrostatikTest-v1.7.2-windows-x64.zip",
                    "browser_download_url": "https://example.com/old.zip",
                    "size": 10,
                },
                {
                    "name": "HidrostatikTest-v1.7.3-windows-x64.zip",
                    "browser_download_url": "https://example.com/new.zip",
                    "size": 20,
                },
            ]
        }
        with patch("hidrostatik_test.services.updater.sys.platform", "win32"):
            selected = _extract_asset(release, "1.7.3")
        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, "HidrostatikTest-v1.7.3-windows-x64.zip")

        with patch("hidrostatik_test.services.updater.sys.platform", "win32"):
            assert _extract_asset({"assets": release["assets"][:1]}, "1.7.3") is None


if __name__ == "__main__":
    unittest.main()

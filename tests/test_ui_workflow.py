from __future__ import annotations

import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import hidrostatik_test.ui.app as app_module
from hidrostatik_test.app_metadata import APP_VERSION, SPEC_DOCUMENT_CODE
from hidrostatik_test.data import BOTAS_REFERENCE_OPTION_LABEL, GAIL_REFERENCE_OPTION_LABEL
from hidrostatik_test.domain import BSource
from hidrostatik_test.domain.coefficient_manager import CoefficientState
from hidrostatik_test.domain.hydrotest_core import STEEL_MODELS, PipeSection, ValidationError
from hidrostatik_test.services.download_manager import DownloadManager
from hidrostatik_test.ui import constants as ui_constants
from hidrostatik_test.ui.app import HydrostaticTestApp
from hidrostatik_test.ui.constants import (
    AUTO_A_MODE,
    AUTO_B_MODE,
    B_SOURCE_AUTO_LABEL,
    B_SOURCE_GAIL_LABEL,
    B_SOURCE_INSTITUTIONAL_LABEL,
    MANUAL_A_MODE,
    MANUAL_B_MODE,
    REFERENCE_A_MODE,
    REFERENCE_B_MODE,
    REQUIRED_FIELD_HINT,
    STEEL_MODEL_LINEAR_LABEL,
    STEEL_MODEL_VOLUMETRIC_LABEL,
    TABLE_B_MODE,
)


class UiWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk kullanilamiyor: {exc}")
        self.root.withdraw()
        self.app = HydrostaticTestApp(self.root)

    def tearDown(self) -> None:
        self.root.destroy()

    def _fill_geometry(self) -> None:
        self.app.geometry_vars["outside_diameter_mm"].set("406.4")
        self.app.geometry_vars["wall_thickness_mm"].set("8.74")
        self.app.geometry_vars["length_m"].set("1000")

    def test_temperature_change_refreshes_computed_air_a_live(self) -> None:
        self.app.air_vars["temperature_c"].set("20")
        self.app.air_vars["pressure_bar"].set("80")

        self.assertTrue(self.app._calculate_air_a(log_result=False))
        self.assertEqual(self.app.coefficient_manager.get("air_a"), CoefficientState.COMPUTED)

        self.app.air_vars["temperature_c"].set("21")

        self.assertEqual(self.app.coefficient_manager.get("air_a"), CoefficientState.COMPUTED)
        self.assertEqual(
            self.app.field_message_vars["air.a_micro_per_bar"].get(), "Hazir: Hesap guncel."
        )

    def test_pressure_evaluation_prepares_default_table_b_without_helper(self) -> None:
        self._fill_geometry()
        self.assertEqual(self.app.pressure_b_source_var.get(), B_SOURCE_INSTITUTIONAL_LABEL)
        self.assertEqual(self.app.pressure_b_mode_var.get(), TABLE_B_MODE)
        self.assertEqual(self.app.pressure_b_reference_var.get(), BOTAS_REFERENCE_OPTION_LABEL)
        self.assertFalse(self.app.use_b_helper_var.get())

        self.app.pressure_vars["temperature_c"].set("20")
        self.app.pressure_vars["pressure_bar"].set("80")
        self.app.pressure_vars["delta_t_c"].set("0.6")
        self.assertTrue(self.app._calculate_pressure_a(log_result=False))
        self.assertTrue(self.app._calculate_b_helper(log_result=False))
        a_value = float(self.app.pressure_vars["a_micro_per_bar"].get())
        b_value = float(self.app.pressure_vars["b_micro_per_c"].get())
        theoretical = (b_value * 0.6) / (
            self.app._build_pipe_section("pressure").elasticity_term + a_value
        )
        self.app.pressure_vars["actual_pressure_change_bar"].set(f"{theoretical + 0.1:.9f}")

        self.app._run_pressure_test()

        self.assertEqual(self.app.decision_status_var.get(), "BASARILI")
        self.assertEqual(self.app.pressure_vars["b_micro_per_c"].get(), "188.661000")
        self.assertEqual(self.app.coefficient_manager.get("pressure_a"), CoefficientState.COMPUTED)
        self.assertEqual(self.app.coefficient_manager.get("pressure_b"), CoefficientState.REFERENCE)

    def test_air_evaluation_accepts_manual_a_mode(self) -> None:
        self._fill_geometry()
        self.app.air_a_mode_var.set(MANUAL_A_MODE)
        self.app._on_air_a_mode_changed()
        self.app.air_vars["temperature_c"].set("20")
        self.app.air_vars["pressure_bar"].set("80")
        self.app.air_vars["a_micro_per_bar"].set("45")
        self.app.air_vars["actual_added_water_m3"].set("0.0079")

        self.app._run_air_test()

        self.assertEqual(self.app.decision_status_var.get(), "BASARILI")
        self.assertEqual(self.app.coefficient_manager.get("air_a"), CoefficientState.MANUAL)
        self.assertIn("Manuel", self.app.air_a_mode_var.get())

    def test_air_manual_detail_report_marks_manual_a_source(self) -> None:
        self.app.air_a_mode_var.set(MANUAL_A_MODE)
        self.app._on_air_a_mode_changed()
        self.app.air_vars["temperature_c"].set("20")
        self.app.air_vars["pressure_bar"].set("80")
        self.app.air_vars["a_micro_per_bar"].set("45.0")

        detail = self.app.active_detail_report_var.get()

        self.assertIn("Hava Icerik Testi - Detay Raporu", detail)
        self.assertIn("A durum: Hazir: manuel giris", detail)
        self.assertIn("A kaynagi: Kullanici girdisi / manuel tablo-prosedur.", detail)
        self.assertIn("A degeri: 45.0 (10^-6/bar)", detail)

    def test_coefficient_source_badges_reflect_manual_and_computed_states(self) -> None:
        self.app.air_a_mode_var.set(MANUAL_A_MODE)
        self.app._on_air_a_mode_changed()
        self.app.air_vars["a_micro_per_bar"].set("45.0")
        self.assertEqual(self.app.coefficient_source_vars["air_a"].get(), "MANUEL")
        self.assertIn("air_a", self.app.inline_coefficient_source_badges)

        self.app.pressure_vars["temperature_c"].set("20")
        self.app.pressure_vars["pressure_bar"].set("80")
        self.assertTrue(self.app._calculate_pressure_a(log_result=False))
        self.assertEqual(self.app.coefficient_source_vars["pressure_a"].get(), "HESAP")
        self.assertIn("pressure_a", self.app.inline_coefficient_source_badges)

    def test_air_evaluation_accepts_reference_a_mode(self) -> None:
        self._fill_geometry()
        self.app.air_vars["temperature_c"].set("15")
        self.app.air_vars["pressure_bar"].set("80")
        self.app.air_a_mode_var.set(REFERENCE_A_MODE)
        self.app._on_air_a_mode_changed()
        self.app.air_a_reference_var.set(GAIL_REFERENCE_OPTION_LABEL)
        self.app._on_air_a_reference_changed()
        self.app.air_vars["actual_added_water_m3"].set("0.0079")

        self.app._run_air_test()

        self.assertEqual(self.app.decision_status_var.get(), "BASARILI")
        self.assertEqual(self.app.coefficient_manager.get("air_a"), CoefficientState.REFERENCE)
        self.assertEqual(self.app.air_vars["a_micro_per_bar"].get(), "45.518533")

    def test_reference_option_lists_include_botas_and_gail_tables(self) -> None:
        self.assertIn(BOTAS_REFERENCE_OPTION_LABEL, self.app.air_a_reference_combo["values"])
        self.assertIn(GAIL_REFERENCE_OPTION_LABEL, self.app.air_a_reference_combo["values"])
        self.assertIn(BOTAS_REFERENCE_OPTION_LABEL, self.app.pressure_a_reference_combo["values"])
        self.assertIn(GAIL_REFERENCE_OPTION_LABEL, self.app.pressure_a_reference_combo["values"])
        self.assertIn(BOTAS_REFERENCE_OPTION_LABEL, self.app.pressure_b_reference_combo["values"])
        self.assertIn(GAIL_REFERENCE_OPTION_LABEL, self.app.pressure_b_reference_combo["values"])

    def test_air_reference_mode_accepts_botas_table(self) -> None:
        self.app.air_vars["temperature_c"].set("10")
        self.app.air_vars["pressure_bar"].set("50")
        self.app.air_a_mode_var.set(REFERENCE_A_MODE)
        self.app._on_air_a_mode_changed()
        self.app.air_a_reference_var.set(BOTAS_REFERENCE_OPTION_LABEL)

        self.app._on_air_a_reference_changed()

        self.assertEqual(self.app.coefficient_manager.get("air_a"), CoefficientState.REFERENCE)
        self.assertEqual(self.app.air_vars["a_micro_per_bar"].get(), "46.775000")

    def test_air_reference_mode_accepts_gail_table(self) -> None:
        self.app.air_vars["temperature_c"].set("10")
        self.app.air_vars["pressure_bar"].set("50")
        self.app.air_a_mode_var.set(REFERENCE_A_MODE)
        self.app._on_air_a_mode_changed()
        self.app.air_a_reference_var.set(GAIL_REFERENCE_OPTION_LABEL)

        self.app._on_air_a_reference_changed()

        self.assertEqual(self.app.coefficient_manager.get("air_a"), CoefficientState.REFERENCE)
        self.assertEqual(self.app.air_vars["a_micro_per_bar"].get(), "46.824270")

    def test_pressure_b_reference_mode_accepts_botas_table_without_helper(self) -> None:
        self.app.pressure_vars["temperature_c"].set("10")
        self.app.pressure_vars["pressure_bar"].set("50")
        self.app.pressure_b_mode_var.set(REFERENCE_B_MODE)
        self.app._on_pressure_b_mode_changed()
        self.app.pressure_b_reference_var.set(BOTAS_REFERENCE_OPTION_LABEL)

        self.app._on_pressure_b_reference_changed()

        self.assertEqual(self.app.coefficient_manager.get("pressure_b"), CoefficientState.REFERENCE)
        self.assertEqual(self.app.pressure_vars["b_micro_per_c"].get(), "64.923000")
        self.assertFalse(self.app.use_b_helper_var.get())
        self.assertEqual(self.app.b_helper_vars["water_beta_micro_per_c"].get(), "")
        self.assertEqual(
            str(self.app.entry_widgets["helper.steel_alpha_micro_per_c"].cget("state")), "disabled"
        )

    def test_pressure_b_reference_mode_accepts_gail_table_without_helper(self) -> None:
        self.app.pressure_vars["temperature_c"].set("10")
        self.app.pressure_vars["pressure_bar"].set("50")
        self.app.pressure_b_mode_var.set(REFERENCE_B_MODE)
        self.app._on_pressure_b_mode_changed()
        self.app.pressure_b_reference_var.set(GAIL_REFERENCE_OPTION_LABEL)

        self.app._on_pressure_b_reference_changed()

        self.assertEqual(self.app.coefficient_manager.get("pressure_b"), CoefficientState.REFERENCE)
        self.assertEqual(self.app.pressure_vars["b_micro_per_c"].get(), "60.450000")
        self.assertFalse(self.app.use_b_helper_var.get())
        self.assertEqual(self.app.b_helper_vars["water_beta_micro_per_c"].get(), "")

    def test_b_source_selector_defaults_to_institutional_table(self) -> None:
        values = tuple(str(value) for value in self.app.pressure_b_source_combo["values"])

        self.assertEqual(
            values,
            (
                B_SOURCE_INSTITUTIONAL_LABEL,
                B_SOURCE_GAIL_LABEL,
                B_SOURCE_AUTO_LABEL,
            ),
        )
        self.assertEqual(self.app.pressure_b_source_var.get(), B_SOURCE_INSTITUTIONAL_LABEL)
        self.assertEqual(self.app.pressure_b_mode_var.get(), TABLE_B_MODE)
        self.assertEqual(self.app.pressure_b_reference_var.get(), BOTAS_REFERENCE_OPTION_LABEL)
        self.assertEqual(self.app.steel_model_var.get(), STEEL_MODEL_VOLUMETRIC_LABEL)
        self.assertFalse(self.app.use_b_helper_var.get())
        self.assertEqual(str(self.app.pressure_b_source_combo.cget("state")), "readonly")
        self.assertEqual(str(self.app.steel_model_combo.cget("state")), "disabled")

    def test_b_source_labels_match_domain_contract(self) -> None:
        self.assertEqual(
            set(ui_constants.B_SOURCE_BY_LABEL.values()),
            {source.value for source in BSource},
        )
        self.assertEqual(
            set(ui_constants.STEEL_MODEL_BY_LABEL.values()),
            set(STEEL_MODELS),
        )
        self.assertEqual(
            ui_constants.DEFAULT_STEEL_MODEL_LABEL,
            ui_constants.STEEL_MODEL_VOLUMETRIC_LABEL,
        )

    def test_b_source_switch_resolves_expected_values_and_states(self) -> None:
        self.app.pressure_vars["temperature_c"].set("10")
        self.app.pressure_vars["pressure_bar"].set("50")

        self.app.pressure_b_source_var.set(B_SOURCE_INSTITUTIONAL_LABEL)
        self.app._on_pressure_b_source_changed()

        self.assertEqual(self.app.pressure_vars["b_micro_per_c"].get(), "64.923000")
        self.assertEqual(self.app.coefficient_manager.get("pressure_b"), CoefficientState.REFERENCE)
        self.assertEqual(self.app.pressure_b_mode_var.get(), TABLE_B_MODE)
        self.assertEqual(self.app.pressure_b_reference_var.get(), BOTAS_REFERENCE_OPTION_LABEL)
        self.assertFalse(self.app.use_b_helper_var.get())

        self.app.pressure_b_source_var.set(B_SOURCE_GAIL_LABEL)
        self.app._on_pressure_b_source_changed()

        self.assertEqual(self.app.pressure_vars["b_micro_per_c"].get(), "60.450000")
        self.assertEqual(self.app.coefficient_manager.get("pressure_b"), CoefficientState.REFERENCE)
        self.assertEqual(self.app.pressure_b_reference_var.get(), GAIL_REFERENCE_OPTION_LABEL)
        self.assertFalse(self.app.use_b_helper_var.get())

        self.app.pressure_b_source_var.set(B_SOURCE_AUTO_LABEL)
        self.app._on_pressure_b_source_changed()

        self.assertEqual(self.app.pressure_vars["b_micro_per_c"].get(), "63.621631")
        self.assertEqual(self.app.coefficient_manager.get("pressure_b"), CoefficientState.COMPUTED)
        self.assertEqual(self.app.pressure_b_mode_var.get(), AUTO_B_MODE)
        self.assertTrue(self.app.use_b_helper_var.get())
        self.assertEqual(self.app.b_helper_vars["water_beta_micro_per_c"].get(), "99.621631")

        self.app.pressure_b_source_var.set(B_SOURCE_INSTITUTIONAL_LABEL)
        self.app._on_pressure_b_source_changed()

        self.assertEqual(self.app.pressure_vars["b_micro_per_c"].get(), "64.923000")
        self.assertEqual(self.app.coefficient_manager.get("pressure_b"), CoefficientState.REFERENCE)
        self.assertEqual(self.app.b_helper_vars["water_beta_micro_per_c"].get(), "")

    def test_auto_steel_model_linear_and_volumetric_differ(self) -> None:
        self.app.notebook.select(1)
        self.app._on_tab_changed()
        self.app.pressure_vars["temperature_c"].set("10")
        self.app.pressure_vars["pressure_bar"].set("50")
        self.app.pressure_b_source_var.set(B_SOURCE_AUTO_LABEL)
        self.app._on_pressure_b_source_changed()
        self.assertEqual(str(self.app.steel_model_combo.cget("state")), "readonly")

        self.app.steel_model_var.set(STEEL_MODEL_LINEAR_LABEL)
        self.app._on_steel_model_changed()

        self.assertEqual(self.app.pressure_vars["b_micro_per_c"].get(), "87.621631")
        self.assertIn("B = beta - alpha", self.app.active_detail_report_var.get())

        self.app.steel_model_var.set(STEEL_MODEL_VOLUMETRIC_LABEL)
        self.app._on_steel_model_changed()

        self.assertEqual(self.app.pressure_vars["b_micro_per_c"].get(), "63.621631")
        self.assertIn(
            "Otomatik B modeli: B = beta - 3*alpha, alpha=12.0 micro/K",
            self.app.active_detail_report_var.get(),
        )

    def test_institutional_repair_is_visible_in_detail_and_report(self) -> None:
        self.app.notebook.select(1)
        self.app._on_tab_changed()
        self.app.pressure_vars["temperature_c"].set("7")
        self.app.pressure_vars["pressure_bar"].set("90")

        self.assertTrue(self.app._calculate_b_helper(log_result=False))
        detail = self.app.active_detail_report_var.get()
        report = self.app._build_report_text()

        self.assertEqual(self.app.pressure_vars["b_micro_per_c"].get(), "32.663000")
        for text in (detail, report):
            self.assertIn("A/B kontrol tablosu (onarilmis hucre: 20)", text)
            self.assertIn("A onarilmis: ham 45.515 -> 47.115", text)
            self.assertIn(f"B kaynagi: {B_SOURCE_INSTITUTIONAL_LABEL}", text)

    def test_b_source_change_clears_previous_value_before_recompute(self) -> None:
        self.app.pressure_vars["temperature_c"].set("10")
        self.app.pressure_vars["pressure_bar"].set("50")
        self.app.pressure_b_source_var.set(B_SOURCE_INSTITUTIONAL_LABEL)
        self.app._on_pressure_b_source_changed()
        self.assertEqual(self.app.pressure_vars["b_micro_per_c"].get(), "64.923000")

        # Yeniden hesaplamayi engellemek icin sicakligi kaldir; kaynak degisimi
        # eski tablo degerini temizlemelidir.
        self.app.pressure_vars["temperature_c"].set("")
        self.app.pressure_b_source_var.set(B_SOURCE_GAIL_LABEL)
        self.app._on_pressure_b_source_changed()

        self.assertEqual(self.app.pressure_vars["b_micro_per_c"].get(), "")
        self.assertEqual(self.app.coefficient_manager.get("pressure_b"), CoefficientState.EMPTY)
        self.assertEqual(self.app.pressure_b_reference_var.get(), GAIL_REFERENCE_OPTION_LABEL)
        self.assertIn("B kaynagi:", self.app.pressure_b_source_summary_var.get())

    def test_b_source_summary_lists_three_sources_and_delta(self) -> None:
        self.app.pressure_vars["temperature_c"].set("10")
        self.app.pressure_vars["pressure_bar"].set("50")

        summary = self.app.pressure_b_source_summary_var.get()

        self.assertIn("B kaynaklari: Kurum 64.92 | GAIL 60.45 | Oto 63.62", summary)
        self.assertIn("\u0394kurum-GAIL +4.47", summary)
        self.assertIn(f"Kullanilan kaynak: {B_SOURCE_INSTITUTIONAL_LABEL}", summary)

    def test_b_source_out_of_institutional_range_warns_and_blocks_value(self) -> None:
        self.app.pressure_vars["temperature_c"].set("26")
        self.app.pressure_vars["pressure_bar"].set("50")
        self.app.pressure_b_source_var.set(B_SOURCE_INSTITUTIONAL_LABEL)
        self.app._on_pressure_b_source_changed()

        self.assertEqual(self.app.pressure_vars["b_micro_per_c"].get(), "")
        self.assertIn("aralik disi", self.app.pressure_b_source_summary_var.get())
        self.assertEqual(self.app.banner_level, "error")

    def test_material_grade_selection_populates_smys(self) -> None:
        option = next(
            option for option in self.app.material_grade_combo["values"] if "X65 / L450" in option
        )

        self.app.material_grade_var.set(option)

        self.assertEqual(self.app.section_profile_vars["smys_mpa"].get(), "450")

    def test_pump_location_requires_explicit_user_selection(self) -> None:
        self._fill_geometry()
        self.app.section_profile_vars["highest_elevation_m"].set("100")
        self.app.section_profile_vars["lowest_elevation_m"].set("0")
        self.app.section_profile_vars["start_elevation_m"].set("0")
        self.app.section_profile_vars["end_elevation_m"].set("100")
        self.app.section_profile_vars["design_pressure_bar"].set("20")
        self.app.material_grade_var.set(
            next(
                option
                for option in self.app.material_grade_combo["values"]
                if "Grade B / L245" in option
            )
        )

        self.assertEqual(self.app.pump_location_var.get(), "")
        self.assertIn(
            "Pompa konumu kullanici tarafindan", self.app.section_pressure_summary_var.get()
        )

    def test_pressure_evaluation_accepts_manual_b_mode(self) -> None:
        self._fill_geometry()
        self.app.pressure_b_mode_var.set(MANUAL_B_MODE)
        self.app._on_pressure_b_mode_changed()
        self.app.pressure_vars["temperature_c"].set("20")
        self.app.pressure_vars["pressure_bar"].set("80")
        self.app.pressure_vars["delta_t_c"].set("0.6")
        self.app.pressure_vars["actual_pressure_change_bar"].set("2.1")
        self.app.pressure_vars["b_micro_per_c"].set("200.0")

        self.app._run_pressure_test()

        self.assertEqual(self.app.decision_status_var.get(), "BASARILI")
        self.assertEqual(self.app.coefficient_manager.get("pressure_b"), CoefficientState.MANUAL)
        self.assertFalse(self.app.use_b_helper_var.get())
        self.assertEqual(self.app.b_helper_vars["water_beta_micro_per_c"].get(), "")

    def test_pressure_evaluation_accepts_reference_b_mode(self) -> None:
        self._fill_geometry()
        self.app.pressure_vars["temperature_c"].set("20")
        self.app.pressure_vars["pressure_bar"].set("100")
        self.app.pressure_b_mode_var.set(REFERENCE_B_MODE)
        self.app._on_pressure_b_mode_changed()
        self.app.pressure_b_reference_var.set(GAIL_REFERENCE_OPTION_LABEL)
        self.app._on_pressure_b_reference_changed()
        self.app.pressure_vars["delta_t_c"].set("0.6")
        self.app.pressure_vars["actual_pressure_change_bar"].set("1.9")

        self.app._run_pressure_test()

        self.assertEqual(self.app.decision_status_var.get(), "BASARILI")
        self.assertEqual(self.app.coefficient_manager.get("pressure_b"), CoefficientState.REFERENCE)
        self.assertFalse(self.app.use_b_helper_var.get())
        self.assertEqual(self.app.b_helper_vars["water_beta_micro_per_c"].get(), "")

    def test_pressure_evaluation_accepts_reference_a_mode(self) -> None:
        self._fill_geometry()
        self.app.pressure_vars["temperature_c"].set("10")
        self.app.pressure_vars["pressure_bar"].set("50")
        self.app.pressure_a_mode_var.set(REFERENCE_A_MODE)
        self.app._on_pressure_a_mode_changed()
        self.app.pressure_a_reference_var.set(BOTAS_REFERENCE_OPTION_LABEL)
        self.app._on_pressure_a_reference_changed()
        self.app.pressure_vars["delta_t_c"].set("0.6")
        self.app.pressure_vars["actual_pressure_change_bar"].set("1.9")
        self.app.pressure_b_mode_var.set(MANUAL_B_MODE)
        self.app._on_pressure_b_mode_changed()
        self.app.pressure_vars["b_micro_per_c"].set("180")

        self.app._run_pressure_test()

        self.assertEqual(self.app.decision_status_var.get(), "BASARILI")
        self.assertEqual(self.app.coefficient_manager.get("pressure_a"), CoefficientState.REFERENCE)
        self.assertEqual(self.app.pressure_vars["a_micro_per_bar"].get(), "46.775000")

    def test_pressure_manual_detail_report_shows_sources_and_decision_basis(self) -> None:
        self._fill_geometry()
        self.app.notebook.select(1)
        self.app._on_tab_changed()
        self.app.pressure_a_mode_var.set(MANUAL_A_MODE)
        self.app._on_pressure_a_mode_changed()
        self.app.pressure_b_mode_var.set(MANUAL_B_MODE)
        self.app._on_pressure_b_mode_changed()
        self.app.pressure_vars["temperature_c"].set("20")
        self.app.pressure_vars["pressure_bar"].set("80")
        self.app.pressure_vars["a_micro_per_bar"].set("45")
        self.app.pressure_vars["b_micro_per_c"].set("200")
        self.app.pressure_vars["delta_t_c"].set("0.6")
        self.app.pressure_vars["actual_pressure_change_bar"].set("2.1")

        detail = self.app.active_detail_report_var.get()

        self.assertIn("Basinc Degisim Testi - Detay Raporu", detail)
        self.assertIn("A kaynagi: Kullanici girdisi / manuel tablo-prosedur.", detail)
        self.assertIn("B kaynagi detayi: Kullanici girdisi / manuel tablo-prosedur.", detail)
        self.assertIn("B kaynagi: Manuel B", detail)
        self.assertIn("Karar kurali: (Pa - Pt) <= 0.3 bar", detail)
        self.assertIn("Anlik sonuc: BASARILI", detail)

    def test_air_control_table_summary_updates_after_a_calculation(self) -> None:
        self.app.air_vars["temperature_c"].set("10")
        self.app.air_vars["pressure_bar"].set("30")

        self.assertTrue(self.app._calculate_air_a(log_result=False))
        self.assertIn("BOTA", self.app.air_control_table_var.get())
        self.assertIn("GAIL", self.app.air_control_table_var.get())
        self.assertIn("A farki =", self.app.air_control_table_var.get())

    def test_pressure_control_table_summary_updates_after_a_and_b_calculation(self) -> None:
        self.app.pressure_vars["temperature_c"].set("15")
        self.app.pressure_vars["pressure_bar"].set("80")
        self.app.b_helper_vars["steel_alpha_micro_per_c"].set("12.0")
        self.app.use_b_helper_var.set(True)

        self.assertTrue(self.app._calculate_pressure_a(log_result=False))
        self.assertTrue(self.app._calculate_b_helper(log_result=False))
        self.assertIn("BOTA", self.app.pressure_control_table_var.get())
        self.assertIn("GAIL", self.app.pressure_control_table_var.get())
        self.assertIn("B farki =", self.app.pressure_control_table_var.get())

    def test_geometry_pressure_summary_updates_with_location_class_window(self) -> None:
        self._fill_geometry()
        self.app.notebook.select(1)
        self.app._on_tab_changed()
        self.app.section_profile_vars["highest_elevation_m"].set("100")
        self.app.section_profile_vars["lowest_elevation_m"].set("0")
        self.app.section_profile_vars["start_elevation_m"].set("0")
        self.app.section_profile_vars["end_elevation_m"].set("100")
        self.app.section_profile_vars["design_pressure_bar"].set("20")
        self.app.material_grade_var.set(
            next(
                option
                for option in self.app.material_grade_combo["values"]
                if "Grade B / L245" in option
            )
        )
        self.app.location_class_var.set("Class 1 - min 1.25 x dizayn basinci")
        self.app.pump_location_var.set("Baslangic noktasi")
        self.app.pressure_vars["pressure_bar"].set("35")

        summary = self.app.section_pressure_summary_var.get()

        self.assertIn("Grade B / L245", summary)
        self.assertIn("100% SMYS limiti", summary)
        self.assertIn("34.797844", summary)
        self.assertIn("105.378937", summary)
        self.assertIn("minimum saglandi", summary)
        self.assertIn("maksimum asilmadi", summary)

    def test_geometry_pressure_status_card_updates_with_location_class_window(self) -> None:
        self._fill_geometry()
        self.app.notebook.select(1)
        self.app._on_tab_changed()
        self.app.section_profile_vars["highest_elevation_m"].set("100")
        self.app.section_profile_vars["lowest_elevation_m"].set("0")
        self.app.section_profile_vars["start_elevation_m"].set("0")
        self.app.section_profile_vars["end_elevation_m"].set("100")
        self.app.section_profile_vars["design_pressure_bar"].set("20")
        self.app.material_grade_var.set(
            next(
                option
                for option in self.app.material_grade_combo["values"]
                if "Grade B / L245" in option
            )
        )
        self.app.location_class_var.set("Class 1 - min 1.25 x dizayn basinci")
        self.app.pump_location_var.set("Baslangic noktasi")
        self.app.pressure_vars["pressure_bar"].set("35")

        self.assertEqual(self.app.section_pressure_status_var.get(), "PENCERE ICINDE")
        self.assertIn("min 34.797844 bar", self.app.section_pressure_window_var.get())
        self.assertIn(
            "Izlenen basinc = 35.000000 bar", self.app.section_pressure_status_detail_var.get()
        )
        self.assertEqual(self.app.section_pressure_status_label.cget("bg"), "#E6F4EA")

    def test_geometry_pressure_status_reports_section_length_limit_exceedance(self) -> None:
        self.app.notebook.select(1)
        self.app._on_tab_changed()
        self.app.geometry_vars["outside_diameter_mm"].set("406.4")
        self.app.geometry_vars["wall_thickness_mm"].set("8.74")
        self.app.geometry_vars["length_m"].set("21000")
        self.app.section_profile_vars["highest_elevation_m"].set("100")
        self.app.section_profile_vars["lowest_elevation_m"].set("0")
        self.app.section_profile_vars["start_elevation_m"].set("0")
        self.app.section_profile_vars["end_elevation_m"].set("100")
        self.app.section_profile_vars["design_pressure_bar"].set("20")
        self.app.material_grade_var.set(
            next(
                option
                for option in self.app.material_grade_combo["values"]
                if "Grade B / L245" in option
            )
        )
        self.app.location_class_var.set("Class 1 - min 1.25 x dizayn basinci")
        self.app.pump_location_var.set("Baslangic noktasi")

        self.assertEqual(self.app.section_pressure_status_var.get(), "KESIT LIMIT ASIMI")
        self.assertIn("20 km limitini asiyor", self.app.section_pressure_status_detail_var.get())
        self.assertIn("Test bolumu uzunlugu", self.app.section_pressure_summary_var.get())
        self.assertEqual(self.app.section_pressure_status_label.cget("bg"), "#FFF6E5")

    def test_pressure_live_decision_updates_without_manual_run(self) -> None:
        self._fill_geometry()
        self.app.notebook.select(1)
        self.app._on_tab_changed()
        self.root.update_idletasks()
        self.app.pressure_vars["temperature_c"].set("20")
        self.app.pressure_vars["pressure_bar"].set("80")
        a_value = float(self.app.pressure_vars["a_micro_per_bar"].get())
        b_value = float(self.app.pressure_vars["b_micro_per_c"].get())
        theoretical = (b_value * 0.6) / (
            self.app._build_pipe_section("pressure").elasticity_term + a_value
        )
        self.app.pressure_vars["delta_t_c"].set("0.6")
        self.app.pressure_vars["actual_pressure_change_bar"].set(f"{theoretical + 0.1:.9f}")

        self.assertEqual(self.app.decision_title_var.get(), "Basinc Degisim Testi")
        self.assertEqual(self.app.decision_status_var.get(), "BASARILI")
        self.assertIn("Canli sonuc: Pt =", self.app.decision_summary_var.get())
        self.assertEqual(self.app.coefficient_manager.get("pressure_a"), CoefficientState.COMPUTED)
        self.assertEqual(self.app.coefficient_manager.get("pressure_b"), CoefficientState.REFERENCE)
        self.assertEqual(self.app.pressure_vars["b_micro_per_c"].get(), "188.661000")

    def test_empty_required_field_sets_feedback(self) -> None:
        self.app._run_air_test()

        self.assertIn("bos birakilamaz", self.app.section_feedback_vars["air"].get())
        self.assertEqual(self.app.decision_status_var.get(), "DOGRULANAMADI")

    def test_geometry_summary_updates_from_inputs(self) -> None:
        self._fill_geometry()

        self.assertIn("Ic cap", self.app.geometry_summary_var.get())
        self.assertIn("ic hacim Vt", self.app.geometry_summary_var.get())

    def test_workflow_checklist_updates_with_active_tab(self) -> None:
        self.assertIn("P=1.0 bar", self.app.workflow_steps_var.get())

        self.app.notebook.select(1)
        self.app._on_tab_changed()

        self.assertIn("Pa = Pilk - Pson", self.app.workflow_steps_var.get())

        self.app.notebook.select(2)
        self.app._on_tab_changed()

        self.assertIn("Pig modu", self.app.workflow_steps_var.get())

    def test_notebook_contains_field_control_tab(self) -> None:
        labels = [
            self.app.notebook.tab(index, "text") for index in range(self.app.notebook.index("end"))
        ]

        self.assertEqual(labels, ["Hava Icerik Testi", "Basinc Degisim Testi", "Saha Kontrol"])

    def test_default_water_backend_is_coolprop(self) -> None:
        self.assertEqual(self.app.water_backend_var.get(), "CoolProp EOS [coolprop]")
        self.assertIn("Secili backend: CoolProp EOS", self.app.water_backend_summary_var.get())

    def test_backend_change_recalculates_auto_coefficients(self) -> None:
        self.app.air_vars["temperature_c"].set("12.3")
        self.app.air_vars["pressure_bar"].set("57.7")
        self.app._calculate_air_a(log_result=False)

        self.app.water_backend_var.set("Table Interpolation v1 [table_v1]")
        self.app._on_water_backend_changed()

        self.assertEqual(self.app.coefficient_manager.get("air_a"), CoefficientState.COMPUTED)
        self.assertEqual(self.app.air_vars["a_micro_per_bar"].get(), "46.586510")

    def test_check_summary_counts_checked_controls(self) -> None:
        self.app.control_check_vars["ambient_temp"].set(True)
        self.app.control_check_vars["thermal_balance"].set(True)

        self.assertIn("2 / 11", self.app.check_summary_var.get())
        self.assertEqual(self.app.check_progress_var.get(), 2.0)

    def test_pig_speed_calculation_updates_status_and_outputs(self) -> None:
        self.app.notebook.select(2)
        self.app.field_vars["pig_distance_m"].set("1000")
        self.app.field_vars["pig_travel_time_min"].set("8")

        self.assertTrue(self.app._calculate_pig_speed(log_result=False))
        self.assertEqual(self.app.pig_status_var.get(), "Pig hizi durumu: UYGUN")
        self.assertEqual(self.app.field_vars["pig_speed_m_per_s"].get(), "2.083333")

    def test_clear_field_form_resets_controls_and_pig_values(self) -> None:
        self.app.notebook.select(2)
        self.app.control_check_vars["ambient_temp"].set(True)
        self.app.field_vars["pig_distance_m"].set("1200")
        self.app.field_vars["pig_travel_time_min"].set("9")
        self.app._calculate_pig_speed(log_result=False)

        self.app._clear_active_form()

        self.assertFalse(self.app.control_check_vars["ambient_temp"].get())
        self.assertEqual(self.app.field_vars["pig_distance_m"].get(), "")
        self.assertEqual(self.app.field_vars["pig_speed_m_per_s"].get(), "")
        self.assertIn("0 / 11", self.app.check_summary_var.get())

    def test_catalog_selection_populates_geometry_fields(self) -> None:
        size_label = next(
            option
            for option in self.app.pipe_size_combo.cget("values")
            if option.startswith("NPS 16 ")
        )
        self.app.geometry_catalog_vars["size_option"].set(size_label)
        self.app._on_pipe_size_selected()
        schedule_label = next(
            option for option in self.app.pipe_schedule_combo.cget("values") if "40 / XS" in option
        )
        self.app.geometry_catalog_vars["schedule_option"].set(schedule_label)

        self.app._apply_catalog_selection()

        self.assertEqual(self.app.geometry_vars["outside_diameter_mm"].get(), "406.40")
        self.assertEqual(self.app.geometry_vars["wall_thickness_mm"].get(), "12.70")

    def test_segment_addition_switches_geometry_to_segment_mode(self) -> None:
        self.app.geometry_vars["outside_diameter_mm"].set("406.4")
        self.app.geometry_vars["wall_thickness_mm"].set("8.74")
        self.app.geometry_vars["length_m"].set("500")
        self.app._add_geometry_segment()
        self.app.geometry_vars["wall_thickness_mm"].set("12.70")
        self.app._add_geometry_segment()

        geometry = self.app._build_pipe_section("air")

        self.assertIn("Segmentli geometri aktif", self.app.geometry_summary_var.get())
        self.assertEqual(len(self.app.segment_tree.get_children()), 2)
        self.assertGreater(geometry.internal_volume_m3, 0.0)

    def test_segment_addition_expands_geometry_details(self) -> None:
        self.assertFalse(self.app.geometry_details_visible_var.get())
        self.app.geometry_vars["outside_diameter_mm"].set("406.4")
        self.app.geometry_vars["wall_thickness_mm"].set("8.74")
        self.app.geometry_vars["length_m"].set("500")

        self.app._add_geometry_segment()

        self.assertTrue(self.app.geometry_details_visible_var.get())
        self.assertEqual(self.app.geometry_toggle_button.cget("text"), "Detaylari Gizle")

    def test_menu_bar_contains_expected_sections(self) -> None:
        menu = self.root.nametowidget(self.root["menu"])

        labels = [
            menu.entrycget(index, "label")
            for index in range(menu.index("end") + 1)
            if menu.type(index) == "cascade"
        ]

        self.assertEqual(labels, ["Dosya", "Hesap", "Rapor", "Guncelleme", "Hakkinda"])

    def test_ocr_report_menu_entry_and_toolbar_button_are_available(self) -> None:
        menu = self.app.report_menu
        labels = [
            menu.entrycget(index, "label")
            for index in range(menu.index("end") + 1)
            if menu.type(index) == "command"
        ]

        self.assertIn("Test Raporu Kontrol (OCR)...", labels)
        self.assertEqual(self.app.ocr_report_button.cget("text"), "Rapor Kontrol (OCR)...")
        self.assertTrue(self.app.ocr_report_button.winfo_manager())

    def _fill_ocr_calculated_inputs(self) -> None:
        self._fill_geometry()
        self.app.air_vars["a_micro_per_bar"].set("45")
        self.app.air_vars["actual_added_water_m3"].set("0.0079")
        self.app.pressure_vars["pressure_bar"].set("80")
        self.app.pressure_vars["delta_t_c"].set("0.6")
        self.app.pressure_vars["actual_pressure_change_bar"].set("0.4")
        self.app.pressure_vars["a_micro_per_bar"].set("45")
        self.app.pressure_vars["b_micro_per_c"].set("188.661")

    def test_ocr_calculated_payload_uses_geometry_tests_and_decisions(self) -> None:
        self._fill_ocr_calculated_inputs()
        self.app._update_decision_card("Hava Icerik Testi", "BASARILI", "Hava testi gecti")
        self.app._update_decision_card("Basinc Degisim Testi", "BASARILI", "Basinc testi gecti")

        payload = self.app._build_ocr_calculated_payload()

        self.assertEqual(payload["pipe_od_mm"], 406.4)
        self.assertEqual(payload["wall_mm"], 8.74)
        self.assertEqual(payload["length_m"], 1000.0)
        self.assertEqual(payload["test_pressure_bar"], 80.0)
        self.assertEqual(payload["result"], "PASS")

        air_test = payload["air_test"]
        self.assertEqual(air_test["vpa_m3"], 0.0079)
        self.assertEqual(air_test["a_micro_per_bar"], 45.0)
        pipe = self.app._build_pipe_section("air")
        expected_vp = (pipe.elasticity_term + 45.0) * 1e-6 * pipe.internal_volume_m3 * 1.0 * 1.02
        self.assertAlmostEqual(air_test["vp_m3"], expected_vp, places=12)

        pressure_test = payload["pressure_test"]
        self.assertEqual(
            pressure_test,
            {
                "delta_t_c": 0.6,
                "pa_bar": 0.4,
                "a_micro_per_bar": 45.0,
                "b_micro_per_c": 188.661,
            },
        )

    def test_ocr_calculated_payload_skips_missing_and_non_finite_values(self) -> None:
        self.assertEqual(self.app._build_ocr_calculated_payload(), {})

        self.app.geometry_vars["outside_diameter_mm"].set("nan")
        self.app.geometry_vars["wall_thickness_mm"].set("8.74")
        self.app.geometry_vars["length_m"].set("abc")
        self.app.pressure_vars["pressure_bar"].set("inf")
        self.app.pressure_vars["delta_t_c"].set("nan")
        self.app.pressure_vars["actual_pressure_change_bar"].set("inf")
        self.app.pressure_vars["a_micro_per_bar"].set("nan")
        self.app.pressure_vars["b_micro_per_c"].set("inf")
        self.app.air_vars["a_micro_per_bar"].set("nan")
        self.app.air_vars["actual_added_water_m3"].set("inf")

        payload = self.app._build_ocr_calculated_payload()

        self.assertEqual(payload, {})
        # nan/inf JSON'a sizmamali.
        self.assertEqual(json.loads(json.dumps(payload, allow_nan=False)), {})

    def test_ocr_calculated_payload_sums_segments_and_skips_mixed_diameters(self) -> None:
        self.app.geometry_segments = [
            {
                "pipe": PipeSection(406.4, 8.74, 400.0),
                "nps_label": "NPS 16",
                "schedule_label": "STD",
            },
            {
                "pipe": PipeSection(406.4, 8.74, 600.0),
                "nps_label": "NPS 16",
                "schedule_label": "STD",
            },
        ]

        payload = self.app._build_ocr_calculated_payload()

        self.assertEqual(payload["length_m"], 1000.0)
        self.assertEqual(payload["pipe_od_mm"], 406.4)
        self.assertEqual(payload["wall_mm"], 8.74)

        self.app.geometry_segments[1]["pipe"] = PipeSection(323.9, 6.35, 600.0)
        mixed_payload = self.app._build_ocr_calculated_payload()

        self.assertEqual(mixed_payload["length_m"], 1000.0)
        self.assertNotIn("pipe_od_mm", mixed_payload)
        self.assertNotIn("wall_mm", mixed_payload)

    def test_ocr_calculated_payload_maps_decisions_to_result(self) -> None:
        self.app._update_decision_card("Hava Icerik Testi", "BASARISIZ", "Kaldi")
        self.assertEqual(self.app._build_ocr_calculated_payload()["result"], "FAIL")

        self.app._update_decision_card("Hava Icerik Testi", "DOGRULANAMADI", "Eksik")
        self.assertEqual(self.app._build_ocr_calculated_payload()["result"], "UNKNOWN")

        self.app._reset_decision_card()
        self.assertNotIn("result", self.app._build_ocr_calculated_payload())

    def test_open_ocr_report_dialog_passes_calculated_payload(self) -> None:
        self._fill_ocr_calculated_inputs()

        with patch("hidrostatik_test.ui.report_ocr_dialog.ReportOcrDialog") as dialog_cls:
            self.app._open_ocr_report_dialog()

        dialog_cls.assert_called_once()
        args, kwargs = dialog_cls.call_args
        self.assertEqual(args[0], self.app.root)
        self.assertEqual(kwargs["calculated_payload"], self.app._build_ocr_calculated_payload())
        self.assertIs(self.app._ocr_report_dialog, dialog_cls.return_value)

    def test_open_ocr_report_dialog_reports_startup_failure(self) -> None:
        with (
            patch(
                "hidrostatik_test.ui.report_ocr_dialog.ReportOcrDialog",
                side_effect=RuntimeError("tk baslatilamadi"),
            ),
            patch("hidrostatik_test.ui.app.messagebox.showerror") as showerror,
        ):
            self.app._open_ocr_report_dialog()

        showerror.assert_called_once()
        self.assertIn("tk baslatilamadi", showerror.call_args.args[1])
        self.assertEqual(self.app.banner_level, "error")

    def test_input_snapshot_roundtrip_restores_state(self) -> None:
        self._fill_geometry()
        self.app.air_vars["temperature_c"].set("18")
        self.app.air_vars["pressure_bar"].set("65")
        self.app.air_a_mode_var.set(REFERENCE_A_MODE)
        self.app._on_air_a_mode_changed()
        self.app.air_a_reference_var.set(BOTAS_REFERENCE_OPTION_LABEL)
        self.app.material_grade_var.set(
            next(
                option
                for option in self.app.material_grade_combo["values"]
                if "X65 / L450" in option
            )
        )
        self.app.control_check_vars["ambient_temp"].set(True)
        self.app.water_backend_var.set("Table Interpolation v1 [table_v1]")
        self.app._on_water_backend_changed()

        snapshot = self.app._build_input_snapshot()

        self.app.air_vars["temperature_c"].set("")
        self.app.air_a_reference_var.set("")
        self.app.control_check_vars["ambient_temp"].set(False)
        self.app.water_backend_var.set("CoolProp EOS [coolprop]")

        self.app._apply_input_snapshot(snapshot)

        self.assertEqual(self.app.air_vars["temperature_c"].get(), "18")
        self.assertEqual(self.app.air_a_reference_var.get(), BOTAS_REFERENCE_OPTION_LABEL)
        self.assertTrue(self.app.control_check_vars["ambient_temp"].get())
        self.assertEqual(self.app.water_backend_var.get(), "Table Interpolation v1 [table_v1]")
        self.assertEqual(self.app.section_profile_vars["smys_mpa"].get(), "450")

    def test_decision_card_colors_follow_result(self) -> None:
        self.app._update_decision_card("Basinc Degisim Testi", "BASARILI", "Test gecti")
        self.assertEqual(self.app.decision_status_label.cget("bg"), "#E6F4EA")

        self.app._update_decision_card("Basinc Degisim Testi", "BASARISIZ", "Test kaldi")
        self.assertEqual(self.app.decision_status_label.cget("bg"), "#FDE7E9")

    def test_side_panel_uses_tabbed_workspace(self) -> None:
        labels = [
            self.app.side_notebook.tab(index, "text")
            for index in range(self.app.side_notebook.index("end"))
        ]

        self.assertEqual(labels, ["Detay Raporu", "Karar ve Akis", "Kayit"])

    def test_three_pane_layout_contains_left_center_and_right_panels(self) -> None:
        self.root.update_idletasks()

        panes = {str(pane) for pane in self.app.content_pane.panes()}

        self.assertIn(str(self.app.left_panel), panes)
        self.assertIn(str(self.app.center_panel), panes)
        self.assertIn(str(self.app.side_panel), panes)

    def test_active_input_panel_switches_with_notebook_tab(self) -> None:
        self.root.update_idletasks()
        self.assertTrue(self.app.active_input_frames["air"].winfo_ismapped())
        self.assertFalse(self.app.active_input_frames["pressure"].winfo_ismapped())
        self.assertFalse(self.app.active_input_frames["field"].winfo_ismapped())

        self.app.notebook.select(1)
        self.app._on_tab_changed()
        self.root.update_idletasks()

        self.assertEqual(
            self.app.active_input_title_label.cget("text"),
            "Aktif test girdileri: Basinc Degisim Testi",
        )
        self.assertFalse(self.app.active_input_frames["air"].winfo_ismapped())
        self.assertTrue(self.app.active_input_frames["pressure"].winfo_ismapped())

        self.app.notebook.select(2)
        self.app._on_tab_changed()
        self.root.update_idletasks()

        self.assertEqual(
            self.app.active_input_title_label.cget("text"), "Aktif test girdileri: Saha Kontrol"
        )
        self.assertTrue(self.app.active_input_frames["field"].winfo_ismapped())

    def test_side_panel_can_be_hidden_and_restored(self) -> None:
        self.root.update_idletasks()
        self.assertIn(str(self.app.side_panel), self.app.content_pane.panes())

        self.app._toggle_side_panel_visibility()
        self.root.update_idletasks()
        self.assertNotIn(str(self.app.side_panel), self.app.content_pane.panes())

        self.app._toggle_side_panel_visibility()
        self.root.update_idletasks()
        self.assertIn(str(self.app.side_panel), self.app.content_pane.panes())

    def test_help_notes_are_hidden_by_default_and_can_be_shown(self) -> None:
        self.root.update_idletasks()
        self.assertFalse(self.app.help_notes_visible_var.get())
        self.assertFalse(self.app.intro_label.winfo_ismapped())

        self.app._toggle_help_notes_visibility()
        self.root.update_idletasks()

        self.assertTrue(self.app.help_notes_visible_var.get())
        self.assertTrue(self.app.intro_label.winfo_ismapped())

    def test_clear_active_form_resets_pressure_inputs(self) -> None:
        self.app.notebook.select(1)
        self.app.pressure_vars["temperature_c"].set("20")
        self.app.pressure_vars["pressure_bar"].set("80")
        self.app.pressure_vars["delta_t_c"].set("0.5")
        self.app.pressure_vars["actual_pressure_change_bar"].set("1.9")
        self.app.pressure_vars["b_micro_per_c"].set("180")

        self.app._clear_active_form()

        self.assertEqual(self.app.pressure_vars["temperature_c"].get(), "")
        self.assertEqual(self.app.pressure_vars["pressure_bar"].get(), "")
        self.assertEqual(self.app.pressure_vars["delta_t_c"].get(), "")
        self.assertEqual(self.app.coefficient_manager.get("pressure_a"), CoefficientState.EMPTY)
        self.assertEqual(self.app.coefficient_manager.get("pressure_b"), CoefficientState.EMPTY)

    def test_clear_active_air_form_resets_custom_k_and_decision(self) -> None:
        self.app.notebook.select(0)
        self.app.air_vars["temperature_c"].set("20")
        self.app.air_vars["pressure_bar"].set("80")
        self.app.air_vars["pressure_rise_bar"].set("1.0")
        self.app.k_preset_var.set("Ozel")
        self.app.air_vars["k_factor"].set("1.15")
        self.app._update_decision_card("Hava Icerik Testi", "BASARILI", "Eski karar")

        self.app._clear_active_form()

        self.assertEqual(self.app.air_vars["temperature_c"].get(), "")
        self.assertEqual(self.app.air_vars["pressure_bar"].get(), "")
        self.assertEqual(self.app.air_vars["pressure_rise_bar"].get(), "1.0")
        self.assertEqual(self.app.air_vars["k_factor"].get(), "")
        self.assertEqual(self.app.decision_status_var.get(), "BEKLIYOR")
        self.assertIn("aktif gorunen", self.app.live_notice_var.get())

    def test_clear_pressure_form_uses_selected_steel_preset(self) -> None:
        self.app.notebook.select(1)
        self.app.steel_preset_var.set("Dusuk alasimli celik - 12.5")
        self.app.b_helper_vars["steel_alpha_micro_per_c"].set("99")

        self.app._clear_pressure_form()

        self.assertEqual(self.app.b_helper_vars["steel_alpha_micro_per_c"].get(), "12.5")
        self.app.steel_preset_var.set("Ozel")
        self.app.b_helper_vars["steel_alpha_micro_per_c"].set("88")

        self.app._clear_pressure_form()

        self.assertEqual(self.app.b_helper_vars["steel_alpha_micro_per_c"].get(), "")

    def test_tab_switch_limits_live_notice_to_relevant_fields(self) -> None:
        self.app.notebook.select(0)
        self.app.air_vars["temperature_c"].set("20")
        self.app.air_vars["pressure_bar"].set("80")
        self.app._clear_air_form()
        self.assertIn("aktif gorunen", self.app.live_notice_var.get())

        self.app.notebook.select(1)
        self.app._on_tab_changed()

        self.assertIn("aktif gorunen", self.app.live_notice_var.get())

    def test_invalid_live_input_sets_field_message(self) -> None:
        self.app.air_vars["temperature_c"].set("abc")

        self.assertIn("Gecerli bir sayi", self.app.field_message_vars["air.temperature_c"].get())
        self.assertIn("gecersiz", self.app.live_notice_var.get())
        self.assertEqual(
            str(self.app.entry_widgets["air.temperature_c"].cget("style")), "Hydro.error.TEntry"
        )

    def test_semantic_invalid_input_sets_error_style(self) -> None:
        self.app.geometry_vars["outside_diameter_mm"].set("10")
        self.app.geometry_vars["wall_thickness_mm"].set("6")

        self.assertIn(
            "yarisindan kucuk", self.app.field_message_vars["geometry.wall_thickness_mm"].get()
        )
        self.assertEqual(
            str(self.app.entry_widgets["geometry.wall_thickness_mm"].cget("style")),
            "Hydro.error.TEntry",
        )

    def test_spec_warning_input_sets_warning_style(self) -> None:
        self.app.air_vars["pressure_rise_bar"].set("1.2")

        self.assertIn("tam 1.0 bar", self.app.field_message_vars["air.pressure_rise_bar"].get())
        self.assertEqual(
            str(self.app.entry_widgets["air.pressure_rise_bar"].cget("style")),
            "Hydro.warning.TEntry",
        )

    def test_ambient_temp_below_limit_sets_error_style(self) -> None:
        self.app.air_vars["temperature_c"].set("0")
        self.app.field_vars["ambient_temperature_c"].set("10")

        self.assertNotIn("10.1", self.app.field_message_vars["air.temperature_c"].get())
        self.assertNotIn("10.1", self.app.field_message_vars["field.ambient_temperature_c"].get())

        self.app.field_vars["ambient_temperature_c"].set("0")

        self.assertIn("10.1", self.app.field_message_vars["field.ambient_temperature_c"].get())
        self.assertIn("altinda", self.app.field_message_vars["field.ambient_temperature_c"].get())
        self.assertEqual(
            str(self.app.entry_widgets["field.ambient_temperature_c"].cget("style")),
            "Hydro.error.TEntry",
        )
        # Su sicakligi 10.1 kontrolune tabi degildir; mesaji 10.1 icermez.
        self.assertNotIn("10.1", self.app.field_message_vars["air.temperature_c"].get())

    def test_table_mode_without_reference_highlights_reference_combo(self) -> None:
        self.app.air_a_mode_var.set(REFERENCE_A_MODE)
        self.app._on_air_a_mode_changed()

        self.assertEqual(
            str(self.app.air_a_reference_combo.cget("style")), "Hydro.warning.TCombobox"
        )

    def test_started_profile_without_pump_location_highlights_combo(self) -> None:
        self.app.section_profile_vars["highest_elevation_m"].set("100")
        self.app.section_profile_vars["lowest_elevation_m"].set("0")
        self.app.section_profile_vars["design_pressure_bar"].set("20")

        self.assertEqual(str(self.app.pump_location_combo.cget("style")), "Hydro.warning.TCombobox")

    def test_live_coefficient_refresh_sets_success_message(self) -> None:
        self.app.air_vars["temperature_c"].set("20")
        self.app.air_vars["pressure_bar"].set("80")
        self.assertTrue(self.app._calculate_air_a(log_result=False))

        self.app.air_vars["pressure_bar"].set("81")

        self.assertEqual(self.app.coefficient_manager.get("air_a"), CoefficientState.COMPUTED)
        self.assertEqual(
            self.app.field_message_vars["air.a_micro_per_bar"].get(), "Hazir: Hesap guncel."
        )
        self.assertIn("tutarli gorunuyor", self.app.live_notice_var.get())

    def test_backend_change_marks_auto_coefficients_stale(self) -> None:
        self.app.air_vars["temperature_c"].set("20")
        self.app.air_vars["pressure_bar"].set("80")
        self.assertTrue(self.app._calculate_air_a(log_result=False))
        self.assertEqual(self.app.coefficient_manager.get("air_a"), CoefficientState.COMPUTED)

        self.app.water_backend_var.set("Table Interpolation v1 [table_v1]")
        self.app._on_water_backend_changed()

        self.assertEqual(self.app.coefficient_manager.get("air_a"), CoefficientState.COMPUTED)
        self.assertIn("Table Interpolation v1", self.app.water_backend_summary_var.get())
        self.assertIn("Backend secimi degisti", self.app.air_backend_comparison_var.get())

    def test_compare_air_backend_updates_summary(self) -> None:
        self.app.air_vars["temperature_c"].set("20")
        self.app.air_vars["pressure_bar"].set("80")

        self.app._compare_active_backend()

        self.assertIn("Hava A karsilastirmasi", self.app.air_backend_comparison_var.get())
        self.assertIn("CoolProp EOS", self.app.air_backend_comparison_var.get())
        self.assertIn("Table Interpolation v1", self.app.air_backend_comparison_var.get())
        self.assertEqual(
            self.app.active_backend_comparison_var.get(), self.app.air_backend_comparison_var.get()
        )

    def test_field_tab_disables_backend_comparison_action(self) -> None:
        self.app.notebook.select(2)
        self.app._on_tab_changed()

        self.assertTrue(self.app.compare_backend_button.instate(["disabled"]))
        self.assertIn("kullanilmaz", self.app.active_backend_comparison_var.get())

    def test_visual_schema_updates_with_active_tab(self) -> None:
        self.assertIn("Hava testi akisi", self.app.visual_schema_var.get())

        self.app.notebook.select(1)
        self.app._on_tab_changed()
        self.assertIn("Basinc degisim testi akisi", self.app.visual_schema_var.get())

        self.app.notebook.select(2)
        self.app._on_tab_changed()
        self.assertIn("Saha kontrol akisi", self.app.visual_schema_var.get())

    def test_update_download_summary_tracks_selected_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target_dir = Path(temp_dir) / "hydro-updates"
            self.app.update_download_dir_var.set(str(target_dir))

            self.assertIn(str(target_dir), self.app.update_download_summary_var.get())

    def test_apply_available_update_uses_download_dialog(self) -> None:
        self.app.latest_update_info = type(
            "UpdateInfoLike",
            (),
            {
                "update_available": True,
                "latest_version": "9.9.9",
                "asset": type(
                    "AssetLike",
                    (),
                    {
                        "name": "update.zip",
                        "download_url": "https://example.com/update.zip",
                        "size": 1024,
                    },
                )(),
            },
        )()
        download_dir = Path(tempfile.mkdtemp())
        self.app.update_download_dir_var.set(str(download_dir))

        dialog_shown = False

        class FakeDialog:
            def __init__(self, **kwargs):
                nonlocal dialog_shown
                dialog_shown = True

            def wait(self):
                return "completed"

        with (
            patch(
                "hidrostatik_test.ui.download_dialog.DownloadDialog",
                side_effect=FakeDialog,
            ),
            patch.object(self.app, "_perform_update_install_after_download") as mock_install,
        ):
            self.app._apply_available_update()

        self.assertTrue(dialog_shown)
        mock_install.assert_called_once()

    def test_apply_available_update_opens_release_page_when_no_asset(self) -> None:
        self.app.latest_update_info = type(
            "UpdateInfoLike",
            (),
            {
                "update_available": True,
                "latest_version": "9.9.9",
                "asset": None,
            },
        )()

        with patch.object(self.app, "_open_release_page") as mock_open:
            self.app._apply_available_update()

        mock_open.assert_called_once()

    def test_report_text_contains_version_spec_and_input_snapshot(self) -> None:
        self._fill_geometry()
        self.app.air_vars["temperature_c"].set("20")
        self.app.air_vars["pressure_bar"].set("80")
        self.app.air_vars["k_factor"].set("1.02")
        self.app._compare_active_backend()
        self.app.notebook.select(1)
        self.app._on_tab_changed()
        self.app.pressure_vars["delta_t_c"].set("0.6")
        self.app.pressure_vars["temperature_c"].set("20")
        self.app.pressure_vars["pressure_bar"].set("80")
        self.app.material_grade_var.set(
            next(
                option
                for option in self.app.material_grade_combo["values"]
                if "X65 / L450" in option
            )
        )
        self.app.b_helper_vars["steel_alpha_micro_per_c"].set("12.0")
        self.app._compare_active_backend()
        self.app.control_check_vars["ambient_temp"].set(True)
        self.app.field_vars["pig_distance_m"].set("1000")
        self.app.field_vars["pig_travel_time_min"].set("8")
        self.app._calculate_pig_speed(log_result=False)

        report = self.app._build_report_text()

        self.assertIn(f"Surum: {APP_VERSION}", report)
        self.assertIn(f"Referans sartname: {SPEC_DOCUMENT_CODE}", report)
        self.assertIn("Hava Icerik Testi Girdileri", report)
        self.assertIn("Basinc Degisim Testi Girdileri", report)
        self.assertIn(f"A secenegi: {AUTO_A_MODE}", report)
        self.assertIn(f"B secenegi: {TABLE_B_MODE}", report)
        self.assertIn(f"B kaynagi: {B_SOURCE_INSTITUTIONAL_LABEL}", report)
        self.assertIn("Su backend'i: CoolProp EOS", report)
        self.assertIn("Hava backend karsilastirmasi: Hava A karsilastirmasi", report)
        self.assertIn("Basinc backend karsilastirmasi: Basinc A/B karsilastirmasi", report)
        self.assertIn("A referans tablosu: -", report)
        self.assertIn(f"B referans tablosu: {BOTAS_REFERENCE_OPTION_LABEL}", report)
        self.assertIn("A/B kontrol tablosu (onarilmis hucre:", report)
        self.assertIn("Dis cap (mm): 406.4", report)
        self.assertIn("Boru malzeme kalitesi: API 5L PSL2 X65 / L450 - SMYS 450 MPa", report)
        self.assertIn("SMYS (MPa): 450", report)
        self.assertIn("Su basinci (bar): 80", report)
        self.assertIn("dT = Tilk - Tson", report)
        self.assertIn("Pa = Pilk - Pson", report)
        self.assertIn("Operasyon Kontrol Noktalari", report)
        self.assertIn("Pig Hiz Hesabi", report)
        self.assertIn(
            "[x] Dolum sirasinda hava sicakligi +2 °C limitine gore kontrol edildi (10.1)", report
        )

    # --- P0/P1 remediation davranis testleri ---

    def _prepare_air_live_result(self) -> None:
        self._fill_geometry()
        self.app.air_vars["temperature_c"].set("20")
        self.app.air_vars["pressure_bar"].set("80")
        self.assertTrue(self.app._calculate_air_a(log_result=False))
        self.app.air_vars["actual_added_water_m3"].set("0.0079")

    def test_save_report_txt_writes_report_without_crash(self) -> None:
        self._fill_geometry()
        target = Path(tempfile.mkdtemp()) / "rapor.txt"

        with (
            patch("hidrostatik_test.ui.app.filedialog.asksaveasfilename", return_value=str(target)),
            patch("hidrostatik_test.ui.app.messagebox.showinfo") as showinfo,
            patch("hidrostatik_test.ui.app.messagebox.showerror") as showerror,
        ):
            self.app._save_report()

        self.assertTrue(target.exists())
        self.assertIn("Hidrostatik", target.read_text(encoding="utf-8"))
        showinfo.assert_called_once()
        showerror.assert_not_called()
        self.assertEqual(self.app.banner_level, "success")

    def test_save_report_pdf_uses_exporter(self) -> None:
        self._fill_geometry()
        target = Path(tempfile.mkdtemp()) / "rapor.pdf"

        with (
            patch("hidrostatik_test.ui.app.filedialog.asksaveasfilename", return_value=str(target)),
            patch("hidrostatik_test.services.report_export.export_pdf_report") as export_pdf,
            patch("hidrostatik_test.services.report_export.export_excel_report") as export_xlsx,
            patch("hidrostatik_test.ui.app.messagebox.showinfo"),
            patch("hidrostatik_test.ui.app.messagebox.showerror"),
        ):
            self.app._save_report()

        export_pdf.assert_called_once()
        export_xlsx.assert_not_called()
        self.assertEqual(export_pdf.call_args.args[0], target)

    def test_save_report_xlsx_uses_exporter(self) -> None:
        self._fill_geometry()
        target = Path(tempfile.mkdtemp()) / "rapor.xlsx"

        with (
            patch("hidrostatik_test.ui.app.filedialog.asksaveasfilename", return_value=str(target)),
            patch("hidrostatik_test.services.report_export.export_excel_report") as export_xlsx,
            patch("hidrostatik_test.ui.app.messagebox.showinfo"),
            patch("hidrostatik_test.ui.app.messagebox.showerror"),
        ):
            self.app._save_report()

        export_xlsx.assert_called_once()

    def test_save_report_cancel_does_not_write(self) -> None:
        with (
            patch("hidrostatik_test.ui.app.filedialog.asksaveasfilename", return_value=""),
            patch("hidrostatik_test.ui.app.messagebox.showinfo") as showinfo,
        ):
            self.app._save_report()

        showinfo.assert_not_called()
        self.assertEqual(self.app.report_entries, [])

    def test_save_report_export_error_is_reported_to_user(self) -> None:
        target = Path(tempfile.mkdtemp()) / "rapor.pdf"

        with (
            patch("hidrostatik_test.ui.app.filedialog.asksaveasfilename", return_value=str(target)),
            patch(
                "hidrostatik_test.services.report_export.export_pdf_report",
                side_effect=RuntimeError("export boom"),
            ),
            patch("hidrostatik_test.ui.app.messagebox.showinfo"),
            patch("hidrostatik_test.ui.app.messagebox.showerror") as showerror,
        ):
            self.app._save_report()

        showerror.assert_called_once()
        self.assertEqual(self.app.banner_level, "error")
        self.assertIn("export boom", self.app.banner_var.get())

    def test_stale_coefficient_blocks_successful_live_decision(self) -> None:
        self._prepare_air_live_result()
        self.app._refresh_live_test_decision()
        self.assertEqual(self.app._decisions["air"]["status"], "BASARILI")

        self.app.air_vars["temperature_c"].set("")

        self.assertEqual(self.app.coefficient_manager.get("air_a"), CoefficientState.STALE)
        self.assertNotEqual(self.app._decisions["air"]["status"], "BASARILI")
        self.assertEqual(self.app._decisions["air"]["status"], "KATSAYI GUNCELLENMELI")

    def test_mode_change_clears_old_coefficient_value(self) -> None:
        self.app.air_vars["temperature_c"].set("20")
        self.app.air_vars["pressure_bar"].set("80")
        self.assertTrue(self.app._calculate_air_a(log_result=False))
        self.assertTrue(self.app.coefficient_manager.is_ready("air_a"))

        self.app.air_a_mode_var.set(MANUAL_A_MODE)
        self.app._on_air_a_mode_changed()

        self.assertEqual(self.app.air_vars["a_micro_per_bar"].get(), "")
        self.assertFalse(self.app.coefficient_manager.is_ready("air_a"))
        self.assertEqual(self.app.coefficient_manager.get("air_a"), CoefficientState.EMPTY)

        self.app.air_vars["a_micro_per_bar"].set("45")
        self.assertTrue(self.app.coefficient_manager.is_ready("air_a"))
        self.app._on_air_a_mode_changed()
        self.assertEqual(self.app.air_vars["a_micro_per_bar"].get(), "45")

    def test_table_mode_requires_reference_after_mode_change(self) -> None:
        self.app.air_vars["temperature_c"].set("15")
        self.app.air_vars["pressure_bar"].set("80")
        self.assertTrue(self.app._calculate_air_a(log_result=False))

        self.app.air_a_mode_var.set(REFERENCE_A_MODE)
        self.app._on_air_a_mode_changed()

        self.assertEqual(self.app.air_vars["a_micro_per_bar"].get(), "")
        self.assertEqual(self.app.air_a_reference_var.get(), "")
        self.assertFalse(self.app.coefficient_manager.is_ready("air_a"))

        self.app.air_a_reference_var.set(GAIL_REFERENCE_OPTION_LABEL)
        self.app._on_air_a_reference_changed()
        self.assertTrue(self.app.coefficient_manager.is_ready("air_a"))

    def test_pressure_decision_preserved_when_switching_to_air_tab(self) -> None:
        self._fill_geometry()
        self.app.notebook.select(1)
        self.app._on_tab_changed()
        self.app.pressure_vars["temperature_c"].set("20")
        self.app.pressure_vars["pressure_bar"].set("80")
        self.assertTrue(self.app._calculate_pressure_a(log_result=False))
        self.assertTrue(self.app._calculate_b_helper(log_result=False))
        a_value = float(self.app.pressure_vars["a_micro_per_bar"].get())
        b_value = float(self.app.pressure_vars["b_micro_per_c"].get())
        theoretical = (b_value * 0.6) / (
            self.app._build_pipe_section("pressure").elasticity_term + a_value
        )
        self.app.pressure_vars["delta_t_c"].set("0.6")
        self.app.pressure_vars["actual_pressure_change_bar"].set(f"{theoretical + 0.1:.9f}")
        self.app._run_pressure_test()
        self.assertEqual(self.app._decisions["pressure"]["status"], "BASARILI")

        self.app.notebook.select(0)
        self.app._on_tab_changed()

        self.assertEqual(self.app._decisions["pressure"]["status"], "BASARILI")
        report = self.app._build_report_text()
        self.assertIn("Basinc Degisim Testi durumu: BASARILI", report)
        self.assertIn("Hava Icerik Testi durumu:", report)

        self.app._clear_active_form()

        self.assertEqual(self.app._decisions["pressure"]["status"], "BASARILI")
        self.assertEqual(self.app._decisions["air"]["status"], "BEKLIYOR")

    def test_live_result_is_recorded_once_per_input_signature(self) -> None:
        self._prepare_air_live_result()
        self.app._refresh_live_test_decision()
        self.app._flush_pending_live_result()

        self.assertGreaterEqual(len(self.app.report_entries), 1)
        recorded = len(self.app.report_entries)

        self.app._refresh_live_test_decision()
        self.app._flush_pending_live_result()
        self.assertEqual(len(self.app.report_entries), recorded)

        self.app.air_vars["actual_added_water_m3"].set("0.0090")
        self.app._refresh_live_test_decision()
        self.app._flush_pending_live_result()
        self.assertEqual(len(self.app.report_entries), recorded + 1)

    def test_failed_air_evaluation_does_not_show_success_banner(self) -> None:
        self._prepare_air_live_result()
        self.app.air_vars["actual_added_water_m3"].set("5")

        self.app._run_air_test()

        self.assertEqual(self.app._decisions["air"]["status"], "BASARISIZ")
        self.assertNotEqual(self.app.banner_level, "success")
        self.assertEqual(self.app.banner_level, "error")
        self.assertIn("BASARISIZ", self.app.header_status_var.get())

    def test_non_finite_and_out_of_range_values_are_rejected(self) -> None:
        for raw in ("nan", "inf", "-inf", "1e999"):
            self.assertIsNone(self.app._safe_float(raw))

        with self.assertRaises(ValidationError):
            self.app._read_float(
                tk.StringVar(value="nan"), "A degeri", "air", "air.a_micro_per_bar"
            )

        self.app.air_a_mode_var.set(MANUAL_A_MODE)
        self.app._on_air_a_mode_changed()
        self.app.air_vars["a_micro_per_bar"].set("450")
        with self.assertRaises(ValidationError):
            self.app._read_float(
                self.app.air_vars["a_micro_per_bar"],
                "A degeri",
                "air",
                "air.a_micro_per_bar",
            )
        self.assertIn("aralik", self.app.field_message_vars["air.a_micro_per_bar"].get())

    def test_field_check_definitions_come_from_single_source(self) -> None:
        self.assertEqual(
            tuple(app_module.FIELD_CHECK_DEFINITIONS),
            tuple(ui_constants.FIELD_CHECK_DEFINITIONS),
        )
        self.assertEqual(len(ui_constants.FIELD_CHECK_DEFINITIONS), 11)
        references = {reference for _key, _label, reference in ui_constants.FIELD_CHECK_DEFINITIONS}
        for expected in ("10.1", "14.3", "15.1", "16-17", "21"):
            self.assertIn(expected, references)

    def test_ambient_and_water_temperature_are_separate_fields(self) -> None:
        self.app.air_vars["temperature_c"].set("0")
        self.app.field_vars["ambient_temperature_c"].set("10")

        self.assertNotIn("10.1", self.app.field_message_vars["air.temperature_c"].get())
        self.assertEqual(self.app.field_message_vars["field.ambient_temperature_c"].get(), "")

        self.app.field_vars["ambient_temperature_c"].set("0")

        self.assertIn("10.1", self.app.field_message_vars["field.ambient_temperature_c"].get())

    def test_single_field_edit_is_bounded_and_debounced(self) -> None:
        self.app.air_vars["temperature_c"].set("20")
        self.app.air_vars["pressure_bar"].set("80")
        self.app._flush_pending_session_save()

        refresh_calls: list[str] = []
        original_refresh = self.app._refresh_live_coefficients

        def counting_refresh() -> None:
            refresh_calls.append("refresh")
            original_refresh()

        self.app._refresh_live_coefficients = counting_refresh  # type: ignore[method-assign]
        session_writes: list[dict[str, object]] = []
        original_update = self.app.session_manager.update_inputs

        def counting_update(inputs: dict[str, object]) -> None:
            session_writes.append(inputs)
            original_update(inputs)

        self.app.session_manager.update_inputs = counting_update  # type: ignore[method-assign]

        self.app.air_vars["pressure_bar"].set("81")
        self.app._flush_pending_session_save()

        self.assertLessEqual(len(refresh_calls), 2)
        self.assertLessEqual(len(session_writes), 1)

    def test_apply_available_update_passes_download_manager_instance(self) -> None:
        self.app.latest_update_info = type(
            "UpdateInfoLike",
            (),
            {
                "update_available": True,
                "latest_version": "9.9.9",
                "asset": type(
                    "AssetLike",
                    (),
                    {
                        "name": "update.zip",
                        "download_url": "https://example.com/update.zip",
                        "size": 1024,
                    },
                )(),
            },
        )()
        self.app.update_download_dir_var.set(str(Path(tempfile.mkdtemp())))
        captured: dict[str, object] = {}

        class FakeDialog:
            def __init__(self, **kwargs):
                captured.update(kwargs)

            def wait(self):
                return "cancelled"

        with (
            patch(
                "hidrostatik_test.ui.download_dialog.DownloadDialog",
                side_effect=FakeDialog,
            ),
            patch("hidrostatik_test.ui.app.messagebox.showinfo"),
        ):
            self.app._apply_available_update()

        manager = captured.get("download_manager")
        self.assertIsInstance(manager, DownloadManager)
        self.assertNotIsInstance(manager, type)
        self.assertIs(manager, self.app.download_manager)
        self.assertFalse(self.app.update_install_in_progress)

    def test_time_series_record_uses_public_session_api(self) -> None:
        self.app.ts_pressure_var.set("70")
        self.app.ts_temp_var.set("18")

        with patch.object(
            self.app.session_manager,
            "add_time_series_record",
            wraps=self.app.session_manager.add_time_series_record,
        ) as add_record:
            self.app._add_time_series_record()

        add_record.assert_called_once()
        session = self.app.session_manager.get_active_session()
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(len(session.time_series.get("records", [])), 1)
        self.assertEqual(self.app.banner_level, "success")
        self.assertFalse(self.app.session_manager.has_database)

    def test_negative_b_is_accepted_with_explanation(self) -> None:
        self._fill_geometry()
        self.app.notebook.select(1)
        self.app._on_tab_changed()
        self.app.pressure_vars["temperature_c"].set("20")
        self.app.pressure_vars["pressure_bar"].set("80")
        self.app.pressure_b_mode_var.set(MANUAL_B_MODE)
        self.app._on_pressure_b_mode_changed()
        self.app.pressure_vars["b_micro_per_c"].set("-100")
        self.app.pressure_vars["delta_t_c"].set("0.6")
        self.app.pressure_vars["actual_pressure_change_bar"].set("-0.9")

        self.app._run_pressure_test()

        self.assertNotEqual(self.app._decisions["pressure"]["status"], "DOGRULANAMADI")
        self.assertEqual(self.app._decisions["pressure"]["status"], "BASARILI")
        self.assertIn("Negatif B", self.app.active_detail_report_var.get())

    def test_minsize_fits_small_screens(self) -> None:
        width, height = self.app.root.minsize()

        self.assertGreaterEqual(width, 1024)
        self.assertGreaterEqual(height, 700)
        self.assertLessEqual(width, 1280)
        self.assertLessEqual(height, 840)

    def test_report_contains_acceptance_rules_and_ambiguous_colors_differ(self) -> None:
        self.app._update_decision_card("Hava Icerik Testi", "DOGRULANAMADI", "Eksik")
        ambiguous_bg = self.app.decision_status_label.cget("bg")
        self.app._update_decision_card("Hava Icerik Testi", "BEKLIYOR", "Bekliyor")
        waiting_bg = self.app.decision_status_label.cget("bg")
        self.assertNotEqual(ambiguous_bg, waiting_bg)

        report = self.app._build_report_text()
        self.assertIn("Vpa < 1.06 x Vp", report)
        self.assertIn("(Pa - Pt) <= 0.3 bar", report)

    # --- Ergonomi fazi: karar seridi, kapi, klavye, kaydirma, birimler ---

    def test_decision_strip_shows_status_rule_and_margin_after_air_result(self) -> None:
        self._prepare_air_live_result()

        self.app._run_air_test()

        self.assertEqual(self.app._decisions["air"]["status"], "BASARILI")
        self.assertIn("BASARILI", self.app.header_status_var.get())
        self.assertIn("Hava Icerik Testi", self.app.header_status_var.get())
        self.assertIn("Vpa < 1.06 x Vp", self.app.header_rule_var.get())
        self.assertIn("Vp=", self.app.header_rule_var.get())
        self.assertIn("Vpa=", self.app.header_rule_var.get())
        self.assertIn("marj=", self.app.header_rule_var.get())
        self.assertEqual(self.app.decision_status_label.cget("bg"), "#E6F4EA")

    def test_decision_strip_follows_active_tab_and_preserves_decisions(self) -> None:
        self._prepare_air_live_result()
        self.app._run_air_test()
        self.assertEqual(self.app._decisions["air"]["status"], "BASARILI")

        self.app._select_tab_by_key("pressure")

        self.assertIn("Basinc Degisim Testi", self.app.header_status_var.get())
        self.assertIn("(Pa - Pt) <= 0.3 bar", self.app.header_rule_var.get())
        self.assertEqual(self.app._decisions["air"]["status"], "BASARILI")

        self.app._select_tab_by_key("air")

        self.assertIn("BASARILI", self.app.header_status_var.get())
        self.assertIn("Vpa < 1.06 x Vp", self.app.header_rule_var.get())

    def test_decision_card_rule_and_long_summary_are_displayed_safely(self) -> None:
        long_summary = ("Uzun karar dayanagi " * 40).strip()
        self.app._update_decision_card("Basinc Degisim Testi", "DOGRULANAMADI", long_summary)

        self.assertIn("Kural: (Pa - Pt) <= 0.3 bar", self.app.decision_rule_var.get())
        self.assertIn("Pt=", self.app.decision_rule_var.get())
        self.assertIn("fark=", self.app.decision_rule_var.get())
        self.assertLessEqual(len(self.app.decision_summary_var.get()), 240)
        self.assertTrue(self.app.decision_summary_var.get().endswith("..."))
        self.assertEqual(self.app._decisions["pressure"]["summary"], long_summary)
        self.assertIn(long_summary, self.app._build_report_text())
        self.app._select_tab_by_key("pressure")
        self.assertIn(long_summary, self.app.active_detail_report_var.get())
        self.assertNotIn(long_summary, self.app.decision_summary_var.get())

    def test_decision_colors_separate_ambiguous_waiting_and_stale(self) -> None:
        palettes: dict[str, str] = {}
        for status in ("DOGRULANAMADI", "BEKLIYOR", "KATSAYI GUNCELLENMELI", "BASARILI"):
            self.app._update_decision_card("Hava Icerik Testi", status, "Durum")
            palettes[status] = self.app.decision_status_label.cget("bg")

        self.assertEqual(palettes["BEKLIYOR"], "#F1F3F5")
        self.assertNotEqual(palettes["DOGRULANAMADI"], palettes["BEKLIYOR"])
        self.assertNotEqual(palettes["KATSAYI GUNCELLENMELI"], palettes["BEKLIYOR"])
        self.assertEqual(palettes["BASARILI"], "#E6F4EA")

    def test_required_field_gate_blocks_evaluation_with_reason(self) -> None:
        self.app._select_tab_by_key("air")

        self.assertEqual(str(self.app.air_test_button.cget("state")), "disabled")
        gate_text = self.app.gate_labels["air"].cget("text")
        self.assertIn("Eksik:", gate_text)
        self.assertIn("geometri", gate_text)

        self._prepare_air_live_result()

        self.assertEqual(str(self.app.air_test_button.cget("state")), "normal")
        self.assertEqual(self.app.gate_labels["air"].cget("text"), "")

        self.app.air_vars["actual_added_water_m3"].set("")

        self.assertEqual(str(self.app.air_test_button.cget("state")), "disabled")
        self.assertIn("Vpa", self.app.gate_labels["air"].cget("text"))

    def test_gate_explains_missing_coefficient_and_blocks_pressure_test(self) -> None:
        self._fill_geometry()
        self.app.pressure_vars["delta_t_c"].set("0.6")
        self.app.pressure_vars["actual_pressure_change_bar"].set("0.9")

        self.assertEqual(str(self.app.pressure_test_button.cget("state")), "disabled")
        gate_text = self.app.gate_labels["pressure"].cget("text")
        self.assertIn("su sicakligi", gate_text)
        self.assertIn("A", gate_text)

    def test_required_markers_follow_mode_changes_immediately(self) -> None:
        auto_label = self.app.field_label_widgets["air.a_micro_per_bar"].cget("text")
        self.assertFalse(auto_label.endswith("*"))

        self.app.air_a_mode_var.set(MANUAL_A_MODE)
        self.app._on_air_a_mode_changed()

        manual_label = self.app.field_label_widgets["air.a_micro_per_bar"].cget("text")
        self.assertTrue(manual_label.endswith("*"))

        self.app.air_a_mode_var.set(AUTO_A_MODE)
        self.app._on_air_a_mode_changed()

        self.assertFalse(
            self.app.field_label_widgets["air.a_micro_per_bar"].cget("text").endswith("*")
        )

        table_b_label = self.app.field_label_widgets["pressure.b_micro_per_c"].cget("text")
        self.assertFalse(table_b_label.endswith("*"))

        self.app.pressure_b_mode_var.set(MANUAL_B_MODE)
        self.app._on_pressure_b_mode_changed()

        self.assertTrue(
            self.app.field_label_widgets["pressure.b_micro_per_c"].cget("text").endswith("*")
        )
        self.assertIn(REQUIRED_FIELD_HINT, self._visible_required_hint_texts())

    def _visible_required_hint_texts(self) -> str:
        texts: list[str] = []
        for widget in self.app.root.winfo_children():
            self._collect_label_texts(widget, texts)
        return "\n".join(texts)

    def _collect_label_texts(self, widget: tk.Misc, texts: list[str]) -> None:
        try:
            text = widget.cget("text")
        except tk.TclError:
            text = ""
        if text:
            texts.append(str(text))
        for child in widget.winfo_children():
            self._collect_label_texts(child, texts)

    def test_enter_moves_to_next_field_and_shift_enter_returns(self) -> None:
        first_entry = self.app.entry_widgets["geometry.outside_diameter_mm"]
        second_key = "geometry.wall_thickness_mm"

        with patch.object(self.app, "_focus_field") as focus_field:
            result = self.app._on_entry_return(SimpleNamespace(widget=first_entry, state=0))

        self.assertEqual(result, "break")
        focus_field.assert_called_once_with(second_key)

        wall_entry = self.app.entry_widgets[second_key]
        with patch.object(self.app, "_focus_field") as focus_field:
            result = self.app._on_entry_return(SimpleNamespace(widget=wall_entry, state=0x1))

        self.assertEqual(result, "break")
        focus_field.assert_called_once_with("geometry.outside_diameter_mm")
        self.assertEqual(self.app._focus_order()[0], "geometry.outside_diameter_mm")

    def test_enter_on_text_widget_and_ctrl_enter_do_not_move_focus(self) -> None:
        with patch.object(self.app, "_focus_field") as focus_field:
            result = self.app._on_entry_return(
                SimpleNamespace(widget=self.app.detail_report_text, state=0)
            )
            ctrl_result = self.app._on_entry_return(
                SimpleNamespace(
                    widget=self.app.entry_widgets["geometry.outside_diameter_mm"],
                    state=0x4,
                )
            )

        self.assertIsNone(result)
        self.assertIsNone(ctrl_result)
        focus_field.assert_not_called()

    def test_keyboard_shortcuts_and_focus_ring_are_available(self) -> None:
        with patch.object(self.app, "_run_selected_test") as run_selected:
            result = self.app._on_evaluate_shortcut()

        self.assertEqual(result, "break")
        run_selected.assert_called_once()

        with patch.object(self.app, "_recalculate_active_coefficients") as recalculate:
            result = self.app._on_refresh_shortcut()

        self.assertEqual(result, "break")
        recalculate.assert_called_once()

        border_map = self.app.ui_style.map("Hydro.neutral.TEntry", "bordercolor")
        self.assertTrue(any(str(item[0]) == "focus" for item in border_map))

    def test_pig_gate_requires_distance_and_time(self) -> None:
        self.app._select_tab_by_key("field")

        self.assertEqual(str(self.app.pig_calculate_button.cget("state")), "disabled")
        self.assertIn("mesafe", self.app.gate_labels["field"].cget("text"))

        self.app.field_vars["pig_distance_m"].set("1000")
        self.app.field_vars["pig_travel_time_min"].set("8")

        self.assertEqual(str(self.app.pig_calculate_button.cget("state")), "normal")
        self.assertEqual(self.app.gate_labels["field"].cget("text"), "")

        self.app._calculate_pig_speed(log_result=False)

        self.assertIn("SAHA KONTROL", self.app.header_status_var.get())
        self.assertIn("2.083333", self.app.header_status_var.get())
        self.assertIn("limit", self.app.header_rule_var.get())

    def test_invalid_or_missing_field_receives_focus_and_scrolls(self) -> None:
        with patch.object(self.app, "_focus_field") as focus_field:
            result = self.app._run_selected_test()

        self.assertIsNone(result)
        self.assertIn("Eksik:", self.app.banner_var.get())
        focus_field.assert_called_once_with("geometry.outside_diameter_mm")

        self._fill_geometry()
        self.app.air_vars["temperature_c"].set("20")
        self.app.air_vars["pressure_bar"].set("80")
        with patch.object(self.app, "_focus_field") as focus_field:
            self.app._run_air_test()

        focus_field.assert_any_call("air.actual_added_water_m3")

        with patch.object(self.app, "_scroll_widget_into_view") as scroll_into_view:
            self.app._focus_field("air.actual_added_water_m3")

        scroll_into_view.assert_called_once()

    def test_mousewheel_is_scoped_to_canvas_under_pointer(self) -> None:
        entry = self.app.entry_widgets["geometry.length_m"]
        entry_canvas = self.app._canvas_for_widget(entry)

        self.assertIsNotNone(entry_canvas)
        self.assertIsNone(self.app._canvas_for_widget(self.app.detail_report_text))
        self.assertEqual(self.app.root.bind("<MouseWheel>"), "")
        self.assertEqual(self.app.detail_report_text.bind("<MouseWheel>"), "")

        assert entry_canvas is not None
        with patch.object(entry_canvas, "yview_scroll") as scroll:
            result = self.app._on_mousewheel(SimpleNamespace(widget=entry, delta=-120))

        self.assertEqual(result, "break")
        scroll.assert_called_once_with(1, "units")

        with patch.object(entry_canvas, "yview_scroll") as scroll:
            result = self.app._on_mousewheel(
                SimpleNamespace(widget=self.app.detail_report_text, delta=-120)
            )

        self.assertIsNone(result)
        scroll.assert_not_called()

    def test_visible_units_and_terminology_are_consistent(self) -> None:
        labels = " | ".join(
            str(widget.cget("text")) for widget in self.app.field_label_widgets.values()
        )

        self.assertIn("Su sicakligi (°C)", labels)
        self.assertIn("m³", labels)
        self.assertIn("m/s", labels)
        self.assertIn("10^-6/bar", labels)
        self.assertIn("10^-6/°C", labels)
        self.assertNotIn("degC", labels)
        self.assertNotIn(" m3", labels)

        self.assertEqual(self.app.notebook.tab(2, "text"), "Saha Kontrol")
        self.assertEqual(self.app.side_panel_toggle_button.cget("text"), "Detay Panelini Gizle")
        self.assertEqual(self.app.help_notes_toggle_button.cget("text"), "Aciklamalari Goster")

    def test_reference_badge_uses_single_table_term(self) -> None:
        self.app.air_vars["temperature_c"].set("10")
        self.app.air_vars["pressure_bar"].set("50")
        self.app.air_a_mode_var.set(REFERENCE_A_MODE)
        self.app._on_air_a_mode_changed()
        self.app.air_a_reference_var.set(BOTAS_REFERENCE_OPTION_LABEL)

        self.app._on_air_a_reference_changed()

        self.assertEqual(self.app.coefficient_source_vars["air_a"].get(), "TABLO")
        self.assertNotIn("REFERANS", self.app.coefficient_source_vars["air_a"].get())

    def test_flow_checklist_stays_visible_when_explanations_hidden(self) -> None:
        self.assertFalse(self.app.help_notes_visible_var.get())
        self.assertTrue(self.app.workflow_steps_label.grid_info())
        self.assertIn("P=1.0 bar", self.app.workflow_steps_var.get())

        self.app._toggle_help_notes_visibility()

        self.assertTrue(self.app.workflow_steps_label.grid_info())
        self.assertEqual(self.app.help_notes_toggle_button.cget("text"), "Aciklamalari Gizle")

    def test_small_screen_hides_detail_panel_but_keeps_critical_buttons(self) -> None:
        self.assertTrue(self.app._should_auto_hide_side_panel(1024, 700))

        self.app._apply_responsive_side_panel(1024, 700)

        self.assertFalse(self.app.side_panel_visible_var.get())
        self.assertNotIn(str(self.app.side_panel), {str(p) for p in self.app.content_pane.panes()})
        self.assertEqual(self.app.save_report_button.cget("text"), "Raporu Kaydet")
        self.assertTrue(self.app.save_report_button.winfo_manager())
        self.assertTrue(self.app.air_test_button.winfo_manager())
        self.assertTrue(self.app.pressure_test_button.winfo_manager())
        self.assertEqual(self.app.side_panel_toggle_button.cget("text"), "Detay Panelini Goster")

        self.app._toggle_side_panel_visibility()
        self.app._apply_responsive_side_panel(1024, 700)

        self.assertTrue(self.app.side_panel_visible_var.get())
        self.assertIn(str(self.app.side_panel), {str(p) for p in self.app.content_pane.panes()})


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

from hidrostatik_test.ui.app import (
    AUTO_A_MODE,
    AUTO_B_MODE,
    MANUAL_A_MODE,
    MANUAL_B_MODE,
    REFERENCE_A_MODE,
    REFERENCE_B_MODE,
    HydrostaticTestApp,
)
from hidrostatik_test.app_metadata import APP_VERSION, SPEC_DOCUMENT_CODE


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

    def test_temperature_change_marks_computed_air_a_stale(self) -> None:
        self.app.air_vars["temperature_c"].set("20")
        self.app.air_vars["pressure_bar"].set("80")

        self.assertTrue(self.app._calculate_air_a(log_result=False))
        self.assertEqual(self.app.coefficient_states["air_a"], "computed")

        self.app.air_vars["temperature_c"].set("21")

        self.assertEqual(self.app.coefficient_states["air_a"], "stale")

    def test_pressure_evaluation_auto_calculates_a_and_b(self) -> None:
        self._fill_geometry()
        self.app.pressure_vars["temperature_c"].set("20")
        self.app.pressure_vars["pressure_bar"].set("80")
        self.app.pressure_vars["delta_t_c"].set("0.6")
        self.app.pressure_vars["actual_pressure_change_bar"].set("2.1")
        self.app.b_helper_vars["steel_alpha_micro_per_c"].set("12.0")
        self.app.use_b_helper_var.set(True)

        self.app._run_pressure_test()

        self.assertEqual(self.app.decision_status_var.get(), "BASARILI")
        self.assertNotEqual(self.app.pressure_vars["a_micro_per_bar"].get(), "")
        self.assertNotEqual(self.app.pressure_vars["b_micro_per_c"].get(), "")
        self.assertEqual(self.app.coefficient_states["pressure_a"], "computed")
        self.assertEqual(self.app.coefficient_states["pressure_b"], "computed")

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
        self.assertEqual(self.app.coefficient_states["air_a"], "manual")
        self.assertIn("Manuel", self.app.air_a_mode_var.get())

    def test_air_evaluation_accepts_reference_a_mode(self) -> None:
        self._fill_geometry()
        self.app.air_a_mode_var.set(REFERENCE_A_MODE)
        self.app._on_air_a_mode_changed()
        self.app.air_a_reference_var.set("IAPWS95 | T=15 degC | P=80 bar")
        self.app._on_air_a_reference_changed()
        self.app.air_vars["actual_added_water_m3"].set("0.0079")

        self.app._run_air_test()

        self.assertEqual(self.app.decision_status_var.get(), "BASARILI")
        self.assertEqual(self.app.coefficient_states["air_a"], "reference")
        self.assertEqual(self.app.air_vars["a_micro_per_bar"].get(), "45.786845")

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
        self.assertEqual(self.app.coefficient_states["pressure_b"], "manual")
        self.assertFalse(self.app.use_b_helper_var.get())
        self.assertEqual(self.app.b_helper_vars["water_beta_micro_per_c"].get(), "")

    def test_pressure_evaluation_accepts_reference_b_mode(self) -> None:
        self._fill_geometry()
        self.app.pressure_b_mode_var.set(REFERENCE_B_MODE)
        self.app._on_pressure_b_mode_changed()
        self.app.pressure_b_reference_var.set("IAPWS95 | T=20 degC | P=100 bar")
        self.app.b_helper_vars["steel_alpha_micro_per_c"].set("12.0")
        self.app._on_pressure_b_reference_changed()
        self.app.pressure_vars["temperature_c"].set("20")
        self.app.pressure_vars["pressure_bar"].set("80")
        self.app.pressure_vars["delta_t_c"].set("0.6")
        self.app.pressure_vars["actual_pressure_change_bar"].set("2.1")

        self.app._run_pressure_test()

        self.assertEqual(self.app.decision_status_var.get(), "BASARILI")
        self.assertEqual(self.app.coefficient_states["pressure_b"], "reference")
        self.assertTrue(self.app.use_b_helper_var.get())
        self.assertEqual(self.app.b_helper_vars["water_beta_micro_per_c"].get(), "221.153338")

    def test_pressure_evaluation_accepts_reference_a_mode(self) -> None:
        self._fill_geometry()
        self.app.pressure_a_mode_var.set(REFERENCE_A_MODE)
        self.app._on_pressure_a_mode_changed()
        self.app.pressure_a_reference_var.set("IAPWS95 | T=10 degC | P=50 bar")
        self.app._on_pressure_a_reference_changed()
        self.app.pressure_vars["temperature_c"].set("20")
        self.app.pressure_vars["pressure_bar"].set("80")
        self.app.pressure_vars["delta_t_c"].set("0.6")
        self.app.pressure_vars["actual_pressure_change_bar"].set("2.1")
        self.app.b_helper_vars["steel_alpha_micro_per_c"].set("12.0")
        self.app.use_b_helper_var.set(True)

        self.app._run_pressure_test()

        self.assertEqual(self.app.decision_status_var.get(), "BASARILI")
        self.assertEqual(self.app.coefficient_states["pressure_a"], "reference")
        self.assertEqual(self.app.pressure_vars["a_micro_per_bar"].get(), "47.193089")

    def test_air_control_table_summary_updates_after_a_calculation(self) -> None:
        self.app.air_vars["temperature_c"].set("10")
        self.app.air_vars["pressure_bar"].set("30")

        self.assertTrue(self.app._calculate_air_a(log_result=False))
        self.assertIn("Kurum ici tablo A = 46.990000", self.app.air_control_table_var.get())
        self.assertIn("A farki =", self.app.air_control_table_var.get())

    def test_pressure_control_table_summary_updates_after_a_and_b_calculation(self) -> None:
        self.app.pressure_vars["temperature_c"].set("15")
        self.app.pressure_vars["pressure_bar"].set("80")
        self.app.b_helper_vars["steel_alpha_micro_per_c"].set("12.0")
        self.app.use_b_helper_var.set(True)

        self.assertTrue(self.app._calculate_pressure_a(log_result=False))
        self.assertTrue(self.app._calculate_b_helper(log_result=False))
        self.assertIn("Kurum ici tablo A = 45.434000, B = 134.050000.", self.app.pressure_control_table_var.get())
        self.assertIn("B farki =", self.app.pressure_control_table_var.get())

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
        labels = [self.app.notebook.tab(index, "text") for index in range(self.app.notebook.index("end"))]

        self.assertEqual(labels, ["Hava Icerik Testi", "Basinc Degisim Testi", "Saha Kontrol"])

    def test_default_water_backend_is_coolprop(self) -> None:
        self.assertEqual(self.app.water_backend_var.get(), "CoolProp EOS [coolprop]")
        self.assertIn("Secili backend: CoolProp EOS", self.app.water_backend_summary_var.get())

    def test_check_summary_counts_checked_controls(self) -> None:
        self.app.control_check_vars["ambient_temp"].set(True)
        self.app.control_check_vars["thermal_balance"].set(True)

        self.assertIn("2 / 10", self.app.check_summary_var.get())
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
        self.assertIn("0 / 10", self.app.check_summary_var.get())

    def test_catalog_selection_populates_geometry_fields(self) -> None:
        size_label = next(option for option in self.app.pipe_size_combo.cget("values") if option.startswith("NPS 16 "))
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

        self.assertEqual(labels, ["Dosya", "Rapor", "Guncelleme", "Hakkinda"])

    def test_side_panel_uses_tabbed_workspace(self) -> None:
        labels = [self.app.side_notebook.tab(index, "text") for index in range(self.app.side_notebook.index("end"))]

        self.assertEqual(labels, ["Rehber", "Durum", "Kayit"])

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
        self.assertEqual(self.app.coefficient_states["pressure_a"], "empty")
        self.assertEqual(self.app.coefficient_states["pressure_b"], "empty")

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

    def test_stale_coefficient_sets_live_warning_message(self) -> None:
        self.app.air_vars["temperature_c"].set("20")
        self.app.air_vars["pressure_bar"].set("80")
        self.assertTrue(self.app._calculate_air_a(log_result=False))

        self.app.air_vars["pressure_bar"].set("81")

        self.assertEqual(self.app.coefficient_states["air_a"], "stale")
        self.assertIn("yeniden hesaplayin", self.app.field_message_vars["air.a_micro_per_bar"].get())
        self.assertIn("guncellenmeli", self.app.live_notice_var.get())

    def test_backend_change_marks_auto_coefficients_stale(self) -> None:
        self.app.air_vars["temperature_c"].set("20")
        self.app.air_vars["pressure_bar"].set("80")
        self.assertTrue(self.app._calculate_air_a(log_result=False))
        self.assertEqual(self.app.coefficient_states["air_a"], "computed")

        self.app.water_backend_var.set("Table Interpolation v1 [table_v1]")
        self.app._on_water_backend_changed()

        self.assertEqual(self.app.coefficient_states["air_a"], "stale")
        self.assertIn("Table Interpolation v1", self.app.water_backend_summary_var.get())
        self.assertIn("Backend secimi degisti", self.app.air_backend_comparison_var.get())

    def test_compare_air_backend_updates_summary(self) -> None:
        self.app.air_vars["temperature_c"].set("20")
        self.app.air_vars["pressure_bar"].set("80")

        self.app._compare_active_backend()

        self.assertIn("Hava A karsilastirmasi", self.app.air_backend_comparison_var.get())
        self.assertIn("CoolProp EOS", self.app.air_backend_comparison_var.get())
        self.assertIn("Table Interpolation v1", self.app.air_backend_comparison_var.get())
        self.assertEqual(self.app.active_backend_comparison_var.get(), self.app.air_backend_comparison_var.get())

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

    def test_apply_available_update_uses_selected_download_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target_dir = Path(temp_dir) / "updates"
            self.app.update_download_dir_var.set(str(target_dir))
            self.app.latest_update_info = type(
                "UpdateInfoLike",
                (),
                {
                    "update_available": True,
                    "latest_version": "9.9.9",
                },
            )()
            captured: dict[str, object] = {}

            class _FakeThread:
                def start(self) -> None:
                    return None

            def fake_thread(*, target, args=(), daemon=None):
                captured["target"] = target
                captured["args"] = args
                captured["daemon"] = daemon
                return _FakeThread()

            with patch("hidrostatik_test.ui.app.messagebox.askyesnocancel", return_value=False), patch(
                "hidrostatik_test.ui.app.threading.Thread",
                side_effect=fake_thread,
            ):
                self.app._apply_available_update()

            self.assertTrue(self.app.update_install_in_progress)
            self.assertEqual(captured["target"], self.app._perform_update_install)
            self.assertEqual(captured["args"], (target_dir,))
            self.assertIn(str(target_dir), self.app.update_detail_var.get())

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
        self.assertIn(f"B secenegi: {AUTO_B_MODE}", report)
        self.assertIn("Su backend'i: CoolProp EOS", report)
        self.assertIn("Hava backend karsilastirmasi: Hava A karsilastirmasi", report)
        self.assertIn("Basinc backend karsilastirmasi: Basinc A/B karsilastirmasi", report)
        self.assertIn("A referans noktasi: -", report)
        self.assertIn("B referans noktasi: -", report)
        self.assertIn("Dis cap (mm): 406.4", report)
        self.assertIn("Su basinci (bar): 80", report)
        self.assertIn("dT = Tilk - Tson", report)
        self.assertIn("Pa = Pilk - Pson", report)
        self.assertIn("Operasyon Kontrol Noktalari", report)
        self.assertIn("Pig Hiz Hesabi", report)
        self.assertIn("[x] Dolum sirasinda hava sicakligi +2 degC limitine gore kontrol edildi (10.1)", report)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tkinter as tk
import unittest
from tkinter import font as tkfont

from hidrostatik_test.ui.wizard import (
    NUM_STEPS,
    REPORT_SIDE_TAB_INDEX,
    STEP_DESC_FONT_SIZE,
    WIZARD_STEP_TAB_INDEX,
    WIZARD_STEP_TAB_KEYS,
    WizardController,
    WizardStepIndicator,
)


class FakeVar:
    def __init__(self, value: str = "") -> None:
        self._value = value

    def get(self) -> str:
        return self._value

    def set(self, value: str) -> None:
        self._value = value


class FakeNotebook:
    def __init__(self) -> None:
        self.selected: list[int] = []

    def select(self, index: int) -> None:
        self.selected.append(index)


class FakeButton:
    def __init__(self) -> None:
        self.state = "normal"
        self.text = ""

    def configure(self, **kwargs: object) -> None:
        self.state = str(kwargs.get("state", self.state))
        self.text = str(kwargs.get("text", self.text))


class FakePipe:
    def __init__(
        self,
        outside_diameter_mm: float = 406.4,
        wall_thickness_mm: float = 8.74,
        length_m: float = 1000.0,
    ) -> None:
        self.outside_diameter_mm = outside_diameter_mm
        self.wall_thickness_mm = wall_thickness_mm
        self.length_m = length_m


class FakeSessionManager:
    def __init__(self) -> None:
        self.states: list[dict[str, object]] = []

    def update_wizard_state(self, state: dict[str, object]) -> None:
        self.states.append(state)

    def get_active_session(self) -> None:
        return None


class FakeApp:
    def __init__(self) -> None:
        self.banners: list[tuple[str, str]] = []
        self.geometry_vars = {
            "outside_diameter_mm": FakeVar(),
            "wall_thickness_mm": FakeVar(),
            "length_m": FakeVar(),
        }
        self.air_vars = {
            "temperature_c": FakeVar(),
            "pressure_bar": FakeVar(),
            "a_micro_per_bar": FakeVar(),
            "k_factor": FakeVar("1.02"),
            "pressure_rise_bar": FakeVar(),
            "actual_added_water_m3": FakeVar(),
        }
        self.pressure_vars = {
            "temperature_c": FakeVar(),
            "pressure_bar": FakeVar(),
            "a_micro_per_bar": FakeVar(),
            "b_micro_per_c": FakeVar(),
            "delta_t_c": FakeVar(),
            "actual_pressure_change_bar": FakeVar(),
        }
        self.use_b_helper_var = _BoolVar(True)  # type: ignore[assignment]
        self.pressure_b_mode_var = FakeVar("Otomatik")
        self.decision_status_var = FakeVar("BEKLIYOR")
        self.notebook = FakeNotebook()
        self.side_notebook = FakeNotebook()
        self.side_panel_visible_var = _BoolVar(True)  # type: ignore[assignment]
        self.geometry_segments: list[object] = []
        self.session_manager = FakeSessionManager()
        self.active_tab = "pressure"
        self.selected_tab_keys: list[str] = []
        self.panel_refreshes = 0
        self.detail_refreshes = 0
        self.side_panel_applied = 0

    def _set_banner(self, message: str, level: str = "info") -> None:
        self.banners.append((message, level))

    def _show_active_input_panel(self) -> None:
        self.panel_refreshes += 1

    def _update_workflow_hint(self) -> None:
        pass

    def _select_tab_by_key(self, tab_key: str) -> None:
        self.selected_tab_keys.append(tab_key)
        self.active_tab = tab_key

    def _refresh_detail_reports(self) -> None:
        self.detail_refreshes += 1

    def _apply_side_panel_visibility(self) -> None:
        self.side_panel_applied += 1

    def _active_tab_key(self) -> str:
        return self.active_tab

    @property
    def last_banner(self) -> tuple[str, str]:
        return self.banners[-1]


class _BoolVar:
    def __init__(self, value: bool = False) -> None:
        self._value = value

    def get(self) -> bool:
        return self._value

    def set(self, value: bool) -> None:
        self._value = value


class FakeIndicator:
    def __init__(self) -> None:
        self.current_step = 0
        self.completed_steps: set[int] = set()
        self.refresh_count = 0

    def _refresh(self) -> None:
        self.refresh_count += 1

    def advance(self) -> None:
        self.completed_steps.add(self.current_step)
        if self.current_step < NUM_STEPS - 1:
            self.current_step += 1
        self._refresh()

    def retreat(self) -> None:
        if self.current_step > 0:
            self.current_step -= 1
        self._refresh()

    def step_status(self, step: int) -> str:
        if step in self.completed_steps:
            return "Tamamlandi"
        if step == self.current_step:
            return "Aktif adim"
        return "Bekliyor"


def make_controller(app: FakeApp, step: int = 0) -> WizardController:
    controller = WizardController(app)
    controller.active = True
    controller.step_indicator = FakeIndicator()
    controller.step_indicator.current_step = step
    controller.step_info_var = FakeVar()  # type: ignore[assignment]
    controller.next_button = FakeButton()  # type: ignore[assignment]
    controller.back_button = FakeButton()  # type: ignore[assignment]
    return controller


def fill_pressure(app: FakeApp, *, b: str = "3.5", dt: str = "0,6", pa: str = "2,1") -> None:
    app.pressure_vars["temperature_c"].set("20")
    app.pressure_vars["pressure_bar"].set("80")
    app.pressure_vars["a_micro_per_bar"].set("45")
    app.pressure_vars["b_micro_per_c"].set(b)
    app.pressure_vars["delta_t_c"].set(dt)
    app.pressure_vars["actual_pressure_change_bar"].set(pa)


class WizardStepMappingTests(unittest.TestCase):
    def test_step_to_tab_mapping_is_fixed_and_testable(self) -> None:
        self.assertEqual(WIZARD_STEP_TAB_INDEX, (0, 1, 1, 1))
        self.assertEqual(WIZARD_STEP_TAB_KEYS, ("air", "pressure", "pressure", "pressure"))
        self.assertEqual(len(WIZARD_STEP_TAB_INDEX), NUM_STEPS)
        self.assertEqual(len(WIZARD_STEP_TAB_KEYS), NUM_STEPS)

    def test_sync_selects_expected_tab_for_every_step(self) -> None:
        app = FakeApp()
        controller = make_controller(app)

        for step, expected_key in enumerate(WIZARD_STEP_TAB_KEYS):
            with self.subTest(step=step):
                controller.step_indicator.current_step = step
                app.selected_tab_keys.clear()
                controller._sync_app_state()
                self.assertEqual(app.selected_tab_keys, [expected_key])

    def test_report_step_opens_decision_report_panel(self) -> None:
        app = FakeApp()
        controller = make_controller(app, step=WizardController.REPORT)
        before = app.detail_refreshes

        controller._sync_app_state()

        self.assertEqual(app.selected_tab_keys, ["pressure"])
        self.assertEqual(app.side_notebook.selected, [REPORT_SIDE_TAB_INDEX])
        self.assertGreater(app.detail_refreshes, before)

    def test_report_step_makes_hidden_side_panel_visible(self) -> None:
        app = FakeApp()
        app.side_panel_visible_var.set(False)
        controller = make_controller(app, step=WizardController.REPORT)

        controller._sync_app_state()

        self.assertTrue(app.side_panel_visible_var.get())
        self.assertEqual(app.side_panel_applied, 1)

    def test_step_info_text_contains_status_word(self) -> None:
        app = FakeApp()
        controller = make_controller(app, step=1)

        controller._sync_app_state()

        info = controller.step_info_var.get()
        self.assertIn("Adim 2/4", info)
        self.assertIn("Aktif adim", info)


class WizardGeometryValidationTests(unittest.TestCase):
    def test_empty_manual_geometry_is_blocked(self) -> None:
        app = FakeApp()
        controller = make_controller(app)

        self.assertFalse(controller._validate_geometry())
        self.assertEqual(app.last_banner[1], "warning")

    def test_manual_geometry_accepts_turkish_decimal_comma(self) -> None:
        app = FakeApp()
        app.geometry_vars["outside_diameter_mm"].set("406,4")
        app.geometry_vars["wall_thickness_mm"].set("8,74")
        app.geometry_vars["length_m"].set("1000")
        controller = make_controller(app)

        self.assertTrue(controller._validate_geometry())
        self.assertEqual(app.last_banner[1], "success")

    def test_nan_manual_geometry_is_rejected(self) -> None:
        app = FakeApp()
        app.geometry_vars["outside_diameter_mm"].set("nan")
        app.geometry_vars["wall_thickness_mm"].set("8,74")
        app.geometry_vars["length_m"].set("1000")
        controller = make_controller(app)

        self.assertFalse(controller._validate_geometry())
        self.assertEqual(app.last_banner[1], "error")
        self.assertIn("sonlu", app.last_banner[0])

    def test_segments_can_unblock_geometry_without_manual_values(self) -> None:
        app = FakeApp()
        app.geometry_segments = [{"pipe": FakePipe(), "nps_label": "16", "schedule_label": "STD"}]
        controller = make_controller(app)

        self.assertTrue(controller._validate_geometry())
        self.assertEqual(app.last_banner[1], "success")

    def test_invalid_segment_is_rejected_with_index(self) -> None:
        app = FakeApp()
        app.geometry_segments = [
            {"pipe": FakePipe()},
            {"pipe": FakePipe(outside_diameter_mm=100.0, wall_thickness_mm=50.0)},
        ]
        controller = make_controller(app)

        self.assertFalse(controller._validate_geometry())
        self.assertIn("Segment 2", app.last_banner[0])


class WizardParameterValidationTests(unittest.TestCase):
    def test_no_test_inputs_is_blocked(self) -> None:
        app = FakeApp()
        controller = make_controller(app, step=WizardController.PARAMETERS)

        self.assertFalse(controller._validate_parameters())
        self.assertEqual(app.last_banner[1], "warning")

    def test_air_only_parameters_are_accepted(self) -> None:
        app = FakeApp()
        app.air_vars["temperature_c"].set("20")
        app.air_vars["pressure_bar"].set("80")
        app.air_vars["a_micro_per_bar"].set("45")
        controller = make_controller(app, step=WizardController.PARAMETERS)

        self.assertTrue(controller._validate_parameters())

    def test_out_of_range_a_is_blocked(self) -> None:
        app = FakeApp()
        app.air_vars["temperature_c"].set("20")
        app.air_vars["pressure_bar"].set("80")
        app.air_vars["a_micro_per_bar"].set("500")
        controller = make_controller(app, step=WizardController.PARAMETERS)

        self.assertFalse(controller._validate_parameters())
        self.assertIn("araliginda", app.last_banner[0])

    def test_pressure_parameters_with_auto_b_are_accepted(self) -> None:
        app = FakeApp()
        fill_pressure(app)
        app.pressure_b_mode_var.set("Otomatik")
        controller = make_controller(app, step=WizardController.PARAMETERS)

        self.assertTrue(controller._validate_parameters())

    def test_auto_b_must_be_ready(self) -> None:
        app = FakeApp()
        fill_pressure(app, b="")
        app.pressure_b_mode_var.set("Otomatik")
        controller = make_controller(app, step=WizardController.PARAMETERS)

        self.assertFalse(controller._validate_parameters())
        self.assertIn("otomatik/tablo", app.last_banner[0])

    def test_manual_b_must_be_filled(self) -> None:
        app = FakeApp()
        fill_pressure(app, b="")
        app.pressure_b_mode_var.set("Manuel")
        controller = make_controller(app, step=WizardController.PARAMETERS)

        self.assertFalse(controller._validate_parameters())
        self.assertIn("manuel", app.last_banner[0])

    def test_manual_negative_b_is_accepted(self) -> None:
        app = FakeApp()
        fill_pressure(app, b="-3,5")
        app.pressure_b_mode_var.set("Manuel")
        controller = make_controller(app, step=WizardController.PARAMETERS)

        self.assertTrue(controller._validate_parameters())

    def test_out_of_range_delta_t_is_blocked(self) -> None:
        app = FakeApp()
        fill_pressure(app, dt="25")
        controller = make_controller(app, step=WizardController.PARAMETERS)

        self.assertFalse(controller._validate_parameters())
        self.assertIn("dT", app.last_banner[0])

    def test_out_of_range_pa_is_blocked(self) -> None:
        app = FakeApp()
        fill_pressure(app, pa="60")
        controller = make_controller(app, step=WizardController.PARAMETERS)

        self.assertFalse(controller._validate_parameters())
        self.assertIn("Pa", app.last_banner[0])


class WizardExecutionValidationTests(unittest.TestCase):
    def test_pending_decision_blocks_advance(self) -> None:
        app = FakeApp()
        app.decision_status_var.set("BEKLIYOR")
        controller = make_controller(app, step=WizardController.EXECUTION)

        self.assertFalse(controller._validate_execution())
        controller._go_next()
        self.assertEqual(controller.step_indicator.current_step, WizardController.EXECUTION)

    def test_unverifiable_decision_blocks_advance(self) -> None:
        app = FakeApp()
        app.decision_status_var.set("DOGRULANAMADI")
        controller = make_controller(app, step=WizardController.EXECUTION)

        self.assertFalse(controller._validate_execution())
        self.assertIn("DOGRULANAMADI", app.last_banner[0])

    def test_stale_decision_blocks_advance(self) -> None:
        app = FakeApp()
        app.decision_status_var.set("STALE")
        controller = make_controller(app, step=WizardController.EXECUTION)

        self.assertFalse(controller._validate_execution())
        self.assertIn("STALE", app.last_banner[0])

    def test_successful_decision_allows_advance(self) -> None:
        app = FakeApp()
        app.decision_status_var.set("BASARILI")
        controller = make_controller(app, step=WizardController.EXECUTION)

        self.assertTrue(controller._validate_execution())

    def test_failed_decision_still_allows_advance(self) -> None:
        app = FakeApp()
        app.decision_status_var.set("BASARISIZ")
        controller = make_controller(app, step=WizardController.EXECUTION)

        self.assertTrue(controller._validate_execution())

    def test_stale_coefficient_blocks_advance_even_with_decision(self) -> None:
        app = FakeApp()
        app.active_tab = "air"
        app.decision_status_var.set("BASARILI")
        app.coefficient_source_vars = {"air_a": FakeVar("YENILE")}
        controller = make_controller(app, step=WizardController.EXECUTION)

        self.assertFalse(controller._validate_execution())
        self.assertIn("STALE", app.last_banner[0])

    def test_guncellenmeli_status_blocks_advance(self) -> None:
        app = FakeApp()
        app.decision_status_var.set("BASARILI")
        app.coefficient_status_vars = {
            "pressure_a": FakeVar("Hazir: otomatik hesap"),
            "pressure_b": FakeVar("Guncellenmeli: kosullar degisti"),
        }
        controller = make_controller(app, step=WizardController.EXECUTION)

        self.assertFalse(controller._validate_execution())


class WizardCompletionTests(unittest.TestCase):
    def test_finish_marks_completed_and_opens_report(self) -> None:
        app = FakeApp()
        app.decision_status_var.set("BASARILI")
        controller = make_controller(app, step=WizardController.REPORT)

        controller._go_next()

        self.assertTrue(controller.completed)
        self.assertIn(WizardController.REPORT, controller.step_indicator.completed_steps)
        self.assertEqual(controller.step_indicator.current_step, WizardController.REPORT)
        self.assertEqual(app.side_notebook.selected, [REPORT_SIDE_TAB_INDEX])
        self.assertIn("tamamlandi", app.last_banner[0].lower())
        self.assertEqual(controller.next_button.state, "disabled")
        self.assertEqual(controller.next_button.text, "Tamamlandi")
        self.assertEqual(app.session_manager.states[-1]["completed"], True)

    def test_going_back_after_finish_reenables_next(self) -> None:
        app = FakeApp()
        app.decision_status_var.set("BASARILI")
        controller = make_controller(app, step=WizardController.REPORT)
        controller._go_next()

        controller._go_back()

        self.assertEqual(controller.step_indicator.current_step, WizardController.EXECUTION)
        self.assertEqual(controller.next_button.state, "normal")
        self.assertEqual(controller.next_button.text, "Ileri >>")


class WizardStepIndicatorTkTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk kullanilamiyor: {exc}")
        self.root.withdraw()

    def tearDown(self) -> None:
        self.root.destroy()

    def test_circles_are_keyboard_focusable(self) -> None:
        clicked: list[int] = []
        indicator = WizardStepIndicator(self.root, on_step_click=clicked.append)
        indicator.pack()

        circle = indicator.step_circles[0]
        self.assertTrue(circle.cget("takefocus"))
        self.assertTrue(circle.bind("<Return>"))
        self.assertTrue(circle.bind("<space>"))
        self.assertTrue(circle.bind("<KP_Enter>"))

        indicator._on_step_key_activated(2)
        self.assertEqual(clicked, [2])

    def test_step_description_font_is_at_least_eight(self) -> None:
        indicator = WizardStepIndicator(self.root)
        indicator.pack()

        self.assertGreaterEqual(STEP_DESC_FONT_SIZE, 8)
        label_font = tkfont.Font(root=self.root, font=indicator.step_desc_labels[0].cget("font"))
        self.assertGreaterEqual(int(label_font.actual()["size"]), 8)

    def test_advance_on_last_step_marks_completed(self) -> None:
        indicator = WizardStepIndicator(self.root)
        indicator.set_step(NUM_STEPS - 1)

        indicator.advance()

        self.assertEqual(indicator.current_step, NUM_STEPS - 1)
        self.assertIn(NUM_STEPS - 1, indicator.completed_steps)

    def test_step_status_is_available_as_text(self) -> None:
        indicator = WizardStepIndicator(self.root)
        indicator.set_step(1)

        self.assertEqual(indicator.step_status(0), "Bekliyor")
        self.assertEqual(indicator.step_status(1), "Aktif adim")

        indicator.set_completed(0)
        self.assertEqual(indicator.step_status(0), "Tamamlandi")


if __name__ == "__main__":
    unittest.main()

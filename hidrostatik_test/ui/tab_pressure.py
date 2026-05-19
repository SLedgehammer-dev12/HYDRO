from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from ..data.ab_control_table import ABControlTableError
from ..data.botas_reference_table import (
    BOTAS_REFERENCE_TABLE_LABEL,
    lookup_botas_reference_point,
)
from ..data.gail_reference_table import (
    GAIL_REFERENCE_TABLE_LABEL,
    lookup_gail_reference_point,
)
from ..domain.hydrotest_core import (
    PressureVariationInputs,
    ValidationError,
    calculate_b_coefficient,
    calculate_water_compressibility_a,
    calculate_water_thermal_expansion_beta,
    evaluate_pressure_variation_test,
)
from ..domain.pressure_profile import (
    SectionPressureProfileInputs,
    SectionPressureProfileResult,
    evaluate_section_pressure_profile,
    get_location_class_rule,
)
from .tab_pressure_detail import PressureDetailMixin

if TYPE_CHECKING:
    from .app_main import HydrostaticTestApp


class PressureTabMixin:
    def _build_pressure_input_panel(self, frame: ttk.Frame) -> None:
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        conditions_frame = ttk.LabelFrame(frame, text="Basinc Testi - Kosullar", padding=12)
        conditions_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        conditions_frame.columnconfigure(1, weight=1)
        conditions_frame.columnconfigure(3, weight=1)
        self._add_entry(
            conditions_frame,
            0,
            "Su sicakligi (degC)",
            self.pressure_vars["temperature_c"],
            field_key="pressure.temperature_c",
        )
        self._add_entry(
            conditions_frame,
            0,
            "Su basinci (bar)",
            self.pressure_vars["pressure_bar"],
            field_key="pressure.pressure_bar",
            column=2,
        )
        self._add_entry(
            conditions_frame,
            1,
            "A (10^-6 / bar)",
            self.pressure_vars["a_micro_per_bar"],
            field_key="pressure.a_micro_per_bar",
        )
        self._add_entry(
            conditions_frame,
            1,
            "B (10^-6 / degC)",
            self.pressure_vars["b_micro_per_c"],
            field_key="pressure.b_micro_per_c",
            column=2,
        )
        self.inline_coefficient_source_badges["pressure_a"] = self._create_source_badge(
            conditions_frame,
            key="pressure_a",
            registry=self.inline_coefficient_source_badges,
        )
        self.inline_coefficient_source_badges["pressure_a"].grid(row=2, column=0, sticky="w", pady=(0, 6))
        ttk.Label(
            conditions_frame,
            textvariable=self.coefficient_status_vars["pressure_a"],
            foreground="#8A6D3B",
        ).grid(row=2, column=1, sticky="w", pady=(0, 6))
        self.inline_coefficient_source_badges["pressure_b"] = self._create_source_badge(
            conditions_frame,
            key="pressure_b",
            registry=self.inline_coefficient_source_badges,
        )
        self.inline_coefficient_source_badges["pressure_b"].grid(row=2, column=2, sticky="w", pady=(0, 6))
        ttk.Label(
            conditions_frame,
            textvariable=self.coefficient_status_vars["pressure_b"],
            foreground="#8A6D3B",
        ).grid(row=2, column=3, sticky="w", pady=(0, 6))
        ttk.Label(conditions_frame, text="A secenegi").grid(row=3, column=0, sticky="w", pady=6)
        pressure_a_mode_combo = ttk.Combobox(
            conditions_frame,
            textvariable=self.pressure_a_mode_var,
            state="readonly",
            values=(self.AUTO_A_MODE, self.REFERENCE_A_MODE, self.MANUAL_A_MODE),
            width=24,
        )
        pressure_a_mode_combo.grid(row=3, column=1, sticky="ew", padx=(0, 12), pady=6)
        pressure_a_mode_combo.bind("<<ComboboxSelected>>", self._on_pressure_a_mode_changed)
        ttk.Label(conditions_frame, text="B secenegi").grid(row=3, column=2, sticky="w", pady=6)
        pressure_b_mode_combo = ttk.Combobox(
            conditions_frame,
            textvariable=self.pressure_b_mode_var,
            state="readonly",
            values=(self.AUTO_B_MODE, self.REFERENCE_B_MODE, self.MANUAL_B_MODE),
            width=24,
        )
        pressure_b_mode_combo.grid(row=3, column=3, sticky="ew", padx=(0, 12), pady=6)
        pressure_b_mode_combo.bind("<<ComboboxSelected>>", self._on_pressure_b_mode_changed)
        ttk.Label(conditions_frame, text="A referans tablosu").grid(row=4, column=0, sticky="w", pady=6)
        self.pressure_a_reference_combo = ttk.Combobox(
            conditions_frame,
            textvariable=self.pressure_a_reference_var,
            state="disabled",
            values=self.reference_option_labels,
            style="Hydro.neutral.TCombobox",
            width=24,
        )
        self.pressure_a_reference_combo.grid(row=4, column=1, sticky="ew", padx=(0, 12), pady=6)
        self.pressure_a_reference_combo.bind("<<ComboboxSelected>>", self._on_pressure_a_reference_changed)
        self._register_choice_widget(
            field_key="pressure.a_reference_table",
            widget=self.pressure_a_reference_combo,
            section="pressure",
            label="A referans tablosu",
            required=False,
        )
        ttk.Label(conditions_frame, text="B referans tablosu").grid(row=4, column=2, sticky="w", pady=6)
        self.pressure_b_reference_combo = ttk.Combobox(
            conditions_frame,
            textvariable=self.pressure_b_reference_var,
            state="disabled",
            values=self.reference_option_labels,
            style="Hydro.neutral.TCombobox",
            width=24,
        )
        self.pressure_b_reference_combo.grid(row=4, column=3, sticky="ew", padx=(0, 12), pady=6)
        self.pressure_b_reference_combo.bind("<<ComboboxSelected>>", self._on_pressure_b_reference_changed)
        self._register_choice_widget(
            field_key="pressure.b_reference_table",
            widget=self.pressure_b_reference_combo,
            section="pressure",
            label="B referans tablosu",
            required=False,
        )

        measurements_frame = ttk.LabelFrame(frame, text="Basinc Testi - Olculen Degerler", padding=12)
        measurements_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        measurements_frame.columnconfigure(1, weight=1)
        measurements_frame.columnconfigure(3, weight=1)
        self._add_entry(
            measurements_frame,
            0,
            "Su sicaklik degisimi (degC)",
            self.pressure_vars["delta_t_c"],
            field_key="pressure.delta_t_c",
        )
        ttk.Label(
            measurements_frame,
            text="dT = T_ilk - T_son",
            foreground="#6B7280",
        ).grid(row=0, column=2, sticky="w", pady=6)
        self._add_entry(
            measurements_frame,
            0,
            "Fiili basinc degisimi (bar)",
            self.pressure_vars["actual_pressure_change_bar"],
            field_key="pressure.actual_pressure_change_bar",
            column=2,
        )
        ttk.Label(
            measurements_frame,
            text="Pa = P_ilk - P_son",
            foreground="#6B7280",
        ).grid(row=0, column=4, sticky="w", pady=6)
        ttk.Label(measurements_frame, text="Celik preset").grid(row=1, column=0, sticky="w", pady=6)
        self.steel_preset_combo = ttk.Combobox(
            measurements_frame,
            textvariable=self.steel_preset_var,
            state="readonly",
            values=(
                "Karbon celik - 12.0",
                "Dusuk alasimli celik - 12.5",
                "Paslanmaz celik - 16.0",
                "Ozel",
            ),
            width=22,
        )
        self.steel_preset_combo.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=6)
        self.steel_preset_combo.bind("<<ComboboxSelected>>", self._on_steel_preset_changed)
        self._add_entry(
            measurements_frame,
            1,
            "Celik alpha (10^-6 / degC)",
            self.b_helper_vars["steel_alpha_micro_per_c"],
            field_key="helper.steel_alpha_micro_per_c",
            column=2,
        )
        self._add_entry(
            measurements_frame,
            2,
            "Su beta (10^-6 / degC)",
            self.b_helper_vars["water_beta_micro_per_c"],
            field_key="helper.water_beta_micro_per_c",
            readonly=True,
        )




    def _build_pressure_tab(self, frame: ttk.Frame) -> None:
        frame.columnconfigure(0, weight=1)

        input_wrapper = ttk.Frame(frame)
        input_wrapper.grid(row=0, column=0, sticky="ew")
        self._build_pressure_input_panel(input_wrapper)

        actions_frame = ttk.LabelFrame(frame, text="Hesap ve Karar", padding=12)
        actions_frame.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        actions_frame.columnconfigure(0, weight=1)
        self.pressure_a_calculate_button = self._create_progress_button(
            actions_frame,
            key="pressure_a_calculate",
            text="A Hesapla",
            command=self._on_pressure_a_calculate_button,
        )
        self.pressure_a_calculate_button.pack(side="left")
        self.b_helper_calculate_button = self._create_progress_button(
            actions_frame,
            key="pressure_b_calculate",
            text="B Hesapla",
            command=self._on_b_helper_calculate_button,
        )
        self.b_helper_calculate_button.pack(side="left", padx=(8, 0))
        self.pressure_test_button = self._create_progress_button(
            actions_frame,
            key="pressure_test",
            text="Basinc Testini Degerlendir",
            command=self._on_pressure_test_button,
        )
        self.pressure_test_button.pack(side="left", padx=(8, 0))

        reference_frame = ttk.LabelFrame(frame, text="Katsayi ve Referans Ozeti", padding=12)
        reference_frame.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        reference_frame.columnconfigure(0, weight=1)
        self._register_help_note(ttk.Label(
            reference_frame,
            text=(
                "Basinc degisim testinde tum girisler ve hesaplama bu panel uzerinden yapilir. "
                "A/B katsayi durumu, backend karsilastirmasi ve kontrol tablosu ozeti asagida gosterilir."
            ),
            wraplength=self.workspace_wraplength,
            justify="left",
        )).grid(row=0, column=0, sticky="ew")
        ttk.Label(
            reference_frame,
            textvariable=self.pressure_backend_comparison_var,
            wraplength=self.workspace_wraplength,
            justify="left",
            foreground="#35506B",
        ).grid(row=1, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(
            reference_frame,
            textvariable=self.pressure_control_table_var,
            wraplength=self.workspace_wraplength,
            justify="left",
            foreground="#35506B",
        ).grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(
            frame,
            textvariable=self.section_feedback_vars["pressure"],
            foreground="#A4262C",
            wraplength=self.workspace_wraplength,
            justify="left",
        ).grid(row=3, column=0, sticky="w", pady=(12, 0))



    def _refresh_live_pressure_decision(self) -> None:
        if not self._ensure_live_pressure_inputs_ready():
            self._update_decision_card(
                "Basinc Degisim Testi",
                "BEKLIYOR",
                "Canli degerlendirme icin geometri, A, B, dT ve Pa tamamlanmali.",
            )
            return
        try:
            pipe = self._detail_pipe_snapshot()[0]
            assert pipe is not None
            result = evaluate_pressure_variation_test(
                PressureVariationInputs(
                    pipe=pipe,
                    a_micro_per_bar=float(self.pressure_vars["a_micro_per_bar"].get().strip().replace(",", ".")),
                    b_micro_per_c=float(self.pressure_vars["b_micro_per_c"].get().strip().replace(",", ".")),
                    delta_t_c=float(self.pressure_vars["delta_t_c"].get().strip().replace(",", ".")),
                    actual_pressure_change_bar=float(
                        self.pressure_vars["actual_pressure_change_bar"].get().strip().replace(",", ".")
                    ),
                )
            )
        except (AssertionError, ValidationError, ValueError):
            self._update_decision_card(
                "Basinc Degisim Testi",
                "DOGRULANAMADI",
                "Canli degerlendirme icin girilen degerlerden biri henuz gecerli degil.",
            )
            return
        status = "BASARILI" if result.passed else "BASARISIZ"
        self._update_decision_card(
            "Basinc Degisim Testi",
            status,
            (
                f"Canli sonuc: Pt = {result.theoretical_pressure_change_bar:.6f} bar, "
                f"ust sinir = {result.allowable_upper_pressure_change_bar:.6f} bar, "
                f"Pa = {result.actual_pressure_change_bar:.6f} bar, fark = {result.margin_bar:.6f} bar"
                f"\nKabul kriteri: (Pa - dP) <= 0.3 bar"
            ),
        )
        self._evaluation_fresh["pressure"] = True
        self.schema_status_var.set("HESAPLANDI")
        self._refresh_visual_schema()


    def _ensure_live_pressure_inputs_ready(self) -> bool:
        pipe, pipe_error = self._detail_pipe_snapshot()
        if pipe_error is not None or pipe is None:
            return False
        required_values = (
            self._safe_float(self.pressure_vars["a_micro_per_bar"].get()),
            self._safe_float(self.pressure_vars["b_micro_per_c"].get()),
            self._safe_float(self.pressure_vars["delta_t_c"].get()),
            self._safe_float(self.pressure_vars["actual_pressure_change_bar"].get()),
        )
        return all(value is not None for value in required_values)


    def _active_monitored_pressure_bar(self) -> float | None:
        active_tab = self._active_tab_key()
        if active_tab == "pressure":
            return self._safe_float(self.pressure_vars["pressure_bar"].get())
        if active_tab == "air":
            return self._safe_float(self.air_vars["pressure_bar"].get())
        pressure_value = self._safe_float(self.pressure_vars["pressure_bar"].get())
        if pressure_value is not None:
            return pressure_value
        return self._safe_float(self.air_vars["pressure_bar"].get())


    def _section_pressure_profile_result(self) -> tuple[SectionPressureProfileResult | None, str | None]:
        pipe, pipe_error = self._detail_pipe_snapshot()
        if pipe_error is not None:
            return None, pipe_error
        assert pipe is not None

        if self._selected_material_grade() is None:
            return None, "API 5L PSL2 boru malzeme kalitesi secilmelidir."

        numeric_values: dict[str, float] = {}
        labels = {
            "highest_elevation_m": "En yuksek nokta kotu",
            "lowest_elevation_m": "En dusuk nokta kotu",
            "start_elevation_m": "Baslangic noktasi kotu",
            "end_elevation_m": "Bitis noktasi kotu",
            "design_pressure_bar": "Dizayn basinci",
            "smys_mpa": "SMYS",
        }
        for key, label in labels.items():
            value = self._safe_float(self.section_profile_vars[key].get())
            if value is None:
                return None, f"{label} bekleniyor"
            numeric_values[key] = value

        try:
            result = evaluate_section_pressure_profile(
                SectionPressureProfileInputs(
                    pipe=pipe,
                    design_pressure_bar=numeric_values["design_pressure_bar"],
                    smys_mpa=numeric_values["smys_mpa"],
                    location_class=get_location_class_rule(self.location_class_var.get()),
                    highest_elevation_m=numeric_values["highest_elevation_m"],
                    lowest_elevation_m=numeric_values["lowest_elevation_m"],
                    start_elevation_m=numeric_values["start_elevation_m"],
                    end_elevation_m=numeric_values["end_elevation_m"],
                    selected_pump_location=self.pump_location_var.get(),
                    monitored_pressure_bar=self._active_monitored_pressure_bar(),
                )
            )
        except ValidationError as exc:
            return None, str(exc)
        return result, None





    def _refresh_section_pressure_overview(self) -> None:
        result, error = self._section_pressure_profile_result()
        self.section_pressure_summary_var.set(self._build_section_pressure_summary())
        self._update_section_pressure_status_card(result, error)
        self._refresh_section_pressure_schematic(result, error)





    def _refresh_section_pressure_schematic(
        self,
        result: SectionPressureProfileResult | None,
        error: str | None,
    ) -> None:
        if not hasattr(self, "section_profile_canvas"):
            return
        canvas = self.section_profile_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 250)
        height = max(canvas.winfo_height(), 180)
        if error is not None or result is None:
            canvas.create_rectangle(12, 12, width - 12, height - 12, outline="#D7DFEA", dash=(4, 2))
            canvas.create_text(
                width / 2,
                height / 2,
                text="Kot girisleri tamamlandiginda\nhat profili burada canlanir.",
                fill="#6B7280",
                font=("Segoe UI", 9),
                justify="center",
            )
            return

        highest = self._safe_float(self.section_profile_vars["highest_elevation_m"].get())
        lowest = self._safe_float(self.section_profile_vars["lowest_elevation_m"].get())
        start = self._safe_float(self.section_profile_vars["start_elevation_m"].get())
        end = self._safe_float(self.section_profile_vars["end_elevation_m"].get())
        if None in {highest, lowest, start, end}:
            return
        assert highest is not None
        assert lowest is not None
        assert start is not None
        assert end is not None

        top_y = 24
        bottom_y = height - 24
        left_x = 54
        right_x = width - 42
        middle_x = (left_x + right_x) / 2
        elevation_span = max(highest - lowest, 1.0)

        def map_y(elevation: float) -> float:
            ratio = (highest - elevation) / elevation_span
            return top_y + (bottom_y - top_y) * ratio

        start_y = map_y(start)
        end_y = map_y(end)
        high_y = map_y(highest)
        low_y = map_y(lowest)

        canvas.create_line(left_x, top_y, left_x, bottom_y, fill="#D0D7E2", width=2)
        canvas.create_text(left_x - 10, high_y, text=f"{highest:.1f} m", anchor="e", fill="#35506B", font=("Segoe UI", 8))
        canvas.create_text(left_x - 10, low_y, text=f"{lowest:.1f} m", anchor="e", fill="#35506B", font=("Segoe UI", 8))
        canvas.create_line(left_x + 22, start_y, right_x - 22, end_y, fill="#4A74A8", width=4, smooth=True)

        canvas.create_oval(left_x + 12, start_y - 6, left_x + 24, start_y + 6, fill="#6FA8DC", outline="#35506B")
        canvas.create_text(left_x + 18, start_y - 14, text="Start", fill="#16365D", font=("Segoe UI", 8, "bold"))
        canvas.create_oval(right_x - 24, end_y - 6, right_x - 12, end_y + 6, fill="#93C47D", outline="#35506B")
        canvas.create_text(right_x - 18, end_y - 14, text="Bitis", fill="#16365D", font=("Segoe UI", 8, "bold"))

        canvas.create_polygon(
            middle_x,
            high_y - 9,
            middle_x + 9,
            high_y,
            middle_x,
            high_y + 9,
            middle_x - 9,
            high_y,
            fill="#F6B26B",
            outline="#A65D00",
        )
        canvas.create_text(middle_x + 18, high_y - 2, text="En yuksek", anchor="w", fill="#16365D", font=("Segoe UI", 8))
        canvas.create_rectangle(middle_x - 8, low_y - 8, middle_x + 8, low_y + 8, fill="#D9EAD3", outline="#38761D")
        canvas.create_text(middle_x + 18, low_y, text="En dusuk", anchor="w", fill="#16365D", font=("Segoe UI", 8))

        selected_location = self.pump_location_var.get().strip()
        if selected_location == "Baslangic noktasi":
            canvas.create_oval(left_x + 6, start_y - 12, left_x + 30, start_y + 12, outline="#C00000", width=2)
        elif selected_location == "Bitis noktasi":
            canvas.create_oval(right_x - 30, end_y - 12, right_x - 6, end_y + 12, outline="#C00000", width=2)

        canvas.create_text(
            width / 2,
            height - 10,
            text=(
                f"Aktif pencere: {result.selected_window.minimum_required_pressure_bar:.2f} - "
                f"{result.selected_window.maximum_allowable_pressure_bar:.2f} bar"
            ),
            fill="#35506B",
            font=("Segoe UI", 8, "bold"),
        )












    def _on_pressure_a_calculate_button(self) -> object:
        return self._execute_progress_button_action(
            "pressure_a_calculate",
            self._calculate_pressure_a,
            result_state_resolver=self._bool_progress_state,
        )


    def _on_pressure_test_button(self) -> object:
        return self._execute_progress_button_action(
            "pressure_test",
            self._run_pressure_test_impl,
            result_state_resolver=self._decision_progress_state,
        )














    def _run_pressure_test_impl(self) -> None:
        self._run_pressure_test()


    def _pressure_a_is_auto(self) -> bool:
        return self.pressure_a_mode_var.get() == self.AUTO_A_MODE


    def _pressure_b_is_auto(self) -> bool:
        return self.pressure_b_mode_var.get() == self.AUTO_B_MODE



    def _pressure_a_is_reference(self) -> bool:
        return self.pressure_a_mode_var.get() == self.REFERENCE_A_MODE


    def _pressure_b_is_reference(self) -> bool:
        return self.pressure_b_mode_var.get() == self.REFERENCE_B_MODE


    def _on_pressure_a_mode_changed(self, _: tk.Event | None = None) -> None:
        self._apply_single_coefficient_mode(
            key="pressure_a",
            field_key="pressure.a_micro_per_bar",
            variable=self.pressure_vars["a_micro_per_bar"],
            mode=self.pressure_a_mode_var.get(),
            reference_combo=self.pressure_a_reference_combo,
            auto_banner="Basinc testi A secenegi otomatik. A Hesapla butonu veya degerlendirme akisi bu alani doldurur.",
            reference_banner=(
                f"Basinc testi A secenegi tablo modda. {BOTAS_REFERENCE_TABLE_LABEL} veya "
                f"{GAIL_REFERENCE_TABLE_LABEL} secin."
            ),
            manual_banner="Basinc testi A secenegi manuel. Tablo/prosedur degerini dogrudan girebilirsiniz.",
        )
        self._refresh_choice_validation_states()
        self._refresh_live_coefficients()
        self._refresh_live_test_decision()



    def _on_pressure_a_reference_changed(self, _: tk.Event | None = None) -> None:
        self._apply_pressure_a_reference(log_result=True)


    def _on_pressure_b_reference_changed(self, _: tk.Event | None = None) -> None:
        self._apply_b_helper_mode()
        self._apply_pressure_b_reference(log_result=True)


    def _on_pressure_b_mode_changed(self, _: tk.Event | None = None) -> None:
        self._apply_b_helper_mode()
        self._refresh_choice_validation_states()
        self._refresh_live_coefficients()
        self._refresh_live_test_decision()


    def _apply_pressure_a_reference(self, log_result: bool = True, silent: bool = False) -> bool:
        selected_label = self.pressure_a_reference_var.get().strip()
        if not selected_label:
            if not silent:
                self._set_feedback("pressure", "Basinc testi A icin bir referans tablo secin.")
                self._focus_field("pressure.a_micro_per_bar")
            return False
        try:
            point = self._lookup_selected_table_reference("pressure", selected_label)
        except ValidationError as exc:
            if not silent:
                self._set_feedback("pressure", str(exc))
                self._focus_field("pressure.a_micro_per_bar")
            return False
        table_label = self._selected_reference_table_label(selected_label)
        self._set_coefficient_value("pressure_a", self.pressure_vars["a_micro_per_bar"], point.a_micro_per_bar, state="reference")
        if log_result:
            self._append_result(
                "Basinc Degisim Testi - A referansi",
                (
                    f"A = {point.a_micro_per_bar:.6f} (10^-6 / bar) {table_label} uzerinden yuklendi.\n"
                    f"Referans: {selected_label}\n"
                    f"Kaynak: {point.source_note}"
                ),
            )
        if not silent:
            self._set_banner(f"Basinc testi icin A {table_label} uzerinden yuklendi.", "success")
        self._refresh_control_table_summaries()
        return True


    def _apply_pressure_b_reference(self, log_result: bool = True, silent: bool = False) -> bool:
        selected_label = self.pressure_b_reference_var.get().strip()
        if not selected_label:
            if not silent:
                self._set_feedback("pressure", "Basinc testi B icin bir referans tablo secin.")
                self._focus_field("pressure.b_micro_per_c")
            return False
        try:
            point = self._lookup_selected_table_reference("pressure", selected_label)
        except ValidationError as exc:
            if not silent:
                self._set_banner(str(exc), "error")
                self._update_decision_card("Basinc Degisim Testi", "DOGRULANAMADI", str(exc))
            return False
        table_label = self._selected_reference_table_label(selected_label)
        self.b_helper_vars["water_beta_micro_per_c"].set("")
        self._set_coefficient_value("pressure_b", self.pressure_vars["b_micro_per_c"], point.b_micro_per_c, state="reference")
        if log_result:
            self._append_result(
                "Basinc Degisim Testi - B referansi",
                (
                    f"B = {point.b_micro_per_c:.6f} (10^-6 / degC) {table_label} uzerinden yuklendi.\n"
                    f"Referans: {selected_label}\n"
                    f"Kaynak: {point.source_note}"
                ),
            )
        if not silent:
            self._set_banner(f"Basinc testi icin B {table_label} uzerinden yuklendi.", "success")
        self._refresh_control_table_summaries()
        return True


    def _calculate_pressure_a(self, log_result: bool = True, silent: bool = False) -> bool:
        self._clear_feedback("pressure")
        backend_info = self._selected_water_backend_info()
        try:
            a_value = calculate_water_compressibility_a(
                temp_c=self._read_float(
                    self.pressure_vars["temperature_c"], "Su sicakligi", "pressure", "pressure.temperature_c"
                ),
                pressure_bar=self._read_float(
                    self.pressure_vars["pressure_bar"], "Su basinci", "pressure", "pressure.pressure_bar"
                ),
                backend=backend_info.key,
            )
        except ValidationError as exc:
            if not silent:
                self._set_banner(str(exc), "error")
                self._update_decision_card("Basinc Degisim Testi", "DOGRULANAMADI", str(exc))
            return False

        self._set_coefficient_value("pressure_a", self.pressure_vars["a_micro_per_bar"], a_value)
        self._refresh_control_table_summaries()
        if log_result:
            self._append_result(
                "Basinc Degisim Testi - A hesabi",
                (
                    f"A = {a_value:.6f} (10^-6 / bar) olarak {backend_info.label} backend'i ile hesaplandi.\n"
                    f"Kontrol tablosu: {self.pressure_control_table_var.get()}"
                ),
            )
        if not silent:
            self._set_banner("Basinc degisim testi icin A katsayisi guncellendi.", "success")
        return True


    def _run_pressure_test(self) -> None:
        self._clear_all_feedback()
        if not self._ensure_coefficient_ready("pressure_a"):
            return
        if not self._ensure_coefficient_ready("pressure_b"):
            return
        try:
            pipe = self._build_pipe_section("pressure")
            inputs = PressureVariationInputs(
                pipe=pipe,
                a_micro_per_bar=self._read_float(
                    self.pressure_vars["a_micro_per_bar"], "A degeri", "pressure", "pressure.a_micro_per_bar"
                ),
                b_micro_per_c=self._read_float(
                    self.pressure_vars["b_micro_per_c"], "B degeri", "pressure", "pressure.b_micro_per_c"
                ),
                delta_t_c=self._read_float(
                    self.pressure_vars["delta_t_c"], "Su sicaklik degisimi dT", "pressure", "pressure.delta_t_c"
                ),
                actual_pressure_change_bar=self._read_float(
                    self.pressure_vars["actual_pressure_change_bar"],
                    "Fiili basinc degisimi Pa",
                    "pressure",
                    "pressure.actual_pressure_change_bar",
                ),
            )
            result = evaluate_pressure_variation_test(inputs)
        except ValidationError as exc:
            self._set_banner(str(exc), "error")
            self._update_decision_card("Basinc Degisim Testi", "DOGRULANAMADI", str(exc))
            return

        status = "BASARILI" if result.passed else "BASARISIZ"
        self._refresh_control_table_summaries()
        self._update_decision_card(
            "Basinc Degisim Testi",
            status,
            (
                f"Pt = {result.theoretical_pressure_change_bar:.6f} bar, ust sinir = "
                f"{result.allowable_upper_pressure_change_bar:.6f} bar, Pa = "
                f"{result.actual_pressure_change_bar:.6f} bar, fark = {result.margin_bar:.6f} bar"
            ),
        )
        self._append_result(
            "Basinc Degisim Testi",
            (
                f"Durum: {status}\n"
                f"Su sicakligi: {self.pressure_vars['temperature_c'].get().strip()} degC\n"
                f"Su basinci: {self.pressure_vars['pressure_bar'].get().strip()} bar\n"
                f"A: {self.pressure_vars['a_micro_per_bar'].get().strip()} (10^-6 / bar)\n"
                f"B: {self.pressure_vars['b_micro_per_c'].get().strip()} (10^-6 / degC)\n"
                f"Su sicaklik degisimi dT = Tilk - Tson: {self.pressure_vars['delta_t_c'].get().strip()} degC\n"
                f"Fiili basinc degisimi Pa = Pilk - Pson: {self.pressure_vars['actual_pressure_change_bar'].get().strip()} bar\n"
                f"B helper modu: {'Acik' if self.use_b_helper_var.get() else 'Kapali'}\n"
                f"Celik alpha: {self.b_helper_vars['steel_alpha_micro_per_c'].get().strip() or '-'} (10^-6 / degC)\n"
                f"Su beta: {self.b_helper_vars['water_beta_micro_per_c'].get().strip() or '-'} (10^-6 / degC)\n"
                f"Ic yaricap: {pipe.internal_radius_mm:.3f} mm\n"
                f"Teorik basinc degisimi Pt: {result.theoretical_pressure_change_bar:.6f} bar\n"
                f"Ust kabul siniri (Pt + 0.3): {result.allowable_upper_pressure_change_bar:.6f} bar\n"
                f"Fiili basinc degisimi Pa: {result.actual_pressure_change_bar:.6f} bar\n"
                f"Fark (Pa - Pt): {result.margin_bar:.6f} bar\n"
                f"Kontrol tablosu: {self.pressure_control_table_var.get()}"
            ),
        )
        self._set_banner("Basinc degisim testi degerlendirmesi tamamlandi.", "success")



    def _clear_pressure_form(self) -> None:
        for variable in self.pressure_vars.values():
            variable.set("")
        self.b_helper_vars["water_beta_micro_per_c"].set("")
        self.b_helper_vars["steel_alpha_micro_per_c"].set(self._default_steel_alpha())
        self.coefficient_states["pressure_a"] = "empty"
        self.coefficient_states["pressure_b"] = "empty"
        self.pressure_backend_comparison_var.set(self._default_backend_comparison_text("pressure"))
        self.pressure_control_table_var.set(self._default_control_table_text("pressure"))
        self._remove_touched_fields("pressure")
        self._clear_feedback("pressure")
        self._refresh_coefficient_statuses()
        self._sync_backend_comparison_summary()
        self._sync_control_table_summary()
        self._reset_decision_card()
        self._set_banner("Basinc degisim testi formu temizlendi.", "info")
        self._refresh_visual_schema()

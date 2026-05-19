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
    AirContentInputs,
    ValidationError,
    calculate_water_compressibility_a,
    evaluate_air_content_test,
)

if TYPE_CHECKING:
    from .app_main import HydrostaticTestApp


class AirTabMixin:
    def _build_air_input_panel(self, frame: ttk.Frame) -> None:
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        conditions_frame = ttk.LabelFrame(frame, text="Hava Testi - Kosullar", padding=12)
        conditions_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        conditions_frame.columnconfigure(1, weight=1)
        conditions_frame.columnconfigure(3, weight=1)
        self._add_entry(
            conditions_frame,
            0,
            "Su sicakligi (degC)",
            self.air_vars["temperature_c"],
            field_key="air.temperature_c",
        )
        self._add_entry(
            conditions_frame,
            0,
            "Su basinci (bar)",
            self.air_vars["pressure_bar"],
            field_key="air.pressure_bar",
            column=2,
        )
        self._add_entry(
            conditions_frame,
            1,
            "A (10^-6 / bar)",
            self.air_vars["a_micro_per_bar"],
            field_key="air.a_micro_per_bar",
            readonly=True,
        )
        self.inline_coefficient_source_badges["air_a"] = self._create_source_badge(
            conditions_frame,
            key="air_a",
            registry=self.inline_coefficient_source_badges,
        )
        self.inline_coefficient_source_badges["air_a"].grid(row=1, column=2, sticky="w", pady=6)
        ttk.Label(
            conditions_frame,
            textvariable=self.coefficient_status_vars["air_a"],
            foreground="#8A6D3B",
        ).grid(row=1, column=3, sticky="w", pady=6)
        ttk.Label(conditions_frame, text="A secenegi").grid(row=2, column=0, sticky="w", pady=6)
        air_a_mode_combo = ttk.Combobox(
            conditions_frame,
            textvariable=self.air_a_mode_var,
            state="readonly",
            values=(self.AUTO_A_MODE, self.REFERENCE_A_MODE, self.MANUAL_A_MODE),
            width=24,
        )
        air_a_mode_combo.grid(row=2, column=1, sticky="ew", padx=(0, 12), pady=6)
        air_a_mode_combo.bind("<<ComboboxSelected>>", self._on_air_a_mode_changed)
        ttk.Label(conditions_frame, text="A referans tablosu").grid(row=2, column=2, sticky="w", pady=6)
        self.air_a_reference_combo = ttk.Combobox(
            conditions_frame,
            textvariable=self.air_a_reference_var,
            state="disabled",
            values=self.reference_option_labels,
            style="Hydro.neutral.TCombobox",
            width=24,
        )
        self.air_a_reference_combo.grid(row=2, column=3, sticky="ew", padx=(0, 12), pady=6)
        self.air_a_reference_combo.bind("<<ComboboxSelected>>", self._on_air_a_reference_changed)
        self._register_choice_widget(
            field_key="air.a_reference_table",
            widget=self.air_a_reference_combo,
            section="air",
            label="A referans tablosu",
            required=False,
        )

        measurements_frame = ttk.LabelFrame(frame, text="Hava Testi - Olculen Degerler", padding=12)
        measurements_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        measurements_frame.columnconfigure(1, weight=1)
        measurements_frame.columnconfigure(3, weight=1)
        self._add_entry(
            measurements_frame,
            0,
            "Basinc artisi P (bar)",
            self.air_vars["pressure_rise_bar"],
            field_key="air.pressure_rise_bar",
            readonly=True,
        )
        ttk.Label(
            measurements_frame,
            text="P = 1.0 bar (sartname zorunlu)",
            foreground="#6B7280",
        ).grid(row=0, column=2, sticky="w", pady=6)
        self._add_entry(
            measurements_frame,
            0,
            "Fiili ilave su Vpa (m3)",
            self.air_vars["actual_added_water_m3"],
            field_key="air.actual_added_water_m3",
            column=2,
        )
        ttk.Label(measurements_frame, text="K faktor preset").grid(row=1, column=0, sticky="w", pady=6)
        k_preset = ttk.Combobox(
            measurements_frame,
            textvariable=self.k_preset_var,
            state="readonly",
            values=("Kaynakli boru - 1.02", "Dikissiz boru - 1.00", "Ozel"),
            width=22,
        )
        k_preset.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=6)
        k_preset.bind("<<ComboboxSelected>>", self._on_k_preset_changed)
        self._add_entry(
            measurements_frame,
            1,
            "K faktor",
            self.air_vars["k_factor"],
            field_key="air.k_factor",
            column=2,
        )

        pv_frame = ttk.LabelFrame(frame, text="Basinc-Hacim Izleme (Madde 14.2)", padding=12)
        pv_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        pv_frame.columnconfigure(1, weight=1)
        pv_frame.columnconfigure(3, weight=1)
        self._add_entry(
            pv_frame,
            0,
            "Toplam basinclandirma basinci (bar)",
            self.pv_vars["total_pressure_rise_bar"],
            field_key="pv.total_pressure_rise_bar",
        )
        self._add_entry(
            pv_frame,
            0,
            "Toplam ilave su hacmi (m3)",
            self.pv_vars["total_water_added_m3"],
            field_key="pv.total_water_added_m3",
            column=2,
        )
        self.pv_result_var = tk.StringVar(value="Basinc-hacim %0.2 esik kontrolu henuz yapilmadi.")
        ttk.Label(
            pv_frame,
            textvariable=self.pv_result_var,
            wraplength=self.input_wraplength,
            justify="left",
            foreground="#35506B",
        ).grid(row=1, column=0, columnspan=4, sticky="ew", pady=(8, 0))


    def _build_air_tab(self, frame: ttk.Frame) -> None:
        frame.columnconfigure(0, weight=1)

        input_wrapper = ttk.Frame(frame)
        input_wrapper.grid(row=0, column=0, sticky="ew")
        self._build_air_input_panel(input_wrapper)

        actions_frame = ttk.LabelFrame(frame, text="Hesap ve Karar", padding=12)
        actions_frame.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        self.air_a_calculate_button = self._create_progress_button(
            actions_frame,
            key="air_a_calculate",
            text="A Hesapla",
            command=self._on_air_a_calculate_button,
        )
        self.air_a_calculate_button.pack(side="left")
        self.air_test_button = self._create_progress_button(
            actions_frame,
            key="air_test",
            text="Hava Testini Degerlendir",
            command=self._on_air_test_button,
        )
        self.air_test_button.pack(side="left", padx=(8, 0))

        reference_frame = ttk.LabelFrame(frame, text="Katsayi ve Referans Ozeti", padding=12)
        reference_frame.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        reference_frame.columnconfigure(0, weight=1)
        self._register_help_note(ttk.Label(
            reference_frame,
            text=(
                "Hava icerik testinde tum girisler ve hesaplama bu panel uzerinden yapilir. "
                "A katsayisi durumu, backend karsilastirmasi ve kontrol tablosu ozeti asagida gosterilir."
            ),
            wraplength=self.workspace_wraplength,
            justify="left",
        )).grid(row=0, column=0, sticky="ew")
        ttk.Label(
            reference_frame,
            textvariable=self.air_backend_comparison_var,
            wraplength=self.workspace_wraplength,
            justify="left",
            foreground="#35506B",
        ).grid(row=1, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(
            reference_frame,
            textvariable=self.air_control_table_var,
            wraplength=self.workspace_wraplength,
            justify="left",
            foreground="#35506B",
        ).grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(
            frame,
            textvariable=self.section_feedback_vars["air"],
            foreground="#A4262C",
            wraplength=self.workspace_wraplength,
            justify="left",
        ).grid(row=3, column=0, sticky="w", pady=(12, 0))


    def _build_air_detail_report(self) -> str:
        lines = [
            "Hava Icerik Testi - Detay Raporu",
            "",
            "Katsayi Durumu",
            f"A modu: {self.air_a_mode_var.get().strip()}",
            f"A durum: {self.coefficient_status_vars['air_a'].get()}",
            f"A kaynagi: {self._coefficient_origin_text('air_a')}",
            f"A degeri: {self._format_detail_value(self.air_vars['a_micro_per_bar'], '(10^-6 / bar)')}",
            f"Su backend'i: {self._selected_water_backend_info().label}",
            f"Backend karsilastirmasi: {self.air_backend_comparison_var.get()}",
            f"Kontrol tablosu: {self.air_control_table_var.get()}",
            "",
            "Kullanici Girdileri",
            f"Su sicakligi: {self._format_detail_value(self.air_vars['temperature_c'], 'degC')} (kullanici girdisi)",
            f"Su basinci: {self._format_detail_value(self.air_vars['pressure_bar'], 'bar')} (kullanici girdisi)",
            f"Basinc artisi P: {self._format_detail_value(self.air_vars['pressure_rise_bar'], 'bar')} (kullanici girdisi)",
            f"K faktor: {self._format_var_value(self.air_vars['k_factor'])} (kullanici girdisi)",
            f"Fiili ilave su Vpa: {self._format_detail_value(self.air_vars['actual_added_water_m3'], 'm3')} (kullanici girdisi)",
            "",
            "Geometri",
            f"Ozet: {self.geometry_summary_var.get()}",
            f"Basinc penceresi: {self.section_pressure_summary_var.get()}",
            f"Canli basinc durumu: {self.section_pressure_status_var.get()}",
            f"Pencere yorumu: {self.section_pressure_status_detail_var.get()}",
            f"Aktif pencere: {self.section_pressure_window_var.get()}",
        ]
        if self.geometry_segments:
            lines.append(f"Segment ozeti: {self.segment_summary_var.get()}")

        lines.extend(
            [
                "",
                "Degerlendirme Temeli",
                "Karar kurali: Vpa <= 1.06 x Vp",
            ]
        )

        pipe, pipe_error = self._detail_pipe_snapshot()
        issues = [
            issue
            for issue in (
                pipe_error,
                self._detail_numeric_issue(self.air_vars["a_micro_per_bar"], "A degeri"),
                self._detail_numeric_issue(self.air_vars["pressure_rise_bar"], "Basinc artisi P"),
                self._detail_numeric_issue(self.air_vars["k_factor"], "K faktor"),
                self._detail_numeric_issue(self.air_vars["actual_added_water_m3"], "Fiili ilave su Vpa"),
            )
            if issue is not None
        ]
        if self.coefficient_states["air_a"] == "stale":
            issues.append("A katsayisi guncellenmeli")
        if issues:
            lines.append("Degerlendirme hazir degil: " + ", ".join(issues) + ".")
            return "\n".join(lines)

        assert pipe is not None
        a_value = self._safe_float(self.air_vars["a_micro_per_bar"].get())
        pressure_rise = self._safe_float(self.air_vars["pressure_rise_bar"].get())
        k_factor = self._safe_float(self.air_vars["k_factor"].get())
        actual_added_water = self._safe_float(self.air_vars["actual_added_water_m3"].get())
        if (
            a_value is None
            or pressure_rise is None
            or k_factor is None
            or actual_added_water is None
        ):
            lines.append("Degerlendirme hazir degil: sayisal girdiler tamamlanmadi.")
            return "\n".join(lines)

        try:
            inputs = AirContentInputs(
                pipe=pipe,
                a_micro_per_bar=a_value,
                pressure_rise_bar=pressure_rise,
                k_factor=k_factor,
                actual_added_water_m3=actual_added_water,
            )
            result = evaluate_air_content_test(inputs)
        except ValidationError as exc:
            lines.append(f"Degerlendirme hazir degil: {exc}")
            return "\n".join(lines)

        deformation_term = pipe.elasticity_term + inputs.a_micro_per_bar
        lines.extend(
            [
                f"Boru elastisite terimi (0.884 x ri / s): {pipe.elasticity_term:.6f}",
                f"Toplam deformasyon terimi ((0.884 x ri / s) + A): {deformation_term:.6f}",
                f"Program hesabi Vp: {result.theoretical_added_water_m3:.6f} m3",
                f"Kabul siniri (1.06 x Vp): {result.acceptance_limit_m3:.6f} m3",
                f"Kullanici girdisi Vpa: {result.actual_added_water_m3:.6f} m3",
                f"Oran (Vpa / Vp): {result.ratio:.6f}",
                f"Anlik sonuc: {'BASARILI' if result.passed else 'BASARISIZ'}",
            ]
        )
        return "\n".join(lines)


    def _build_air_control_table_summary(self) -> str:
        temp_c = self._safe_float(self.air_vars["temperature_c"].get())
        pressure_bar = self._safe_float(self.air_vars["pressure_bar"].get())
        if temp_c is None or pressure_bar is None:
            return self._default_control_table_text("air")
        current_a = self._safe_float(self.air_vars["a_micro_per_bar"].get())
        parts: list[str] = []
        try:
            point = lookup_botas_reference_point(temp_c=temp_c, pressure_bar=pressure_bar)
            if current_a is None:
                parts.append(f"{BOTAS_REFERENCE_TABLE_LABEL} A = {point.a_micro_per_bar:.6f}.")
            else:
                parts.append(
                    f"{BOTAS_REFERENCE_TABLE_LABEL} A = {point.a_micro_per_bar:.6f}. "
                    f"A farki = {self._format_control_table_delta(current_a, point.a_micro_per_bar)}."
                )
        except (ABControlTableError, FileNotFoundError, ValueError) as exc:
            parts.append(f"{BOTAS_REFERENCE_TABLE_LABEL} kullanilamadi ({exc}).")
        try:
            gail_point = lookup_gail_reference_point(temp_c=temp_c, pressure_bar=pressure_bar)
            if current_a is None:
                parts.append(f"{GAIL_REFERENCE_TABLE_LABEL} A = {gail_point.a_micro_per_bar:.6f}.")
            else:
                parts.append(
                    f"{GAIL_REFERENCE_TABLE_LABEL} A = {gail_point.a_micro_per_bar:.6f}. "
                    f"A farki = {self._format_control_table_delta(current_a, gail_point.a_micro_per_bar)}."
                )
        except (ABControlTableError, FileNotFoundError, ValueError) as exc:
            parts.append(f"{GAIL_REFERENCE_TABLE_LABEL} kullanilamadi ({exc}).")
        return " ".join(parts)


    def _build_air_backend_comparison(self) -> str:
        temp_c = self._read_float(
            self.air_vars["temperature_c"], "Su sicakligi", "air", "air.temperature_c"
        )
        pressure_bar = self._read_float(
            self.air_vars["pressure_bar"], "Su basinci", "air", "air.pressure_bar"
        )
        rows: list[dict[str, object]] = []
        for info in self.water_backend_infos:
            try:
                a_value = calculate_water_compressibility_a(
                    temp_c=temp_c,
                    pressure_bar=pressure_bar,
                    backend=info.key,
                )
                rows.append({"info": info, "a_value": a_value, "error": None})
            except ValidationError as exc:
                rows.append({"info": info, "a_value": None, "error": str(exc)})
        selected_key = self._selected_water_backend_key()
        selected_row = next(row for row in rows if getattr(row["info"], "key", "") == selected_key)
        selected_info = selected_row["info"]
        selected_a = selected_row["a_value"]
        parts = [f"Hava A karsilastirmasi @ {temp_c:.3f} degC / {pressure_bar:.3f} bar."]
        if isinstance(selected_a, float):
            parts.append(f"Secili backend {selected_info.label}: A = {selected_a:.6f}.")
        else:
            parts.append(f"Secili backend {selected_info.label}: hesaplanamadi ({selected_row['error']}).")
        for row in rows:
            info = row["info"]
            if getattr(info, "key", "") == selected_key:
                continue
            a_value = row["a_value"]
            if not isinstance(a_value, float):
                parts.append(f"{info.label}: hesaplanamadi ({row['error']}).")
                continue
            if isinstance(selected_a, float):
                delta = a_value - selected_a
                delta_pct = (delta / selected_a * 100) if selected_a else 0.0
                parts.append(
                    f"{info.label}: A = {a_value:.6f} | fark = {delta:+.6f} | %{delta_pct:+.6f}."
                )
            else:
                parts.append(f"{info.label}: A = {a_value:.6f}.")
        return " ".join(parts)


    def _on_air_a_calculate_button(self) -> object:
        return self._execute_progress_button_action(
            "air_a_calculate",
            self._calculate_air_a,
            result_state_resolver=self._bool_progress_state,
        )


    def _on_air_test_button(self) -> object:
        return self._execute_progress_button_action(
            "air_test",
            self._run_air_test_impl,
            result_state_resolver=self._decision_progress_state,
        )


    def _run_air_test_impl(self) -> None:
        self._run_air_test()


    def _air_a_is_auto(self) -> bool:
        return self.air_a_mode_var.get() == self.AUTO_A_MODE


    def _air_a_is_reference(self) -> bool:
        return self.air_a_mode_var.get() == self.REFERENCE_A_MODE


    def _on_air_a_mode_changed(self, _: tk.Event | None = None) -> None:
        self._apply_single_coefficient_mode(
            key="air_a",
            field_key="air.a_micro_per_bar",
            variable=self.air_vars["a_micro_per_bar"],
            mode=self.air_a_mode_var.get(),
            reference_combo=self.air_a_reference_combo,
            auto_banner="Hava A secenegi otomatik. A Hesapla butonu veya degerlendirme akisi bu alani doldurur.",
            reference_banner=(
                f"Hava A secenegi tablo modda. {BOTAS_REFERENCE_TABLE_LABEL} veya "
                f"{GAIL_REFERENCE_TABLE_LABEL} secin."
            ),
            manual_banner="Hava A secenegi manuel. Tablo/prosedur degerini dogrudan girebilirsiniz.",
        )
        self._refresh_choice_validation_states()
        self._refresh_live_coefficients()
        self._refresh_live_test_decision()


    def _on_air_a_reference_changed(self, _: tk.Event | None = None) -> None:
        self._apply_air_a_reference(log_result=True)


    def _apply_air_a_reference(self, log_result: bool = True, silent: bool = False) -> bool:
        selected_label = self.air_a_reference_var.get().strip()
        if not selected_label:
            if not silent:
                self._set_feedback("air", "Hava A icin bir referans tablo secin.")
                self._focus_field("air.a_micro_per_bar")
            return False
        try:
            point = self._lookup_selected_table_reference("air", selected_label)
        except ValidationError as exc:
            if not silent:
                self._set_feedback("air", str(exc))
                self._focus_field("air.a_micro_per_bar")
            return False
        table_label = self._selected_reference_table_label(selected_label)
        self._set_coefficient_value("air_a", self.air_vars["a_micro_per_bar"], point.a_micro_per_bar, state="reference")
        if log_result:
            self._append_result(
                "Hava Icerik Testi - A referansi",
                (
                    f"A = {point.a_micro_per_bar:.6f} (10^-6 / bar) {table_label} uzerinden yuklendi.\n"
                    f"Referans: {selected_label}\n"
                    f"Kaynak: {point.source_note}"
                ),
            )
        if not silent:
            self._set_banner(f"Hava icerik testi icin A {table_label} uzerinden yuklendi.", "success")
        self._refresh_control_table_summaries()
        return True


    def _calculate_air_a(self, log_result: bool = True, silent: bool = False) -> bool:
        self._clear_feedback("air")
        backend_info = self._selected_water_backend_info()
        try:
            a_value = calculate_water_compressibility_a(
                temp_c=self._read_float(
                    self.air_vars["temperature_c"], "Su sicakligi", "air", "air.temperature_c"
                ),
                pressure_bar=self._read_float(
                    self.air_vars["pressure_bar"], "Su basinci", "air", "air.pressure_bar"
                ),
                backend=backend_info.key,
            )
        except ValidationError as exc:
            if not silent:
                self._set_banner(str(exc), "error")
                self._update_decision_card("Hava Icerik Testi", "DOGRULANAMADI", str(exc))
            return False

        self._set_coefficient_value("air_a", self.air_vars["a_micro_per_bar"], a_value)
        self._refresh_control_table_summaries()
        if log_result:
            self._append_result(
                "Hava Icerik Testi - A hesabi",
                (
                    f"A = {a_value:.6f} (10^-6 / bar) olarak {backend_info.label} backend'i ile hesaplandi.\n"
                    f"Kontrol tablosu: {self.air_control_table_var.get()}"
                ),
            )
        if not silent:
            self._set_banner("Hava icerik testi icin A katsayisi guncellendi.", "success")
        return True


    def _run_air_test(self) -> None:
        self._clear_all_feedback()
        if not self._ensure_coefficient_ready("air_a"):
            return
        try:
            pipe = self._build_pipe_section("air")
            inputs = AirContentInputs(
                pipe=pipe,
                a_micro_per_bar=self._read_float(
                    self.air_vars["a_micro_per_bar"], "A degeri", "air", "air.a_micro_per_bar"
                ),
                pressure_rise_bar=self._read_float(
                    self.air_vars["pressure_rise_bar"], "Basinc artisi P", "air", "air.pressure_rise_bar"
                ),
                k_factor=self._read_float(self.air_vars["k_factor"], "K faktor", "air", "air.k_factor"),
                actual_added_water_m3=self._read_float(
                    self.air_vars["actual_added_water_m3"], "Fiili ilave su Vpa", "air", "air.actual_added_water_m3"
                ),
            )
            result = evaluate_air_content_test(inputs)
        except ValidationError as exc:
            self._set_banner(str(exc), "error")
            self._update_decision_card("Hava Icerik Testi", "DOGRULANAMADI", str(exc))
            return

        status = "BASARILI" if result.passed else "BASARISIZ"
        self._refresh_control_table_summaries()
        self._update_decision_card(
            "Hava Icerik Testi",
            status,
            (
                f"Vp = {result.theoretical_added_water_m3:.6f} m3, limit = {result.acceptance_limit_m3:.6f} m3, "
                f"Vpa = {result.actual_added_water_m3:.6f} m3, oran = {result.ratio:.6f}"
            ),
        )
        self._append_result(
            "Hava Icerik Testi",
            (
                f"Durum: {status}\n"
                f"Su sicakligi: {self.air_vars['temperature_c'].get().strip()} degC\n"
                f"Su basinci: {self.air_vars['pressure_bar'].get().strip()} bar\n"
                f"A: {self.air_vars['a_micro_per_bar'].get().strip()} (10^-6 / bar)\n"
                f"Basinc artisi P (sartname): {self.air_vars['pressure_rise_bar'].get().strip()} bar\n"
                f"K faktor: {self.air_vars['k_factor'].get().strip()}\n"
                f"Ic yaricap: {pipe.internal_radius_mm:.3f} mm\n"
                f"Ic hacim Vt: {pipe.internal_volume_m3:.6f} m3\n"
                f"Teorik ilave su Vp: {result.theoretical_added_water_m3:.6f} m3\n"
                f"Kabul limiti (1.06 x Vp): {result.acceptance_limit_m3:.6f} m3\n"
                f"Fiili ilave su Vpa: {result.actual_added_water_m3:.6f} m3\n"
                f"Vpa / Vp: {result.ratio:.6f}\n"
                f"Kontrol tablosu: {self.air_control_table_var.get()}"
            ),
        )
        self._set_banner("Hava icerik testi degerlendirmesi tamamlandi.", "success")


    def _clear_air_form(self) -> None:
        for key, variable in self.air_vars.items():
            if key in {"k_factor", "pressure_rise_bar"}:
                continue
            variable.set("")
        self.air_vars["pressure_rise_bar"].set("1.0")
        self.air_vars["k_factor"].set(self._default_k_factor())
        self.coefficient_states["air_a"] = "empty"
        self.air_backend_comparison_var.set(self._default_backend_comparison_text("air"))
        self.air_control_table_var.set(self._default_control_table_text("air"))
        self._remove_touched_fields("air")
        self._clear_feedback("air")
        self._refresh_coefficient_statuses()
        self._sync_backend_comparison_summary()
        self._sync_control_table_summary()
        self._reset_decision_card()
        self._set_banner("Hava icerik testi formu temizlendi.", "info")
        self._refresh_visual_schema()



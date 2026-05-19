from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from ..domain.hydrotest_core import ValidationError
from ..domain.operations import evaluate_pig_speed, get_pig_speed_limit, get_pig_speed_limit_options
from ..domain.depressurization import (
    DepressurizationStage,
    DepressurizationInputs,
    evaluate_depressurization,
)

if TYPE_CHECKING:
    from .app_main import HydrostaticTestApp


class FieldTabMixin:
    def _checked_control_lines(self: HydrostaticTestApp) -> list[str]:
        lines: list[str] = []
        for key, label, reference in self.FIELD_CHECK_DEFINITIONS:
            checked = "x" if self.control_check_vars[key].get() else " "
            lines.append(f"[{checked}] {label} ({reference})")
        return lines

    def _build_field_input_panel(self: HydrostaticTestApp, frame: ttk.Frame) -> None:
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        checklist_frame = ttk.LabelFrame(frame, text="Saha Kontrol Girdileri", padding=12)
        checklist_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        checklist_frame.columnconfigure(1, weight=1)
        ttk.Label(checklist_frame, text="Durum", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(checklist_frame, text="Kontrol noktasi", font=("Segoe UI", 9, "bold")).grid(
            row=0, column=1, sticky="w"
        )
        for row_index, (key, label, reference) in enumerate(self.FIELD_CHECK_DEFINITIONS, start=1):
            ttk.Checkbutton(checklist_frame, variable=self.control_check_vars[key]).grid(
                row=row_index, column=0, sticky="w", padx=(0, 8), pady=4
            )
            ttk.Label(checklist_frame, text=label, wraplength=self.input_subframe_wraplength, justify="left").grid(
                row=row_index, column=1, sticky="w", pady=4
            )
            ttk.Label(checklist_frame, text=reference, foreground="#35506B").grid(
                row=row_index, column=2, sticky="w", pady=4, padx=(8, 0)
            )

        pig_frame = ttk.LabelFrame(frame, text="Pig Hiz Girdileri", padding=12)
        pig_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        pig_frame.columnconfigure(1, weight=1)
        pig_frame.columnconfigure(3, weight=1)
        ttk.Label(pig_frame, text="Pig modu").grid(row=0, column=0, sticky="w", pady=6)
        self.pig_mode_combo = ttk.Combobox(
            pig_frame,
            textvariable=self.pig_mode_var,
            state="readonly",
            values=get_pig_speed_limit_options(),
            width=24,
        )
        self.pig_mode_combo.grid(row=0, column=1, columnspan=3, sticky="ew", padx=(0, 12), pady=6)
        self.pig_mode_combo.bind("<<ComboboxSelected>>", self._on_pig_mode_changed)
        ttk.Label(
            pig_frame,
            textvariable=self.pig_limit_var,
            wraplength=self.input_subframe_wraplength,
            justify="left",
            foreground="#35506B",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 8))
        self._add_entry(
            pig_frame,
            2,
            "Pig mesafesi (m)",
            self.field_vars["pig_distance_m"],
            field_key="field.pig_distance_m",
        )
        self._add_entry(
            pig_frame,
            2,
            "Varis suresi (dakika)",
            self.field_vars["pig_travel_time_min"],
            field_key="field.pig_travel_time_min",
            column=2,
        )
        self._add_entry(
            pig_frame,
            3,
            "Pig hizi (m/sn)",
            self.field_vars["pig_speed_m_per_s"],
            field_key="field.pig_speed_m_per_s",
            readonly=True,
        )
        self._add_entry(
            pig_frame,
            3,
            "Pig hizi (km/sa)",
            self.field_vars["pig_speed_km_per_h"],
            field_key="field.pig_speed_km_per_h",
            column=2,
            readonly=True,
        )

    def _build_field_tab(self: HydrostaticTestApp, frame: ttk.Frame) -> None:
        frame.columnconfigure(0, weight=1)

        input_wrapper = ttk.Frame(frame)
        input_wrapper.grid(row=0, column=0, sticky="ew")
        self._build_field_input_panel(input_wrapper)

        summary_frame = ttk.LabelFrame(frame, text="Saha Hesaplari ve Yontemler", padding=12)
        summary_frame.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        summary_frame.columnconfigure(0, weight=1)
        ttk.Label(
            summary_frame,
            textvariable=self.check_summary_var,
            foreground="#35506B",
            wraplength=self.workspace_wraplength,
            justify="left",
        ).grid(row=0, column=0, sticky="ew")
        self.check_progress = ttk.Progressbar(
            summary_frame,
            mode="determinate",
            maximum=len(self.FIELD_CHECK_DEFINITIONS),
            variable=self.check_progress_var,
        )
        self.check_progress.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(
            summary_frame,
            textvariable=self.pig_summary_var,
            wraplength=self.workspace_wraplength,
            justify="left",
        ).grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.pig_calculate_button = self._create_progress_button(
            summary_frame,
            key="pig_calculate",
            text="Pig Hizini Hesapla",
            command=self._on_pig_calculate_button,
        )
        self.pig_calculate_button.grid(row=3, column=0, sticky="w", pady=(10, 0))
        ttk.Label(
            summary_frame,
            textvariable=self.pig_status_var,
            foreground="#8A6D3B",
        ).grid(row=4, column=0, sticky="w", pady=(8, 0))
        ttk.Label(
            summary_frame,
            textvariable=self.pig_limit_var,
            wraplength=self.workspace_wraplength,
            justify="left",
            foreground="#35506B",
        ).grid(row=5, column=0, sticky="ew", pady=(8, 0))

        methods_frame = ttk.LabelFrame(frame, text="A ve B Tespit Yontemleri", padding=12)
        methods_frame.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        self._register_help_note(ttk.Label(
            methods_frame,
            text=(
                "Programda su an 4 tespit yolu vardir.\n"
                "A icin: 1) otomatik backend hesabi (CoolProp EOS veya Table Interpolation v1), "
                "2) BOTA\u015e veya GAIL referans tablosu, 3) manuel/prosedur tablosu girisi.\n"
                "B icin: 1) otomatik backend hesabi (su beta - celik alpha), 2) BOTA\u015e veya GAIL referans tablosu, "
                "3) manuel/prosedur tablosu girisi.\n"
                "Table Interpolation v1 dagitima uygun ikinci runtime backend olarak 0-40 degC ve 1-150 bar "
                "araliginda 1x1 grid ile calisir. Secili backend sag panelden degistirilebilir ve burada "
                "karsilastirma ozeti alinabilir."
            ),
            wraplength=self.workspace_wraplength,
            justify="left",
        )).grid(row=0, column=0, sticky="w")

        thermal_frame = ttk.LabelFrame(frame, text="Termal Dengeleme Kayitlari (Madde 12)", padding=12)
        thermal_frame.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        thermal_frame.columnconfigure(0, weight=1)
        add_row = ttk.Frame(thermal_frame)
        add_row.grid(row=0, column=0, sticky="ew")
        ttk.Label(add_row, text="Tarih/Saat (YYYY-AA-GG SS:DD)").pack(side="left")
        ttk.Entry(add_row, textvariable=self.thermal_timestamp_var, width=20).pack(side="left", padx=(8, 16))
        ttk.Label(add_row, text="Boru Sic. (degC)").pack(side="left")
        ttk.Entry(add_row, textvariable=self.thermal_pipe_temp_var, width=8).pack(side="left", padx=(8, 16))
        ttk.Button(add_row, text="Kayit Ekle", command=self._add_thermal_record).pack(side="left")
        ttk.Button(add_row, text="Secili Kaydi Sil", command=self._remove_thermal_record).pack(side="left", padx=(8, 0))
        ttk.Button(add_row, text="Tumunu Temizle", command=self._clear_thermal_records).pack(side="left", padx=(8, 0))

        self.thermal_tree = ttk.Treeview(
            thermal_frame,
            columns=("index", "timestamp", "pipe_temp"),
            show="headings",
            height=4,
        )
        self.thermal_tree.heading("index", text="#")
        self.thermal_tree.heading("timestamp", text="Tarih / Saat")
        self.thermal_tree.heading("pipe_temp", text="Boru Sic. (degC)")
        self.thermal_tree.column("index", width=30, anchor="center")
        self.thermal_tree.column("timestamp", width=160, anchor="w")
        self.thermal_tree.column("pipe_temp", width=100, anchor="e")
        self.thermal_tree.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        thermal_scroll = ttk.Scrollbar(thermal_frame, orient="vertical", command=self.thermal_tree.yview)
        thermal_scroll.grid(row=1, column=1, sticky="ns", pady=(8, 0))
        self.thermal_tree.configure(yscrollcommand=thermal_scroll.set)

        ttk.Label(
            thermal_frame,
            textvariable=self.thermal_result_var,
            wraplength=self.workspace_wraplength,
            justify="left",
            foreground="#35506B",
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        depr_frame = ttk.LabelFrame(frame, text="Basinc Dusurme ve Bosaltma Kayitlari (Madde 16-17)", padding=12)
        depr_frame.grid(row=4, column=0, sticky="ew", pady=(14, 0))
        depr_frame.columnconfigure(0, weight=1)
        add_row = ttk.Frame(depr_frame)
        add_row.grid(row=0, column=0, sticky="ew")
        ttk.Label(add_row, text="Kademe adi").pack(side="left")
        ttk.Entry(add_row, textvariable=self.depr_stage_label_var, width=14).pack(side="left", padx=(8, 8))
        ttk.Label(add_row, text="Baslangic (bar)").pack(side="left")
        ttk.Entry(add_row, textvariable=self.depr_start_pressure_var, width=8).pack(side="left", padx=(8, 8))
        ttk.Label(add_row, text="Bitis (bar)").pack(side="left")
        ttk.Entry(add_row, textvariable=self.depr_end_pressure_var, width=8).pack(side="left", padx=(8, 8))
        ttk.Label(add_row, text="Bekleme (dk)").pack(side="left")
        ttk.Entry(add_row, textvariable=self.depr_hold_time_var, width=6).pack(side="left", padx=(8, 8))
        ttk.Button(add_row, text="Kademe Ekle", command=self._add_depr_stage).pack(side="left")
        ttk.Button(add_row, text="Secili Kademeyi Sil", command=self._remove_depr_stage).pack(side="left", padx=(8, 0))
        ttk.Button(add_row, text="Tumunu Temizle", command=self._clear_depr_stages).pack(side="left", padx=(8, 0))

        self.depr_tree = ttk.Treeview(
            depr_frame,
            columns=("index", "stage_label", "start_pressure", "end_pressure", "hold_time"),
            show="headings",
            height=4,
        )
        self.depr_tree.heading("index", text="#")
        self.depr_tree.heading("stage_label", text="Kademe")
        self.depr_tree.heading("start_pressure", text="Baslangic (bar)")
        self.depr_tree.heading("end_pressure", text="Bitis (bar)")
        self.depr_tree.heading("hold_time", text="Bekleme (dk)")
        self.depr_tree.column("index", width=30, anchor="center")
        self.depr_tree.column("stage_label", width=120, anchor="w")
        self.depr_tree.column("start_pressure", width=90, anchor="e")
        self.depr_tree.column("end_pressure", width=80, anchor="e")
        self.depr_tree.column("hold_time", width=80, anchor="e")
        self.depr_tree.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        depr_scroll = ttk.Scrollbar(depr_frame, orient="vertical", command=self.depr_tree.yview)
        depr_scroll.grid(row=1, column=1, sticky="ns", pady=(8, 0))
        self.depr_tree.configure(yscrollcommand=depr_scroll.set)

        ttk.Label(
            depr_frame,
            textvariable=self.depr_result_var,
            wraplength=self.workspace_wraplength,
            justify="left",
            foreground="#35506B",
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        ttk.Label(
            frame,
            textvariable=self.section_feedback_vars["field"],
            foreground="#A4262C",
            wraplength=self.workspace_wraplength,
            justify="left",
        ).grid(row=5, column=0, sticky="w", pady=(12, 0))

    def _build_field_detail_report(self: HydrostaticTestApp) -> str:
        lines = [
            "Saha Kontrol - Detay Raporu",
            "",
            "Kontrol Noktalari",
            self.check_summary_var.get(),
        ]
        lines.extend(self._checked_control_lines())
        lines.extend(
            [
                "",
                "Test Bolumu Profili",
                f"Basinc penceresi: {self.section_pressure_summary_var.get()}",
                f"Canli basinc durumu: {self.section_pressure_status_var.get()}",
                f"Aktif pencere: {self.section_pressure_window_var.get()}",
                "",
                "Pig Hiz Hesabi",
                f"Pig modu: {self.pig_mode_var.get().strip() or '-'}",
                f"Mesafe: {self._format_detail_value(self.field_vars['pig_distance_m'], 'm')} (kullanici girdisi)",
                f"Varis suresi: {self._format_detail_value(self.field_vars['pig_travel_time_min'], 'dakika')} (kullanici girdisi)",
                f"Hiz (m/sn): {self._format_detail_value(self.field_vars['pig_speed_m_per_s'], 'm/sn')}",
                f"Hiz (km/sa): {self._format_detail_value(self.field_vars['pig_speed_km_per_h'], 'km/sa')}",
                f"Durum: {self.pig_status_var.get()}",
                f"Ozet: {self.pig_summary_var.get()}",
            ]
        )
        return "\n".join(lines)

    def _update_pig_limit_hint(self: HydrostaticTestApp) -> None:
        try:
            limit = get_pig_speed_limit(self.pig_mode_var.get())
        except ValidationError:
            self.pig_limit_var.set("Pig modu secilmedigi icin limit bilgisi gosterilemiyor.")
            self._refresh_visual_schema()
            return
        if limit.max_speed_m_per_s is None:
            self.pig_limit_var.set(f"Secili mod: {limit.label}. Bu secenekte limit karsilastirmasi yapilmaz.")
            self._refresh_visual_schema()
            return
        self.pig_limit_var.set(
            f"Secili mod: {limit.label}. Maksimum hiz = {limit.max_speed_m_per_s:.3f} m/sn "
            f"({limit.max_speed_km_per_h:.3f} km/sa). Referans: {limit.spec_reference}."
        )
        self._refresh_visual_schema()

    def _on_pig_mode_changed(self: HydrostaticTestApp, _: tk.Event | None = None) -> None:
        self._update_pig_limit_hint()

    def _add_thermal_record(self: HydrostaticTestApp) -> None:
        timestamp = self.thermal_timestamp_var.get().strip()
        temp_str = self.thermal_pipe_temp_var.get().strip().replace(",", ".")
        if not timestamp or not temp_str:
            self._set_banner("Tarih/saat ve sicaklik girilmelidir.", "warning")
            return
        try:
            pipe_temp = float(temp_str)
        except ValueError:
            self._set_banner("Gecerli bir sicaklik degeri girin.", "error")
            return
        self.thermal_records.append((timestamp, f"{pipe_temp:.2f}"))
        self._refresh_thermal_tree()
        self._evaluate_thermal_stabilization()
        self.thermal_timestamp_var.set("")
        self.thermal_pipe_temp_var.set("")
        self._set_banner("Termal kayit eklendi.", "success")

    def _remove_thermal_record(self: HydrostaticTestApp) -> None:
        selected = self.thermal_tree.selection()
        if not selected:
            self._set_banner("Silmek icin bir kayit secin.", "warning")
            return
        index = int(selected[0]) - 1
        if 0 <= index < len(self.thermal_records):
            self.thermal_records.pop(index)
            self._refresh_thermal_tree()
            self._evaluate_thermal_stabilization()
            self._set_banner("Termal kayit silindi.", "info")

    def _clear_thermal_records(self: HydrostaticTestApp) -> None:
        self.thermal_records.clear()
        self._refresh_thermal_tree()
        self.thermal_result_var.set(
            "24 saatlik termal dengeleme ve 0.5 degC son iki ortalama kontrolu henuz yapilmadi."
        )
        self._set_banner("Termal kayitlar temizlendi.", "info")

    def _refresh_thermal_tree(self: HydrostaticTestApp) -> None:
        if not hasattr(self, "thermal_tree"):
            return
        for item_id in self.thermal_tree.get_children():
            self.thermal_tree.delete(item_id)
        for index, (timestamp, pipe_temp) in enumerate(self.thermal_records, start=1):
            self.thermal_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(index, timestamp, pipe_temp),
            )

    def _evaluate_thermal_stabilization(self: HydrostaticTestApp) -> None:
        if len(self.thermal_records) < 2:
            self.thermal_result_var.set(
                "Degerlendirme icin en az 2 termal kayit gerekli. "
                f"Mevcut kayit: {len(self.thermal_records)}"
            )
            return
        try:
            from ..domain.thermal_stabilization import (
                ThermalRecord,
                ThermalStabilizationInputs,
                evaluate_thermal_stabilization,
            )
            from datetime import datetime
            records: list[ThermalRecord] = []
            for timestamp, pipe_temp in self.thermal_records:
                dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M")
                records.append(ThermalRecord(timestamp=dt, pipe_temp_c=float(pipe_temp)))
            result = evaluate_thermal_stabilization(ThermalStabilizationInputs(records=tuple(records)))
        except Exception as exc:
            self.thermal_result_var.set(f"Degerlendirme hatasi: {exc}")
            return
        self.thermal_result_var.set(
            f"Toplam sure: {result.total_hours:.1f} saat (limit: 24h) -> "
            f"{'YETERLI' if result.within_hours else 'YETERSIZ'} | "
            f"Son iki ortalama: {result.last_two_average_c:.3f} degC, "
            f"Onceki iki: {result.previous_two_average_c:.3f} degC, "
            f"|Delta|: {result.delta_between_averages_c:.3f} degC (limit: 0.5) -> "
            f"{'SINIR ICINDE' if result.within_delta else 'ASIM'} | "
            f"Nihai: {'BASARILI' if result.passed else 'BASARISIZ'}"
        )
        if result.passed:
            if self.control_check_vars.get("thermal_balance"):
                self.control_check_vars["thermal_balance"].set(True)
            self._update_check_summary()

    def _add_depr_stage(self: HydrostaticTestApp) -> None:
        label = self.depr_stage_label_var.get().strip()
        start_str = self.depr_start_pressure_var.get().strip().replace(",", ".")
        end_str = self.depr_end_pressure_var.get().strip().replace(",", ".")
        hold_str = self.depr_hold_time_var.get().strip().replace(",", ".")
        if not label or not start_str or not end_str or not hold_str:
            self._set_banner("Kademe adi, basinc ve sure bilgileri girilmelidir.", "warning")
            return
        try:
            start_p = float(start_str)
            end_p = float(end_str)
            hold = float(hold_str)
        except ValueError:
            self._set_banner("Gecerli sayisal degerler girin.", "error")
            return
        self.depr_records.append((label, f"{start_p:.2f}", f"{end_p:.2f}", f"{hold:.1f}"))
        self._refresh_depr_tree()
        self._evaluate_depressurization()
        self.depr_stage_label_var.set("")
        self.depr_start_pressure_var.set("")
        self.depr_end_pressure_var.set("")
        self.depr_hold_time_var.set("")
        self._set_banner("Basinc dusurme kademesi eklendi.", "success")

    def _remove_depr_stage(self: HydrostaticTestApp) -> None:
        selected = self.depr_tree.selection()
        if not selected:
            self._set_banner("Silmek icin bir kademe secin.", "warning")
            return
        index = int(selected[0]) - 1
        if 0 <= index < len(self.depr_records):
            self.depr_records.pop(index)
            self._refresh_depr_tree()
            if not self.depr_records:
                if self.control_check_vars.get("depressurize_discharge"):
                    self.control_check_vars["depressurize_discharge"].set(False)
                self._update_check_summary()
            self._evaluate_depressurization()
            self._set_banner("Basinc dusurme kademesi silindi.", "info")

    def _clear_depr_stages(self: HydrostaticTestApp) -> None:
        self.depr_records.clear()
        self._refresh_depr_tree()
        self.depr_result_var.set(
            "Basinc dusurme ve bosaltma kademeleri henuz degerlendirilmedi."
        )
        if self.control_check_vars.get("depressurize_discharge"):
            self.control_check_vars["depressurize_discharge"].set(False)
        self._update_check_summary()
        self._set_banner("Basinc dusurme kayitlari temizlendi.", "info")

    def _refresh_depr_tree(self: HydrostaticTestApp) -> None:
        if not hasattr(self, "depr_tree"):
            return
        for item_id in self.depr_tree.get_children():
            self.depr_tree.delete(item_id)
        for index, (label, start_p, end_p, hold) in enumerate(self.depr_records, start=1):
            self.depr_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(index, label, start_p, end_p, hold),
            )

    def _evaluate_depressurization(self: HydrostaticTestApp) -> None:
        if not self.depr_records:
            self.depr_result_var.set(
                "Degerlendirme icin en az 1 basinclandirma kademesi gerekli."
            )
            return
        try:
            pressure_bar_str = self.pressure_vars["pressure_bar"].get().strip().replace(",", ".")
            initial_pressure = float(pressure_bar_str) if pressure_bar_str else 0.0
        except ValueError:
            initial_pressure = 0.0
        if initial_pressure <= 0:
            self.depr_result_var.set(
                "Baslangic basinci icin Basinc Degisim Testi sekmesinde "
                "test basinci (P) girilmelidir."
            )
            return
        try:
            stages: list[DepressurizationStage] = []
            for label, start_p, end_p, hold in self.depr_records:
                stages.append(DepressurizationStage(
                    stage_label=label,
                    start_pressure_bar=float(start_p),
                    end_pressure_bar=float(end_p),
                    hold_minutes=float(hold),
                ))
            result = evaluate_depressurization(
                DepressurizationInputs(stages=tuple(stages), initial_pressure_bar=initial_pressure)
            )
        except Exception as exc:
            self.depr_result_var.set(f"Degerlendirme hatasi: {exc}")
            return
        self.depr_result_var.set(
            f"Kademe sayisi: {result.total_stages} | "
            f"Toplam sure: {result.total_time_min:.1f} dk | "
            f"Kademeli indirim: {'EVET' if result.gradual_reduction else 'HAYIR'} | "
            f"Bekleme suresi yeterli: {'EVET' if result.all_holds_sufficient else 'HAYIR'} | "
            f"Tam bosaltma: {'EVET' if result.full_depressurization else 'HAYIR'} | "
            f"Nihai: {'BASARILI' if result.passed else 'BASARISIZ'}"
        )
        if result.passed:
            if self.control_check_vars.get("depressurize_discharge"):
                self.control_check_vars["depressurize_discharge"].set(True)
            self._update_check_summary()

    def _on_pig_calculate_button(self: HydrostaticTestApp) -> object:
        return self._execute_progress_button_action(
            "pig_calculate",
            self._calculate_pig_speed,
            result_state_resolver=self._pig_progress_state,
        )

    def _calculate_pig_speed(self: HydrostaticTestApp, log_result: bool = True) -> bool:
        self._clear_feedback("field")
        try:
            limit = get_pig_speed_limit(self.pig_mode_var.get())
            result = evaluate_pig_speed(
                distance_m=self._read_float(
                    self.field_vars["pig_distance_m"], "Pig mesafesi", "field", "field.pig_distance_m"
                ),
                travel_time_min=self._read_float(
                    self.field_vars["pig_travel_time_min"],
                    "Varis suresi",
                    "field",
                    "field.pig_travel_time_min",
                ),
                limit=limit,
            )
        except ValidationError as exc:
            self.pig_status_var.set("Pig hiz hesabi dogrulanamadi.")
            self.pig_summary_var.set(str(exc))
            self._set_banner(str(exc), "error")
            self._refresh_detail_reports()
            return False

        self.field_vars["pig_speed_m_per_s"].set(f"{result.speed_m_per_s:.6f}")
        self.field_vars["pig_speed_km_per_h"].set(f"{result.speed_km_per_h:.6f}")

        if result.passed is None:
            status = "BILGI"
            summary = (
                f"Hesaplanan pig hizi = {result.speed_m_per_s:.6f} m/sn "
                f"({result.speed_km_per_h:.6f} km/sa). Secili modda limit karsilastirmasi yapilmadi."
            )
            banner_level = "info"
        elif result.passed:
            status = "UYGUN"
            summary = (
                f"Hesaplanan pig hizi = {result.speed_m_per_s:.6f} m/sn "
                f"({result.speed_km_per_h:.6f} km/sa). {result.limit.spec_reference} icin limit asilmadi."
            )
            banner_level = "success"
        else:
            status = "LIMIT ASILDI"
            summary = (
                f"Hesaplanan pig hizi = {result.speed_m_per_s:.6f} m/sn "
                f"({result.speed_km_per_h:.6f} km/sa). {result.limit.spec_reference} icin maksimum "
                f"{result.limit.max_speed_m_per_s:.6f} m/sn limiti asildi."
            )
            banner_level = "warning"

        self.pig_status_var.set(f"Pig hizi durumu: {status}")
        self.pig_summary_var.set(summary)
        self._set_banner("Pig hiz hesabi guncellendi.", banner_level)
        self._refresh_detail_reports()

        if log_result:
            self._append_result(
                "Pig Hiz Hesabi",
                (
                    f"Pig modu: {result.limit.label}\n"
                    f"Referans: {result.limit.spec_reference}\n"
                    f"Mesafe: {result.distance_m:.3f} m\n"
                    f"Varis suresi: {result.travel_time_min:.3f} dakika\n"
                    f"Hiz: {result.speed_m_per_s:.6f} m/sn\n"
                    f"Hiz: {result.speed_km_per_h:.6f} km/sa\n"
                    f"Durum: {status}"
                ),
            )
        return True

    def _clear_field_form(self: HydrostaticTestApp) -> None:
        for variable in self.field_vars.values():
            variable.set("")
        for variable in self.control_check_vars.values():
            variable.set(False)
        self.pig_mode_var.set(get_pig_speed_limit_options()[0])
        self.pig_status_var.set("Pig hiz hesabi henuz yapilmadi.")
        self.pig_summary_var.set(
            "Mesafe ve sure girildiginde pig hizi m/sn ve km/sa olarak burada gosterilir."
        )
        self._remove_touched_fields("field")
        self._clear_feedback("field")
        self._update_check_summary()
        self._update_pig_limit_hint()
        self._sync_backend_comparison_summary()
        self._set_banner("Saha kontrol formu temizlendi.", "info")
        self._refresh_visual_schema()

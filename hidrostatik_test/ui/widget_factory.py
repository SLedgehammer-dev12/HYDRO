from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from ..domain.hydrotest_core import ValidationError

if TYPE_CHECKING:
    from .app_main import HydrostaticTestApp


class WidgetFactoryMixin:
    def _configure_input_styles(self) -> None:
        palettes = {
            "neutral": "#FFFFFF",
            "success": "#EEF8EE",
            "warning": "#FFF6E5",
            "error": "#FDEAEA",
            "readonly": "#F5F7FA",
        }
        for widget_kind, style_suffix in (("entry", "TEntry"), ("combo", "TCombobox")):
            for level in ("neutral", "success", "warning", "error"):
                style_name = f"Hydro.{level}.{style_suffix}"
                color = palettes[level]
                self.ui_style.configure(style_name, fieldbackground=color, background=color)
                self.ui_style.map(
                    style_name,
                    fieldbackground=[
                        ("readonly", palettes["readonly"] if level == "neutral" else color),
                        ("disabled", palettes["readonly"]),
                    ],
                    background=[
                        ("readonly", palettes["readonly"] if level == "neutral" else color),
                        ("disabled", palettes["readonly"]),
                    ],
                )
        self.ui_style.configure("Hydro.readonly.TEntry", fieldbackground=palettes["readonly"], background=palettes["readonly"])
        self.ui_style.map(
            "Hydro.readonly.TEntry",
            fieldbackground=[("readonly", palettes["readonly"]), ("disabled", palettes["readonly"])],
            background=[("readonly", palettes["readonly"]), ("disabled", palettes["readonly"])],
        )


    def _add_entry(
        self,
        frame: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar,
        column: int = 0,
        field_key: str | None = None,
        readonly: bool = False,
    ) -> None:
        section = "general"
        required = not readonly
        if field_key is not None:
            prefix = field_key.split(".", 1)[0]
            section = "pressure" if prefix == "helper" else prefix
            if field_key in {
                "air.a_micro_per_bar",
                "pressure.a_micro_per_bar",
                "helper.water_beta_micro_per_c",
                "field.pig_speed_m_per_s",
                "field.pig_speed_km_per_h",
            }:
                required = False
        label_text = f"{label} *" if required else label
        ttk.Label(frame, text=label_text).grid(row=row, column=column, sticky="w", pady=6)
        state = "readonly" if readonly else "normal"
        entry_container = ttk.Frame(frame)
        entry_container.grid(
            row=row,
            column=column + 1,
            sticky="ew",
            padx=(0, 12),
            pady=6,
        )
        entry_container.columnconfigure(0, weight=1)
        entry = ttk.Entry(
            entry_container,
            textvariable=variable,
            state=state,
            style="Hydro.readonly.TEntry" if readonly else "Hydro.neutral.TEntry",
            width=self._entry_width_for_field(field_key),
        )
        entry.grid(row=0, column=0, sticky="ew")
        if field_key is not None:
            self.entry_widgets[field_key] = entry
            self.input_widgets[field_key] = entry
            self.field_meta[field_key] = {
                "label": label,
                "section": section,
                "required": required,
                "readonly": readonly,
                "value_type": "numeric",
            }
            message_var = tk.StringVar()
            self.field_message_vars[field_key] = message_var
            message_label = ttk.Label(
                entry_container,
                textvariable=message_var,
                foreground="#6B7280",
                wraplength=280,
                justify="left",
            )
            message_label.grid(row=1, column=0, sticky="w", pady=(3, 0))
            self.field_message_labels[field_key] = message_label
            self.field_validation_levels[field_key] = "neutral"


    def _register_choice_widget(
        self,
        *,
        field_key: str,
        widget: tk.Widget,
        section: str,
        label: str,
        required: bool,
    ) -> None:
        self.input_widgets[field_key] = widget
        self.field_meta[field_key] = {
            "label": label,
            "section": section,
            "required": required,
            "readonly": False,
            "value_type": "choice",
        }
        self.field_validation_levels[field_key] = "neutral"


    def _entry_width_for_field(self, field_key: str | None) -> int:
        if field_key is None:
            return 16
        compact_fields = {
            "geometry.outside_diameter_mm",
            "geometry.wall_thickness_mm",
            "geometry.length_m",
            "geometry.highest_elevation_m",
            "geometry.lowest_elevation_m",
            "geometry.start_elevation_m",
            "geometry.end_elevation_m",
            "geometry.design_pressure_bar",
            "geometry.smys_mpa",
            "air.temperature_c",
            "air.pressure_bar",
            "air.pressure_rise_bar",
            "air.k_factor",
            "air.actual_added_water_m3",
            "pressure.temperature_c",
            "pressure.pressure_bar",
            "pressure.delta_t_c",
            "pressure.actual_pressure_change_bar",
            "helper.steel_alpha_micro_per_c",
            "helper.water_beta_micro_per_c",
            "field.pig_distance_m",
            "field.pig_travel_time_min",
            "field.pig_speed_m_per_s",
            "field.pig_speed_km_per_h",
        }
        coefficient_fields = {
            "air.a_micro_per_bar",
            "pressure.a_micro_per_bar",
            "pressure.b_micro_per_c",
        }
        if field_key in coefficient_fields:
            return 18
        if field_key in compact_fields:
            return 14
        return 16


    def _widget_style_for_field(self, field_key: str, level: str) -> str | None:
        widget = self.input_widgets.get(field_key)
        if widget is None:
            return None
        meta = self.field_meta.get(field_key, {})
        if isinstance(widget, ttk.Combobox):
            return f"Hydro.{level}.TCombobox"
        if isinstance(widget, ttk.Entry):
            if meta.get("readonly") and level == "neutral":
                return "Hydro.readonly.TEntry"
            return f"Hydro.{level}.TEntry"
        return None


    def _apply_field_visual_state(self, field_key: str, level: str) -> None:
        normalized_level = level if level in {"neutral", "success", "warning", "error"} else "neutral"
        self.field_validation_levels[field_key] = normalized_level
        style_name = self._widget_style_for_field(field_key, normalized_level)
        widget = self.input_widgets.get(field_key)
        if style_name is not None and widget is not None:
            widget.configure(style=style_name)
        message_label = self.field_message_labels.get(field_key)
        if message_label is not None:
            palette = {
                "neutral": "#6B7280",
                "success": "#1E6F43",
                "warning": "#8A5B00",
                "error": "#A4262C",
            }
            message_label.configure(foreground=palette[normalized_level])


    def _register_traces(self) -> None:
        for variable in self.geometry_vars.values():
            variable.trace_add("write", lambda *_: self._refresh_geometry_summary())
        for variable in self.section_profile_vars.values():
            variable.trace_add("write", lambda *_: self._refresh_geometry_summary())
        self.material_grade_var.trace_add("write", lambda *_: self._on_material_grade_changed())
        self.material_grade_var.trace_add("write", lambda *_: self._refresh_choice_validation_states())
        self.ambient_temp_var.trace_add("write", lambda *_: self._check_ambient_temp_constraint())
        for field_key, variable in (
            [(f"geometry.{key}", variable) for key, variable in self.geometry_vars.items()]
            + [(f"geometry.{key}", variable) for key, variable in self.section_profile_vars.items()]
            + [("geometry.ambient_temp_c", self.ambient_temp_var)]
            + [(f"air.{key}", variable) for key, variable in self.air_vars.items()]
            + [(f"pressure.{key}", variable) for key, variable in self.pressure_vars.items()]
            + [(f"field.{key}", variable) for key, variable in self.field_vars.items()]
            + [(f"helper.{key}", variable) for key, variable in self.b_helper_vars.items()]
            + [(f"pv.{key}", variable) for key, variable in self.pv_vars.items()]
        ):
            if field_key in self.field_meta:
                variable.trace_add("write", lambda *_args, key=field_key, var=variable: self._on_live_field_change(key, var))
        self.location_class_var.trace_add("write", lambda *_: self._refresh_geometry_summary())
        self.location_class_var.trace_add("write", lambda *_: self._refresh_choice_validation_states())
        self.pump_location_var.trace_add("write", lambda *_: self._refresh_geometry_summary())
        self.pump_location_var.trace_add("write", lambda *_: self._refresh_choice_validation_states())
        self.air_a_reference_var.trace_add("write", lambda *_: self._refresh_choice_validation_states())
        self.pressure_a_reference_var.trace_add("write", lambda *_: self._refresh_choice_validation_states())
        self.pressure_b_reference_var.trace_add("write", lambda *_: self._refresh_choice_validation_states())
        self.air_vars["temperature_c"].trace_add("write", lambda *_: self._mark_dependencies_changed(("air_a",)))
        self.air_vars["pressure_bar"].trace_add("write", lambda *_: self._mark_dependencies_changed(("air_a",)))
        self.air_vars["pressure_bar"].trace_add("write", lambda *_: self._refresh_geometry_summary())
        self.pressure_vars["temperature_c"].trace_add(
            "write", lambda *_: self._mark_dependencies_changed(("pressure_a", "pressure_b"))
        )
        self.pressure_vars["pressure_bar"].trace_add(
            "write", lambda *_: self._mark_dependencies_changed(("pressure_a", "pressure_b"))
        )
        self.pressure_vars["pressure_bar"].trace_add("write", lambda *_: self._refresh_geometry_summary())
        self.b_helper_vars["steel_alpha_micro_per_c"].trace_add(
            "write", lambda *_: self._mark_dependencies_changed(("pressure_b",))
        )
        for variable in self.control_check_vars.values():
            variable.trace_add("write", lambda *_: self._update_check_summary())
        self.pig_mode_var.trace_add("write", lambda *_: self._update_pig_limit_hint())
        self.update_download_dir_var.trace_add("write", lambda *_: self._refresh_update_download_summary())
        self.air_vars["a_micro_per_bar"].trace_add(
            "write", lambda *_: self._on_coefficient_field_changed("air_a", self.air_vars["a_micro_per_bar"])
        )
        self.pressure_vars["a_micro_per_bar"].trace_add(
            "write", lambda *_: self._on_coefficient_field_changed("pressure_a", self.pressure_vars["a_micro_per_bar"])
        )
        self.pressure_vars["b_micro_per_c"].trace_add(
            "write", lambda *_: self._on_coefficient_field_changed("pressure_b", self.pressure_vars["b_micro_per_c"])
        )


    def _create_source_badge(
        self,
        parent: tk.Misc,
        *,
        key: str,
        registry: dict[str, tk.Label],
    ) -> tk.Label:
        label = tk.Label(
            parent,
            textvariable=self.coefficient_source_vars[key],
            bg="#EEF2FF",
            fg="#243B73",
            padx=8,
            pady=3,
            font=("Segoe UI", 8, "bold"),
        )
        registry[key] = label
        return label


    def _create_progress_button(
        self,
        parent: tk.Misc,
        *,
        key: str,
        text: str,
        command: object,
    ) -> tk.Button:
        button = tk.Button(
            parent,
            text=text,
            command=command,
            bg="#EEF2FF",
            fg="#243B73",
            activebackground="#DCE7FF",
            activeforeground="#243B73",
            relief="flat",
            bd=0,
            padx=12,
            pady=6,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
        )
        self.progress_buttons[key] = button
        self.progress_button_idle_texts[key] = text
        return button


    def _set_progress_button_idle_text(self, key: str, text: str) -> None:
        self.progress_button_idle_texts[key] = text
        if key not in self.progress_button_busy:
            button = self.progress_buttons.get(key)
            if button is not None:
                button.configure(text=text)


    def _apply_progress_button_appearance(self, key: str, state: str, text: str | None = None) -> None:
        button = self.progress_buttons.get(key)
        if button is None:
            return
        palette = {
            "idle": ("#EEF2FF", "#243B73"),
            "working": ("#FFF6E5", "#8A5B00"),
            "success": ("#EAF7EA", "#1D5F2F"),
            "warning": ("#FFF6E5", "#8A5B00"),
            "error": ("#FDEAEA", "#8B1E1E"),
            "info": ("#EAF2FF", "#1E4E8C"),
        }
        bg, fg = palette.get(state, palette["idle"])
        target_text = text if text is not None else self.progress_button_idle_texts.get(key, button.cget("text"))
        button.configure(
            text=target_text,
            bg=bg,
            fg=fg,
            activebackground=bg,
            activeforeground=fg,
        )


    def _reset_progress_button(self, key: str) -> None:
        self.progress_button_busy.discard(key)
        self.progress_button_reset_jobs.pop(key, None)
        self._apply_progress_button_appearance(key, "idle")


    def _finish_progress_button(self, key: str, state: str) -> None:
        button = self.progress_buttons.get(key)
        if button is None:
            return
        idle_text = self.progress_button_idle_texts.get(key, button.cget("text"))
        suffix = {
            "success": "Tamam",
            "warning": "Kontrol Et",
            "error": "Hata",
            "info": "Bilgi",
        }.get(state)
        display_text = idle_text if suffix is None else f"{idle_text} - {suffix}"
        self._apply_progress_button_appearance(key, state, display_text)
        existing_job = self.progress_button_reset_jobs.pop(key, None)
        if existing_job is not None:
            self.root.after_cancel(existing_job)
        self.progress_button_reset_jobs[key] = self.root.after(1400, lambda: self._reset_progress_button(key))


    def _execute_progress_button_action(
        self,
        key: str,
        action: object,
        *,
        result_state_resolver: object,
        working_text: str | None = None,
    ) -> object:
        if key in self.progress_button_busy:
            return None
        self.progress_button_busy.add(key)
        idle_text = self.progress_button_idle_texts.get(key, "")
        self._apply_progress_button_appearance(key, "working", working_text or f"{idle_text}...")
        self.root.update_idletasks()
        try:
            result = action()
        except Exception:
            self._finish_progress_button(key, "error")
            raise
        state = result_state_resolver(result)
        self._finish_progress_button(key, state)
        return result


    def _bool_progress_state(self, result: object) -> str:
        return "success" if result else "error"


    def _decision_progress_state(self, _: object = None) -> str:
        status = self.decision_status_var.get().strip()
        if status == "BASARILI":
            return "success"
        if status == "BASARISIZ":
            return "warning"
        if status == "DOGRULANAMADI":
            return "error"
        return "info"


    def _pig_progress_state(self, result: object) -> str:
        if not result:
            return "error"
        status = self.pig_status_var.get().strip()
        if "UYGUN" in status:
            return "success"
        if "LIMIT ASILDI" in status:
            return "warning"
        return "info"

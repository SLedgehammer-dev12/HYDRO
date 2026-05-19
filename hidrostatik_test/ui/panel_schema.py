from __future__ import annotations

from typing import TYPE_CHECKING

from ..domain.hydrotest_core import PipeSection

if TYPE_CHECKING:
    from .app_main import HydrostaticTestApp


class PanelSchemaMixin:
    def _visual_segment_payload(self: HydrostaticTestApp) -> list[dict[str, float]]:
        segments: list[dict[str, float]] = []
        if self.geometry_segments:
            for segment_info in self.geometry_segments:
                pipe = segment_info["pipe"]
                assert isinstance(pipe, PipeSection)
                segments.append(
                    {
                        "length_m": pipe.length_m,
                        "outside_diameter_mm": pipe.outside_diameter_mm,
                        "wall_thickness_mm": pipe.wall_thickness_mm,
                    }
                )
            return segments

        outside = self._safe_float(self.geometry_vars["outside_diameter_mm"].get())
        wall = self._safe_float(self.geometry_vars["wall_thickness_mm"].get())
        length = self._safe_float(self.geometry_vars["length_m"].get())
        if outside is None or wall is None or length is None:
            return []
        if outside <= 0 or wall <= 0 or length <= 0 or (wall * 2) >= outside:
            return []
        return [
            {
                "length_m": length,
                "outside_diameter_mm": outside,
                "wall_thickness_mm": wall,
            }
        ]

    def _refresh_visual_schema(self: HydrostaticTestApp) -> None:
        if not hasattr(self, "visual_canvas"):
            return
        canvas = self.visual_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 340)
        active_tab = self._active_tab_key()
        selector_specs = (
            ("air", "Hava", 24, 100),
            ("pressure", "Basinc", 124, 224),
            ("field", "Saha", 248, 336),
        )
        for tab_key, label, left, right in selector_specs:
            fill = "#DDEBFF" if tab_key == active_tab else "#FFFFFF"
            outline = "#4A74A8" if tab_key == active_tab else "#C6D0E0"
            tag = f"schema_nav_{tab_key}"
            canvas.create_rectangle(left, 16, right, 46, fill=fill, outline=outline, width=1.5, tags=(tag,))
            canvas.create_text((left + right) / 2, 31, text=label, fill="#16365D", font=("Segoe UI", 9, "bold"), tags=(tag,))
            canvas.tag_bind(tag, "<Button-1>", lambda _event, key=tab_key: self._select_tab_by_key(key))

        pipe_y = 116
        canvas.create_line(28, pipe_y, width - 28, pipe_y, fill="#B9C4D6", width=4)
        segments = self._visual_segment_payload()
        if segments:
            total_length = sum(segment["length_m"] for segment in segments) or 1.0
            available_width = width - 80
            current_x = 40.0
            palette = ("#6FA8DC", "#93C47D", "#F6B26B", "#C27BA0")
            for index, segment in enumerate(segments, start=1):
                segment_width = max(36.0, available_width * (segment["length_m"] / total_length))
                visual_height = max(16.0, min(30.0, 14.0 + (segment["outside_diameter_mm"] / 40.0)))
                top = pipe_y - (visual_height / 2)
                bottom = pipe_y + (visual_height / 2)
                fill = palette[(index - 1) % len(palette)]
                canvas.create_rectangle(current_x, top, current_x + segment_width, bottom, fill=fill, outline="#35506B")
                canvas.create_text(
                    current_x + (segment_width / 2),
                    bottom + 16,
                    text=f"S{index} | {segment['length_m']:.0f} m",
                    fill="#35506B",
                    font=("Segoe UI", 8),
                )
                current_x += segment_width
        else:
            canvas.create_rectangle(40, pipe_y - 12, width - 40, pipe_y + 12, outline="#C6D0E0", dash=(4, 2))
            canvas.create_text(
                width / 2,
                pipe_y,
                text="Geometri girdileri tamamlandiginda hat semasi burada canlanir.",
                fill="#6B7280",
                font=("Segoe UI", 9),
            )

        backend_label = self._selected_water_backend_info().label
        if active_tab == "air":
            air_state = self.coefficient_status_vars["air_a"].get()
            canvas.create_oval(52, 150, 88, 186, fill="#D8EEF9", outline="#4A74A8")
            canvas.create_text(70, 168, text="A", fill="#16365D", font=("Segoe UI", 10, "bold"))
            canvas.create_text(150, 160, text="P = 1.0 bar", fill="#16365D", font=("Segoe UI", 9, "bold"))
            canvas.create_text(242, 160, text="K", fill="#16365D", font=("Segoe UI", 9, "bold"))
            canvas.create_text(320, 160, text="Vpa", fill="#16365D", font=("Segoe UI", 9, "bold"))
            self.visual_schema_var.set(
                "Hava testi akisi gosteriliyor. "
                f"Geometriye gore A, P=1.0 bar, K ve Vpa adimlari okunur. A durumu: {air_state}. "
                f"Secili backend: {backend_label}."
            )
        elif active_tab == "pressure":
            pressure_a_state = self.coefficient_status_vars["pressure_a"].get()
            pressure_b_state = self.coefficient_status_vars["pressure_b"].get()
            canvas.create_text(68, 166, text="A", fill="#16365D", font=("Segoe UI", 10, "bold"))
            canvas.create_text(130, 166, text="B", fill="#16365D", font=("Segoe UI", 10, "bold"))
            canvas.create_text(210, 154, text="dT = Tilk - Tson", fill="#16365D", font=("Segoe UI", 9, "bold"))
            canvas.create_text(316, 178, text="Pa = Pilk - Pson", fill="#16365D", font=("Segoe UI", 9, "bold"))
            self.visual_schema_var.set(
                "Basinc degisim testi akisi gosteriliyor. "
                f"A ve B hazirlandiktan sonra dT ve Pa okunur. A durumu: {pressure_a_state}; "
                f"B durumu: {pressure_b_state}. Secili backend: {backend_label}."
            )
        else:
            checked_count = sum(1 for variable in self.control_check_vars.values() if variable.get())
            pig_speed = self.field_vars["pig_speed_m_per_s"].get().strip() or "-"
            canvas.create_oval(52, 150, 88, 186, fill="#FCE5CD", outline="#B45F06")
            canvas.create_text(70, 168, text="PIG", fill="#7F3F00", font=("Segoe UI", 8, "bold"))
            canvas.create_line(88, 168, 160, 168, fill="#B45F06", width=3, arrow="last")
            canvas.create_text(
                250,
                156,
                text=f"Checklist: {checked_count}/{len(self.control_check_vars)} | Mesafe + sure -> hiz",
                fill="#16365D",
                font=("Segoe UI", 9, "bold"),
            )
            canvas.create_text(250, 178, text=f"Anlik hiz: {pig_speed} m/sn", fill="#35506B", font=("Segoe UI", 9))
            self.visual_schema_var.set(
                "Saha kontrol akisi gosteriliyor. "
                f"Isaretlenen kontrol noktasi: {checked_count}/{len(self.control_check_vars)}. "
                "Checklist tamamlandiktan sonra pig mesafesi ve suresi girilerek hiz limiti dogrulanir."
            )

        canvas.create_text(
            width - 12,
            204,
            text=f"Backend: {backend_label}",
            fill="#35506B",
            font=("Segoe UI", 8),
            anchor="e",
        )

        status = self.schema_status_var.get()
        badge_colors = {
            "BEKLIYOR": ("#E5E7EB", "#6B7280"),
            "HESAPLANDI": ("#E6F4EA", "#1E6F43"),
            "DEGISTI": ("#FFF6E5", "#8A5B00"),
        }
        bg, fg = badge_colors.get(status, ("#E5E7EB", "#6B7280"))
        badge_x1, badge_x2 = width - 164, width - 12
        canvas.create_rectangle(badge_x1, 16, badge_x2, 42, fill=bg, outline=bg, width=0)
        canvas.create_text((badge_x1 + badge_x2) / 2, 29, text=status, fill=fg, font=("Segoe UI", 8, "bold"))

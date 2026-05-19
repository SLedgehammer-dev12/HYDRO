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
    SectionPressureProfileResult,
)

if TYPE_CHECKING:
    from .app_main import HydrostaticTestApp


class PressureDetailMixin:
    """Pressure detail report, status card, comparison and control table mixin."""

    def _build_section_pressure_summary(self) -> str:
        result, error = self._section_pressure_profile_result()
        if error is not None:
            return (
                "Basinc kontrolu henuz tamamlanmadi. "
                "Min/max kotlar, dizayn basinci, API 5L PSL2 malzeme kalitesi, SMYS, Location Class ve pompa konumu "
                "girildiginde pompa noktasinda izlenmesi gereken basinc penceresi hesaplanir. "
                f"Durum: {error}."
            )
        assert result is not None
        selected_window = result.selected_window
        material_grade = self._selected_material_grade()
        parts = [
            (
                f"Malzeme: {self.material_grade_var.get().strip() or '-'} | "
                f"SMYS = {self.section_profile_vars['smys_mpa'].get().strip() or '-'} MPa."
            ),
            (
                f"Test bolumu uzunlugu = {result.total_length_m:.3f} m, geometrik hacim Vt = "
                f"{result.total_internal_volume_m3:.6f} m3."
            ),
            (
                f"Yuksek noktada korunmasi gereken minimum test basinci = "
                f"{result.required_minimum_pressure_at_high_point_bar:.6f} bar "
                f"({result.location_class.label})."
            ),
            (
                f"100% SMYS limiti (kritik dusuk nokta) = "
                f"{result.maximum_allowable_pressure_at_low_point_bar:.6f} bar | "
                f"{result.limiting_pipe_description}."
            ),
            (
                f"Ek kontrol: yuksek nokta min basinci + kot farki = "
                f"{result.required_pressure_with_span_bar:.6f} bar. "
                f"Bu deger 100% SMYS limitini "
                f"{'asmiyor' if result.within_100_smys_span_limit else 'asiyor'}."
            ),
            (
                f"{result.start_window.location_label}: min izlenen = "
                f"{result.start_window.minimum_required_pressure_bar:.6f} bar, max izlenen = "
                f"{result.start_window.maximum_allowable_pressure_bar:.6f} bar."
            ),
            (
                f"{result.end_window.location_label}: min izlenen = "
                f"{result.end_window.minimum_required_pressure_bar:.6f} bar, max izlenen = "
                f"{result.end_window.maximum_allowable_pressure_bar:.6f} bar."
            ),
            (
                f"Secili pompa konumu {selected_window.location_label}: aktif pencere = "
                f"{selected_window.minimum_required_pressure_bar:.6f} - "
                f"{selected_window.maximum_allowable_pressure_bar:.6f} bar."
            ),
        ]
        if material_grade is not None:
            parts.append(
                f"Malzeme grade referansi: API 5L PSL2 {material_grade['grade']} / {material_grade['iso_label']}."
            )
        if not result.within_length_limit:
            parts.append("Uyari: test bolumu uzunlugu 20 km sartname limitini asiyor.")
        if not result.within_volume_limit:
            parts.append("Uyari: test bolumu hacmi 12.500 m3 sartname limitini asiyor.")
        if not result.within_100_smys_span_limit:
            parts.append(
                "Uyari: minimum yuksek nokta basinci ile min-max kot farkindan gelen toplam basinc 100% SMYS limitini asiyor."
            )
        monitored_pressure = result.monitored_pressure_bar
        if monitored_pressure is not None:
            status_bits = []
            if result.monitored_meets_minimum:
                status_bits.append("minimum saglandi")
            else:
                status_bits.append("minimum saglanmadi")
            if result.monitored_under_maximum:
                status_bits.append("maksimum asilmadi")
            else:
                status_bits.append("kritik maksimum asildi")
            parts.append(
                f"Aktif sekme su basinci = {monitored_pressure:.6f} bar -> " + ", ".join(status_bits) + "."
            )
        return " ".join(parts)

    def _update_section_pressure_status_card(
        self,
        result: SectionPressureProfileResult | None,
        error: str | None,
    ) -> None:
        if error is not None or result is None:
            self.section_pressure_status_var.set("VERI EKSIK")
            self.section_pressure_status_detail_var.set(
                "Basinc penceresi hesaplanamadi. Eksik veya tutarsiz bilgi: "
                + (error or "bilgi bekleniyor")
                + "."
            )
            self.section_pressure_window_var.set(
                "Aktif pencere: en yuksek ve en dusuk kot, baslangic ve bitis kotu, dizayn basinci, "
                "API 5L PSL2 malzeme kalitesi, Location Class ve pompa konumu gereklidir."
            )
            self.section_pressure_logic_var.set(
                "Mantik: yuksek noktadaki minimum test basinci korunur; dusuk noktadaki basinc 100% SMYS limitini asmamalidir."
            )
            self.section_pressure_status_label.configure(bg="#EEF2FF", fg="#243B73")
            return

        selected_window = result.selected_window
        self.section_pressure_window_var.set(
            f"{selected_window.location_label} icin izleme penceresi: "
            f"min {selected_window.minimum_required_pressure_bar:.6f} bar | "
            f"max {selected_window.maximum_allowable_pressure_bar:.6f} bar."
        )
        self.section_pressure_logic_var.set(
            f"Hidrolik kot farki = {result.hydraulic_span_bar:.6f} bar. "
            f"Yuksek nokta min gereksinimi = {result.required_minimum_pressure_at_high_point_bar:.6f} bar. "
            f"Yuksek nokta min + kot farki = {result.required_pressure_with_span_bar:.6f} bar. "
            f"Dusuk nokta 100% SMYS limiti = {result.maximum_allowable_pressure_at_low_point_bar:.6f} bar."
        )

        if not result.within_100_smys_span_limit:
            self.section_pressure_status_var.set("PENCERE UYGULANAMAZ")
            self.section_pressure_status_detail_var.set(
                "Yuksek noktada korunmasi gereken minimum test basinci ile min-max kot farkindan gelen toplam basinc, "
                "dusuk noktadaki 100% SMYS limitini asiyor."
            )
            self.section_pressure_status_label.configure(bg="#FDE7E9", fg="#A4262C")
            return

        if not result.within_length_limit or not result.within_volume_limit:
            issues: list[str] = []
            if not result.within_length_limit:
                issues.append(f"uzunluk {result.total_length_m:.3f} m ile 20 km limitini asiyor")
            if not result.within_volume_limit:
                issues.append(f"hacim {result.total_internal_volume_m3:.6f} m3 ile 12.500 m3 limitini asiyor")
            self.section_pressure_status_var.set("KESIT LIMIT ASIMI")
            self.section_pressure_status_detail_var.set(
                "Test bolumu 5007 sartnamesindeki kesit sinirlarini saglamiyor: " + ", ".join(issues) + "."
            )
            self.section_pressure_status_label.configure(bg="#FFF6E5", fg="#8A5B00")
            return

        if result.monitored_pressure_bar is None:
            self.section_pressure_status_var.set("PENCERE HAZIR")
            self.section_pressure_status_detail_var.set(
                "Basinc penceresi hesaplandi. Aktif sekmedeki test basinci girildiginde minimum ve maksimum kontrolleri "
                "otomatik yorumlanir."
            )
            self.section_pressure_status_label.configure(bg="#EEF7E8", fg="#2D6A2D")
            return

        meets_min = bool(result.monitored_meets_minimum)
        under_max = bool(result.monitored_under_maximum)
        monitored_text = (
            f"Izlenen basinc = {result.monitored_pressure_bar:.6f} bar. "
            f"Minimum {'saglandi' if meets_min else 'saglanmadi'}, "
            f"maksimum {'asilmadi' if under_max else 'asildi'}."
        )
        if meets_min and under_max:
            self.section_pressure_status_var.set("PENCERE ICINDE")
            self.section_pressure_status_detail_var.set(
                monitored_text + " Test bolumu secili pompa noktasinda izin verilen pencere icinde gorunuyor."
            )
            self.section_pressure_status_label.configure(bg="#E6F4EA", fg="#1E6F43")
        elif not meets_min and under_max:
            self.section_pressure_status_var.set("MINIMUM ALTINDA")
            self.section_pressure_status_detail_var.set(
                monitored_text + " Yuksek noktadaki zorunlu minimum test basinci korunmuyor."
            )
            self.section_pressure_status_label.configure(bg="#FFF6E5", fg="#8A5B00")
        elif meets_min and not under_max:
            self.section_pressure_status_var.set("MAKSIMUM ASILIYOR")
            self.section_pressure_status_detail_var.set(
                monitored_text + " Dusuk noktadaki 100% SMYS limiti asiliyor."
            )
            self.section_pressure_status_label.configure(bg="#FDE7E9", fg="#A4262C")
        else:
            self.section_pressure_status_var.set("PENCERE DISINDA")
            self.section_pressure_status_detail_var.set(
                monitored_text + " Hem minimum gereksinim saglanmiyor hem de maksimum limit asiliyor."
            )
            self.section_pressure_status_label.configure(bg="#FDE7E9", fg="#A4262C")

    def _build_pressure_detail_report(self) -> str:
        lines = [
            "Basinc Degisim Testi - Detay Raporu",
            "",
            "Katsayi Durumu",
            f"A modu: {self.pressure_a_mode_var.get().strip()}",
            f"A durum: {self.coefficient_status_vars['pressure_a'].get()}",
            f"A kaynagi: {self._coefficient_origin_text('pressure_a')}",
            f"A degeri: {self._format_detail_value(self.pressure_vars['a_micro_per_bar'], '(10^-6 / bar)')}",
            f"B modu: {self.pressure_b_mode_var.get().strip()}",
            f"B durum: {self.coefficient_status_vars['pressure_b'].get()}",
            f"B kaynagi: {self._coefficient_origin_text('pressure_b')}",
            f"B degeri: {self._format_detail_value(self.pressure_vars['b_micro_per_c'], '(10^-6 / degC)')}",
            f"B helper modu: {'Acik' if self.use_b_helper_var.get() else 'Kapali'}",
            f"Celik alpha: {self._format_detail_value(self.b_helper_vars['steel_alpha_micro_per_c'], '(10^-6 / degC)')}",
            f"Su beta: {self._format_detail_value(self.b_helper_vars['water_beta_micro_per_c'], '(10^-6 / degC)')}",
            f"Su backend'i: {self._selected_water_backend_info().label}",
            f"Backend karsilastirmasi: {self.pressure_backend_comparison_var.get()}",
            f"Kontrol tablosu: {self.pressure_control_table_var.get()}",
            "",
            "Kullanici Girdileri",
            f"Su sicakligi: {self._format_detail_value(self.pressure_vars['temperature_c'], 'degC')} (kullanici girdisi)",
            f"Su basinci: {self._format_detail_value(self.pressure_vars['pressure_bar'], 'bar')} (kullanici girdisi)",
            f"dT = Tilk - Tson: {self._format_detail_value(self.pressure_vars['delta_t_c'], 'degC')} (kullanici girdisi)",
            f"Pa = Pilk - Pson: {self._format_detail_value(self.pressure_vars['actual_pressure_change_bar'], 'bar')} (kullanici girdisi)",
            "",
            "Geometri",
            f"Ozet: {self.geometry_summary_var.get()}",
            f"Basinc penceresi: {self.section_pressure_summary_var.get()}",
        ]
        if self.geometry_segments:
            lines.append(f"Segment ozeti: {self.segment_summary_var.get()}")

        lines.extend(
            [
                "",
                "Degerlendirme Temeli",
                "Karar kurali: (Pa - Pt) <= 0.3 bar",
                "Formul: Pt = (B x dT) / ((0.884 x ri / s) + A)",
            ]
        )

        pipe, pipe_error = self._detail_pipe_snapshot()
        issues = [
            issue
            for issue in (
                pipe_error,
                self._detail_numeric_issue(self.pressure_vars["a_micro_per_bar"], "A degeri"),
                self._detail_numeric_issue(self.pressure_vars["b_micro_per_c"], "B degeri"),
                self._detail_numeric_issue(self.pressure_vars["delta_t_c"], "dT"),
                self._detail_numeric_issue(self.pressure_vars["actual_pressure_change_bar"], "Pa"),
            )
            if issue is not None
        ]
        if self.coefficient_states["pressure_a"] == "stale":
            issues.append("A katsayisi guncellenmeli")
        if self.coefficient_states["pressure_b"] == "stale":
            issues.append("B katsayisi guncellenmeli")
        if issues:
            lines.append("Degerlendirme hazir degil: " + ", ".join(issues) + ".")
            return "\n".join(lines)

        assert pipe is not None
        a_value = self._safe_float(self.pressure_vars["a_micro_per_bar"].get())
        b_value = self._safe_float(self.pressure_vars["b_micro_per_c"].get())
        delta_t = self._safe_float(self.pressure_vars["delta_t_c"].get())
        actual_pressure_change = self._safe_float(self.pressure_vars["actual_pressure_change_bar"].get())
        if (
            a_value is None
            or b_value is None
            or delta_t is None
            or actual_pressure_change is None
        ):
            lines.append("Degerlendirme hazir degil: sayisal girdiler tamamlanmadi.")
            return "\n".join(lines)

        try:
            inputs = PressureVariationInputs(
                pipe=pipe,
                a_micro_per_bar=a_value,
                b_micro_per_c=b_value,
                delta_t_c=delta_t,
                actual_pressure_change_bar=actual_pressure_change,
            )
            result = evaluate_pressure_variation_test(inputs)
        except ValidationError as exc:
            lines.append(f"Degerlendirme hazir degil: {exc}")
            return "\n".join(lines)

        deformation_term = pipe.elasticity_term + inputs.a_micro_per_bar
        lines.extend(
            [
                f"Boru elastisite terimi (0.884 x ri / s): {pipe.elasticity_term:.6f}",
                f"Toplam deformasyon terimi ((0.884 x ri / s) + A): {deformation_term:.6f}",
                f"Program hesabi Pt: {result.theoretical_pressure_change_bar:.6f} bar",
                f"Ust kabul siniri (Pt + 0.3): {result.allowable_upper_pressure_change_bar:.6f} bar",
                f"Kullanici girdisi Pa: {result.actual_pressure_change_bar:.6f} bar",
                f"Fark (Pa - Pt): {result.margin_bar:.6f} bar",
                f"Anlik sonuc: {'BASARILI' if result.passed else 'BASARISIZ'}",
            ]
        )
        return "\n".join(lines)

    def _build_pressure_control_table_summary(self) -> str:
        temp_c = self._safe_float(self.pressure_vars["temperature_c"].get())
        pressure_bar = self._safe_float(self.pressure_vars["pressure_bar"].get())
        if temp_c is None or pressure_bar is None:
            return self._default_control_table_text("pressure")
        current_a = self._safe_float(self.pressure_vars["a_micro_per_bar"].get())
        current_b = self._safe_float(self.pressure_vars["b_micro_per_c"].get())
        parts: list[str] = []
        try:
            point = lookup_botas_reference_point(temp_c=temp_c, pressure_bar=pressure_bar)
            internal = [f"{BOTAS_REFERENCE_TABLE_LABEL} A = {point.a_micro_per_bar:.6f}, B = {point.b_micro_per_c:.6f}."]
            if current_a is not None:
                internal.append(f"A farki = {self._format_control_table_delta(current_a, point.a_micro_per_bar)}.")
            if current_b is not None:
                internal.append(f"B farki = {self._format_control_table_delta(current_b, point.b_micro_per_c)}.")
            parts.append(" ".join(internal))
        except (ABControlTableError, FileNotFoundError, ValueError) as exc:
            parts.append(f"{BOTAS_REFERENCE_TABLE_LABEL} kullanilamadi ({exc}).")
        try:
            gail_point = lookup_gail_reference_point(temp_c=temp_c, pressure_bar=pressure_bar)
            gail = [
                f"{GAIL_REFERENCE_TABLE_LABEL} A = {gail_point.a_micro_per_bar:.6f}, "
                f"B = {gail_point.b_micro_per_c:.6f}."
            ]
            if current_a is not None:
                gail.append(
                    f"A farki = {self._format_control_table_delta(current_a, gail_point.a_micro_per_bar)}."
                )
            if current_b is not None:
                gail.append(
                    f"B farki = {self._format_control_table_delta(current_b, gail_point.b_micro_per_c)}."
                )
            parts.append(" ".join(gail))
        except (ABControlTableError, FileNotFoundError, ValueError) as exc:
            parts.append(f"{GAIL_REFERENCE_TABLE_LABEL} kullanilamadi ({exc}).")
        return " ".join(parts)

    def _build_pressure_backend_comparison(self) -> str:
        temp_c = self._read_float(
            self.pressure_vars["temperature_c"], "Su sicakligi", "pressure", "pressure.temperature_c"
        )
        pressure_bar = self._read_float(
            self.pressure_vars["pressure_bar"], "Su basinci", "pressure", "pressure.pressure_bar"
        )
        steel_alpha_text = self.b_helper_vars["steel_alpha_micro_per_c"].get().strip()
        steel_alpha = self._safe_float(steel_alpha_text)
        if steel_alpha is None and steel_alpha_text:
            self._set_feedback("pressure", "Celik alpha icin gecerli bir sayi girin.")
            self._set_field_message("helper.steel_alpha_micro_per_c", "Gecerli bir sayi girin.", "error")
            self._focus_field("helper.steel_alpha_micro_per_c")
            raise ValidationError("Celik alpha icin gecerli bir sayi girin.")
        b_enabled = steel_alpha is not None
        rows: list[dict[str, object]] = []
        for info in self.water_backend_infos:
            try:
                a_value = calculate_water_compressibility_a(
                    temp_c=temp_c,
                    pressure_bar=pressure_bar,
                    backend=info.key,
                )
                beta_value = calculate_water_thermal_expansion_beta(
                    temp_c=temp_c,
                    pressure_bar=pressure_bar,
                    backend=info.key,
                )
            except ValidationError as exc:
                rows.append(
                    {
                        "info": info,
                        "a_value": None,
                        "beta_value": None,
                        "b_value": None,
                        "error": str(exc),
                        "b_error": str(exc),
                    }
                )
                continue
            if b_enabled:
                try:
                    b_value = calculate_b_coefficient(beta_value, steel_alpha)
                    b_error = None
                except ValidationError as exc:
                    b_value = None
                    b_error = str(exc)
            else:
                b_value = None
                b_error = "Celik alpha verilmedigi icin B karsilastirmasi yapilmadi."
            rows.append(
                {
                    "info": info,
                    "a_value": a_value,
                    "beta_value": beta_value,
                    "b_value": b_value,
                    "error": None,
                    "b_error": b_error,
                }
            )
        selected_key = self._selected_water_backend_key()
        selected_row = next(row for row in rows if getattr(row["info"], "key", "") == selected_key)
        selected_info = selected_row["info"]
        selected_a = selected_row["a_value"]
        selected_beta = selected_row["beta_value"]
        selected_b = selected_row["b_value"]
        header = f"Basinc A/B karsilastirmasi @ {temp_c:.3f} degC / {pressure_bar:.3f} bar."
        if b_enabled:
            header += f" Celik alpha = {steel_alpha:.6f}."
        else:
            header += " Celik alpha verilmedigi icin yalnizca A ve beta karsilastirildi."
        parts = [header]
        if isinstance(selected_a, float) and isinstance(selected_beta, float):
            parts.append(
                f"Secili backend {selected_info.label}: A = {selected_a:.6f}, beta = {selected_beta:.6f}, B = {self._format_backend_b_value(selected_b, selected_row['b_error'])}."
            )
        else:
            parts.append(f"Secili backend {selected_info.label}: hesaplanamadi ({selected_row['error']}).")
        for row in rows:
            info = row["info"]
            if getattr(info, "key", "") == selected_key:
                continue
            a_value = row["a_value"]
            beta_value = row["beta_value"]
            if not isinstance(a_value, float) or not isinstance(beta_value, float):
                parts.append(f"{info.label}: hesaplanamadi ({row['error']}).")
                continue
            if isinstance(selected_a, float) and isinstance(selected_beta, float):
                a_delta = a_value - selected_a
                beta_delta = beta_value - selected_beta
                if isinstance(selected_b, float) and isinstance(row["b_value"], float):
                    b_delta = row["b_value"] - selected_b
                    b_fragment = f"{row['b_value']:.6f} | B farki = {b_delta:+.6f}"
                else:
                    b_fragment = self._format_backend_b_value(row["b_value"], row["b_error"])
                parts.append(
                    f"{info.label}: A = {a_value:.6f} | A farki = {a_delta:+.6f}; beta = {beta_value:.6f} | beta farki = {beta_delta:+.6f}; B = {b_fragment}."
                )
            else:
                parts.append(
                    f"{info.label}: A = {a_value:.6f}, beta = {beta_value:.6f}, B = {self._format_backend_b_value(row['b_value'], row['b_error'])}."
                )
        return " ".join(parts)

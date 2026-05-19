from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from ..app_metadata import (
    APP_NAME,
    APP_TITLE,
    APP_VERSION,
    RELEASES_PAGE_URL,
    SPEC_DOCUMENT_CODE,
    SPEC_DOCUMENT_TITLE,
)
from ..config import FIELD_CHECK_DEFINITIONS
from ..logging_config import install_exception_handler
from ..data.ab_control_table import (
    ABControlTableError,
    describe_ab_control_table_range,
    lookup_ab_control_point,
)
from ..data.botas_reference_table import (
    BOTAS_REFERENCE_OPTION_LABEL,
    BOTAS_REFERENCE_TABLE_LABEL,
    describe_botas_reference_table_range,
    is_botas_reference_option,
    lookup_botas_reference_point,
)
from ..data.gail_reference_table import (
    GAIL_REFERENCE_OPTION_LABEL,
    GAIL_REFERENCE_TABLE_LABEL,
    describe_gail_reference_table_range,
    is_gail_reference_option,
    lookup_gail_reference_point,
)
from ..data.segment_csv import ParsedSegment, parse_segment_csv
from ..domain import (
    evaluate_depressurization,
    evaluate_section_pressure_profile,
    get_available_water_property_backends,
    get_default_water_property_backend,
    get_location_class_options,
    get_location_class_rule,
    MAX_TEST_SECTION_LENGTH_M,
    MAX_TEST_SECTION_VOLUME_M3,
    get_pump_location_options,
    get_water_property_backend,
)
from ..domain.hydrotest_core import (
    SEAMLESS_PIPE_K,
    WELDED_PIPE_K,
    AirContentInputs,
    PipeGeometry,
    PipeSection,
    PressureVariationInputs,
    ValidationError,
    calculate_b_coefficient,
    calculate_water_compressibility_a,
    calculate_water_thermal_expansion_beta,
    evaluate_air_content_test,
    evaluate_pressure_variation_test,
)
from ..domain.pressure_profile import SectionPressureProfileInputs, SectionPressureProfileResult
from ..domain.depressurization import (
    DepressurizationStage,
    DepressurizationInputs,
)
from ..domain.operations import evaluate_pig_speed, get_pig_speed_limit, get_pig_speed_limit_options
from ..data.pipe_catalog import (
    find_api_5l_psl2_grade,
    find_pipe_size,
    find_schedule,
    get_api_5l_psl2_grade_options,
    get_pipe_size_options,
    get_schedule_options,
)
from ..services.updater import UpdateError, UpdateInfo, fetch_latest_update_info, install_update, open_release_page

DEFAULT_DECISION_TITLE = "Henuz degerlendirme yapilmadi"
DEFAULT_DECISION_STATUS = "BEKLIYOR"
DEFAULT_DECISION_SUMMARY = (
    "Girdileri tamamlayip ilgili testi calistirdiginizde nihai karar burada gosterilecek."
)
AUTO_A_MODE = "Otomatik"
TABLE_A_MODE = "Tablo"
REFERENCE_A_MODE = TABLE_A_MODE
MANUAL_A_MODE = "Manuel"
AUTO_B_MODE = "Otomatik"
TABLE_B_MODE = "Tablo"
REFERENCE_B_MODE = TABLE_B_MODE
MANUAL_B_MODE = "Manuel"


from .dialog_update import UpdateDialogMixin
from .panel_schema import PanelSchemaMixin
from .app_state import AppStateMixin
from .layout_builder import LayoutBuilderMixin
from .tab_air import AirTabMixin
from .tab_field import FieldTabMixin
from .tab_pressure import PressureTabMixin
from .tab_pressure_detail import PressureDetailMixin
from .widget_factory import WidgetFactoryMixin


class HydrostaticTestApp(FieldTabMixin, AirTabMixin, PressureDetailMixin, PressureTabMixin, UpdateDialogMixin, PanelSchemaMixin, WidgetFactoryMixin, AppStateMixin, LayoutBuilderMixin):
    FIELD_CHECK_DEFINITIONS = FIELD_CHECK_DEFINITIONS
    AUTO_A_MODE = AUTO_A_MODE
    TABLE_A_MODE = TABLE_A_MODE
    REFERENCE_A_MODE = TABLE_A_MODE
    MANUAL_A_MODE = MANUAL_A_MODE
    AUTO_B_MODE = AUTO_B_MODE
    TABLE_B_MODE = TABLE_B_MODE
    REFERENCE_B_MODE = TABLE_B_MODE
    MANUAL_B_MODE = MANUAL_B_MODE




    def _default_update_download_dir(self) -> Path:
        downloads_dir = Path.home() / "Downloads" / "HidrostatikTestUpdates"
        return downloads_dir


    def _resolve_update_download_dir(self, create: bool = False) -> Path:
        target_dir = Path(self.update_download_dir_var.get()).expanduser()
        if create:
            target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir

    def _choose_update_download_dir(self) -> bool:
        selected_dir = filedialog.askdirectory(
            title="Guncelleme Paketinin Indirilecegi Klasor",
            initialdir=str(self._resolve_update_download_dir(create=True)),
            mustexist=False,
        )
        if not selected_dir:
            return False
        self.update_download_dir_var.set(selected_dir)
        self._refresh_update_download_summary()
        self._set_banner(f"Guncelleme indirme klasoru secildi: {selected_dir}", "info")
        return True

    def _refresh_update_download_summary(self) -> None:
        target_dir = self._resolve_update_download_dir(create=False)
        self.update_download_summary_var.set(
            f"Guncelleme indirilecek klasor: {target_dir}"
        )






















    def _mark_dependencies_changed(self, keys: tuple[str, ...]) -> None:
        for key in keys:
            if self.coefficient_states[key] in {"computed", "reference"}:
                self.coefficient_states[key] = "stale"
        self._refresh_coefficient_statuses()
        self._update_workflow_hint()

    def _refresh_live_coefficients(self) -> None:
        air_ready = (
            self._safe_float(self.air_vars["temperature_c"].get()) is not None
            and self._safe_float(self.air_vars["pressure_bar"].get()) is not None
        )
        pressure_ready = (
            self._safe_float(self.pressure_vars["temperature_c"].get()) is not None
            and self._safe_float(self.pressure_vars["pressure_bar"].get()) is not None
        )
        if air_ready:
            if self._air_a_is_auto():
                self._calculate_air_a(log_result=False, silent=True)
            elif self._air_a_is_reference() and self.air_a_reference_var.get().strip():
                self._apply_air_a_reference(log_result=False, silent=True)
        if pressure_ready:
            if self._pressure_a_is_auto():
                self._calculate_pressure_a(log_result=False, silent=True)
            elif self._pressure_a_is_reference() and self.pressure_a_reference_var.get().strip():
                self._apply_pressure_a_reference(log_result=False, silent=True)
            if self._pressure_b_is_auto():
                if self._safe_float(self.b_helper_vars["steel_alpha_micro_per_c"].get()) is not None:
                    self._calculate_b_helper(log_result=False, silent=True)
            elif self._pressure_b_is_reference() and self.pressure_b_reference_var.get().strip():
                self._apply_pressure_b_reference(log_result=False, silent=True)
        self._update_live_notice()

    def _check_ambient_temp_constraint(self) -> None:
        ambient = self._safe_float(self.ambient_temp_var.get())
        if ambient is None:
            return True
        if ambient < 2.0:
            self.banner_var.set(
                f"UYARI: Ortam sicakligi {ambient:.1f} degC < +2 degC. "
                "Sartname Madde 10.1 geregi dolum yapilamaz. Daha sicak bir gun beklenmelidir."
            )
            self.banner_label.configure(bg="#FDEAEA", fg="#A4262C")
            if self.control_check_vars.get("ambient_temp"):
                self.control_check_vars["ambient_temp"].set(False)
            return False
        elif ambient < 5.0:
            self.banner_var.set(
                f"Dikkat: Ortam sicakligi {ambient:.1f} degC, +2 degC limitine yakin. "
                "Sicaklik takibi onerilir."
            )
            self.banner_label.configure(bg="#FFF6E5", fg="#8A5B00")
        else:
            self.banner_label.configure(bg="#EEF4FF", fg="#16365D")
        return True

    def _refresh_live_test_decision(self) -> None:
        if not self._check_ambient_temp_constraint():
            self._update_decision_card(
                "Ortam Sicakligi Kisiti",
                "BEKLIYOR",
                "Ortam sicakligi +2 degC altinda. Sartname Madde 10.1 geregi dolum yapilamaz. Test degerlendirilemez.",
            )
            return
        self._evaluate_pv_limit()
        active_tab = self._active_tab_key()
        if active_tab == "air":
            self._refresh_live_air_decision()
        elif active_tab == "pressure":
            self._refresh_live_pressure_decision()

    def _refresh_live_air_decision(self) -> None:
        if not self._ensure_live_air_inputs_ready():
            self._update_decision_card(
                "Hava Icerik Testi",
                "BEKLIYOR",
                "Canli degerlendirme icin geometri, A, P, K ve Vpa tamamlanmali.",
            )
            return
        try:
            pipe = self._detail_pipe_snapshot()[0]
            assert pipe is not None
            result = evaluate_air_content_test(
                AirContentInputs(
                    pipe=pipe,
                    a_micro_per_bar=float(self.air_vars["a_micro_per_bar"].get().strip().replace(",", ".")),
                    pressure_rise_bar=float(self.air_vars["pressure_rise_bar"].get().strip().replace(",", ".")),
                    k_factor=float(self.air_vars["k_factor"].get().strip().replace(",", ".")),
                    actual_added_water_m3=float(self.air_vars["actual_added_water_m3"].get().strip().replace(",", ".")),
                )
            )
        except (AssertionError, ValidationError, ValueError):
            self._update_decision_card(
                "Hava Icerik Testi",
                "DOGRULANAMADI",
                "Canli degerlendirme icin girilen degerlerden biri henuz gecerli degil.",
            )
            return
        status = "BASARILI" if result.passed else "BASARISIZ"
        self._update_decision_card(
            "Hava Icerik Testi",
            status,
            (
                f"Canli sonuc: Vp = {result.theoretical_added_water_m3:.6f} m3, "
                f"limit = {result.acceptance_limit_m3:.6f} m3, "
                f"Vpa = {result.actual_added_water_m3:.6f} m3, oran = {result.ratio:.6f}"
                f"\nKabul kriteri: Vpa <= 1.06 x Vp"
            ),
        )
        self._evaluation_fresh["air"] = True
        self.schema_status_var.set("HESAPLANDI")
        self._refresh_visual_schema()


    def _ensure_live_air_inputs_ready(self) -> bool:
        pipe, pipe_error = self._detail_pipe_snapshot()
        if pipe_error is not None or pipe is None:
            return False
        required_values = (
            self._safe_float(self.air_vars["a_micro_per_bar"].get()),
            self._safe_float(self.air_vars["pressure_rise_bar"].get()),
            self._safe_float(self.air_vars["k_factor"].get()),
            self._safe_float(self.air_vars["actual_added_water_m3"].get()),
        )
        return all(value is not None for value in required_values)


    def _evaluate_pv_limit(self) -> None:
        p_rise = self._safe_float(self.pv_vars["total_pressure_rise_bar"].get())
        v_added = self._safe_float(self.pv_vars["total_water_added_m3"].get())
        a_val = self._safe_float(self.air_vars["a_micro_per_bar"].get())
        k_val = self._safe_float(self.air_vars["k_factor"].get())
        if p_rise is None or v_added is None or a_val is None or k_val is None:
            return
        pipe, pipe_error = self._detail_pipe_snapshot()
        if pipe_error is not None or pipe is None:
            return
        try:
            from ..domain.hydrotest_core import PressureVolumeInputs, evaluate_pressure_volume_limit
            result = evaluate_pressure_volume_limit(
                PressureVolumeInputs(
                    pipe=pipe,
                    a_micro_per_bar=a_val,
                    total_pressure_rise_bar=p_rise,
                    k_factor=k_val,
                    actual_total_water_added_m3=v_added,
                )
            )
        except (ValidationError, ValueError) as exc:
            self.pv_result_var.set(f"Basinc-hacim degerlendirme hatasi: {exc}")
            return
        percentage = result.excess_ratio * 100
        if result.within_limit:
            self.pv_result_var.set(
                f"%0.2 esigi kontrolu BASARILI: teorik = {result.theoretical_water_m3:.6f} m3, "
                f"fiili = {result.actual_water_m3:.6f} m3, "
                f"sapma = {percentage:+.4f}% (limit: %0.2)"
            )
        else:
            self.pv_result_var.set(
                f"%0.2 esigi ASIM: teorik = {result.theoretical_water_m3:.6f} m3, "
                f"fiili = {result.actual_water_m3:.6f} m3, "
                f"sapma = {percentage:+.4f}% > %0.2. "
                f"Sartname Madde 14.2'ye gore ilave su miktari limiti asmistir."
            )

    def _safe_float(self, value: str) -> float | None:
        normalized = value.strip().replace(",", ".")
        if not normalized:
            return None
        try:
            return float(normalized)
        except ValueError:
            return None

    def _set_field_message(self, field_key: str, message: str, level: str = "info") -> None:
        var = self.field_message_vars.get(field_key)
        if var is None:
            return
        prefixes = {
            "info": "",
            "success": "Hazir: ",
            "warning": "Uyari: ",
            "error": "Hata: ",
        }
        var.set(f"{prefixes.get(level, '')}{message}" if message else "")
        visual_level = "neutral" if level == "info" else level
        self._apply_field_visual_state(field_key, visual_level)

    def _clear_field_message(self, field_key: str) -> None:
        var = self.field_message_vars.get(field_key)
        if var is not None:
            var.set("")
        self._apply_field_visual_state(field_key, "neutral")

    def _auto_field_hint(self, field_key: str) -> str:
        backend_label = self._selected_water_backend_info().label
        if field_key == "air.a_micro_per_bar":
            if self._air_a_is_auto():
                return f"Otomatik modda A, secili backend ({backend_label}) ile hesaplanir."
            if self._air_a_is_reference():
                return "Tablo modda BOTAS veya GAIL referans tablosunu secerek A degerini yukleyin."
            return "Manuel modda tablo/prosedurden A degerini girin."
        if field_key == "pressure.a_micro_per_bar":
            if self._pressure_a_is_auto():
                return f"Otomatik modda A, secili backend ({backend_label}) ile hesaplanir."
            if self._pressure_a_is_reference():
                return "Tablo modda BOTAS veya GAIL referans tablosunu secerek A degerini yukleyin."
            return "Manuel modda tablo/prosedurden A degerini girin."
        if field_key == "pressure.b_micro_per_c":
            if self.use_b_helper_var.get():
                if self._pressure_b_is_reference():
                    return "Tablo modda B degeri secilen BOTAS veya GAIL referans tablosundan dogrudan yuklenir."
                return f"Otomatik modda B, secili backend ({backend_label}) ile su beta ve celik alpha kullanarak hesaplanir."
            return "Manuel modda tablo/prosedurden B degerini girin."
        if field_key == "air.pressure_rise_bar":
            return "Sartnameye gore bu alan 1.0 bar olmalidir."
        if field_key == "pressure.delta_t_c":
            return "dT degeri Tilk - Tson olarak girilir."
        if field_key == "pressure.actual_pressure_change_bar":
            return "Pa degeri Pilk - Pson olarak girilir."
        if field_key == "helper.steel_alpha_micro_per_c" and self.use_b_helper_var.get():
            if self._pressure_b_is_reference():
                return "Tablo modda B dogrudan referans tablodan alindigi icin celik alpha kullanilmaz."
            return "Otomatik B icin celik alpha preset secin veya ozel deger girin."
        if field_key == "helper.water_beta_micro_per_c" and self.use_b_helper_var.get():
            if self._pressure_b_is_reference():
                return "Tablo modda su beta alani kullanilmaz; B dogrudan referans tablodan gelir."
            return f"B hesaplandiginda {backend_label} backend'inden gelen su beta burada gosterilir."
        if field_key == "geometry.highest_elevation_m":
            return "Test bolumundeki en yuksek kot noktasini metre cinsinden girin."
        if field_key == "geometry.lowest_elevation_m":
            return "Test bolumundeki en dusuk kot noktasini metre cinsinden girin."
        if field_key == "geometry.start_elevation_m":
            return "Pompa baslangictaysa izlenen basinc bu kotta okunur."
        if field_key == "geometry.end_elevation_m":
            return "Pompa bitisteyse izlenen basinc bu kotta okunur."
        if field_key == "geometry.design_pressure_bar":
            return "Minimum test basinci, dizayn basincinin Class 1-2 icin 1.25, Class 3-4 icin 1.50 katidir."
        if field_key == "geometry.smys_mpa":
            return "SMYS, secilen API 5L PSL2 boru kalitesinden otomatik alinir."
        if field_key == "field.pig_distance_m":
            return "Pig ilerledigi toplam mesafeyi metre cinsinden girin."
        if field_key == "field.pig_travel_time_min":
            return "Pigin bu mesafeyi kac dakikada gittigini girin."
        if field_key == "field.pig_speed_m_per_s":
            return "Hesap sonrasi burada m/sn cinsinden gosterilir."
        if field_key == "field.pig_speed_km_per_h":
            return "Hesap sonrasi burada km/sa cinsinden gosterilir."
        return ""

    def _update_live_notice(self) -> None:
        invalid_count = 0
        warning_count = 0
        stale_coefficients = [
            key
            for key, value in self.coefficient_states.items()
            if value == "stale" and key in self._relevant_coefficient_keys()
        ]
        for field_key in self._relevant_field_keys():
            meta = self.field_meta[field_key]
            if meta.get("readonly"):
                continue
            value = self._field_raw_value(field_key)
            normalized = value.strip().replace(",", ".")
            if meta.get("value_type") == "choice":
                semantic = self._semantic_field_feedback(field_key)
                if semantic is not None:
                    _message, level = semantic
                    if level == "error":
                        invalid_count += 1
                    elif level == "warning":
                        warning_count += 1
            elif meta.get("value_type") == "numeric" and normalized and self._safe_float(value) is None:
                invalid_count += 1
            elif normalized:
                semantic = self._semantic_field_feedback(field_key)
                if semantic is not None:
                    _message, level = semantic
                    if level == "error":
                        invalid_count += 1
                    elif level == "warning":
                        warning_count += 1
            elif field_key in self.touched_fields and meta.get("required") and not normalized:
                warning_count += 1
        if invalid_count:
            self.live_notice_var.set(
                f"Canli kontrol: {invalid_count} alan sayisal olarak gecersiz. Devam etmeden duzeltin."
            )
        elif stale_coefficients:
            self.live_notice_var.set(
                f"Canli kontrol: {len(stale_coefficients)} katsayi guncellenmeli. Yeniden hesaplama onerilir."
            )
        elif warning_count:
            self.live_notice_var.set(
                f"Canli kontrol: {warning_count} zorunlu alan henuz tamamlanmadi."
            )
        else:
            self.live_notice_var.set("Canli kontrol: aktif gorunen girdiler tutarli gorunuyor.")

    def _field_raw_value(self, field_key: str) -> str:
        prefix, name = field_key.split(".", 1)
        if prefix == "geometry":
            if name in self.geometry_vars:
                return self.geometry_vars[name].get()
            if name in self.section_profile_vars:
                return self.section_profile_vars[name].get()
            if name == "material_grade":
                return self.material_grade_var.get()
            if name == "location_class":
                return self.location_class_var.get()
            if name == "pump_location":
                return self.pump_location_var.get()
        if prefix == "air":
            if name in self.air_vars:
                return self.air_vars[name].get()
            if name == "a_reference_table":
                return self.air_a_reference_var.get()
        if prefix == "pressure":
            if name in self.pressure_vars:
                return self.pressure_vars[name].get()
            if name == "a_reference_table":
                return self.pressure_a_reference_var.get()
            if name == "b_reference_table":
                return self.pressure_b_reference_var.get()
        if prefix == "field":
            return self.field_vars[name].get()
        if prefix == "helper":
            return self.b_helper_vars[name].get()
        return ""

    def _semantic_field_feedback(self, field_key: str) -> tuple[str, str] | None:
        value = self._field_raw_value(field_key).strip()
        numeric_value = self._safe_float(value)

        if field_key == "geometry.outside_diameter_mm" and numeric_value is not None:
            if numeric_value <= 0:
                return ("Dis cap sifirdan buyuk olmalidir.", "error")
            wall = self._safe_float(self.geometry_vars["wall_thickness_mm"].get())
            if wall is not None and (wall * 2) >= numeric_value:
                return ("Et kalinligi mevcut dis cap ile ic capi sifira dusuruyor.", "error")
        if field_key == "geometry.wall_thickness_mm" and numeric_value is not None:
            if numeric_value <= 0:
                return ("Et kalinligi sifirdan buyuk olmalidir.", "error")
            outside = self._safe_float(self.geometry_vars["outside_diameter_mm"].get())
            if outside is not None and (numeric_value * 2) >= outside:
                return ("Et kalinligi dis capin yarisindan kucuk olmalidir.", "error")
        if field_key == "geometry.length_m" and numeric_value is not None:
            if numeric_value <= 0:
                return ("Hat uzunlugu sifirdan buyuk olmalidir.", "error")
            if numeric_value > MAX_TEST_SECTION_LENGTH_M:
                return ("Tek kesit uzunlugu 5007 limitine gore 20 km ustunde.", "warning")
        if field_key in {"geometry.highest_elevation_m", "geometry.lowest_elevation_m"} and numeric_value is not None:
            highest = self._safe_float(self.section_profile_vars["highest_elevation_m"].get())
            lowest = self._safe_float(self.section_profile_vars["lowest_elevation_m"].get())
            if highest is not None and lowest is not None and highest < lowest:
                return ("En yuksek nokta kotu, en dusuk noktadan kucuk olamaz.", "error")
        if field_key in {"geometry.start_elevation_m", "geometry.end_elevation_m"} and numeric_value is not None:
            highest = self._safe_float(self.section_profile_vars["highest_elevation_m"].get())
            lowest = self._safe_float(self.section_profile_vars["lowest_elevation_m"].get())
            if highest is not None and lowest is not None and (numeric_value < lowest or numeric_value > highest):
                return ("Bu kot degeri min-max kot araliginda olmalidir.", "error")
        if field_key == "geometry.design_pressure_bar" and numeric_value is not None and numeric_value <= 0:
            return ("Dizayn basinci sifirdan buyuk olmalidir.", "error")
        if field_key == "geometry.smys_mpa" and numeric_value is not None and numeric_value <= 0:
            return ("SMYS sifirdan buyuk olmalidir.", "error")
        if field_key == "air.pressure_rise_bar" and numeric_value is not None:
            if numeric_value <= 0:
                return ("Basinc artisi sifirdan buyuk olmalidir.", "error")
            if abs(numeric_value - 1.0) > 1e-9:
                return ("5007'ye gore hava icerik testi icin P tam 1.0 bar olmalidir.", "warning")
        if field_key == "air.k_factor" and numeric_value is not None and numeric_value <= 0:
            return ("K faktoru sifirdan buyuk olmalidir.", "error")
        if field_key == "air.actual_added_water_m3" and numeric_value is not None and numeric_value < 0:
            return ("Fiili ilave su negatif olamaz.", "error")
        if field_key in {"air.temperature_c", "pressure.temperature_c"} and numeric_value is not None:
            if numeric_value < -5 or numeric_value > 60:
                return ("Girilmis sicaklik tipik saha araliginin disinda gorunuyor.", "warning")
        if field_key in {"air.pressure_bar", "pressure.pressure_bar"} and numeric_value is not None and numeric_value <= 0:
            return ("Su basinci sifirdan buyuk olmalidir.", "error")
        if field_key == "pressure.actual_pressure_change_bar" and numeric_value is not None and numeric_value < 0:
            return ("Pa = Pilk - Pson negatif olmamalidir.", "warning")
        if field_key == "helper.steel_alpha_micro_per_c" and numeric_value is not None and numeric_value <= 0:
            return ("Celik alpha sifirdan buyuk olmalidir.", "error")
        if field_key == "field.pig_distance_m" and numeric_value is not None and numeric_value <= 0:
            return ("Pig mesafesi sifirdan buyuk olmalidir.", "error")
        if field_key == "field.pig_travel_time_min" and numeric_value is not None and numeric_value <= 0:
            return ("Pig suresi sifirdan buyuk olmalidir.", "error")
        if field_key == "geometry.material_grade" and not value:
            if any(var.get().strip() for var in self.section_profile_vars.values()):
                return ("API 5L PSL2 malzeme kalitesi secin.", "warning")
            return None
        if field_key == "geometry.pump_location" and not value:
            if any(var.get().strip() for var in self.section_profile_vars.values()):
                return ("Pompa konumu secilmeden pencere tamamlanmaz.", "warning")
            return None
        if field_key == "air.a_reference_table" and self._air_a_is_reference() and not value:
            return ("Tablo modda A icin referans tablo secin.", "warning")
        if field_key == "pressure.a_reference_table" and self._pressure_a_is_reference() and not value:
            return ("Tablo modda A icin referans tablo secin.", "warning")
        if field_key == "pressure.b_reference_table" and self._pressure_b_is_reference() and not value:
            return ("Tablo modda B icin referans tablo secin.", "warning")
        return None

    def _on_live_field_change(self, field_key: str, variable: tk.StringVar) -> None:
        self.touched_fields.add(field_key)
        active_tab = self._active_tab_key()
        if self._evaluation_fresh.get(active_tab):
            self._evaluation_fresh[active_tab] = False
            self.schema_status_var.set("DEGISTI")
            self._refresh_visual_schema()
        meta = self.field_meta.get(field_key)
        if meta is None:
            return
        normalized = variable.get().strip().replace(",", ".")
        if not normalized:
            hint = self._auto_field_hint(field_key)
            if hint:
                self._set_field_message(field_key, hint, "info")
            elif meta.get("required"):
                self._set_field_message(field_key, "Bu alan gerekli.", "warning")
            else:
                self._clear_field_message(field_key)
            self._refresh_control_table_summaries()
            self._update_live_notice()
            self._refresh_visual_schema()
            self._refresh_live_coefficients()
            self._refresh_live_test_decision()
            self._update_action_button_states()
            return
        if self._safe_float(variable.get()) is None:
            self._set_field_message(field_key, "Gecerli bir sayi girin.", "error")
            self._refresh_control_table_summaries()
            self._update_live_notice()
            self._refresh_visual_schema()
            self._refresh_live_test_decision()
            self._update_action_button_states()
            return
        if field_key == "pressure.b_micro_per_c" and self.use_b_helper_var.get():
            self._set_field_message(field_key, "Helper modu bu degeri yonetiyor.", "info")
            self._refresh_control_table_summaries()
            self._update_live_notice()
            self._refresh_visual_schema()
            self._refresh_live_coefficients()
            self._refresh_live_test_decision()
            self._update_action_button_states()
            return
        semantic_feedback = self._semantic_field_feedback(field_key)
        if semantic_feedback is not None:
            message, level = semantic_feedback
            self._set_field_message(field_key, message, level)
        else:
            self._clear_field_message(field_key)
        self._refresh_control_table_summaries()
        self._refresh_choice_validation_states()
        self._update_live_notice()
        self._refresh_visual_schema()
        self._refresh_live_coefficients()
        self._refresh_live_test_decision()
        self._update_action_button_states()

    def _are_active_test_inputs_ready(self) -> bool:
        active_tab = self._active_tab_key()
        if active_tab == "air":
            return self._ensure_live_air_inputs_ready()
        elif active_tab == "pressure":
            return self._ensure_live_pressure_inputs_ready()
        return True

    def _update_action_button_states(self) -> None:
        inputs_ready = self._are_active_test_inputs_ready()
        state = "normal" if inputs_ready else "disabled"
        for attr_name in ("air_a_calculate_button", "air_test_button",
                          "pressure_a_calculate_button", "b_helper_calculate_button",
                          "pressure_test_button", "pig_calculate_button",
                          "run_selected_button", "recalculate_button"):
            if hasattr(self, attr_name):
                widget = getattr(self, attr_name)
                if hasattr(widget, "configure"):
                    try:
                        widget.configure(state=state)
                    except tk.TclError:
                        pass

    def _refresh_choice_validation_states(self) -> None:
        for field_key in (
            "geometry.material_grade",
            "geometry.location_class",
            "geometry.pump_location",
            "air.a_reference_table",
            "pressure.a_reference_table",
            "pressure.b_reference_table",
        ):
            if field_key not in self.input_widgets:
                continue
            feedback = self._semantic_field_feedback(field_key)
            if feedback is None:
                value = self._field_raw_value(field_key).strip()
                if value:
                    self._apply_field_visual_state(field_key, "success")
                else:
                    self._apply_field_visual_state(field_key, "neutral")
            else:
                _message, level = feedback
                self._apply_field_visual_state(field_key, level)

    def _selected_material_grade(self) -> dict | None:
        return find_api_5l_psl2_grade(self.material_grade_var.get().strip())

    def _on_material_grade_changed(self) -> None:
        grade = self._selected_material_grade()
        if grade is None:
            self.section_profile_vars["smys_mpa"].set("")
        else:
            self.section_profile_vars["smys_mpa"].set(f"{float(grade['smys_mpa']):.0f}")
        self._refresh_geometry_summary()
        self._refresh_live_test_decision()

    def _refresh_geometry_summary(self) -> None:
        if self.geometry_segments:
            try:
                geometry = PipeGeometry(
                    sections=tuple(segment_info["pipe"] for segment_info in self.geometry_segments)  # type: ignore[arg-type]
                )
            except ValidationError as exc:
                self.geometry_summary_var.set(f"Segment ozeti hazir degil: {exc}")
                self._refresh_visual_schema()
                self._refresh_detail_reports()
                self._refresh_live_test_decision()
                return
            self.geometry_summary_var.set(
                "Segmentli geometri aktif. Esdeger ic yaricap = "
                f"{geometry.internal_radius_mm:.3f} mm, toplam ic hacim Vt = {geometry.internal_volume_m3:.6f} m3, "
                f"toplam uzunluk = {geometry.total_length_m:.3f} m"
            )
            self._refresh_section_pressure_overview()
            self._refresh_visual_schema()
            self._refresh_detail_reports()
            self._refresh_live_test_decision()
            return
        outside = self._safe_float(self.geometry_vars["outside_diameter_mm"].get())
        wall = self._safe_float(self.geometry_vars["wall_thickness_mm"].get())
        length = self._safe_float(self.geometry_vars["length_m"].get())
        if outside is None or wall is None or length is None:
            self.geometry_summary_var.set(
                "Geometri girildiginde ic cap, ic yaricap ve hacim ozeti burada gosterilir."
            )
            self._refresh_section_pressure_overview()
            self._refresh_visual_schema()
            self._refresh_detail_reports()
            self._refresh_live_test_decision()
            return
        try:
            pipe = PipeSection(
                outside_diameter_mm=outside,
                wall_thickness_mm=wall,
                length_m=length,
            )
        except ValidationError as exc:
            self.geometry_summary_var.set(f"Geometri ozeti hazir degil: {exc}")
            self._refresh_section_pressure_overview()
            self._refresh_visual_schema()
            self._refresh_detail_reports()
            self._refresh_live_test_decision()
            return
        internal_diameter_mm = pipe.internal_radius_mm * 2
        self.geometry_summary_var.set(
            "Ic cap = "
            f"{internal_diameter_mm:.3f} mm, ic yaricap = {pipe.internal_radius_mm:.3f} mm, "
            f"ic hacim Vt = {pipe.internal_volume_m3:.6f} m3"
        )
        self._refresh_section_pressure_overview()
        self._refresh_visual_schema()
        self._refresh_detail_reports()
        self._refresh_live_test_decision()

    def _on_coefficient_field_changed(self, key: str, variable: tk.StringVar) -> None:
        if key in self._programmatic_coefficient_updates:
            return
        self.coefficient_states[key] = "manual" if variable.get().strip() else "empty"
        self._refresh_coefficient_statuses()
        self._update_workflow_hint()

    def _refresh_coefficient_statuses(self) -> None:
        self.coefficient_status_vars["air_a"].set(self._coefficient_status_text("air_a"))
        self.coefficient_status_vars["pressure_a"].set(self._coefficient_status_text("pressure_a"))
        self.coefficient_status_vars["pressure_b"].set(self._coefficient_status_text("pressure_b"))
        self._refresh_coefficient_source_badges()
        self._sync_coefficient_field_messages()
        self._update_workflow_hint()
        self._refresh_visual_schema()
        self._refresh_detail_reports()

    def _coefficient_status_text(self, key: str) -> str:
        state = self.coefficient_states[key]
        if state == "computed":
            return "Hazir: otomatik hesap"
        if state == "reference":
            return "Hazir: tablo referansi"
        if state == "stale":
            return "Guncellenmeli: secenek veya kosullar degisti"
        if state == "manual":
            return "Hazir: manuel giris"
        return "Bekleniyor"

    def _coefficient_source_text(self, key: str) -> str:
        state = self.coefficient_states[key]
        if state == "computed":
            return "HESAP"
        if state == "reference":
            return "REFERANS"
        if state == "manual":
            return "MANUEL"
        if state == "stale":
            return "YENILE"
        return "BEKLIYOR"

    def _refresh_coefficient_source_badges(self) -> None:
        palette = {
            "computed": ("#EAF7EA", "#1D5F2F"),
            "reference": ("#EAF2FF", "#1E4E8C"),
            "manual": ("#FFF6E5", "#8A5B00"),
            "stale": ("#FDEAEA", "#8B1E1E"),
            "empty": ("#EEF2FF", "#243B73"),
        }
        all_badges = (self.coefficient_source_badges, self.inline_coefficient_source_badges)
        for key, variable in self.coefficient_source_vars.items():
            state = self.coefficient_states.get(key, "empty")
            variable.set(self._coefficient_source_text(key))
            bg, fg = palette.get(state, palette["empty"])
            for badge_registry in all_badges:
                badge = badge_registry.get(key)
                if badge is not None:
                    badge.configure(bg=bg, fg=fg)

    def _sync_coefficient_field_messages(self) -> None:
        mapping = {
            "air_a": "air.a_micro_per_bar",
            "pressure_a": "pressure.a_micro_per_bar",
            "pressure_b": "pressure.b_micro_per_c",
        }
        for coefficient_key, field_key in mapping.items():
            state = self.coefficient_states[coefficient_key]
            existing_message = self.field_message_vars.get(field_key)
            if state == "stale":
                self._set_field_message(field_key, "Kosullar degisti, yeniden hesaplayin.", "warning")
            elif state == "computed":
                self._set_field_message(field_key, "Hesap guncel.", "success")
            elif state == "reference":
                self._set_field_message(field_key, "Referans noktadan yuklendi.", "success")
            elif state == "manual":
                self._set_field_message(field_key, "Manuel giris aktif.", "info")
            elif existing_message is not None and not existing_message.get():
                hint = self._auto_field_hint(field_key)
                if hint:
                    self._set_field_message(field_key, hint, "info")

    def _set_feedback(self, section: str, message: str) -> None:
        self.section_feedback_vars[section].set(message)
        self._update_live_notice()

    def _clear_feedback(self, section: str) -> None:
        self.section_feedback_vars[section].set("")
        for field_key, meta in self.field_meta.items():
            if meta.get("section") == section:
                if field_key in {"air.a_micro_per_bar", "pressure.a_micro_per_bar", "pressure.b_micro_per_c"}:
                    continue
                hint = self._auto_field_hint(field_key)
                if hint:
                    self._set_field_message(field_key, hint, "info")
                else:
                    self._clear_field_message(field_key)
        self._update_live_notice()

    def _clear_all_feedback(self) -> None:
        for key in self.section_feedback_vars:
            self.section_feedback_vars[key].set("")
        self._update_live_notice()

    def _set_banner(self, message: str, level: str = "info") -> None:
        colors = {
            "info": ("#EEF4FF", "#16365D"),
            "success": ("#EAF7EA", "#1D5F2F"),
            "warning": ("#FFF6E5", "#8A5B00"),
            "error": ("#FDEAEA", "#8B1E1E"),
        }
        bg, fg = colors.get(level, colors["info"])
        self.banner_var.set(message)
        self.banner_label.configure(bg=bg, fg=fg)

    def _active_tab_key(self) -> str:
        if not hasattr(self, "notebook"):
            return "air"
        current_text = self.notebook.tab(self.notebook.select(), "text")
        if "Saha" in current_text:
            return "field"
        return "pressure" if "Basinc" in current_text else "air"

    def _relevant_field_keys(self) -> set[str]:
        active_tab = self._active_tab_key()
        relevant_fields: set[str] = set()
        for field_key, meta in self.field_meta.items():
            section = meta.get("section")
            if active_tab == "field":
                if section != "field":
                    continue
            else:
                if self.geometry_segments and section == "geometry":
                    continue
                if section not in {"geometry", active_tab}:
                    continue
            if field_key.startswith("helper.") and not self.use_b_helper_var.get():
                continue
            relevant_fields.add(field_key)
        return relevant_fields

    def _relevant_coefficient_keys(self) -> tuple[str, ...]:
        if self._active_tab_key() == "air":
            return ("air_a",)
        if self._active_tab_key() == "field":
            return ()
        return ("pressure_a", "pressure_b")

    def _remove_touched_fields(self, section: str) -> None:
        for field_key, meta in self.field_meta.items():
            if meta.get("section") == section:
                self.touched_fields.discard(field_key)

    def _reset_decision_card(self) -> None:
        self._update_decision_card(
            DEFAULT_DECISION_TITLE,
            DEFAULT_DECISION_STATUS,
            DEFAULT_DECISION_SUMMARY,
        )

    def _default_k_factor(self) -> str:
        selected = self.k_preset_var.get()
        if "1.02" in selected:
            return f"{WELDED_PIPE_K:.2f}"
        if "1.00" in selected:
            return f"{SEAMLESS_PIPE_K:.2f}"
        return ""

    def _default_steel_alpha(self) -> str:
        selected = self.steel_preset_var.get()
        if "12.0" in selected:
            return "12.0"
        if "12.5" in selected:
            return "12.5"
        if "16.0" in selected:
            return "16.0"
        return ""

    def _format_backend_option_label(self, info: object) -> str:
        label = getattr(info, "label", "")
        key = getattr(info, "key", "")
        return f"{label} [{key}]"





    def _default_water_backend_option_label(self) -> str:
        return self._format_backend_option_label(get_default_water_property_backend().info)

    def _selected_water_backend_key(self) -> str:
        selected_label = self.water_backend_var.get().strip()
        backend_key = self.water_backend_option_map.get(selected_label)
        if backend_key is not None:
            return backend_key
        default_label = self._default_water_backend_option_label()
        if selected_label != default_label:
            self.water_backend_var.set(default_label)
        return self.water_backend_option_map[default_label]

    def _selected_water_backend_info(self) -> object:
        return get_water_property_backend(self._selected_water_backend_key()).info

    def _default_backend_comparison_text(self, section: str) -> str:
        if section == "air":
            return "Hava testi icin backend karsilastirmasi henuz yapilmadi."
        if section == "pressure":
            return "Basinc testi icin backend karsilastirmasi henuz yapilmadi."
        return "Bu sekmede backend karsilastirmasi kullanilmaz."

    def _default_control_table_text(self, section: str) -> str:
        if section == "air":
            return (
                f"{BOTAS_REFERENCE_TABLE_LABEL} ve {GAIL_REFERENCE_TABLE_LABEL} henuz kullanilmadi. "
                f"{BOTAS_REFERENCE_TABLE_LABEL} aralik: {self.botas_reference_range_text}. "
                f"{GAIL_REFERENCE_TABLE_LABEL} aralik: {self.gail_reference_range_text}."
            )
        if section == "pressure":
            return (
                f"Basinc testi icin {BOTAS_REFERENCE_TABLE_LABEL} ve {GAIL_REFERENCE_TABLE_LABEL} henuz kullanilmadi. "
                f"{BOTAS_REFERENCE_TABLE_LABEL} aralik: {self.botas_reference_range_text}. "
                f"{GAIL_REFERENCE_TABLE_LABEL} aralik: {self.gail_reference_range_text}."
            )
        return "Bu sekmede A/B kontrol tablosu kullanilmaz."

    def _is_botas_reference_selection(self, label: str) -> bool:
        return is_botas_reference_option(label)

    def _is_gail_reference_selection(self, label: str) -> bool:
        return is_gail_reference_option(label)

    def _lookup_botas_reference_for_section(self, section: str):
        if section == "air":
            temp_c = self._safe_float(self.air_vars["temperature_c"].get())
            pressure_bar = self._safe_float(self.air_vars["pressure_bar"].get())
        else:
            temp_c = self._safe_float(self.pressure_vars["temperature_c"].get())
            pressure_bar = self._safe_float(self.pressure_vars["pressure_bar"].get())
        if temp_c is None or pressure_bar is None:
            raise ValidationError(
                f"{BOTAS_REFERENCE_TABLE_LABEL} icin once sicaklik ve basinc girilmelidir."
            )
        try:
            return lookup_botas_reference_point(temp_c=temp_c, pressure_bar=pressure_bar)
        except (ABControlTableError, FileNotFoundError, ValueError) as exc:
            raise ValidationError(f"{BOTAS_REFERENCE_TABLE_LABEL} bu nokta icin kullanilamaz: {exc}") from exc

    def _lookup_gail_reference_for_section(self, section: str):
        if section == "air":
            temp_c = self._safe_float(self.air_vars["temperature_c"].get())
            pressure_bar = self._safe_float(self.air_vars["pressure_bar"].get())
        else:
            temp_c = self._safe_float(self.pressure_vars["temperature_c"].get())
            pressure_bar = self._safe_float(self.pressure_vars["pressure_bar"].get())
        if temp_c is None or pressure_bar is None:
            raise ValidationError(
                f"{GAIL_REFERENCE_TABLE_LABEL} icin once sicaklik ve basinc girilmelidir."
            )
        try:
            return lookup_gail_reference_point(temp_c=temp_c, pressure_bar=pressure_bar)
        except (ABControlTableError, FileNotFoundError, ValueError) as exc:
            raise ValidationError(f"{GAIL_REFERENCE_TABLE_LABEL} bu nokta icin kullanilamaz: {exc}") from exc

    def _lookup_selected_table_reference(self, section: str, selected_label: str):
        if self._is_botas_reference_selection(selected_label):
            return self._lookup_botas_reference_for_section(section)
        if self._is_gail_reference_selection(selected_label):
            return self._lookup_gail_reference_for_section(section)
        raise ValidationError("Tablo secenegi icin BOTAS veya GAIL referans tablosu secilmelidir.")

    def _selected_reference_table_label(self, selected_label: str) -> str:
        if self._is_botas_reference_selection(selected_label):
            return BOTAS_REFERENCE_TABLE_LABEL
        if self._is_gail_reference_selection(selected_label):
            return GAIL_REFERENCE_TABLE_LABEL
        return "referans tablo"


    def _default_detail_report_text(self, section: str) -> str:
        if section == "air":
            return (
                "Hava Icerik Testi - Detay Raporu\n\n"
                "Geometri, A katsayisi ve karar hesabinda kullanilan terimler burada canli olarak gosterilir."
            )
        if section == "pressure":
            return (
                "Basinc Degisim Testi - Detay Raporu\n\n"
                "A/B katsayilarinin kaynagi ile karar hesabinda kullanilan tum degerler burada canli olarak gosterilir."
            )
        return (
            "Saha Kontrol - Detay Raporu\n\n"
            "Kontrol noktasi ozeti ve pig hiz hesabi burada canli olarak gosterilir."
        )

    def _format_detail_value(self, variable: tk.StringVar, unit: str = "") -> str:
        value = self._format_var_value(variable)
        if value == "-" or not unit:
            return value
        return f"{value} {unit}"

    def _detail_numeric_issue(self, variable: tk.StringVar, label: str) -> str | None:
        raw_value = variable.get().strip()
        if not raw_value:
            return f"{label} bekleniyor"
        if self._safe_float(raw_value) is None:
            return f"{label} gecersiz"
        return None

    def _detail_pipe_snapshot(self) -> tuple[PipeSection | PipeGeometry | None, str | None]:
        if self.geometry_segments:
            try:
                return (
                    PipeGeometry(
                        sections=tuple(segment_info["pipe"] for segment_info in self.geometry_segments)  # type: ignore[arg-type]
                    ),
                    None,
                )
            except ValidationError as exc:
                return None, str(exc)

        issues = [
            issue
            for issue in (
                self._detail_numeric_issue(self.geometry_vars["outside_diameter_mm"], "Dis cap"),
                self._detail_numeric_issue(self.geometry_vars["wall_thickness_mm"], "Et kalinligi"),
                self._detail_numeric_issue(self.geometry_vars["length_m"], "Hat uzunlugu"),
            )
            if issue is not None
        ]
        if issues:
            return None, ", ".join(issues)

        outside = self._safe_float(self.geometry_vars["outside_diameter_mm"].get())
        wall = self._safe_float(self.geometry_vars["wall_thickness_mm"].get())
        length = self._safe_float(self.geometry_vars["length_m"].get())
        if outside is None or wall is None or length is None:
            return None, "Geometri hazir degil."
        try:
            return (
                PipeSection(
                    outside_diameter_mm=outside,
                    wall_thickness_mm=wall,
                    length_m=length,
                ),
                None,
            )
        except ValidationError as exc:
            return None, str(exc)




    def _coefficient_origin_text(self, key: str) -> str:
        backend_label = self._selected_water_backend_info().label
        state = self.coefficient_states[key]
        if key == "air_a":
            if state == "computed":
                return f"Program hesabi ({backend_label} backend'i)."
            if state == "reference":
                reference_label = self.air_a_reference_var.get().strip() or "tablo secilmedi"
                return (
                    f"{self._selected_reference_table_label(reference_label)}: aktif sicaklik/basinc noktasinda "
                    "tablo/interpolasyon degeri."
                )
            if state == "manual":
                return "Kullanici girdisi / manuel tablo-prosedur."
            if state == "stale":
                return "Mevcut deger var ama kosullar degistigi icin yeniden dogrulanmali."
            return "Hazir degil; secili moda gore A degeri bekleniyor."
        if key == "pressure_a":
            if state == "computed":
                return f"Program hesabi ({backend_label} backend'i)."
            if state == "reference":
                reference_label = self.pressure_a_reference_var.get().strip() or "tablo secilmedi"
                return (
                    f"{self._selected_reference_table_label(reference_label)}: aktif sicaklik/basinc noktasinda "
                    "tablo/interpolasyon degeri."
                )
            if state == "manual":
                return "Kullanici girdisi / manuel tablo-prosedur."
            if state == "stale":
                return "Mevcut deger var ama kosullar degistigi icin yeniden dogrulanmali."
            return "Hazir degil; secili moda gore A degeri bekleniyor."
        if state == "computed":
            return f"Program hesabi (su beta - celik alpha, backend: {backend_label})."
        if state == "reference":
            reference_label = self.pressure_b_reference_var.get().strip() or "tablo secilmedi"
            return (
                f"{self._selected_reference_table_label(reference_label)}: B degeri aktif sicaklik/basinc "
                "noktasinda tablo/interpolasyon ile alindi."
            )
        if state == "manual":
            return "Kullanici girdisi / manuel tablo-prosedur."
        if state == "stale":
            return "Mevcut deger var ama helper kosullari degistigi icin yeniden dogrulanmali."
        if self.use_b_helper_var.get():
            return "Hazir degil; B helper veya tablo secimi ile olusturulmayi bekliyor."
        return "Hazir degil; kullanici tarafindan manuel B degeri bekleniyor."

    def _sync_detail_report_summary(self) -> None:
        active_tab = self._active_tab_key()
        if active_tab == "air":
            detail_text = self.air_detail_report_var.get() or self._default_detail_report_text("air")
        elif active_tab == "pressure":
            detail_text = self.pressure_detail_report_var.get() or self._default_detail_report_text("pressure")
        else:
            detail_text = self.field_detail_report_var.get() or self._default_detail_report_text("field")
        self.active_detail_report_var.set(detail_text)
        self._render_active_detail_report()

    def _render_active_detail_report(self) -> None:
        if not hasattr(self, "detail_report_text"):
            return
        self.detail_report_text.configure(state="normal")
        self.detail_report_text.delete("1.0", "end")
        self.detail_report_text.insert("end", self.active_detail_report_var.get())
        self.detail_report_text.configure(state="disabled")

    def _refresh_detail_reports(self) -> None:
        self.air_detail_report_var.set(self._build_air_detail_report())
        self.pressure_detail_report_var.set(self._build_pressure_detail_report())
        self.field_detail_report_var.set(self._build_field_detail_report())
        self._sync_detail_report_summary()



    def _update_water_backend_summary(self) -> None:
        info = self._selected_water_backend_info()
        self.water_backend_summary_var.set(
            f"Secili backend: {info.label}. Backend secimi ust menudeki Hesap > Su Ozelligi Backend'i alanindan yapilir. {info.note}"
        )

    def _sync_backend_comparison_summary(self) -> None:
        active_tab = self._active_tab_key()
        if active_tab == "air":
            self.active_backend_comparison_var.set(self.air_backend_comparison_var.get())
            self._sync_detail_report_summary()
            return
        if active_tab == "pressure":
            self.active_backend_comparison_var.set(self.pressure_backend_comparison_var.get())
            self._sync_detail_report_summary()
            return
        self.active_backend_comparison_var.set(self._default_backend_comparison_text("field"))
        self._sync_detail_report_summary()

    def _sync_control_table_summary(self) -> None:
        active_tab = self._active_tab_key()
        if active_tab == "air":
            self.active_control_table_var.set(self.air_control_table_var.get())
            return
        if active_tab == "pressure":
            self.active_control_table_var.set(self.pressure_control_table_var.get())
            return
        self.active_control_table_var.set(self._default_control_table_text("field"))

    def _refresh_control_table_summaries(self) -> None:
        self.air_control_table_var.set(self._build_air_control_table_summary())
        self.pressure_control_table_var.set(self._build_pressure_control_table_summary())
        self._sync_control_table_summary()
        self._refresh_detail_reports()



    def _format_control_table_delta(self, value: float, reference: float) -> str:
        delta = value - reference
        delta_pct = (delta / reference * 100.0) if abs(reference) > 1e-12 else 0.0
        return f"{delta:+.6f} | %{delta_pct:+.6f}"

    def _mark_water_backend_change(self) -> None:
        if self._air_a_is_auto() and self.air_vars["a_micro_per_bar"].get().strip():
            self.coefficient_states["air_a"] = "stale"
        if self._pressure_a_is_auto() and self.pressure_vars["a_micro_per_bar"].get().strip():
            self.coefficient_states["pressure_a"] = "stale"
        if self._pressure_b_is_auto() and self.pressure_vars["b_micro_per_c"].get().strip():
            self.coefficient_states["pressure_b"] = "stale"
            self.b_helper_vars["water_beta_micro_per_c"].set("")
        self._refresh_coefficient_statuses()

    def _format_var_value(self, variable: tk.StringVar) -> str:
        value = variable.get().strip()
        return value if value else "-"

    def _current_geometry_descriptor(self) -> tuple[str, str]:
        size_label = self.geometry_catalog_vars["size_option"].get().strip()
        schedule_label = self.geometry_catalog_vars["schedule_option"].get().strip()
        pipe_size = find_pipe_size(size_label)
        schedule = find_schedule(size_label, schedule_label)
        nps_label = "-"
        schedule_text = "Elle giris"
        if pipe_size is not None:
            nps_label = f"NPS {pipe_size['nps']} / DN {pipe_size['dn']}"
        if schedule is not None:
            schedule_text = schedule["label"]
        return nps_label, schedule_text

    def _on_pipe_size_selected(self, _: tk.Event | None = None) -> None:
        size_label = self.geometry_catalog_vars["size_option"].get().strip()
        schedule_options = get_schedule_options(size_label)
        self.pipe_schedule_combo.configure(values=schedule_options)
        if schedule_options:
            self.geometry_catalog_vars["schedule_option"].set(schedule_options[0])
        else:
            self.geometry_catalog_vars["schedule_option"].set("")

    def _apply_catalog_selection(self) -> None:
        size_label = self.geometry_catalog_vars["size_option"].get().strip()
        schedule_label = self.geometry_catalog_vars["schedule_option"].get().strip()
        pipe_size = find_pipe_size(size_label)
        schedule = find_schedule(size_label, schedule_label)
        if pipe_size is None or schedule is None:
            self._set_banner("Listeden doldurmak icin once NPS ve schedule secin.", "warning")
            return
        self.geometry_vars["outside_diameter_mm"].set(f"{pipe_size['outside_diameter_mm']:.2f}")
        self.geometry_vars["wall_thickness_mm"].set(f"{schedule['wall_thickness_mm']:.2f}")
        self._set_banner("ASME B36.10 listesinden geometri alanlari dolduruldu.", "success")

    def _build_manual_pipe_section(self, section: str) -> PipeSection:
        return PipeSection(
            outside_diameter_mm=self._read_float(
                self.geometry_vars["outside_diameter_mm"], "Dis cap", section, "geometry.outside_diameter_mm"
            ),
            wall_thickness_mm=self._read_float(
                self.geometry_vars["wall_thickness_mm"], "Et kalinligi", section, "geometry.wall_thickness_mm"
            ),
            length_m=self._read_float(
                self.geometry_vars["length_m"], "Hat uzunlugu", section, "geometry.length_m"
            ),
        )

    def _add_geometry_segment(self) -> None:
        self._clear_feedback("geometry")
        try:
            segment = self._build_manual_pipe_section("geometry")
        except ValidationError as exc:
            self._set_banner(str(exc), "error")
            return
        nps_label, schedule_text = self._current_geometry_descriptor()
        self.geometry_segments.append(
            {
                "pipe": segment,
                "nps_label": nps_label,
                "schedule_label": schedule_text,
            }
        )
        if not self.geometry_details_visible_var.get():
            self.geometry_details_visible_var.set(True)
            self._apply_geometry_details_visibility()
        self._refresh_segment_tree()
        self._refresh_geometry_summary()
        self._set_banner("Geometri segmenti listeye eklendi.", "success")

    def _remove_selected_segment(self) -> None:
        selected_item = self.segment_tree.selection()
        if not selected_item:
            self._set_banner("Silmek icin once bir segment secin.", "warning")
            return
        index = int(selected_item[0]) - 1
        if 0 <= index < len(self.geometry_segments):
            self.geometry_segments.pop(index)
            self._refresh_segment_tree()
            self._refresh_geometry_summary()
            self._set_banner("Secili segment kaldirildi.", "info")

    def _clear_geometry_segments(self) -> None:
        self.geometry_segments.clear()
        self._refresh_segment_tree()
        self._refresh_geometry_summary()
        self._set_banner("Segment listesi temizlendi. Ustteki geometri alanlari tekrar aktif referans oldu.", "info")

    def _import_segments_from_csv(self) -> None:
        file_path = filedialog.askopenfilename(
            title="CSV Dosyasindan Segment Icari Al",
            filetypes=(("CSV dosyalari", "*.csv"), ("Tum dosyalar", "*.*")),
        )
        if not file_path:
            return
        try:
            with open(file_path, "r", encoding="utf-8-sig", newline="") as handle:
                raw = handle.read()
            segments = self._parse_segment_csv(raw)
        except Exception as exc:
            self._set_banner(f"CSV okunamadi: {exc}", "error")
            return
        self._ingest_parsed_segments(segments)

    def _import_segments_from_clipboard(self) -> None:
        try:
            raw = self.root.clipboard_get()
        except tk.TclError:
            self._set_banner("Panoda metin bulunamadi.", "warning")
            return
        if not raw.strip():
            self._set_banner("Panoda metin bulunamadi.", "warning")
            return
        segments = self._parse_segment_csv(raw)
        self._ingest_parsed_segments(segments)

    def _ingest_parsed_segments(self, segments: list[ParsedSegment]) -> None:
        if not segments:
            self._set_banner("Gecerli segment satiri bulunamadi. Format: OD,Et,Uzunluk", "warning")
            return
        for seg in segments:
            try:
                pipe = PipeSection(
                    outside_diameter_mm=seg.outside_diameter_mm,
                    wall_thickness_mm=seg.wall_thickness_mm,
                    length_m=seg.length_m,
                )
            except ValidationError as exc:
                self._set_banner(
                    f"Segment gecersiz (OD={seg.outside_diameter_mm}, "
                    f"Et={seg.wall_thickness_mm}, L={seg.length_m}): {exc}",
                    "error",
                )
                continue
            self.geometry_segments.append(
                {
                    "pipe": pipe,
                    "nps_label": f"OD {seg.outside_diameter_mm:.1f}",
                    "schedule_label": f"WT {seg.wall_thickness_mm:.2f}",
                }
            )
        if not self.geometry_details_visible_var.get():
            self.geometry_details_visible_var.set(True)
            self._apply_geometry_details_visibility()
        self._refresh_segment_tree()
        self._refresh_geometry_summary()
        self._set_banner(f"{len(self.geometry_segments)} segment listede.", "success")

    @staticmethod
    def _parse_segment_csv(raw: str) -> list[ParsedSegment]:
        return parse_segment_csv(raw)

    def _refresh_segment_tree(self) -> None:
        if not hasattr(self, "segment_tree"):
            return
        for item_id in self.segment_tree.get_children():
            self.segment_tree.delete(item_id)
        if not self.geometry_segments:
            self.segment_summary_var.set(
                "Segmentasyon kullanilmazsa ustteki geometri alanlari tek boru kesiti olarak kullanilir."
            )
            return
        total_length = 0.0
        total_volume = 0.0
        for index, segment_info in enumerate(self.geometry_segments, start=1):
            pipe = segment_info["pipe"]
            assert isinstance(pipe, PipeSection)
            total_length += pipe.length_m
            total_volume += pipe.internal_volume_m3
            self.segment_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    index,
                    segment_info["nps_label"],
                    segment_info["schedule_label"],
                    f"{pipe.outside_diameter_mm:.2f}",
                    f"{pipe.wall_thickness_mm:.2f}",
                    f"{pipe.length_m:.2f}",
                ),
            )
        self.segment_summary_var.set(
            f"Segment sayisi = {len(self.geometry_segments)}, toplam uzunluk = {total_length:.2f} m, toplam ic hacim = {total_volume:.6f} m3"
        )

    def _on_tab_changed(self, _: tk.Event | None = None) -> None:
        self._update_workflow_hint()
        self._update_contextual_actions()
        self._sync_backend_comparison_summary()
        self._sync_control_table_summary()
        self._sync_detail_report_summary()
        self._refresh_section_pressure_overview()
        self._refresh_live_test_decision()
        self._update_live_notice()
        self._refresh_visual_schema()
        self._update_action_button_states()

    def _update_workflow_hint(self) -> None:
        active_tab = self._active_tab_key()
        backend_label = self._selected_water_backend_info().label
        if active_tab == "air":
            a_hint = (
                f"A otomatik modda; backend = {backend_label}."
                if self._air_a_is_auto()
                else "A manuel modda; tablo/prosedur degeri beklenir."
            )
            self.workflow_steps_var.set(
                "1. Geometri ve segmentleri tamamla.\n"
                "2. A katsayisini hazirla.\n"
                "3. P=1.0 bar, K ve Vpa degerlerini gir.\n"
                "4. Testi degerlendir, karar karti ve oran sonucunu kontrol et."
            )
            self.workflow_hint_var.set(
                "Aktif test: Hava Icerik Testi. Onerilen akis: geometriyi kontrol edin, A'yi hesaplayin, "
                "sartnameye gore P=1.0 bar, K ve Vpa girip 'Aktif Testi Degerlendir' kullanin. "
                + a_hint
                + " Kisayol: Ctrl+Enter."
            )
        elif active_tab == "pressure":
            a_mode = (
                f"A otomatik modda; backend = {backend_label}."
                if self._pressure_a_is_auto()
                else "A manuel modda; tablo/prosedur degeri beklenir."
            )
            b_mode = (
                f"B otomatik modda; helper secili backend ({backend_label}) ile su beta ve celik alpha kullanir."
                if self._pressure_b_is_auto()
                else "B tablo modda; secilen BOTAS veya GAIL referans tablosundan dogrudan yuklenir."
                if self._pressure_b_is_reference()
                else "B manuel modda; degeri dogrudan ve dogrulanmis kaynaktan girmelisiniz."
            )
            self.workflow_steps_var.set(
                "1. Geometri ve segmentleri tamamla.\n"
                "2. A ve B katsayilarini hazirla.\n"
                "3. dT = Tilk - Tson ve Pa = Pilk - Pson gir.\n"
                "4. Testi degerlendir, (Pa - dP) <= 0.3 bar kararini kontrol et."
            )
            self.workflow_hint_var.set(
                "Aktif test: Basinc Degisim Testi. Onerilen akis: geometriyi kontrol edin, A ve B'yi hazirlayin, "
                "dT = Tilk - Tson ve Pa = Pilk - Pson girip degerlendirin. "
                + a_mode
                + " "
                + b_mode
            )
        else:
            self.workflow_steps_var.set(
                "1. Saha kontrol noktalarini isaretle.\n"
                "2. Pig modu, mesafe ve sureyi gir.\n"
                "3. Pig hizini hesapla ve limit asimi olup olmadigini kontrol et.\n"
                "4. Bu sekmedeki notlari saha kaydiyla birlikte rapora aktar."
            )
            self.workflow_hint_var.set(
                "Aktif alan: Saha Kontrol. Bu sekme test uygulanirken dikkat edilen kritik noktalarin "
                "unutulmamasina yardim eder ve pig hizinin sartname limitlerini asip asmadigini kontrol eder. "
                "Backend karsilastirmasi bu sekmede kullanilmaz."
            )

    def _update_contextual_actions(self) -> None:
        active_tab = self._active_tab_key()
        if active_tab in {"air", "pressure"}:
            self._set_progress_button_idle_text("run_selected", "Aktif Testi Degerlendir")
            self._set_progress_button_idle_text("recalculate", "Katsayilari Yenile")
            self.clear_form_button.configure(text="Aktif Formu Temizle")
            self.compare_backend_button.configure(
                state="normal" if len(self.water_backend_infos) > 1 else "disabled"
            )
        else:
            self._set_progress_button_idle_text("run_selected", "Pig Hizini Hesapla")
            self._set_progress_button_idle_text("recalculate", "Kontrol Ozetini Yenile")
            self.clear_form_button.configure(text="Saha Formunu Temizle")
            self.compare_backend_button.configure(state="disabled")

    def _update_check_summary(self) -> None:
        checked_count = sum(1 for variable in self.control_check_vars.values() if variable.get())
        total_count = len(self.control_check_vars)
        self.check_progress_var.set(float(checked_count))
        self.check_summary_var.set(
            f"Isaretlenen kontrol noktasi: {checked_count} / {total_count}. "
            "Bu tablo karar algoritmasi degil, saha uygulama dogrulama yardimcisidir."
        )
        self._update_live_notice()
        self._refresh_visual_schema()
        self._refresh_detail_reports()




    def _on_water_backend_changed(self, _: tk.Event | None = None) -> None:
        self._update_water_backend_summary()
        self._mark_water_backend_change()
        self._refresh_auto_coefficients_for_selected_backend()
        self.air_backend_comparison_var.set(
            "Backend secimi degisti. Hava testi icin tekrar karsilastirin."
        )
        self.pressure_backend_comparison_var.set(
            "Backend secimi degisti. Basinc testi icin tekrar karsilastirin."
        )
        self._sync_backend_comparison_summary()
        self._set_banner(
            f"Su ozelligi backend'i {self._selected_water_backend_info().label} olarak secildi.",
            "info",
        )
        self._refresh_live_test_decision()
        self._update_live_notice()
        self._refresh_visual_schema()
        self._refresh_detail_reports()

    def _refresh_auto_coefficients_for_selected_backend(self) -> None:
        air_ready = (
            self._air_a_is_auto()
            and self._safe_float(self.air_vars["temperature_c"].get()) is not None
            and self._safe_float(self.air_vars["pressure_bar"].get()) is not None
        )
        pressure_ready = (
            self._pressure_a_is_auto()
            and self._safe_float(self.pressure_vars["temperature_c"].get()) is not None
            and self._safe_float(self.pressure_vars["pressure_bar"].get()) is not None
        )
        b_ready = (
            self._pressure_b_is_auto()
            and pressure_ready
            and self._safe_float(self.b_helper_vars["steel_alpha_micro_per_c"].get()) is not None
        )
        if air_ready:
            self._calculate_air_a(log_result=False, silent=True)
        if pressure_ready:
            self._calculate_pressure_a(log_result=False, silent=True)
        if b_ready:
            self._calculate_b_helper(log_result=False, silent=True)

    def _compare_active_backend(self) -> None:
        active_tab = self._active_tab_key()
        if active_tab == "field":
            self._sync_backend_comparison_summary()
            self._set_banner("Saha Kontrol sekmesinde backend karsilastirmasi kullanilmaz.", "info")
            return
        try:
            if active_tab == "air":
                self._clear_feedback("air")
                summary = self._build_air_backend_comparison()
                self.air_backend_comparison_var.set(summary)
                title = "Hava Icerik Testi - backend karsilastirmasi"
            else:
                self._clear_feedback("pressure")
                summary = self._build_pressure_backend_comparison()
                self.pressure_backend_comparison_var.set(summary)
                title = "Basinc Degisim Testi - backend karsilastirmasi"
        except ValidationError as exc:
            self._set_banner(str(exc), "error")
            return
        self._sync_backend_comparison_summary()
        self._refresh_detail_reports()
        self._append_result(title, summary)
        self._set_banner("Backend karsilastirmasi guncellendi.", "success")


    def _format_backend_b_value(self, value: float | None, error: str | None = None) -> str:
        if value is not None:
            return f"{value:.6f}"
        if error:
            return f"hesaplanamadi ({error})"
        return "hesaplanamadi"


    def _focus_field(self, field_key: str | None) -> None:
        if not field_key:
            return
        widget = self.input_widgets.get(field_key) or self.entry_widgets.get(field_key)
        if widget is not None:
            widget.focus_set()
            if isinstance(widget, ttk.Entry):
                widget.selection_range(0, "end")



    def _on_b_helper_calculate_button(self) -> object:
        return self._execute_progress_button_action(
            "pressure_b_calculate",
            self._calculate_b_helper,
            result_state_resolver=self._bool_progress_state,
        )




    def _run_selected_test(self) -> object:
        active_tab = self._active_tab_key()
        if active_tab == "air":
            return self._execute_progress_button_action(
                "run_selected",
                self._run_air_test_impl,
                result_state_resolver=self._decision_progress_state,
            )
        if active_tab == "pressure":
            return self._execute_progress_button_action(
                "run_selected",
                self._run_pressure_test_impl,
                result_state_resolver=self._decision_progress_state,
            )
        return self._execute_progress_button_action(
            "run_selected",
            lambda: self._calculate_pig_speed(),
            result_state_resolver=self._pig_progress_state,
        )

    def _run_selected_test_impl(self) -> None:
        active_tab = self._active_tab_key()
        if active_tab == "air":
            self._run_air_test_impl()
        elif active_tab == "pressure":
            self._run_pressure_test_impl()
        else:
            self._calculate_pig_speed()

    def _recalculate_active_coefficients(self) -> object:
        active_tab = self._active_tab_key()
        if active_tab == "air":
            return self._execute_progress_button_action(
                "recalculate",
                self._calculate_air_a,
                result_state_resolver=self._bool_progress_state,
            )
        if active_tab == "pressure":
            return self._execute_progress_button_action(
                "recalculate",
                self._recalculate_active_coefficients_impl,
                result_state_resolver=self._bool_progress_state,
            )
        return self._execute_progress_button_action(
            "recalculate",
            self._recalculate_active_coefficients_impl,
            result_state_resolver=self._pig_progress_state,
        )

    def _recalculate_active_coefficients_impl(self) -> bool:
        active_tab = self._active_tab_key()
        if active_tab == "air":
            return self._calculate_air_a()
        if active_tab == "pressure":
            if not self._calculate_pressure_a():
                return False
            if self.use_b_helper_var.get():
                return self._calculate_b_helper()
            return True
        self._update_check_summary()
        if self.field_vars["pig_distance_m"].get().strip() and self.field_vars["pig_travel_time_min"].get().strip():
            return self._calculate_pig_speed(log_result=False)
        return True

    def _clear_active_form(self) -> None:
        active_tab = self._active_tab_key()
        if active_tab == "air":
            self._clear_air_form()
        elif active_tab == "pressure":
            self._clear_pressure_form()
        else:
            self._clear_field_form()

    def _read_float(
        self, variable: tk.StringVar, field_name: str, section: str, field_key: str | None = None
    ) -> float:
        normalized = variable.get().strip().replace(",", ".")
        if not normalized:
            message = f"{field_name} bos birakilamaz."
            self._set_feedback(section, message)
            if field_key is not None:
                self._set_field_message(field_key, "Bu alan zorunlu.", "error")
            self._focus_field(field_key)
            raise ValidationError(message)
        try:
            value = float(normalized)
        except ValueError as exc:
            message = f"{field_name} icin gecerli bir sayi girin."
            self._set_feedback(section, message)
            if field_key is not None:
                self._set_field_message(field_key, "Gecerli bir sayi girin.", "error")
            self._focus_field(field_key)
            raise ValidationError(message) from exc
        if field_key is not None and field_key not in {"air.a_micro_per_bar", "pressure.a_micro_per_bar", "pressure.b_micro_per_c"}:
            self._clear_field_message(field_key)
        return value






    def _apply_single_coefficient_mode(
        self,
        *,
        key: str,
        field_key: str,
        variable: tk.StringVar,
        mode: str,
        reference_combo: ttk.Combobox | None = None,
        auto_banner: str,
        reference_banner: str,
        manual_banner: str,
    ) -> None:
        entry = self.entry_widgets.get(field_key)
        if entry is not None:
            entry.configure(state="readonly" if mode != MANUAL_A_MODE else "normal")
        if reference_combo is not None:
            reference_combo.configure(state="readonly" if mode == REFERENCE_A_MODE else "disabled")
        if field_key == "air.a_micro_per_bar" and hasattr(self, "air_a_calculate_button"):
            self.air_a_calculate_button.configure(state="normal" if mode == AUTO_A_MODE else "disabled")
        if field_key == "pressure.a_micro_per_bar" and hasattr(self, "pressure_a_calculate_button"):
            self.pressure_a_calculate_button.configure(state="normal" if mode == AUTO_A_MODE else "disabled")
        meta = self.field_meta.get(field_key)
        if meta is not None:
            meta["required"] = mode == MANUAL_A_MODE
            meta["readonly"] = mode != MANUAL_A_MODE
        if mode == AUTO_A_MODE:
            self.coefficient_states[key] = "stale" if variable.get().strip() else "empty"
            self._set_banner(auto_banner, "info")
        elif mode == REFERENCE_A_MODE:
            self.coefficient_states[key] = "reference" if variable.get().strip() else "empty"
            self._set_banner(reference_banner, "info")
        else:
            self.coefficient_states[key] = "manual" if variable.get().strip() else "empty"
            self._set_banner(manual_banner, "warning")
        self._refresh_coefficient_statuses()
        self._update_live_notice()
        self._update_workflow_hint()






    def _apply_b_helper_mode(self) -> None:
        b_entry = self.entry_widgets.get("pressure.b_micro_per_c")
        steel_entry = self.entry_widgets.get("helper.steel_alpha_micro_per_c")
        water_entry = self.entry_widgets.get("helper.water_beta_micro_per_c")
        if b_entry is None:
            return
        auto_mode = self._pressure_b_is_auto()
        reference_mode = self._pressure_b_is_reference()
        helper_active = auto_mode
        self.use_b_helper_var.set(helper_active)
        if hasattr(self, "pressure_b_reference_combo"):
            self.pressure_b_reference_combo.configure(state="readonly" if reference_mode else "disabled")
        if auto_mode or reference_mode:
            b_entry.configure(state="readonly")
            if steel_entry is not None:
                steel_entry.configure(state="normal" if helper_active else "disabled")
            if water_entry is not None:
                water_entry.configure(state="readonly" if helper_active else "disabled")
            if hasattr(self, "steel_preset_combo"):
                self.steel_preset_combo.configure(state="readonly" if helper_active else "disabled")
            if hasattr(self, "b_helper_calculate_button"):
                self.b_helper_calculate_button.configure(state="normal" if auto_mode else "disabled")
            self.field_meta["pressure.b_micro_per_c"]["required"] = False
            self.field_meta["pressure.b_micro_per_c"]["readonly"] = True
            self.field_meta["helper.steel_alpha_micro_per_c"]["required"] = helper_active
            self.field_meta["helper.steel_alpha_micro_per_c"]["readonly"] = not helper_active
            self.field_meta["helper.water_beta_micro_per_c"]["required"] = False
            self.field_meta["helper.water_beta_micro_per_c"]["readonly"] = helper_active
            if auto_mode:
                self.coefficient_states["pressure_b"] = (
                    "stale" if self.pressure_vars["b_micro_per_c"].get().strip() else "empty"
                )
                self.helper_mode_summary_var.set(
                    "B secenegi otomatik. B alani kilitlidir; helper su beta ve celik alpha ile hesaplar."
                )
                self._set_banner(
                    "B secenegi otomatik. Degerlendirme sirasinda B helper kullanilir ve alan otomatik doldurulur.",
                    "info",
                )
            else:
                self.coefficient_states["pressure_b"] = (
                    "reference" if self.pressure_vars["b_micro_per_c"].get().strip() else "empty"
                )
                self.b_helper_vars["water_beta_micro_per_c"].set("")
                self.helper_mode_summary_var.set(
                    f"B secenegi tablo modda. {BOTAS_REFERENCE_TABLE_LABEL} veya "
                    f"{GAIL_REFERENCE_TABLE_LABEL} secildiginde B dogrudan tablodan yuklenir."
                )
                self._set_banner(
                    "B secenegi tablo modda. B degeri secilen referans tablodan yuklenir.",
                    "info",
                )
        else:
            b_entry.configure(state="normal")
            if steel_entry is not None:
                steel_entry.configure(state="disabled")
            if water_entry is not None:
                water_entry.configure(state="disabled")
            if hasattr(self, "steel_preset_combo"):
                self.steel_preset_combo.configure(state="disabled")
            if hasattr(self, "b_helper_calculate_button"):
                self.b_helper_calculate_button.configure(state="disabled")
            self.field_meta["pressure.b_micro_per_c"]["required"] = True
            self.field_meta["pressure.b_micro_per_c"]["readonly"] = False
            self.field_meta["helper.steel_alpha_micro_per_c"]["required"] = False
            self.field_meta["helper.steel_alpha_micro_per_c"]["readonly"] = True
            self.field_meta["helper.water_beta_micro_per_c"]["required"] = False
            self.field_meta["helper.water_beta_micro_per_c"]["readonly"] = True
            self.b_helper_vars["water_beta_micro_per_c"].set("")
            self.coefficient_states["pressure_b"] = (
                "manual" if self.pressure_vars["b_micro_per_c"].get().strip() else "empty"
            )
            self.helper_mode_summary_var.set(
                "B secenegi manuel. B degerini tabloda veya prosedurde dogrulanan haliyle dogrudan girin."
            )
            self._set_banner(
                "B secenegi manuel. Basinc testi icin B degerini dogrudan girmeniz gerekir.",
                "warning",
            )
        self._refresh_coefficient_statuses()
        self._sync_coefficient_field_messages()
        self._refresh_choice_validation_states()
        self._update_live_notice()
        self._update_workflow_hint()
        self._refresh_live_coefficients()
        self._refresh_live_test_decision()




    def _set_coefficient_value(
        self,
        key: str,
        variable: tk.StringVar,
        value: float,
        *,
        state: str = "computed",
    ) -> None:
        self._programmatic_coefficient_updates.add(key)
        try:
            variable.set(f"{value:.6f}")
        finally:
            self._programmatic_coefficient_updates.discard(key)
        self.coefficient_states[key] = state
        self._refresh_coefficient_statuses()

    def _update_decision_card(self, title: str, status: str, summary: str) -> None:
        self.decision_title_var.set(title)
        self.decision_status_var.set(status)
        self.decision_summary_var.set(summary)
        if status == "BASARILI":
            self.decision_status_label.configure(bg="#E6F4EA", fg="#1E6F43")
        elif status == "BASARISIZ":
            self.decision_status_label.configure(bg="#FDE7E9", fg="#A4262C")
        else:
            self.decision_status_label.configure(bg="#EEF2FF", fg="#243B73")

    def _on_k_preset_changed(self, _: tk.Event) -> None:
        self.air_vars["k_factor"].set(self._default_k_factor())

    def _on_steel_preset_changed(self, _: tk.Event) -> None:
        self.b_helper_vars["steel_alpha_micro_per_c"].set(self._default_steel_alpha())

    def _build_pipe_section(self, section: str) -> PipeSection | PipeGeometry:
        try:
            if self.geometry_segments:
                return PipeGeometry(
                    sections=tuple(segment_info["pipe"] for segment_info in self.geometry_segments)  # type: ignore[arg-type]
                )
            return self._build_manual_pipe_section(section)
        except ValidationError as exc:
            self._set_feedback("geometry", str(exc))
            raise



    def _calculate_b_helper(self, log_result: bool = True, silent: bool = False) -> bool:
        self._clear_feedback("pressure")
        backend_info = self._selected_water_backend_info()
        try:
            water_beta = calculate_water_thermal_expansion_beta(
                temp_c=self._read_float(
                    self.pressure_vars["temperature_c"], "Su sicakligi", "pressure", "pressure.temperature_c"
                ),
                pressure_bar=self._read_float(
                    self.pressure_vars["pressure_bar"], "Su basinci", "pressure", "pressure.pressure_bar"
                ),
                backend=backend_info.key,
            )
            steel_alpha = self._read_float(
                self.b_helper_vars["steel_alpha_micro_per_c"], "Celik alpha", "pressure", "helper.steel_alpha_micro_per_c"
            )
            b_value = calculate_b_coefficient(water_beta, steel_alpha)
        except ValidationError as exc:
            if not silent:
                self._set_banner(str(exc), "error")
                self._update_decision_card("Basinc Degisim Testi", "DOGRULANAMADI", str(exc))
            return False

        self.b_helper_vars["water_beta_micro_per_c"].set(f"{water_beta:.6f}")
        self._set_coefficient_value("pressure_b", self.pressure_vars["b_micro_per_c"], b_value)
        self._refresh_control_table_summaries()
        if log_result:
            self._append_result(
                "B Yardimcisi",
                (
                    f"Backend: {backend_info.label}\n"
                    f"Su beta: {water_beta:.6f} (10^-6 / degC)\n"
                    f"Celik alpha: {steel_alpha:.6f} (10^-6 / degC)\n"
                    f"Hesaplanan B: {b_value:.6f} (10^-6 / degC)\n"
                    f"Kontrol tablosu: {self.pressure_control_table_var.get()}"
                ),
            )
        if not silent:
            self._set_banner("Basinc degisim testi icin B katsayisi helper ile guncellendi.", "success")
        return True

    def coefficient_value_present(self, key: str) -> bool:
        if key == "air_a":
            return bool(self.air_vars["a_micro_per_bar"].get().strip())
        if key == "pressure_a":
            return bool(self.pressure_vars["a_micro_per_bar"].get().strip())
        return bool(self.pressure_vars["b_micro_per_c"].get().strip())

    def _ensure_coefficient_ready(self, key: str) -> bool:
        if self.coefficient_states[key] in {"computed", "reference", "manual"} and self.coefficient_value_present(key):
            return True
        if key == "air_a":
            if self._air_a_is_auto():
                return self._calculate_air_a(log_result=False)
            if self._air_a_is_reference():
                return self._apply_air_a_reference(log_result=False)
            self._set_feedback("air", "A degeri manuel secenekte tablo/prosedurdan girilmelidir.")
            self._focus_field("air.a_micro_per_bar")
            self._set_banner("Hava testi icin A degeri manuel olarak girilmelidir.", "warning")
            self._update_decision_card("Hava Icerik Testi", "DOGRULANAMADI", "Gerekli A katsayisi hazir degil.")
            return False
        if key == "pressure_a":
            if self._pressure_a_is_auto():
                return self._calculate_pressure_a(log_result=False)
            if self._pressure_a_is_reference():
                return self._apply_pressure_a_reference(log_result=False)
            self._set_feedback("pressure", "A degeri manuel secenekte tablo/prosedurdan girilmelidir.")
            self._focus_field("pressure.a_micro_per_bar")
            self._set_banner("Basinc testi icin A degeri manuel olarak girilmelidir.", "warning")
            self._update_decision_card("Basinc Degisim Testi", "DOGRULANAMADI", "Gerekli A katsayisi hazir degil.")
            return False
        if key == "pressure_b":
            if self._pressure_b_is_reference():
                return self._apply_pressure_b_reference(log_result=False)
            if self.use_b_helper_var.get():
                return self._calculate_b_helper(log_result=False)
        self._set_feedback("pressure", "B degeri manuel girilmeli veya yardimci ile hesaplanmali.")
        self._focus_field("pressure.b_micro_per_c")
        self._set_banner("Basinc testi icin B degeri hazir degil.", "warning")
        self._update_decision_card("Basinc Degisim Testi", "DOGRULANAMADI", "Gerekli katsayi hazir degil.")
        return False



    def _append_result(self, title: str, content: str) -> None:
        stamped_entry = (
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {title}\n{content}"
        )
        self.report_entries.append(stamped_entry)
        self.results_text.configure(state="normal")
        self.results_text.insert("end", f"\n{stamped_entry}\n")
        self.results_text.see("end")
        self.results_text.configure(state="disabled")



    def _clear_results(self) -> None:
        self.report_entries.clear()
        self.results_text.configure(state="normal")
        self.results_text.delete("1.0", "end")
        self.results_text.insert(
            "end",
            "Oturum sonuclari burada zaman damgasi ile listelenecek.\n"
            "Not: Bu panel bir karar ozeti degil, kayit gunlugudur.\n",
        )
        self.results_text.configure(state="disabled")
        self._reset_decision_card()
        self._set_banner(
            "Sonuc gecmisi temizlendi. Yeni degerlendirme icin guncel girdileri kullanin.",
            "info",
        )

    def _build_report_text(self) -> str:
        lines = [
            f"{APP_NAME} Raporu",
            f"Surum: {APP_VERSION}",
            f"Referans sartname: {SPEC_DOCUMENT_CODE} - {SPEC_DOCUMENT_TITLE}",
            f"Olusturma zamani: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "Boru Kesiti",
            f"Dis cap (mm): {self._format_var_value(self.geometry_vars['outside_diameter_mm'])}",
            f"Et kalinligi (mm): {self._format_var_value(self.geometry_vars['wall_thickness_mm'])}",
            f"Hat uzunlugu (m): {self._format_var_value(self.geometry_vars['length_m'])}",
            f"Liste secimi: {self.geometry_catalog_vars['size_option'].get().strip() or '-'}",
            f"Schedule secimi: {self.geometry_catalog_vars['schedule_option'].get().strip() or '-'}",
            f"En yuksek nokta kotu (m): {self._format_var_value(self.section_profile_vars['highest_elevation_m'])}",
            f"En dusuk nokta kotu (m): {self._format_var_value(self.section_profile_vars['lowest_elevation_m'])}",
            f"Baslangic noktasi kotu (m): {self._format_var_value(self.section_profile_vars['start_elevation_m'])}",
            f"Bitis noktasi kotu (m): {self._format_var_value(self.section_profile_vars['end_elevation_m'])}",
            f"Dizayn basinci (bar): {self._format_var_value(self.section_profile_vars['design_pressure_bar'])}",
            f"Boru malzeme kalitesi: {self.material_grade_var.get().strip() or '-'}",
            f"SMYS (MPa): {self._format_var_value(self.section_profile_vars['smys_mpa'])}",
            f"Location Class: {self.location_class_var.get().strip() or '-'}",
            f"Pompa konumu: {self.pump_location_var.get().strip() or '-'}",
            f"Basinc penceresi: {self.section_pressure_summary_var.get()}",
            "",
        ]
        if self.geometry_segments:
            lines.extend(["Segment Listesi"])
            for index, segment_info in enumerate(self.geometry_segments, start=1):
                pipe = segment_info["pipe"]
                assert isinstance(pipe, PipeSection)
                lines.append(
                    f"{index}. {segment_info['nps_label']} | {segment_info['schedule_label']} | OD {pipe.outside_diameter_mm:.2f} mm | Et {pipe.wall_thickness_mm:.2f} mm | L {pipe.length_m:.2f} m"
                )
            lines.append("")
        lines.extend(
            [
                "Hava Icerik Testi Girdileri",
                f"Su sicakligi (degC): {self._format_var_value(self.air_vars['temperature_c'])}",
                f"Su basinci (bar): {self._format_var_value(self.air_vars['pressure_bar'])}",
                f"A secenegi: {self.air_a_mode_var.get().strip()}",
                f"Su backend'i: {self._selected_water_backend_info().label}",
                f"Backend ozeti: {self.water_backend_summary_var.get()}",
                f"A referans tablosu: {self.air_a_reference_var.get().strip() or '-'}",
                f"A (10^-6 / bar): {self._format_var_value(self.air_vars['a_micro_per_bar'])}",
                f"Hava backend karsilastirmasi: {self.air_backend_comparison_var.get()}",
                f"Hava kontrol tablosu: {self.air_control_table_var.get()}",
                f"Basinc artisi P (bar, sartname 1.0): {self._format_var_value(self.air_vars['pressure_rise_bar'])}",
                f"K faktor: {self._format_var_value(self.air_vars['k_factor'])}",
                f"Fiili ilave su Vpa (m3): {self._format_var_value(self.air_vars['actual_added_water_m3'])}",
                "",
                "Basinc Degisim Testi Girdileri",
                f"Su sicakligi (degC): {self._format_var_value(self.pressure_vars['temperature_c'])}",
                f"Su basinci (bar): {self._format_var_value(self.pressure_vars['pressure_bar'])}",
                f"A secenegi: {self.pressure_a_mode_var.get().strip()}",
                f"A referans tablosu: {self.pressure_a_reference_var.get().strip() or '-'}",
                f"A (10^-6 / bar): {self._format_var_value(self.pressure_vars['a_micro_per_bar'])}",
                f"B secenegi: {self.pressure_b_mode_var.get().strip()}",
                f"B referans tablosu: {self.pressure_b_reference_var.get().strip() or '-'}",
                f"B (10^-6 / degC): {self._format_var_value(self.pressure_vars['b_micro_per_c'])}",
                f"Basinc backend karsilastirmasi: {self.pressure_backend_comparison_var.get()}",
                f"Basinc kontrol tablosu: {self.pressure_control_table_var.get()}",
                f"Su sicaklik degisimi dT = Tilk - Tson (degC): {self._format_var_value(self.pressure_vars['delta_t_c'])}",
                f"Fiili basinc degisimi Pa = Pilk - Pson (bar): {self._format_var_value(self.pressure_vars['actual_pressure_change_bar'])}",
                f"B helper modu: {'Acik' if self.use_b_helper_var.get() else 'Kapali'}",
                f"Celik alpha (10^-6 / degC): {self._format_var_value(self.b_helper_vars['steel_alpha_micro_per_c'])}",
                f"Su beta (10^-6 / degC): {self._format_var_value(self.b_helper_vars['water_beta_micro_per_c'])}",
                "",
                "Operasyon Kontrol Noktalari",
                f"Kontrol ozeti: {self.check_summary_var.get()}",
            ]
        )
        lines.extend(self._checked_control_lines())
        lines.extend(
            [
                "",
                "Pig Hiz Hesabi",
                f"Pig modu: {self.pig_mode_var.get().strip() or '-'}",
                f"Mesafe (m): {self._format_var_value(self.field_vars['pig_distance_m'])}",
                f"Varis suresi (dakika): {self._format_var_value(self.field_vars['pig_travel_time_min'])}",
                f"Pig hizi (m/sn): {self._format_var_value(self.field_vars['pig_speed_m_per_s'])}",
                f"Pig hizi (km/sa): {self._format_var_value(self.field_vars['pig_speed_km_per_h'])}",
                f"Pig hiz durumu: {self.pig_status_var.get()}",
                "",
                "Nihai Karar",
                f"Baslik: {self.decision_title_var.get()}",
                f"Durum: {self.decision_status_var.get()}",
                f"Ozet: {self.decision_summary_var.get()}",
                "",
                "Oturum Sonuclari",
            ]
        )
        if self.report_entries:
            lines.extend(self.report_entries)
        else:
            lines.append("Kaydedilecek sonuc yok.")
        lines.extend(
            [
                "",
                "Not",
                "Bu rapor nihai saha karari icin ASME B31.8 ve proje proseduru ile birlikte degerlendirilmelidir.",
                "Bu cikti dT = Tilk - Tson ve Pa = Pilk - Pson isaret tanimi ile hazirlanmistir.",
            ]
        )
        return "\n".join(lines) + "\n"

    def _build_input_snapshot(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "saved_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "app_version": APP_VERSION,
            "active_tab": self._active_tab_key(),
            "water_backend_option": self.water_backend_var.get(),
            "geometry": {key: variable.get() for key, variable in self.geometry_vars.items()},
            "section_profile": {key: variable.get() for key, variable in self.section_profile_vars.items()},
            "geometry_catalog": {key: variable.get() for key, variable in self.geometry_catalog_vars.items()},
            "material_grade": self.material_grade_var.get(),
            "location_class": self.location_class_var.get(),
            "pump_location": self.pump_location_var.get(),
            "air": {key: variable.get() for key, variable in self.air_vars.items()},
            "pressure": {key: variable.get() for key, variable in self.pressure_vars.items()},
            "field": {key: variable.get() for key, variable in self.field_vars.items()},
            "helper": {key: variable.get() for key, variable in self.b_helper_vars.items()},
            "modes": {
                "air_a_mode": self.air_a_mode_var.get(),
                "pressure_a_mode": self.pressure_a_mode_var.get(),
                "pressure_b_mode": self.pressure_b_mode_var.get(),
                "air_a_reference": self.air_a_reference_var.get(),
                "pressure_a_reference": self.pressure_a_reference_var.get(),
                "pressure_b_reference": self.pressure_b_reference_var.get(),
                "k_preset": self.k_preset_var.get(),
                "steel_preset": self.steel_preset_var.get(),
                "pig_mode": self.pig_mode_var.get(),
            },
            "checks": {key: variable.get() for key, variable in self.control_check_vars.items()},
            "geometry_segments": [
                {
                    "outside_diameter_mm": f"{segment_info['pipe'].outside_diameter_mm:.6f}",
                    "wall_thickness_mm": f"{segment_info['pipe'].wall_thickness_mm:.6f}",
                    "length_m": f"{segment_info['pipe'].length_m:.6f}",
                    "nps_label": str(segment_info["nps_label"]),
                    "schedule_label": str(segment_info["schedule_label"]),
                }
                for segment_info in self.geometry_segments
            ],
        }

    def _apply_input_snapshot(self, payload: dict[str, object]) -> None:
        geometry = payload.get("geometry", {})
        if isinstance(geometry, dict):
            for key, variable in self.geometry_vars.items():
                variable.set(str(geometry.get(key, "")))
        section_profile = payload.get("section_profile", {})
        if isinstance(section_profile, dict):
            for key, variable in self.section_profile_vars.items():
                variable.set(str(section_profile.get(key, "")))
        geometry_catalog = payload.get("geometry_catalog", {})
        if isinstance(geometry_catalog, dict):
            for key, variable in self.geometry_catalog_vars.items():
                variable.set(str(geometry_catalog.get(key, "")))

        self.material_grade_var.set(str(payload.get("material_grade", "")))
        self.location_class_var.set(str(payload.get("location_class", self.location_class_var.get())))
        self.pump_location_var.set(str(payload.get("pump_location", "")))

        air = payload.get("air", {})
        if isinstance(air, dict):
            for key, variable in self.air_vars.items():
                variable.set(str(air.get(key, "")))
        pressure = payload.get("pressure", {})
        if isinstance(pressure, dict):
            for key, variable in self.pressure_vars.items():
                variable.set(str(pressure.get(key, "")))
        field = payload.get("field", {})
        if isinstance(field, dict):
            for key, variable in self.field_vars.items():
                variable.set(str(field.get(key, "")))
        helper = payload.get("helper", {})
        if isinstance(helper, dict):
            for key, variable in self.b_helper_vars.items():
                variable.set(str(helper.get(key, "")))

        modes = payload.get("modes", {})
        if isinstance(modes, dict):
            self.air_a_mode_var.set(str(modes.get("air_a_mode", self.air_a_mode_var.get())))
            self.pressure_a_mode_var.set(str(modes.get("pressure_a_mode", self.pressure_a_mode_var.get())))
            self.pressure_b_mode_var.set(str(modes.get("pressure_b_mode", self.pressure_b_mode_var.get())))
            self.air_a_reference_var.set(str(modes.get("air_a_reference", "")))
            self.pressure_a_reference_var.set(str(modes.get("pressure_a_reference", "")))
            self.pressure_b_reference_var.set(str(modes.get("pressure_b_reference", "")))
            self.k_preset_var.set(str(modes.get("k_preset", self.k_preset_var.get())))
            self.steel_preset_var.set(str(modes.get("steel_preset", self.steel_preset_var.get())))
            self.pig_mode_var.set(str(modes.get("pig_mode", self.pig_mode_var.get())))

        checks = payload.get("checks", {})
        if isinstance(checks, dict):
            for key, variable in self.control_check_vars.items():
                variable.set(bool(checks.get(key, False)))

        self.water_backend_var.set(str(payload.get("water_backend_option", self._default_water_backend_option_label())))

        self.geometry_segments.clear()
        geometry_segments = payload.get("geometry_segments", [])
        if isinstance(geometry_segments, list):
            for segment_payload in geometry_segments:
                if not isinstance(segment_payload, dict):
                    continue
                try:
                    pipe = PipeSection(
                        outside_diameter_mm=float(segment_payload["outside_diameter_mm"]),
                        wall_thickness_mm=float(segment_payload["wall_thickness_mm"]),
                        length_m=float(segment_payload["length_m"]),
                    )
                except (KeyError, TypeError, ValueError, ValidationError):
                    continue
                self.geometry_segments.append(
                    {
                        "pipe": pipe,
                        "nps_label": str(segment_payload.get("nps_label", "-")),
                        "schedule_label": str(segment_payload.get("schedule_label", "Elle giris")),
                    }
                )

        self._on_air_a_mode_changed()
        self._on_pressure_a_mode_changed()
        self._apply_b_helper_mode()
        self._on_water_backend_changed()
        self._refresh_segment_tree()
        self._refresh_geometry_summary()
        self._refresh_control_table_summaries()
        self._update_check_summary()
        self._update_pig_limit_hint()

        active_tab = str(payload.get("active_tab", "air"))
        if active_tab == "pressure":
            self.notebook.select(1)
        elif active_tab == "field":
            self.notebook.select(2)
        else:
            self.notebook.select(0)
        self._on_tab_changed()

    def _save_input_snapshot(self) -> None:
        initial_name = f"hidrostatik_test_girdileri_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        file_path = filedialog.asksaveasfilename(
            title="Hidrostatik Test Girdilerini Kaydet",
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
            initialfile=initial_name,
        )
        if not file_path:
            return
        try:
            Path(file_path).write_text(
                json.dumps(self._build_input_snapshot(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            self._set_banner(f"Girdiler kaydedilemedi: {exc}", "error")
            messagebox.showerror("Hata", f"Girdiler kaydedilemedi: {exc}")
            return
        self._set_banner("Girdiler basariyla kaydedildi.", "success")
        messagebox.showinfo("Kaydedildi", f"Girdiler kaydedildi:\n{file_path}")

    def _load_input_snapshot(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Hidrostatik Test Girdilerini Yukle",
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
        )
        if not file_path:
            return
        try:
            payload = json.loads(Path(file_path).read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Girdi dosyasi nesne yapisinda degil.")
            self._apply_input_snapshot(payload)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            self._set_banner(f"Girdiler yuklenemedi: {exc}", "error")
            messagebox.showerror("Hata", f"Girdiler yuklenemedi: {exc}")
            return
        self._set_banner("Girdiler basariyla yuklendi.", "success")
        messagebox.showinfo("Yuklendi", f"Girdiler yuklendi:\n{file_path}")

    def _save_report(self) -> None:
        initial_name = f"hidrostatik_test_raporu_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        file_path = filedialog.asksaveasfilename(
            title="Hidrostatik Test Raporunu Kaydet",
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
            initialfile=initial_name,
        )
        if not file_path:
            return

        try:
            Path(file_path).write_text(self._build_report_text(), encoding="utf-8")
        except OSError as exc:
            self._set_banner(f"Rapor kaydedilemedi: {exc}", "error")
            messagebox.showerror("Hata", f"Rapor kaydedilemedi: {exc}")
            return

        self._set_banner("Rapor basariyla kaydedildi.", "success")
        messagebox.showinfo("Kaydedildi", f"Rapor kaydedildi:\n{file_path}")

def main() -> None:
    install_exception_handler()
    root = tk.Tk()
    style = ttk.Style()
    if "vista" in style.theme_names():
        style.theme_use("vista")
    HydrostaticTestApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

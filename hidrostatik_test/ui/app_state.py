from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING
from pathlib import Path

from ..app_metadata import APP_TITLE, APP_VERSION
from ..config import FIELD_CHECK_DEFINITIONS
from ..domain import (
    get_available_water_property_backends,
    get_location_class_options,
)
from ..domain.hydrotest_core import WELDED_PIPE_K
from ..domain.operations import get_pig_speed_limit_options
from ..data.botas_reference_table import (
    BOTAS_REFERENCE_OPTION_LABEL,
    describe_botas_reference_table_range,
)
from ..data.gail_reference_table import (
    GAIL_REFERENCE_OPTION_LABEL,
    describe_gail_reference_table_range,
)
from ..services.updater import UpdateInfo

if TYPE_CHECKING:
    from .app_main import HydrostaticTestApp

AUTO_A_MODE = "Otomatik"
TABLE_A_MODE = "Tablo"
REFERENCE_A_MODE = TABLE_A_MODE
MANUAL_A_MODE = "Manuel"
AUTO_B_MODE = "Otomatik"
TABLE_B_MODE = "Tablo"
REFERENCE_B_MODE = TABLE_B_MODE
MANUAL_B_MODE = "Manuel"
DEFAULT_DECISION_TITLE = "Henuz degerlendirme yapilmadi"
DEFAULT_DECISION_STATUS = "BEKLIYOR"
DEFAULT_DECISION_SUMMARY = (
    "Girdileri tamamlayip ilgili testi calistirdiginizda nihai karar burada gosterilecek."
)


class AppStateMixin:
    """Application state initialization mixin."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"{APP_TITLE} v{APP_VERSION}")
        self._configure_window_geometry()
        self.ui_style = ttk.Style(self.root)
        self._configure_input_styles()

        self.geometry_vars = {
            "outside_diameter_mm": tk.StringVar(),
            "wall_thickness_mm": tk.StringVar(),
            "length_m": tk.StringVar(),
        }
        self.section_profile_vars = {
            "highest_elevation_m": tk.StringVar(),
            "lowest_elevation_m": tk.StringVar(),
            "start_elevation_m": tk.StringVar(),
            "end_elevation_m": tk.StringVar(),
            "design_pressure_bar": tk.StringVar(),
            "smys_mpa": tk.StringVar(),
        }
        self.ambient_temp_var = tk.StringVar()
        self.geometry_catalog_vars = {
            "size_option": tk.StringVar(),
            "schedule_option": tk.StringVar(),
        }
        self.material_grade_var = tk.StringVar()
        self.location_class_var = tk.StringVar(value=get_location_class_options()[0])
        self.pump_location_var = tk.StringVar()
        self.air_vars = {
            "temperature_c": tk.StringVar(),
            "pressure_bar": tk.StringVar(),
            "a_micro_per_bar": tk.StringVar(),
            "pressure_rise_bar": tk.StringVar(value="1.0"),
            "k_factor": tk.StringVar(value=f"{WELDED_PIPE_K:.2f}"),
            "actual_added_water_m3": tk.StringVar(),
        }
        self.pv_vars = {
            "total_pressure_rise_bar": tk.StringVar(),
            "total_water_added_m3": tk.StringVar(),
        }
        self.pv_result_var = tk.StringVar(value="Basinc-hacim %0.2 esik kontrolu henuz yapilmadi.")
        self.thermal_records: list[tuple[str, str]] = []
        self.thermal_timestamp_var = tk.StringVar()
        self.thermal_pipe_temp_var = tk.StringVar()
        self.thermal_result_var = tk.StringVar(
            value="24 saatlik termal dengeleme ve 0.5 degC son iki ortalama kontrolu henuz yapilmadi."
        )
        self.pressure_vars = {
            "temperature_c": tk.StringVar(),
            "pressure_bar": tk.StringVar(),
            "a_micro_per_bar": tk.StringVar(),
            "b_micro_per_c": tk.StringVar(),
            "delta_t_c": tk.StringVar(),
            "actual_pressure_change_bar": tk.StringVar(),
        }
        self.field_vars = {
            "pig_distance_m": tk.StringVar(),
            "pig_travel_time_min": tk.StringVar(),
            "pig_speed_m_per_s": tk.StringVar(),
            "pig_speed_km_per_h": tk.StringVar(),
        }
        self.depr_records: list[tuple[str, str, str, str]] = []
        self.depr_stage_label_var = tk.StringVar()
        self.depr_start_pressure_var = tk.StringVar()
        self.depr_end_pressure_var = tk.StringVar()
        self.depr_hold_time_var = tk.StringVar()
        self.depr_result_var = tk.StringVar(
            value="Basinc dusurme ve bosaltma kademeleri henuz degerlendirilmedi."
        )
        self.air_a_mode_var = tk.StringVar(value=AUTO_A_MODE)
        self.pressure_a_mode_var = tk.StringVar(value=AUTO_A_MODE)
        self.pressure_b_mode_var = tk.StringVar(value=AUTO_B_MODE)
        self.pig_mode_var = tk.StringVar(value=get_pig_speed_limit_options()[0])
        self.air_a_reference_var = tk.StringVar()
        self.pressure_a_reference_var = tk.StringVar()
        self.pressure_b_reference_var = tk.StringVar()
        self.k_preset_var = tk.StringVar(value="Kaynakli boru - 1.02")
        self.steel_preset_var = tk.StringVar(value="Karbon celik - 12.0")
        self.use_b_helper_var = tk.BooleanVar(value=True)
        self.b_helper_vars = {
            "steel_alpha_micro_per_c": tk.StringVar(value="12.0"),
            "water_beta_micro_per_c": tk.StringVar(),
        }
        self.banner_var = tk.StringVar(
            value=(
                "Akis: geometriyi girin, katsayilari kontrol edin ve ilgili testi degerlendirin. "
                "Helper aciksa B otomatik uretilecek, A ise gerektiginde yeniden hesaplanacaktir."
            )
        )
        self.section_feedback_vars = {
            "geometry": tk.StringVar(),
            "air": tk.StringVar(),
            "pressure": tk.StringVar(),
            "field": tk.StringVar(),
        }
        self.geometry_details_visible_var = tk.BooleanVar(value=False)
        self.side_panel_visible_var = tk.BooleanVar(value=True)
        self.help_notes_visible_var = tk.BooleanVar(value=False)
        self.control_check_vars = {
            key: tk.BooleanVar(value=False) for key, _label, _reference in FIELD_CHECK_DEFINITIONS
        }
        self.live_notice_var = tk.StringVar(value="Canli kontrol hazir. Girdiler izleniyor.")
        self.geometry_summary_var = tk.StringVar(
            value="Geometri girildiginde ic cap, ic yaricap ve hacim ozeti burada gosterilir."
        )
        self.segment_summary_var = tk.StringVar(
            value="Segmentasyon kullanilmazsa ustteki geometri alanlari tek boru kesiti olarak kullanilir."
        )
        self.workflow_hint_var = tk.StringVar()
        self.workflow_steps_var = tk.StringVar()
        self.helper_mode_summary_var = tk.StringVar()
        self.reference_option_labels = (
            BOTAS_REFERENCE_OPTION_LABEL,
            GAIL_REFERENCE_OPTION_LABEL,
        )
        self.water_backend_infos = tuple(
            info for info in get_available_water_property_backends() if info.distribution_ready
        )
        self.water_backend_option_map = {
            self._format_backend_option_label(info): info.key for info in self.water_backend_infos
        }
        self.water_backend_var = tk.StringVar(value=self._default_water_backend_option_label())
        self.water_backend_summary_var = tk.StringVar()
        self.air_backend_comparison_var = tk.StringVar(
            value="Hava testi icin backend karsilastirmasi henuz yapilmadi."
        )
        self.pressure_backend_comparison_var = tk.StringVar(
            value="Basinc testi icin backend karsilastirmasi henuz yapilmadi."
        )
        self.active_backend_comparison_var = tk.StringVar(
            value="Aktif sekme icin backend karsilastirmasi henuz yapilmadi."
        )
        self.botas_reference_range_text = describe_botas_reference_table_range()
        self.gail_reference_range_text = describe_gail_reference_table_range()
        self.air_control_table_var = tk.StringVar()
        self.pressure_control_table_var = tk.StringVar()
        self.active_control_table_var = tk.StringVar()
        self.section_pressure_summary_var = tk.StringVar(
            value=(
                "Min/max kotlar, dizayn basinci, API 5L PSL2 malzeme kalitesi, SMYS ve Location Class secildiginde "
                "pompa noktasindaki minimum/maksimum izlenen basinc penceresi burada hesaplanir."
            )
        )
        self.section_pressure_status_var = tk.StringVar(value="BEKLIYOR")
        self.section_pressure_status_detail_var = tk.StringVar(
            value="Test bolumu profili tamamlandiginda basinc penceresi burada renkli olarak yorumlanir."
        )
        self.section_pressure_logic_var = tk.StringVar(
            value="Mantik: yuksek noktada minimum test basinci korunur, dusuk noktada 100% SMYS limiti asilmaz."
        )
        self.section_pressure_window_var = tk.StringVar(
            value="Aktif pompa noktasi secildiginde minimum ve maksimum izleme penceresi burada gosterilir."
        )
        self.air_detail_report_var = tk.StringVar()
        self.pressure_detail_report_var = tk.StringVar()
        self.field_detail_report_var = tk.StringVar()
        self.active_detail_report_var = tk.StringVar()
        self.visual_schema_var = tk.StringVar(
            value="Canli sema aktif sekmeye gore guncelenir. Ustteki kutulara tiklayarak sekme degistirebilirsiniz."
        )
        self.schema_status_var = tk.StringVar(value="BEKLIYOR")
        self._evaluation_fresh: dict[str, bool] = {"air": False, "pressure": False, "field": False}
        self.update_download_summary_var = tk.StringVar()
        self.pig_limit_var = tk.StringVar()
        self.pig_status_var = tk.StringVar(value="Pig hiz hesabi henuz yapilmadi.")
        self.pig_summary_var = tk.StringVar(
            value="Mesafe ve sure girildiginde pig hizi m/sn ve km/sa olarak burada gosterilir."
        )
        self.input_panel_title_var = tk.StringVar(value="Aktif test girdileri solda gosterilir.")
        self.check_summary_var = tk.StringVar()
        self.check_progress_var = tk.DoubleVar(value=0.0)
        self.decision_title_var = tk.StringVar(value=DEFAULT_DECISION_TITLE)
        self.decision_status_var = tk.StringVar(value=DEFAULT_DECISION_STATUS)
        self.decision_summary_var = tk.StringVar(value=DEFAULT_DECISION_SUMMARY)
        self.update_status_var = tk.StringVar(value=f"Surum {APP_VERSION} aktif. Guncelleme henuz kontrol edilmedi.")
        self.update_detail_var = tk.StringVar(
            value="Acilista otomatik kontrol yapilir. Isterseniz elle de guncelleme kontrolu baslatabilirsiniz."
        )
        self.update_download_dir_var = tk.StringVar(value=str(self._default_update_download_dir()))
        self.coefficient_states = {
            "air_a": "empty",
            "pressure_a": "empty",
            "pressure_b": "empty",
        }
        self.coefficient_status_vars = {
            "air_a": tk.StringVar(value="Bekleniyor"),
            "pressure_a": tk.StringVar(value="Bekleniyor"),
            "pressure_b": tk.StringVar(value="Bekleniyor"),
        }
        self.coefficient_source_vars = {
            "air_a": tk.StringVar(value="BEKLIYOR"),
            "pressure_a": tk.StringVar(value="BEKLIYOR"),
            "pressure_b": tk.StringVar(value="BEKLIYOR"),
        }
        self.coefficient_source_badges: dict[str, tk.Label] = {}
        self.inline_coefficient_source_badges: dict[str, tk.Label] = {}
        self.progress_buttons: dict[str, tk.Button] = {}
        self.progress_button_idle_texts: dict[str, str] = {}
        self.progress_button_reset_jobs: dict[str, str] = {}
        self.progress_button_busy: set[str] = set()
        self._programmatic_coefficient_updates: set[str] = set()
        self.entry_widgets: dict[str, ttk.Entry] = {}
        self.input_widgets: dict[str, tk.Widget] = {}
        self.field_meta: dict[str, dict[str, str | bool]] = {}
        self.field_message_vars: dict[str, tk.StringVar] = {}
        self.field_message_labels: dict[str, tk.Widget] = {}
        self.field_validation_levels: dict[str, str] = {}
        self.touched_fields: set[str] = set()
        self.report_entries: list[str] = []
        self.geometry_segments: list[dict[str, object]] = []
        self.help_note_widgets: list[tk.Widget] = []
        self.latest_update_info: UpdateInfo | None = None
        self.update_check_in_progress = False
        self.update_install_in_progress = False
        self._active_scroll_canvas: tk.Canvas | None = None
        self.input_wraplength = 440
        self.input_subframe_wraplength = 340
        self.workspace_wraplength = 560
        self.detail_wraplength = 360

        self._build_menu()
        self._build_ui()
        self._register_traces()
        self._bind_shortcuts()
        self._refresh_coefficient_statuses()
        self._refresh_geometry_summary()
        self._update_workflow_hint()
        self._update_water_backend_summary()
        self._sync_backend_comparison_summary()
        self._refresh_control_table_summaries()
        self._update_contextual_actions()
        self._on_air_a_mode_changed()
        self._on_pressure_a_mode_changed()
        self._apply_b_helper_mode()
        self._refresh_choice_validation_states()
        self._refresh_update_download_summary()
        self._apply_geometry_details_visibility()
        self._apply_side_panel_visibility()
        self._apply_help_notes_visibility()
        self._update_check_summary()
        self._update_pig_limit_hint()
        self._refresh_visual_schema()
        self.root.after(1200, self._check_for_updates_on_startup)


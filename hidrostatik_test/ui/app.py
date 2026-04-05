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
from ..domain import (
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
FIELD_CHECK_DEFINITIONS = (
    ("ambient_temp", "Dolum sirasinda hava sicakligi +2 degC limitine gore kontrol edildi", "10.1"),
    ("temp_probes", "Boru ve toprak sicaklik problari uygun yerlere yerlestirildi", "10.4"),
    ("fill_air_entry", "Su dolumu sirasinda sisteme hava girmesi engellendi", "11.2"),
    ("fill_records", "Doldurulan su hacmi ve sicakligi saatlik olarak kaydedildi", "11.3-11.4"),
    ("thermal_balance", "Minimum 24 saat termal dengeleme ve 0.5 degC kosulu kontrol edildi", "12"),
    ("air_content_limit", "Hava icerik testi %6 kabul sinirina gore teyit edildi", "13"),
    ("pressurization_volume", "14.2 icin basinc-hacim ve %0.2 ilave su limiti izlendi", "14.2"),
    ("two_hour_hold", "14.3 icin 2 saat bekleme ve 15 dakikalik okumalar alindi", "14.3"),
    ("pressure_records", "24 saatlik basinc ve sicaklik kayitlari duzenli tutuldu", "15.1"),
    ("depressurize_discharge", "Basinc dusurme ve bosaltma islemleri kontrollu ve raporlu yapildi", "16-17"),
)


class HydrostaticTestApp:
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
            value="Canli sema aktif sekmeye gore guncellenir. Ustteki kutulara tiklayarak sekme degistirebilirsiniz."
        )
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

    def _build_menu(self) -> None:
        menu_bar = tk.Menu(self.root)

        file_menu = tk.Menu(menu_bar, tearoff=False)
        file_menu.add_command(label="Girdileri Kaydet", command=self._save_input_snapshot)
        file_menu.add_command(label="Girdileri Yukle", command=self._load_input_snapshot)
        file_menu.add_separator()
        file_menu.add_command(label="Raporu Kaydet", command=self._save_report)
        file_menu.add_separator()
        file_menu.add_command(label="Cikis", command=self.root.destroy)
        menu_bar.add_cascade(label="Dosya", menu=file_menu)

        calc_menu = tk.Menu(menu_bar, tearoff=False)
        backend_menu = tk.Menu(calc_menu, tearoff=False)
        for option_label in self.water_backend_option_map.keys():
            backend_menu.add_radiobutton(
                label=option_label,
                variable=self.water_backend_var,
                value=option_label,
                command=self._on_water_backend_changed,
            )
        calc_menu.add_cascade(label="Su Ozelligi Backend'i", menu=backend_menu)
        calc_menu.add_separator()
        calc_menu.add_command(label="Backendleri Karsilastir", command=self._compare_active_backend)
        menu_bar.add_cascade(label="Hesap", menu=calc_menu)

        report_menu = tk.Menu(menu_bar, tearoff=False)
        report_menu.add_command(label="Raporu Kaydet", command=self._save_report)
        report_menu.add_command(label="Sonuclari Temizle", command=self._clear_results)
        menu_bar.add_cascade(label="Rapor", menu=report_menu)

        update_menu = tk.Menu(menu_bar, tearoff=False)
        update_menu.add_command(label="Guncelleme Kontrol Et", command=self._check_for_updates_manually)
        update_menu.add_command(label="Guncellemeyi Uygula", command=self._apply_available_update)
        update_menu.add_command(label="Indirme Klasoru Sec", command=self._choose_update_download_dir)
        update_menu.add_separator()
        update_menu.add_command(label="Release Sayfasini Ac", command=self._open_release_page)
        menu_bar.add_cascade(label="Guncelleme", menu=update_menu)

        about_menu = tk.Menu(menu_bar, tearoff=False)
        about_menu.add_command(label="Uygulama Hakkinda", command=self._show_about_dialog)
        menu_bar.add_cascade(label="Hakkinda", menu=about_menu)

        self.root.configure(menu=menu_bar)

    def _configure_window_geometry(self) -> None:
        screen_width = max(self.root.winfo_screenwidth(), 1280)
        screen_height = max(self.root.winfo_screenheight(), 900)
        width = min(screen_width - 120, max(1440, int(screen_width * 0.84)))
        height = min(screen_height - 100, max(920, int(screen_height * 0.86)))
        x_offset = max((screen_width - width) // 2, 0)
        y_offset = max((screen_height - height) // 2, 0)
        self.root.geometry(f"{width}x{height}+{x_offset}+{y_offset}")
        self.root.minsize(1280, 840)

    def _default_update_download_dir(self) -> Path:
        downloads_dir = Path.home() / "Downloads" / "HidrostatikTestUpdates"
        return downloads_dir

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

    def _bind_mousewheel(self, canvas: tk.Canvas) -> None:
        self._active_scroll_canvas = canvas
        self.root.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, canvas: tk.Canvas) -> None:
        if self._active_scroll_canvas is canvas:
            self._active_scroll_canvas = None
        self.root.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event: tk.Event) -> None:
        if self._active_scroll_canvas is None:
            return
        if event.delta == 0:
            return
        self._active_scroll_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _create_scrollable_region(
        self,
        parent: tk.Misc,
        *,
        padding: int | tuple[int, ...] = 0,
    ) -> tuple[ttk.Frame, ttk.Frame, tk.Canvas]:
        wrapper = ttk.Frame(parent)
        wrapper.columnconfigure(0, weight=1)
        wrapper.rowconfigure(0, weight=1)
        canvas = tk.Canvas(wrapper, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(wrapper, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        content = ttk.Frame(canvas, padding=padding)
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind(
            "<Configure>",
            lambda _event, target_canvas=canvas: target_canvas.configure(scrollregion=target_canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda event, target_canvas=canvas, item_id=window_id: target_canvas.itemconfigure(item_id, width=event.width),
        )
        canvas.bind("<Enter>", lambda _event, target_canvas=canvas: self._bind_mousewheel(target_canvas))
        canvas.bind("<Leave>", lambda _event, target_canvas=canvas: self._unbind_mousewheel(target_canvas))
        return wrapper, content, canvas

    def _create_scrollable_tab(self, title: str) -> ttk.Frame:
        wrapper, content, _canvas = self._create_scrollable_region(self.notebook, padding=16)
        content.columnconfigure(0, weight=1)
        self.notebook.add(wrapper, text=title)
        return content

    def _toggle_geometry_details(self) -> None:
        self.geometry_details_visible_var.set(not self.geometry_details_visible_var.get())
        self._apply_geometry_details_visibility()

    def _toggle_side_panel_visibility(self) -> None:
        self.side_panel_visible_var.set(not self.side_panel_visible_var.get())
        self._apply_side_panel_visibility()

    def _position_content_sashes(self) -> None:
        if not hasattr(self, "content_pane") or not hasattr(self, "side_panel"):
            return
        panes = self.content_pane.panes()
        if not panes:
            return
        self.root.update_idletasks()
        total_width = max(self.root.winfo_width(), 1280)
        left_width = max(430, int(total_width * 0.31))
        if len(panes) >= 2:
            self.content_pane.sashpos(0, left_width)
        if len(panes) >= 3 and str(self.side_panel) in {str(pane) for pane in panes}:
            right_width = max(left_width + 420, int(total_width * 0.72))
            self.content_pane.sashpos(1, right_width)

    def _apply_side_panel_visibility(self) -> None:
        if not hasattr(self, "content_pane") or not hasattr(self, "side_panel") or not hasattr(self, "side_panel_toggle_button"):
            return
        visible = self.side_panel_visible_var.get()
        pane_names = {str(pane) for pane in self.content_pane.panes()}
        side_name = str(self.side_panel)
        if visible and side_name not in pane_names:
            self.content_pane.add(self.side_panel, weight=2)
            self._position_content_sashes()
        elif not visible and side_name in pane_names:
            self.content_pane.forget(self.side_panel)
        self.side_panel_toggle_button.configure(text="Detay Panelini Gizle" if visible else "Detay Panelini Goster")

    def _register_help_note(self, widget: tk.Widget) -> tk.Widget:
        self.help_note_widgets.append(widget)
        return widget

    def _toggle_help_notes_visibility(self) -> None:
        self.help_notes_visible_var.set(not self.help_notes_visible_var.get())
        self._apply_help_notes_visibility()

    def _apply_help_notes_visibility(self) -> None:
        if not hasattr(self, "help_notes_toggle_button"):
            return
        visible = self.help_notes_visible_var.get()
        self.help_notes_toggle_button.configure(text="Bilgi Notlarini Gizle" if visible else "Bilgi Notlarini Goster")
        for widget in self.help_note_widgets:
            if visible:
                widget.grid()
            else:
                widget.grid_remove()

    def _apply_geometry_details_visibility(self) -> None:
        if not hasattr(self, "geometry_segment_frame") or not hasattr(self, "geometry_toggle_button"):
            return
        visible = self.geometry_details_visible_var.get()
        self.geometry_toggle_button.configure(text="Detaylari Gizle" if visible else "Detaylari Goster")
        if visible:
            self.geometry_segment_frame.grid(row=6, column=0, columnspan=6, sticky="ew", pady=(8, 0))
            self.geometry_segment_summary_label.grid(row=7, column=0, columnspan=6, sticky="w", pady=(6, 0))
        else:
            self.geometry_segment_frame.grid_remove()
            self.geometry_segment_summary_label.grid_remove()
        self._refresh_visual_schema()

    def _select_tab_by_key(self, tab_key: str) -> None:
        tab_index = {"air": 0, "pressure": 1, "field": 2}.get(tab_key)
        if tab_index is None or not hasattr(self, "notebook"):
            return
        self.notebook.select(tab_index)
        self._on_tab_changed()

    def _visual_segment_payload(self) -> list[dict[str, float]]:
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

    def _refresh_visual_schema(self) -> None:
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
                text=f"Checklist: {checked_count}/{len(FIELD_CHECK_DEFINITIONS)} | Mesafe + sure -> hiz",
                fill="#16365D",
                font=("Segoe UI", 9, "bold"),
            )
            canvas.create_text(250, 178, text=f"Anlik hiz: {pig_speed} m/sn", fill="#35506B", font=("Segoe UI", 9))
            self.visual_schema_var.set(
                "Saha kontrol akisi gosteriliyor. "
                f"Isaretlenen kontrol noktasi: {checked_count}/{len(FIELD_CHECK_DEFINITIONS)}. "
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

    def _build_ui(self) -> None:
        scroll_root, container, _canvas = self._create_scrollable_region(self.root, padding=16)
        scroll_root.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(3, weight=1)

        self.intro_label = self._register_help_note(ttk.Label(
            container,
            text=(
                "Calisma alani hesap ve saha dogrulama girdileri icindir. Yardimci paneller sagdaki "
                "sekmelerde tutulur. Referans akisi "
                f"{SPEC_DOCUMENT_CODE} {SPEC_DOCUMENT_TITLE} ile hizalanmistir."
            ),
            wraplength=1180,
            justify="left",
        ))
        self.intro_label.grid(row=0, column=0, sticky="ew", pady=(0, 12))

        self.banner_label = tk.Label(
            container,
            textvariable=self.banner_var,
            anchor="w",
            justify="left",
            bg="#EEF4FF",
            fg="#16365D",
            padx=10,
            pady=8,
        )
        self.banner_label.grid(row=1, column=0, sticky="ew", pady=(0, 12))

        workspace_tools = ttk.Frame(container)
        workspace_tools.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        self.side_panel_toggle_button = ttk.Button(
            workspace_tools,
            text="Yan Paneli Gizle",
            command=self._toggle_side_panel_visibility,
        )
        self.side_panel_toggle_button.pack(side="left")
        self.help_notes_toggle_button = ttk.Button(
            workspace_tools,
            text="Bilgi Notlarini Goster",
            command=self._toggle_help_notes_visibility,
        )
        self.help_notes_toggle_button.pack(side="left", padx=(8, 0))
        ttk.Label(
            workspace_tools,
            text="Dar calisma modunda yardim panellerini gizleyip sadece giris alanlarini kullanabilirsiniz.",
            foreground="#35506B",
        ).pack(side="left", padx=(12, 0))

        content_pane = ttk.Panedwindow(container, orient="horizontal")
        content_pane.grid(row=3, column=0, sticky="nsew")
        self.content_pane = content_pane

        left_panel = ttk.Frame(content_pane, padding=(0, 0, 10, 0))
        left_panel.columnconfigure(0, weight=1)
        left_panel.rowconfigure(0, weight=1)
        content_pane.add(left_panel, weight=3)
        self.left_panel = left_panel

        center_panel = ttk.Frame(content_pane, padding=(0, 0, 10, 0))
        center_panel.columnconfigure(0, weight=1)
        center_panel.rowconfigure(0, weight=1)
        content_pane.add(center_panel, weight=5)
        self.center_panel = center_panel

        side_panel = ttk.Frame(content_pane)
        side_panel.columnconfigure(0, weight=1)
        side_panel.rowconfigure(1, weight=1)
        content_pane.add(side_panel, weight=3)
        self.side_panel = side_panel

        self._build_input_sidebar(left_panel)

        self.notebook = ttk.Notebook(center_panel)
        self.notebook.grid(row=0, column=0, sticky="nsew")
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        air_frame = self._create_scrollable_tab("Hava Icerik Testi")
        pressure_frame = self._create_scrollable_tab("Basinc Degisim Testi")
        field_frame = self._create_scrollable_tab("Saha Grubu")

        self._build_air_tab(air_frame)
        self._build_pressure_tab(pressure_frame)
        self._build_field_tab(field_frame)

        side_wrap = self.detail_wraplength

        decision_frame = ttk.LabelFrame(side_panel, text="Nihai Karar", padding=12)
        decision_frame.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        decision_frame.columnconfigure(1, weight=1)

        ttk.Label(
            decision_frame,
            textvariable=self.decision_title_var,
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="w")
        self.decision_status_label = tk.Label(
            decision_frame,
            textvariable=self.decision_status_var,
            bg="#EEF2FF",
            fg="#243B73",
            padx=12,
            pady=6,
            font=("Segoe UI", 10, "bold"),
        )
        self.decision_status_label.grid(row=0, column=1, sticky="e")
        tk.Label(
            decision_frame,
            textvariable=self.decision_summary_var,
            justify="left",
            anchor="w",
            wraplength=side_wrap,
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        self.side_notebook = ttk.Notebook(side_panel)
        self.side_notebook.grid(row=1, column=0, sticky="nsew")

        detail_tab = ttk.Frame(self.side_notebook, padding=8)
        detail_tab.columnconfigure(0, weight=1)
        detail_tab.rowconfigure(0, weight=1)
        self.side_notebook.add(detail_tab, text="Detay Raporu")

        status_tab = ttk.Frame(self.side_notebook, padding=8)
        status_tab.columnconfigure(0, weight=1)
        status_tab.rowconfigure(2, weight=1)
        self.side_notebook.add(status_tab, text="Karar ve Akis")

        session_tab = ttk.Frame(self.side_notebook, padding=8)
        session_tab.columnconfigure(0, weight=1)
        session_tab.rowconfigure(0, weight=1)
        self.side_notebook.add(session_tab, text="Kayit")

        detail_frame = ttk.LabelFrame(detail_tab, text="Detay Raporu", padding=12)
        detail_frame.grid(row=0, column=0, sticky="nsew")
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(0, weight=1)
        self.detail_report_text = ScrolledText(detail_frame, height=26, wrap="word")
        self.detail_report_text.grid(row=0, column=0, sticky="nsew")
        self.detail_report_text.insert(
            "end",
            "Aktif sekmedeki girdi, katsayi ve karar detayi burada canli olarak gosterilecek.\n",
        )
        self.detail_report_text.configure(state="disabled")

        visual_frame = ttk.LabelFrame(status_tab, text="Canli Sema", padding=12)
        visual_frame.grid(row=0, column=0, sticky="ew")
        visual_frame.columnconfigure(0, weight=1)
        self.visual_canvas = tk.Canvas(
            visual_frame,
            height=220,
            bg="#F8FAFD",
            highlightthickness=1,
            highlightbackground="#D6DCE8",
        )
        self.visual_canvas.grid(row=0, column=0, sticky="ew")
        ttk.Label(
            visual_frame,
            textvariable=self.visual_schema_var,
            wraplength=side_wrap,
            justify="left",
            foreground="#35506B",
        ).grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self._register_help_note(ttk.Label(
            visual_frame,
            text="Guncelleme islemleri menuden yonetilir. Indirme klasoru da Guncelleme menusu altindan secilir.",
            wraplength=side_wrap,
            justify="left",
            foreground="#35506B",
        )).grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(
            visual_frame,
            textvariable=self.update_download_summary_var,
            wraplength=side_wrap,
            justify="left",
            foreground="#35506B",
        ).grid(row=3, column=0, sticky="ew", pady=(8, 0))

        workflow_frame = ttk.LabelFrame(status_tab, text="Hizli Akis", padding=12)
        workflow_frame.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        workflow_frame.columnconfigure(0, weight=1)
        ttk.Label(
            workflow_frame,
            textvariable=self.workflow_hint_var,
            wraplength=side_wrap,
            justify="left",
        ).grid(row=0, column=0, sticky="ew")
        ttk.Label(
            workflow_frame,
            textvariable=self.live_notice_var,
            wraplength=side_wrap,
            justify="left",
            foreground="#35506B",
        ).grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self._register_help_note(tk.Label(
            workflow_frame,
            textvariable=self.workflow_steps_var,
            anchor="w",
            justify="left",
            bg="#F6F8FC",
            fg="#16365D",
            padx=10,
            pady=8,
        )).grid(row=2, column=0, sticky="ew", pady=(10, 0))
        workflow_actions = ttk.Frame(workflow_frame)
        workflow_actions.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        self.run_selected_button = self._create_progress_button(
            workflow_actions,
            key="run_selected",
            text="Aktif Testi Degerlendir",
            command=self._run_selected_test,
        )
        self.run_selected_button.pack(side="left")
        self.recalculate_button = self._create_progress_button(
            workflow_actions,
            key="recalculate",
            text="Katsayilari Yenile",
            command=self._recalculate_active_coefficients,
        )
        self.recalculate_button.pack(side="left", padx=(8, 0))
        self.clear_form_button = ttk.Button(
            workflow_actions,
            text="Aktif Formu Temizle",
            command=self._clear_active_form,
        )
        self.clear_form_button.pack(side="left", padx=(8, 0))

        coefficient_frame = ttk.LabelFrame(status_tab, text="Katsayi Durumu", padding=12)
        coefficient_frame.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        coefficient_frame.columnconfigure(1, weight=1)
        coefficient_frame.columnconfigure(2, weight=0)
        ttk.Label(coefficient_frame, text="Hava testi A").grid(row=0, column=0, sticky="w")
        ttk.Label(
            coefficient_frame,
            textvariable=self.coefficient_status_vars["air_a"],
            foreground="#8A6D3B",
        ).grid(row=0, column=1, sticky="w")
        self.coefficient_source_badges["air_a"] = self._create_source_badge(
            coefficient_frame,
            key="air_a",
            registry=self.coefficient_source_badges,
        )
        self.coefficient_source_badges["air_a"].grid(row=0, column=2, sticky="e", padx=(8, 0))
        ttk.Label(coefficient_frame, text="Basinc testi A").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Label(
            coefficient_frame,
            textvariable=self.coefficient_status_vars["pressure_a"],
            foreground="#8A6D3B",
        ).grid(row=1, column=1, sticky="w", pady=(6, 0))
        self.coefficient_source_badges["pressure_a"] = self._create_source_badge(
            coefficient_frame,
            key="pressure_a",
            registry=self.coefficient_source_badges,
        )
        self.coefficient_source_badges["pressure_a"].grid(row=1, column=2, sticky="e", padx=(8, 0), pady=(6, 0))
        ttk.Label(coefficient_frame, text="Basinc testi B").grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Label(
            coefficient_frame,
            textvariable=self.coefficient_status_vars["pressure_b"],
            foreground="#8A6D3B",
        ).grid(row=2, column=1, sticky="w", pady=(6, 0))
        self.coefficient_source_badges["pressure_b"] = self._create_source_badge(
            coefficient_frame,
            key="pressure_b",
            registry=self.coefficient_source_badges,
        )
        self.coefficient_source_badges["pressure_b"].grid(row=2, column=2, sticky="e", padx=(8, 0), pady=(6, 0))
        ttk.Label(
            coefficient_frame,
            textvariable=self.helper_mode_summary_var,
            wraplength=side_wrap,
            justify="left",
            foreground="#35506B",
        ).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Label(
            coefficient_frame,
            textvariable=self.water_backend_summary_var,
            wraplength=side_wrap,
            justify="left",
            foreground="#35506B",
        ).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        comparison_actions = ttk.Frame(coefficient_frame)
        comparison_actions.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        self.compare_backend_button = ttk.Button(
            comparison_actions,
            text="Backendleri Karsilastir",
            command=self._compare_active_backend,
        )
        self.compare_backend_button.pack(side="left")
        ttk.Label(
            coefficient_frame,
            textvariable=self.active_backend_comparison_var,
            wraplength=side_wrap,
            justify="left",
            foreground="#35506B",
        ).grid(row=6, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Label(coefficient_frame, text="A/B tablo karsilastirmasi").grid(
            row=7, column=0, sticky="w", pady=(10, 0)
        )
        ttk.Label(
            coefficient_frame,
            textvariable=self.active_control_table_var,
            wraplength=side_wrap,
            justify="left",
            foreground="#35506B",
        ).grid(row=8, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        results_frame = ttk.LabelFrame(session_tab, text="Oturum Kaydi", padding=12)
        results_frame.grid(row=0, column=0, sticky="nsew")
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(0, weight=1)

        self.results_text = ScrolledText(results_frame, height=22, wrap="word")
        self.results_text.grid(row=0, column=0, sticky="nsew")
        self.results_text.insert(
            "end",
            "Oturum sonuclari burada zaman damgasi ile listelenecek.\n"
            "Not: Bu panel bir karar ozeti degil, kayit gunlugudur.\n",
        )
        self.results_text.configure(state="disabled")

        results_actions = ttk.Frame(results_frame)
        results_actions.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(results_actions, text="Raporu Kaydet", command=self._save_report).pack(side="left")
        ttk.Button(results_actions, text="Sonuclari Temizle", command=self._clear_results).pack(
            side="left", padx=(8, 0)
        )
        self._show_active_input_panel()
        self._position_content_sashes()

    def _build_input_sidebar(self, parent: ttk.Frame) -> None:
        wrapper, content, _canvas = self._create_scrollable_region(parent, padding=0)
        wrapper.grid(row=0, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)

        sidebar_header = ttk.Frame(content)
        sidebar_header.grid(row=0, column=0, sticky="ew")
        sidebar_header.columnconfigure(0, weight=1)
        ttk.Label(
            sidebar_header,
            text="Girdi Paneli",
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            sidebar_header,
            textvariable=self.input_panel_title_var,
            wraplength=self.input_wraplength,
            justify="left",
            foreground="#35506B",
        ).grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self._register_help_note(ttk.Label(
            sidebar_header,
            text=(
                "Tum kullanici girisleri bu panelde toplanir. Orta bolmede sadece secili testin "
                "is akisi, sonuc ozetleri ve calisma kartlari gosterilir."
            ),
            wraplength=self.input_wraplength,
            justify="left",
            foreground="#35506B",
        )).grid(row=2, column=0, sticky="ew", pady=(8, 0))

        geometry_shell = ttk.Frame(content)
        geometry_shell.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        geometry_shell.columnconfigure(0, weight=1)
        self._build_geometry_input_panel(geometry_shell)

        ttk.Separator(content, orient="horizontal").grid(row=2, column=0, sticky="ew", pady=12)

        active_section = ttk.Frame(content)
        active_section.grid(row=3, column=0, sticky="ew")
        active_section.columnconfigure(0, weight=1)

        self.active_input_title_label = ttk.Label(
            active_section,
            text="Aktif test girdileri",
            font=("Segoe UI", 10, "bold"),
        )
        self.active_input_title_label.grid(row=0, column=0, sticky="w")
        ttk.Label(
            active_section,
            text="Sekme degistikce bu panel otomatik olarak ilgili girdi grubuna gecer.",
            wraplength=self.input_wraplength,
            justify="left",
            foreground="#35506B",
        ).grid(row=1, column=0, sticky="ew", pady=(4, 0))

        self.active_input_container = ttk.Frame(active_section)
        self.active_input_container.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.active_input_container.columnconfigure(0, weight=1)

        self.active_input_frames = {
            "air": ttk.Frame(self.active_input_container),
            "pressure": ttk.Frame(self.active_input_container),
            "field": ttk.Frame(self.active_input_container),
        }
        for frame in self.active_input_frames.values():
            frame.columnconfigure(0, weight=1)
            frame.grid(row=0, column=0, sticky="ew")

        self._build_air_input_panel(self.active_input_frames["air"])
        self._build_pressure_input_panel(self.active_input_frames["pressure"])
        self._build_field_input_panel(self.active_input_frames["field"])

    def _build_geometry_input_panel(self, parent: ttk.Frame) -> None:
        geometry_frame = ttk.LabelFrame(parent, text="Boru Kesiti", padding=8)
        geometry_frame.grid(row=0, column=0, sticky="ew")
        geometry_frame.columnconfigure(1, weight=1)
        geometry_frame.columnconfigure(3, weight=1)
        geometry_frame.columnconfigure(5, weight=1)

        ttk.Label(geometry_frame, text="ASME B36.10 NPS").grid(row=0, column=0, sticky="w", pady=6)
        self.pipe_size_combo = ttk.Combobox(
            geometry_frame,
            textvariable=self.geometry_catalog_vars["size_option"],
            state="readonly",
            values=get_pipe_size_options(),
            width=18,
        )
        self.pipe_size_combo.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=6)
        self.pipe_size_combo.bind("<<ComboboxSelected>>", self._on_pipe_size_selected)

        ttk.Label(geometry_frame, text="Schedule / Et kalinligi").grid(row=0, column=2, sticky="w", pady=6)
        self.pipe_schedule_combo = ttk.Combobox(
            geometry_frame,
            textvariable=self.geometry_catalog_vars["schedule_option"],
            state="readonly",
            values=(),
            width=18,
        )
        self.pipe_schedule_combo.grid(row=0, column=3, sticky="ew", padx=(0, 12), pady=6)
        ttk.Button(geometry_frame, text="Listeden Doldur", command=self._apply_catalog_selection).grid(
            row=0, column=4, sticky="w", pady=6
        )
        self.geometry_toggle_button = ttk.Button(
            geometry_frame,
            text="Detaylari Goster",
            command=self._toggle_geometry_details,
        )
        self.geometry_toggle_button.grid(row=0, column=5, sticky="e", pady=6)

        self._add_entry(
            geometry_frame,
            row=1,
            label="Dis cap (mm)",
            variable=self.geometry_vars["outside_diameter_mm"],
            field_key="geometry.outside_diameter_mm",
        )
        self._add_entry(
            geometry_frame,
            row=1,
            label="Et kalinligi (mm)",
            variable=self.geometry_vars["wall_thickness_mm"],
            field_key="geometry.wall_thickness_mm",
            column=2,
        )
        self._add_entry(
            geometry_frame,
            row=1,
            label="Hat uzunlugu (m)",
            variable=self.geometry_vars["length_m"],
            field_key="geometry.length_m",
            column=4,
        )

        profile_frame = ttk.LabelFrame(geometry_frame, text="Test Bolumu Profili ve Basinc Penceresi", padding=8)
        profile_frame.grid(row=2, column=0, columnspan=6, sticky="ew", pady=(6, 4))
        profile_frame.columnconfigure(1, weight=1)
        profile_frame.columnconfigure(3, weight=1)
        profile_frame.columnconfigure(4, weight=1)
        self._add_entry(
            profile_frame,
            row=0,
            label="En yuksek nokta kotu (m)",
            variable=self.section_profile_vars["highest_elevation_m"],
            field_key="geometry.highest_elevation_m",
        )
        self._add_entry(
            profile_frame,
            row=0,
            label="En dusuk nokta kotu (m)",
            variable=self.section_profile_vars["lowest_elevation_m"],
            field_key="geometry.lowest_elevation_m",
            column=2,
        )
        self._add_entry(
            profile_frame,
            row=1,
            label="Baslangic noktasi kotu (m)",
            variable=self.section_profile_vars["start_elevation_m"],
            field_key="geometry.start_elevation_m",
        )
        self._add_entry(
            profile_frame,
            row=1,
            label="Bitis noktasi kotu (m)",
            variable=self.section_profile_vars["end_elevation_m"],
            field_key="geometry.end_elevation_m",
            column=2,
        )
        self._add_entry(
            profile_frame,
            row=2,
            label="Dizayn basinci (bar)",
            variable=self.section_profile_vars["design_pressure_bar"],
            field_key="geometry.design_pressure_bar",
        )
        ttk.Label(profile_frame, text="Boru malzeme kalitesi").grid(row=2, column=2, sticky="w", pady=6)
        material_grade_container = ttk.Frame(profile_frame)
        material_grade_container.grid(row=2, column=3, sticky="ew", padx=(0, 12), pady=6)
        material_grade_container.columnconfigure(0, weight=1)
        self.material_grade_combo = ttk.Combobox(
            material_grade_container,
            textvariable=self.material_grade_var,
            state="readonly",
            values=get_api_5l_psl2_grade_options(),
            style="Hydro.neutral.TCombobox",
            width=28,
        )
        self.material_grade_combo.grid(row=0, column=0, sticky="ew")
        self._register_choice_widget(
            field_key="geometry.material_grade",
            widget=self.material_grade_combo,
            section="geometry",
            label="Boru malzeme kalitesi",
            required=True,
        )
        ttk.Label(
            material_grade_container,
            text="API 5L PSL2 kalite secildiginde SMYS otomatik doldurulur.",
            foreground="#6B7280",
            wraplength=self.input_subframe_wraplength,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))
        self._add_entry(
            profile_frame,
            row=3,
            label="SMYS (MPa)",
            variable=self.section_profile_vars["smys_mpa"],
            field_key="geometry.smys_mpa",
            column=0,
            readonly=True,
        )
        ttk.Label(profile_frame, text="Location Class").grid(row=3, column=2, sticky="w", pady=6)
        self.location_class_combo = ttk.Combobox(
            profile_frame,
            textvariable=self.location_class_var,
            state="readonly",
            values=get_location_class_options(),
            style="Hydro.neutral.TCombobox",
            width=28,
        )
        self.location_class_combo.grid(row=3, column=3, sticky="ew", padx=(0, 12), pady=6)
        self._register_choice_widget(
            field_key="geometry.location_class",
            widget=self.location_class_combo,
            section="geometry",
            label="Location Class",
            required=True,
        )
        ttk.Label(profile_frame, text="Pompa konumu").grid(row=4, column=0, sticky="w", pady=6)
        self.pump_location_combo = ttk.Combobox(
            profile_frame,
            textvariable=self.pump_location_var,
            state="readonly",
            values=get_pump_location_options(),
            style="Hydro.neutral.TCombobox",
            width=18,
        )
        self.pump_location_combo.grid(row=4, column=1, sticky="ew", padx=(0, 12), pady=6)
        self._register_choice_widget(
            field_key="geometry.pump_location",
            widget=self.pump_location_combo,
            section="geometry",
            label="Pompa konumu",
            required=True,
        )
        profile_visual_frame = ttk.LabelFrame(profile_frame, text="Kot Semasi", padding=6)
        profile_visual_frame.grid(row=0, column=4, rowspan=5, sticky="nsew", padx=(6, 0), pady=(0, 6))
        profile_visual_frame.columnconfigure(0, weight=1)
        profile_visual_frame.rowconfigure(0, weight=1)
        self.section_profile_canvas = tk.Canvas(
            profile_visual_frame,
            height=180,
            highlightthickness=0,
            bg="#FFFFFF",
        )
        self.section_profile_canvas.grid(row=0, column=0, sticky="nsew")
        ttk.Label(
            profile_visual_frame,
            text="Start/End, en yuksek ve en dusuk kot sematik olarak gosterilir. Secili pompa noktasi vurgulanir.",
            foreground="#6B7280",
            wraplength=240,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))
        status_frame = ttk.LabelFrame(profile_frame, text="Canli Basinc Kontrolu", padding=8)
        status_frame.grid(row=5, column=0, columnspan=5, sticky="ew", pady=(8, 0))
        status_frame.columnconfigure(1, weight=1)
        self.section_pressure_status_label = tk.Label(
            status_frame,
            textvariable=self.section_pressure_status_var,
            bg="#EEF2FF",
            fg="#243B73",
            font=("Segoe UI", 10, "bold"),
            padx=10,
            pady=6,
        )
        self.section_pressure_status_label.grid(row=0, column=0, sticky="w")
        ttk.Label(
            status_frame,
            textvariable=self.section_pressure_window_var,
            wraplength=self.workspace_wraplength,
            justify="left",
            foreground="#16365D",
        ).grid(row=0, column=1, sticky="ew", padx=(12, 0))
        ttk.Label(
            status_frame,
            textvariable=self.section_pressure_status_detail_var,
            wraplength=self.workspace_wraplength,
            justify="left",
            foreground="#35506B",
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Label(
            status_frame,
            textvariable=self.section_pressure_logic_var,
            wraplength=self.workspace_wraplength,
            justify="left",
            foreground="#6B7280",
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Label(
            profile_frame,
            textvariable=self.section_pressure_summary_var,
            wraplength=self.input_wraplength,
            justify="left",
            foreground="#35506B",
        ).grid(row=6, column=0, columnspan=5, sticky="ew", pady=(8, 0))

        segment_actions = ttk.Frame(geometry_frame)
        segment_actions.grid(row=3, column=0, columnspan=6, sticky="w", pady=(2, 6))
        ttk.Button(segment_actions, text="Segment Ekle", command=self._add_geometry_segment).pack(side="left")
        ttk.Button(segment_actions, text="Secili Segmenti Sil", command=self._remove_selected_segment).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(segment_actions, text="Segmentleri Temizle", command=self._clear_geometry_segments).pack(
            side="left", padx=(8, 0)
        )

        self.geometry_segment_frame = ttk.Frame(geometry_frame)
        self.geometry_segment_frame.columnconfigure(0, weight=1)
        self.segment_tree = ttk.Treeview(
            self.geometry_segment_frame,
            columns=("segment", "nps", "schedule", "od", "wt", "length"),
            show="headings",
            height=3,
        )
        self.segment_tree.heading("segment", text="Segment")
        self.segment_tree.heading("nps", text="NPS / DN")
        self.segment_tree.heading("schedule", text="Schedule")
        self.segment_tree.heading("od", text="OD (mm)")
        self.segment_tree.heading("wt", text="Et (mm)")
        self.segment_tree.heading("length", text="Uzunluk (m)")
        self.segment_tree.column("segment", width=70, anchor="center")
        self.segment_tree.column("nps", width=120, anchor="w")
        self.segment_tree.column("schedule", width=120, anchor="w")
        self.segment_tree.column("od", width=80, anchor="e")
        self.segment_tree.column("wt", width=80, anchor="e")
        self.segment_tree.column("length", width=90, anchor="e")
        self.segment_tree.grid(row=0, column=0, sticky="ew")
        segment_scroll = ttk.Scrollbar(self.geometry_segment_frame, orient="vertical", command=self.segment_tree.yview)
        segment_scroll.grid(row=0, column=1, sticky="ns")
        self.segment_tree.configure(yscrollcommand=segment_scroll.set)

        ttk.Label(
            geometry_frame,
            textvariable=self.geometry_summary_var,
            wraplength=self.input_wraplength,
            justify="left",
            foreground="#35506B",
        ).grid(row=4, column=0, columnspan=6, sticky="w", pady=(4, 0))
        ttk.Label(
            geometry_frame,
            textvariable=self.section_feedback_vars["geometry"],
            foreground="#A4262C",
            wraplength=self.input_wraplength,
            justify="left",
        ).grid(row=5, column=0, columnspan=6, sticky="w", pady=(6, 0))
        self.geometry_segment_summary_label = ttk.Label(
            geometry_frame,
            textvariable=self.segment_summary_var,
            wraplength=self.input_wraplength,
            justify="left",
            foreground="#35506B",
        )

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
            values=(AUTO_A_MODE, REFERENCE_A_MODE, MANUAL_A_MODE),
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
            "Basinc artisi P (bar, sartname: 1.0)",
            self.air_vars["pressure_rise_bar"],
            field_key="air.pressure_rise_bar",
        )
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
            values=(AUTO_A_MODE, REFERENCE_A_MODE, MANUAL_A_MODE),
            width=24,
        )
        pressure_a_mode_combo.grid(row=3, column=1, sticky="ew", padx=(0, 12), pady=6)
        pressure_a_mode_combo.bind("<<ComboboxSelected>>", self._on_pressure_a_mode_changed)
        ttk.Label(conditions_frame, text="B secenegi").grid(row=3, column=2, sticky="w", pady=6)
        pressure_b_mode_combo = ttk.Combobox(
            conditions_frame,
            textvariable=self.pressure_b_mode_var,
            state="readonly",
            values=(AUTO_B_MODE, REFERENCE_B_MODE, MANUAL_B_MODE),
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
            "Su sicaklik degisimi dT = Tilk - Tson (degC)",
            self.pressure_vars["delta_t_c"],
            field_key="pressure.delta_t_c",
        )
        self._add_entry(
            measurements_frame,
            0,
            "Fiili basinc degisimi Pa = Pilk - Pson (bar)",
            self.pressure_vars["actual_pressure_change_bar"],
            field_key="pressure.actual_pressure_change_bar",
            column=2,
        )
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

    def _build_field_input_panel(self, frame: ttk.Frame) -> None:
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        checklist_frame = ttk.LabelFrame(frame, text="Saha Kontrol Girdileri", padding=12)
        checklist_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        checklist_frame.columnconfigure(1, weight=1)
        ttk.Label(checklist_frame, text="Durum", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(checklist_frame, text="Kontrol noktasi", font=("Segoe UI", 9, "bold")).grid(
            row=0, column=1, sticky="w"
        )
        for row_index, (key, label, reference) in enumerate(FIELD_CHECK_DEFINITIONS, start=1):
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

    def _show_active_input_panel(self) -> None:
        if not hasattr(self, "active_input_frames"):
            return
        active_tab = self._active_tab_key()
        title_map = {
            "air": "Aktif test girdileri: Hava Icerik Testi",
            "pressure": "Aktif test girdileri: Basinc Degisim Testi",
            "field": "Aktif test girdileri: Saha Grubu",
        }
        self.input_panel_title_var.set(
            "Sol paneldeki tum giris kutulari aktif sekme ile eslesir. Geometri ve test bolumu profili her zaman ustte tutulur."
        )
        self.active_input_title_label.configure(text=title_map.get(active_tab, "Aktif test girdileri"))
        for key, frame in self.active_input_frames.items():
            if key == active_tab:
                frame.grid()
            else:
                frame.grid_remove()

    def _build_air_tab(self, frame: ttk.Frame) -> None:
        frame.columnconfigure(0, weight=1)

        summary_frame = ttk.LabelFrame(frame, text="Calisma Alani", padding=12)
        summary_frame.grid(row=0, column=0, sticky="ew")
        summary_frame.columnconfigure(0, weight=1)
        ttk.Label(
            summary_frame,
            textvariable=self.workflow_hint_var,
            wraplength=self.workspace_wraplength,
            justify="left",
        ).grid(row=0, column=0, sticky="ew")
        ttk.Label(
            summary_frame,
            textvariable=self.live_notice_var,
            wraplength=self.workspace_wraplength,
            justify="left",
            foreground="#35506B",
        ).grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(
            summary_frame,
            textvariable=self.water_backend_summary_var,
            wraplength=self.workspace_wraplength,
            justify="left",
            foreground="#35506B",
        ).grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Label(
            summary_frame,
            textvariable=self.geometry_summary_var,
            wraplength=self.workspace_wraplength,
            justify="left",
            foreground="#35506B",
        ).grid(row=3, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(
            summary_frame,
            textvariable=self.section_pressure_summary_var,
            wraplength=self.workspace_wraplength,
            justify="left",
            foreground="#35506B",
        ).grid(row=4, column=0, sticky="ew", pady=(8, 0))

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
                "Hava icerik testinde kullanici girdileri solda toplanir. Bu merkez panel, "
                "A katsayisinin durumu ile karar dayanaklarini toplu gosterir."
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

    def _build_pressure_tab(self, frame: ttk.Frame) -> None:
        frame.columnconfigure(0, weight=1)

        summary_frame = ttk.LabelFrame(frame, text="Calisma Alani", padding=12)
        summary_frame.grid(row=0, column=0, sticky="ew")
        summary_frame.columnconfigure(0, weight=1)
        ttk.Label(
            summary_frame,
            textvariable=self.workflow_hint_var,
            wraplength=self.workspace_wraplength,
            justify="left",
        ).grid(row=0, column=0, sticky="ew")
        ttk.Label(
            summary_frame,
            textvariable=self.live_notice_var,
            wraplength=self.workspace_wraplength,
            justify="left",
            foreground="#35506B",
        ).grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(
            summary_frame,
            textvariable=self.helper_mode_summary_var,
            wraplength=self.workspace_wraplength,
            justify="left",
            foreground="#35506B",
        ).grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(
            summary_frame,
            textvariable=self.section_pressure_summary_var,
            wraplength=self.workspace_wraplength,
            justify="left",
            foreground="#35506B",
        ).grid(row=3, column=0, sticky="ew", pady=(8, 0))

        helper_frame = ttk.LabelFrame(frame, text="Katsayi Hazirlama ve Test", padding=12)
        helper_frame.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        helper_frame.columnconfigure(0, weight=1)
        self.pressure_a_calculate_button = self._create_progress_button(
            helper_frame,
            key="pressure_a_calculate",
            text="A Hesapla",
            command=self._on_pressure_a_calculate_button,
        )
        self.pressure_a_calculate_button.grid(
            row=2, column=0, sticky="w", pady=6
        )
        self.b_helper_calculate_button = self._create_progress_button(
            helper_frame,
            key="pressure_b_calculate",
            text="B Hesapla",
            command=self._on_b_helper_calculate_button,
        )
        self.b_helper_calculate_button.grid(
            row=2, column=1, sticky="w", pady=6
        )
        self.pressure_test_button = self._create_progress_button(
            helper_frame,
            key="pressure_test",
            text="Basinc Testini Degerlendir",
            command=self._on_pressure_test_button,
        )
        self.pressure_test_button.grid(row=2, column=2, sticky="w", pady=6)
        self._register_help_note(ttk.Label(
            helper_frame,
            text=(
                "Basinc degisim testinde soldaki girdilerle A/B katsayilari burada hazirlanir ve karar "
                "kurali tek merkezden izlenir."
            ),
            wraplength=self.workspace_wraplength,
            justify="left",
        )).grid(row=3, column=0, columnspan=4, sticky="w", pady=(10, 0))

        reference_frame = ttk.LabelFrame(frame, text="Referans ve Kontrol Ozeti", padding=12)
        reference_frame.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        reference_frame.columnconfigure(0, weight=1)
        ttk.Label(
            reference_frame,
            textvariable=self.pressure_backend_comparison_var,
            wraplength=self.workspace_wraplength,
            justify="left",
            foreground="#35506B",
        ).grid(row=0, column=0, sticky="ew")
        ttk.Label(
            reference_frame,
            textvariable=self.pressure_control_table_var,
            wraplength=self.workspace_wraplength,
            justify="left",
            foreground="#35506B",
        ).grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(
            frame,
            textvariable=self.section_feedback_vars["pressure"],
            foreground="#A4262C",
            wraplength=self.workspace_wraplength,
            justify="left",
        ).grid(row=3, column=0, sticky="w", pady=(12, 0))

    def _build_field_tab(self, frame: ttk.Frame) -> None:
        frame.columnconfigure(0, weight=1)

        checklist_frame = ttk.LabelFrame(frame, text="Saha Durum Ozetleri", padding=12)
        checklist_frame.grid(row=0, column=0, sticky="ew")
        checklist_frame.columnconfigure(0, weight=1)
        ttk.Label(
            checklist_frame,
            textvariable=self.check_summary_var,
            foreground="#35506B",
            wraplength=self.workspace_wraplength,
            justify="left",
        ).grid(row=0, column=0, sticky="ew")
        self.check_progress = ttk.Progressbar(
            checklist_frame,
            mode="determinate",
            maximum=len(FIELD_CHECK_DEFINITIONS),
            variable=self.check_progress_var,
        )
        self.check_progress.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(
            checklist_frame,
            textvariable=self.pig_summary_var,
            wraplength=self.workspace_wraplength,
            justify="left",
        ).grid(row=2, column=0, sticky="ew", pady=(10, 0))

        pig_frame = ttk.LabelFrame(frame, text="Saha Hesaplari ve Yontemler", padding=12)
        pig_frame.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        pig_frame.columnconfigure(0, weight=1)
        self._register_help_note(ttk.Label(
            pig_frame,
            text=(
                "Soldaki checklist ve pig girisleri saha uygulama notlari ile birlikte bu merkez "
                "panelden izlenir."
            ),
            wraplength=self.workspace_wraplength,
            justify="left",
        )).grid(row=0, column=0, sticky="ew")
        self.pig_calculate_button = self._create_progress_button(
            pig_frame,
            key="pig_calculate",
            text="Pig Hizini Hesapla",
            command=self._on_pig_calculate_button,
        )
        self.pig_calculate_button.grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Label(
            pig_frame,
            textvariable=self.pig_status_var,
            foreground="#8A6D3B",
        ).grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Label(
            pig_frame,
            textvariable=self.pig_limit_var,
            wraplength=self.workspace_wraplength,
            justify="left",
            foreground="#35506B",
        ).grid(row=3, column=0, sticky="ew", pady=(8, 0))

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

        ttk.Label(
            frame,
            textvariable=self.section_feedback_vars["field"],
            foreground="#A4262C",
            wraplength=self.workspace_wraplength,
            justify="left",
        ).grid(row=3, column=0, sticky="w", pady=(12, 0))

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
        for field_key, variable in (
            [(f"geometry.{key}", variable) for key, variable in self.geometry_vars.items()]
            + [(f"geometry.{key}", variable) for key, variable in self.section_profile_vars.items()]
            + [(f"air.{key}", variable) for key, variable in self.air_vars.items()]
            + [(f"pressure.{key}", variable) for key, variable in self.pressure_vars.items()]
            + [(f"field.{key}", variable) for key, variable in self.field_vars.items()]
            + [(f"helper.{key}", variable) for key, variable in self.b_helper_vars.items()]
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

    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-Return>", lambda *_: self._run_selected_test())
        self.root.bind("<F5>", lambda *_: self._recalculate_active_coefficients())

    def _check_for_updates_on_startup(self) -> None:
        self._start_update_check(user_requested=False)

    def _check_for_updates_manually(self) -> None:
        self._start_update_check(user_requested=True)

    def _start_update_check(self, user_requested: bool) -> None:
        if self.update_check_in_progress:
            if user_requested:
                messagebox.showinfo("Bilgi", "Guncelleme kontrolu zaten devam ediyor.")
            return
        self.update_check_in_progress = True
        self.update_status_var.set("Guncelleme kontrol ediliyor...")
        self.update_detail_var.set("GitHub release listesi sorgulaniyor.")
        worker = threading.Thread(
            target=self._perform_update_check,
            args=(user_requested,),
            daemon=True,
        )
        worker.start()

    def _perform_update_check(self, user_requested: bool) -> None:
        try:
            update_info = fetch_latest_update_info()
        except UpdateError as exc:
            self.root.after(0, lambda: self._handle_update_check_error(str(exc), user_requested))
            return
        self.root.after(0, lambda: self._handle_update_check_result(update_info, user_requested))

    def _handle_update_check_error(self, message: str, user_requested: bool) -> None:
        self.update_check_in_progress = False
        self.update_status_var.set("Guncelleme kontrolu tamamlanamadi.")
        self.update_detail_var.set(message)
        if user_requested:
            self._set_banner(message, "warning")
            messagebox.showwarning("Guncelleme Kontrolu", message)

    def _handle_update_check_result(self, update_info: UpdateInfo, user_requested: bool) -> None:
        self.update_check_in_progress = False
        self.latest_update_info = update_info
        if update_info.update_available:
            asset_name = update_info.asset.name if update_info.asset is not None else "uygun zip asset bulunamadi"
            self.update_status_var.set(
                f"Yeni surum bulundu: {update_info.latest_version} ({update_info.tag_name})"
            )
            self.update_detail_var.set(
                f"Kaynak repo: {update_info.source_repository} | Yayin tarihi: {update_info.published_at or '-'} | Paket: {asset_name}"
            )
            self._set_banner(
                f"Yeni surum bulundu: {update_info.latest_version}. Isterseniz uygulama icinden guncellemeyi baslatabilirsiniz.",
                "warning",
            )
            if messagebox.askyesno(
                "Guncelleme Bulundu",
                (
                    f"Yeni surum bulundu: {update_info.latest_version}\n\n"
                    "Simdi indirip uygulamak ister misiniz?"
                ),
            ):
                self._apply_available_update()
            elif user_requested:
                self._set_banner(
                    "Yeni surum bulundu ancak kurulum kullanici onayi olmadan baslatilmadi.",
                    "info",
                )
            return

        self.update_status_var.set(f"Guncel surum kullaniyorsunuz: {APP_VERSION}")
        self.update_detail_var.set(
            f"Bu uygulama icin daha yeni bir release bulunmadi. Kontrol edilen birincil kaynak: {update_info.source_repository}"
        )
        if user_requested:
            self._set_banner("En guncel surumu kullaniyorsunuz.", "success")
            messagebox.showinfo("Guncelleme Kontrolu", "En guncel surumu kullaniyorsunuz.")

    def _apply_available_update(self) -> None:
        if self.update_install_in_progress:
            messagebox.showinfo("Bilgi", "Guncelleme kurulumu zaten devam ediyor.")
            return
        if self.latest_update_info is None:
            self._check_for_updates_manually()
            return
        if not self.latest_update_info.update_available:
            messagebox.showinfo("Bilgi", "Kurulacak yeni bir surum bulunmuyor.")
            return
        try:
            download_root = self._resolve_update_download_dir(create=True)
        except OSError as exc:
            messagebox.showerror("Guncelleme", f"Indirme klasoru hazirlanamadi: {exc}")
            return
        folder_choice = messagebox.askyesnocancel(
            "Guncelleme Indirme Klasoru",
            (
                "Guncelleme paketinin nereye indirilecegini secin.\n\n"
                f"Mevcut klasor:\n{download_root}\n\n"
                "Evet: farkli klasor sec\n"
                "Hayir: mevcut klasorle devam et\n"
                "Iptal: islemi durdur"
            ),
        )
        if folder_choice is None:
            self._set_banner("Guncelleme kurulumu kullanici tarafindan iptal edildi.", "info")
            return
        if folder_choice:
            if not self._choose_update_download_dir():
                self._set_banner("Guncelleme indirme klasoru secilmedigi icin islem baslatilmadi.", "warning")
                return
            try:
                download_root = self._resolve_update_download_dir(create=True)
            except OSError as exc:
                messagebox.showerror("Guncelleme", f"Indirme klasoru hazirlanamadi: {exc}")
                return
        self.update_install_in_progress = True
        self.update_status_var.set(f"Guncelleme indiriliyor: {self.latest_update_info.latest_version}")
        self.update_detail_var.set(
            f"Release paketi indiriliyor ve kurulum hazirlaniyor. Indirme klasoru: {download_root}"
        )
        worker = threading.Thread(target=self._perform_update_install, args=(download_root,), daemon=True)
        worker.start()

    def _perform_update_install(self, download_root: Path) -> None:
        if self.latest_update_info is None:
            self.root.after(0, lambda: self._handle_update_install_error("Guncel release bilgisi bulunamadi."))
            return
        try:
            install_mode = install_update(self.latest_update_info, download_root=download_root)
        except UpdateError as exc:
            self.root.after(0, lambda: self._handle_update_install_error(str(exc)))
            return
        self.root.after(0, lambda: self._handle_update_install_result(install_mode))

    def _handle_update_install_error(self, message: str) -> None:
        self.update_install_in_progress = False
        self.update_status_var.set("Guncelleme kurulumu basarisiz oldu.")
        self.update_detail_var.set(message)
        self._set_banner(message, "error")
        messagebox.showerror("Guncelleme", message)

    def _handle_update_install_result(self, install_mode: str) -> None:
        self.update_install_in_progress = False
        if install_mode == "browser":
            self.update_status_var.set("Tarayici uzerinden guncelleme yonlendirmesi acildi.")
            self.update_detail_var.set(
                "Bu ortam kendini otomatik guncelleyemiyor. Release sayfasi tarayicida acildi."
            )
            self._set_banner("Release sayfasi acildi. Guncel paketi indirip mevcut klasorun yerine koyabilirsiniz.", "warning")
            messagebox.showinfo(
                "Guncelleme",
                "Bu calisma ortami kendini otomatik guncelleyemiyor. Release sayfasi acildi.",
            )
            return
        if install_mode == "up_to_date":
            self.update_status_var.set(f"Guncel surum kullaniyorsunuz: {APP_VERSION}")
            self.update_detail_var.set("Kurulacak yeni bir surum bulunmuyor.")
            messagebox.showinfo("Guncelleme", "Kurulacak yeni bir surum bulunmuyor.")
            return
        self.update_status_var.set("Guncelleme baslatildi. Uygulama yeniden acilacak.")
        self.update_detail_var.set("Indirme tamamlandi. Uygulama kapanirken yeni surum uygulanacak.")
        self._set_banner("Guncelleme indirildi. Uygulama kapatilip yeni surumle yeniden baslatilacak.", "success")
        messagebox.showinfo(
            "Guncelleme",
            "Indirme tamamlandi. Uygulama kapanacak ve guncelleme uygulanacaktir.",
        )
        self.root.after(250, self.root.destroy)

    def _open_release_page(self) -> None:
        target_url = RELEASES_PAGE_URL
        if self.latest_update_info is not None and self.latest_update_info.html_url:
            target_url = self.latest_update_info.html_url
        open_release_page(target_url)

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

    def _refresh_live_test_decision(self) -> None:
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
            ),
        )

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
            ),
        )

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
            return
        if self._safe_float(variable.get()) is None:
            self._set_field_message(field_key, "Gecerli bir sayi girin.", "error")
            self._refresh_control_table_summaries()
            self._update_live_notice()
            self._refresh_visual_schema()
            self._refresh_live_test_decision()
            return
        if field_key == "pressure.b_micro_per_c" and self.use_b_helper_var.get():
            self._set_field_message(field_key, "Helper modu bu degeri yonetiyor.", "info")
            self._refresh_control_table_summaries()
            self._update_live_notice()
            self._refresh_visual_schema()
            self._refresh_live_coefficients()
            self._refresh_live_test_decision()
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

    def _refresh_section_pressure_overview(self) -> None:
        result, error = self._section_pressure_profile_result()
        self.section_pressure_summary_var.set(self._build_section_pressure_summary())
        self._update_section_pressure_status_card(result, error)
        self._refresh_section_pressure_schematic(result, error)

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

    def _build_field_detail_report(self) -> str:
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
        self._show_active_input_panel()
        self._update_workflow_hint()
        self._update_contextual_actions()
        self._sync_backend_comparison_summary()
        self._sync_control_table_summary()
        self._sync_detail_report_summary()
        self._refresh_section_pressure_overview()
        self._refresh_live_test_decision()
        self._update_live_notice()
        self._refresh_visual_schema()

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

    def _checked_control_lines(self) -> list[str]:
        lines: list[str] = []
        for key, label, reference in FIELD_CHECK_DEFINITIONS:
            checked = "x" if self.control_check_vars[key].get() else " "
            lines.append(f"[{checked}] {label} ({reference})")
        return lines

    def _update_pig_limit_hint(self) -> None:
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

    def _on_pig_mode_changed(self, _: tk.Event | None = None) -> None:
        self._update_pig_limit_hint()

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

    def _format_backend_b_value(self, value: float | None, error: str | None = None) -> str:
        if value is not None:
            return f"{value:.6f}"
        if error:
            return f"hesaplanamadi ({error})"
        return "hesaplanamadi"

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

    def _focus_field(self, field_key: str | None) -> None:
        if not field_key:
            return
        widget = self.input_widgets.get(field_key) or self.entry_widgets.get(field_key)
        if widget is not None:
            widget.focus_set()
            if isinstance(widget, ttk.Entry):
                widget.selection_range(0, "end")

    def _on_air_a_calculate_button(self) -> object:
        return self._execute_progress_button_action(
            "air_a_calculate",
            self._calculate_air_a,
            result_state_resolver=self._bool_progress_state,
        )

    def _on_pressure_a_calculate_button(self) -> object:
        return self._execute_progress_button_action(
            "pressure_a_calculate",
            self._calculate_pressure_a,
            result_state_resolver=self._bool_progress_state,
        )

    def _on_b_helper_calculate_button(self) -> object:
        return self._execute_progress_button_action(
            "pressure_b_calculate",
            self._calculate_b_helper,
            result_state_resolver=self._bool_progress_state,
        )

    def _on_air_test_button(self) -> object:
        return self._execute_progress_button_action(
            "air_test",
            self._run_air_test_impl,
            result_state_resolver=self._decision_progress_state,
        )

    def _on_pressure_test_button(self) -> object:
        return self._execute_progress_button_action(
            "pressure_test",
            self._run_pressure_test_impl,
            result_state_resolver=self._decision_progress_state,
        )

    def _on_pig_calculate_button(self) -> object:
        return self._execute_progress_button_action(
            "pig_calculate",
            self._calculate_pig_speed,
            result_state_resolver=self._pig_progress_state,
        )

    def _run_air_test_impl(self) -> None:
        self._run_air_test()

    def _run_pressure_test_impl(self) -> None:
        self._run_pressure_test()

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

    def _air_a_is_auto(self) -> bool:
        return self.air_a_mode_var.get() == AUTO_A_MODE

    def _pressure_a_is_auto(self) -> bool:
        return self.pressure_a_mode_var.get() == AUTO_A_MODE

    def _pressure_b_is_auto(self) -> bool:
        return self.pressure_b_mode_var.get() == AUTO_B_MODE

    def _air_a_is_reference(self) -> bool:
        return self.air_a_mode_var.get() == REFERENCE_A_MODE

    def _pressure_a_is_reference(self) -> bool:
        return self.pressure_a_mode_var.get() == REFERENCE_A_MODE

    def _pressure_b_is_reference(self) -> bool:
        return self.pressure_b_mode_var.get() == REFERENCE_B_MODE

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

    def _on_air_a_reference_changed(self, _: tk.Event | None = None) -> None:
        self._apply_air_a_reference(log_result=True)

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

    def _calculate_pig_speed(self, log_result: bool = True) -> bool:
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

    def _append_result(self, title: str, content: str) -> None:
        stamped_entry = (
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {title}\n{content}"
        )
        self.report_entries.append(stamped_entry)
        self.results_text.configure(state="normal")
        self.results_text.insert("end", f"\n{stamped_entry}\n")
        self.results_text.see("end")
        self.results_text.configure(state="disabled")

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

    def _clear_field_form(self) -> None:
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

    def _show_about_dialog(self) -> None:
        messagebox.showinfo(
            "Hakkinda",
            (
                f"{APP_NAME}\n"
                f"Surum: {APP_VERSION}\n\n"
                f"Referans sartname: {SPEC_DOCUMENT_CODE}\n"
                f"{SPEC_DOCUMENT_TITLE}\n\n"
                "Bu uygulama hidrostatik test degerlendirmesi icin gelistirildi.\n"
                "Geometri manuel girilebilir, ASME B36.10 katalog listesinden secilebilir\n"
                "ve farkli et kalinliklarina sahip segmentler birlikte modellenebilir."
            ),
        )


def main() -> None:
    root = tk.Tk()
    style = ttk.Style()
    if "vista" in style.theme_names():
        style.theme_use("vista")
    HydrostaticTestApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

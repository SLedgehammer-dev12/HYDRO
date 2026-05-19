from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, ttk
from tkinter.scrolledtext import ScrolledText
from typing import TYPE_CHECKING

from ..app_metadata import SPEC_DOCUMENT_CODE, SPEC_DOCUMENT_TITLE
from ..domain import (
    get_pump_location_options,
    get_location_class_options,
)
from ..data.pipe_catalog import (
    get_api_5l_psl2_grade_options,
    get_pipe_size_options,
    get_schedule_options,
)

if TYPE_CHECKING:
    from .app_main import HydrostaticTestApp


class LayoutBuilderMixin:
    """UI layout and window management mixin."""

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
            text="Boru Kesiti ve Test Profili",
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, sticky="w")
        self._register_help_note(ttk.Label(
            sidebar_header,
            text=(
                "Tum testler icin ortak olan boru geometrisi, test bolumu profili ve basinc penceresi "
                "bu panelde toplanir. Teste ozel girisler orta paneldeki sekmelerde yer alir."
            ),
            wraplength=self.input_wraplength,
            justify="left",
            foreground="#35506B",
        )).grid(row=1, column=0, sticky="ew", pady=(6, 0))

        geometry_shell = ttk.Frame(content)
        geometry_shell.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        geometry_shell.columnconfigure(0, weight=1)
        self._build_geometry_input_panel(geometry_shell)

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
        self._add_entry(
            profile_frame,
            row=4,
            label="Ortam sicakligi (degC)",
            variable=self.ambient_temp_var,
            field_key="geometry.ambient_temp_c",
            column=2,
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
        ttk.Button(segment_actions, text="CSV'den Icari Al", command=self._import_segments_from_csv).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(segment_actions, text="Panodan Yapistir", command=self._import_segments_from_clipboard).pack(
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

    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-Return>", lambda *_: self._run_selected_test())
        self.root.bind("<F5>", lambda *_: self._recalculate_active_coefficients())


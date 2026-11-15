from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .constants import MANUAL_B_MODE
from .validators import (
    A_MICRO_PER_BAR_MAX,
    A_MICRO_PER_BAR_MIN,
    ACTUAL_PRESSURE_CHANGE_BAR_MAX,
    ACTUAL_PRESSURE_CHANGE_BAR_MIN,
    B_MICRO_PER_C_MAX,
    B_MICRO_PER_C_MIN,
    DELTA_T_C_MAX,
    DELTA_T_C_MIN,
    K_FACTOR_MAX,
    K_FACTOR_MIN,
    NumericInputError,
    parse_finite_float,
    validate_geometry_inputs,
    validate_geometry_text_inputs,
)

WIZARD_STEPS_CONFIG = [
    ("Boru Geometrisi", "Boru katalog, olcu ve profil bilgileri"),
    ("Test Parametreleri", "Sicaklik, basinc ve A/B katsayilari"),
    ("Test Uygulama", "Hava icerik ve basinc degisim testleri"),
    ("Rapor ve Karar", "Nihai karar karti ve rapor exportu"),
]

# Adim -> sekme eslemesi. Saha sekmesi (2) bilincli olarak kullanilmaz:
# test uygulama ve rapor adimlari Basinc sekmesinde yurutulur.
WIZARD_STEP_TAB_KEYS: tuple[str, ...] = ("air", "pressure", "pressure", "pressure")
WIZARD_STEP_TAB_INDEX: tuple[int, ...] = (0, 1, 1, 1)

# Rapor adiminda sag panelde acilacak "Karar ve Akis" sekmesi.
REPORT_SIDE_TAB_INDEX = 1

COMPLETED_COLOR = "#1D5F2F"
ACTIVE_COLOR = "#16365D"
PENDING_COLOR = "#9CA3AF"
COMPLETED_BG = "#EAF7EA"
ACTIVE_BG = "#EEF4FF"
PENDING_BG = "#F3F4F6"

STEP_DESC_FONT_SIZE = 8
STEP_STATUS_COMPLETED = "Tamamlandi"
STEP_STATUS_ACTIVE = "Aktif adim"
STEP_STATUS_PENDING = "Bekliyor"

NUM_STEPS = len(WIZARD_STEPS_CONFIG)

ALLOWED_EXECUTION_DECISIONS = frozenset({"BASARILI", "BASARISIZ"})
BLOCKED_EXECUTION_DECISIONS = frozenset({"", "BEKLIYOR", "DOGRULANAMADI", "STALE"})


def _text_value(variable: object) -> str:
    """StringVar, duz metin veya ``None`` degerini guvenli bicimde metne cevirir."""
    if variable is None:
        return ""
    getter = getattr(variable, "get", None)
    value = getter() if callable(getter) else variable
    if value is None:
        return ""
    return str(value).strip()


def _segment_dimensions(segment: object) -> tuple[float | None, float | None, float | None]:
    """Segment kaydindan (dict veya nesne) cap/kalinlik/uzunluk degerlerini cikarir."""
    pipe = segment.get("pipe") if isinstance(segment, dict) else getattr(segment, "pipe", segment)

    def _value(name: str) -> float | None:
        if isinstance(pipe, dict):
            raw = pipe.get(name)
        else:
            raw = getattr(pipe, name, None)
        if raw is None:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    return _value("outside_diameter_mm"), _value("wall_thickness_mm"), _value("length_m")


class WizardStepIndicator(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        on_step_click: callable | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(parent, **kwargs)
        self.on_step_click = on_step_click
        self.current_step = 0
        self.completed_steps: set[int] = set()
        self.step_labels: list[tk.Label] = []
        self.step_desc_labels: list[tk.Label] = []
        self.step_circles: list[tk.Canvas] = []
        self.connector_lines: list[tk.Canvas] = []
        self._build()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        container = ttk.Frame(self)
        container.grid(row=0, column=0, sticky="ew", padx=8, pady=6)
        total_columns = NUM_STEPS + (NUM_STEPS - 1)
        for i in range(total_columns):
            container.columnconfigure(i, weight=1 if i % 2 == 0 else 0)

        col = 0
        for idx, (title, desc) in enumerate(WIZARD_STEPS_CONFIG):
            step_frame = ttk.Frame(container)
            step_frame.grid(row=0, column=col, sticky="ew", padx=4)
            step_frame.columnconfigure(0, weight=1)

            circle_canvas = tk.Canvas(
                step_frame,
                width=32,
                height=32,
                highlightthickness=2,
                highlightbackground=PENDING_BG,
                highlightcolor=ACTIVE_COLOR,
                bg=PENDING_BG,
                takefocus=True,
            )
            circle_canvas.create_oval(4, 4, 28, 28, fill=PENDING_COLOR, outline="", tags="circle")
            circle_canvas.create_text(
                16, 16, text=str(idx + 1), fill="white", font=("Segoe UI", 11, "bold"), tags="text"
            )
            circle_canvas.grid(row=0, column=0, pady=(0, 4))
            circle_canvas.bind("<Button-1>", lambda _e, s=idx: self._on_step_clicked(s))
            circle_canvas.bind("<Return>", lambda _e, s=idx: self._on_step_key_activated(s))
            circle_canvas.bind("<KP_Enter>", lambda _e, s=idx: self._on_step_key_activated(s))
            circle_canvas.bind("<space>", lambda _e, s=idx: self._on_step_key_activated(s))

            title_label = tk.Label(
                step_frame,
                text=title,
                font=("Segoe UI", 9, "bold"),
                fg=PENDING_COLOR,
                bg=PENDING_BG,
                anchor="center",
                justify="center",
            )
            title_label.grid(row=1, column=0, sticky="ew")

            desc_label = tk.Label(
                step_frame,
                text=desc,
                font=("Segoe UI", STEP_DESC_FONT_SIZE),
                fg=PENDING_COLOR,
                bg=PENDING_BG,
                anchor="center",
                justify="center",
                wraplength=160,
            )
            desc_label.grid(row=2, column=0, sticky="ew", pady=(2, 0))

            self.step_circles.append(circle_canvas)
            self.step_labels.append(title_label)
            self.step_desc_labels.append(desc_label)

            col += 1

            if idx < NUM_STEPS - 1:
                connector = tk.Canvas(
                    container,
                    width=40,
                    height=4,
                    highlightthickness=0,
                    bg=PENDING_BG,
                )
                connector.create_line(0, 2, 40, 2, fill=PENDING_COLOR, width=3, tags="line")
                connector.grid(row=0, column=col, sticky="ew", padx=0)
                self.connector_lines.append(connector)
                col += 1

        self._refresh()

    def _on_step_clicked(self, step: int) -> None:
        if self.on_step_click:
            self.on_step_click(step)

    def _on_step_key_activated(self, step: int) -> str:
        self._on_step_clicked(step)
        return "break"

    def set_step(self, step: int) -> None:
        self.current_step = max(0, min(step, NUM_STEPS - 1))
        self._refresh()

    def set_completed(self, step: int, completed: bool = True) -> None:
        if completed:
            self.completed_steps.add(step)
        else:
            self.completed_steps.discard(step)
        self._refresh()

    def advance(self) -> None:
        # Son adimda da ilerleme kaydedilir; boylece "Tamamla" no-op olmaz.
        self.completed_steps.add(self.current_step)
        if self.current_step < NUM_STEPS - 1:
            self.current_step += 1
        self._refresh()

    def retreat(self) -> None:
        if self.current_step > 0:
            self.current_step -= 1
            self._refresh()

    def step_status(self, step: int) -> str:
        if step in self.completed_steps:
            return STEP_STATUS_COMPLETED
        if step == self.current_step:
            return STEP_STATUS_ACTIVE
        return STEP_STATUS_PENDING

    def _refresh(self) -> None:
        for idx in range(NUM_STEPS):
            if idx == self.current_step:
                bg = ACTIVE_BG
                circle_fill = ACTIVE_COLOR
                fg = ACTIVE_COLOR
            elif idx in self.completed_steps:
                bg = COMPLETED_BG
                circle_fill = COMPLETED_COLOR
                fg = COMPLETED_COLOR
            else:
                bg = PENDING_BG
                circle_fill = PENDING_COLOR
                fg = PENDING_COLOR

            self.step_circles[idx].configure(bg=bg, highlightbackground=bg)
            self.step_circles[idx].itemconfigure("circle", fill=circle_fill)
            self.step_labels[idx].configure(fg=fg, bg=bg)
            self.step_desc_labels[idx].configure(fg=fg, bg=bg)

            if idx < NUM_STEPS - 1:
                connector_bg = COMPLETED_BG if idx in self.completed_steps else PENDING_BG
                connector_fill = COMPLETED_COLOR if idx in self.completed_steps else PENDING_COLOR
                self.connector_lines[idx].configure(bg=connector_bg)
                self.connector_lines[idx].itemconfigure("line", fill=connector_fill)


class WizardController:
    GEOMETRY = 0
    PARAMETERS = 1
    EXECUTION = 2
    REPORT = 3

    def __init__(self, app: object) -> None:
        self.app = app
        self.active = False
        self.completed = False
        self.step_indicator: WizardStepIndicator | None = None
        self.next_button: ttk.Button | None = None
        self.back_button: ttk.Button | None = None
        self.wizard_frame: ttk.Frame | None = None

    def build_wizard_bar(self, parent: ttk.Frame) -> None:
        self.wizard_frame = ttk.LabelFrame(parent, text="Adim Adim Test Akisi (Wizard)", padding=8)
        self.wizard_frame.columnconfigure(0, weight=1)

        self.step_indicator = WizardStepIndicator(
            self.wizard_frame,
            on_step_click=self._on_step_selected,
        )
        self.step_indicator.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        nav_frame = ttk.Frame(self.wizard_frame)
        nav_frame.grid(row=1, column=0, sticky="ew")

        self.back_button = ttk.Button(
            nav_frame,
            text="<< Geri",
            command=self._go_back,
            state="disabled",
        )
        self.back_button.pack(side="left")

        self.step_info_var = tk.StringVar(value=self._step_info_text(0))
        step_info_label = ttk.Label(
            nav_frame,
            textvariable=self.step_info_var,
            anchor="center",
            font=("Segoe UI", 9),
        )
        step_info_label.pack(side="left", fill="x", expand=True, padx=12)

        self.next_button = ttk.Button(
            nav_frame,
            text="Ileri >>",
            command=self._go_next,
        )
        self.next_button.pack(side="right")

        self.wizard_frame.grid_remove()

    def set_active(self, active: bool) -> None:
        self.active = active
        if active:
            restored = self._restore_from_session()
            if not restored:
                self._reset()
            self._set_banner("Wizard modu aktif. Adim adim ilerleyerek testi tamamlayin.", "info")
        else:
            self._set_banner(
                "Wizard modu kapandi. Girdileri serbest sekme mantigiyla kullanabilirsiniz.",
                "info",
            )
        self._update_ui()

    def _restore_from_session(self) -> bool:
        session_manager = getattr(self.app, "session_manager", None)
        if session_manager is None:
            return False
        getter = getattr(session_manager, "get_active_session", None)
        if not callable(getter):
            return False
        session = getter()
        if session and session.wizard_state:
            state = session.wizard_state
            if self.step_indicator:
                self.step_indicator.current_step = state.get("current_step", 0)
                self.step_indicator.completed_steps = set(state.get("completed_steps", []))
                self.step_indicator._refresh()
            self.completed = bool(state.get("completed", False))
            self._sync_app_state()
            return True
        return False

    def toggle(self) -> None:
        self.set_active(not self.active)

    def _reset(self) -> None:
        self.completed = False
        if self.step_indicator:
            self.step_indicator.completed_steps.clear()
            self.step_indicator.current_step = 0
            self.step_indicator._refresh()
        self._sync_app_state()

    def _on_step_selected(self, step: int) -> None:
        if not self.active:
            return
        if self.step_indicator and step <= self.step_indicator.current_step:
            self.step_indicator.current_step = step
            self.step_indicator._refresh()
            self._sync_app_state()

    def _go_back(self) -> None:
        if not self.active or not self.step_indicator:
            return
        self.step_indicator.retreat()
        self._sync_app_state()

    def _go_next(self) -> None:
        if not self.active or not self.step_indicator:
            return
        if self.step_indicator.current_step == self.REPORT:
            self._finish_wizard()
            return
        if not self._validate_current_step():
            return
        self.step_indicator.advance()
        self._sync_app_state()

    def _finish_wizard(self) -> None:
        """Son adimda "Tamamla" gercek bir is yapar: karar/raporu acar ve adimi kapatir."""
        self.completed = True
        if self.step_indicator:
            self.step_indicator.completed_steps.add(self.REPORT)
            self.step_indicator._refresh()
            self.step_indicator.current_step = self.REPORT
        self._sync_app_state()
        self._set_banner(
            "Wizard tamamlandi. Karar karti ve detay raporu sag panelde gosteriliyor.",
            "success",
        )

    def _validate_current_step(self) -> bool:
        if not self.step_indicator:
            return False
        step = self.step_indicator.current_step

        if step == self.GEOMETRY:
            return self._validate_geometry()
        if step == self.PARAMETERS:
            return self._validate_parameters()
        if step == self.EXECUTION:
            return self._validate_execution()
        if step == self.REPORT:
            return True
        return False

    # --- Dogrulama ---

    def _validate_geometry(self) -> bool:
        segments = list(getattr(self.app, "geometry_segments", None) or [])
        if segments:
            for index, segment in enumerate(segments, start=1):
                outside, wall, length = _segment_dimensions(segment)
                if outside is None or wall is None or length is None:
                    self._set_banner(
                        f"Segment {index}: dis cap, et kalinligi ve uzunluk degerleri gerekli.",
                        "error",
                    )
                    return False
                message, status = validate_geometry_inputs(outside, wall, length)
                if status != "valid":
                    self._set_banner(f"Segment {index}: {message}", "error")
                    return False
            self._set_banner("Adim 1 tamamlandi. Segmentli boru geometrisi gecerli.", "success")
            return True

        message, status = validate_geometry_text_inputs(
            self._text("geometry_vars", "outside_diameter_mm"),
            self._text("geometry_vars", "wall_thickness_mm"),
            self._text("geometry_vars", "length_m"),
        )
        if status == "incomplete":
            self._set_banner(
                "Lutfen boru dis cap, et kalinligi ve hat uzunlugunu girin.", "warning"
            )
            return False
        if status != "valid":
            self._set_banner(message or "Geometri degerleri gecersiz.", "error")
            return False
        self._set_banner("Adim 1 tamamlandi. Boru geometrisi gecerli.", "success")
        return True

    def _validate_parameters(self) -> bool:
        air_temperature = self._text("air_vars", "temperature_c")
        air_pressure = self._text("air_vars", "pressure_bar")
        pressure_temperature = self._text("pressure_vars", "temperature_c")
        pressure_pressure = self._text("pressure_vars", "pressure_bar")

        air_active = bool(air_temperature or air_pressure)
        pressure_active = bool(pressure_temperature or pressure_pressure)

        if not air_active and not pressure_active:
            self._set_banner("En az bir test icin sicaklik ve basinc degeri girin.", "warning")
            return False

        if air_active:
            if not (air_temperature and air_pressure):
                self._set_banner(
                    "Hava icerik testi icin sicaklik ve basinc birlikte girilmelidir.",
                    "warning",
                )
                return False
            if not self._require_number(
                air_temperature, "Hava su sicakligi"
            ) or not self._require_number(air_pressure, "Hava su basinci", min_value=0.0):
                return False
            if not self._require_coefficient(
                self._text("air_vars", "a_micro_per_bar"),
                "Hava A katsayisi",
                A_MICRO_PER_BAR_MIN,
                A_MICRO_PER_BAR_MAX,
            ):
                return False
            if not self._require_coefficient(
                self._text("air_vars", "k_factor"),
                "K faktoru",
                K_FACTOR_MIN,
                K_FACTOR_MAX,
                missing_message="K faktorunu girin.",
            ):
                return False

        if pressure_active:
            if not (pressure_temperature and pressure_pressure):
                self._set_banner(
                    "Basinc degisim testi icin sicaklik ve basinc birlikte girilmelidir.",
                    "warning",
                )
                return False
            if not self._require_number(
                pressure_temperature, "Basinc testi su sicakligi"
            ) or not self._require_number(
                pressure_pressure, "Basinc testi su basinci", min_value=0.0
            ):
                return False
            if not self._require_coefficient(
                self._text("pressure_vars", "a_micro_per_bar"),
                "Basinc testi A katsayisi",
                A_MICRO_PER_BAR_MIN,
                A_MICRO_PER_BAR_MAX,
            ):
                return False
            if not self._validate_b_coefficient():
                return False
            if not self._require_number(
                self._text("pressure_vars", "delta_t_c"),
                "dT (Tilk - Tson)",
                min_value=DELTA_T_C_MIN,
                max_value=DELTA_T_C_MAX,
            ):
                return False
            if not self._require_number(
                self._text("pressure_vars", "actual_pressure_change_bar"),
                "Pa (Pilk - Pson)",
                min_value=ACTUAL_PRESSURE_CHANGE_BAR_MIN,
                max_value=ACTUAL_PRESSURE_CHANGE_BAR_MAX,
            ):
                return False

        self._set_banner("Adim 2 tamamlandi. Test parametreleri hazir.", "success")
        return True

    def _validate_b_coefficient(self) -> bool:
        b_value = self._text("pressure_vars", "b_micro_per_c")
        mode = _text_value(getattr(self.app, "pressure_b_mode_var", None))
        manual_mode = mode == MANUAL_B_MODE
        if not b_value:
            if manual_mode:
                self._set_banner("B katsayisini manuel olarak girin.", "warning")
            else:
                self._set_banner(
                    "B katsayisi otomatik/tablo modunda henuz hazir degil. "
                    "B'yi hesaplayin veya referans tablosunu secin.",
                    "warning",
                )
            return False
        try:
            parse_finite_float(
                b_value,
                "B katsayisi",
                min_value=B_MICRO_PER_C_MIN,
                max_value=B_MICRO_PER_C_MAX,
            )
        except NumericInputError as exc:
            self._set_banner(str(exc), "error")
            return False
        return True

    def _validate_execution(self) -> bool:
        decision = _text_value(getattr(self.app, "decision_status_var", None)).upper()
        if decision not in ALLOWED_EXECUTION_DECISIONS:
            if decision == "DOGRULANAMADI":
                message = (
                    "Degerlendirme DOGRULANAMADI durumunda. Eksik veya gecersiz "
                    "girdileri duzeltip testi yeniden degerlendirin."
                )
            elif decision == "STALE":
                message = (
                    "Katsayi durumu STALE (guncellenmeli). Katsayilari yenileyip "
                    "testi tekrar degerlendirin."
                )
            else:
                message = (
                    "En az bir testi degerlendirin. Karar BASARILI veya BASARISIZ "
                    "olana kadar sonraki adima gecilemez."
                )
            self._set_banner(message, "warning")
            return False

        if self._active_coefficients_stale():
            self._set_banner(
                "Aktif testin katsayilari guncel degil (STALE). Katsayilari yenileyin.",
                "warning",
            )
            return False

        self._set_banner("Adim 3 tamamlandi. Test sonuclari alindi.", "success")
        return True

    # --- Uygulama durumu ---

    def _sync_app_state(self) -> None:
        if not self.step_indicator:
            return
        step = max(0, min(self.step_indicator.current_step, NUM_STEPS - 1))
        self.step_indicator.current_step = step
        self.step_info_var.set(self._step_info_text(step))

        self._select_step_tab(step)
        if step == self.REPORT:
            self._show_decision_report_view()

        self._call_app("_show_active_input_panel")
        self._call_app("_update_workflow_hint")

        if self.back_button is not None:
            self.back_button.configure(state="normal" if step > 0 else "disabled")
        if self.next_button is not None:
            is_last = step == NUM_STEPS - 1
            if is_last and self.completed:
                self.next_button.configure(text="Tamamlandi", state="disabled")
            else:
                self.next_button.configure(
                    text="Tamamla >>" if is_last else "Ileri >>",
                    state="normal",
                )

        session_manager = getattr(self.app, "session_manager", None)
        updater = getattr(session_manager, "update_wizard_state", None)
        if callable(updater):
            updater(
                {
                    "current_step": step,
                    "completed_steps": sorted(self.step_indicator.completed_steps),
                    "completed": self.completed,
                    "active": self.active,
                }
            )

        self._update_ui()

    def _step_info_text(self, step: int) -> str:
        title = WIZARD_STEPS_CONFIG[step][0]
        status = STEP_STATUS_ACTIVE
        if self.step_indicator is not None:
            status = self.step_indicator.step_status(step)
        return f"Adim {step + 1}/{NUM_STEPS}: {title} - {status}"

    def _select_step_tab(self, step: int) -> None:
        tab_key = WIZARD_STEP_TAB_KEYS[step]
        selector = getattr(self.app, "_select_tab_by_key", None)
        if callable(selector):
            selector(tab_key)
            return
        notebook = getattr(self.app, "notebook", None)
        select = getattr(notebook, "select", None)
        if callable(select):
            try:
                select(WIZARD_STEP_TAB_INDEX[step])
            except Exception:
                return

    def _show_decision_report_view(self) -> None:
        app = self.app
        side_notebook = getattr(app, "side_notebook", None)
        select = getattr(side_notebook, "select", None)
        if callable(select):
            try:
                select(REPORT_SIDE_TAB_INDEX)
            except Exception:
                pass
        visible_var = getattr(app, "side_panel_visible_var", None)
        if visible_var is not None and not bool(visible_var.get()):
            visible_var.set(True)
            self._call_app("_apply_side_panel_visibility")
        if not self._call_app("_refresh_detail_reports"):
            self._call_app("_sync_detail_report_summary")

    # --- Yardimcilar ---

    def _text(self, group_name: str, key: str) -> str:
        group = getattr(self.app, group_name, None)
        if not isinstance(group, dict):
            return ""
        return _text_value(group.get(key))

    def _require_number(
        self,
        raw: str,
        label: str,
        min_value: float | None = None,
        max_value: float | None = None,
    ) -> bool:
        if not raw:
            self._set_banner(f"{label} bos birakilamaz.", "warning")
            return False
        try:
            parse_finite_float(raw, label, min_value, max_value)
        except NumericInputError as exc:
            self._set_banner(str(exc), "error")
            return False
        return True

    def _require_coefficient(
        self,
        raw: str,
        label: str,
        min_value: float,
        max_value: float,
        *,
        missing_message: str = "A katsayisini hesaplayin veya manuel girin.",
    ) -> bool:
        if not raw:
            self._set_banner(missing_message, "warning")
            return False
        try:
            parse_finite_float(raw, label, min_value, max_value)
        except NumericInputError as exc:
            self._set_banner(str(exc), "error")
            return False
        return True

    def _active_test_key(self) -> str:
        getter = getattr(self.app, "_active_tab_key", None)
        if callable(getter):
            try:
                return str(getter())
            except Exception:
                return "pressure"
        return "pressure"

    def _active_coefficient_keys(self) -> tuple[str, ...]:
        active_tab = self._active_test_key()
        if active_tab == "air":
            return ("air_a",)
        if active_tab == "field":
            return ()
        return ("pressure_a", "pressure_b")

    def _active_coefficients_stale(self) -> bool:
        keys = self._active_coefficient_keys()
        if not keys:
            return False
        sources = getattr(self.app, "coefficient_source_vars", None)
        statuses = getattr(self.app, "coefficient_status_vars", None)
        manager = getattr(self.app, "coefficient_manager", None)
        for key in keys:
            if isinstance(sources, dict):
                source_text = _text_value(sources.get(key)).upper()
                if source_text in {"YENILE", "STALE"}:
                    return True
            if isinstance(statuses, dict):
                status_text = _text_value(statuses.get(key)).lower()
                if "guncellenmeli" in status_text or "stale" in status_text:
                    return True
            getter = getattr(manager, "get", None)
            if callable(getter):
                try:
                    state = getter(key)
                except Exception:
                    state = None
                if getattr(state, "name", "") == "STALE":
                    return True
        return False

    def _set_banner(self, message: str, level: str = "info") -> None:
        setter = getattr(self.app, "_set_banner", None)
        if callable(setter):
            setter(message, level)

    def _call_app(self, method_name: str) -> bool:
        method = getattr(self.app, method_name, None)
        if not callable(method):
            return False
        try:
            method()
        except Exception:
            return False
        return True

    def _update_ui(self) -> None:
        if not self.wizard_frame:
            return
        if self.active:
            self.wizard_frame.grid()
        else:
            self.wizard_frame.grid_remove()

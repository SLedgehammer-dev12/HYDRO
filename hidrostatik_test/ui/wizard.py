from __future__ import annotations

from enum import Enum
import tkinter as tk
from tkinter import ttk

WIZARD_STEPS_CONFIG = [
    ("Boru Geometrisi", "Boru katalog, olcu ve profil bilgileri"),
    ("Test Parametreleri", "Sicaklik, basinc ve A/B katsayilari"),
    ("Test Uygulama", "Hava icerik ve basinc degisim testleri"),
    ("Rapor ve Karar", "Nihai karar karti ve rapor exportu"),
]

COMPLETED_COLOR = "#1D5F2F"
ACTIVE_COLOR = "#16365D"
PENDING_COLOR = "#9CA3AF"
COMPLETED_BG = "#EAF7EA"
ACTIVE_BG = "#EEF4FF"
PENDING_BG = "#F3F4F6"

NUM_STEPS = len(WIZARD_STEPS_CONFIG)


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
                highlightthickness=0,
                bg=PENDING_BG,
            )
            circle_canvas.create_oval(4, 4, 28, 28, fill=PENDING_COLOR, outline="", tags="circle")
            circle_canvas.create_text(
                16, 16, text=str(idx + 1), fill="white", font=("Segoe UI", 11, "bold"), tags="text"
            )
            circle_canvas.grid(row=0, column=0, pady=(0, 4))
            circle_canvas.bind("<Button-1>", lambda _e, s=idx: self._on_step_clicked(s))

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
                font=("Segoe UI", 7),
                fg=PENDING_COLOR,
                bg=PENDING_BG,
                anchor="center",
                justify="center",
                wraplength=160,
            )
            desc_label.grid(row=2, column=0, sticky="ew", pady=(2, 0))

            self.step_circles.append(circle_canvas)
            self.step_labels.append(title_label)

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
        if self.current_step < NUM_STEPS - 1:
            self.completed_steps.add(self.current_step)
            self.current_step += 1
            self._refresh()

    def retreat(self) -> None:
        if self.current_step > 0:
            self.current_step -= 1
            self._refresh()

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

            self.step_circles[idx].configure(bg=bg)
            self.step_circles[idx].itemconfigure("circle", fill=circle_fill)
            self.step_labels[idx].configure(fg=fg, bg=bg)

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

        self.step_info_var = tk.StringVar(value="Adim 1/4: Boru Geometrisi")
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
            self.app._set_banner("Wizard modu aktif. Adim adim ilerleyerek testi tamamlayin.", "info")
        else:
            self.app._set_banner("Wizard modu kapandi. Girdileri serbest sekme mantigiyla kullanabilirsiniz.", "info")
        self._update_ui()

    def _restore_from_session(self) -> bool:
        if hasattr(self.app, "session_manager"):
            session = self.app.session_manager.get_active_session()
            if session and session.wizard_state:
                state = session.wizard_state
                if self.step_indicator:
                    self.step_indicator.current_step = state.get("current_step", 0)
                    self.step_indicator.completed_steps = set(state.get("completed_steps", []))
                    self.step_indicator._refresh()
                self._sync_app_state()
                return True
        return False

    def toggle(self) -> None:
        self.set_active(not self.active)

    def _reset(self) -> None:
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
        if not self._validate_current_step():
            return
        self.step_indicator.advance()
        self._sync_app_state()

    def _validate_current_step(self) -> bool:
        if not self.step_indicator:
            return False
        step = self.step_indicator.current_step

        if step == self.GEOMETRY:
            return self._validate_geometry()
        elif step == self.PARAMETERS:
            return self._validate_parameters()
        elif step == self.EXECUTION:
            return self._validate_execution()
        elif step == self.REPORT:
            return True
        return False

    def _validate_geometry(self) -> bool:
        app = self.app
        od_str = app.geometry_vars["outside_diameter_mm"].get().strip()
        wt_str = app.geometry_vars["wall_thickness_mm"].get().strip()
        length_str = app.geometry_vars["length_m"].get().strip()
        if not (od_str and wt_str and length_str):
            app._set_banner("Lutfen boru dis cap, et kalinligi ve hat uzunlugunu girin.", "warning")
            return False
        try:
            od = float(od_str.replace(",", "."))
            wt = float(wt_str.replace(",", "."))
            length = float(length_str.replace(",", "."))
        except ValueError:
            app._set_banner("Geometri degerleri gecerli sayilar olmalidir.", "error")
            return False
        if od <= 0 or wt <= 0 or length <= 0:
            app._set_banner("Geometri degerleri pozitif olmalidir.", "error")
            return False
        if wt >= od / 2:
            app._set_banner("Et kalinligi dis capin yarisindan fazla olamaz.", "error")
            return False
        app._set_banner("Adim 1 tamamlandi. Boru geometrisi gecerli.", "success")
        return True

    def _validate_parameters(self) -> bool:
        app = self.app
        has_temp_c = False
        has_pressure = False
        for test_type in ("air", "pressure"):
            temp = app.air_vars["temperature_c"].get().strip() if test_type == "air" else app.pressure_vars["temperature_c"].get().strip()
            pres = app.air_vars["pressure_bar"].get().strip() if test_type == "air" else app.pressure_vars["pressure_bar"].get().strip()
            if temp:
                has_temp_c = True
            if pres:
                has_pressure = True

        if not has_temp_c:
            app._set_banner("En az bir test icin sicaklik degeri girin.", "warning")
            return False
        if not has_pressure:
            app._set_banner("En az bir test icin basinc degeri girin.", "warning")
            return False

        a_ok = (
            app.air_vars["a_micro_per_bar"].get().strip()
            or app.pressure_vars["a_micro_per_bar"].get().strip()
        )
        b_ok = app.pressure_vars["b_micro_per_c"].get().strip() or not app.use_b_helper_var.get()
        if not a_ok:
            app._set_banner("A katsayisini hesaplayin veya manuel girin.", "warning")
            return False
        app._set_banner("Adim 2 tamamlandi. Test parametreleri hazir.", "success")
        return True

    def _validate_execution(self) -> bool:
        app = self.app
        decision = app.decision_status_var.get()
        if decision == "BEKLIYOR":
            app._set_banner("En az bir testi degerlendirin (Hava veya Basinc).", "warning")
            return False
        app._set_banner("Adim 3 tamamlandi. Test sonuclari alindi.", "success")
        return True

    def _sync_app_state(self) -> None:
        if not self.step_indicator:
            return
        step = self.step_indicator.current_step
        self.step_info_var.set(f"Adim {step + 1}/4: {WIZARD_STEPS_CONFIG[step][0]}")

        if step == self.GEOMETRY:
            self.app.notebook.select(0)
        elif step == self.PARAMETERS:
            self.app.notebook.select(1)
        elif step == self.EXECUTION:
            self.app.notebook.select(2)
        elif step == self.REPORT:
            pass

        self.app._show_active_input_panel()
        self.app._update_workflow_hint()

        self.back_button.configure(state="normal" if step > 0 else "disabled")
        is_last = step == NUM_STEPS - 1
        self.next_button.configure(text="Tamamla >>" if is_last else "Ileri >>")
        if not is_last:
            self.next_button.configure(state="normal")

        if hasattr(self.app, "session_manager"):
            self.app.session_manager.update_wizard_state({
                "current_step": self.step_indicator.current_step,
                "completed_steps": list(self.step_indicator.completed_steps),
                "active": self.active,
            })

        self._update_ui()

    def _update_ui(self) -> None:
        if not self.wizard_frame:
            return
        if self.active:
            self.wizard_frame.grid()
        else:
            self.wizard_frame.grid_remove()

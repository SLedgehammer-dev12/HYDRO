"""Test raporu OCR kontrolu diyalogu.

Servis cagrisi worker thread'inde yapilir; Tk widget'larina yalnizca ana
thread'de dokunulur. Worker sonucu ``queue.Queue`` uzerinden ana thread'e
aktarir ve periyodik ``after`` yoklamasi ile arayuz guncellenir.

Tasarim ilkesi: hicbir OCR alani sessizce "dogru" kabul edilmez. Sonuc
``needs_human_review`` bayragi ile birlikte gosterilir ve resmi kabul icin
yetkili personel onayi gerektigi vurgulanir.
"""

from __future__ import annotations

import inspect
import json
import math
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import TYPE_CHECKING, Any, Callable

from ..domain.report_schema import FIELD_LABELS
from ..services.report_ocr import (
    SUPPORTED_EXTENSIONS,
    ReportOcrError,
    analyze_report,
    ocr_status,
)

if TYPE_CHECKING:
    from ..services.report_ocr import OcrAnalysisResult

#: Worker kuyrugunun ana thread'de ne siklikla tuketilecegi.
POLL_INTERVAL_MS = 100
#: Bu skorun altindaki alanlar amber, daha dusukleri kirmizi isaretlenir.
LOW_CONFIDENCE_THRESHOLD = 0.6
CRITICAL_CONFIDENCE_THRESHOLD = 0.4

_AMBER_BG = "#FFF6E5"
_AMBER_FG = "#6B4A00"
_RED_BG = "#FDEAEA"
_RED_FG = "#8A1C1C"
_INFO_BG = "#EEF4FF"
_INFO_FG = "#16365D"

_SOURCE_LABELS = {
    "pdf-text-layer": "PDF metin katmani",
    "spreadsheet": "Excel calisma kitabi",
    "ocr": "OCR (Tesseract)",
    "mixed": "Karma (metin katmani + OCR)",
}

_STATUS_LABELS = {
    "match": "Uyusuyor",
    "within_tolerance": "Tolerans icinde",
    "mismatch": "Uyusmuyor",
    "missing_in_report": "Raporda yok",
    "missing_in_calculation": "Hesap yok",
    "not_comparable": "Karsilastirilamaz",
}


def _format_value(value: object) -> str:
    """Return a compact display value for a report field."""
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "Evet" if value else "Hayir"
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number):
            return "-"
        return f"{number:g}"
    text = str(value).strip()
    return text or "-"


def _format_confidence(value: float) -> str:
    if not math.isfinite(value):
        return "-"
    return f"{value:.2f}"


def _format_delta(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "-"
    return f"{value:+g}"


class ReportOcrDialog:
    """PDF/JPG test raporunu analiz eden modal kontrol penceresi."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        calculated_payload: dict[str, Any] | None = None,
        initial_path: str | Path | None = None,
        analyzer: Callable[[str, dict[str, Any] | None], OcrAnalysisResult] | None = None,
    ) -> None:
        self._calculated_payload: dict[str, Any] = dict(calculated_payload or {})
        self._analyzer = analyzer or analyze_report
        self._events: queue.Queue[tuple[str, int, Any]] = queue.Queue()
        self._poll_job: str | None = None
        self._destroyed = False
        self._analysis_running = False
        self._generation = 0
        self._cancel_event: threading.Event | None = None
        self._result: OcrAnalysisResult | None = None

        self._dialog = tk.Toplevel(parent)
        self._dialog.title("Test Raporu Kontrol (OCR)")
        self._dialog.geometry("1060x700")
        self._dialog.minsize(860, 560)
        self._dialog.transient(parent)  # type: ignore[arg-type]
        try:
            self._dialog.grab_set()
        except tk.TclError:
            # Baska bir grab aktifse analiz yine calisir; diyalogu kapatmayiz.
            pass

        self._build_ui()
        if initial_path is not None:
            self.path_var.set(str(initial_path))

        self._dialog.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll_job = self._dialog.after(POLL_INTERVAL_MS, self._poll_queue)

    # ------------------------------------------------------------------
    # Arayuz kurulumu
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        frame = ttk.Frame(self._dialog, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        file_frame = ttk.LabelFrame(frame, text="Rapor Dosyasi", padding=10)
        file_frame.grid(row=0, column=0, sticky="ew")
        file_frame.columnconfigure(1, weight=1)

        ttk.Label(file_frame, text="Dosya:").grid(row=0, column=0, sticky="w")
        self.path_var = tk.StringVar()
        self.path_entry = ttk.Entry(file_frame, textvariable=self.path_var)
        self.path_entry.grid(row=0, column=1, sticky="ew", padx=(8, 8))

        self.browse_button = ttk.Button(file_frame, text="Gozat...", command=self._browse_report)
        self.browse_button.grid(row=0, column=2, sticky="e")

        self.analysis_button = ttk.Button(
            file_frame, text="Analiz Et", command=self._start_analysis
        )
        self.analysis_button.grid(row=0, column=3, sticky="e", padx=(8, 0))

        self.cancel_button = ttk.Button(
            file_frame, text="Iptal Et", command=self._cancel_analysis, state="disabled"
        )
        self.cancel_button.grid(row=0, column=4, sticky="e", padx=(8, 0))

        self.compare_var = tk.BooleanVar(value=True)
        self.compare_check = ttk.Checkbutton(
            file_frame,
            text="Mevcut hesaplamalarla karsilastir",
            variable=self.compare_var,
        )
        self.compare_check.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        ttk.Label(
            file_frame,
            text=f"Desteklenen dosyalar: {supported}",
            foreground="#35506B",
        ).grid(row=2, column=0, columnspan=5, sticky="w", pady=(4, 0))

        self.compare_hint_var = tk.StringVar()
        self._refresh_compare_hint()
        ttk.Label(
            file_frame,
            textvariable=self.compare_hint_var,
            foreground="#8A5B00",
        ).grid(row=3, column=0, columnspan=4, sticky="w", pady=(4, 0))

        try:
            status_text = ocr_status()
        except Exception as exc:  # noqa: BLE001 - durum metni UI'i engellememeli
            status_text = f"OCR durumu okunamadi: {exc}"
        self.ocr_status_label = ttk.Label(
            file_frame,
            text=status_text,
            foreground="#1E6B33" if status_text.startswith("OCR hazir") else "#8A5B00",
        )
        self.ocr_status_label.grid(row=4, column=0, columnspan=4, sticky="w", pady=(6, 0))

        self.analysis_status_var = tk.StringVar(
            value="Dosya secip 'Analiz Et' ile kontrolu baslatin."
        )
        ttk.Label(frame, textvariable=self.analysis_status_var, foreground=_INFO_FG).grid(
            row=1, column=0, sticky="ew", pady=(8, 6)
        )

        self.notebook = ttk.Notebook(frame)
        self.notebook.grid(row=2, column=0, sticky="nsew")

        self._build_summary_tab()
        self._build_fields_tab()
        self._build_discrepancies_tab()
        self._build_warnings_tab()

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        self.save_json_button = ttk.Button(
            button_frame,
            text="JSON Kaydet",
            command=self._save_json,
            state="disabled",
        )
        self.save_json_button.pack(side="left")
        self.close_button = ttk.Button(button_frame, text="Kapat", command=self._on_close)
        self.close_button.pack(side="right")

    def _build_summary_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=12)
        tab.columnconfigure(1, weight=1)
        self.notebook.add(tab, text="Ozet")

        self.summary_vars = {
            "file": tk.StringVar(value="-"),
            "source": tk.StringVar(value="-"),
            "pages": tk.StringVar(value="-"),
            "characters": tk.StringVar(value="-"),
            "confidence": tk.StringVar(value="-"),
            "needs_review": tk.StringVar(value="-"),
            "discrepancies": tk.StringVar(value="-"),
            "warnings": tk.StringVar(value="-"),
        }
        rows = (
            ("Dosya", "file"),
            ("Kaynak", "source"),
            ("Sayfa sayisi", "pages"),
            ("Karakter sayisi", "characters"),
            ("Ortalama guven", "confidence"),
            ("Insan onayi", "needs_review"),
            ("Uyusmazliklar", "discrepancies"),
            ("Uyarilar / sema sorunlari", "warnings"),
        )
        for index, (label, key) in enumerate(rows):
            ttk.Label(tab, text=f"{label}:", font=("Segoe UI", 9, "bold")).grid(
                row=index, column=0, sticky="nw", pady=4
            )
            ttk.Label(
                tab,
                textvariable=self.summary_vars[key],
                wraplength=780,
                justify="left",
            ).grid(row=index, column=1, sticky="w", pady=4)

        self.review_banner = tk.Label(
            tab,
            text="Insan onayi gereklidir.",
            bg=_INFO_BG,
            fg=_INFO_FG,
            anchor="w",
            justify="left",
            padx=10,
            pady=8,
            wraplength=820,
            font=("Segoe UI", 9, "bold"),
        )
        self.review_banner.grid(row=len(rows), column=0, columnspan=2, sticky="ew", pady=(14, 0))

        ttk.Label(
            tab,
            text=(
                "Bu ekran resmi kabul raporu degildir. OCR/alan cikarimi on-kontrol amaclidir; "
                "nihai kabul karari yetkili personel tarafindan verilir. Dusuk guvenli alanlar "
                "ve engelleyici uyusmazliklar giderilmeden sonuc kullanilmamalidir."
            ),
            foreground="#35506B",
            wraplength=820,
            justify="left",
        ).grid(row=len(rows) + 1, column=0, columnspan=2, sticky="ew", pady=(12, 0))

    def _build_fields_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=8)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        self.notebook.add(tab, text="Alanlar")

        columns = ("field", "value", "unit", "confidence", "raw")
        self.fields_tree = ttk.Treeview(tab, columns=columns, show="headings")
        headings = {
            "field": "Alan",
            "value": "Deger",
            "unit": "Birim",
            "confidence": "Guven",
            "raw": "Ham Metin",
        }
        widths = {"field": 210, "value": 150, "unit": 110, "confidence": 80, "raw": 420}
        for column in columns:
            self.fields_tree.heading(column, text=headings[column])
            self.fields_tree.column(
                column, width=widths[column], anchor="w", stretch=column == "raw"
            )
        self.fields_tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(tab, orient="vertical", command=self.fields_tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.fields_tree.configure(yscrollcommand=scrollbar.set)

        self.fields_tree.tag_configure(
            "critical_confidence", background=_RED_BG, foreground=_RED_FG
        )
        self.fields_tree.tag_configure("low_confidence", background=_AMBER_BG, foreground=_AMBER_FG)

        ttk.Label(
            tab,
            text=(
                "Kirmizi: guven < 0.40 (zorunlu manuel kontrol); "
                "amber: guven < 0.60 (insan onayi gerekli)."
            ),
            foreground="#35506B",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

    def _build_discrepancies_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=8)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        self.notebook.add(tab, text="Uyusmazliklar")

        columns = ("field", "reported", "calculated", "delta", "tolerance", "status", "message")
        self.discrepancies_tree = ttk.Treeview(tab, columns=columns, show="headings")
        headings = {
            "field": "Alan",
            "reported": "Rapor",
            "calculated": "Hesap",
            "delta": "Fark",
            "tolerance": "Tolerans",
            "status": "Durum",
            "message": "Mesaj",
        }
        widths = {
            "field": 150,
            "reported": 90,
            "calculated": 90,
            "delta": 80,
            "tolerance": 120,
            "status": 110,
            "message": 380,
        }
        for column in columns:
            self.discrepancies_tree.heading(column, text=headings[column])
            self.discrepancies_tree.column(
                column, width=widths[column], anchor="w", stretch=column == "message"
            )
        self.discrepancies_tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(tab, orient="vertical", command=self.discrepancies_tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.discrepancies_tree.configure(yscrollcommand=scrollbar.set)

        self.discrepancies_tree.tag_configure("blocking", background=_RED_BG, foreground=_RED_FG)
        self.discrepancies_tree.tag_configure("warning", background=_AMBER_BG, foreground=_AMBER_FG)

        ttk.Label(
            tab,
            text=(
                "Kirmizi: engelleyici uyusmazlik (rapor/hesap farki veya raporda eksik alan); "
                "amber: uyari. Hesaplanan deger verilmemisse durum 'Hesap yok' olur."
            ),
            foreground="#35506B",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

    def _build_warnings_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=8)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        self.notebook.add(tab, text="Uyarilar")

        self.warnings_text = ScrolledText(tab, wrap="word", height=18)
        self.warnings_text.grid(row=0, column=0, sticky="nsew")
        self.warnings_text.configure(state="disabled")

    # ------------------------------------------------------------------
    # Kullanici eylemleri
    # ------------------------------------------------------------------

    def _browse_report(self) -> None:
        patterns = " ".join(f"*{extension}" for extension in sorted(SUPPORTED_EXTENSIONS))
        selected = filedialog.askopenfilename(
            parent=self._dialog,
            title="Test Raporunu Sec",
            filetypes=[
                ("Desteklenen raporlar", patterns),
                ("PDF", "*.pdf"),
                ("Excel", "*.xlsx *.xls"),
                ("Goruntuler", "*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp"),
                ("Tum dosyalar", "*.*"),
            ],
        )
        if not selected:
            return
        self.path_var.set(selected)
        self.analysis_status_var.set("Dosya secildi. 'Analiz Et' ile kontrolu baslatin.")

    def _start_analysis(self) -> None:
        if self._analysis_running or self._destroyed:
            return

        path = self.path_var.get().strip()
        if not path:
            messagebox.showwarning(
                "Rapor Secilmedi",
                "Once bir PDF, Excel veya goruntu dosyasi secin.",
                parent=self._dialog,
            )
            return

        suffix = Path(path).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            messagebox.showwarning(
                "Desteklenmeyen Dosya",
                (
                    f"Desteklenmeyen dosya turu: {suffix or '(uzantisiz)'}.\n"
                    f"Desteklenen: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
                ),
                parent=self._dialog,
            )
            return

        payload = None
        if self.compare_var.get() and self._calculated_payload:
            payload = dict(self._calculated_payload)

        if self._cancel_event is not None:
            self._cancel_event.set()
        cancel_event = threading.Event()
        self._cancel_event = cancel_event
        self._generation += 1
        token = self._generation
        self._analysis_running = True
        self.analysis_button.configure(state="disabled")
        self.browse_button.configure(state="disabled")
        self.compare_check.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.analysis_status_var.set("Analiz ediliyor... Rapor okunuyor, lutfen bekleyin.")

        worker = threading.Thread(
            target=self._worker,
            args=(token, path, payload, cancel_event),
            name="ocr-report-analysis",
            daemon=True,
        )
        worker.start()

    def _cancel_analysis(self) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()
        if not self._analysis_running:
            return
        self._generation += 1
        self._analysis_running = False
        self.analysis_button.configure(state="normal")
        self.browse_button.configure(state="normal")
        self.compare_check.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self.analysis_status_var.set("Analiz kullanici tarafindan iptal edildi.")

    def _worker(
        self,
        token: int,
        path: str,
        payload: dict[str, Any] | None,
        cancel_event: threading.Event | None = None,
    ) -> None:
        """Run the analyzer off the Tk thread; only the queue is touched."""
        call_kwargs: dict[str, Any] = {}
        if cancel_event is not None:
            try:
                sig = inspect.signature(self._analyzer)
            except (TypeError, ValueError):
                sig = None
            if sig is not None and (
                "cancel_event" in sig.parameters
                or any(
                    param.kind == inspect.Parameter.VAR_KEYWORD for param in sig.parameters.values()
                )
            ):
                call_kwargs["cancel_event"] = cancel_event
        try:
            result = self._analyzer(path, payload, **call_kwargs)
        except Exception as exc:  # noqa: BLE001 - hata ana thread'de gosterilir
            self._events.put(("error", token, exc))
        else:
            self._events.put(("result", token, result))

    def _save_json(self) -> None:
        if self._result is None:
            messagebox.showwarning(
                "Sonuc Yok",
                "JSON kaydetmek icin once bir rapor analiz edin.",
                parent=self._dialog,
            )
            return

        initial_name = f"{Path(self._result.path).stem}_ocr_kontrol.json"
        target = filedialog.asksaveasfilename(
            parent=self._dialog,
            title="OCR Kontrol Sonucunu Kaydet",
            defaultextension=".json",
            initialfile=initial_name,
            filetypes=[("JSON", "*.json"), ("Tum dosyalar", "*.*")],
        )
        if not target:
            return

        try:
            content = json.dumps(self._result.to_dict(), ensure_ascii=False, indent=2)
            Path(target).write_text(content + "\n", encoding="utf-8")
        except (OSError, TypeError, ValueError) as exc:
            messagebox.showerror(
                "Kaydetme Hatasi",
                f"OCR kontrol sonucu kaydedilemedi:\n{exc}",
                parent=self._dialog,
            )
            return

        self.analysis_status_var.set("JSON kaydedildi.")
        messagebox.showinfo(
            "Kaydedildi",
            f"OCR kontrol sonucu kaydedildi:\n{target}",
            parent=self._dialog,
        )

    def _on_close(self) -> None:
        if self._analysis_running and not messagebox.askyesno(
            "Analiz Suruyor",
            "Rapor analizi halen suruyor. Kapatmak istediginize emin misiniz?",
            parent=self._dialog,
        ):
            return
        self._close_dialog()

    def _close_dialog(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        if self._cancel_event is not None:
            self._cancel_event.set()
        self._generation += 1
        if self._poll_job is not None:
            try:
                self._dialog.after_cancel(self._poll_job)
            except tk.TclError:
                pass
            self._poll_job = None
        try:
            self._dialog.destroy()
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Ana Tk thread tarafi: worker olaylarini isle
    # ------------------------------------------------------------------

    def _poll_queue(self) -> None:
        self._poll_job = None
        if self._destroyed or not self._dialog_exists():
            return
        self._drain_events()
        if not self._destroyed and self._dialog_exists():
            self._poll_job = self._dialog.after(POLL_INTERVAL_MS, self._poll_queue)

    def _drain_events(self) -> None:
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                return
            if not event:
                continue
            kind = str(event[0])
            token = event[1] if len(event) > 1 else -1
            payload = event[2] if len(event) > 2 else None
            if self._destroyed or token != self._generation:
                # Diyalog kapandi veya yeni bir analiz basladi; eski sonucu yoksay.
                continue
            if kind == "result":
                self._apply_result(payload)
            elif kind == "error":
                self._apply_error(payload)

    def _dialog_exists(self) -> bool:
        try:
            return bool(self._dialog.winfo_exists())
        except tk.TclError:
            return False

    # ------------------------------------------------------------------
    # Sonuc/hata uygulama (testler bu metotlari dogrudan cagirabilir)
    # ------------------------------------------------------------------

    def _apply_result(self, result: OcrAnalysisResult) -> None:
        if self._destroyed:
            return
        self._result = result
        self._analysis_running = False
        self.analysis_button.configure(state="normal")
        self.browse_button.configure(state="normal")
        self.compare_check.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self.save_json_button.configure(state="normal")
        self.analysis_status_var.set("Analiz tamamlandi. Sonuclar insan onayina sunulmalidir.")
        self._render_summary(result)
        self._render_fields(result)
        self._render_discrepancies(result)
        self._render_warnings(result)

    def _apply_error(self, error: BaseException) -> None:
        if self._destroyed:
            return
        self._analysis_running = False
        self.analysis_button.configure(state="normal")
        self.browse_button.configure(state="normal")
        self.compare_check.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self.save_json_button.configure(state="normal" if self._result is not None else "disabled")
        self.analysis_status_var.set("Analiz basarisiz. Hata mesajini kontrol edin.")

        if isinstance(error, ReportOcrError):
            message = f"{error.message}\n\nHata kodu: {error.code}"
            if error.detail:
                message += f"\nAyrinti: {error.detail}"
        else:
            message = f"Beklenmeyen hata: {error}"
        messagebox.showerror("OCR Rapor Kontrolu", message, parent=self._dialog)

    def _render_summary(self, result: OcrAnalysisResult) -> None:
        blocking = sum(1 for item in result.discrepancies if item.is_blocking)
        self.summary_vars["file"].set(result.path)
        self.summary_vars["source"].set(_SOURCE_LABELS.get(result.source, result.source or "-"))
        self.summary_vars["pages"].set(str(result.page_count))
        self.summary_vars["characters"].set(str(result.character_count))
        self.summary_vars["confidence"].set(f"{result.confidence:.0%}")
        if result.needs_human_review:
            self.summary_vars["needs_review"].set(
                "EVET - resmi kabul icin yetkili personel onayi zorunlu"
            )
            self.review_banner.configure(
                text=(
                    "INSAN ONAYI GEREKLIDIR: OCR/alan cikarimi tek basina kabul "
                    "karari degildir. Tum alanlari ve uyusmazliklari kontrol edin."
                ),
                bg=_RED_BG,
                fg=_RED_FG,
            )
        else:
            self.summary_vars["needs_review"].set("Hayir - yine de kontrol onerilir")
            self.review_banner.configure(
                text=(
                    "Otomatik kontrol tamamlandi; resmi kabul yine yetkili personel "
                    "onayina tabidir."
                ),
                bg=_INFO_BG,
                fg=_INFO_FG,
            )
        self.summary_vars["discrepancies"].set(
            f"{len(result.discrepancies)} karsilastirma, {blocking} engelleyici"
        )
        self.summary_vars["warnings"].set(
            f"{len(result.warnings)} uyari, {len(result.issues)} sema sorunu"
        )

    def _render_fields(self, result: OcrAnalysisResult) -> None:
        for item in self.fields_tree.get_children():
            self.fields_tree.delete(item)

        for key, field in result.report.iter_fields():
            confidence = float(field.confidence)
            tags: tuple[str, ...] = ()
            if confidence < CRITICAL_CONFIDENCE_THRESHOLD:
                tags = ("critical_confidence",)
            elif confidence < LOW_CONFIDENCE_THRESHOLD:
                tags = ("low_confidence",)
            self.fields_tree.insert(
                "",
                "end",
                iid=key,
                values=(
                    FIELD_LABELS.get(key, key),
                    _format_value(field.value),
                    field.unit or "-",
                    _format_confidence(confidence),
                    field.raw_text or "-",
                ),
                tags=tags,
            )

    def _render_discrepancies(self, result: OcrAnalysisResult) -> None:
        for item in self.discrepancies_tree.get_children():
            self.discrepancies_tree.delete(item)

        for index, discrepancy in enumerate(result.discrepancies):
            if discrepancy.is_blocking:
                tags: tuple[str, ...] = ("blocking",)
            elif discrepancy.severity == "warning":
                tags = ("warning",)
            elif discrepancy.severity == "critical":
                tags = ("blocking",)
            else:
                tags = ()
            self.discrepancies_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    discrepancy.label,
                    _format_value(discrepancy.reported),
                    _format_value(discrepancy.calculated),
                    _format_delta(discrepancy.delta),
                    discrepancy.tolerance or "-",
                    _STATUS_LABELS.get(discrepancy.status, discrepancy.status),
                    discrepancy.message,
                ),
                tags=tags,
            )

    def _render_warnings(self, result: OcrAnalysisResult) -> None:
        lines: list[str] = []
        lines.append("Uyarilar")
        lines.append("-" * 72)
        if result.warnings:
            lines.extend(f"- {warning}" for warning in result.warnings)
        else:
            lines.append("- Uyari yok.")

        lines.extend(["", "Sema ve tutarlilik sorunlari", "-" * 72])
        if result.issues:
            for issue in result.issues:
                field_label = FIELD_LABELS.get(issue.field, issue.field) if issue.field else "-"
                lines.append(f"- [{issue.severity}] {field_label} ({issue.code}): {issue.message}")
        else:
            lines.append("- Sema sorunu yok.")

        if result.needs_human_review:
            lines.extend(
                [
                    "",
                    "NOT: Bu cikti resmi kabul raporu degildir; insan onayi olmadan kullanilamaz.",
                ]
            )

        self.warnings_text.configure(state="normal")
        self.warnings_text.delete("1.0", "end")
        self.warnings_text.insert("1.0", "\n".join(lines) + "\n")
        self.warnings_text.configure(state="disabled")

    def _refresh_compare_hint(self) -> None:
        if self._calculated_payload:
            self.compare_hint_var.set(
                "Aktif test formundan "
                f"{len(self._calculated_payload)} hesaplanan deger kullanilacak. "
                "Kapatirsaniz yalnizca rapor alanlari okunur."
            )
        else:
            self.compare_hint_var.set(
                "Hesaplanan deger bulunamadi; yalnizca rapor alanlari okunacak."
            )

    def wait(self) -> OcrAnalysisResult | None:
        """Diyalog kapanana kadar Tk dongusunu calistirir."""
        if not self._destroyed and self._dialog_exists():
            self._dialog.wait_window()
        return self._result


__all__ = [
    "CRITICAL_CONFIDENCE_THRESHOLD",
    "LOW_CONFIDENCE_THRESHOLD",
    "POLL_INTERVAL_MS",
    "ReportOcrDialog",
]

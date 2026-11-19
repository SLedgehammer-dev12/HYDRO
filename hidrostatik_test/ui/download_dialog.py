from __future__ import annotations

import math
import queue
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from ..services.download_manager import DownloadManager, DownloadStatus, DownloadTask

# Worker thread'den gelen olaylar bu aralikla ana Tk thread'inde tuketilir.
POLL_INTERVAL_MS = 120

_TERMINAL_STATUSES = frozenset(
    {
        DownloadStatus.COMPLETED,
        DownloadStatus.FAILED,
        DownloadStatus.CANCELLED,
    }
)


def _isfinite(value: object) -> bool:
    if not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def _format_size(bytes_val: float) -> str:
    """Boyutu B/KB/MB/GB olarak bicimler; negatif ve nan/inf icin guvenlidir."""
    if not _isfinite(bytes_val):
        return "--"
    size = max(0.0, float(bytes_val))
    if size < 1024:
        return f"{size:.0f} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    if size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    return f"{size / (1024 * 1024 * 1024):.2f} GB"


def _format_speed(bps: float) -> str:
    if not _isfinite(bps):
        return "--"
    return _format_size(bps) + "/s"


def _format_eta(seconds: float) -> str:
    """Kalan sureyi sn/dk/sa olarak bicimler; negatif ve nan/inf icin '--' doner."""
    if not _isfinite(seconds) or seconds <= 0:
        return "--"
    total = float(seconds)
    if total < 60:
        return f"{int(total)} sn"
    if total < 3600:
        return f"{int(total // 60)} dk {int(total % 60)} sn"
    return f"{int(total // 3600)} sa {int((total % 3600) // 60)} dk"


def _require_download_manager(download_manager: object) -> DownloadManager:
    """Sinif gecilmesi gibi yaygin kullanim hatasini anlasilir bicimde reddeder."""
    if isinstance(download_manager, type):
        raise TypeError(
            "DownloadDialog: download_manager parametresi DownloadManager instance'i bekler "
            "(ornegin DownloadManager()). Sinif gecmeyin."
        )
    required_methods = ("enqueue", "start", "remove")
    missing = [
        name for name in required_methods if not callable(getattr(download_manager, name, None))
    ]
    if missing:
        raise TypeError(
            "DownloadDialog: download_manager DownloadManager instance'i olmalidir. "
            f"Eksik metotlar: {', '.join(missing)}"
        )
    return download_manager  # type: ignore[return-value]


class DownloadDialog:
    """Indirme ilerlemesini gosteren modal diyalog.

    Worker thread Tk widget'larina dokunmaz; olaylar ``queue.Queue`` uzerinden
    ana thread'de calisan periyodik ``after`` yoklamasi ile islenir.
    """

    def __init__(
        self,
        parent: tk.Misc,
        download_manager: DownloadManager,
        file_url: str,
        file_name: str,
        dest_path: Path,
        total_bytes: int = 0,
        title: str = "Guncelleme Indiriliyor",
        expected_sha256: str = "",
    ) -> None:
        self._manager = _require_download_manager(download_manager)
        self._file_url = file_url
        self._file_name = file_name
        self._dest_path = dest_path
        self._events: queue.Queue[tuple[object, ...]] = queue.Queue()
        self._poll_job: str | None = None
        self._finished = False
        self._destroyed = False

        self._paused = False
        self._cancelled = False
        self._result: str | None = None

        self._dialog = tk.Toplevel(parent)
        self._dialog.title(title)
        self._dialog.geometry("480x200")
        self._dialog.resizable(False, False)
        self._dialog.transient(parent)  # type: ignore[arg-type]
        try:
            self._dialog.grab_set()
        except tk.TclError:
            # Bazi platformlarda (ornegin baska bir grab varken) grab kurulamaz;
            # indirme yine de calisir, bu yuzden diyalogu kapatmiyoruz.
            pass

        self._task = DownloadTask(
            url=file_url,
            destination=dest_path,
            total_bytes=total_bytes,
            expected_sha256=expected_sha256,
        )

        self._build_ui()

        self._manager.enqueue(self._task)

        self._dialog.protocol("WM_DELETE_WINDOW", self._on_close)
        self._start_download()
        self._poll_job = self._dialog.after(POLL_INTERVAL_MS, self._poll_queue)

    def _build_ui(self) -> None:
        frame = ttk.Frame(self._dialog, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Dosya:", font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        self._file_label = ttk.Label(frame, text=self._file_name, foreground="#35506B")
        self._file_label.grid(row=0, column=1, sticky="w", pady=(0, 4))

        ttk.Label(frame, text="Boyut:", font=("Segoe UI", 9, "bold")).grid(
            row=1, column=0, sticky="w", pady=(0, 4)
        )
        self._size_label = ttk.Label(frame, text=_format_size(self._task.total_bytes))
        self._size_label.grid(row=1, column=1, sticky="w", pady=(0, 4))

        self._progress_bar = ttk.Progressbar(frame, length=400, mode="determinate")
        self._progress_bar.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 4))

        self._percent_label = ttk.Label(frame, text="%0")
        self._percent_label.grid(row=3, column=0, sticky="w")

        info_frame = ttk.Frame(frame)
        info_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(4, 8))
        info_frame.columnconfigure(1, weight=1)

        self._speed_label = ttk.Label(info_frame, text="Hiz: --")
        self._speed_label.pack(side="left")

        self._eta_label = ttk.Label(info_frame, text="Kalan: --")
        self._eta_label.pack(side="right")

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=5, column=0, columnspan=2, sticky="ew")
        btn_frame.columnconfigure(0, weight=1)

        self._pause_btn = ttk.Button(btn_frame, text="Duraklat", command=self._toggle_pause)
        self._pause_btn.pack(side="left")

        self._cancel_btn = ttk.Button(btn_frame, text="Iptal", command=self._on_cancel)
        self._cancel_btn.pack(side="left", padx=(8, 0))

        self._status_label = ttk.Label(frame, text="Bekleniyor...", foreground="#16365D")
        self._status_label.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(8, 0))

    def _start_download(self) -> None:
        self._manager.start(
            self._task,
            on_progress=self._on_progress,
            on_complete=self._on_complete,
            on_error=self._on_error,
        )

    # --- Worker thread tarafi: sadece kuyruga yazilir, Tk'ya dokunulmaz ---

    def _on_progress(
        self, dest: Path, downloaded: int, total: int, speed: float, eta: float
    ) -> None:
        self._events.put(("progress", downloaded, total, speed, eta))

    def _on_complete(self, dest: Path) -> None:
        self._events.put(("complete",))

    def _on_error(self, dest: Path, error: str) -> None:
        self._events.put(("error", error))

    # --- Ana Tk thread tarafi ---

    def _poll_queue(self) -> None:
        self._poll_job = None
        if self._destroyed:
            return
        if not self._dialog_exists():
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
            kind = event[0] if event else ""
            if kind == "progress":
                self._update_ui(*event[1:])  # type: ignore[arg-type]
            elif kind == "complete":
                self._handle_complete()
            elif kind == "error":
                self._handle_error(str(event[1]) if len(event) > 1 else "Bilinmeyen hata")

    def _dialog_exists(self) -> bool:
        try:
            return bool(self._dialog.winfo_exists())
        except tk.TclError:
            return False

    def _update_ui(self, downloaded: int, total: int, speed: float, eta: float) -> None:
        if self._destroyed or self._finished:
            return
        percent = (downloaded / total * 100) if total and total > 0 else 0.0
        percent = max(0.0, min(100.0, percent))
        self._progress_bar["value"] = percent
        self._progress_bar["maximum"] = 100
        self._percent_label.configure(text=f"%{percent:.1f}")
        self._speed_label.configure(text=f"Hiz: {_format_speed(speed)}")
        self._eta_label.configure(text=f"Kalan: {_format_eta(eta)}")
        self._size_label.configure(text=f"{_format_size(downloaded)} / {_format_size(total)}")
        self._status_label.configure(text="Indiriliyor...")

    def _handle_complete(self) -> None:
        if self._destroyed or self._finished:
            return
        self._finished = True
        self._status_label.configure(text="Indirme tamamlandi.")
        self._progress_bar["value"] = 100
        self._pause_btn.configure(state="disabled")
        self._cancel_btn.configure(text="Kapat", command=self._close_dialog)
        self._result = "completed"

    def _handle_error(self, error: str) -> None:
        if self._destroyed or self._finished:
            return
        self._finished = True
        self._status_label.configure(text=f"Hata: {error}")
        self._pause_btn.configure(state="disabled")
        self._cancel_btn.configure(text="Kapat", command=self._close_dialog)
        retry = messagebox.askretrycancel(
            "Indirme Hatasi",
            f"Dosya indirilemedi.\n{error}\n\nYeniden denemek ister misiniz?",
        )
        if retry and not self._destroyed:
            remover = getattr(self._manager, "remove", None)
            if callable(remover):
                remover(self._dest_path)
            try:
                if self._dest_path.exists():
                    self._dest_path.unlink()
            except OSError:
                pass
            self._task.total_bytes = 0
            self._task.downloaded_bytes = 0
            self._task.status = DownloadStatus.PENDING
            self._task.error_message = ""
            self._task.start_time = 0.0
            self._pause_btn.configure(state="normal")
            self._cancel_btn.configure(text="Iptal", command=self._on_cancel)
            self._progress_bar["value"] = 0
            self._percent_label.configure(text="%0")
            self._speed_label.configure(text="Hiz: --")
            self._eta_label.configure(text="Kalan: --")
            self._status_label.configure(text="Yeniden deneniyor...")
            self._finished = False
            self._start_download()
        else:
            self._result = "error"

    def _toggle_pause(self) -> None:
        if self._finished:
            return
        if self._paused:
            resumed = self._manager.resume(
                self._dest_path,
                on_progress=self._on_progress,
                on_complete=self._on_complete,
                on_error=self._on_error,
            )
            if resumed:
                self._paused = False
                self._pause_btn.configure(text="Duraklat")
                self._status_label.configure(text="Devam ediyor...")
            else:
                self._status_label.configure(
                    text="Indirme durdurulamadi; yeniden baslatmayi deneyin."
                )
        else:
            if self._manager.pause(self._dest_path):
                self._paused = True
                self._pause_btn.configure(text="Devam Et")
                self._status_label.configure(text="Duraklatildi.")
            else:
                self._status_label.configure(text="Indirme su anda duraklatilamaz.")

    def _on_cancel(self) -> None:
        if self._finished:
            self._close_dialog()
            return
        sure = messagebox.askyesno(
            "Iptal",
            "Indirme islemini iptal etmek istediginize emin misiniz?",
        )
        if not sure:
            return
        self._cancel_download()

    def _cancel_download(self) -> None:
        if self._finished:
            return
        self._finished = True
        self._cancelled = True
        self._manager.cancel(self._dest_path)
        self._status_label.configure(text="Iptal edildi.")
        self._pause_btn.configure(state="disabled")
        self._cancel_btn.configure(text="Kapat", command=self._close_dialog)
        self._result = "cancelled"

    def _is_terminal_status(self) -> bool:
        if self._task.status in _TERMINAL_STATUSES:
            return True
        getter = getattr(self._manager, "get_status", None)
        if callable(getter):
            try:
                return getter(self._dest_path) in _TERMINAL_STATUSES
            except Exception:
                return False
        return False

    def _on_close(self) -> None:
        # Tamamlanmis, hatali veya iptal edilmis iste kapatma onayi sorulmaz.
        if self._finished or self._is_terminal_status():
            self._close_dialog()
            return
        if not messagebox.askyesno(
            "Iptal",
            "Indirme islemini iptal etmek istediginize emin misiniz?",
        ):
            return
        self._cancel_download()
        self._close_dialog()

    def _close_dialog(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        if self._poll_job is not None:
            try:
                self._dialog.after_cancel(self._poll_job)
            except tk.TclError:
                pass
            self._poll_job = None
        remover = getattr(self._manager, "remove", None)
        if callable(remover):
            remover(self._dest_path)
        try:
            self._dialog.destroy()
        except tk.TclError:
            pass

    def wait(self) -> str | None:
        """Diyalog kapanana kadar Tk dongusunu calistirir ve sonucu dondurur."""
        if not self._destroyed and self._dialog_exists():
            self._dialog.wait_window()
        return self._result

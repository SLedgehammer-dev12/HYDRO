from __future__ import annotations

import threading
import time
from pathlib import Path
from tkinter import messagebox, ttk
import tkinter as tk

from ..services.download_manager import DownloadManager, DownloadStatus


def _format_size(bytes_val: float) -> str:
    if bytes_val < 1024:
        return f"{bytes_val:.0f} B"
    elif bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.1f} KB"
    elif bytes_val < 1024 * 1024 * 1024:
        return f"{bytes_val / (1024 * 1024):.1f} MB"
    return f"{bytes_val / (1024 * 1024 * 1024):.2f} GB"


def _format_speed(bps: float) -> str:
    return _format_size(bps) + "/s"


def _format_eta(seconds: float) -> str:
    if seconds <= 0 or not _isfinite(seconds):
        return "--"
    if seconds < 60:
        return f"{int(seconds)} sn"
    elif seconds < 3600:
        return f"{int(seconds // 60)} dk {int(seconds % 60)} sn"
    return f"{int(seconds // 3600)} sa {int((seconds % 3600) // 60)} dk"


def _isfinite(value: float) -> bool:
    import math
    return math.isfinite(value)


class DownloadDialog:
    def __init__(
        self,
        parent: tk.Misc,
        download_manager: DownloadManager,
        file_url: str,
        file_name: str,
        dest_path: Path,
        total_bytes: int = 0,
        title: str = "Guncelleme Indiriliyor",
    ) -> None:
        self._manager = download_manager
        self._file_url = file_url
        self._file_name = file_name
        self._dest_path = dest_path
        self._completed = threading.Event()

        self._dialog = tk.Toplevel(parent)
        self._dialog.title(title)
        self._dialog.geometry("480x200")
        self._dialog.resizable(False, False)
        self._dialog.transient(parent)  # type: ignore[arg-type]
        self._dialog.grab_set()

        self._paused = False
        self._cancelled = False
        self._result: str | None = None

        self._build_ui()

        self._task = download_manager.DownloadTask(
            url=file_url,
            destination=dest_path,
            total_bytes=total_bytes,
        )
        self._manager.enqueue(self._task)

        self._dialog.protocol("WM_DELETE_WINDOW", self._on_close)
        self._start_download()

    def _build_ui(self) -> None:
        frame = ttk.Frame(self._dialog, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Dosya:", font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        self._file_label = ttk.Label(
            frame, text=self._file_name, foreground="#35506B"
        )
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

        self._pause_btn = ttk.Button(
            btn_frame, text="Duraklat", command=self._toggle_pause
        )
        self._pause_btn.pack(side="left")

        self._cancel_btn = ttk.Button(
            btn_frame, text="Iptal", command=self._on_cancel
        )
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

    def _on_progress(
        self, dest: Path, downloaded: int, total: int, speed: float, eta: float
    ) -> None:
        self._dialog.after(0, self._update_ui, downloaded, total, speed, eta)

    def _update_ui(self, downloaded: int, total: int, speed: float, eta: float) -> None:
        if self._cancelled:
            return
        percent = (downloaded / total * 100) if total > 0 else 0
        self._progress_bar["value"] = percent
        self._progress_bar["maximum"] = 100
        self._percent_label.configure(text=f"%{percent:.1f}")
        self._speed_label.configure(text=f"Hiz: {_format_speed(speed)}")
        self._eta_label.configure(text=f"Kalan: {_format_eta(eta)}")
        self._size_label.configure(
            text=f"{_format_size(downloaded)} / {_format_size(total)}"
        )
        self._status_label.configure(text="Indiriliyor...")

    def _on_complete(self, dest: Path) -> None:
        self._dialog.after(0, self._handle_complete)

    def _handle_complete(self) -> None:
        if self._cancelled:
            return
        self._status_label.configure(text="Indirme tamamlandi.")
        self._progress_bar["value"] = 100
        self._pause_btn.configure(state="disabled")
        self._cancel_btn.configure(text="Kapat", command=self._close_dialog)
        self._result = "completed"
        self._completed.set()

    def _on_error(self, dest: Path, error: str) -> None:
        self._dialog.after(0, self._handle_error, error)

    def _handle_error(self, error: str) -> None:
        if self._cancelled:
            return
        self._status_label.configure(text=f"Hata: {error}")
        self._pause_btn.configure(state="disabled")
        self._cancel_btn.configure(text="Kapat")
        retry = messagebox.askretrycancel(
            "Indirme Hatasi",
            f"Dosya indirilemedi.\n{error}\n\nYeniden denemek ister misiniz?",
        )
        if retry:
            self._manager.remove(self._dest_path)
            if self._dest_path.exists():
                self._dest_path.unlink()
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
            self._start_download()
        else:
            self._result = "error"
            self._completed.set()

    def _toggle_pause(self) -> None:
        if self._paused:
            self._manager.resume(self._dest_path, on_progress=self._on_progress)
            self._paused = False
            self._pause_btn.configure(text="Duraklat")
            self._status_label.configure(text="Devam ediyor...")
        else:
            self._manager.pause(self._dest_path)
            self._paused = True
            self._pause_btn.configure(text="Devam Et")
            self._status_label.configure(text="Duraklatildi.")

    def _on_cancel(self) -> None:
        sure = messagebox.askyesno(
            "Iptal",
            "Indirme islemini iptal etmek istediginize emin misiniz?",
        )
        if not sure:
            return
        self._cancelled = True
        self._manager.cancel(self._dest_path)
        self._status_label.configure(text="Iptal edildi.")
        self._pause_btn.configure(state="disabled")
        self._cancel_btn.configure(text="Kapat")
        self._result = "cancelled"
        self._completed.set()

    def _on_close(self) -> None:
        if self._task.status in (
            DownloadStatus.COMPLETED,
            DownloadStatus.FAILED,
            DownloadStatus.CANCELLED,
        ):
            self._close_dialog()
        else:
            self._on_cancel()

    def _close_dialog(self) -> None:
        self._manager.remove(self._dest_path)
        self._dialog.destroy()

    def wait(self) -> str | None:
        self._dialog.wait_window()
        return self._result

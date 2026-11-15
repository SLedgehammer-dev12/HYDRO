from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, replace
from enum import Enum, auto
from pathlib import Path
from threading import Event, RLock, Thread
from typing import Any, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CHUNK_SIZE = 8192
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2.0


class DownloadStatus(Enum):
    PENDING = auto()
    CONNECTING = auto()
    DOWNLOADING = auto()
    PAUSED = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


@dataclass
class DownloadTask:
    url: str
    destination: Path
    expected_sha256: str = ""
    total_bytes: int = 0
    downloaded_bytes: int = 0
    status: DownloadStatus = DownloadStatus.PENDING
    error_message: str = ""
    start_time: float = 0.0
    speed_bps: float = 0.0
    eta_seconds: float = 0.0
    platform: str = ""


class ProgressCallback(Protocol):
    def __call__(
        self,
        destination: Path,
        downloaded: int,
        total: int,
        speed: float,
        eta: float,
    ) -> None: ...


_TERMINAL_STATUSES = frozenset(
    {
        DownloadStatus.COMPLETED,
        DownloadStatus.FAILED,
        DownloadStatus.CANCELLED,
    }
)


class DownloadManager:
    """Tek yazicili (single writer) indirme yoneticisi.

    Her hedef dosya icin en fazla bir worker thread calisir. ``resume`` yeni bir
    thread acmaz; duraklatilmis worker'i uyandirir. Bu sayede ayni dosyaya iki
    thread'in ayni anda yazmasi (bozuk indirme) engellenir.

    ``DownloadTask`` alanlari yonetici kilidi altinda guncellenir. ``get_task``
    paylasilan nesneyi degil, o anki durumun kopyasini dondurur.
    """

    def __init__(self, delete_partial_on_cancel: bool = False) -> None:
        self._tasks: dict[Path, DownloadTask] = {}
        self._lock = RLock()
        self._pause_events: dict[Path, Event] = {}
        self._cancel_events: dict[Path, Event] = {}
        self._threads: dict[Path, Thread] = {}
        self._callbacks: dict[Path, dict[str, Any]] = {}
        self._cancel_cleanup: dict[Path, bool] = {}
        self.delete_partial_on_cancel = delete_partial_on_cancel

    # --- Public API ---

    def enqueue(self, task: DownloadTask) -> DownloadTask:
        with self._lock:
            self._tasks[task.destination] = task
        return task

    def start(
        self,
        task: DownloadTask,
        on_progress: ProgressCallback | None = None,
        on_complete: Callable[[Path], None] | None = None,
        on_error: Callable[[Path, str], None] | None = None,
    ) -> Thread:
        """Ilk indirmeyi baslatir veya bitmis isi yeniden dener.

        Ayni hedef icin yasayan bir worker varsa yeni thread acilmaz; mevcut
        thread dondurulur. Boylece ``start`` yanlislikla ikinci bir yazici
        olusturamaz. Duraklatilmis bir isi surdurmek icin ``resume`` kullanin.
        """
        with self._lock:
            existing = self._threads.get(task.destination)
            if existing is not None and existing.is_alive():
                return existing

            pause_event = Event()
            cancel_event = Event()
            callbacks = {
                "on_progress": on_progress,
                "on_complete": on_complete,
                "on_error": on_error,
            }
            self._tasks[task.destination] = task
            self._pause_events[task.destination] = pause_event
            self._cancel_events[task.destination] = cancel_event
            self._callbacks[task.destination] = callbacks
            self._cancel_cleanup.pop(task.destination, None)
            thread = Thread(
                target=self._download_worker,
                args=(task, pause_event, cancel_event, callbacks),
                name=f"download-{task.destination.name}",
                daemon=True,
            )
            self._threads[task.destination] = thread

        thread.start()
        return thread

    def pause(self, destination: Path) -> bool:
        with self._lock:
            task = self._tasks.get(destination)
            event = self._pause_events.get(destination)
            if task is None or event is None:
                return False
            if task.status in _TERMINAL_STATUSES:
                return False
            if not self._worker_alive(destination):
                return False
            if task.status == DownloadStatus.PAUSED:
                return True
            task.status = DownloadStatus.PAUSED
            event.set()
        return True

    def resume(
        self,
        destination: Path,
        on_progress: ProgressCallback | None = None,
        on_complete: Callable[[Path], None] | None = None,
        on_error: Callable[[Path, str], None] | None = None,
    ) -> bool:
        """Duraklatilmis worker'i uyandirir; yeni thread acmaz.

        Zaten calisan worker'in callback'leri korunur; yalnizca verilen
        callback'ler guncellenir. Worker yoksa (ornegin is bitmisse) ``False``
        doner ve cagiran taraf ``start`` ile yeni bir is baslatmalidir.
        """
        with self._lock:
            task = self._tasks.get(destination)
            event = self._pause_events.get(destination)
            if task is None or event is None:
                return False
            if task.status != DownloadStatus.PAUSED:
                return False
            if not self._worker_alive(destination):
                return False

            callbacks = self._callbacks.setdefault(
                destination,
                {"on_progress": None, "on_complete": None, "on_error": None},
            )
            if on_progress is not None:
                callbacks["on_progress"] = on_progress
            if on_complete is not None:
                callbacks["on_complete"] = on_complete
            if on_error is not None:
                callbacks["on_error"] = on_error

            task.status = DownloadStatus.PENDING
            event.clear()
        return True

    def cancel(self, destination: Path, *, delete_partial: bool | None = None) -> bool:
        """Indirmeyi iptal eder.

        ``delete_partial`` verilmezse yoneticinin
        ``delete_partial_on_cancel`` politikasi kullanilir. Yarim dosya silme
        islemi worker'in yazmayi biraktigi noktada (veya worker yoksa hemen)
        yapilir; boylece silinen dosya yeniden olusturulmaz.
        """
        cleanup = self.delete_partial_on_cancel if delete_partial is None else delete_partial
        with self._lock:
            task = self._tasks.get(destination)
            event = self._cancel_events.get(destination)
            if task is None or event is None:
                return False
            if task.status in _TERMINAL_STATUSES:
                # Tamamlanmis/basarisiz bir isin artefaktini iptal gibi silme.
                return task.status == DownloadStatus.CANCELLED
            task.status = DownloadStatus.CANCELLED
            event.set()
            pause_event = self._pause_events.get(destination)
            if pause_event is not None:
                pause_event.set()
            self._cancel_cleanup[destination] = cleanup
            worker_alive = self._worker_alive(destination)

        if not worker_alive:
            self._cleanup_partial(task, cleanup)
        return True

    def get_status(self, destination: Path) -> DownloadStatus | None:
        with self._lock:
            task = self._tasks.get(destination)
            return task.status if task else None

    def get_task(self, destination: Path) -> DownloadTask | None:
        """Gorev durumunun kopyasini dondurur.

        Donen nesne paylasilan kayit degildir; uzerinde yapilan degisiklikler
        yoneticiyi etkilemez.
        """
        with self._lock:
            task = self._tasks.get(destination)
            if task is None:
                return None
            return replace(task)

    def active_worker_count(self, destination: Path | None = None) -> int:
        with self._lock:
            if destination is not None:
                return 1 if self._worker_alive(destination) else 0
            return sum(1 for thread in self._threads.values() if thread.is_alive())

    def remove(self, destination: Path) -> None:
        with self._lock:
            event = self._cancel_events.get(destination)
            if event is not None:
                event.set()
            pause_event = self._pause_events.get(destination)
            if pause_event is not None:
                pause_event.set()
            self._tasks.pop(destination, None)
            self._pause_events.pop(destination, None)
            self._cancel_events.pop(destination, None)
            self._threads.pop(destination, None)
            self._callbacks.pop(destination, None)
            self._cancel_cleanup.pop(destination, None)

    # --- Internal helpers ---

    def _worker_alive(self, destination: Path) -> bool:
        thread = self._threads.get(destination)
        return thread is not None and thread.is_alive()

    @staticmethod
    def _update_task(task: DownloadTask, **fields: object) -> None:
        for key, value in fields.items():
            setattr(task, key, value)

    def _set_status(self, task: DownloadTask, status: DownloadStatus) -> None:
        with self._lock:
            task.status = status

    def _cleanup_partial(self, task: DownloadTask, cleanup: bool) -> None:
        if not cleanup:
            return
        try:
            task.destination.unlink(missing_ok=True)
        except OSError:
            # Windows'ta dosya hala aciksa silme basarisiz olabilir; worker
            # sonlandiginda tekrar denenecegi icin burada yutulur.
            pass

    def _finish_cancelled(self, task: DownloadTask) -> None:
        with self._lock:
            cleanup = self._cancel_cleanup.pop(task.destination, False)
        self._cleanup_partial(task, cleanup)

    # --- Worker ---

    def _download_worker(
        self,
        task: DownloadTask,
        pause_event: Event,
        cancel_event: Event,
        callbacks: dict[str, Any],
    ) -> None:
        retries = 0
        while retries <= MAX_RETRIES:
            if cancel_event.is_set():
                self._finish_cancelled(task)
                return

            if pause_event.is_set():
                self._wait_while_paused(task, pause_event, cancel_event)
                if cancel_event.is_set():
                    self._finish_cancelled(task)
                    return

            try:
                self._do_download(task, pause_event, cancel_event, callbacks.get("on_progress"))
            except (HTTPError, URLError, OSError) as exc:
                retries += 1
                if retries > MAX_RETRIES or cancel_event.is_set():
                    self._fail(task, str(exc), callbacks.get("on_error"))
                    return
                time.sleep(RETRY_BACKOFF_SECONDS * retries)
                continue
            except Exception as exc:
                self._fail(task, str(exc), callbacks.get("on_error"))
                return

            if task.status == DownloadStatus.CANCELLED:
                self._finish_cancelled(task)
                return

            if task.expected_sha256:
                try:
                    actual = _sha256_of(task.destination)
                except OSError as exc:
                    self._fail(
                        task,
                        f"Hash dogrulamasi basarisiz: {exc}",
                        callbacks.get("on_error"),
                    )
                    return
                if actual.lower() != task.expected_sha256.lower():
                    self._fail(
                        task,
                        f"SHA-256 uyusmazligi: beklenen {task.expected_sha256}, alinan {actual}",
                        callbacks.get("on_error"),
                    )
                    return

            self._set_status(task, DownloadStatus.COMPLETED)
            on_complete = callbacks.get("on_complete")
            if on_complete:
                on_complete(task.destination)
            return

        self._fail(
            task,
            "Maksimum yeniden deneme sayisina ulasildi.",
            callbacks.get("on_error"),
        )

    def _fail(
        self,
        task: DownloadTask,
        message: str,
        on_error: Callable[[Path, str], None] | None,
    ) -> None:
        with self._lock:
            task.status = DownloadStatus.FAILED
            task.error_message = message
        if on_error:
            on_error(task.destination, message)

    def _wait_while_paused(
        self, task: DownloadTask, pause_event: Event, cancel_event: Event
    ) -> None:
        self._set_status(task, DownloadStatus.PAUSED)
        # Kucuk zaman asimlariyla dongu: resume ile temizlenip yeniden
        # duraklatilan bir is, uyanir uyanmaz yanlislikla "indiriliyor"
        # durumuna gecmez.
        while pause_event.is_set() and not cancel_event.is_set():
            pause_event.wait(0.2)
        if not cancel_event.is_set():
            self._set_status(task, DownloadStatus.DOWNLOADING)

    def _do_download(
        self,
        task: DownloadTask,
        pause_event: Event,
        cancel_event: Event,
        on_progress: ProgressCallback | None,
    ) -> None:
        self._set_status(task, DownloadStatus.CONNECTING)
        task.destination.parent.mkdir(parents=True, exist_ok=True)

        headers: dict[str, str] = {
            "User-Agent": "HidrostatikTest-updater/1.0",
        }
        resume_pos = 0
        if task.destination.exists() and task.destination.stat().st_size > 0:
            resume_pos = task.destination.stat().st_size
            headers["Range"] = f"bytes={resume_pos}-"

        request = Request(task.url, headers=headers)
        with urlopen(request, timeout=30) as response:
            status_code = getattr(response, "status", None)
            if status_code is None and hasattr(response, "getcode"):
                status_code = response.getcode()
            if resume_pos > 0 and status_code != 206:
                # Sunucu Range'i yok saydiysa dosyayi bastan yaz; ekleme (append)
                # yapmak bozuk bir artefakt uretirdi.
                resume_pos = 0
            total = task.total_bytes or _content_length(response) or 0
            if resume_pos > 0:
                total = max(total, _total_from_content_range(response) or 0)
            else:
                total = _content_length(response) or total
            with self._lock:
                task.total_bytes = total

            if pause_event.is_set():
                self._wait_while_paused(task, pause_event, cancel_event)
                if cancel_event.is_set():
                    return

            mode = "ab" if resume_pos > 0 else "wb"
            self._set_status(task, DownloadStatus.DOWNLOADING)
            with self._lock:
                task.start_time = time.monotonic()
            downloaded = resume_pos

            with task.destination.open(mode) as output:
                while True:
                    if cancel_event.is_set():
                        with self._lock:
                            task.downloaded_bytes = downloaded
                        return
                    if pause_event.is_set():
                        with self._lock:
                            task.downloaded_bytes = downloaded
                        self._wait_while_paused(task, pause_event, cancel_event)
                        if cancel_event.is_set():
                            return

                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    output.write(chunk)
                    downloaded += len(chunk)

                    start_time = task.start_time
                    elapsed = time.monotonic() - start_time
                    speed = downloaded / elapsed if elapsed > 0 else 0.0
                    eta = (total - downloaded) / speed if speed > 0 else 0.0

                    with self._lock:
                        task.downloaded_bytes = downloaded
                        task.speed_bps = speed
                        task.eta_seconds = eta

                    if on_progress:
                        on_progress(task.destination, downloaded, total, speed, eta)

    @staticmethod
    def download_file(
        url: str,
        destination: Path,
        on_progress: ProgressCallback | None = None,
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        headers = {"User-Agent": "HidrostatikTest-updater/1.0"}
        request = Request(url, headers=headers)
        with urlopen(request, timeout=30) as response:
            total = _content_length(response) or 0
            downloaded = 0
            start = time.monotonic()
            with destination.open("wb") as output:
                while True:
                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    output.write(chunk)
                    downloaded += len(chunk)
                    if on_progress and total > 0:
                        elapsed = time.monotonic() - start
                        speed = downloaded / elapsed if elapsed > 0 else 0
                        eta = (total - downloaded) / speed if speed > 0 else 0
                        on_progress(destination, downloaded, total, speed, eta)


def _content_length(response: object) -> int:
    headers = getattr(response, "headers", None)
    length = headers.get("Content-Length") if headers is not None else None
    return int(length) if length else 0


def _total_from_content_range(response: object) -> int:
    headers = getattr(response, "headers", None)
    content_range = headers.get("Content-Range") if headers is not None else None
    if not content_range or "/" not in content_range:
        return 0
    _, _, total = content_range.partition("/")
    return int(total) if total.strip().isdigit() else 0


def _sha256_of(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()

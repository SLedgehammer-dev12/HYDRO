from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Callable, Protocol
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


class DownloadManager:
    def __init__(self) -> None:
        self._tasks: dict[Path, DownloadTask] = {}
        self._lock = Lock()
        self._pause_events: dict[Path, Event] = {}
        self._cancel_events: dict[Path, Event] = {}

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
        pause_event = Event()
        cancel_event = Event()
        with self._lock:
            self._pause_events[task.destination] = pause_event
            self._cancel_events[task.destination] = cancel_event
        thread = Thread(
            target=self._download_worker,
            args=(task, pause_event, cancel_event, on_progress, on_complete, on_error),
            daemon=True,
        )
        thread.start()
        return thread

    def pause(self, destination: Path) -> bool:
        with self._lock:
            task = self._tasks.get(destination)
            event = self._pause_events.get(destination)
            if task is None or event is None:
                return False
            if task.status != DownloadStatus.DOWNLOADING:
                return False
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
        with self._lock:
            task = self._tasks.get(destination)
            event = self._pause_events.get(destination)
            if task is None or event is None:
                return False
            if task.status != DownloadStatus.PAUSED:
                return False
            task.status = DownloadStatus.PENDING
            event.clear()
        self.start(task, on_progress, on_complete, on_error)
        return True

    def cancel(self, destination: Path) -> bool:
        with self._lock:
            task = self._tasks.get(destination)
            event = self._cancel_events.get(destination)
            if task is None or event is None:
                return False
            task.status = DownloadStatus.CANCELLED
            event.set()
            pause_event = self._pause_events.get(destination)
            if pause_event:
                pause_event.set()
        return True

    def get_status(self, destination: Path) -> DownloadStatus | None:
        with self._lock:
            task = self._tasks.get(destination)
            return task.status if task else None

    def get_task(self, destination: Path) -> DownloadTask | None:
        with self._lock:
            return self._tasks.get(destination)

    def remove(self, destination: Path) -> None:
        with self._lock:
            self._tasks.pop(destination, None)
            self._pause_events.pop(destination, None)
            self._cancel_events.pop(destination, None)

    def _download_worker(
        self,
        task: DownloadTask,
        pause_event: Event,
        cancel_event: Event,
        on_progress: ProgressCallback | None,
        on_complete: Callable[[Path], None] | None,
        on_error: Callable[[Path, str], None] | None,
    ) -> None:
        retries = 0
        while retries <= MAX_RETRIES:
            if cancel_event.is_set():
                task.status = DownloadStatus.CANCELLED
                return

            if pause_event.is_set():
                pause_event.wait()
                if cancel_event.is_set():
                    task.status = DownloadStatus.CANCELLED
                    return

            try:
                self._do_download(task, pause_event, cancel_event, on_progress)
            except (HTTPError, URLError, OSError) as exc:
                retries += 1
                if retries > MAX_RETRIES or cancel_event.is_set():
                    task.status = DownloadStatus.FAILED
                    task.error_message = str(exc)
                    if on_error:
                        on_error(task.destination, str(exc))
                    return
                time.sleep(RETRY_BACKOFF_SECONDS * retries)
                continue
            except Exception as exc:
                task.status = DownloadStatus.FAILED
                task.error_message = str(exc)
                if on_error:
                    on_error(task.destination, str(exc))
                return

            if task.status == DownloadStatus.CANCELLED:
                return

            if task.expected_sha256:
                try:
                    actual = _sha256_of(task.destination)
                    if actual.lower() != task.expected_sha256.lower():
                        task.status = DownloadStatus.FAILED
                        task.error_message = (
                            f"SHA-256 uyusmazligi: beklenen {task.expected_sha256}, alinan {actual}"
                        )
                        if on_error:
                            on_error(task.destination, task.error_message)
                        return
                except OSError as exc:
                    task.status = DownloadStatus.FAILED
                    task.error_message = f"Hash dogrulamasi basarisiz: {exc}"
                    if on_error:
                        on_error(task.destination, task.error_message)
                    return

            task.status = DownloadStatus.COMPLETED
            if on_complete:
                on_complete(task.destination)
            return

        task.status = DownloadStatus.FAILED
        task.error_message = "Maksimum yeniden deneme sayisina ulasildi."
        if on_error:
            on_error(task.destination, task.error_message)

    def _do_download(
        self,
        task: DownloadTask,
        pause_event: Event,
        cancel_event: Event,
        on_progress: ProgressCallback | None,
    ) -> None:
        task.status = DownloadStatus.CONNECTING
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
            total = task.total_bytes or _content_length(response) or 0
            task.total_bytes = total

            mode = "ab" if resume_pos > 0 else "wb"
            task.status = DownloadStatus.DOWNLOADING
            task.start_time = time.monotonic()
            downloaded = resume_pos

            with task.destination.open(mode) as output:
                while True:
                    if cancel_event.is_set():
                        return
                    if pause_event.is_set():
                        task.downloaded_bytes = downloaded
                        pause_event.wait()
                        if cancel_event.is_set():
                            return

                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    output.write(chunk)
                    downloaded += len(chunk)

                    elapsed = time.monotonic() - task.start_time
                    speed = downloaded / elapsed if elapsed > 0 else 0
                    eta = (total - downloaded) / speed if speed > 0 else 0

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
    length = response.headers.get("Content-Length") if hasattr(response, "headers") else None
    return int(length) if length else 0


def _sha256_of(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()

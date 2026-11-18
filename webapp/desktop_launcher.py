#!/usr/bin/env python3
"""Standalone desktop launcher for HYDRO Web (FastAPI + React + status controller)."""

from __future__ import annotations

import argparse
import json
import logging
import multiprocessing
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import replace
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TextIO

_STDIO_LOG_STREAM: TextIO | None = None
_ACTIVE_LOG_HANDLER: logging.Handler | None = None


def _bootstrap_paths() -> None:
    """Ensure ``app`` and ``hidrostatik_test`` packages are importable."""
    if getattr(sys, "frozen", False):
        candidates: list[str] = []
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(str(meipass))
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(str(exe_dir))
        internal_dir = exe_dir / "_internal"
        if internal_dir.is_dir():
            candidates.append(str(internal_dir))
        for candidate in candidates:
            if candidate not in sys.path:
                sys.path.insert(0, candidate)
        return

    webapp_dir = Path(__file__).resolve().parent
    repo_root = webapp_dir.parent
    backend_dir = webapp_dir / "backend"
    for path in (str(backend_dir), str(repo_root)):
        if path not in sys.path:
            sys.path.insert(0, path)


def _configure_logging_and_stdio(data_dir: Path, log_level: str = "INFO") -> Path:
    """Configure rotating file logs and guard against console=False None stdio."""
    global _STDIO_LOG_STREAM, _ACTIVE_LOG_HANDLER

    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "hydro_web.log"

    if sys.stdout is None or sys.stderr is None:
        stream = open(log_file, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
        _STDIO_LOG_STREAM = stream
        if sys.stdout is None:
            sys.stdout = stream
        if sys.stderr is None:
            sys.stderr = stream

    root_logger = logging.getLogger()
    if _ACTIVE_LOG_HANDLER is not None:
        root_logger.removeHandler(_ACTIVE_LOG_HANDLER)
        _ACTIVE_LOG_HANDLER.close()
        _ACTIVE_LOG_HANDLER = None

    level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger.setLevel(level)
    handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root_logger.addHandler(handler)
    _ACTIVE_LOG_HANDLER = handler
    return log_file


def _cleanup_logging() -> None:
    global _STDIO_LOG_STREAM, _ACTIVE_LOG_HANDLER
    if _ACTIVE_LOG_HANDLER is not None:
        logging.getLogger().removeHandler(_ACTIVE_LOG_HANDLER)
        try:
            _ACTIVE_LOG_HANDLER.close()
        except Exception:
            pass
        _ACTIVE_LOG_HANDLER = None
    if _STDIO_LOG_STREAM is not None:
        if sys.stdout is _STDIO_LOG_STREAM:
            sys.stdout = None
        if sys.stderr is _STDIO_LOG_STREAM:
            sys.stderr = None
        try:
            _STDIO_LOG_STREAM.close()
        except Exception:
            pass
        _STDIO_LOG_STREAM = None


def _is_port_available(host: str, port: int) -> bool:
    """Bind without SO_REUSEADDR (important on Windows to avoid dual-bind races)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, port))
            return True
    except OSError:
        return False


def _pick_port(host: str, preferred_port: int | None = None) -> int:
    candidates: list[int] = []
    if preferred_port is not None and preferred_port > 0:
        candidates.append(preferred_port)
    for port in range(8080, 8100):
        if port not in candidates:
            candidates.append(port)

    for port in candidates:
        if _is_port_available(host, port):
            return port

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _open_directory(path: Path) -> None:
    target = str(path)
    if sys.platform == "darwin":
        subprocess.Popen(["open", target])
    elif sys.platform == "win32":
        os.startfile(target)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", target])


def _start_uvicorn_thread(app: object, host: str, port: int, log_level: str):
    import uvicorn

    class _ThreadedServer(uvicorn.Server):
        def install_signal_handlers(self) -> None:
            return

    # log_config=None avoids uvicorn's tty isatty() calls under windowed mode.
    config = uvicorn.Config(
        app,  # type: ignore[arg-type]
        host=host,
        port=port,
        log_level=log_level.lower(),
        workers=1,
        log_config=None,
    )
    server = _ThreadedServer(config)
    error_holder: list[BaseException] = []

    def _run() -> None:
        try:
            server.run()
        except BaseException as exc:  # pragma: no cover - defensive runtime capture
            logging.getLogger("hydro.web.launcher").exception("Uvicorn sunucu hatasi")
            error_holder.append(exc)

    thread = threading.Thread(target=_run, name="hydro-web-uvicorn", daemon=True)
    thread.start()
    return server, thread, error_holder


def _http_json(
    url: str, *, method: str = "GET", payload: dict | None = None, timeout: float = 5.0
) -> tuple[int, dict]:
    data = None
    headers: dict[str, str] = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return int(resp.status), json.loads(raw)


def _http_text(url: str, *, timeout: float = 5.0) -> tuple[int, str]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return int(resp.status), resp.read().decode("utf-8", errors="replace")


def _run_self_test(args: argparse.Namespace) -> int:
    _bootstrap_paths()

    from app import db
    from app.core.config import Settings
    from app.main import create_app

    from hidrostatik_test import APP_VERSION

    tmp_dir = Path(tempfile.mkdtemp(prefix="hydro_web_selftest_"))
    server = None
    thread = None
    try:
        _configure_logging_and_stdio(tmp_dir, log_level="WARNING")
        env_settings = Settings.from_env()
        frontend_dist = (
            Path(args.frontend_dist) if args.frontend_dist else env_settings.frontend_dist
        )
        host = "127.0.0.1"
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, 0))
            port = int(sock.getsockname()[1])

        settings = replace(
            env_settings,
            host=host,
            port=port,
            database_url=f"sqlite:///{(tmp_dir / 'hydro_web.db').as_posix()}",
            data_dir=tmp_dir,
            frontend_dist=frontend_dist,
            log_level="WARNING",
        )
        app = create_app(settings)
        server, thread, error_holder = _start_uvicorn_thread(app, host, port, "WARNING")

        base_url = f"http://{host}:{port}"
        deadline = time.monotonic() + 20.0
        health_data: dict | None = None
        last_err: Exception | None = None

        while time.monotonic() < deadline:
            if error_holder:
                raise RuntimeError(f"Sunucu baslatilamadi: {error_holder[0]}")
            try:
                status, health_data = _http_json(f"{base_url}/api/health", timeout=2.0)
                if status == 200:
                    break
            except (urllib.error.URLError, ConnectionError, OSError) as exc:
                last_err = exc
                time.sleep(0.1)
        else:
            raise TimeoutError(f"/api/health 20s icinde yanit vermedi: {last_err}")

        if not health_data or not health_data.get("db", {}).get("ok"):
            raise AssertionError(f"DB health basarisiz: {health_data}")
        if health_data.get("version") != APP_VERSION:
            raise AssertionError(
                f"Health version uyumsuz: {health_data.get('version')} != {APP_VERSION}"
            )

        meta_status, meta_data = _http_json(f"{base_url}/api/meta", timeout=5.0)
        if meta_status != 200 or meta_data.get("app", {}).get("version") != APP_VERSION:
            raise AssertionError(f"/api/meta dogrulamasi basarisiz: {meta_data}")

        upd_status, upd_data = _http_json(f"{base_url}/api/update/status", timeout=5.0)
        if upd_status != 200 or upd_data.get("current_version") != APP_VERSION:
            raise AssertionError(f"/api/update/status dogrulamasi basarisiz: {upd_data}")

        coef_status, coef_data = _http_json(
            f"{base_url}/api/coefficients/a",
            method="POST",
            payload={"temperature_c": 15.0, "pressure_bar": 80.0, "backend": "coolprop"},
            timeout=5.0,
        )
        if coef_status != 200 or not isinstance(coef_data.get("a_micro_per_bar"), (int, float)):
            raise AssertionError(f"/api/coefficients/a (coolprop) basarisiz: {coef_data}")

        cmp_status, cmp_data = _http_json(
            f"{base_url}/api/coefficients/compare",
            method="POST",
            payload={"temperature_c": 15.0, "pressure_bar": 80.0},
            timeout=5.0,
        )
        if cmp_status != 200 or "institutional" not in cmp_data:
            raise AssertionError(f"/api/coefficients/compare basarisiz: {cmp_data}")

        ocr_status_code, ocr_data = _http_json(f"{base_url}/api/ocr/status", timeout=5.0)
        if ocr_status_code != 200:
            raise AssertionError(f"/api/ocr/status basarisiz: {ocr_data}")
        rasterizer_ok = bool((ocr_data.get("pdf_rasterizer") or {}).get("available"))
        if not rasterizer_ok:
            raise AssertionError(f"PDF rasterizer hazir degil: {ocr_data}")
        ocr_ok = bool(ocr_data.get("available"))
        if getattr(sys, "frozen", False) and not ocr_ok:
            raise AssertionError(f"Frozen pakette OCR motoru hazir degil: {ocr_data}")

        if ocr_ok and rasterizer_ok:
            from PIL import Image, ImageDraw, ImageFont

            from hidrostatik_test.services.report_ocr import extract_text

            scanned_pdf = tmp_dir / "scanned_check.pdf"
            img = Image.new("RGB", (1200, 400), "white")
            draw = ImageDraw.Draw(img)
            try:
                font = ImageFont.load_default(size=48)
            except TypeError:  # pragma: no cover - Pillow < 10.1
                font = ImageFont.load_default()
            draw.text(
                (80, 120),
                "HIDROSTATIK TEST RAPORU\nTEST BASINCI: 80 BAR",
                fill="black",
                font=font,
            )
            img.save(scanned_pdf, "PDF", resolution=200.0)
            pages = extract_text(scanned_pdf)
            if not pages or pages[0].source != "ocr" or "80" not in pages[0].text:
                raise AssertionError(f"Taranmis PDF OCR dogrulamasi basarisiz: {pages!r}")

        frontend_exists = (settings.frontend_dist / "index.html").is_file()
        if getattr(sys, "frozen", False) and not frontend_exists:
            raise AssertionError(
                f"Frozen paket icinde frontend dist bulunamadi: {settings.frontend_dist}"
            )
        if frontend_exists:
            root_status, html = _http_text(f"{base_url}/", timeout=5.0)
            if root_status != 200 or '<div id="root"' not in html:
                raise AssertionError("Frontend index.html / kokundan dogru sunulmadi")

        print(f"SELF_TEST_OK version={APP_VERSION}")
        return 0
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=5.0)
        try:
            db.dispose_database()
        except Exception:
            pass
        _cleanup_logging()
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _run_controller_gui(args: argparse.Namespace) -> int:
    _bootstrap_paths()

    from app import db
    from app.core.config import Settings
    from app.main import create_app

    from hidrostatik_test import APP_VERSION

    env_settings = Settings.from_env()
    data_dir = Path(args.data_dir) if args.data_dir else env_settings.data_dir
    frontend_dist = Path(args.frontend_dist) if args.frontend_dist else env_settings.frontend_dist
    log_file = _configure_logging_and_stdio(
        data_dir, log_level=args.log_level or env_settings.log_level
    )

    host = args.host or "127.0.0.1"
    preferred = args.port if args.port is not None else env_settings.port
    port = _pick_port(host, preferred_port=preferred)

    database_url = (
        args.database_url
        or os.environ.get("HYDRO_DATABASE_URL")
        or os.environ.get("HYDRO_DB_URL")
        or os.environ.get("DATABASE_URL")
        or f"sqlite:///{(data_dir / 'hydro_web.db').as_posix()}"
    )

    settings = replace(
        env_settings,
        host=host,
        port=port,
        database_url=database_url,
        data_dir=data_dir,
        frontend_dist=frontend_dist,
        log_level=(args.log_level or env_settings.log_level).upper(),
    )
    settings.ensure_directories()

    if settings.ocr_lang:
        os.environ.setdefault("HYDRO_OCR_LANG", settings.ocr_lang)
    if settings.tesseract_cmd:
        os.environ.setdefault("HYDRO_TESSERACT_CMD", settings.tesseract_cmd)

    app = create_app(settings)
    url_host = "127.0.0.1" if settings.host in {"0.0.0.0", "::"} else settings.host
    url = f"http://{url_host}:{settings.port}"

    server, thread, error_holder = _start_uvicorn_thread(
        app, settings.host, settings.port, settings.log_level
    )

    import tkinter as tk
    from tkinter import messagebox, ttk

    root = tk.Tk()
    root.title(f"HYDRO Web Sunucusu v{APP_VERSION}")
    root.geometry("500x260")
    root.minsize(460, 240)
    root.resizable(False, False)

    state = {"opened": False, "closing": False}

    frame = ttk.Frame(root, padding=16)
    frame.pack(fill="both", expand=True)

    title_lbl = ttk.Label(
        frame,
        text=f"HYDRO Web v{APP_VERSION}",
        font=("TkDefaultFont", 14, "bold"),
    )
    title_lbl.pack(anchor="w")

    status_var = tk.StringVar(value="Durum: Başlatılıyor...")
    status_lbl = ttk.Label(frame, textvariable=status_var)
    status_lbl.pack(anchor="w", pady=(6, 4))

    url_var = tk.StringVar(value=f"Adres: {url}")
    url_lbl = ttk.Label(frame, textvariable=url_var)
    url_lbl.pack(anchor="w", pady=(0, 4))

    data_lbl = ttk.Label(
        frame,
        text=f"Veri Klasörü: {settings.data_dir}",
        wraplength=460,
    )
    data_lbl.pack(anchor="w", pady=(0, 12))

    feedback_var = tk.StringVar(value="")
    feedback_lbl = ttk.Label(frame, textvariable=feedback_var)
    feedback_lbl.pack(anchor="w", pady=(0, 8))

    def _open_browser() -> None:
        try:
            webbrowser.open(url)
        except Exception as exc:
            feedback_var.set(f"Tarayıcı açılamadı: {exc}")

    def _copy_url() -> None:
        root.clipboard_clear()
        root.clipboard_append(url)
        root.update_idletasks()
        feedback_var.set("Sunucu adresi panoya kopyalandı.")

    def _open_data() -> None:
        try:
            _open_directory(settings.data_dir)
        except Exception as exc:
            feedback_var.set(f"Klasör açılamadı: {exc}")

    def _shutdown(*_event: object) -> None:
        if state["closing"]:
            return
        state["closing"] = True
        status_var.set("Durum: Kapatılıyor...")
        root.update_idletasks()
        server.should_exit = True
        thread.join(timeout=3.0)
        try:
            db.dispose_database()
        except Exception:
            pass
        _cleanup_logging()
        root.destroy()

    btn_row = ttk.Frame(frame)
    btn_row.pack(fill="x", pady=(4, 0))

    ttk.Button(btn_row, text="Tarayıcıda Aç", command=_open_browser).pack(side="left", padx=(0, 6))
    ttk.Button(btn_row, text="Adresi Kopyala", command=_copy_url).pack(side="left", padx=(0, 6))
    ttk.Button(btn_row, text="Veri Klasörünü Aç", command=_open_data).pack(side="left", padx=(0, 6))
    ttk.Button(btn_row, text="Sunucuyu Durdur ve Çık", command=_shutdown).pack(side="right")

    def _poll_server() -> None:
        if state["closing"]:
            return
        if error_holder or not thread.is_alive():
            err_msg = str(error_holder[0]) if error_holder else "Sunucu beklenmedik şekilde durdu."
            messagebox.showerror(
                "HYDRO Web Hatası",
                f"{err_msg}\n\nDetaylar: {log_file}",
                parent=root,
            )
            _shutdown()
            return
        if getattr(server, "started", False):
            status_var.set("Durum: Çalışıyor")
            if not state["opened"]:
                state["opened"] = True
                if not args.no_browser:
                    _open_browser()
        root.after(150, _poll_server)

    root.protocol("WM_DELETE_WINDOW", _shutdown)
    if sys.platform == "darwin":
        root.bind("<Command-q>", _shutdown)
    root.after(150, _poll_server)
    root.mainloop()
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="HYDRO Web masaüstü başlatıcı (yerel sunucu + tarayıcı)."
    )
    parser.add_argument("--host", default=None, help="Bind adresi (varsayılan 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="Tercih edilen port")
    parser.add_argument("--database-url", default=None, help="Özel SQLAlchemy URL")
    parser.add_argument("--data-dir", default=None, help="Özel veri klasörü")
    parser.add_argument("--frontend-dist", default=None, help="Özel frontend dist klasörü")
    parser.add_argument("--log-level", default=None, help="Log seviyesi")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Sunucu açıldığında otomatik tarayıcı sekmesi açma",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Geçici dizin üzerinde sunucuyu başlat, temel uç noktaları doğrula ve çık",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.self_test:
        return _run_self_test(args)
    return _run_controller_gui(args)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())

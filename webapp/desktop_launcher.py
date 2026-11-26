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
import traceback
import urllib.error
import urllib.request
import webbrowser
from dataclasses import replace
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TextIO

_STDIO_LOG_STREAM: TextIO | None = None
_STDIN_NULL_STREAM: TextIO | None = None
_ACTIVE_LOG_HANDLER: logging.Handler | None = None
_LOOPBACK_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _harden_windows_process() -> None:
    """Suppress blocking Windows critical/missing-DLL modal dialogs in child/loader calls."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel32 = getattr(ctypes, "windll", None) and ctypes.windll.kernel32  # type: ignore[attr-defined]
        if kernel32 is not None:
            kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
    except Exception:
        pass


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
    global _STDIO_LOG_STREAM, _STDIN_NULL_STREAM, _ACTIVE_LOG_HANDLER

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
    if sys.stdin is None:
        stdin_stream = open(os.devnull, "r", encoding="utf-8")  # noqa: SIM115
        _STDIN_NULL_STREAM = stdin_stream
        sys.stdin = stdin_stream

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
    global _STDIO_LOG_STREAM, _STDIN_NULL_STREAM, _ACTIVE_LOG_HANDLER
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
    if _STDIN_NULL_STREAM is not None:
        if sys.stdin is _STDIN_NULL_STREAM:
            sys.stdin = None
        try:
            _STDIN_NULL_STREAM.close()
        except Exception:
            pass
        _STDIN_NULL_STREAM = None


def _is_port_available(host: str, port: int) -> bool:
    """Bind cleanly (checking active listeners + Windows SO_EXCLUSIVEADDRUSE)."""
    probe_host = "127.0.0.1" if host in {"0.0.0.0", "::", ""} else host
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.08)
            if probe.connect_ex((probe_host, port)) == 0:
                return False
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)  # type: ignore[attr-defined]
            sock.bind((host, port))
            return True
    except OSError:
        return False


def _pick_port(host: str, preferred_port: int | None = None) -> int:
    candidates: list[int] = []
    if preferred_port is not None and preferred_port > 0:
        candidates.append(preferred_port)
    for port in range(18790, 18830):
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
    with _LOOPBACK_OPENER.open(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return int(resp.status), json.loads(raw)


def _http_text(url: str, *, timeout: float = 5.0) -> tuple[int, str]:
    req = urllib.request.Request(url, method="GET")
    with _LOOPBACK_OPENER.open(req, timeout=timeout) as resp:
        return int(resp.status), resp.read().decode("utf-8", errors="replace")


def _run_self_test(args: argparse.Namespace) -> int:
    def _write_self_test_report(text: str, *, is_error: bool = False) -> None:
        stream = sys.stderr if is_error else sys.stdout
        if stream is not None:
            try:
                stream.write(text + "\n")
                stream.flush()
            except Exception:
                pass
        log_path_arg = getattr(args, "self_test_log", None)
        if log_path_arg:
            try:
                log_path = Path(log_path_arg)
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text(text + "\n", encoding="utf-8")
            except Exception:
                pass

    tmp_dir: Path | None = None
    db_mod = None
    server = None
    thread = None
    try:
        _harden_windows_process()
        _bootstrap_paths()

        from app import db as db_mod
        from app.core.config import Settings
        from app.main import create_app

        from hidrostatik_test import APP_VERSION

        tmp_dir = Path(tempfile.mkdtemp(prefix="hydro_web_selftest_"))
        _configure_logging_and_stdio(tmp_dir, log_level="WARNING")
        env_settings = Settings.from_env()
        frontend_dist = (
            Path(args.frontend_dist) if args.frontend_dist else env_settings.frontend_dist
        )
        host = "127.0.0.1"
        health_data: dict | None = None
        last_err: Exception | None = None

        for bind_attempt in range(3):
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
            deadline = time.monotonic() + 30.0
            bind_retry = False

            while time.monotonic() < deadline:
                if error_holder:
                    err_text = str(error_holder[0]).lower()
                    if bind_attempt < 2 and (
                        "address already in use" in err_text
                        or "errno 98" in err_text
                        or "errno 48" in err_text
                    ):
                        bind_retry = True
                        break
                    raise RuntimeError(f"Sunucu baslatilamadi: {error_holder[0]}")
                try:
                    status, health_data = _http_json(f"{base_url}/api/health", timeout=2.0)
                    if status == 200:
                        break
                except (urllib.error.URLError, ConnectionError, OSError) as exc:
                    last_err = exc
                    time.sleep(0.1)
            else:
                raise TimeoutError(f"/api/health 30s icinde yanit vermedi: {last_err}")

            if not bind_retry:
                break
            server.should_exit = True
            thread.join(timeout=3.0)
            try:
                db_mod.dispose_database()
            except Exception:
                pass
            time.sleep(0.15)
        else:
            raise RuntimeError(f"Sunucu port tahsis edemedi: {error_holder!r}")

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
        win32_frozen = sys.platform == "win32" and getattr(sys, "frozen", False)
        if getattr(sys, "frozen", False) and not ocr_ok:
            has_languages = bool(ocr_data.get("languages") or [])
            if not win32_frozen or has_languages:
                raise AssertionError(f"Frozen pakette OCR motoru hazir degil: {ocr_data}")

        if rasterizer_ok:
            from PIL import Image, ImageDraw, ImageFont

            from hidrostatik_test.services.report_ocr import (
                ReportOcrError,
                _iter_rendered_pdf_pages,
                extract_text,
            )

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

            rendered_pages = list(_iter_rendered_pdf_pages(scanned_pdf, max_pages=1, dpi=150))
            if (
                len(rendered_pages) != 1
                or rendered_pages[0].width <= 100
                or rendered_pages[0].height <= 100
            ):
                raise AssertionError(
                    f"PDF rasterizer sayfa render dogrulamasi basarisiz: {rendered_pages!r}"
                )

            if win32_frozen:
                import importlib

                for winrt_mod in (
                    "winrt.windows.media.ocr",
                    "winrt.windows.globalization",
                    "winrt.windows.graphics.imaging",
                    "winrt.windows.storage.streams",
                    "winrt.windows.data.pdf",
                ):
                    importlib.import_module(winrt_mod)

            if ocr_ok:
                try:
                    pages = extract_text(scanned_pdf)
                except ReportOcrError as exc:
                    err_text = f"{exc.message} {exc.detail or ''}".lower()
                    if sys.platform == "win32" and any(
                        marker in err_text
                        for marker in ("0x80040154", "class not registered", "sinif kaydedilmemis")
                    ):
                        pages = []
                    else:
                        raise
                else:
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

        _write_self_test_report(f"SELF_TEST_OK version={APP_VERSION}")
        return 0
    except BaseException:
        _write_self_test_report(
            f"SELF_TEST_FAILED\n{traceback.format_exc()}",
            is_error=True,
        )
        return 1
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=5.0)
        if db_mod is not None:
            try:
                db_mod.dispose_database()
            except Exception:
                pass
        _cleanup_logging()
        if tmp_dir is not None:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _run_controller_gui(args: argparse.Namespace) -> int:
    _harden_windows_process()
    _bootstrap_paths()

    from app import db
    from app.core.config import Settings, validate_bind_security
    from app.main import create_app

    from hidrostatik_test import APP_VERSION

    env_settings = Settings.from_env()
    data_dir = Path(args.data_dir) if args.data_dir else env_settings.data_dir
    frontend_dist = Path(args.frontend_dist) if args.frontend_dist else env_settings.frontend_dist
    log_file = _configure_logging_and_stdio(
        data_dir, log_level=args.log_level or env_settings.log_level
    )

    host = args.host or "127.0.0.1"
    env_port = (os.environ.get("HYDRO_PORT") or os.environ.get("HYDRO_WEB_PORT") or "").strip()
    preferred = args.port if args.port is not None else (env_settings.port if env_port else None)
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
    bind_err = validate_bind_security(settings)
    if bind_err is not None:
        print(bind_err, file=sys.stderr)
        return 2
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
    try:
        candidates = [
            Path(__file__).resolve().parents[1] / "assets" / "icons" / "hydro-256.png",
            Path(getattr(sys, "_MEIPASS", "")) / "assets" / "icons" / "hydro-256.png",
            Path(sys.executable).resolve().parent / "assets" / "icons" / "hydro-256.png",
            Path(sys.executable).resolve().parent
            / "_internal"
            / "assets"
            / "icons"
            / "hydro-256.png",
        ]
        icon_file = next((p for p in candidates if str(p) and p.is_file()), None)
        if icon_file is not None and hasattr(root, "iconphoto"):
            icon_img = tk.PhotoImage(file=str(icon_file))
            root.iconphoto(True, icon_img)
            root._hydro_icon_img = icon_img  # type: ignore[attr-defined]
    except Exception:
        pass
    root.geometry("520x295")
    root.minsize(480, 265)
    root.resizable(False, False)

    state = {"opened": False, "closing": False, "verified": False}

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
        wraplength=480,
    )
    data_lbl.pack(anchor="w", pady=(0, 4))

    note_lbl = ttk.Label(
        frame,
        text="Not: Tarayıcıda çalışırken bu pencereyi kapatmayın; küçültebilirsiniz.",
        wraplength=480,
    )
    note_lbl.pack(anchor="w", pady=(0, 10))

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

    def _on_close_window(*_event: object) -> None:
        if state["closing"]:
            return
        choice = messagebox.askyesnocancel(
            "HYDRO Web Sunucusu",
            "Bu pencereyi kapatmak yerel HYDRO Web sunucusunu durdurur ve açık tarayıcı sekmesinin bağlantısını keser.\n\n"
            "Sunucuyu açık tutup pencereyi küçültmek ister misiniz?",
            parent=root,
        )
        if choice is True:
            root.iconify()
        elif choice is False:
            _shutdown()

    btn_row = ttk.Frame(frame)
    btn_row.pack(fill="x", pady=(4, 0))

    ttk.Button(btn_row, text="Tarayıcıda Aç", command=_open_browser).pack(side="left", padx=(0, 6))
    ttk.Button(btn_row, text="Adresi Kopyala", command=_copy_url).pack(side="left", padx=(0, 6))
    ttk.Button(btn_row, text="Veri Klasörünü Aç", command=_open_data).pack(side="left", padx=(0, 6))
    ttk.Button(btn_row, text="Küçült", command=root.iconify).pack(side="left", padx=(0, 6))
    ttk.Button(btn_row, text="Sunucuyu Durdur ve Çık", command=_shutdown).pack(side="right")

    expected_instance_id = getattr(app.state, "instance_id", None)

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
            if not state["verified"]:
                try:
                    hstatus, hdata = _http_json(f"{url}/api/health", timeout=1.5)
                    if hstatus == 200 and (
                        expected_instance_id is None
                        or hdata.get("instance_id") == expected_instance_id
                    ):
                        state["verified"] = True
                except Exception:
                    state["verified"] = False
            if state["verified"]:
                status_var.set("Durum: Çalışıyor")
                if not state["opened"]:
                    state["opened"] = True
                    if not args.no_browser:
                        _open_browser()
        root.after(150, _poll_server)

    root.protocol("WM_DELETE_WINDOW", _on_close_window)
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
    parser.add_argument(
        "--self-test-log",
        default=None,
        help="Self-test sonuc/hata ciktisini dosyaya da yaz (windowed/CI calismalari icin)",
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

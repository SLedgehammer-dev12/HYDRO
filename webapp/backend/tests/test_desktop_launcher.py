"""Tests for frozen web path resolution and standalone desktop launcher."""

from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path

from app.core import config as web_config


def test_default_data_dir_source_mode():
    assert web_config._default_data_dir() == web_config.WEBAPP_DIR / "data"


def test_frozen_data_and_frontend_paths_macos(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    fake_meipass = tmp_path / "bundle" / "_internal"
    (fake_meipass / "webapp_frontend_dist").mkdir(parents=True)
    (fake_meipass / "webapp_frontend_dist" / "index.html").write_text(
        "<html></html>", encoding="utf-8"
    )

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(fake_meipass), raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    assert (
        web_config._default_data_dir()
        == fake_home / "Library" / "Application Support" / "HYDRO-Web"
    )
    assert web_config._default_frontend_dist() == fake_meipass / "webapp_frontend_dist"


def test_frozen_data_and_frontend_paths_windows(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    fake_localappdata = tmp_path / "LocalAppData"
    fake_exe_dir = tmp_path / "HydroWebInstall"
    (fake_exe_dir / "webapp_frontend_dist").mkdir(parents=True)
    (fake_exe_dir / "webapp_frontend_dist" / "index.html").write_text(
        "<html></html>", encoding="utf-8"
    )

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe_dir / "HydroWeb.exe"))
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    monkeypatch.setenv("LOCALAPPDATA", str(fake_localappdata))

    assert web_config._default_data_dir() == fake_localappdata / "HYDRO-Web"
    assert web_config._default_frontend_dist() == fake_exe_dir / "webapp_frontend_dist"

    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert web_config._default_data_dir() == fake_home / "AppData" / "Local" / "HYDRO-Web"


def test_frozen_settings_from_env_uses_writable_user_dir(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    fake_meipass = tmp_path / "app_res"
    fake_meipass.mkdir()

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(fake_meipass), raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    for var in (
        "HYDRO_DATA_DIR",
        "HYDRO_FRONTEND_DIST",
        "HYDRO_DATABASE_URL",
        "HYDRO_DB_URL",
        "DATABASE_URL",
    ):
        monkeypatch.delenv(var, raising=False)

    settings = web_config.Settings.from_env()
    expected_data = (fake_home / "Library" / "Application Support" / "HYDRO-Web").resolve()
    assert settings.data_dir == expected_data
    assert settings.frontend_dist == (fake_meipass / "webapp_frontend_dist").resolve()
    assert f"sqlite:///{(expected_data / 'hydro_web.db').as_posix()}" == settings.database_url


def test_pick_port_skips_busy_preferred_port():
    from webapp import desktop_launcher

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as busy:
        busy.bind(("127.0.0.1", 0))
        busy_port = busy.getsockname()[1]
        picked = desktop_launcher._pick_port("127.0.0.1", preferred_port=busy_port)
        assert picked != busy_port
        assert picked > 0


def test_pick_port_defaults_to_uncontested_range():
    from webapp import desktop_launcher

    picked = desktop_launcher._pick_port("127.0.0.1", preferred_port=None)
    assert picked != 8080
    assert picked >= 18790


def test_desktop_launcher_self_test_subprocess(tmp_path):
    repo_root = Path(__file__).resolve().parents[3]
    launcher = repo_root / "webapp" / "desktop_launcher.py"
    log_file = tmp_path / "self_test.log"
    proc = subprocess.run(
        [sys.executable, str(launcher), "--self-test", "--self-test-log", str(log_file)],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    assert "SELF_TEST_OK" in proc.stdout
    assert log_file.is_file()
    assert "SELF_TEST_OK" in log_file.read_text(encoding="utf-8")


def test_desktop_launcher_self_test_catches_exceptions_without_crashing(monkeypatch, tmp_path):
    from app import main as app_main

    from webapp import desktop_launcher

    log_file = tmp_path / "failed_self_test.log"

    def _boom(_settings):
        raise RuntimeError("boom")

    monkeypatch.setattr(app_main, "create_app", _boom)
    args = desktop_launcher._parse_args(["--self-test", "--self-test-log", str(log_file)])
    exit_code = desktop_launcher._run_self_test(args)
    assert exit_code == 1
    assert log_file.is_file()
    log_text = log_file.read_text(encoding="utf-8")
    assert "SELF_TEST_FAILED" in log_text
    assert "boom" in log_text

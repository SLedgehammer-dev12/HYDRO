from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import tkinter as tk
import unittest
from urllib.error import URLError
from unittest.mock import patch

from hidrostatik_test.app_metadata import APP_VERSION, BINARY_NAME
from hidrostatik_test.services.updater import (
    ReleaseAsset,
    RuntimeContext,
    UpdateInfo,
    _download_asset,
    _write_update_script,
    fetch_latest_update_info,
    install_update,
)
from hidrostatik_test.ui.app import HydrostaticTestApp

NEXT_TEST_VERSION = f"{int(APP_VERSION.split('.', 1)[0]) + 1}.0.0"


class _FakeResponse:
    def __init__(self, payload: object) -> None:
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self, *_args, **_kwargs) -> bytes:
        return self._payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class UpdaterTests(unittest.TestCase):
    def test_fetch_latest_update_info_filters_project_specific_releases(self) -> None:
        payload = [
            {
                "tag_name": "other-app-v9.9.9",
                "draft": False,
                "prerelease": False,
                "assets": [{"name": "OtherApp-v9.9.9-windows-x64.zip", "browser_download_url": "https://example.com/other.zip", "size": 11}],
                "html_url": "https://example.com/other",
                "body": "other",
                "published_at": "2026-03-01T12:00:00Z",
            },
            {
                "tag_name": f"hidrostatik-test-v{NEXT_TEST_VERSION}",
                "draft": False,
                "prerelease": False,
                "assets": [{"name": f"HidrostatikTest-v{NEXT_TEST_VERSION}-windows-x64.zip", "browser_download_url": "https://example.com/app.zip", "size": 42}],
                "html_url": "https://example.com/app",
                "body": "notes",
                "published_at": "2026-03-30T12:00:00Z",
            },
        ]

        with patch("hidrostatik_test.services.updater.urlopen", return_value=_FakeResponse(payload)):
            info = fetch_latest_update_info()

        self.assertEqual(info.latest_version, NEXT_TEST_VERSION)
        self.assertTrue(info.update_available)
        self.assertIsNotNone(info.asset)
        self.assertEqual(info.asset.name, f"HidrostatikTest-v{NEXT_TEST_VERSION}-windows-x64.zip")
        self.assertEqual(info.source_repository, "SLedgehammer-dev12/HYDRO")

    def test_fetch_latest_update_info_marks_current_version_up_to_date(self) -> None:
        payload = [
            {
                "tag_name": f"hidrostatik-test-v{APP_VERSION}",
                "draft": False,
                "prerelease": False,
                "assets": [],
                "html_url": "https://example.com/current",
                "body": "notes",
                "published_at": "2026-03-30T12:00:00Z",
            }
        ]

        with patch("hidrostatik_test.services.updater.urlopen", return_value=_FakeResponse(payload)):
            info = fetch_latest_update_info()

        self.assertEqual(info.latest_version, APP_VERSION)
        self.assertFalse(info.update_available)
        self.assertEqual(info.source_repository, "SLedgehammer-dev12/HYDRO")

    def test_fetch_latest_update_info_falls_back_to_powershell_when_python_tls_fails(self) -> None:
        payload = [
            {
                "tag_name": f"hidrostatik-test-v{NEXT_TEST_VERSION}",
                "draft": False,
                "prerelease": False,
                "assets": [{"name": f"HidrostatikTest-v{NEXT_TEST_VERSION}-windows-x64.zip", "browser_download_url": "https://example.com/app.zip", "size": 42}],
                "html_url": "https://example.com/app",
                "body": "notes",
                "published_at": "2026-03-30T12:00:00Z",
            }
        ]
        powershell_result = subprocess.CompletedProcess(
            args=["powershell"],
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )

        with patch("hidrostatik_test.services.updater.urlopen", side_effect=URLError("tls failure")), patch(
            "hidrostatik_test.services.updater.subprocess.run",
            return_value=powershell_result,
        ):
            info = fetch_latest_update_info()

        self.assertEqual(info.latest_version, NEXT_TEST_VERSION)
        self.assertTrue(info.update_available)
        self.assertEqual(info.source_repository, "SLedgehammer-dev12/HYDRO")

    def test_fetch_latest_update_info_falls_back_to_legacy_repo_when_primary_has_no_release(self) -> None:
        primary_payload: list[dict[str, object]] = []
        legacy_payload = [
            {
                "tag_name": f"hidrostatik-test-v{NEXT_TEST_VERSION}",
                "draft": False,
                "prerelease": False,
                "assets": [
                    {
                        "name": f"HidrostatikTest-v{NEXT_TEST_VERSION}-windows-x64.zip",
                        "browser_download_url": "https://example.com/legacy-app.zip",
                        "size": 42,
                    }
                ],
                "html_url": "https://example.com/legacy-app",
                "body": "legacy notes",
                "published_at": "2026-03-31T12:00:00Z",
            }
        ]

        def fake_urlopen(request, timeout=10):
            url = request.full_url
            if url.endswith("/HYDRO/releases"):
                return _FakeResponse(primary_payload)
            if url.endswith("/Programlar/releases"):
                return _FakeResponse(legacy_payload)
            raise AssertionError(f"Beklenmeyen URL: {url}")

        with patch("hidrostatik_test.services.updater.urlopen", side_effect=fake_urlopen):
            info = fetch_latest_update_info()

        self.assertEqual(info.latest_version, NEXT_TEST_VERSION)
        self.assertEqual(info.source_repository, "SLedgehammer-dev12/Programlar")

    def test_download_asset_falls_back_to_powershell_when_python_tls_fails(self) -> None:
        asset = ReleaseAsset(
            name=f"HidrostatikTest-v{NEXT_TEST_VERSION}-windows-x64.zip",
            download_url="https://example.com/app.zip",
            size=42,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            target_path = Path(temp_dir) / asset.name

            def fake_powershell_download(url: str, headers: dict[str, str], target: Path, timeout: int) -> None:
                self.assertEqual(url, asset.download_url)
                self.assertIn("User-Agent", headers)
                self.assertEqual(timeout, 10)
                target.write_bytes(b"zip-data")

            with patch("hidrostatik_test.services.updater.urlopen", side_effect=URLError("tls failure")), patch(
                "hidrostatik_test.services.updater._download_via_powershell",
                side_effect=fake_powershell_download,
            ):
                _download_asset(asset, target_path, 10)

            self.assertTrue(target_path.exists())
            self.assertEqual(target_path.read_bytes(), b"zip-data")

    def test_install_update_uses_selected_download_root(self) -> None:
        info = UpdateInfo(
            current_version=APP_VERSION,
            latest_version=NEXT_TEST_VERSION,
            tag_name=f"hidrostatik-test-v{NEXT_TEST_VERSION}",
            html_url="https://example.com/update",
            body="notes",
            published_at="2026-03-30T12:00:00Z",
            asset=ReleaseAsset(
                name=f"HidrostatikTest-v{NEXT_TEST_VERSION}-windows-x64.zip",
                download_url="https://example.com/update.zip",
                size=1024,
            ),
            update_available=True,
            source_repository="SLedgehammer-dev12/HYDRO",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            chosen_dir = base_dir / "chosen-downloads"
            working_root = base_dir / "hidrostatik-update-test"
            working_root.mkdir()
            install_dir = base_dir / "install"
            install_dir.mkdir()
            executable_path = install_dir / "HidrostatikTest.exe"
            executable_path.write_text("stub", encoding="utf-8")
            captured: dict[str, str | None] = {}

            def fake_mkdtemp(prefix: str, dir: str | None = None) -> str:
                captured["prefix"] = prefix
                captured["dir"] = dir
                return str(working_root)

            def write_test_zip(asset: ReleaseAsset, target_path: Path, timeout: int) -> None:
                del asset, timeout
                import zipfile

                with zipfile.ZipFile(target_path, "w") as archive:
                    archive.writestr(f"{BINARY_NAME}/marker.txt", "ok")

            runtime = RuntimeContext(
                frozen=True,
                can_self_update=True,
                executable_path=executable_path,
                install_dir=install_dir,
            )

            with patch("hidrostatik_test.services.updater.tempfile.mkdtemp", side_effect=fake_mkdtemp), patch(
                "hidrostatik_test.services.updater.get_runtime_context",
                return_value=runtime,
            ), patch(
                "hidrostatik_test.services.updater._download_asset",
                side_effect=write_test_zip,
            ), patch(
                "hidrostatik_test.services.updater.subprocess.Popen"
            ) as mocked_popen:
                result = install_update(info, download_root=chosen_dir)

        self.assertEqual(result, "self_update")
        self.assertEqual(captured["prefix"], "hidrostatik-update-")
        self.assertEqual(captured["dir"], str(chosen_dir))
        mocked_popen.assert_called_once()
        launch_command = mocked_popen.call_args.args[0]
        self.assertEqual(launch_command[0], "powershell")
        self.assertIn("-File", launch_command)
        self.assertTrue(str(launch_command[-1]).endswith(".ps1"))

    def test_write_update_script_preserves_turkish_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir) / "İş_Çalışan"
            working_root = base_dir / "güncelleme"
            stage_dir = working_root / "sahne"
            install_dir = base_dir / "Çalışan programlar" / "Hidrostatik_Test"
            executable_path = install_dir / "HidrostatikTest.exe"
            working_root.mkdir(parents=True)

            script_path = _write_update_script(
                working_root=working_root,
                stage_dir=stage_dir,
                install_dir=install_dir,
                executable_path=executable_path,
                current_pid=1234,
            )

            script_text = script_path.read_text(encoding="utf-8-sig")

        self.assertEqual(script_path.suffix, ".ps1")
        self.assertIn("İş_Çalışan", script_text)
        self.assertIn("Çalışan programlar", script_text)
        self.assertIn("Copy-Item -LiteralPath", script_text)
        self.assertIn("Start-Process -FilePath $ExePath", script_text)


class UpdateUiTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk kullanilamiyor: {exc}")
        self.root.withdraw()
        self.app = HydrostaticTestApp(self.root)

    def tearDown(self) -> None:
        self.root.destroy()

    def test_update_result_marks_current_build_as_up_to_date(self) -> None:
        info = UpdateInfo(
            current_version=APP_VERSION,
            latest_version=APP_VERSION,
            tag_name=f"hidrostatik-test-v{APP_VERSION}",
            html_url="https://example.com/current",
            body="notes",
            published_at="2026-03-30T12:00:00Z",
            asset=None,
            update_available=False,
            source_repository="SLedgehammer-dev12/HYDRO",
        )

        with patch("hidrostatik_test.ui.app.messagebox.showinfo") as mocked_showinfo:
            self.app._handle_update_check_result(info, user_requested=True)

        self.assertIn("Guncel surum", self.app.update_status_var.get())
        self.assertIn("daha yeni bir release bulunmadi", self.app.update_detail_var.get())
        mocked_showinfo.assert_called_once()

    def test_update_result_marks_new_release_as_available(self) -> None:
        info = UpdateInfo(
            current_version=APP_VERSION,
            latest_version=NEXT_TEST_VERSION,
            tag_name=f"hidrostatik-test-v{NEXT_TEST_VERSION}",
            html_url="https://example.com/update",
            body="notes",
            published_at="2026-03-30T12:00:00Z",
            asset=ReleaseAsset(
                name=f"HidrostatikTest-v{NEXT_TEST_VERSION}-windows-x64.zip",
                download_url="https://example.com/update.zip",
                size=1024,
            ),
            update_available=True,
            source_repository="SLedgehammer-dev12/Programlar",
        )

        with patch("hidrostatik_test.ui.app.messagebox.askyesno", return_value=False):
            self.app._handle_update_check_result(info, user_requested=True)

        self.assertIn("Yeni surum bulundu", self.app.update_status_var.get())
        self.assertIn(f"HidrostatikTest-v{NEXT_TEST_VERSION}-windows-x64.zip", self.app.update_detail_var.get())
        self.assertIn("SLedgehammer-dev12/Programlar", self.app.update_detail_var.get())

    def test_manual_update_check_offers_install_flow(self) -> None:
        info = UpdateInfo(
            current_version=APP_VERSION,
            latest_version=NEXT_TEST_VERSION,
            tag_name=f"hidrostatik-test-v{NEXT_TEST_VERSION}",
            html_url="https://example.com/update",
            body="notes",
            published_at="2026-03-30T12:00:00Z",
            asset=ReleaseAsset(
                name=f"HidrostatikTest-v{NEXT_TEST_VERSION}-windows-x64.zip",
                download_url="https://example.com/update.zip",
                size=1024,
            ),
            update_available=True,
            source_repository="SLedgehammer-dev12/HYDRO",
        )

        with patch("hidrostatik_test.ui.app.messagebox.askyesno", return_value=True), patch.object(
            self.app,
            "_apply_available_update",
        ) as mocked_apply:
            self.app._handle_update_check_result(info, user_requested=True)

        mocked_apply.assert_called_once()


if __name__ == "__main__":
    unittest.main()

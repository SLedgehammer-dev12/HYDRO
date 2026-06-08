from __future__ import annotations

import hashlib
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
    _download_checksum,
    _extract_asset,
    _matches_project_release,
    _select_latest_release,
    _verify_sha256,
    _version_from_tag,
    _write_update_script,
    fetch_latest_update_info,
    install_update,
)
from hidrostatik_test.ui.app import HydrostaticTestApp

NEXT_TEST_VERSION = f"{int(APP_VERSION.split('.', 1)[0]) + 1}.0.0"


class _FakeJsonResponse:
    def __init__(self, payload: object) -> None:
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self, *_args, **_kwargs) -> bytes:
        return self._payload

    def __enter__(self) -> "_FakeJsonResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class _FakeBytesResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self, *_args, **_kwargs) -> bytes:
        return self._data

    def __enter__(self) -> "_FakeBytesResponse":
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

        with patch("hidrostatik_test.services.updater.urlopen", return_value=_FakeJsonResponse(payload)):
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

        with patch("hidrostatik_test.services.updater.urlopen", return_value=_FakeJsonResponse(payload)):
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
                return _FakeJsonResponse(primary_payload)
            if url.endswith("/Programlar/releases"):
                return _FakeJsonResponse(legacy_payload)
            raise AssertionError(f"Beklenmeyen URL: {url}")

        with patch("hidrostatik_test.services.updater.urlopen", side_effect=fake_urlopen):
            info = fetch_latest_update_info()

        self.assertEqual(info.latest_version, NEXT_TEST_VERSION)
        self.assertEqual(info.source_repository, "SLedgehammer-dev12/Programlar")

    def test_download_asset_uses_download_manager(self) -> None:
        asset = ReleaseAsset(
            name=f"HidrostatikTest-v{NEXT_TEST_VERSION}-windows-x64.zip",
            download_url="https://example.com/app.zip",
            size=42,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            target_path = Path(temp_dir) / asset.name

            def fake_download(url: str, dest: Path, on_progress=None):
                self.assertEqual(url, asset.download_url)
                dest.write_bytes(b"downloaded-data")

            with (
                patch(
                    "hidrostatik_test.services.download_manager.DownloadManager.download_file",
                    side_effect=fake_download,
                ),
                patch(
                    "hidrostatik_test.services.updater._download_checksum",
                    return_value=hashlib.sha256(b"downloaded-data").hexdigest(),
                ),
            ):
                _download_asset(asset, target_path, 10)

            self.assertTrue(target_path.exists())
            self.assertEqual(target_path.read_bytes(), b"downloaded-data")

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

            def write_test_zip(asset: ReleaseAsset, target_path: Path, timeout: int, **kwargs: object) -> None:
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


class UpdaterUtilityTests(unittest.TestCase):
    def test_version_from_tag_with_prefix(self) -> None:
        self.assertEqual(_version_from_tag("hidrostatik-test-v1.2.3"), "1.2.3")

    def test_version_from_tag_with_v_prefix_only(self) -> None:
        self.assertEqual(_version_from_tag("v9.9.9"), "9.9.9")

    def test_version_from_tag_without_prefix(self) -> None:
        self.assertEqual(_version_from_tag("1.0.0"), "1.0.0")

    def test_matches_project_release_by_tag(self) -> None:
        release = {"tag_name": "hidrostatik-test-v1.7.2", "assets": []}
        self.assertTrue(_matches_project_release(release))

    def test_matches_project_release_by_asset_for_windows(self) -> None:
        release = {
            "tag_name": "custom-tag",
            "assets": [
                {"name": "HidrostatikTest-v1.7.2-windows-x64.zip", "browser_download_url": "https://example.com/app.zip", "size": 42}
            ],
        }
        self.assertTrue(_matches_project_release(release))

    def test_matches_project_release_by_asset_for_macos(self) -> None:
        release = {
            "tag_name": "custom-tag",
            "assets": [
                {"name": "HidrostatikTest-v1.7.2-macos-universal.dmg", "browser_download_url": "https://example.com/app.dmg", "size": 42}
            ],
        }
        self.assertTrue(_matches_project_release(release))

    def test_matches_project_release_returns_false_for_unrelated(self) -> None:
        release = {"tag_name": "other-app-v1.0.0", "assets": [{"name": "OtherApp.exe", "browser_download_url": "https://example.com/other.exe", "size": 42}]}
        self.assertFalse(_matches_project_release(release))

    def test_select_latest_release_ignores_drafts(self) -> None:
        releases = [
            {"tag_name": "hidrostatik-test-v1.0.0", "draft": True, "prerelease": False, "assets": []},
            {"tag_name": "hidrostatik-test-v2.0.0", "draft": False, "prerelease": False, "assets": []},
        ]
        selected = _select_latest_release(releases, "HYDRO")
        self.assertEqual(selected["tag_name"], "hidrostatik-test-v2.0.0")

    def test_select_latest_release_ignores_prereleases(self) -> None:
        releases = [
            {"tag_name": "hidrostatik-test-v1.0.0", "draft": False, "prerelease": True, "assets": []},
            {"tag_name": "hidrostatik-test-v2.0.0", "draft": False, "prerelease": False, "assets": []},
        ]
        selected = _select_latest_release(releases, "HYDRO")
        self.assertEqual(selected["tag_name"], "hidrostatik-test-v2.0.0")

    def test_select_latest_release_sorts_by_version_desc(self) -> None:
        releases = [
            {"tag_name": "hidrostatik-test-v1.0.0", "draft": False, "prerelease": False, "assets": []},
            {"tag_name": "hidrostatik-test-v3.0.0", "draft": False, "prerelease": False, "assets": []},
            {"tag_name": "hidrostatik-test-v2.0.0", "draft": False, "prerelease": False, "assets": []},
        ]
        selected = _select_latest_release(releases, "HYDRO")
        self.assertEqual(selected["tag_name"], "hidrostatik-test-v3.0.0")

    def test_select_latest_release_raises_when_no_matching(self) -> None:
        releases: list[dict[str, object]] = [{"tag_name": "other-app-v1.0.0", "draft": False, "prerelease": False, "assets": []}]
        with self.assertRaisesRegex(RuntimeError, "yayin bulunamadi"):
            _select_latest_release(releases, "HYDRO")

    def test_extract_asset_matches_windows_zip_exactly(self) -> None:
        release = {
            "tag_name": "hidrostatik-test-v1.7.2",
            "assets": [
                {"name": "HidrostatikTest-v1.7.2-windows-x64.zip", "browser_download_url": "https://example.com/app.zip", "size": 100},
                {"name": "HidrostatikTest-v1.7.2-macos-universal.dmg", "browser_download_url": "https://example.com/app.dmg", "size": 200},
            ],
        }
        asset = _extract_asset(release, "1.7.2")
        self.assertIsNotNone(asset)
        self.assertEqual(asset.name, "HidrostatikTest-v1.7.2-windows-x64.zip")
        self.assertEqual(asset.size, 100)

    def test_extract_asset_uses_fallback_when_no_exact_match(self) -> None:
        release = {
            "tag_name": "hidrostatik-test-v1.7.0",
            "assets": [
                {"name": "HidrostatikTest-v1.7.0-windows-x64.zip", "browser_download_url": "https://example.com/old.zip", "size": 50},
            ],
        }
        asset = _extract_asset(release, "1.7.2")
        self.assertIsNotNone(asset)
        self.assertEqual(asset.name, "HidrostatikTest-v1.7.0-windows-x64.zip")

    def test_extract_asset_returns_none_when_no_assets(self) -> None:
        release = {"tag_name": "hidrostatik-test-v1.7.2", "assets": []}
        asset = _extract_asset(release, "1.7.2")
        self.assertIsNone(asset)

    def test_verify_sha256_passes_for_matching_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "test.bin"
            file_path.write_bytes(b"hello world")
            expected = hashlib.sha256(b"hello world").hexdigest()
            _verify_sha256(file_path, expected)

    def test_verify_sha256_raises_for_mismatched_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "test.bin"
            file_path.write_bytes(b"hello world")
            with self.assertRaisesRegex(RuntimeError, "SHA-256 dogrulamasi basarisiz"):
                _verify_sha256(file_path, "0000000000000000000000000000000000000000000000000000000000000000")

    def test_download_checksum_parses_sha_from_response(self) -> None:
        content = b"abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890  filename.zip"
        with patch("hidrostatik_test.services.updater.urlopen", return_value=_FakeBytesResponse(content)):
            result = _download_checksum("https://example.com/app.zip", 10)
        self.assertEqual(result, "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890")

    def test_download_checksum_parses_sha_with_tabs(self) -> None:
        content = b"abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890\tfilename.zip"
        with patch("hidrostatik_test.services.updater.urlopen", return_value=_FakeBytesResponse(content)):
            result = _download_checksum("https://example.com/app.zip", 10)
        self.assertEqual(result, "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890")

    def test_download_checksum_normalizes_to_lowercase(self) -> None:
        content = b"ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890"
        with patch("hidrostatik_test.services.updater.urlopen", return_value=_FakeBytesResponse(content)):
            result = _download_checksum("https://example.com/app.zip", 10)
        self.assertEqual(result, "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890")

    def test_download_checksum_raises_on_empty_content(self) -> None:
        with patch("hidrostatik_test.services.updater.urlopen", return_value=_FakeBytesResponse(b"   ")):
            with self.assertRaisesRegex(RuntimeError, "SHA-256 dosyasi bos"):
                _download_checksum("https://example.com/app.zip", 10)

    def test_download_checksum_raises_on_404(self) -> None:
        from urllib.error import HTTPError

        def fake_urlopen(request, timeout=10):
            raise HTTPError("https://example.com/app.zip.sha256.txt", 404, "Not Found", {}, None)

        with patch("hidrostatik_test.services.updater.urlopen", side_effect=fake_urlopen):
            with self.assertRaisesRegex(RuntimeError, "SHA-256 dogrulama dosyasi.*bulunamadi"):
                _download_checksum("https://example.com/app.zip", 10)


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

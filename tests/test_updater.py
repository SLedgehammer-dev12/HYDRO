from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import tkinter as tk
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from hidrostatik_test.app_metadata import APP_VERSION, BINARY_NAME, UPDATE_SIGNING_PUBLIC_KEY
from hidrostatik_test.services import updater
from hidrostatik_test.services.updater import (
    ReleaseAsset,
    RuntimeContext,
    UpdateError,
    UpdateInfo,
    _checksum_candidate_urls,
    _decode_public_key,
    _download_asset,
    _download_checksum,
    _ensure_pe_executable,
    _extract_asset,
    _install_macos_update,
    _matches_project_release,
    _safe_extract_zip,
    _select_latest_release,
    _verify_sha256,
    _version_from_tag,
    _write_update_script,
    fetch_latest_update_info,
    install_update,
    verify_asset_signature,
)
from hidrostatik_test.ui.app import HydrostaticTestApp

try:  # Imza testleri icin gercek Ed25519 uretimi (opsiyonel bagimlilik)
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    HAVE_CRYPTOGRAPHY = True
except ImportError:  # pragma: no cover
    HAVE_CRYPTOGRAPHY = False

NEXT_TEST_VERSION = f"{int(APP_VERSION.split('.', 1)[0]) + 1}.0.0"
SIGNING_TOOL = Path(__file__).resolve().parents[1] / "tools" / "update_signing.py"


def _clean_hydro_env(**values: str) -> dict[str, str]:
    """Gelistirici kabugundaki HYDRO_* degiskenlerini testten izole eder."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("HYDRO_")}
    env.update(values)
    return env


def _new_keypair():
    private_key = Ed25519PrivateKey.generate()
    public_raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return private_key, base64.b64encode(public_raw).decode("ascii")


class UnsignedUpdateAllowedMixin:
    """Imza uretmeyen eski testler icin acik gelistirici kacis bayragi.

    Varsayilan davranis fail-closed oldugu icin bu testler imzayi bilerek
    devre disi birakir; imza zorunlulugu ``SignatureEnforcementTests`` ile
    ayrica dogrulanir.
    """

    def setUp(self) -> None:
        super().setUp()
        env_patch = patch.dict(
            os.environ, _clean_hydro_env(HYDRO_ALLOW_UNSIGNED_UPDATE="1"), clear=True
        )
        env_patch.start()
        self.addCleanup(env_patch.stop)
        key_patch = patch.object(updater, "UPDATE_SIGNING_PUBLIC_KEY", "")
        key_patch.start()
        self.addCleanup(key_patch.stop)


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


def _make_zip(path: Path, entries: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)


def _fake_pe_bytes() -> bytes:
    data = bytearray(256)
    data[0:2] = b"MZ"
    data[0x3C:0x40] = (64).to_bytes(4, "little")
    data[64:68] = b"PE\x00\x00"
    return bytes(data)


class UpdaterTests(UnsignedUpdateAllowedMixin, unittest.TestCase):
    def test_fetch_latest_update_info_filters_project_specific_releases(self) -> None:
        payload = [
            {
                "tag_name": "other-app-v9.9.9",
                "draft": False,
                "prerelease": False,
                "assets": [
                    {
                        "name": "OtherApp-v9.9.9-windows-x64.zip",
                        "browser_download_url": "https://example.com/other.zip",
                        "size": 11,
                    }
                ],
                "html_url": "https://example.com/other",
                "body": "other",
                "published_at": "2026-03-01T12:00:00Z",
            },
            {
                "tag_name": f"hidrostatik-test-v{NEXT_TEST_VERSION}",
                "draft": False,
                "prerelease": False,
                "assets": [
                    {
                        "name": f"HidrostatikTest-v{NEXT_TEST_VERSION}-windows-x64.zip",
                        "browser_download_url": "https://example.com/app.zip",
                        "size": 42,
                    }
                ],
                "html_url": "https://example.com/app",
                "body": "notes",
                "published_at": "2026-03-30T12:00:00Z",
            },
        ]

        with patch(
            "hidrostatik_test.services.updater.urlopen", return_value=_FakeJsonResponse(payload)
        ):
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

        with patch(
            "hidrostatik_test.services.updater.urlopen", return_value=_FakeJsonResponse(payload)
        ):
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
                "assets": [
                    {
                        "name": f"HidrostatikTest-v{NEXT_TEST_VERSION}-windows-x64.zip",
                        "browser_download_url": "https://example.com/app.zip",
                        "size": 42,
                    }
                ],
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

        with (
            patch("hidrostatik_test.services.updater.urlopen", side_effect=URLError("tls failure")),
            patch(
                "hidrostatik_test.services.updater.subprocess.run",
                return_value=powershell_result,
            ),
        ):
            info = fetch_latest_update_info()

        self.assertEqual(info.latest_version, NEXT_TEST_VERSION)
        self.assertTrue(info.update_available)
        self.assertEqual(info.source_repository, "SLedgehammer-dev12/HYDRO")

    def test_fetch_latest_update_info_falls_back_to_legacy_repo_when_primary_has_no_release(
        self,
    ) -> None:
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

            def write_test_zip(
                asset: ReleaseAsset, target_path: Path, timeout: int, **kwargs: object
            ) -> None:
                del asset, timeout, kwargs
                _make_zip(
                    target_path,
                    {
                        f"{BINARY_NAME}/marker.txt": b"ok",
                        f"{BINARY_NAME}/{BINARY_NAME}.exe": b"stub",
                    },
                )

            runtime = RuntimeContext(
                frozen=True,
                can_self_update=True,
                executable_path=executable_path,
                install_dir=install_dir,
            )

            with (
                patch(
                    "hidrostatik_test.services.updater.tempfile.mkdtemp", side_effect=fake_mkdtemp
                ),
                patch(
                    "hidrostatik_test.services.updater.get_runtime_context",
                    return_value=runtime,
                ),
                patch(
                    "hidrostatik_test.services.updater._download_asset",
                    side_effect=write_test_zip,
                ),
                patch("hidrostatik_test.services.updater.subprocess.Popen") as mocked_popen,
            ):
                result = install_update(info, download_root=chosen_dir)

            self.assertEqual(result, "self_update")
            self.assertEqual(captured["prefix"], "hidrostatik-update-")
            self.assertEqual(captured["dir"], str(chosen_dir))
            mocked_popen.assert_called_once()
            launch_command = mocked_popen.call_args.args[0]
            self.assertEqual(launch_command[0], "powershell")
            self.assertIn("-File", launch_command)
            self.assertTrue(str(launch_command[-1]).endswith(".ps1"))
            script_text = Path(launch_command[-1]).read_text(encoding="utf-8-sig")
            backup_path = install_dir.with_name(f"install-backup-{NEXT_TEST_VERSION}")
            self.assertIn(str(backup_path), script_text)
            self.assertIn("apply_update.log", script_text)
            self.assertIn("Geri alma", script_text)
            staged = working_root / "stage" / BINARY_NAME
            self.assertTrue((staged / "marker.txt").exists())
            self.assertTrue((staged / f"{BINARY_NAME}.exe").exists())
            self.assertFalse((install_dir / "marker.txt").exists())
            self.assertTrue((working_root / "apply_update.log").exists())

    def test_install_update_supports_single_exe_asset(self) -> None:
        exe_name = f"HidrostatikTest-v{NEXT_TEST_VERSION}-windows-x64.exe"
        info = UpdateInfo(
            current_version=APP_VERSION,
            latest_version=NEXT_TEST_VERSION,
            tag_name=f"hidrostatik-test-v{NEXT_TEST_VERSION}",
            html_url="https://example.com/update",
            body="notes",
            published_at="2026-03-30T12:00:00Z",
            asset=ReleaseAsset(
                name=exe_name,
                download_url=f"https://example.com/{exe_name}",
                size=1024,
            ),
            update_available=True,
            source_repository="SLedgehammer-dev12/HYDRO",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            working_root = base_dir / "work"
            working_root.mkdir()
            install_dir = base_dir / "install"
            install_dir.mkdir()
            executable_path = install_dir / "HidrostatikTest.exe"
            executable_path.write_bytes(_fake_pe_bytes())
            runtime = RuntimeContext(
                frozen=True,
                can_self_update=True,
                executable_path=executable_path,
                install_dir=install_dir,
            )

            def write_test_exe(
                asset: ReleaseAsset, target_path: Path, timeout: int, **kwargs: object
            ) -> None:
                del asset, timeout, kwargs
                target_path.write_bytes(_fake_pe_bytes())

            with (
                patch(
                    "hidrostatik_test.services.updater.tempfile.mkdtemp",
                    return_value=str(working_root),
                ),
                patch(
                    "hidrostatik_test.services.updater.get_runtime_context",
                    return_value=runtime,
                ),
                patch(
                    "hidrostatik_test.services.updater._download_asset",
                    side_effect=write_test_exe,
                ),
                patch("hidrostatik_test.services.updater.subprocess.Popen"),
            ):
                result = install_update(info, download_root=base_dir / "downloads")

            self.assertEqual(result, "self_update")
            staged_exe = working_root / "stage" / BINARY_NAME / f"{BINARY_NAME}.exe"
            self.assertTrue(staged_exe.exists())
            self.assertEqual(staged_exe.read_bytes(), _fake_pe_bytes())

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
                version="1.7.3",
            )

            script_text = script_path.read_text(encoding="utf-8-sig")

        self.assertEqual(script_path.suffix, ".ps1")
        self.assertIn("İş_Çalışan", script_text)
        self.assertIn("Çalışan programlar", script_text)
        self.assertIn("Copy-Item -LiteralPath", script_text)
        self.assertIn("Start-Process -FilePath $ExePath", script_text)
        self.assertIn("Hidrostatik_Test-backup-1.7.3", script_text)
        self.assertIn("$LogPath", script_text)
        self.assertIn(
            "Move-Item -LiteralPath $BackupDir -Destination $TargetDir -Force", script_text
        )


class UpdaterUtilityTests(UnsignedUpdateAllowedMixin, unittest.TestCase):
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
                {
                    "name": "HidrostatikTest-v1.7.2-windows-x64.zip",
                    "browser_download_url": "https://example.com/app.zip",
                    "size": 42,
                }
            ],
        }
        self.assertTrue(_matches_project_release(release))

    def test_matches_project_release_by_exe_asset_for_windows(self) -> None:
        release = {
            "tag_name": "custom-tag",
            "assets": [
                {
                    "name": "HidrostatikTest-v1.7.2-windows-x64.exe",
                    "browser_download_url": "https://example.com/app.exe",
                    "size": 42,
                }
            ],
        }
        self.assertTrue(_matches_project_release(release))

    def test_matches_project_release_by_asset_for_macos(self) -> None:
        release = {
            "tag_name": "custom-tag",
            "assets": [
                {
                    "name": "HidrostatikTest-v1.7.2-macos-universal.dmg",
                    "browser_download_url": "https://example.com/app.dmg",
                    "size": 42,
                }
            ],
        }
        self.assertTrue(_matches_project_release(release))

    def test_matches_project_release_returns_false_for_unrelated(self) -> None:
        release = {
            "tag_name": "other-app-v1.0.0",
            "assets": [
                {
                    "name": "OtherApp.exe",
                    "browser_download_url": "https://example.com/other.exe",
                    "size": 42,
                }
            ],
        }
        self.assertFalse(_matches_project_release(release))

    def test_select_latest_release_ignores_drafts(self) -> None:
        releases = [
            {
                "tag_name": "hidrostatik-test-v1.0.0",
                "draft": True,
                "prerelease": False,
                "assets": [],
            },
            {
                "tag_name": "hidrostatik-test-v2.0.0",
                "draft": False,
                "prerelease": False,
                "assets": [],
            },
        ]
        selected = _select_latest_release(releases, "HYDRO")
        self.assertEqual(selected["tag_name"], "hidrostatik-test-v2.0.0")

    def test_select_latest_release_ignores_prereleases(self) -> None:
        releases = [
            {
                "tag_name": "hidrostatik-test-v1.0.0",
                "draft": False,
                "prerelease": True,
                "assets": [],
            },
            {
                "tag_name": "hidrostatik-test-v2.0.0",
                "draft": False,
                "prerelease": False,
                "assets": [],
            },
        ]
        selected = _select_latest_release(releases, "HYDRO")
        self.assertEqual(selected["tag_name"], "hidrostatik-test-v2.0.0")

    def test_select_latest_release_sorts_by_version_desc(self) -> None:
        releases = [
            {
                "tag_name": "hidrostatik-test-v1.0.0",
                "draft": False,
                "prerelease": False,
                "assets": [],
            },
            {
                "tag_name": "hidrostatik-test-v3.0.0",
                "draft": False,
                "prerelease": False,
                "assets": [],
            },
            {
                "tag_name": "hidrostatik-test-v2.0.0",
                "draft": False,
                "prerelease": False,
                "assets": [],
            },
        ]
        selected = _select_latest_release(releases, "HYDRO")
        self.assertEqual(selected["tag_name"], "hidrostatik-test-v3.0.0")

    def test_select_latest_release_raises_when_no_matching(self) -> None:
        releases: list[dict[str, object]] = [
            {"tag_name": "other-app-v1.0.0", "draft": False, "prerelease": False, "assets": []}
        ]
        with self.assertRaisesRegex(RuntimeError, "yayin bulunamadi"):
            _select_latest_release(releases, "HYDRO")

    def test_extract_asset_matches_windows_zip_exactly(self) -> None:
        release = {
            "tag_name": "hidrostatik-test-v1.7.2",
            "assets": [
                {
                    "name": "HidrostatikTest-v1.7.2-windows-x64.zip",
                    "browser_download_url": "https://example.com/app.zip",
                    "size": 100,
                },
                {
                    "name": "HidrostatikTest-v1.7.2-macos-universal.dmg",
                    "browser_download_url": "https://example.com/app.dmg",
                    "size": 200,
                },
            ],
        }
        asset = _extract_asset(release, "1.7.2", platform="win32")
        self.assertIsNotNone(asset)
        self.assertEqual(asset.name, "HidrostatikTest-v1.7.2-windows-x64.zip")
        self.assertEqual(asset.size, 100)

    def test_extract_asset_prefers_dmg_on_macos(self) -> None:
        release = {
            "tag_name": "hidrostatik-test-v1.7.2",
            "assets": [
                {
                    "name": "HidrostatikTest-v1.7.2-windows-x64.zip",
                    "browser_download_url": "https://example.com/app.zip",
                    "size": 100,
                },
                {
                    "name": "HidrostatikTest-v1.7.2-macos-universal.dmg",
                    "browser_download_url": "https://example.com/app.dmg",
                    "size": 200,
                },
            ],
        }
        asset = _extract_asset(release, "1.7.2", platform="darwin")
        self.assertIsNotNone(asset)
        self.assertEqual(asset.name, "HidrostatikTest-v1.7.2-macos-universal.dmg")

    def test_extract_asset_matches_windows_exe_exactly(self) -> None:
        release = {
            "tag_name": "hidrostatik-test-v1.7.2",
            "assets": [
                {
                    "name": "HidrostatikTest-v1.7.2-windows-x64.exe",
                    "browser_download_url": "https://example.com/app.exe",
                    "size": 300,
                },
            ],
        }
        asset = _extract_asset(release, "1.7.2", platform="win32")
        self.assertIsNotNone(asset)
        self.assertEqual(asset.name, "HidrostatikTest-v1.7.2-windows-x64.exe")
        self.assertEqual(asset.size, 300)

    def test_extract_asset_prefers_zip_over_exe_when_both_exact(self) -> None:
        release = {
            "tag_name": "hidrostatik-test-v1.7.2",
            "assets": [
                {
                    "name": "HidrostatikTest-v1.7.2-windows-x64.exe",
                    "browser_download_url": "https://example.com/app.exe",
                    "size": 300,
                },
                {
                    "name": "HidrostatikTest-v1.7.2-windows-x64.zip",
                    "browser_download_url": "https://example.com/app.zip",
                    "size": 100,
                },
            ],
        }
        asset = _extract_asset(release, "1.7.2", platform="win32")
        self.assertIsNotNone(asset)
        self.assertEqual(asset.name, "HidrostatikTest-v1.7.2-windows-x64.zip")

    def test_extract_asset_accepts_fallback_only_for_requested_version(self) -> None:
        release = {
            "tag_name": "hidrostatik-test-v1.7.2",
            "assets": [
                {
                    "name": "HidrostatikTest-v1.7.2-win64-portable.zip",
                    "browser_download_url": "https://example.com/portable.zip",
                    "size": 50,
                },
            ],
        }
        asset = _extract_asset(release, "1.7.2", platform="win32")
        self.assertIsNotNone(asset)
        self.assertEqual(asset.name, "HidrostatikTest-v1.7.2-win64-portable.zip")

    def test_extract_asset_rejects_wrong_version_fallback(self) -> None:
        release = {
            "tag_name": "hidrostatik-test-v1.7.0",
            "assets": [
                {
                    "name": "HidrostatikTest-v1.7.0-windows-x64.zip",
                    "browser_download_url": "https://example.com/old.zip",
                    "size": 50,
                },
            ],
        }
        self.assertIsNone(_extract_asset(release, "1.7.2", platform="win32"))

    def test_extract_asset_rejects_version_prefix_collision(self) -> None:
        release = {
            "tag_name": "hidrostatik-test-v1.7.20",
            "assets": [
                {
                    "name": "HidrostatikTest-v1.7.20-windows-portable.zip",
                    "browser_download_url": "https://example.com/new.zip",
                    "size": 50,
                },
            ],
        }
        self.assertIsNone(_extract_asset(release, "1.7.2", platform="win32"))

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
                _verify_sha256(
                    file_path, "0000000000000000000000000000000000000000000000000000000000000000"
                )

    def test_checksum_candidates_include_asset_and_stem_urls(self) -> None:
        candidates = _checksum_candidate_urls("https://example.com/releases/app.zip")
        self.assertEqual(
            candidates,
            [
                "https://example.com/releases/app.zip.sha256.txt",
                "https://example.com/releases/app.sha256.txt",
            ],
        )

    def test_download_checksum_parses_sha_from_response(self) -> None:
        content = b"abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890  filename.zip"
        with patch(
            "hidrostatik_test.services.updater.urlopen", return_value=_FakeBytesResponse(content)
        ):
            result = _download_checksum("https://example.com/app.zip", 10)
        self.assertEqual(result, "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890")

    def test_download_checksum_parses_sha_with_tabs(self) -> None:
        content = b"abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890\tfilename.zip"
        with patch(
            "hidrostatik_test.services.updater.urlopen", return_value=_FakeBytesResponse(content)
        ):
            result = _download_checksum("https://example.com/app.zip", 10)
        self.assertEqual(result, "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890")

    def test_download_checksum_normalizes_to_lowercase(self) -> None:
        content = b"ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890"
        with patch(
            "hidrostatik_test.services.updater.urlopen", return_value=_FakeBytesResponse(content)
        ):
            result = _download_checksum("https://example.com/app.zip", 10)
        self.assertEqual(result, "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890")

    def test_download_checksum_raises_on_empty_content(self) -> None:
        with patch(
            "hidrostatik_test.services.updater.urlopen", return_value=_FakeBytesResponse(b"   ")
        ):
            with self.assertRaisesRegex(RuntimeError, "SHA-256 dosyasi bos"):
                _download_checksum("https://example.com/app.zip", 10)

    def test_download_checksum_raises_on_404(self) -> None:
        def fake_urlopen(request, timeout=10):
            raise HTTPError(request.full_url, 404, "Not Found", {}, None)

        with patch("hidrostatik_test.services.updater.urlopen", side_effect=fake_urlopen):
            with self.assertRaisesRegex(RuntimeError, "SHA-256 dogrulama dosyasi.*bulunamadi"):
                _download_checksum("https://example.com/app.zip", 10)

    def test_download_checksum_falls_back_to_published_stem_name_for_exe(self) -> None:
        checksum = b"abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
        requested: list[str] = []

        def fake_urlopen(request, timeout=10):
            requested.append(request.full_url)
            if request.full_url.endswith(".exe.sha256.txt"):
                raise HTTPError(request.full_url, 404, "Not Found", {}, None)
            return _FakeBytesResponse(checksum + b"  HidrostatikTest-v1.7.3-windows-x64.exe")

        with patch("hidrostatik_test.services.updater.urlopen", side_effect=fake_urlopen):
            result = _download_checksum(
                "https://example.com/HidrostatikTest-v1.7.3-windows-x64.exe", 10
            )

        self.assertEqual(result, checksum.decode())
        self.assertEqual(
            requested,
            [
                "https://example.com/HidrostatikTest-v1.7.3-windows-x64.exe.sha256.txt",
                "https://example.com/HidrostatikTest-v1.7.3-windows-x64.sha256.txt",
            ],
        )

    def test_download_checksum_uses_stem_name_for_zip_release(self) -> None:
        checksum = b"1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        requested: list[str] = []

        def fake_urlopen(request, timeout=10):
            requested.append(request.full_url)
            if request.full_url.endswith(".zip.sha256.txt"):
                raise HTTPError(request.full_url, 404, "Not Found", {}, None)
            return _FakeBytesResponse(checksum)

        with patch("hidrostatik_test.services.updater.urlopen", side_effect=fake_urlopen):
            result = _download_checksum(
                "https://example.com/HidrostatikTest-v1.7.3-windows-x64.zip", 10
            )

        self.assertEqual(result, checksum.decode())
        self.assertTrue(requested[1].endswith("/HidrostatikTest-v1.7.3-windows-x64.sha256.txt"))

    def test_safe_extract_accepts_expected_structure_and_windows_separators(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            archive_path = base / "update.zip"
            _make_zip(
                archive_path,
                {
                    f"{BINARY_NAME}\\{BINARY_NAME}.exe": b"MZ",
                    f"{BINARY_NAME}\\data\\table.csv": b"a,b",
                },
            )
            app_dir = _safe_extract_zip(archive_path, base / "extract")

            self.assertEqual(app_dir.name, BINARY_NAME)
            self.assertTrue((app_dir / f"{BINARY_NAME}.exe").is_file())
            self.assertTrue((app_dir / "data" / "table.csv").is_file())

    def test_safe_extract_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            archive_path = base / "update.zip"
            _make_zip(
                archive_path,
                {
                    f"{BINARY_NAME}/{BINARY_NAME}.exe": b"MZ",
                    "../../evil.txt": b"pwned",
                },
            )
            with self.assertRaisesRegex(UpdateError, "guvenli olmayan"):
                _safe_extract_zip(archive_path, base / "extract")
            self.assertFalse((base / "evil.txt").exists())

    def test_safe_extract_rejects_absolute_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            archive_path = base / "update.zip"
            _make_zip(
                archive_path,
                {
                    f"{BINARY_NAME}/{BINARY_NAME}.exe": b"MZ",
                    "/tmp/evil.txt": b"pwned",
                },
            )
            with self.assertRaisesRegex(UpdateError, "guvenli olmayan"):
                _safe_extract_zip(archive_path, base / "extract")

    def test_safe_extract_rejects_symlink_member(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            archive_path = base / "update.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr(f"{BINARY_NAME}/{BINARY_NAME}.exe", b"MZ")
                info = zipfile.ZipInfo(f"{BINARY_NAME}/link")
                info.external_attr = 0o120777 << 16  # S_IFLNK
                archive.writestr(info, "target")
            with self.assertRaisesRegex(UpdateError, "sembolik baglanti"):
                _safe_extract_zip(archive_path, base / "extract")

    def test_safe_extract_rejects_missing_expected_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            archive_path = base / "update.zip"
            _make_zip(archive_path, {f"{BINARY_NAME}/marker.txt": b"ok"})
            with self.assertRaisesRegex(UpdateError, "beklenen yapiyi icermiyor"):
                _safe_extract_zip(archive_path, base / "extract")

    def test_safe_extract_enforces_file_count_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            archive_path = base / "update.zip"
            _make_zip(
                archive_path,
                {
                    f"{BINARY_NAME}/{BINARY_NAME}.exe": b"MZ",
                    f"{BINARY_NAME}/a.txt": b"a",
                    f"{BINARY_NAME}/b.txt": b"b",
                },
            )
            with patch.object(updater, "MAX_EXTRACTED_FILES", 2):
                with self.assertRaisesRegex(UpdateError, "cok fazla dosya"):
                    _safe_extract_zip(archive_path, base / "extract")

    def test_safe_extract_enforces_extracted_size_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            archive_path = base / "update.zip"
            _make_zip(
                archive_path,
                {
                    f"{BINARY_NAME}/{BINARY_NAME}.exe": b"MZ",
                    f"{BINARY_NAME}/big.bin": bytes(range(256)) * 8,
                },
            )
            with patch.object(updater, "MAX_EXTRACTED_BYTES", 512):
                with self.assertRaisesRegex(UpdateError, "boyut siniri"):
                    _safe_extract_zip(archive_path, base / "extract")

    def test_safe_extract_rejects_non_zip_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            archive_path = base / "update.zip"
            archive_path.write_bytes(b"not a zip")
            with self.assertRaisesRegex(UpdateError, "gecerli bir zip degil"):
                _safe_extract_zip(archive_path, base / "extract")

    def test_ensure_pe_executable_accepts_pe_header(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            exe_path = Path(temp_dir) / "app.exe"
            exe_path.write_bytes(_fake_pe_bytes())
            _ensure_pe_executable(exe_path)

    def test_ensure_pe_executable_rejects_non_pe_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            exe_path = Path(temp_dir) / "app.exe"
            exe_path.write_bytes(b"MZ" + b"\0" * 200)
            with self.assertRaisesRegex(UpdateError, "PE basligi"):
                _ensure_pe_executable(exe_path)

    def test_install_macos_update_uses_private_mount_and_verifies_signature(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            asset_path = base / "HidrostatikTest.dmg"
            asset_path.write_bytes(b"dmg")
            apps_dir = base / "Applications"
            log_path = base / "apply_update.log"
            commands: list[list[str]] = []

            def fake_run(arguments, **kwargs):
                command = [str(part) for part in arguments]
                commands.append(command)
                if command[0] == "hdiutil" and command[1] == "attach":
                    mount_point = Path(command[command.index("-mountpoint") + 1])
                    app = mount_point / f"{BINARY_NAME}.app"
                    (app / "Contents").mkdir(parents=True)
                    landmark = app / "Contents" / "Info.plist"
                    landmark.write_text("plist", encoding="utf-8")
                return subprocess.CompletedProcess(arguments, 0, "", "")

            with (
                patch("hidrostatik_test.services.updater.subprocess.run", side_effect=fake_run),
                patch("hidrostatik_test.services.updater.subprocess.Popen") as mocked_popen,
            ):
                _install_macos_update(
                    asset_path,
                    BINARY_NAME,
                    version="1.7.3",
                    apps_dir=apps_dir,
                    log_path=log_path,
                )

            attach_command = commands[0]
            mount_point = Path(attach_command[attach_command.index("-mountpoint") + 1])
            self.assertFalse(str(mount_point).startswith("/Volumes/"))
            self.assertIn("-readonly", attach_command)
            self.assertIn("-nobrowse", attach_command)
            flat_commands = [" ".join(command) for command in commands]
            self.assertFalse(any("xattr" in command for command in flat_commands))
            self.assertTrue(
                any("codesign --verify --deep --strict" in command for command in flat_commands)
            )
            install_command = next(
                command
                for command in commands
                if command[0] == "ditto"
                and "-backup-" not in command[1]
                and command[2] == str(apps_dir / f"{BINARY_NAME}.app")
            )
            self.assertIn(str(mount_point / f"{BINARY_NAME}.app"), install_command[1])
            self.assertTrue(any("hdiutil detach" in command for command in flat_commands))
            log_text = log_path.read_text(encoding="utf-8")
            self.assertIn("codesign", log_text)
            mocked_popen.assert_called_once()
            self.assertEqual(mocked_popen.call_args.args[0][0], "open")
            self.assertEqual(
                mocked_popen.call_args.args[0][1],
                str(apps_dir / f"{BINARY_NAME}.app"),
            )

    def test_install_macos_update_rolls_back_when_copy_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            asset_path = base / "HidrostatikTest.dmg"
            asset_path.write_bytes(b"dmg")
            apps_dir = base / "Applications"
            existing_app = apps_dir / f"{BINARY_NAME}.app"
            existing_app.mkdir(parents=True)
            (existing_app / "old.txt").write_text("old", encoding="utf-8")
            log_path = base / "apply_update.log"

            def fake_run(arguments, **kwargs):
                command = [str(part) for part in arguments]
                if command[0] == "hdiutil" and command[1] == "attach":
                    mount_point = Path(command[command.index("-mountpoint") + 1])
                    app = mount_point / f"{BINARY_NAME}.app"
                    app.mkdir(parents=True)
                if command[0] == "ditto" and "-backup-" in command[2]:
                    Path(command[2]).mkdir(parents=True, exist_ok=True)
                if (
                    command[0] == "ditto"
                    and "mount" in Path(command[1]).parts
                    and "-backup-" not in command[1]
                ):
                    raise subprocess.CalledProcessError(1, command)
                return subprocess.CompletedProcess(command, 0, "", "")

            with (
                patch("hidrostatik_test.services.updater.subprocess.run", side_effect=fake_run),
                patch("hidrostatik_test.services.updater.subprocess.Popen"),
            ):
                with self.assertRaises(UpdateError):
                    _install_macos_update(
                        asset_path,
                        BINARY_NAME,
                        version="1.7.3",
                        apps_dir=apps_dir,
                        log_path=log_path,
                    )

            log_text = log_path.read_text(encoding="utf-8")
            self.assertIn("Geri alma tamamlandi", log_text)


class SignatureEnforcementTests(unittest.TestCase):
    """Imza varsayilan olarak zorunludur: imzasiz/bozuk paket kurulmaz."""

    def _env(self, **values: str):
        return patch.dict(os.environ, _clean_hydro_env(**values), clear=True)

    def test_embedded_public_key_is_a_32_byte_ed25519_key(self) -> None:
        self.assertTrue(UPDATE_SIGNING_PUBLIC_KEY)
        self.assertEqual(len(_decode_public_key(UPDATE_SIGNING_PUBLIC_KEY)), 32)

    def test_unsigned_update_is_rejected_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            asset_path = Path(temp_dir) / "app.zip"
            asset_path.write_bytes(b"payload")
            with (
                self._env(),
                patch(
                    "hidrostatik_test.services.updater.urlopen",
                    side_effect=HTTPError(
                        "https://example.com/app.zip.sig", 404, "Not Found", {}, None
                    ),
                ) as mocked_urlopen,
            ):
                with self.assertRaisesRegex(UpdateError, r"imzasi \(\.sig\) bulunamadi"):
                    verify_asset_signature(asset_path, "https://example.com/app.zip", 10)

            # .sig ve .minisig adaylari denendi; hicbiri bulunamadi.
            self.assertEqual(mocked_urlopen.call_count, 2)

    @unittest.skipUnless(HAVE_CRYPTOGRAPHY, "cryptography paketi yok")
    def test_valid_raw_signature_is_accepted_with_embedded_key(self) -> None:
        private_key, public_b64 = _new_keypair()
        with tempfile.TemporaryDirectory() as temp_dir:
            asset_path = Path(temp_dir) / "app.zip"
            asset_path.write_bytes(b"payload")
            signature = private_key.sign(b"payload")
            with (
                self._env(),
                patch.object(updater, "UPDATE_SIGNING_PUBLIC_KEY", public_b64),
                patch(
                    "hidrostatik_test.services.updater.urlopen",
                    return_value=_FakeBytesResponse(signature),
                ) as mocked_urlopen,
            ):
                verified = verify_asset_signature(asset_path, "https://example.com/app.zip", 10)

            self.assertTrue(verified)
            self.assertTrue(mocked_urlopen.call_args.args[0].full_url.endswith("app.zip.sig"))

    @unittest.skipUnless(HAVE_CRYPTOGRAPHY, "cryptography paketi yok")
    def test_base64_signature_format_is_accepted(self) -> None:
        private_key, public_b64 = _new_keypair()
        with tempfile.TemporaryDirectory() as temp_dir:
            asset_path = Path(temp_dir) / "app.zip"
            asset_path.write_bytes(b"payload")
            signature_b64 = base64.b64encode(private_key.sign(b"payload")) + b"\n"
            with (
                self._env(),
                patch.object(updater, "UPDATE_SIGNING_PUBLIC_KEY", public_b64),
                patch(
                    "hidrostatik_test.services.updater.urlopen",
                    return_value=_FakeBytesResponse(signature_b64),
                ),
            ):
                verified = verify_asset_signature(asset_path, "https://example.com/app.zip", 10)

            self.assertTrue(verified)

    @unittest.skipUnless(HAVE_CRYPTOGRAPHY, "cryptography paketi yok")
    def test_corrupted_signature_is_rejected(self) -> None:
        private_key, public_b64 = _new_keypair()
        with tempfile.TemporaryDirectory() as temp_dir:
            asset_path = Path(temp_dir) / "app.zip"
            asset_path.write_bytes(b"payload")
            corrupted = bytearray(private_key.sign(b"payload"))
            corrupted[0] ^= 0xFF
            with (
                self._env(),
                patch.object(updater, "UPDATE_SIGNING_PUBLIC_KEY", public_b64),
                patch(
                    "hidrostatik_test.services.updater.urlopen",
                    return_value=_FakeBytesResponse(bytes(corrupted)),
                ),
            ):
                with self.assertRaisesRegex(UpdateError, "imzasi gecersiz"):
                    verify_asset_signature(asset_path, "https://example.com/app.zip", 10)

    @unittest.skipUnless(HAVE_CRYPTOGRAPHY, "cryptography paketi yok")
    def test_signature_from_foreign_key_is_rejected(self) -> None:
        foreign_key, _foreign_public = _new_keypair()
        _trusted_key, trusted_public = _new_keypair()
        with tempfile.TemporaryDirectory() as temp_dir:
            asset_path = Path(temp_dir) / "app.zip"
            asset_path.write_bytes(b"payload")
            with (
                self._env(),
                patch.object(updater, "UPDATE_SIGNING_PUBLIC_KEY", trusted_public),
                patch(
                    "hidrostatik_test.services.updater.urlopen",
                    return_value=_FakeBytesResponse(foreign_key.sign(b"payload")),
                ),
            ):
                with self.assertRaisesRegex(UpdateError, "imzasi gecersiz"):
                    verify_asset_signature(asset_path, "https://example.com/app.zip", 10)

    @unittest.skipUnless(HAVE_CRYPTOGRAPHY, "cryptography paketi yok")
    def test_env_pubkey_overrides_embedded_key_for_rotation(self) -> None:
        rotation_key, rotation_public = _new_keypair()
        embedded_key, embedded_public = _new_keypair()
        with tempfile.TemporaryDirectory() as temp_dir:
            asset_path = Path(temp_dir) / "app.zip"
            asset_path.write_bytes(b"payload")
            rotation_signature = rotation_key.sign(b"payload")
            with (
                self._env(HYDRO_UPDATE_PUBKEY=rotation_public),
                patch.object(updater, "UPDATE_SIGNING_PUBLIC_KEY", embedded_public),
                patch(
                    "hidrostatik_test.services.updater.urlopen",
                    return_value=_FakeBytesResponse(rotation_signature),
                ),
            ):
                self.assertTrue(
                    verify_asset_signature(asset_path, "https://example.com/app.zip", 10)
                )

            # Ayni imza, override kaldirilinca gomulu anahtarla reddedilir.
            with (
                self._env(),
                patch.object(updater, "UPDATE_SIGNING_PUBLIC_KEY", embedded_public),
                patch(
                    "hidrostatik_test.services.updater.urlopen",
                    return_value=_FakeBytesResponse(rotation_signature),
                ),
            ):
                with self.assertRaisesRegex(UpdateError, "imzasi gecersiz"):
                    verify_asset_signature(asset_path, "https://example.com/app.zip", 10)

            # Gomulu anahtarin imzasi override etkinken gecersizdir.
            with (
                self._env(HYDRO_UPDATE_PUBKEY=rotation_public),
                patch.object(updater, "UPDATE_SIGNING_PUBLIC_KEY", embedded_public),
                patch(
                    "hidrostatik_test.services.updater.urlopen",
                    return_value=_FakeBytesResponse(embedded_key.sign(b"payload")),
                ),
            ):
                with self.assertRaisesRegex(UpdateError, "imzasi gecersiz"):
                    verify_asset_signature(asset_path, "https://example.com/app.zip", 10)

    @unittest.skipUnless(HAVE_CRYPTOGRAPHY, "cryptography paketi yok")
    def test_env_pubkey_can_point_to_a_key_file(self) -> None:
        private_key, public_b64 = _new_keypair()
        with tempfile.TemporaryDirectory() as temp_dir:
            asset_path = Path(temp_dir) / "app.zip"
            asset_path.write_bytes(b"payload")
            key_file = Path(temp_dir) / "public_key.txt"
            key_file.write_text(public_b64, encoding="utf-8")
            with (
                self._env(HYDRO_UPDATE_PUBKEY=str(key_file)),
                patch(
                    "hidrostatik_test.services.updater.urlopen",
                    return_value=_FakeBytesResponse(private_key.sign(b"payload")),
                ),
            ):
                self.assertTrue(
                    verify_asset_signature(asset_path, "https://example.com/app.zip", 10)
                )

    def test_missing_public_key_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            asset_path = Path(temp_dir) / "app.zip"
            asset_path.write_bytes(b"payload")
            with (
                self._env(),
                patch.object(updater, "UPDATE_SIGNING_PUBLIC_KEY", ""),
                patch("hidrostatik_test.services.updater.urlopen") as mocked_urlopen,
            ):
                with self.assertRaisesRegex(UpdateError, "imza anahtari tanimli degil"):
                    verify_asset_signature(asset_path, "https://example.com/app.zip", 10)
            mocked_urlopen.assert_not_called()

    @unittest.skipUnless(HAVE_CRYPTOGRAPHY, "cryptography paketi yok")
    def test_allow_unsigned_env_flag_tolerates_missing_signature(self) -> None:
        _private_key, public_b64 = _new_keypair()
        with tempfile.TemporaryDirectory() as temp_dir:
            asset_path = Path(temp_dir) / "app.zip"
            asset_path.write_bytes(b"payload")
            with (
                self._env(HYDRO_ALLOW_UNSIGNED_UPDATE="1"),
                patch.object(updater, "UPDATE_SIGNING_PUBLIC_KEY", public_b64),
                patch(
                    "hidrostatik_test.services.updater.urlopen",
                    side_effect=HTTPError(
                        "https://example.com/app.zip.sig", 404, "Not Found", {}, None
                    ),
                ),
            ):
                verified = verify_asset_signature(asset_path, "https://example.com/app.zip", 10)
            self.assertFalse(verified)

    @unittest.skipUnless(HAVE_CRYPTOGRAPHY, "cryptography paketi yok")
    def test_require_signature_zero_flag_tolerates_missing_signature(self) -> None:
        _private_key, public_b64 = _new_keypair()
        with tempfile.TemporaryDirectory() as temp_dir:
            asset_path = Path(temp_dir) / "app.zip"
            asset_path.write_bytes(b"payload")
            with (
                self._env(HYDRO_REQUIRE_SIGNATURE="0"),
                patch.object(updater, "UPDATE_SIGNING_PUBLIC_KEY", public_b64),
                patch(
                    "hidrostatik_test.services.updater.urlopen",
                    side_effect=HTTPError(
                        "https://example.com/app.zip.sig", 404, "Not Found", {}, None
                    ),
                ),
            ):
                verified = verify_asset_signature(asset_path, "https://example.com/app.zip", 10)
            self.assertFalse(verified)

    @unittest.skipUnless(HAVE_CRYPTOGRAPHY, "cryptography paketi yok")
    def test_developer_escape_still_rejects_a_bad_signature(self) -> None:
        private_key, public_b64 = _new_keypair()
        with tempfile.TemporaryDirectory() as temp_dir:
            asset_path = Path(temp_dir) / "app.zip"
            asset_path.write_bytes(b"payload")
            with (
                self._env(HYDRO_ALLOW_UNSIGNED_UPDATE="1"),
                patch.object(updater, "UPDATE_SIGNING_PUBLIC_KEY", public_b64),
                patch(
                    "hidrostatik_test.services.updater.urlopen",
                    return_value=_FakeBytesResponse(private_key.sign(b"other-payload")),
                ),
            ):
                with self.assertRaisesRegex(UpdateError, "imzasi gecersiz"):
                    verify_asset_signature(asset_path, "https://example.com/app.zip", 10)

    def test_malformed_signature_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            asset_path = Path(temp_dir) / "app.zip"
            asset_path.write_bytes(b"payload")
            with (
                self._env(),
                patch(
                    "hidrostatik_test.services.updater.urlopen",
                    return_value=_FakeBytesResponse(b"not-a-valid-signature!!"),
                ),
            ):
                with self.assertRaisesRegex(UpdateError, "base64 olarak okunamadi"):
                    verify_asset_signature(asset_path, "https://example.com/app.zip", 10)

    def test_signature_download_http_error_is_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            asset_path = Path(temp_dir) / "app.zip"
            asset_path.write_bytes(b"payload")
            with (
                self._env(),
                patch(
                    "hidrostatik_test.services.updater.urlopen",
                    side_effect=HTTPError(
                        "https://example.com/app.zip.sig", 500, "Server Error", {}, None
                    ),
                ),
            ):
                with self.assertRaisesRegex(UpdateError, r"HTTP 500.*iptal edildi"):
                    verify_asset_signature(asset_path, "https://example.com/app.zip", 10)

    def test_signature_download_network_error_is_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            asset_path = Path(temp_dir) / "app.zip"
            asset_path.write_bytes(b"payload")
            with (
                self._env(),
                patch(
                    "hidrostatik_test.services.updater.urlopen",
                    side_effect=URLError("offline"),
                ),
            ):
                with self.assertRaisesRegex(UpdateError, "Imza dosyasina ulasilamadi"):
                    verify_asset_signature(asset_path, "https://example.com/app.zip", 10)

    def test_download_asset_rejects_unsigned_package(self) -> None:
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
                self._env(),
                patch(
                    "hidrostatik_test.services.download_manager.DownloadManager.download_file",
                    side_effect=fake_download,
                ),
                patch(
                    "hidrostatik_test.services.updater._download_checksum",
                    return_value=hashlib.sha256(b"downloaded-data").hexdigest(),
                ),
                patch(
                    "hidrostatik_test.services.updater.urlopen",
                    side_effect=HTTPError(
                        "https://example.com/app.zip.sig", 404, "Not Found", {}, None
                    ),
                ),
            ):
                with self.assertRaisesRegex(UpdateError, r"imzasi \(\.sig\) bulunamadi"):
                    _download_asset(asset, target_path, 10)

    def test_install_update_does_not_apply_unsigned_package(self) -> None:
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
            working_root = base_dir / "work"
            working_root.mkdir()
            install_dir = base_dir / "install"
            install_dir.mkdir()
            executable_path = install_dir / "HidrostatikTest.exe"
            executable_path.write_bytes(_fake_pe_bytes())
            runtime = RuntimeContext(
                frozen=True,
                can_self_update=True,
                executable_path=executable_path,
                install_dir=install_dir,
            )

            def fake_download(url: str, dest: Path, on_progress=None):
                del url, on_progress
                _make_zip(
                    dest,
                    {
                        f"{BINARY_NAME}/marker.txt": b"ok",
                        f"{BINARY_NAME}/{BINARY_NAME}.exe": b"stub",
                    },
                )

            with (
                self._env(),
                patch(
                    "hidrostatik_test.services.updater.tempfile.mkdtemp",
                    return_value=str(working_root),
                ),
                patch(
                    "hidrostatik_test.services.updater.get_runtime_context",
                    return_value=runtime,
                ),
                patch(
                    "hidrostatik_test.services.download_manager.DownloadManager.download_file",
                    side_effect=fake_download,
                ),
                patch(
                    "hidrostatik_test.services.updater._download_checksum",
                    return_value="0" * 64,
                ),
                patch("hidrostatik_test.services.updater._verify_sha256"),
                patch(
                    "hidrostatik_test.services.updater.urlopen",
                    side_effect=HTTPError(
                        "https://example.com/update.zip.sig", 404, "Not Found", {}, None
                    ),
                ),
                patch("hidrostatik_test.services.updater.subprocess.Popen") as mocked_popen,
            ):
                with self.assertRaisesRegex(UpdateError, r"imzasi \(\.sig\) bulunamadi"):
                    install_update(info, download_root=base_dir / "downloads")

            mocked_popen.assert_not_called()
            self.assertFalse((working_root / "stage").exists())
            self.assertFalse((install_dir / "marker.txt").exists())


class UpdateSigningToolTests(unittest.TestCase):
    """tools/update_signing.py: generate / sign / verify ve updater uyumu."""

    def _run_tool(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SIGNING_TOOL), *arguments],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

    @unittest.skipUnless(HAVE_CRYPTOGRAPHY, "cryptography paketi yok")
    def test_generate_sign_verify_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            key_path = Path(temp_dir) / "update_signing_key.pem"
            generated = self._run_tool("generate", "--key", str(key_path))
            self.assertEqual(generated.returncode, 0, generated.stderr)
            public_b64 = generated.stdout.strip()
            self.assertEqual(len(base64.b64decode(public_b64)), 32)
            self.assertTrue(key_path.is_file())
            self.assertEqual(key_path.stat().st_mode & 0o777, 0o600)

            artifact = Path(temp_dir) / "app.zip"
            artifact.write_bytes(b"release-payload")
            signed = self._run_tool("sign", str(artifact), "--key", str(key_path))
            self.assertEqual(signed.returncode, 0, signed.stderr)
            signature_path = artifact.with_name("app.zip.sig")
            self.assertTrue(signature_path.is_file())
            signature = base64.b64decode(signature_path.read_text(encoding="ascii").strip())
            self.assertEqual(len(signature), 64)

            verified = self._run_tool(
                "verify", str(artifact), str(signature_path), "--public-key", public_b64
            )
            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assertIn("OK", verified.stdout)

            # Bozulan artefakt reddedilir.
            artifact.write_bytes(b"tampered-payload")
            tampered = self._run_tool(
                "verify", str(artifact), str(signature_path), "--public-key", public_b64
            )
            self.assertNotEqual(tampered.returncode, 0)
            self.assertIn("GECERSIZ", tampered.stderr)

    @unittest.skipUnless(HAVE_CRYPTOGRAPHY, "cryptography paketi yok")
    def test_tool_signature_is_accepted_by_updater(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            key_path = Path(temp_dir) / "update_signing_key.pem"
            generated = self._run_tool("generate", "--key", str(key_path))
            self.assertEqual(generated.returncode, 0, generated.stderr)
            public_b64 = generated.stdout.strip()

            artifact = Path(temp_dir) / "app.zip"
            artifact.write_bytes(b"release-payload")
            signed = self._run_tool("sign", str(artifact), "--key", str(key_path))
            self.assertEqual(signed.returncode, 0, signed.stderr)
            signature_bytes = artifact.with_name("app.zip.sig").read_bytes()

            with (
                patch.dict(
                    os.environ,
                    _clean_hydro_env(HYDRO_UPDATE_PUBKEY=public_b64),
                    clear=True,
                ),
                patch(
                    "hidrostatik_test.services.updater.urlopen",
                    return_value=_FakeBytesResponse(signature_bytes),
                ),
            ):
                verified = verify_asset_signature(artifact, "https://example.com/app.zip", 10)

            self.assertTrue(verified)

    @unittest.skipUnless(HAVE_CRYPTOGRAPHY, "cryptography paketi yok")
    def test_generate_does_not_overwrite_existing_key_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            key_path = Path(temp_dir) / "update_signing_key.pem"
            first = self._run_tool("generate", "--key", str(key_path))
            self.assertEqual(first.returncode, 0, first.stderr)
            original = key_path.read_bytes()

            second = self._run_tool("generate", "--key", str(key_path))
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(second.stdout.strip(), first.stdout.strip())
            self.assertEqual(key_path.read_bytes(), original)
            self.assertIn("zaten mevcut", second.stderr)

            forced = self._run_tool("generate", "--key", str(key_path), "--force")
            self.assertEqual(forced.returncode, 0, forced.stderr)
            self.assertNotEqual(forced.stdout.strip(), first.stdout.strip())
            self.assertNotEqual(key_path.read_bytes(), original)

    def test_sign_without_private_key_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "app.zip"
            artifact.write_bytes(b"payload")
            result = self._run_tool(
                "sign", str(artifact), "--key", str(Path(temp_dir) / "missing.pem")
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("Ozel anahtar bulunamadi", result.stderr)
            self.assertFalse(artifact.with_name("app.zip.sig").exists())

    def test_verify_without_signature_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "app.zip"
            artifact.write_bytes(b"payload")
            result = self._run_tool("verify", str(artifact))
            self.assertEqual(result.returncode, 1)
            self.assertIn("Imza dosyasi bulunamadi", result.stderr)


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
        self.assertIn(
            f"HidrostatikTest-v{NEXT_TEST_VERSION}-windows-x64.zip",
            self.app.update_detail_var.get(),
        )
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

        with (
            patch("hidrostatik_test.ui.app.messagebox.askyesno", return_value=True),
            patch.object(
                self.app,
                "_apply_available_update",
            ) as mocked_apply,
        ):
            self.app._handle_update_check_result(info, user_requested=True)

        mocked_apply.assert_called_once()


if __name__ == "__main__":
    unittest.main()

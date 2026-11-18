"""Tests for signed GitHub Release WebUpdateManager and /api/update/* endpoints."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import Any

import pytest
from app.api import system as system_api
from app.services import web_updater
from app.services.web_updater import WebUpdateManager, _extract_web_assets
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hidrostatik_test.services import updater
from hidrostatik_test.services.updater import UpdateError


def _sample_release(version: str = "9.9.9") -> list[dict[str, Any]]:
    base = (
        f"https://github.com/SLedgehammer-dev12/HYDRO/releases/download/hidrostatik-test-v{version}"
    )
    assets = [
        f"HydroWeb-v{version}-macos-arm64.dmg",
        f"HydroWeb-v{version}-macos-arm64.dmg.sha256.txt",
        f"HydroWeb-v{version}-macos-arm64.dmg.sig",
        f"HydroWeb-v{version}-windows-x64-setup.exe",
        f"HydroWeb-v{version}-windows-x64-setup.exe.sha256.txt",
        f"HydroWeb-v{version}-windows-x64-setup.exe.sig",
        f"HydroWeb-v{version}-windows-x64-portable.zip",
        f"HydroWeb-v{version}-windows-x64-portable.zip.sha256.txt",
        f"HydroWeb-v{version}-windows-x64-portable.zip.sig",
    ]
    return [
        {
            "tag_name": f"hidrostatik-test-v{version}",
            "html_url": f"https://github.com/SLedgehammer-dev12/HYDRO/releases/tag/hidrostatik-test-v{version}",
            "published_at": "2026-11-18T00:00:00Z",
            "body": "### HYDRO Web Güncelleme Test Notları",
            "draft": False,
            "prerelease": False,
            "assets": [
                {
                    "name": name,
                    "browser_download_url": f"{base}/{name}",
                    "size": 4096 if not name.endswith((".txt", ".sig")) else 128,
                }
                for name in assets
            ],
        }
    ]


def _new_keypair() -> tuple[Ed25519PrivateKey, str]:
    priv = Ed25519PrivateKey.generate()
    pub_raw = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return priv, base64.b64encode(pub_raw).decode("ascii")


@pytest.fixture()
def isolated_manager(monkeypatch: pytest.MonkeyPatch) -> WebUpdateManager:
    monkeypatch.delenv("HYDRO_ALLOW_UNSIGNED_UPDATE", raising=False)
    monkeypatch.delenv("HYDRO_REQUIRE_SIGNATURE", raising=False)
    manager = WebUpdateManager(exit_scheduler=lambda: None)
    monkeypatch.setattr(system_api, "WEB_UPDATE_MANAGER", manager)
    return manager


def test_extract_web_assets_and_check_platform_selection(monkeypatch: pytest.MonkeyPatch):
    release = _sample_release("9.9.9")[0]

    mac_asset, all_assets = _extract_web_assets(
        release, "9.9.9", platform_key="darwin", prefer_kind="macos_arm64_dmg"
    )
    assert mac_asset is not None
    assert mac_asset.name == "HydroWeb-v9.9.9-macos-arm64.dmg"
    assert len(all_assets) == 3

    win_setup, _ = _extract_web_assets(
        release, "9.9.9", platform_key="win32", prefer_kind="windows_setup_exe"
    )
    assert win_setup is not None
    assert win_setup.name == "HydroWeb-v9.9.9-windows-x64-setup.exe"

    win_port, _ = _extract_web_assets(
        release, "9.9.9", platform_key="win32", prefer_kind="windows_portable_zip"
    )
    assert win_port is not None
    assert win_port.name == "HydroWeb-v9.9.9-windows-x64-portable.zip"

    monkeypatch.setattr(
        web_updater, "_fetch_release_payload", lambda url, timeout=15: _sample_release("9.9.9")
    )
    monkeypatch.setattr(
        web_updater,
        "get_web_runtime_context",
        lambda: {
            "frozen": False,
            "platform": "darwin",
            "arch": "arm64",
            "install_mode": "download_only",
            "can_self_install": False,
            "executable_path": "/tmp/python",
            "install_dir": "/tmp",
            "prefer_kind": "macos_arm64_dmg",
        },
    )
    mgr = WebUpdateManager(exit_scheduler=lambda: None)
    status = mgr.check_for_updates(force=True)
    assert status["update_available"] is True
    assert status["latest_version"] == "9.9.9"
    assert status["selected_asset"]["name"] == "HydroWeb-v9.9.9-macos-arm64.dmg"
    assert status["job"]["state"] == "available"


def test_signed_download_verification_and_fail_closed_rejections(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.delenv("HYDRO_ALLOW_UNSIGNED_UPDATE", raising=False)
    monkeypatch.delenv("HYDRO_REQUIRE_SIGNATURE", raising=False)

    payload_bytes = b"HYDRO-WEB-SIGNED-DMG-BINARY-PAYLOAD" * 64
    expected_sha = hashlib.sha256(payload_bytes).hexdigest()
    priv_key, pub_b64 = _new_keypair()
    valid_sig = priv_key.sign(payload_bytes)

    monkeypatch.setenv("HYDRO_UPDATE_PUBKEY", pub_b64)
    monkeypatch.setattr(
        web_updater, "_fetch_release_payload", lambda url, timeout=15: _sample_release("9.9.9")
    )
    monkeypatch.setattr(
        web_updater,
        "get_web_runtime_context",
        lambda: {
            "frozen": False,
            "platform": "darwin",
            "arch": "arm64",
            "install_mode": "download_only",
            "can_self_install": False,
            "executable_path": "/tmp/python",
            "install_dir": "/tmp",
            "prefer_kind": "macos_arm64_dmg",
        },
    )

    class _FakeDownloader:
        def download_file(self, url: str, dest_path: Path, on_progress=None, **_kwargs) -> Path:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(payload_bytes)
            if on_progress is not None:
                on_progress(dest_path, len(payload_bytes), len(payload_bytes), 1000.0, 0.0)
            return dest_path

    monkeypatch.setattr(web_updater, "DownloadManager", _FakeDownloader)
    monkeypatch.setattr(web_updater, "_download_checksum", lambda url, timeout=15: expected_sha)
    monkeypatch.setattr(updater, "_download_signature", lambda url, timeout=15: valid_sig)

    mgr = WebUpdateManager(exit_scheduler=lambda: None)
    data_dir = tmp_path / "data"
    state = mgr.start_download(data_dir=data_dir, blocking=True)
    job = state["job"]
    assert job["state"] == "ready_to_install"
    assert job["sha256_verified"] is True
    assert job["signature_verified"] is True
    verified = mgr.get_verified_download_path()
    assert verified.is_file()
    assert verified.read_bytes() == payload_bytes

    # 1) Fail-closed on corrupt Ed25519 signature -> state=failed and file removed
    bad_sig = bytearray(valid_sig)
    bad_sig[0] ^= 0xFF
    mgr.reset()
    monkeypatch.setattr(updater, "_download_signature", lambda url, timeout=15: bytes(bad_sig))
    failed_sig_state = mgr.start_download(data_dir=data_dir, blocking=True)
    assert failed_sig_state["job"]["state"] == "failed"
    assert failed_sig_state["job"]["signature_verified"] is False
    assert failed_sig_state["job"]["verified_path"] == ""
    assert not list((data_dir / "updates").glob("HydroWeb-*"))
    assert not list((data_dir / "updates").glob(".*part*"))
    with pytest.raises(UpdateError):
        mgr.get_verified_download_path()

    # 2) Fail-closed on missing .sig -> state=failed and file removed
    mgr.reset()
    monkeypatch.setattr(updater, "_download_signature", lambda url, timeout=15: None)
    missing_sig_state = mgr.start_download(data_dir=data_dir, blocking=True)
    assert missing_sig_state["job"]["state"] == "failed"
    assert missing_sig_state["job"]["signature_verified"] is False
    assert not list((data_dir / "updates").glob("HydroWeb-*"))

    # 3) Fail-closed on SHA-256 mismatch -> state=failed and file removed
    mgr.reset()
    monkeypatch.setattr(updater, "_download_signature", lambda url, timeout=15: valid_sig)
    monkeypatch.setattr(web_updater, "_download_checksum", lambda url, timeout=15: "0" * 64)
    bad_sha_state = mgr.start_download(data_dir=data_dir, blocking=True)
    assert bad_sha_state["job"]["state"] == "failed"
    assert bad_sha_state["job"]["sha256_verified"] is False
    assert not list((data_dir / "updates").glob("HydroWeb-*"))


def test_update_api_endpoints_status_check_download_and_apply(
    client, settings, isolated_manager: WebUpdateManager, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        web_updater, "_fetch_release_payload", lambda url, timeout=15: _sample_release("9.9.9")
    )

    r_status = client.get("/api/update/status")
    assert r_status.status_code == 200
    assert "current_version" in r_status.json()
    assert r_status.json()["job"]["state"] == "idle"

    # Non-frozen mode: /api/update/download/file returns 409 before download, /apply returns 409
    assert client.get("/api/update/download/file").status_code == 409
    r_apply_blocked = client.post("/api/update/apply")
    assert r_apply_blocked.status_code == 409
    assert r_apply_blocked.json()["code"] == "self_install_unavailable"

    r_chk = client.post("/api/update/check?force=true")
    assert r_chk.status_code == 200
    chk_body = r_chk.json()
    assert chk_body["update_available"] is True
    assert chk_body["latest_version"] == "9.9.9"

    # Perform verified blocking download then download via /api/update/download/file
    payload_bytes = b"VERIFIED-DMG-BYTES" * 16
    expected_sha = hashlib.sha256(payload_bytes).hexdigest()
    priv_key, pub_b64 = _new_keypair()
    valid_sig = priv_key.sign(payload_bytes)
    monkeypatch.setenv("HYDRO_UPDATE_PUBKEY", pub_b64)

    class _FakeDownloader:
        def download_file(self, url: str, dest_path: Path, on_progress=None, **_kwargs) -> Path:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(payload_bytes)
            return dest_path

    monkeypatch.setattr(web_updater, "DownloadManager", _FakeDownloader)
    monkeypatch.setattr(web_updater, "_download_checksum", lambda url, timeout=15: expected_sha)
    monkeypatch.setattr(updater, "_download_signature", lambda url, timeout=15: valid_sig)

    isolated_manager.start_download(
        data_dir=settings.data_dir,
        asset_name="HydroWeb-v9.9.9-macos-arm64.dmg",
        blocking=True,
    )
    r_file = client.get("/api/update/download/file")
    assert r_file.status_code == 200
    assert r_file.content == payload_bytes

    # Frozen macOS self-install via POST /api/update/apply invokes _install_macos_update and exit_scheduler
    exit_calls: list[bool] = []
    isolated_manager._exit_scheduler = lambda: exit_calls.append(True)
    install_calls: list[dict[str, Any]] = []

    def _fake_install_macos(
        dmg_path: Path, *, app_name: str, version: str, apps_dir: Path, log_path: Path
    ) -> None:
        install_calls.append(
            {
                "dmg": dmg_path.name,
                "app_name": app_name,
                "version": version,
                "apps_dir": str(apps_dir),
            }
        )

    fake_ctx = {
        "frozen": True,
        "platform": "darwin",
        "arch": "arm64",
        "install_mode": "macos_dmg",
        "can_self_install": True,
        "executable_path": "/Applications/HydroWeb.app/Contents/MacOS/HydroWeb",
        "install_dir": "/Applications",
        "app_bundle": "/Applications/HydroWeb.app",
        "prefer_kind": "macos_arm64_dmg",
    }
    monkeypatch.setattr(system_api, "get_web_runtime_context", lambda: fake_ctx)
    monkeypatch.setattr(web_updater, "get_web_runtime_context", lambda: fake_ctx)
    monkeypatch.setattr(web_updater, "_install_macos_update", _fake_install_macos)

    r_apply_ok = client.post("/api/update/apply")
    assert r_apply_ok.status_code == 200, r_apply_ok.text
    apply_body = r_apply_ok.json()
    assert apply_body["job"]["state"] == "restarting"
    assert len(install_calls) == 1
    assert install_calls[0]["app_name"] == "HydroWeb"
    assert install_calls[0]["version"] == "9.9.9"
    assert exit_calls == [True]

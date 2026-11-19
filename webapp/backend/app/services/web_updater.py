"""Signed GitHub Release Update Manager for HYDRO Web."""

from __future__ import annotations

import hashlib
import logging
import os
import platform as py_platform
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from hidrostatik_test.app_metadata import (
    APP_VERSION,
    GITHUB_OWNER,
    RELEASES_PAGE_URL,
)
from hidrostatik_test.services.download_manager import DownloadManager
from hidrostatik_test.services.updater import (
    DEFAULT_TIMEOUT_SECONDS,
    MAX_COMPRESSION_RATIO,
    MAX_EXTRACTED_BYTES,
    MAX_EXTRACTED_FILES,
    UPDATE_LOG_NAME,
    UpdateError,
    _append_update_log,
    _asset_name_mentions_version,
    _download_checksum,
    _ensure_pe_executable,
    _fetch_release_payload,
    _install_macos_update,
    _is_zip_symlink,
    _normalized_member_name,
    _powershell_literal,
    _release_source_repositories,
    _releases_api_url,
    _releases_page_url,
    _safe_path_component,
    _verify_sha256,
    _version_from_tag,
    _version_key,
    verify_asset_signature,
)

logger = logging.getLogger("hydro.web.updater")

WEB_BINARY_NAME = "HydroWeb"
WEB_MACOS_DMG_ARM64_TEMPLATE = f"{WEB_BINARY_NAME}-v{{version}}-macos-arm64.dmg"
WEB_MACOS_DMG_UNIV_TEMPLATE = f"{WEB_BINARY_NAME}-v{{version}}-macos-universal.dmg"
WEB_WINDOWS_SETUP_TEMPLATE = f"{WEB_BINARY_NAME}-v{{version}}-windows-x64-setup.exe"
WEB_WINDOWS_PORTABLE_TEMPLATE = f"{WEB_BINARY_NAME}-v{{version}}-windows-x64-portable.zip"
CHECK_CACHE_TTL_SECONDS = 600.0


@dataclass(frozen=True)
class WebReleaseAsset:
    name: str
    download_url: str
    size: int
    kind: str


@dataclass
class UpdateJobState:
    state: str = "idle"  # idle|checking|available|up_to_date|downloading|verifying|ready_to_install|installing|restarting|failed
    target_version: str = ""
    asset_name: str = ""
    download_url: str = ""
    downloaded_bytes: int = 0
    total_bytes: int = 0
    progress_pct: float = 0.0
    sha256_verified: bool = False
    signature_verified: bool = False
    verified_path: str = ""
    verified_sha256: str = ""
    error: str = ""
    message: str = ""
    updated_at: str = ""


@dataclass
class CachedUpdateCheck:
    checked_at_mono: float = 0.0
    checked_at_iso: str = ""
    current_version: str = APP_VERSION
    latest_version: str = ""
    tag_name: str = ""
    html_url: str = RELEASES_PAGE_URL
    body: str = ""
    published_at: str = ""
    source_repository: str = ""
    update_available: bool = False
    selected_asset: WebReleaseAsset | None = None
    all_assets: list[WebReleaseAsset] = field(default_factory=list)
    error: str = ""


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_web_runtime_context() -> dict[str, Any]:
    """Describe runtime packaging capabilities for self-update vs verified download."""
    frozen = bool(getattr(sys, "frozen", False))
    executable_path = Path(sys.executable if frozen else __file__).resolve()
    plat = sys.platform
    arch = py_platform.machine().lower() or "unknown"

    if frozen and plat.startswith("darwin"):
        # .../HydroWeb.app/Contents/MacOS/HydroWeb
        app_bundle = (
            executable_path.parents[2]
            if len(executable_path.parents) >= 3
            else executable_path.parent
        )
        apps_dir = app_bundle.parent if app_bundle.suffix == ".app" else Path("/Applications")
        can_self_install = app_bundle.suffix == ".app" and os.access(apps_dir, os.W_OK)
        return {
            "frozen": True,
            "platform": plat,
            "arch": arch,
            "install_mode": "macos_dmg" if can_self_install else "download_only",
            "can_self_install": can_self_install,
            "executable_path": str(executable_path),
            "install_dir": str(apps_dir),
            "app_bundle": str(app_bundle),
            "prefer_kind": "macos_arm64_dmg",
        }

    if frozen and plat.startswith("win"):
        install_dir = executable_path.parent
        is_inno_setup = (install_dir / "unins000.exe").is_file()
        is_portable_onedir = (install_dir / "_internal").is_dir()
        can_self_install = (
            executable_path.suffix.lower() == ".exe"
            and os.access(install_dir, os.W_OK)
            and (is_inno_setup or is_portable_onedir)
        )
        mode = (
            "windows_setup"
            if is_inno_setup
            else ("windows_portable" if is_portable_onedir else "download_only")
        )
        return {
            "frozen": True,
            "platform": plat,
            "arch": arch,
            "install_mode": mode if can_self_install else "download_only",
            "can_self_install": can_self_install,
            "executable_path": str(executable_path),
            "install_dir": str(install_dir),
            "is_inno_setup": is_inno_setup,
            "prefer_kind": "windows_setup_exe" if is_inno_setup else "windows_portable_zip",
        }

    prefer_kind = (
        "macos_arm64_dmg"
        if plat.startswith("darwin")
        else ("windows_setup_exe" if plat.startswith("win") else "windows_setup_exe")
    )
    return {
        "frozen": frozen,
        "platform": plat,
        "arch": arch,
        "install_mode": "download_only",
        "can_self_install": False,
        "executable_path": str(executable_path),
        "install_dir": str(executable_path.parent),
        "prefer_kind": prefer_kind,
    }


def _classify_web_asset_kind(name: str) -> str:
    lowered = name.lower()
    if lowered.endswith("-macos-arm64.dmg"):
        return "macos_arm64_dmg"
    if lowered.endswith("-macos-universal.dmg") or lowered.endswith(".dmg"):
        return "macos_universal_dmg"
    if lowered.endswith("-windows-x64-setup.exe") or (
        "setup" in lowered and lowered.endswith(".exe")
    ):
        return "windows_setup_exe"
    if lowered.endswith("-windows-x64-portable.zip") or (
        "portable" in lowered and lowered.endswith(".zip")
    ):
        return "windows_portable_zip"
    return "other"


def _matches_web_release(release: dict[str, Any]) -> bool:
    for asset in release.get("assets", []):
        name = str(asset.get("name", ""))
        lowered = name.lower()
        if not lowered.startswith(f"{WEB_BINARY_NAME.lower()}-"):
            continue
        if lowered.endswith((".dmg", ".exe", ".zip")):
            return True
    return False


def _select_latest_web_release(releases: list[dict[str, Any]], repo_name: str) -> dict[str, Any]:
    matching = [
        rel
        for rel in releases
        if not rel.get("draft") and not rel.get("prerelease") and _matches_web_release(rel)
    ]
    if not matching:
        raise UpdateError(f"{GITHUB_OWNER}/{repo_name} icinde {WEB_BINARY_NAME} surumu bulunamadi.")
    matching.sort(
        key=lambda rel: _version_key(_version_from_tag(str(rel.get("tag_name", "")))),
        reverse=True,
    )
    return matching[0]


def _extract_web_assets(
    release: dict[str, Any],
    version: str,
    *,
    platform_key: str | None = None,
    prefer_kind: str | None = None,
) -> tuple[WebReleaseAsset | None, list[WebReleaseAsset]]:
    current_platform = platform_key or sys.platform
    all_assets: list[WebReleaseAsset] = []
    for raw in release.get("assets", []):
        name = str(raw.get("name", ""))
        lowered = name.lower()
        if not lowered.startswith(f"{WEB_BINARY_NAME.lower()}-"):
            continue
        if not lowered.endswith((".dmg", ".exe", ".zip")):
            continue
        if lowered.endswith((".sha256.txt", ".sig", ".minisig")):
            continue
        if version and not _asset_name_mentions_version(name, version):
            continue
        all_assets.append(
            WebReleaseAsset(
                name=name,
                download_url=str(raw.get("browser_download_url", "")),
                size=int(raw.get("size", 0) or 0),
                kind=_classify_web_asset_kind(name),
            )
        )

    if not all_assets:
        return None, []

    if prefer_kind:
        for item in all_assets:
            if item.kind == prefer_kind:
                return item, all_assets

    if current_platform.startswith("darwin"):
        order = ("macos_arm64_dmg", "macos_universal_dmg", "windows_setup_exe")
    elif current_platform.startswith("win"):
        order = ("windows_setup_exe", "windows_portable_zip", "macos_arm64_dmg")
    else:
        order = ("windows_setup_exe", "macos_arm64_dmg", "windows_portable_zip")

    for kind in order:
        for item in all_assets:
            if item.kind == kind:
                return item, all_assets
    return all_assets[0], all_assets


def _compute_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest().lower()


def _safe_extract_web_zip(archive_path: Path, extract_root: Path) -> Path:
    """Safely extract portable HydroWeb zip and validate HydroWeb/HydroWeb.exe structure."""
    extract_root.mkdir(parents=True, exist_ok=True)
    try:
        archive = zipfile.ZipFile(archive_path, "r")
    except zipfile.BadZipFile as exc:
        raise UpdateError("Indirilen portable zip arsivi bozuk.") from exc

    with archive:
        members = archive.infolist()
        if not members:
            raise UpdateError("Indirilen guncelleme paketi bos.")
        if len(members) > MAX_EXTRACTED_FILES:
            raise UpdateError(
                f"Guncelleme paketi cok fazla dosya iceriyor ({len(members)} > {MAX_EXTRACTED_FILES})."
            )
        written_total = 0
        for info in members:
            normalized = _normalized_member_name(info.filename)
            if normalized is None:
                raise UpdateError(f"Guvenli olmayan arsiv yolu: {info.filename!r}")
            target_path = extract_root / normalized
            try:
                target_path.resolve().relative_to(extract_root.resolve())
            except ValueError as exc:
                raise UpdateError(f"Hedef klasor disina cikma girisimi: {info.filename!r}") from exc
            if info.is_dir() or normalized.endswith("/"):
                target_path.mkdir(parents=True, exist_ok=True)
                continue
            if _is_zip_symlink(info):
                raise UpdateError(f"Sembolik baglanti reddedildi: {info.filename!r}")
            if info.compress_size > 0 and (
                info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
            ):
                raise UpdateError(f"Supheli sikistirma orani: {info.filename!r}")
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, target_path.open("wb") as dst:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    written_total += len(chunk)
                    if written_total > MAX_EXTRACTED_BYTES:
                        raise UpdateError("Arsiv acilmis boyut siniri asildi.")
                    dst.write(chunk)

    app_dir = extract_root / WEB_BINARY_NAME
    exe_file = app_dir / f"{WEB_BINARY_NAME}.exe"
    if not exe_file.is_file():
        candidates = list(extract_root.rglob(f"{WEB_BINARY_NAME}.exe"))
        if not candidates:
            raise UpdateError(
                f"Portable arsivde {WEB_BINARY_NAME}/{WEB_BINARY_NAME}.exe bulunamadi."
            )
        app_dir = candidates[0].parent
    return app_dir


def _write_windows_setup_script(
    working_root: Path,
    setup_exe: Path,
    executable_path: Path,
    current_pid: int,
    log_path: Path,
) -> Path:
    script_path = working_root / "apply_web_setup.ps1"
    script = "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            f"$AppPid = {current_pid}",
            f"$SetupExe = '{_powershell_literal(str(setup_exe))}'",
            f"$ExePath = '{_powershell_literal(str(executable_path))}'",
            f"$LogPath = '{_powershell_literal(str(log_path))}'",
            "function Write-UpdateLog([string]$Message) {",
            "    $line = ('{0} {1}' -f (Get-Date).ToString('s'), $Message)",
            "    Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8",
            "}",
            "Write-UpdateLog 'HYDRO Web Inno Setup guncellemesi bekliyor.'",
            "$deadline = (Get-Date).AddSeconds(90)",
            "while ((Get-Process -Id $AppPid -ErrorAction SilentlyContinue) -and ((Get-Date) -lt $deadline)) {",
            "    Start-Sleep -Seconds 1",
            "}",
            "Write-UpdateLog 'Kurulum baslatiliyor (/SILENT).'",
            "$proc = Start-Process -FilePath $SetupExe -ArgumentList @('/SILENT', '/CLOSEAPPLICATIONS', '/NORESTART') -Wait -PassThru",
            "Write-UpdateLog ('Kurulum cikis kodu: ' + $proc.ExitCode)",
            "if ($proc.ExitCode -ne 0) { throw ('Kurulum basarisiz oldu: ' + $proc.ExitCode) }",
            "if (Test-Path -LiteralPath $ExePath) {",
            "    Start-Process -FilePath $ExePath",
            "    Write-UpdateLog 'HYDRO Web yeniden baslatildi.'",
            "}",
        ]
    )
    script_path.write_text(script, encoding="utf-8-sig", newline="\r\n")
    return script_path


def _write_windows_portable_script(
    working_root: Path,
    source_app_dir: Path,
    install_dir: Path,
    executable_path: Path,
    current_pid: int,
    version: str,
    log_path: Path,
) -> Path:
    script_path = working_root / "apply_web_portable.ps1"
    safe_ver = _safe_path_component(version or "previous")
    backup_dir = install_dir.with_name(f"{install_dir.name}-backup-{safe_ver}")
    new_dir = install_dir.with_name(f"{install_dir.name}-new-{current_pid}")
    script = "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            f"$AppPid = {current_pid}",
            f"$SourceDir = '{_powershell_literal(str(source_app_dir))}'",
            f"$TargetDir = '{_powershell_literal(str(install_dir))}'",
            f"$ExePath = '{_powershell_literal(str(executable_path))}'",
            f"$BackupDir = '{_powershell_literal(str(backup_dir))}'",
            f"$NewDir = '{_powershell_literal(str(new_dir))}'",
            f"$LogPath = '{_powershell_literal(str(log_path))}'",
            "function Write-UpdateLog([string]$Message) {",
            "    $line = ('{0} {1}' -f (Get-Date).ToString('s'), $Message)",
            "    Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8",
            "}",
            f"Write-UpdateLog 'Portable guncelleme basladi ({_powershell_literal(safe_ver)}).'",
            "$deadline = (Get-Date).AddSeconds(90)",
            "while ((Get-Process -Id $AppPid -ErrorAction SilentlyContinue) -and ((Get-Date) -lt $deadline)) {",
            "    Start-Sleep -Seconds 1",
            "}",
            "$swapped = $false",
            "try {",
            "    if (Test-Path -LiteralPath $BackupDir) { Remove-Item -LiteralPath $BackupDir -Recurse -Force }",
            "    if (Test-Path -LiteralPath $TargetDir) { Copy-Item -LiteralPath $TargetDir -Destination $BackupDir -Recurse -Force }",
            "    if (Test-Path -LiteralPath $NewDir) { Remove-Item -LiteralPath $NewDir -Recurse -Force }",
            "    New-Item -ItemType Directory -Path $NewDir -Force | Out-Null",
            "    Get-ChildItem -LiteralPath $SourceDir -Force | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $NewDir -Recurse -Force }",
            "    if (Test-Path -LiteralPath $TargetDir) { Remove-Item -LiteralPath $TargetDir -Recurse -Force }",
            "    Move-Item -LiteralPath $NewDir -Destination $TargetDir -Force",
            "    $swapped = $true",
            "    Write-UpdateLog 'Yeni portable surum yerlestirildi.'",
            "} catch {",
            "    Write-UpdateLog ('HATA: ' + $_.Exception.Message)",
            "    if (-not $swapped) {",
            "        if (Test-Path -LiteralPath $TargetDir) { Remove-Item -LiteralPath $TargetDir -Recurse -Force }",
            "        if (Test-Path -LiteralPath $BackupDir) { Move-Item -LiteralPath $BackupDir -Destination $TargetDir -Force }",
            "    }",
            "    throw",
            "}",
            "Start-Process -FilePath $ExePath",
        ]
    )
    script_path.write_text(script, encoding="utf-8-sig", newline="\r\n")
    return script_path


def _default_schedule_exit() -> None:
    def _terminate() -> None:
        try:
            os.kill(os.getpid(), signal.SIGTERM)
        except Exception:  # pragma: no cover
            os._exit(0)

    timer = threading.Timer(0.8, _terminate)
    timer.daemon = True
    timer.start()


class WebUpdateManager:
    """Thread-safe release checker, verifier, downloader, and installer for HYDRO Web."""

    def __init__(self, *, exit_scheduler: Callable[[], None] | None = None) -> None:
        self._lock = threading.RLock()
        self._cached: CachedUpdateCheck | None = None
        self._job = UpdateJobState()
        self._download_thread: threading.Thread | None = None
        self._exit_scheduler = exit_scheduler or _default_schedule_exit

    def reset(self) -> None:
        with self._lock:
            self._cached = None
            self._job = UpdateJobState()
            self._download_thread = None

    def _serialize_status_unlocked(self) -> dict[str, Any]:
        runtime = get_web_runtime_context()
        chk = self._cached
        job = self._job
        selected = asdict(chk.selected_asset) if (chk and chk.selected_asset) else None
        all_assets = [asdict(a) for a in (chk.all_assets if chk else [])]
        return {
            "current_version": APP_VERSION,
            "runtime": runtime,
            "checked": chk is not None,
            "checked_at": chk.checked_at_iso if chk else None,
            "latest_version": chk.latest_version if chk else None,
            "tag_name": chk.tag_name if chk else None,
            "html_url": chk.html_url if chk else RELEASES_PAGE_URL,
            "release_notes": chk.body if chk else "",
            "published_at": chk.published_at if chk else "",
            "source_repository": chk.source_repository if chk else "",
            "update_available": bool(chk.update_available) if chk else False,
            "check_error": chk.error if chk else "",
            "selected_asset": selected,
            "all_assets": all_assets,
            "job": asdict(job),
        }

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return self._serialize_status_unlocked()

    def check_for_updates(
        self,
        *,
        force: bool = False,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        with self._lock:
            if (
                not force
                and self._cached is not None
                and not self._cached.error
                and (time.monotonic() - self._cached.checked_at_mono) < CHECK_CACHE_TTL_SECONDS
            ):
                return self._serialize_status_unlocked()
            prev_job_state = self._job.state
            if prev_job_state in {"idle", "available", "up_to_date", "failed"}:
                self._job = UpdateJobState(state="checking", updated_at=_utc_iso())

        runtime = get_web_runtime_context()
        prefer_kind = str(runtime.get("prefer_kind") or "")
        platform_key = str(runtime.get("platform") or sys.platform)

        candidates: list[tuple[tuple[int, ...], int, CachedUpdateCheck]] = []
        errors: list[str] = []
        for priority, repo_name in enumerate(_release_source_repositories()):
            try:
                payload = _fetch_release_payload(_releases_api_url(repo_name), timeout_seconds)
                release = _select_latest_web_release(payload, repo_name)
            except UpdateError as exc:
                errors.append(f"{repo_name}: {exc}")
                continue
            latest_ver = _version_from_tag(str(release.get("tag_name", "")))
            selected_asset, all_assets = _extract_web_assets(
                release,
                latest_ver,
                platform_key=platform_key,
                prefer_kind=prefer_kind,
            )
            upd_avail = _version_key(latest_ver) > _version_key(APP_VERSION)
            candidates.append(
                (
                    _version_key(latest_ver),
                    priority,
                    CachedUpdateCheck(
                        checked_at_mono=time.monotonic(),
                        checked_at_iso=_utc_iso(),
                        current_version=APP_VERSION,
                        latest_version=latest_ver,
                        tag_name=str(release.get("tag_name", "")),
                        html_url=str(release.get("html_url", _releases_page_url(repo_name))),
                        body=str(release.get("body", "")),
                        published_at=str(release.get("published_at", "")),
                        source_repository=f"{GITHUB_OWNER}/{repo_name}",
                        update_available=upd_avail,
                        selected_asset=selected_asset,
                        all_assets=all_assets,
                        error="",
                    ),
                )
            )

        with self._lock:
            if not candidates:
                msg = " | ".join(errors) if errors else "GitHub release kaynaklarina ulasilamadi."
                self._cached = CachedUpdateCheck(
                    checked_at_mono=time.monotonic(),
                    checked_at_iso=_utc_iso(),
                    error=msg,
                )
                if self._job.state == "checking":
                    self._job = UpdateJobState(
                        state="failed",
                        error=msg,
                        message="Guncelleme sunucusuna erisilemedi.",
                        updated_at=_utc_iso(),
                    )
                return self._serialize_status_unlocked()

            candidates.sort(key=lambda item: (item[0], -item[1]), reverse=True)
            best = candidates[0][2]
            self._cached = best
            if self._job.state in {"checking", "idle", "available", "up_to_date", "failed"}:
                self._job = UpdateJobState(
                    state="available" if best.update_available else "up_to_date",
                    target_version=best.latest_version,
                    asset_name=best.selected_asset.name if best.selected_asset else "",
                    download_url=best.selected_asset.download_url if best.selected_asset else "",
                    total_bytes=best.selected_asset.size if best.selected_asset else 0,
                    message=(
                        f"Yeni surum v{best.latest_version} hazir."
                        if best.update_available
                        else f"Uygulama guncel (v{APP_VERSION})."
                    ),
                    updated_at=_utc_iso(),
                )
            return self._serialize_status_unlocked()

    def _resolve_asset_for_download(self, asset_name: str | None) -> tuple[str, WebReleaseAsset]:
        with self._lock:
            chk = self._cached
        if chk is None or chk.error:
            self.check_for_updates(force=True)
            with self._lock:
                chk = self._cached
        if chk is None or chk.error:
            raise UpdateError((chk.error if chk else "") or "Release bilgisi alinamadi.")
        if asset_name:
            for item in chk.all_assets:
                if item.name == asset_name:
                    return chk.latest_version, item
            raise UpdateError(f"Secilen kurulum paketi release icinde bulunamadi: {asset_name}")
        if chk.selected_asset is None:
            raise UpdateError("Bu platform icin uygun HydroWeb kurulum paketi bulunamadi.")
        return chk.latest_version, chk.selected_asset

    def start_download(
        self,
        *,
        data_dir: Path,
        asset_name: str | None = None,
        timeout_seconds: int = 30,
        blocking: bool = False,
    ) -> dict[str, Any]:
        target_version, asset = self._resolve_asset_for_download(asset_name)
        updates_dir = data_dir / "updates"
        updates_dir.mkdir(parents=True, exist_ok=True)
        dest_path = updates_dir / asset.name

        existing_thread: threading.Thread | None = None
        with self._lock:
            if self._job.state in {"installing", "restarting"}:
                raise UpdateError("Kurulum devam ederken yeni indirme baslatilamaz.")

            if (
                self._job.state in {"downloading", "verifying"}
                and self._download_thread is not None
                and self._download_thread.is_alive()
            ):
                if not blocking:
                    return self._serialize_status_unlocked()
                existing_thread = self._download_thread

        if existing_thread is not None:
            existing_thread.join(timeout=max(timeout_seconds * 4, 120))
            return self.get_status()

        with self._lock:
            if (
                self._job.state == "ready_to_install"
                and self._job.asset_name == asset.name
                and self._job.target_version == target_version
                and self._job.verified_path
                and Path(self._job.verified_path).is_file()
                and _compute_file_sha256(Path(self._job.verified_path)) == self._job.verified_sha256
            ):
                return self._serialize_status_unlocked()

            self._job = UpdateJobState(
                state="downloading",
                target_version=target_version,
                asset_name=asset.name,
                download_url=asset.download_url,
                downloaded_bytes=0,
                total_bytes=asset.size,
                progress_pct=0.0,
                message=f"{asset.name} indiriliyor...",
                updated_at=_utc_iso(),
            )

        def _worker() -> None:
            tmp_path = updates_dir / f".{asset.name}.part"
            try:
                tmp_path.unlink(missing_ok=True)

                def _on_progress(
                    destination: Path, downloaded: int, total: int, speed: float, eta: float
                ) -> None:
                    del destination, speed, eta
                    eff_total = total if total > 0 else asset.size
                    pct = round((downloaded / eff_total) * 100.0, 1) if eff_total > 0 else 0.0
                    with self._lock:
                        self._job.downloaded_bytes = int(downloaded)
                        self._job.total_bytes = int(eff_total)
                        self._job.progress_pct = min(100.0, pct)
                        self._job.updated_at = _utc_iso()

                dm = DownloadManager()
                dm.download_file(asset.download_url, tmp_path, on_progress=_on_progress)

                with self._lock:
                    self._job.state = "verifying"
                    self._job.progress_pct = 100.0
                    self._job.message = "SHA-256 ve Ed25519 dijital imzasi dogrulaniyor..."
                    self._job.updated_at = _utc_iso()

                expected_sha = _download_checksum(asset.download_url, timeout_seconds)
                _verify_sha256(tmp_path, expected_sha)
                sig_ok = verify_asset_signature(tmp_path, asset.download_url, timeout_seconds)

                dest_path.unlink(missing_ok=True)
                shutil.move(str(tmp_path), str(dest_path))

                with self._lock:
                    self._job.state = "ready_to_install"
                    self._job.sha256_verified = True
                    self._job.signature_verified = bool(sig_ok)
                    self._job.verified_path = str(dest_path)
                    self._job.verified_sha256 = expected_sha.lower()
                    self._job.downloaded_bytes = dest_path.stat().st_size
                    self._job.total_bytes = dest_path.stat().st_size
                    self._job.progress_pct = 100.0
                    self._job.error = ""
                    self._job.message = (
                        f"{asset.name} indirildi ve SHA-256 + Ed25519 imza dogrulamasi basarili."
                    )
                    self._job.updated_at = _utc_iso()
            except Exception as exc:
                tmp_path.unlink(missing_ok=True)
                dest_path.unlink(missing_ok=True)
                logger.warning("HydroWeb guncelleme indirme/dogrulama hatasi: %s", exc)
                with self._lock:
                    self._job.state = "failed"
                    self._job.sha256_verified = False
                    self._job.signature_verified = False
                    self._job.verified_path = ""
                    self._job.verified_sha256 = ""
                    self._job.error = str(exc)
                    self._job.message = f"Dogrulama / indirme basarisiz: {exc}"
                    self._job.updated_at = _utc_iso()

        if blocking:
            _worker()
        else:
            thread = threading.Thread(target=_worker, name="hydro-web-update-dl", daemon=True)
            with self._lock:
                self._download_thread = thread
            thread.start()

        return self.get_status()

    def get_verified_download_path(self) -> Path:
        with self._lock:
            state = self._job.state
            v_path = Path(self._job.verified_path) if self._job.verified_path else None
            v_sha = self._job.verified_sha256
        if state not in {"ready_to_install", "installing", "restarting"} or v_path is None:
            raise UpdateError("Henuz dogrulanmis bir guncelleme paketi indirilmedi.")
        if not v_path.is_file():
            raise UpdateError("Dogrulanmis guncelleme paketi diskte bulunamadi; tekrar indirin.")
        actual_sha = _compute_file_sha256(v_path)
        if not v_sha or actual_sha != v_sha.lower():
            raise UpdateError(
                "Diskteki guncelleme paketinin SHA-256 ozeti degismis; indirme iptal."
            )
        return v_path

    def apply_update(self, *, data_dir: Path) -> dict[str, Any]:
        runtime = get_web_runtime_context()
        if not runtime["can_self_install"]:
            raise UpdateError(
                "Bu calisma kipinde otomatik yerinde kurulum desteklenmiyor; dogrulanmis kurulum dosyasini indirip calistirin."
            )

        with self._lock:
            if self._job.state in {"installing", "restarting"}:
                raise UpdateError("Guncelleme kurulumu zaten devam ediyor.")
            ready = (
                self._job.state == "ready_to_install"
                and self._job.verified_path
                and Path(self._job.verified_path).is_file()
            )
        if not ready:
            self.start_download(data_dir=data_dir, blocking=True)

        verified_path = self.get_verified_download_path()

        with self._lock:
            target_version = self._job.target_version or (
                self._cached.latest_version if self._cached else APP_VERSION
            )
            self._job.state = "installing"
            self._job.message = f"v{target_version} kuruluyor ve uygulama yeniden baslatiliyor..."
            self._job.updated_at = _utc_iso()

        updates_dir = data_dir / "updates"
        updates_dir.mkdir(parents=True, exist_ok=True)
        log_path = updates_dir / UPDATE_LOG_NAME
        _append_update_log(log_path, f"HydroWeb guncellemesi uygulanacak: {verified_path.name}")

        plat = str(runtime["platform"])
        if verified_path.suffix.lower() == ".dmg" and plat.startswith("darwin"):
            apps_dir = Path(str(runtime["install_dir"]))
            _install_macos_update(
                verified_path,
                app_name=WEB_BINARY_NAME,
                version=target_version,
                apps_dir=apps_dir,
                log_path=log_path,
            )
            with self._lock:
                self._job.state = "restarting"
                self._job.message = (
                    f"HydroWeb v{target_version} kuruldu. Uygulama yeniden baslatiliyor..."
                )
                self._job.updated_at = _utc_iso()
            self._exit_scheduler()
            return self.get_status()

        if plat.startswith("win"):
            executable_path = Path(str(runtime["executable_path"]))
            install_dir = Path(str(runtime["install_dir"]))
            working_root = Path(tempfile.mkdtemp(prefix="hydroweb-update-", dir=str(updates_dir)))

            if verified_path.suffix.lower() == ".exe":
                _ensure_pe_executable(verified_path)
                script_path = _write_windows_setup_script(
                    working_root=working_root,
                    setup_exe=verified_path,
                    executable_path=executable_path,
                    current_pid=os.getpid(),
                    log_path=log_path,
                )
            elif verified_path.suffix.lower() == ".zip":
                if not (install_dir / "_internal").is_dir():
                    raise UpdateError(
                        "Portable dizin yapisi (_internal) bulunamadigi icin otomatik klasor "
                        "degisimi guvenlik nedeniyle durduruldu."
                    )
                extracted_dir = _safe_extract_web_zip(verified_path, working_root / "extract")
                script_path = _write_windows_portable_script(
                    working_root=working_root,
                    source_app_dir=extracted_dir,
                    install_dir=install_dir,
                    executable_path=executable_path,
                    current_pid=os.getpid(),
                    version=target_version,
                    log_path=log_path,
                )
            else:
                raise UpdateError(f"Desteklenmeyen Windows paket uzantisi: {verified_path.name}")

            subprocess.Popen(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-WindowStyle",
                    "Hidden",
                    "-File",
                    str(script_path),
                ],
                close_fds=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            with self._lock:
                self._job.state = "restarting"
                self._job.message = (
                    f"HydroWeb v{target_version} kurulumu baslatildi. Yeniden baslatiliyor..."
                )
                self._job.updated_at = _utc_iso()
            self._exit_scheduler()
            return self.get_status()

        raise UpdateError(
            f"Otomatik kurulum bu paket/platform kombinasyonu icin desteklenmiyor: {verified_path.name}"
        )


WEB_UPDATE_MANAGER = WebUpdateManager()

__all__ = [
    "WEB_BINARY_NAME",
    "WEB_UPDATE_MANAGER",
    "WebReleaseAsset",
    "WebUpdateManager",
    "get_web_runtime_context",
]

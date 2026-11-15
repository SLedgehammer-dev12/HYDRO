from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import webbrowser
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..app_metadata import (
    APP_VERSION,
    BINARY_NAME,
    GITHUB_OWNER,
    GITHUB_REPO,
    LEGACY_GITHUB_REPOS,
    RELEASE_ASSET_TEMPLATE,
    RELEASE_ASSET_TEMPLATE_MACOS,
    RELEASE_TAG_PREFIX,
    RELEASES_PAGE_URL,
    UPDATE_SIGNING_PUBLIC_KEY,
)
from .download_manager import DownloadManager, ProgressCallback

DEFAULT_TIMEOUT_SECONDS = 10
POWERSHELL_JSON_DEPTH = 32

# Windows icin iki artefakt bicimi yayinlanabilir: arsiv (.zip) veya tek dosya
# calistirilabilir (.exe). MacOS yalnizca .dmg kullanir.
WINDOWS_EXE_TEMPLATE = f"{BINARY_NAME}-v{{version}}-windows-x64.exe"
WINDOWS_EXTENSIONS = (".zip", ".exe")
MACOS_EXTENSIONS = (".dmg",)
WINDOWS_SINGLE_EXE_NAME = f"{BINARY_NAME}.exe"

# Guvenli zip cikarma limitleri. Bir guncelleme paketi bunlari asarsa paket
# reddedilir (zip bomb / kaynak tuketimi korumasi).
MAX_EXTRACTED_BYTES = 512 * 1024 * 1024
MAX_EXTRACTED_FILES = 5000
MAX_COMPRESSION_RATIO = 200

SIGNATURE_ENV_PUBKEY = "HYDRO_UPDATE_PUBKEY"
SIGNATURE_ENV_REQUIRED = "HYDRO_REQUIRE_SIGNATURE"
SIGNATURE_ENV_ALLOW_UNSIGNED = "HYDRO_ALLOW_UNSIGNED_UPDATE"
# Guncelleme imzasi varsayilan olarak ZORUNLUDUR (fail-closed): gomulu public
# key (`app_metadata.UPDATE_SIGNING_PUBLIC_KEY`) veya `HYDRO_UPDATE_PUBKEY`
# varsa `.sig` dosyasi olmayan/gecersiz paket kurulmaz.
#
# Yalnizca gelistirici makinelerinde, acikca istenerek kapatilabilir:
#   HYDRO_ALLOW_UNSIGNED_UPDATE=1  veya  HYDRO_REQUIRE_SIGNATURE=0
# Bu iki bayrak yalnizca imza dosyasinin YOKLUGUNU tolere eder; imza varsa
# yine dogrulanir. Uretim dagitiminda kullanilmamalidir.
SIGNATURE_URL_SUFFIXES = (".sig", ".minisig")
SIGNATURE_ALGORITHM_MINISIGN = (b"Ed", b"ED")
_SIGNATURE_FALSE_VALUES = {"0", "false", "no", "off", "disabled"}
UPDATE_LOG_NAME = "apply_update.log"

MISSING_SIGNATURE_MESSAGE = (
    "Guncelleme imzasi (.sig) bulunamadi. Bu surum imzali olarak yayinlanmamis "
    "veya imza dosyasi release'e yuklenmemis olabilir. Guvenlik nedeniyle "
    "guncelleme iptal edildi. Lutfen {releases_url} adresinden paketi elle "
    "indirin veya yayin sorumlusundan imzali surum isteyin."
)
MISSING_PUBLIC_KEY_MESSAGE = (
    "Guncelleme imza anahtari tanimli degil (app_metadata.UPDATE_SIGNING_PUBLIC_KEY "
    "bos). Imza dogrulanamadigi icin guncelleme iptal edildi. Yonetici "
    "HYDRO_UPDATE_PUBKEY ortam degiskeniyle anahtari saglayabilir."
)
INVALID_SIGNATURE_MESSAGE = (
    "Guncelleme paketinin dijital imzasi gecersiz. Paket bozulmus veya "
    "degistirilmis olabilir. Guvenlik nedeniyle guncelleme iptal edildi. "
    "Lutfen {releases_url} adresinden yeniden indirin; sorun surerse yayin "
    "sorumlusuna bildirin."
)
MISSING_CRYPTOGRAPHY_MESSAGE = (
    "Imza dogrulamasi icin 'cryptography' paketi gerekli ancak bulunamadi. "
    "Guvenlik nedeniyle guncelleme iptal edildi. Paketi kurun "
    "(python -m pip install -r requirements.txt) ve tekrar deneyin."
)

logger = logging.getLogger(__name__)


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    download_url: str
    size: int


@dataclass(frozen=True)
class UpdateInfo:
    current_version: str
    latest_version: str
    tag_name: str
    html_url: str
    body: str
    published_at: str
    asset: ReleaseAsset | None
    update_available: bool
    source_repository: str


@dataclass(frozen=True)
class RuntimeContext:
    frozen: bool
    can_self_update: bool
    executable_path: Path
    install_dir: Path


def _version_key(version: str) -> tuple[int, ...]:
    parts = version.strip().split(".")
    numeric_parts: list[int] = []
    for part in parts:
        digits = "".join(ch for ch in part if ch.isdigit())
        numeric_parts.append(int(digits) if digits else 0)
    while len(numeric_parts) < 3:
        numeric_parts.append(0)
    return tuple(numeric_parts)


def _version_from_tag(tag_name: str) -> str:
    normalized = tag_name.strip()
    if normalized.startswith(RELEASE_TAG_PREFIX):
        return normalized[len(RELEASE_TAG_PREFIX) :]
    if normalized.startswith("v"):
        return normalized[1:]
    return normalized


def _matches_project_release(release: dict[str, Any]) -> bool:
    tag_name = str(release.get("tag_name", ""))
    if tag_name.startswith(RELEASE_TAG_PREFIX):
        return True
    asset_template_prefix = RELEASE_ASSET_TEMPLATE.split("{version}", 1)[0]
    exe_template_prefix = WINDOWS_EXE_TEMPLATE.split("{version}", 1)[0]
    macos_template_prefix = RELEASE_ASSET_TEMPLATE_MACOS.split("{version}", 1)[0]
    for asset in release.get("assets", []):
        asset_name = str(asset.get("name", ""))
        lowered = asset_name.lower()
        if asset_name.startswith(asset_template_prefix) and lowered.endswith(".zip"):
            return True
        if asset_name.startswith(exe_template_prefix) and lowered.endswith(".exe"):
            return True
        if asset_name.startswith(macos_template_prefix) and lowered.endswith(".dmg"):
            return True
    return False


def _platform_extensions(platform: str) -> tuple[str, ...]:
    if platform.startswith("darwin"):
        return MACOS_EXTENSIONS
    return WINDOWS_EXTENSIONS


def _expected_asset_names(version: str, platform: str) -> tuple[str, ...]:
    if platform.startswith("darwin"):
        return (RELEASE_ASSET_TEMPLATE_MACOS.format(version=version),)
    return (
        RELEASE_ASSET_TEMPLATE.format(version=version),
        WINDOWS_EXE_TEMPLATE.format(version=version),
    )


def _asset_name_mentions_version(asset_name: str, version: str) -> bool:
    """Asset adinda istenen surumun tam bir surum belirteci olarak gecmesini arar.

    ``1.7.2`` aramasi ``1.7.20`` veya ``11.7.2`` icinde eslesmemelidir.
    """
    pattern = rf"(?<![\d.])v?{re.escape(version)}(?![\d.])"
    return re.search(pattern, asset_name, flags=re.IGNORECASE) is not None


def _extract_asset(
    release: dict[str, Any],
    version: str,
    platform: str | None = None,
) -> ReleaseAsset | None:
    """Release icinden bu platforma uygun artefakti secer.

    Sirasiyla:
    1. Platformun beklenen tam adi (ornegin ``...-windows-x64.zip``).
    2. Baska bir platformun beklenen tam adi (meta veri/raporlama icin).

    Cozumleyici (fallback) yalnizca dosya adinda istenen surum geciyorsa kabul
    edilir; boylece 1.7.2 aranirken 1.7.0 paketi kurulmaz.
    """
    current_platform = platform or sys.platform
    assets: list[ReleaseAsset] = []
    for asset in release.get("assets", []):
        assets.append(
            ReleaseAsset(
                name=str(asset.get("name", "")),
                download_url=str(asset.get("browser_download_url", "")),
                size=int(asset.get("size", 0) or 0),
            )
        )
    if not assets:
        return None

    expected_names = [name.casefold() for name in _expected_asset_names(version, current_platform)]
    for expected_name in expected_names:
        for asset in assets:
            if asset.name.casefold() == expected_name:
                return asset

    other_platform = "windows" if current_platform.startswith("darwin") else "darwin"
    other_names = [name.casefold() for name in _expected_asset_names(version, other_platform)]
    for expected_name in other_names:
        for asset in assets:
            if asset.name.casefold() == expected_name:
                return asset

    allowed_extensions = _platform_extensions(current_platform)
    for asset in assets:
        lowered = asset.name.lower()
        if not lowered.endswith(allowed_extensions):
            continue
        if _asset_name_mentions_version(asset.name, version):
            return asset
    return None


def _select_latest_release(releases: list[dict[str, Any]], repo_name: str) -> dict[str, Any]:
    matching_releases = [
        release
        for release in releases
        if not release.get("draft")
        and not release.get("prerelease")
        and _matches_project_release(release)
    ]
    if not matching_releases:
        raise UpdateError(f"{GITHUB_OWNER}/{repo_name} icinde bu uygulamaya ait yayin bulunamadi.")
    matching_releases.sort(
        key=lambda release: _version_key(_version_from_tag(str(release.get("tag_name", "")))),
        reverse=True,
    )
    return matching_releases[0]


def _build_headers(accept: str) -> dict[str, str]:
    return {
        "Accept": accept,
        "User-Agent": f"{BINARY_NAME}-updater/{APP_VERSION}",
    }


def _release_source_repositories() -> tuple[str, ...]:
    repositories = [GITHUB_REPO]
    repositories.extend(repo for repo in LEGACY_GITHUB_REPOS if repo != GITHUB_REPO)
    return tuple(repositories)


def _releases_api_url(repo_name: str) -> str:
    return f"https://api.github.com/repos/{GITHUB_OWNER}/{repo_name}/releases"


def _releases_page_url(repo_name: str) -> str:
    return f"https://github.com/{GITHUB_OWNER}/{repo_name}/releases"


def _powershell_literal(value: str) -> str:
    return value.replace("'", "''")


def _powershell_headers_block(headers: dict[str, str]) -> str:
    lines = ["$headers = @{}"]
    for key, value in headers.items():
        lines.append(f"$headers['{_powershell_literal(key)}'] = '{_powershell_literal(value)}'")
    return "\n".join(lines)


def _run_powershell(script: str, timeout_seconds: int) -> str:
    wrapped_script = "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            "$ProgressPreference = 'SilentlyContinue'",
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8",
            "$OutputEncoding = [System.Text.Encoding]::UTF8",
            script,
        ]
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", wrapped_script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise UpdateError("PowerShell bu sistemde bulunamadi.") from exc
    except subprocess.TimeoutExpired as exc:
        raise UpdateError("PowerShell ag cagrisi zaman asimina ugradi.") from exc
    except OSError as exc:
        raise UpdateError(f"PowerShell calistirilamadi: {exc}") from exc

    if completed.returncode != 0:
        message = (
            completed.stderr.strip()
            or completed.stdout.strip()
            or "PowerShell komutu basarisiz oldu."
        )
        raise UpdateError(message)
    return completed.stdout


def _load_json_via_powershell(url: str, headers: dict[str, str], timeout_seconds: int) -> Any:
    script = "\n".join(
        [
            _powershell_headers_block(headers),
            (
                f"$response = Invoke-RestMethod -Uri '{_powershell_literal(url)}' "
                f"-Headers $headers -TimeoutSec {timeout_seconds}"
            ),
            f"$response | ConvertTo-Json -Depth {POWERSHELL_JSON_DEPTH} -Compress",
        ]
    )
    raw_output = _run_powershell(script, timeout_seconds).strip()
    if not raw_output:
        raise UpdateError("PowerShell bos bir release cevabi dondurdu.")
    try:
        return json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise UpdateError("PowerShell release cevabi JSON olarak okunamadi.") from exc


def _download_via_powershell(
    url: str,
    headers: dict[str, str],
    target_path: Path,
    timeout_seconds: int,
) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    script = "\n".join(
        [
            _powershell_headers_block(headers),
            (
                f"Invoke-WebRequest -Uri '{_powershell_literal(url)}' "
                f"-Headers $headers -OutFile '{_powershell_literal(str(target_path))}' "
                f"-TimeoutSec {timeout_seconds}"
            ),
        ]
    )
    _run_powershell(script, timeout_seconds)
    if not target_path.exists() or target_path.stat().st_size <= 0:
        raise UpdateError("PowerShell indirmesi bos bir dosya olusturdu.")


def _fetch_release_payload(source_url: str, timeout_seconds: int) -> list[dict[str, Any]]:
    headers = _build_headers("application/vnd.github+json")
    request = Request(source_url, headers=headers)

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise UpdateError(f"GitHub release bilgisi okunamadi: HTTP {exc.code}") from exc
    except URLError:
        try:
            payload = _load_json_via_powershell(source_url, headers, timeout_seconds)
        except UpdateError as fallback_exc:
            raise UpdateError(
                "GitHub release servisine ulasilamadi. Python TLS dogrulamasi ve Windows fallback denemesi basarisiz oldu."
            ) from fallback_exc
    except json.JSONDecodeError as exc:
        raise UpdateError("GitHub release cevabi okunamadi.") from exc

    if not isinstance(payload, list):
        raise UpdateError("GitHub release cevabi beklenen list formatinda degil.")
    return payload


def fetch_latest_update_info(timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> UpdateInfo:
    candidates: list[tuple[tuple[int, ...], int, UpdateInfo]] = []
    source_errors: list[str] = []
    for priority, repo_name in enumerate(_release_source_repositories()):
        try:
            payload = _fetch_release_payload(_releases_api_url(repo_name), timeout_seconds)
            release = _select_latest_release(payload, repo_name)
        except UpdateError as exc:
            source_errors.append(f"{repo_name}: {exc}")
            continue

        latest_version = _version_from_tag(str(release.get("tag_name", "")))
        latest_asset = _extract_asset(release, latest_version)
        candidates.append(
            (
                _version_key(latest_version),
                priority,
                UpdateInfo(
                    current_version=APP_VERSION,
                    latest_version=latest_version,
                    tag_name=str(release.get("tag_name", "")),
                    html_url=str(release.get("html_url", _releases_page_url(repo_name))),
                    body=str(release.get("body", "")),
                    published_at=str(release.get("published_at", "")),
                    asset=latest_asset,
                    update_available=_version_key(latest_version) > _version_key(APP_VERSION),
                    source_repository=f"{GITHUB_OWNER}/{repo_name}",
                ),
            )
        )

    if not candidates:
        joined_errors = " | ".join(source_errors) if source_errors else "kaynak repo bulunamadi"
        raise UpdateError(f"Release kaynaklari okunamadi: {joined_errors}")

    candidates.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    return candidates[0][2]


def get_runtime_context() -> RuntimeContext:
    frozen = bool(getattr(sys, "frozen", False))
    executable_path = Path(sys.executable if frozen else __file__).resolve()
    install_dir = executable_path.parent if frozen else Path(__file__).resolve().parent
    if frozen and sys.platform.startswith("darwin"):
        install_dir = executable_path.parent.parent.parent.parent
    can_self_update = frozen and (
        (sys.platform.startswith("win") and executable_path.suffix.lower() == ".exe")
        or (sys.platform.startswith("darwin") and executable_path.suffix == "")
    )
    return RuntimeContext(
        frozen=frozen,
        can_self_update=can_self_update,
        executable_path=executable_path,
        install_dir=install_dir,
    )


def open_release_page(url: str | None = None) -> None:
    webbrowser.open(url or RELEASES_PAGE_URL)


# --- Checksum ---------------------------------------------------------------


def _checksum_url(asset_download_url: str) -> str:
    """Birincil checksum adresi: ``<asset_url>.sha256.txt``."""
    return f"{asset_download_url}.sha256.txt"


def _checksum_candidate_urls(asset_download_url: str) -> list[str]:
    """Yayinlanmis olabilecek checksum adlarini oncelik sirasiyla dondurur.

    Build zinciri checksum dosyasini ``<stem>.sha256.txt`` olarak yayinlar
    (ornegin ``HidrostatikTest-v1.7.3-windows-x64.sha256.txt``); eski
    artefaktlarda ise ``<asset_url>.sha256.txt`` bicimi bulunur. Her iki ad ve
    uzantisi tamamen cikarilmis varyant denenir.
    """
    candidates: list[str] = []

    def add(url: str) -> None:
        if url and url not in candidates:
            candidates.append(url)

    add(_checksum_url(asset_download_url))
    base_url = asset_download_url.split("?", 1)[0]
    directory, _, filename = base_url.rpartition("/")
    prefix = f"{directory}/" if directory else ""
    stem = filename
    for extension in (".exe", ".zip", ".dmg", ".tar.gz", ".tgz"):
        if stem.lower().endswith(extension):
            stem = stem[: -len(extension)]
            break
    add(f"{prefix}{stem}.sha256.txt")
    extensionless = stem
    while "." in extensionless:
        extensionless = extensionless.rsplit(".", 1)[0]
    if extensionless and extensionless != stem:
        add(f"{prefix}{extensionless}.sha256.txt")
    return candidates


def _download_checksum(
    asset_download_url: str,
    timeout_seconds: int,
) -> str:
    candidates = _checksum_candidate_urls(asset_download_url)
    last_not_found: HTTPError | None = None
    for checksum_url in candidates:
        request = Request(checksum_url, headers=_build_headers("text/plain"))
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                content = response.read().decode("utf-8").strip()
        except HTTPError as exc:
            if exc.code == 404:
                last_not_found = exc
                continue
            raise UpdateError(f"SHA-256 dosyasi indirilemedi: HTTP {exc.code}") from exc
        except URLError as exc:
            raise UpdateError(
                "SHA-256 dogrulama dosyasina ulasilamadi. Guvenlik riski nedeniyle guncelleme iptal edildi."
            ) from exc
        parts = content.replace("\t", " ").split()
        if not parts:
            raise UpdateError("SHA-256 dosyasi bos.")
        checksum = parts[0].lower()
        if re.fullmatch(r"[0-9a-f]{64}", checksum) is None:
            raise UpdateError("SHA-256 dogrulama dosyasi gecersiz formatta.")
        return checksum

    raise UpdateError(
        "SHA-256 dogrulama dosyasi GitHub release'de bulunamadi. Guvenlik riski nedeniyle guncelleme iptal edildi."
    ) from last_not_found


def _verify_sha256(file_path: Path, expected_hex: str) -> None:
    hash_sha256 = hashlib.sha256()
    with file_path.open("rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            hash_sha256.update(chunk)
    actual = hash_sha256.hexdigest().lower()
    if actual != expected_hex.lower():
        raise UpdateError(
            f"SHA-256 dogrulamasi basarisiz. Beklenen: {expected_hex.lower()}, Gerceklesen: {actual}."
        )


# --- Ed25519 signature enforcement ------------------------------------------


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _signing_required() -> bool:
    """Guncelleme imzasi zorunlu mu? Varsayilan: evet (fail-closed).

    Kaçış bayraklari yalnizca acikca verildiginde imza *yoklugunu* tolere eder:
    ``HYDRO_ALLOW_UNSIGNED_UPDATE=1`` veya ``HYDRO_REQUIRE_SIGNATURE=0``.
    """
    if _env_flag(SIGNATURE_ENV_ALLOW_UNSIGNED):
        return False
    explicit = os.environ.get(SIGNATURE_ENV_REQUIRED, "").strip().lower()
    if explicit in _SIGNATURE_FALSE_VALUES:
        return False
    return True


def _signing_public_key_material() -> str:
    """Ortam degiskeni override'i (rotasyon) once, gomulu anahtar sonra."""
    override = os.environ.get(SIGNATURE_ENV_PUBKEY, "").strip()
    if override:
        return override
    return str(UPDATE_SIGNING_PUBLIC_KEY or "").strip()


def _decode_public_key(material: str) -> bytes:
    """Public key degerini 32 baytlik Ed25519 anahtarina cevirir.

    Deger ya base64/hex kodlanmis anahtar ya da anahtari iceren bir dosya yolu
    olabilir.
    """
    candidate_path = Path(material)
    try:
        if candidate_path.is_file():
            material = candidate_path.read_text(encoding="utf-8").strip()
    except OSError:
        pass
    compact = "".join(material.split())
    if re.fullmatch(r"[0-9a-fA-F]{64}", compact):
        return bytes.fromhex(compact)
    try:
        key = base64.b64decode(compact, validate=True)
    except (ValueError, TypeError) as exc:
        raise UpdateError(
            "Guncelleme imza anahtari base64 veya hex kodlu olmali. "
            "Anahtar rotasyonu icin HYDRO_UPDATE_PUBKEY degerini kontrol edin."
        ) from exc
    if len(key) != 32:
        raise UpdateError(
            "Guncelleme imza anahtari 32 baytlik bir Ed25519 anahtari olmali "
            f"(gelen: {len(key)} bayt)."
        )
    return key


def _signature_candidate_urls(asset_download_url: str) -> list[str]:
    return [f"{asset_download_url}{suffix}" for suffix in SIGNATURE_URL_SUFFIXES]


def _decode_signature_blob(data: bytes) -> bytes:
    if not data:
        raise UpdateError(
            "Imza dosyasi bos. Guvenlik nedeniyle guncelleme iptal edildi; "
            "paketi release sayfasindan yeniden indirmeyi deneyin."
        )
    # Ham Ed25519 imzasi ikili veridir; metin normalizasyonu (strip/base64)
    # uygulanmaz. Aksi halde rastgele bir imzanin son bayti kirpilabilir.
    if len(data) == 64:
        return data
    blob = data.strip()
    if not blob:
        raise UpdateError(
            "Imza dosyasi bos. Guvenlik nedeniyle guncelleme iptal edildi; "
            "paketi release sayfasindan yeniden indirmeyi deneyin."
        )
    if blob.startswith(b"untrusted comment"):
        lines = [line.strip() for line in blob.splitlines() if line.strip()]
        if len(lines) < 2:
            raise UpdateError("Imza dosyasi minisign formatinda okunamadi.")
        try:
            blob = base64.b64decode(lines[1], validate=True)
        except (ValueError, TypeError) as exc:
            raise UpdateError("Imza dosyasi base64 olarak okunamadi.") from exc
    else:
        try:
            blob = base64.b64decode(blob, validate=True)
        except (ValueError, TypeError) as exc:
            raise UpdateError(
                "Imza dosyasi base64 olarak okunamadi; dosya bozulmus olabilir. "
                "Guvenlik nedeniyle guncelleme iptal edildi, paketi yeniden indirin."
            ) from exc
    if len(blob) == 74 and blob[:2] in SIGNATURE_ALGORITHM_MINISIGN:
        blob = blob[10:]
    if len(blob) != 64:
        raise UpdateError(
            "Imza formati desteklenmiyor (64 baytlik Ed25519 imzasi bekleniyor). "
            "Yayin sorumlusundan gecerli bir .sig dosyasi isteyin."
        )
    return blob


def _download_signature(
    asset_download_url: str,
    timeout_seconds: int,
) -> bytes | None:
    """``<asset>.sig`` / ``<asset>.minisig`` adaylarini dener; yoksa ``None``.

    404 disindaki HTTP hatalari ve ag hatalari ``UpdateError`` olarak yukselir.
    """
    for signature_url in _signature_candidate_urls(asset_download_url):
        request = Request(signature_url, headers=_build_headers("application/octet-stream"))
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                data = response.read()
        except HTTPError as exc:
            if exc.code == 404:
                continue
            raise UpdateError(
                f"Imza dosyasi indirilemedi (HTTP {exc.code}). "
                "Guvenlik nedeniyle guncelleme iptal edildi; lutfen daha sonra tekrar deneyin."
            ) from exc
        except URLError as exc:
            raise UpdateError(
                "Imza dosyasina ulasilamadi. Ag baglantisini kontrol edip tekrar deneyin; "
                "guvenlik nedeniyle imzasiz guncelleme yapilmaz."
            ) from exc
        if data.strip():
            return data
    return None


def _verify_ed25519_signature(file_path: Path, signature: bytes, public_key: bytes) -> None:
    """Dosyanin tamami uzerinde Ed25519 detached imza dogrular."""
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:  # pragma: no cover - runtime bagimliligi
        raise UpdateError(MISSING_CRYPTOGRAPHY_MESSAGE) from exc

    if len(public_key) != 32:
        raise UpdateError("Ed25519 acik anahtari 32 bayt olmali.")
    if len(signature) != 64:
        raise UpdateError("Ed25519 imzasi 64 bayt olmali.")

    key = Ed25519PublicKey.from_public_bytes(public_key)
    payload = file_path.read_bytes()
    try:
        key.verify(signature, payload)
    except InvalidSignature as exc:
        raise UpdateError(INVALID_SIGNATURE_MESSAGE.format(releases_url=RELEASES_PAGE_URL)) from exc


def verify_asset_signature(
    asset_path: Path,
    asset_download_url: str,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> bool:
    """Indirilen artefaktin Ed25519 imzasini dogrular.

    Varsayilan davranis **fail-closed**: gomulu public key
    (``app_metadata.UPDATE_SIGNING_PUBLIC_KEY``) veya ``HYDRO_UPDATE_PUBKEY``
    varsa imza zorunludur. Imza dosyasi yoksa/gecersizse ``UpdateError``
    yukselir ve guncelleme uygulanmaz.

    - ``HYDRO_UPDATE_PUBKEY`` gomulu anahtari gecersiz kilar (rotasyon kancasi).
    - ``HYDRO_ALLOW_UNSIGNED_UPDATE=1`` / ``HYDRO_REQUIRE_SIGNATURE=0`` yalnizca
      gelistirici icin imza *yoklugunu* tolere eder; imza varsa yine dogrulanir.

    Basarili dogrulamada ``True`` doner. Imza zorunlu degilse ve imza dosyasi
    yoksa ``False`` doner.
    """
    required = _signing_required()
    key_material = _signing_public_key_material()
    if not key_material:
        if required:
            raise UpdateError(MISSING_PUBLIC_KEY_MESSAGE)
        logger.warning(
            "Imza dogrulamasi devre disi: public key tanimli degil ve "
            "%s etkin. Bu yalnizca gelistirici makineleri icindir.",
            SIGNATURE_ENV_ALLOW_UNSIGNED,
        )
        return False

    public_key = _decode_public_key(key_material)
    signature_blob = _download_signature(asset_download_url, timeout_seconds)
    if signature_blob is None:
        if required:
            raise UpdateError(MISSING_SIGNATURE_MESSAGE.format(releases_url=RELEASES_PAGE_URL))
        logger.warning(
            "Imza zorunlu degil ve %s icin imza dosyasi bulunamadi; "
            "gelistirici kacis bayragi etkin oldugu icin devam ediliyor.",
            asset_path.name,
        )
        return False

    signature = _decode_signature_blob(signature_blob)
    _verify_ed25519_signature(asset_path, signature, public_key)
    logger.info("Guncelleme imzasi dogrulandi: %s", asset_path.name)
    return True


# --- Download / install -----------------------------------------------------


def _download_asset(
    asset: ReleaseAsset,
    target_path: Path,
    timeout_seconds: int,
    progress_callback: ProgressCallback | None = None,
) -> None:
    dm = DownloadManager()
    dm.download_file(
        asset.download_url,
        target_path,
        on_progress=progress_callback,
    )

    expected_sha = _download_checksum(asset.download_url, timeout_seconds)
    _verify_sha256(target_path, expected_sha)
    signature_verified = verify_asset_signature(target_path, asset.download_url, timeout_seconds)
    if signature_verified:
        logger.info("Guncelleme paketi imzali: %s", asset.name)
    else:
        logger.warning(
            "Guncelleme paketi imza dogrulamasi olmadan kabul edildi "
            "(gelistirici kacis bayragi etkin): %s",
            asset.name,
        )


def _append_update_log(log_path: Path | None, message: str) -> None:
    if log_path is None:
        return
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"{timestamp} {message}\n")
    except OSError:
        logger.warning("Guncelleme logu yazilamadi: %s", message)


def _normalized_member_name(name: str) -> str | None:
    """Zip uye adini guvenli goreli yola cevirir; guvensizse ``None``.

    Windows PowerShell ``Compress-Archive`` ters bolu kullanabilir; bu yuzden
    ``\\`` ayirici olarak normalize edilir. Mutlak yollar, surucu harfleri ve
    ``..`` bilesenleri reddedilir.
    """
    normalized = name.replace("\\", "/").strip()
    if not normalized:
        return None
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        return None
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    if not parts or ".." in parts:
        return None
    return "/".join(parts)


def _is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK(info.external_attr >> 16)


def _safe_extract_zip(archive_path: Path, extract_root: Path) -> Path:
    """Zip'i dogrulayarak cikarir ve beklenen uygulama klasorunu dondurur.

    Kurallar:
    - her uye goreli ve ``..`` icermeyen bir yol olmali (path traversal yok),
    - sembolik baglanti reddedilir,
    - dosya sayisi ve toplam acilmis boyut sinirlidir,
    - sonuc ``HidrostatikTest/HidrostatikTest.exe`` yapisini icermelidir.
    """
    extract_root.mkdir(parents=True, exist_ok=True)
    try:
        archive = zipfile.ZipFile(archive_path, "r")
    except zipfile.BadZipFile as exc:
        raise UpdateError("Indirilen guncelleme paketi gecerli bir zip degil.") from exc

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
                raise UpdateError(
                    f"Guncelleme paketi guvenli olmayan bir yol iceriyor: {info.filename!r}"
                )
            target_path = extract_root / normalized
            try:
                target_path.resolve().relative_to(extract_root.resolve())
            except ValueError as exc:
                raise UpdateError(
                    f"Guncelleme paketi hedef klasor disina yazmaya calisiyor: {info.filename!r}"
                ) from exc

            if info.is_dir() or normalized.endswith("/"):
                target_path.mkdir(parents=True, exist_ok=True)
                continue
            if _is_zip_symlink(info):
                raise UpdateError(
                    f"Guncelleme paketi sembolik baglanti iceriyor: {info.filename!r}"
                )
            if info.compress_size > 0 and (
                info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
            ):
                raise UpdateError(
                    f"Guncelleme paketi supheli sikistirma oranina sahip: {info.filename!r}"
                )

            target_path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target_path.open("wb") as destination:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    written_total += len(chunk)
                    if written_total > MAX_EXTRACTED_BYTES:
                        raise UpdateError(
                            "Guncelleme paketi acildiginda boyut siniri asildi "
                            f"({MAX_EXTRACTED_BYTES} bayt)."
                        )
                    destination.write(chunk)

    app_dir = extract_root / BINARY_NAME
    executable = app_dir / WINDOWS_SINGLE_EXE_NAME
    if not executable.is_file():
        raise UpdateError(
            "Guncelleme paketi beklenen yapiyi icermiyor "
            f"({BINARY_NAME}/{WINDOWS_SINGLE_EXE_NAME})."
        )
    return app_dir


def _ensure_pe_executable(file_path: Path) -> None:
    """Tek dosya .exe artefaktinin PE basligi tasidigini dogrular."""
    try:
        with file_path.open("rb") as executable_file:
            header = executable_file.read(2)
            if header != b"MZ":
                raise UpdateError(
                    "Indirilen .exe dosyasi gecerli bir Windows calistirilabilir dosyasi degil."
                )
            executable_file.seek(0x3C)
            offset_bytes = executable_file.read(4)
    except OSError as exc:
        raise UpdateError(f"Indirilen .exe dosyasi okunamadi: {exc}") from exc
    if len(offset_bytes) != 4:
        raise UpdateError("Indirilen .exe dosyasi eksik veya bozuk.")
    pe_offset = int.from_bytes(offset_bytes, "little")
    try:
        with file_path.open("rb") as executable_file:
            executable_file.seek(pe_offset)
            signature = executable_file.read(4)
    except OSError as exc:
        raise UpdateError(f"Indirilen .exe dosyasi okunamadi: {exc}") from exc
    if signature != b"PE\0\0":
        raise UpdateError("Indirilen .exe dosyasi gecerli bir PE basligi tasimiyor.")


def _prepare_staged_app(asset_path: Path, working_root: Path) -> Path:
    """Yeni surumu calisan dizinin disindaki bir sahne klasorune hazirlar."""
    stage_root = working_root / "stage"
    stage_app_dir = stage_root / BINARY_NAME
    if stage_app_dir.exists():
        raise UpdateError("Gecici update klasoru beklenmedik sekilde dolu.")
    stage_root.mkdir(parents=True, exist_ok=True)

    if asset_path.suffix.lower() == ".exe":
        _ensure_pe_executable(asset_path)
        stage_app_dir.mkdir(parents=True)
        shutil.copy2(asset_path, stage_app_dir / WINDOWS_SINGLE_EXE_NAME)
        return stage_app_dir

    extracted_app_dir = _safe_extract_zip(asset_path, working_root / "extract")
    shutil.move(str(extracted_app_dir), str(stage_app_dir))
    return stage_app_dir


def _safe_path_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", value.strip())
    return cleaned or "previous"


def _write_update_script(
    working_root: Path,
    stage_dir: Path,
    install_dir: Path,
    executable_path: Path,
    current_pid: int,
    version: str = "",
    backup_dir: Path | None = None,
    log_path: Path | None = None,
    new_dir: Path | None = None,
) -> Path:
    """Uygulama kapandiktan sonra calisacak yedekli/takasli kurulum betigi.

    Betik once canli dizinin ``backup-<version>`` kopyasini alir, yeni icerigi
    yan dizine cikarir, takas eder ve herhangi bir hata durumunda yedegi geri
    yukler. Tum adimlar ``apply_update.log`` dosyasina yazilir.
    """
    script_path = working_root / "apply_update.ps1"
    safe_version = _safe_path_component(version or "previous")
    backup_path = backup_dir or install_dir.with_name(f"{install_dir.name}-backup-{safe_version}")
    new_path = new_dir or install_dir.with_name(f"{install_dir.name}-new-{current_pid}")
    log_path = log_path or (working_root / UPDATE_LOG_NAME)
    script = "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            f"$AppPid = {current_pid}",
            f"$StageDir = '{_powershell_literal(str(stage_dir))}'",
            f"$TargetDir = '{_powershell_literal(str(install_dir))}'",
            f"$ExePath = '{_powershell_literal(str(executable_path))}'",
            f"$BackupDir = '{_powershell_literal(str(backup_path))}'",
            f"$NewDir = '{_powershell_literal(str(new_path))}'",
            f"$LogPath = '{_powershell_literal(str(log_path))}'",
            f"$SourceDir = Join-Path $StageDir '{BINARY_NAME}'",
            "function Write-UpdateLog([string]$Message) {",
            "    $line = ('{0} {1}' -f (Get-Date).ToString('s'), $Message)",
            "    Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8",
            "}",
            f"Write-UpdateLog 'Guncelleme basladi (surum: {_powershell_literal(safe_version)}).'",
            "$deadline = (Get-Date).AddSeconds(120)",
            "while ((Get-Process -Id $AppPid -ErrorAction SilentlyContinue) -and ((Get-Date) -lt $deadline)) {",
            "    Start-Sleep -Seconds 1",
            "}",
            "if (-not (Test-Path -LiteralPath $SourceDir)) {",
            "    Write-UpdateLog 'HATA: Guncelleme klasoru bulunamadi.'",
            "    throw 'Guncelleme klasoru bulunamadi.'",
            "}",
            "$swapped = $false",
            "try {",
            "    if (Test-Path -LiteralPath $BackupDir) {",
            "        Remove-Item -LiteralPath $BackupDir -Recurse -Force",
            "    }",
            "    if (Test-Path -LiteralPath $TargetDir) {",
            "        Write-UpdateLog ('Yedek aliniyor: ' + $BackupDir)",
            "        Copy-Item -LiteralPath $TargetDir -Destination $BackupDir -Recurse -Force",
            "    }",
            "    if (Test-Path -LiteralPath $NewDir) {",
            "        Remove-Item -LiteralPath $NewDir -Recurse -Force",
            "    }",
            "    New-Item -ItemType Directory -Path $NewDir -Force | Out-Null",
            "    Get-ChildItem -LiteralPath $SourceDir -Force | ForEach-Object {",
            "        Copy-Item -LiteralPath $_.FullName -Destination $NewDir -Recurse -Force",
            "    }",
            "    Write-UpdateLog ('Yeni icerik yan dizine cikarildi: ' + $NewDir)",
            "    if (Test-Path -LiteralPath $TargetDir) {",
            "        Remove-Item -LiteralPath $TargetDir -Recurse -Force",
            "    }",
            "    Move-Item -LiteralPath $NewDir -Destination $TargetDir -Force",
            "    $swapped = $true",
            "    Write-UpdateLog 'Yeni surum yerlestirildi.'",
            "} catch {",
            "    Write-UpdateLog ('HATA: ' + $_.Exception.Message)",
            "    if (-not $swapped) {",
            "        try {",
            "            if (Test-Path -LiteralPath $TargetDir) {",
            "                Remove-Item -LiteralPath $TargetDir -Recurse -Force",
            "            }",
            "            if (Test-Path -LiteralPath $BackupDir) {",
            "                Move-Item -LiteralPath $BackupDir -Destination $TargetDir -Force",
            "                Write-UpdateLog 'Geri alma tamamlandi.'",
            "            }",
            "        } catch {",
            "            Write-UpdateLog ('Geri alma basarisiz: ' + $_.Exception.Message)",
            "        }",
            "    }",
            "    throw",
            "}",
            "try {",
            "    Start-Process -FilePath $ExePath",
            "    Write-UpdateLog 'Uygulama yeniden baslatildi.'",
            "} catch {",
            "    Write-UpdateLog ('UYARI: Uygulama baslatilamadi: ' + $_.Exception.Message)",
            "}",
            "Remove-Item -LiteralPath $StageDir -Recurse -Force -ErrorAction SilentlyContinue",
        ]
    )
    # Windows PowerShell, UTF-8 BOM ile kaydedilen script dosyalarini Unicode yol adlariyla daha guvenli okur.
    script_path.write_text(script, encoding="utf-8-sig", newline="\r\n")
    return script_path


def _run_macos_command(arguments: list[str], error_message: str, timeout: int = 120) -> None:
    try:
        subprocess.run(arguments, check=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise UpdateError(f"{error_message}: gerekli arac bulunamadi ({arguments[0]}).") from exc
    except subprocess.TimeoutExpired as exc:
        raise UpdateError(f"{error_message}: islem zaman asimina ugradi.") from exc
    except subprocess.CalledProcessError as exc:
        raise UpdateError(f"{error_message}: {exc}") from exc
    except OSError as exc:
        raise UpdateError(f"{error_message}: {exc}") from exc


def _verify_macos_code_signature(app_path: Path, log_path: Path | None) -> bool:
    """``codesign --verify`` dener. Basarisizlik uyaridir; hash zorunludur."""
    try:
        completed = subprocess.run(
            ["codesign", "--verify", "--deep", "--strict", str(app_path)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        _append_update_log(log_path, f"UYARI: codesign calistirilamadi: {exc}")
        return False
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        _append_update_log(log_path, f"UYARI: kod imzasi dogrulanamadi: {detail}")
        logger.warning("Kod imzasi dogrulanamadi: %s", detail)
        return False
    _append_update_log(log_path, "Kod imzasi dogrulandi (codesign).")
    return True


def _install_macos_update(
    asset_path: Path,
    app_name: str = BINARY_NAME,
    version: str = "",
    apps_dir: Path | None = None,
    log_path: Path | None = None,
) -> None:
    """DMG'yi gecici bir mount noktasina baglar ve .app'i geri alinabilir kurar."""
    apps_root = apps_dir or Path("/Applications")
    mount_parent = Path(tempfile.mkdtemp(prefix="hidrostatik-dmg-"))
    mount_point = mount_parent / "mount"
    mount_point.mkdir(parents=True, exist_ok=True)
    attached = False
    try:
        _run_macos_command(
            [
                "hdiutil",
                "attach",
                str(asset_path),
                "-mountpoint",
                str(mount_point),
                "-readonly",
                "-nobrowse",
                "-noautoopen",
                "-quiet",
            ],
            "DMG mount edilemedi",
            timeout=60,
        )
        attached = True

        dmg_app = mount_point / f"{app_name}.app"
        if not dmg_app.exists():
            alternatives = sorted(mount_point.glob("*.app"))
            if not alternatives:
                raise UpdateError("DMG icinde .app bulunamadi.")
            dmg_app = alternatives[0]

        _verify_macos_code_signature(dmg_app, log_path)

        apps_root.mkdir(parents=True, exist_ok=True)
        target_app = apps_root / dmg_app.name
        backup_app = apps_root / (
            f"{dmg_app.name}-backup-{_safe_path_component(version or 'previous')}"
        )

        installed = False
        try:
            if target_app.exists():
                if backup_app.exists():
                    shutil.rmtree(backup_app, ignore_errors=True)
                _run_macos_command(
                    ["ditto", str(target_app), str(backup_app)],
                    "Mevcut uygulama yedeklenemedi",
                )
                _append_update_log(log_path, f"Yedek alindi: {backup_app}")
                try:
                    shutil.rmtree(target_app)
                except OSError as exc:
                    raise UpdateError(f"Mevcut uygulama kaldirilamadi: {exc}") from exc
            _run_macos_command(
                ["ditto", str(dmg_app), str(target_app)],
                "Guncelleme uygulanamadi",
            )
            installed = True
            _append_update_log(log_path, f"Yeni surum kuruldu: {target_app}")
        except UpdateError:
            if backup_app.exists():
                try:
                    if target_app.exists():
                        shutil.rmtree(target_app, ignore_errors=True)
                    _run_macos_command(
                        ["ditto", str(backup_app), str(target_app)],
                        "Geri alma basarisiz",
                    )
                    _append_update_log(log_path, "Geri alma tamamlandi.")
                except UpdateError as rollback_exc:
                    _append_update_log(log_path, f"HATA: {rollback_exc}")
            raise
        finally:
            if not installed:
                _append_update_log(log_path, "Kurulum tamamlanmadi.")

        try:
            subprocess.Popen(
                ["open", str(target_app)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            raise UpdateError(f"Uygulama yeniden baslatilamadi: {exc}") from exc
    finally:
        if attached:
            try:
                subprocess.run(
                    ["hdiutil", "detach", str(mount_point), "-quiet"],
                    check=False,
                    timeout=30,
                )
            except (OSError, subprocess.SubprocessError):
                pass
        shutil.rmtree(mount_parent, ignore_errors=True)


def install_update(
    update_info: UpdateInfo,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    download_root: Path | None = None,
    progress_callback: ProgressCallback | None = None,
) -> str:
    if not update_info.update_available:
        return "up_to_date"

    if update_info.asset is None:
        open_release_page(update_info.html_url)
        return "browser"

    runtime = get_runtime_context()
    if not runtime.can_self_update:
        open_release_page(update_info.html_url)
        return "browser"

    if download_root is not None:
        download_root.mkdir(parents=True, exist_ok=True)
        working_root = Path(tempfile.mkdtemp(prefix="hidrostatik-update-", dir=str(download_root)))
    else:
        working_root = Path(tempfile.mkdtemp(prefix="hidrostatik-update-"))

    log_path = working_root / UPDATE_LOG_NAME
    _append_update_log(log_path, f"Guncelleme hazirlaniyor: {update_info.asset.name}")

    asset_path = working_root / update_info.asset.name

    _download_asset(
        update_info.asset,
        asset_path,
        timeout_seconds,
        progress_callback=progress_callback,
    )

    if asset_path.suffix.lower() == ".dmg":
        if not sys.platform.startswith("darwin"):
            raise UpdateError("DMG paketi yalnizca macOS uzerinde kurulabilir.")
        _install_macos_update(
            asset_path,
            BINARY_NAME,
            version=update_info.latest_version,
            log_path=log_path,
        )
        return "self_update"

    if runtime.executable_path.suffix.lower() != ".exe":
        # Windows disi bir calistirilabilir ile Windows paketi kurulmaz.
        open_release_page(update_info.html_url)
        return "browser"

    _prepare_staged_app(asset_path, working_root)
    stage_root = working_root / "stage"
    safe_version = _safe_path_component(update_info.latest_version)
    backup_dir = runtime.install_dir.with_name(f"{runtime.install_dir.name}-backup-{safe_version}")
    new_dir = runtime.install_dir.with_name(f"{runtime.install_dir.name}-new-{os.getpid()}")
    script_path = _write_update_script(
        working_root=working_root,
        stage_dir=stage_root,
        install_dir=runtime.install_dir,
        executable_path=runtime.executable_path,
        current_pid=os.getpid(),
        version=update_info.latest_version,
        backup_dir=backup_dir,
        log_path=log_path,
        new_dir=new_dir,
    )
    try:
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
    except OSError as exc:
        _append_update_log(log_path, f"HATA: kurulum betigi baslatilamadi: {exc}")
        raise UpdateError(f"Guncelleme kurulum betigi baslatilamadi: {exc}") from exc
    return "self_update"

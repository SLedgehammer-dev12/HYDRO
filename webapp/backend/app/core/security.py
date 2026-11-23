"""Workspace identity and upload safety helpers.

MVP has no authentication. ``X-Session-ID`` is an anonymous *workspace* key;
it is hashed before storage and never logged raw.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import tempfile
import uuid
import weakref
from pathlib import Path
from typing import Any

WORKSPACE_HEADER = "X-Session-ID"
DEFAULT_WORKSPACE = "anonymous"
MAX_JSON_BODY_BYTES = 32 * 1024 * 1024
_UPLOAD_SEMAPHORES: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = (
    weakref.WeakKeyDictionary()
)
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")

_MAGIC_PREFIXES: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
    (b"BM", "image/bmp"),
    (b"PK\x03\x04", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "application/vnd.ms-excel"),
)

_EXTENSION_MIME = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
}


def normalize_workspace(raw: str | None) -> str:
    if raw is None:
        return DEFAULT_WORKSPACE
    cleaned = raw.strip()
    if not cleaned:
        return DEFAULT_WORKSPACE
    if len(cleaned) > 200:
        return cleaned[:200]
    return cleaned


def workspace_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def actor_for(raw: str) -> str:
    return f"anonymous:{workspace_hash(raw)[:8]}"


def hash_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def safe_filename(name: str | None) -> str:
    """Return a display-only filename (never used to build paths)."""

    if not name:
        return "upload"
    base = Path(name).name
    base = _SAFE_NAME.sub("_", base).strip("._")
    return (base or "upload")[:180]


def sniff_mime(head: bytes) -> str | None:
    for prefix, mime in _MAGIC_PREFIXES:
        if head.startswith(prefix):
            return mime
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def expected_mime(extension: str) -> str | None:
    return _EXTENSION_MIME.get(extension.lower())


def new_stored_name(extension: str) -> str:
    return f"{uuid.uuid4().hex}{extension.lower()}"


def ensure_within(root: Path, candidate: Path) -> Path:
    """Resolve ``candidate`` and make sure it stays under ``root``."""

    from .errors import AppError

    resolved_root = root.resolve()
    resolved = candidate.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise AppError(
            "invalid_path",
            "Dosya yolu izin verilen kok dizin disinda.",
            status_code=400,
            details={"reason": "path_traversal"},
        )
    return resolved


def write_private_file(target: Path, chunks) -> int:
    """Write chunks to ``target`` atomically with ``0600`` permissions."""

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(target.parent, 0o700)
    except OSError:
        pass
    temp = target.parent / f".tmp-{uuid.uuid4().hex}"
    written = 0
    try:
        with temp.open("wb") as handle:
            for chunk in chunks:
                if not chunk:
                    continue
                handle.write(chunk)
                written += len(chunk)
        os.chmod(temp, 0o600)
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink(missing_ok=True)
    return written


async def read_upload_bounded(upload: Any, max_bytes: int, *, chunk_size: int = 65536) -> bytes:
    """Stream-read an upload and abort early with ``413`` if it exceeds ``max_bytes``."""

    from .errors import AppError

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            limit_mb = max(1, max_bytes // (1024 * 1024))
            raise AppError(
                "file_too_large",
                f"Yuklenen dosya izin verilen boyutu ({limit_mb} MB) asiyor.",
                status_code=413,
                details={"max_bytes": max_bytes},
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _get_upload_semaphore() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    sem = _UPLOAD_SEMAPHORES.get(loop)
    if sem is None:
        sem = asyncio.Semaphore(2)
        _UPLOAD_SEMAPHORES[loop] = sem
    return sem


async def stream_upload_to_tempfile(
    upload: Any,
    max_bytes: int,
    *,
    suffix: str = ".bin",
    chunk_size: int = 65536,
    temp_dir: Path | None = None,
) -> Path:
    """Stream an upload directly to a ``0600`` temporary file on disk under concurrency cap."""

    from .errors import AppError

    if temp_dir is not None:
        temp_dir.mkdir(parents=True, exist_ok=True)

    sem = _get_upload_semaphore()
    async with sem:
        fd, tmp_name = tempfile.mkstemp(
            prefix="hydro_upload_",
            suffix=suffix,
            dir=str(temp_dir) if temp_dir is not None else None,
        )
        target = Path(tmp_name)
        try:
            try:
                os.fchmod(fd, 0o600)
            except OSError:
                pass
            total = 0
            with os.fdopen(fd, "wb") as handle:
                while True:
                    chunk = await upload.read(chunk_size)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        limit_mb = max(1, max_bytes // (1024 * 1024))
                        raise AppError(
                            "file_too_large",
                            f"Yuklenen dosya izin verilen boyutu ({limit_mb} MB) asiyor.",
                            status_code=413,
                            details={"max_bytes": max_bytes},
                        )
                    handle.write(chunk)
            return target
        except Exception:
            target.unlink(missing_ok=True)
            raise


__all__ = [
    "DEFAULT_WORKSPACE",
    "MAX_JSON_BODY_BYTES",
    "WORKSPACE_HEADER",
    "actor_for",
    "ensure_within",
    "expected_mime",
    "hash_bytes",
    "new_stored_name",
    "normalize_workspace",
    "read_upload_bounded",
    "safe_filename",
    "sniff_mime",
    "stream_upload_to_tempfile",
    "workspace_hash",
    "write_private_file",
]

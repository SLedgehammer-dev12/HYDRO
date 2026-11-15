"""Upload storage with allowlist, size limit and MIME sniffing."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from hidrostatik_test.services.report_ocr import SUPPORTED_EXTENSIONS

from ..core.errors import AppError
from ..core.security import (
    ensure_within,
    expected_mime,
    new_stored_name,
    safe_filename,
    sniff_mime,
)

MAX_HEAD_BYTES = 4096
_FOLDER_SAFE = re.compile(r"[^A-Za-z0-9_-]+")


@dataclass(frozen=True)
class StoredUpload:
    path: Path
    relative_path: str
    filename: str
    mime: str
    size_bytes: int
    sha256: str
    extension: str


def _upload_folder(uploads_root: Path, workspace_hash: str, session_id: str | None) -> Path:
    if session_id:
        folder_name = _FOLDER_SAFE.sub("", session_id)[:64] or "session"
    else:
        folder_name = (workspace_hash or "anonymous")[:16]
    folder = uploads_root / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    try:
        folder.chmod(0o700)
    except OSError:
        pass
    return folder


def _sanitize_head(head: bytes) -> bytes:
    return head.lstrip(b"\xef\xbb\xbf \t\r\n")


def store_upload(
    *,
    uploads_root: Path,
    workspace_hash: str,
    session_id: str | None,
    original_name: str | None,
    stream: BinaryIO,
    max_bytes: int,
) -> StoredUpload:
    display_name = safe_filename(original_name)
    extension = Path(display_name).suffix.lower()
    if extension not in {item.lower() for item in SUPPORTED_EXTENSIONS}:
        raise AppError(
            "unsupported_format",
            f"Desteklenmeyen dosya turu: {extension or '(uzantisiz)'}.",
            status_code=415,
            details={"supported": sorted(SUPPORTED_EXTENSIONS)},
        )

    head = stream.read(MAX_HEAD_BYTES) or b""
    if not head:
        raise AppError("empty_file", "Dosya bos.", status_code=422)

    detected = sniff_mime(_sanitize_head(head))
    expected = expected_mime(extension)
    if detected is None:
        raise AppError(
            "unsupported_format",
            "Dosya icerigi taninmadi (uzanti/MIME uyusmuyor).",
            status_code=415,
            details={"extension": extension, "detected": None},
        )
    if expected and detected != expected:
        raise AppError(
            "unsupported_format",
            f"Dosya uzantisi ({extension}) icerikle ({detected}) uyusmuyor.",
            status_code=415,
            details={"extension": extension, "detected": detected, "expected": expected},
        )

    folder = _upload_folder(uploads_root, workspace_hash, session_id)
    stored_name = new_stored_name(extension)
    target = ensure_within(uploads_root, folder / stored_name)

    temp = target.parent / f".tmp-{uuid.uuid4().hex}"
    digest = hashlib.sha256()
    size = 0
    try:
        with temp.open("wb") as handle:
            for chunk in (head,):
                handle.write(chunk)
                digest.update(chunk)
                size += len(chunk)
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise AppError(
                        "file_too_large",
                        f"Dosya boyut siniri asildi ({max_bytes} bayt).",
                        status_code=413,
                        details={"max_bytes": max_bytes},
                    )
                handle.write(chunk)
                digest.update(chunk)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            temp.chmod(0o600)
        except OSError:
            pass
        temp.replace(target)
    finally:
        if temp.exists():
            temp.unlink(missing_ok=True)

    return StoredUpload(
        path=target,
        relative_path=target.relative_to(uploads_root.resolve()).as_posix(),
        filename=display_name,
        mime=detected,
        size_bytes=size,
        sha256=digest.hexdigest(),
        extension=extension,
    )


def resolve_stored_path(uploads_root: Path, relative_path: str) -> Path:
    candidate = (uploads_root / relative_path).resolve()
    return ensure_within(uploads_root, candidate)


__all__ = [
    "StoredUpload",
    "kind_for_extension",
    "resolve_stored_path",
    "store_upload",
]


def kind_for_extension(extension: str) -> str:
    return "report_pdf" if extension.lower() == ".pdf" else "report_image"

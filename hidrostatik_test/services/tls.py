"""Strict TLS/SSL context construction for updater HTTPS requests.

PyInstaller bundles on macOS and Python installs on corporate Windows networks
often lack an OpenSSL CA file in Python's default verify paths. Preferring
``truststore`` uses the operating system certificate store (macOS Keychain,
Windows Certificate Store / Schannel, Linux system trust), with ``certifi`` as
the cross-platform CA bundle fallback. Hostname checking and ``CERT_REQUIRED``
are never disabled.
"""

from __future__ import annotations

import logging
import os
import ssl
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


def _has_valid_ssl_env_override() -> bool:
    for env_name in ("SSL_CERT_FILE", "SSL_CERT_DIR"):
        raw = os.environ.get(env_name, "").strip()
        if raw and Path(raw).exists():
            return True
    return False


def build_ssl_context() -> ssl.SSLContext:
    """Return a strict TLS client context backed by OS trust store or certifi."""
    if _has_valid_ssl_env_override():
        return ssl.create_default_context()

    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception as exc:
        logger.debug("truststore SSLContext kullanilamadi, certifi denenecek: %s", exc)

    try:
        import certifi

        cafile = certifi.where()
        if cafile and Path(cafile).is_file():
            return ssl.create_default_context(cafile=cafile)
    except Exception as exc:
        logger.debug("certifi CA paketi yuklenemedi, sistem varsayilani kullanilacak: %s", exc)

    return ssl.create_default_context()


def open_url(
    request: Request,
    *,
    timeout: int | float,
    opener: Callable[..., Any] = urlopen,
) -> Any:
    """Open an HTTP/HTTPS request with a strict TLS context.

    Falls back to calling ``opener(request, timeout=timeout)`` only when a
    mocked opener in tests does not accept a ``context`` keyword argument.
    """
    ctx = build_ssl_context()
    try:
        return opener(request, timeout=timeout, context=ctx)
    except TypeError as exc:
        if "context" in str(exc):
            return opener(request, timeout=timeout)
        raise


__all__ = ["build_ssl_context", "open_url"]

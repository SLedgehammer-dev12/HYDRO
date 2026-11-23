from __future__ import annotations

import builtins
import ssl
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
from urllib.request import Request

from hidrostatik_test.services import download_manager, tls, updater


class TlsContextTests(unittest.TestCase):
    def test_build_ssl_context_prefers_truststore_and_keeps_strict_verification(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            ctx = tls.build_ssl_context()
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(ctx.check_hostname)

    def test_build_ssl_context_falls_back_to_certifi_when_truststore_missing(self) -> None:
        real_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "truststore":
                raise ImportError("no truststore")
            return real_import(name, globals, locals, fromlist, level)

        with (
            patch.dict("os.environ", {}, clear=True),
            patch("builtins.__import__", side_effect=fake_import),
        ):
            ctx = tls.build_ssl_context()
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(ctx.check_hostname)

    def test_build_ssl_context_respects_ssl_cert_file_env_override(self) -> None:
        import certifi

        with (
            patch.dict("os.environ", {"SSL_CERT_FILE": certifi.where()}, clear=True),
            patch("hidrostatik_test.services.tls.ssl.create_default_context") as mocked_default,
        ):
            tls.build_ssl_context()
        mocked_default.assert_called_once_with()

    def test_open_url_passes_context_and_supports_legacy_two_arg_stubs(self) -> None:
        seen: list[object] = []

        def strict_opener(req, timeout=10, context=None):
            seen.append(context)
            return "ok"

        req = Request("https://example.com")
        self.assertEqual(tls.open_url(req, timeout=5, opener=strict_opener), "ok")
        self.assertIsNotNone(seen[0])

        def legacy_stub(req, timeout=10):
            return f"legacy:{timeout}"

        self.assertEqual(tls.open_url(req, timeout=7, opener=legacy_stub), "legacy:7")


class UpdaterWindowsTlsFallbackTests(unittest.TestCase):
    def test_download_file_falls_back_to_powershell_on_win32_urlerror(self) -> None:
        progress_calls: list[tuple[int, int]] = []

        def fake_ps(
            url: str, headers: dict[str, str], target_path: Path, timeout_seconds: int
        ) -> None:
            target_path.write_bytes(b"zip-payload")

        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "app.zip"
            with (
                patch.object(download_manager.sys, "platform", "win32"),
                patch.object(
                    download_manager,
                    "open_url",
                    side_effect=URLError("CERTIFICATE_VERIFY_FAILED"),
                ),
                patch.object(updater, "_download_via_powershell", side_effect=fake_ps),
            ):
                download_manager.DownloadManager.download_file(
                    "https://github.com/org/repo/releases/download/v1/app.zip",
                    dest,
                    on_progress=lambda _p, d, t, _s, _e: progress_calls.append((d, t)),
                )
            self.assertEqual(dest.read_bytes(), b"zip-payload")
            self.assertEqual(progress_calls, [(11, 11)])

    def test_download_checksum_and_signature_fall_back_to_powershell_on_win32(self) -> None:
        digest = "a" * 64
        raw_sig = b"S" * 64

        def fake_ps(
            url: str, headers: dict[str, str], target_path: Path, timeout_seconds: int
        ) -> None:
            if url.endswith(".sha256.txt"):
                target_path.write_text(f"{digest}  app.zip\n", encoding="utf-8")
            elif url.endswith(".sig"):
                target_path.write_bytes(raw_sig)
            else:
                raise updater.UpdateError("404 Not Found")

        asset_url = "https://github.com/org/repo/releases/download/v1/app.zip"
        with (
            patch.object(updater.sys, "platform", "win32"),
            patch.object(updater, "open_url", side_effect=URLError("CERTIFICATE_VERIFY_FAILED")),
            patch.object(updater, "_download_via_powershell", side_effect=fake_ps),
        ):
            self.assertEqual(updater._download_checksum(asset_url, 10), digest)
            self.assertEqual(updater._download_signature(asset_url, 10), raw_sig)
            self.assertEqual(sys.platform, sys.platform)


if __name__ == "__main__":
    unittest.main()

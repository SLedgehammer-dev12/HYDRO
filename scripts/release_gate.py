#!/usr/bin/env python3
"""Single-command release gate and cross-file version parity checker."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "webapp" / "frontend"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def check_version_parity() -> tuple[bool, str]:
    """Verify APP_VERSION matches package.json, Inno Setup, OpenAPI, and release docs."""
    meta_text = _read_text(ROOT / "hidrostatik_test" / "app_metadata.py")
    match = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', meta_text, re.MULTILINE)
    if not match:
        return False, "APP_VERSION not found in hidrostatik_test/app_metadata.py"
    version = match.group(1).strip()

    failures: list[str] = []

    pkg = json.loads(_read_text(FRONTEND_DIR / "package.json"))
    if pkg.get("version") != version:
        failures.append(f"package.json={pkg.get('version')!r} != {version!r}")

    iss_text = _read_text(ROOT / "installer" / "hydro_web.iss")
    iss_match = re.search(r'#define\s+MyAppVersion\s+"([^"]+)"', iss_text)
    if not iss_match or iss_match.group(1) != version:
        actual_iss = iss_match.group(1) if iss_match else None
        failures.append(f"hydro_web.iss={actual_iss!r} != {version!r}")

    openapi = json.loads(_read_text(ROOT / "webapp" / "docs" / "openapi.json"))
    openapi_ver = (openapi.get("info") or {}).get("version")
    if openapi_ver != version:
        failures.append(f"openapi.json={openapi_ver!r} != {version!r}")

    changelog = _read_text(ROOT / "CHANGELOG.md")
    cl_match = re.search(r"^##\s+([^\s]+)\s+-", changelog, re.MULTILINE)
    if not cl_match or cl_match.group(1) != version:
        actual_cl = cl_match.group(1) if cl_match else None
        failures.append(f"CHANGELOG.md={actual_cl!r} != {version!r}")

    whats_new = _read_text(ROOT / "WHATS_NEW.md")
    if f"v{version}" not in whats_new:
        failures.append(f"WHATS_NEW.md missing v{version}")

    durum = _read_text(ROOT / "DURUM.md")
    if f"`v{version}" not in durum:
        failures.append(f"DURUM.md missing `v{version}`")

    if failures:
        return False, "; ".join(failures)
    return True, f"version={version} consistent across 7 artifacts"


def _run_step(
    name: str,
    cmd: list[str],
    *,
    cwd: Path = ROOT,
    extra_env: dict[str, str] | None = None,
) -> tuple[bool, float]:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    started = time.monotonic()
    print(f"\n==> [{name}] {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(cwd), env=env, check=False)
    elapsed = time.monotonic() - started
    return proc.returncode == 0, elapsed


def _run_browser_smoke() -> tuple[bool, float]:
    started = time.monotonic()
    print("\n==> [verify-tabs] starting isolated backend on 127.0.0.1:8099")
    with tempfile.TemporaryDirectory(prefix="hydro_gate_") as tmp_dir:
        log_path = Path(tmp_dir) / "server.log"
        env = os.environ.copy()
        env["HYDRO_DATA_DIR"] = tmp_dir
        with log_path.open("w", encoding="utf-8") as log_file:
            server = subprocess.Popen(
                [
                    sys.executable,
                    "webapp/run_web.py",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8099",
                ],
                cwd=str(ROOT),
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
            try:
                healthy = False
                for _ in range(40):
                    try:
                        with urllib.request.urlopen(
                            "http://127.0.0.1:8099/api/health",
                            timeout=1.5,
                        ) as resp:
                            if resp.status == 200:
                                healthy = True
                                break
                    except (urllib.error.URLError, TimeoutError):
                        time.sleep(0.5)
                if not healthy:
                    print("Server failed health check. Log:\n" + _read_text(log_path))
                    return False, time.monotonic() - started

                smoke_env = os.environ.copy()
                smoke_env["HYDRO_APP_URL"] = "http://127.0.0.1:8099"
                proc = subprocess.run(
                    ["node", "scripts/verify-tabs.mjs"],
                    cwd=str(FRONTEND_DIR),
                    env=smoke_env,
                    check=False,
                )
                return proc.returncode == 0, time.monotonic() - started
            finally:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version-only",
        action="store_true",
        help="Check cross-file APP_VERSION consistency only.",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run lint, format, mypy, OpenAPI, and client contract checks without full test suites.",
    )
    parser.add_argument(
        "--with-smoke",
        action="store_true",
        help="Also start an isolated web server and run Playwright/CDP verify-tabs smoke.",
    )
    args = parser.parse_args(argv)

    results: list[tuple[str, bool, float, str]] = []
    ver_ok, ver_note = check_version_parity()
    results.append(("version-parity", ver_ok, 0.0, ver_note))
    if args.version_only:
        _print_summary(results)
        return 0 if ver_ok else 1

    py_backend_env = {"PYTHONPATH": f"{ROOT / 'webapp' / 'backend'}:{ROOT}"}
    quick_steps: list[tuple[str, list[str], Path, dict[str, str] | None]] = [
        ("ruff-check", [sys.executable, "-m", "ruff", "check", "."], ROOT, None),
        ("ruff-format", [sys.executable, "-m", "ruff", "format", "--check", "."], ROOT, None),
        ("mypy-domain", [sys.executable, "-m", "mypy", "hidrostatik_test/domain/"], ROOT, None),
        (
            "mypy-web",
            [sys.executable, "-m", "mypy", "--ignore-missing-imports", "webapp/backend/app"],
            ROOT,
            None,
        ),
        (
            "openapi-check",
            [sys.executable, "-m", "app.tools.dump_openapi", "--check"],
            ROOT,
            py_backend_env,
        ),
        (
            "api-inventory-check",
            [sys.executable, "-m", "app.tools.sync_api_inventory", "--check"],
            ROOT,
            py_backend_env,
        ),
        (
            "doc-metrics-check",
            [sys.executable, "scripts/sync_doc_metrics.py", "--check"],
            ROOT,
            None,
        ),
        ("frontend-check-api", ["npm", "run", "check:api"], FRONTEND_DIR, None),
        ("frontend-api-types", ["npm", "run", "check:api-types"], FRONTEND_DIR, None),
    ]

    full_steps: list[tuple[str, list[str], Path, dict[str, str] | None]] = [
        (
            "backend-pytest",
            [sys.executable, "-m", "pytest", "webapp/backend/tests", "-q"],
            ROOT,
            None,
        ),
        ("ocr-unittest", [sys.executable, "-m", "unittest", "tests.test_report_ocr"], ROOT, None),
        ("frontend-lint", ["npm", "run", "lint"], FRONTEND_DIR, None),
        ("frontend-test", ["npm", "test"], FRONTEND_DIR, None),
        ("frontend-typecheck", ["npm", "run", "typecheck"], FRONTEND_DIR, None),
        ("frontend-build", ["npm", "run", "build"], FRONTEND_DIR, None),
        ("frontend-bundle", ["npm", "run", "check:bundle"], FRONTEND_DIR, None),
    ]

    steps = quick_steps if args.quick else quick_steps + full_steps
    for name, cmd, cwd, env in steps:
        ok, elapsed = _run_step(name, cmd, cwd=cwd, extra_env=env)
        results.append((name, ok, elapsed, ""))

    if args.with_smoke and not args.quick:
        smoke_ok, smoke_elapsed = _run_browser_smoke()
        results.append(("verify-tabs", smoke_ok, smoke_elapsed, ""))

    _print_summary(results)
    return 0 if all(item[1] for item in results) else 1


def _print_summary(results: list[tuple[str, bool, float, str]]) -> None:
    print("\n================ RELEASE GATE SUMMARY ================")
    for name, ok, elapsed, note in results:
        status = "PASS" if ok else "FAIL"
        suffix = f" ({note})" if note else f" ({elapsed:.1f}s)"
        print(f"  {status:<4}  {name:<20}{suffix}")
    print("======================================================")


if __name__ == "__main__":
    raise SystemExit(main())

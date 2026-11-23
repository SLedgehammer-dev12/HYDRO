"""OpenAPI machine-verified contract and run_web worker resolution tests (Slice 3: F2, F9)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from app.core.config import Settings
from app.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[3]
OPENAPI_JSON_PATH = REPO_ROOT / "webapp" / "docs" / "openapi.json"
API_CONTRACT_MD_PATH = REPO_ROOT / "webapp" / "docs" / "api_contract.md"
RUN_WEB_PATH = REPO_ROOT / "webapp" / "run_web.py"


def _load_run_web():
    spec = importlib.util.spec_from_file_location("hydro_run_web_test", RUN_WEB_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_openapi_snapshot_matches_live_app():
    assert OPENAPI_JSON_PATH.is_file(), "webapp/docs/openapi.json must be generated and committed"
    committed = json.loads(OPENAPI_JSON_PATH.read_text(encoding="utf-8"))
    live = create_app(Settings()).openapi()
    assert committed == live


def test_api_contract_doc_references_openapi_and_admin_form_headers():
    text = API_CONTRACT_MD_PATH.read_text(encoding="utf-8")
    assert "openapi.json" in text
    assert "X-Hydro-Admin-Token" in text
    assert "forms/{form_code}" in text


def test_resolve_worker_count_clamps_sqlite_and_allows_postgres(capsys):
    run_web = _load_run_web()
    assert hasattr(run_web, "resolve_worker_count")

    clamped = run_web.resolve_worker_count("sqlite:///data/hydro_web.db", "4")
    captured = capsys.readouterr()
    assert clamped == 1
    assert "SQLite" in captured.err

    pg_workers = run_web.resolve_worker_count(
        "postgresql+psycopg://hydro:secret@db:5432/hydro", "4"
    )
    assert pg_workers == 4

    assert (
        run_web.resolve_worker_count("postgresql+psycopg://hydro:secret@db:5432/hydro", None) == 1
    )
    assert (
        run_web.resolve_worker_count("postgresql+psycopg://hydro:secret@db:5432/hydro", "abc") == 1
    )
    assert run_web.resolve_worker_count("postgresql+psycopg://hydro:secret@db:5432/hydro", "0") == 1

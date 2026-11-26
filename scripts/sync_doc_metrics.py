#!/usr/bin/env python3
"""Sync live repository metrics into DURUM.md (R24 single source of truth)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START_MARKER = "<!-- generated:metrics:start -->"
END_MARKER = "<!-- generated:metrics:end -->"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_app_version() -> str:
    text = _read(ROOT / "hidrostatik_test" / "app_metadata.py")
    match = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise RuntimeError("APP_VERSION not found in hidrostatik_test/app_metadata.py")
    return match.group(1).strip()


def _extract_head_revision() -> str:
    text = _read(ROOT / "webapp" / "backend" / "app" / "migrations_runner.py")
    match = re.search(r'^HEAD_REVISION\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise RuntimeError("HEAD_REVISION not found in migrations_runner.py")
    return match.group(1).strip()


def render_metrics_block() -> str:
    app_version = _extract_app_version()
    pkg = json.loads(_read(ROOT / "webapp" / "frontend" / "package.json"))
    frontend_version = str(pkg.get("version") or "")
    openapi = json.loads(_read(ROOT / "webapp" / "docs" / "openapi.json"))
    paths = openapi.get("paths") or {}
    path_count = len(paths)
    op_count = sum(
        len(
            [
                m
                for m in methods
                if m in {"get", "post", "put", "patch", "delete", "options", "head"}
            ]
        )
        for methods in paths.values()
        if isinstance(methods, dict)
    )
    head_rev = _extract_head_revision()

    lines = [
        START_MARKER,
        "| Otomatik Metrik (`sync_doc_metrics.py`) | Değer | Kaynak |",
        "| --- | --- | --- |",
        f"| Uygulama / Frontend Sürümü | `{app_version}` / `{frontend_version}` | `app_metadata.py`, `package.json` |",
        f"| Veritabanı Şema Revizyonu (Alembic) | `{head_rev}` | `migrations_runner.py` |",
        f"| OpenAPI Sözleşme Yüzeyi | `{path_count}` path / `{op_count}` operation | `webapp/docs/openapi.json` |",
        END_MARKER,
    ]
    return "\n".join(lines)


def sync_durum(*, check_only: bool) -> int:
    durum_path = ROOT / "DURUM.md"
    content = _read(durum_path)
    block = render_metrics_block()
    pattern = re.compile(
        rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}",
        re.DOTALL,
    )
    if not pattern.search(content):
        print("DURUM.md missing <!-- generated:metrics:start/end --> markers.", file=sys.stderr)
        return 1

    updated = pattern.sub(block, content, count=1)
    if check_only:
        if content != updated:
            print(
                "Doc metrics out of sync. Run: python3 scripts/sync_doc_metrics.py", file=sys.stderr
            )
            return 1
        print("Doc metrics OK: DURUM.md matches live repository sources.")
        return 0

    if content != updated:
        durum_path.write_text(updated, encoding="utf-8")
        print("Updated DURUM.md generated metrics block.")
    else:
        print("DURUM.md metrics block already up to date.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync live repo metrics into DURUM.md")
    parser.add_argument("--check", action="store_true", help="Exit 1 if DURUM.md is out of sync.")
    args = parser.parse_args(argv)
    return sync_durum(check_only=args.check)


if __name__ == "__main__":
    raise SystemExit(main())

"""Synchronize the auto-generated OpenAPI endpoint inventory inside api_contract.md."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OPENAPI_PATH = ROOT / "webapp" / "docs" / "openapi.json"
CONTRACT_PATH = ROOT / "webapp" / "docs" / "api_contract.md"

START_MARKER = "<!-- generated:openapi-inventory:start -->"
END_MARKER = "<!-- generated:openapi-inventory:end -->"
SECTION_HEADER = "## 16. Otomatik Üretilen OpenAPI Uç Envanteri"
HTTP_METHODS = ("get", "post", "put", "patch", "delete")


def render_inventory_block(openapi_path: Path = OPENAPI_PATH) -> str:
    spec = json.loads(openapi_path.read_text(encoding="utf-8"))
    paths = spec.get("paths") or {}
    rows: list[tuple[str, str, str]] = []
    for path_str in sorted(paths.keys()):
        ops = paths[path_str] or {}
        for method in HTTP_METHODS:
            op = ops.get(method)
            if not isinstance(op, dict):
                continue
            label = str(op.get("summary") or op.get("operationId") or "").strip().replace("|", "/")
            rows.append((method.upper(), path_str, label))

    lines = [
        START_MARKER,
        f"> OpenAPI `info.version={spec.get('info', {}).get('version', '?')}` · "
        f"**{len(paths)}** path / **{len(rows)}** operasyon (`sync_api_inventory` ile üretildi).",
        "",
        "| Metot | Yol | Özet / Operation ID |",
        "| --- | --- | --- |",
    ]
    for method, path_str, label in rows:
        lines.append(f"| `{method}` | `{path_str}` | {label} |")
    lines.append(END_MARKER)
    return "\n".join(lines)


def update_contract_text(contract_text: str, block: str) -> str:
    pattern = re.compile(
        re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER),
        flags=re.DOTALL,
    )
    if pattern.search(contract_text):
        return pattern.sub(block, contract_text, count=1)
    suffix = contract_text.rstrip() + f"\n\n---\n\n{SECTION_HEADER}\n\n{block}\n"
    return suffix


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify api_contract.md matches openapi.json without modifying files.",
    )
    args = parser.parse_args(argv)

    block = render_inventory_block()
    current = CONTRACT_PATH.read_text(encoding="utf-8")
    updated = update_contract_text(current, block)

    if args.check:
        if current != updated:
            print(
                "FAIL: webapp/docs/api_contract.md OpenAPI inventory is out of date.\n"
                "Run: PYTHONPATH=webapp/backend:. python3 -m app.tools.sync_api_inventory"
            )
            return 1
        print("API inventory OK: api_contract.md matches openapi.json.")
        return 0

    if current != updated:
        CONTRACT_PATH.write_text(updated, encoding="utf-8")
        print("Updated webapp/docs/api_contract.md OpenAPI inventory.")
    else:
        print("webapp/docs/api_contract.md OpenAPI inventory already up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

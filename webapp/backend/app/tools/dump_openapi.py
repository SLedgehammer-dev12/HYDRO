"""Generate or verify webapp/docs/openapi.json from the live FastAPI application."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_OUTPUT = REPO_ROOT / "webapp" / "docs" / "openapi.json"


def render_openapi_json() -> str:
    from ..core.config import Settings
    from ..main import create_app

    schema = create_app(Settings()).openapi()
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="HYDRO FastAPI OpenAPI semasini uretir veya dogrular."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Hedef openapi.json dosya yolu",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Dosyayi yazmak yerine mevcut dosyayla birebir esitligini denetler",
    )
    args = parser.parse_args(argv)
    rendered = render_openapi_json()
    target: Path = args.output
    if args.check:
        if not target.is_file():
            print(f"Eksik OpenAPI dosyasi: {target}", file=sys.stderr)
            return 1
        existing = target.read_text(encoding="utf-8")
        if existing != rendered:
            print(
                f"OpenAPI sozlesmesi guncel degil: {target}. "
                "Yenilemek icin `PYTHONPATH=webapp/backend:. python3 -m app.tools.dump_openapi` calistirin.",
                file=sys.stderr,
            )
            return 1
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

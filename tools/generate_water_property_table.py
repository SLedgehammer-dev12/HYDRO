from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hidrostatik_test.services.water_property_table_builder import generate_default_water_property_table


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "0-40 degC ve 1-150 bar icin A ve beta_water grid tablosunu "
            "CSV + metadata olarak uretir."
        )
    )
    parser.add_argument(
        "--backend",
        default="coolprop",
        help="Tabloyu dolduracak backend anahtari. Varsayilan: coolprop",
    )
    args = parser.parse_args()

    csv_path, metadata_path = generate_default_water_property_table(backend=args.backend)
    print(f"CSV: {csv_path}")
    print(f"Metadata: {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

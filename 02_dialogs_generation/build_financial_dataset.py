from __future__ import annotations

import argparse
import sys
from pathlib import Path


# Allow running from repo root or any working directory.
_THIS_DIR = Path(__file__).resolve().parent
_SRC_DIR = _THIS_DIR / "src"
for _path in (_SRC_DIR, _THIS_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


from financial_dataset import build_financial_profiles_from_tables, save_financial_profiles_json


def main() -> None:
    p = argparse.ArgumentParser(description="Build a household-level financial dataset JSON from generated CSV tables.")
    p.add_argument(
        "--tables-dir",
        type=Path,
        required=True,
        help="Path to 01_data_generation/artifacts/tables (contains households.csv, people.csv, etc.)",
    )
    p.add_argument(
        "--out-json",
        type=Path,
        required=True,
        help="Output JSON path (list of per-household profiles)",
    )
    args = p.parse_args()

    profiles = build_financial_profiles_from_tables(args.tables_dir)
    save_financial_profiles_json(profiles, args.out_json)
    print(f"Wrote {len(profiles)} profiles to {args.out_json}")


if __name__ == "__main__":
    main()

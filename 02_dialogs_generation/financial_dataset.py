from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


def _records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    recs = df.to_dict(orient="records")
    # Normalize NaN -> None for JSON friendliness.
    for r in recs:
        for k, v in list(r.items()):
            if pd.isna(v):
                r[k] = None
    return recs


def build_financial_profiles_from_tables(tables_dir: Path) -> List[Dict[str, Any]]:
    households = pd.read_csv(tables_dir / "households.csv")
    people = pd.read_csv(tables_dir / "people.csv")
    income_lines = pd.read_csv(tables_dir / "income_lines.csv")
    assets = pd.read_csv(tables_dir / "assets.csv")
    liabilities = pd.read_csv(tables_dir / "liabilities.csv")
    policies_path = tables_dir / "protection_policies.csv"
    protection_policies = pd.read_csv(policies_path) if policies_path.exists() else pd.DataFrame()

    profiles: List[Dict[str, Any]] = []

    for _, hh in households.iterrows():
        household_id = str(hh["household_id"])
        hh_obj = hh.to_dict()
        for k, v in list(hh_obj.items()):
            if pd.isna(v):
                hh_obj[k] = None

        prof = {
            "household_id": household_id,
            "households": hh_obj,
            "people": _records(people[people["household_id"].astype(str) == household_id]),
            "income_lines": _records(income_lines[income_lines["household_id"].astype(str) == household_id]),
            "assets": _records(assets[assets["household_id"].astype(str) == household_id]),
            "liabilities": _records(liabilities[liabilities["household_id"].astype(str) == household_id]),
            "protection_policies": _records(
                protection_policies[protection_policies["household_id"].astype(str) == household_id]
            )
            if not protection_policies.empty
            else [],
        }
        profiles.append(prof)

    return profiles


def save_financial_profiles_json(profiles: List[Dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(profiles, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

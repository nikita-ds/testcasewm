from __future__ import annotations

import json
from pathlib import Path
from typing import Set

from schema_spec import EntitySpec


def default_exclusions_path() -> Path:
    return Path(__file__).resolve().parent / "config" / "scoring_exclusions.json"


def load_exclusions(path: Path) -> Set[str]:
    if not path.exists():
        return set()
    obj = json.loads(path.read_text(encoding="utf-8"))
    raw = obj.get("exclude_field_paths")
    if not isinstance(raw, list):
        return set()
    out: Set[str] = set()
    for x in raw:
        s = str(x).strip()
        if s:
            out.add(s)
    return out


def should_score_field(*, entity: EntitySpec, field_name: str, include_ids: bool, exclusions: Set[str]) -> bool:
    # Exclude derived relationship metrics from scoring by default.
    if field_name.endswith("_ratio"):
        return False

    if not include_ids:
        if field_name == entity.primary_key:
            return False
        if field_name.endswith("_id"):
            return False

    field_path = f"{entity.name}.{field_name}"
    if field_path in exclusions:
        return False

    return True

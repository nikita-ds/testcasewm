from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List


RULES_PATH = Path(__file__).resolve().parent / "normalization_rules.json"


@lru_cache(maxsize=1)
def load_normalization_rules() -> Dict[str, Any]:
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def state_like_field_suffixes() -> List[str]:
    raw = load_normalization_rules().get("state_like_field_suffixes") or []
    return [str(x).strip() for x in raw if str(x).strip()]


def is_state_like_field(field_path: str) -> bool:
    path = str(field_path or "").strip()
    return any(path.endswith(suffix) for suffix in state_like_field_suffixes())


def state_variants(value: Any, stringify) -> List[str]:
    s = stringify(value).strip()
    if not s:
        return []

    rules = load_normalization_rules()
    name_to_code_raw = rules.get("us_state_name_to_code") or {}
    name_to_code = {str(k).strip().lower(): str(v).strip().upper() for k, v in name_to_code_raw.items()}
    code_to_name = {code: name.title() for name, code in name_to_code.items()}

    key = s.lower()
    code = None
    name = None
    if len(s) == 2 and s.upper() in code_to_name:
        code = s.upper()
        name = code_to_name[code]
    elif key in name_to_code:
        code = name_to_code[key]
        name = code_to_name[code]

    if not code:
        return [s]
    return [s, code, code.lower(), name, name.lower()]

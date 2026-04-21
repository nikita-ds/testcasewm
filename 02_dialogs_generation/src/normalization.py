from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional


RULES_PATH = Path(__file__).resolve().parents[1] / "normalization_rules.json"


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


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _norm_key(s: str) -> str:
    """Normalize a free-form text key for alias matching."""

    t = str(s or "").strip().lower()
    if not t:
        return ""
    # Drop parentheticals like "RIA (registered ...)" -> "RIA".
    t = re.sub(r"\([^)]*\)", " ", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    t = " ".join(t.split())
    return t


def _snakeish(s: str) -> str:
    """Convert value to a snake-ish token (spaces/dashes/slashes -> '_')."""

    t = str(s or "").strip().lower()
    if not t:
        return ""
    # Drop parentheticals.
    t = re.sub(r"\([^)]*\)", " ", t)
    # Normalize separators.
    t = t.replace("/", " ")
    t = re.sub(r"[^a-z0-9]+", "_", t)
    t = re.sub(r"_+", "_", t).strip("_")
    return t


def categorical_aliases() -> Dict[str, Dict[str, str]]:
    raw = load_normalization_rules().get("categorical_aliases") or {}
    out: Dict[str, Dict[str, str]] = {}
    if not isinstance(raw, dict):
        return out
    for field_path, mapping in raw.items():
        if not isinstance(mapping, dict):
            continue
        fp = str(field_path).strip()
        if not fp:
            continue
        out[fp] = {str(k).strip().lower(): str(v) for k, v in mapping.items() if str(k).strip()}
    return out


def canonicalize_state(value: Any) -> Any:
    """Return canonical US state code when possible, else original-ish string."""

    s = _stringify(value).strip()
    if not s:
        return value

    rules = load_normalization_rules()
    name_to_code_raw = rules.get("us_state_name_to_code") or {}
    name_to_code = {str(k).strip().lower(): str(v).strip().upper() for k, v in name_to_code_raw.items()}

    if len(s) == 2 and s.upper() in set(name_to_code.values()):
        return s.upper()

    key = s.strip().lower()
    if key in name_to_code:
        return name_to_code[key]
    return s


def canonicalize_categorical(field_path: str, value: Any) -> Any:
    """Canonicalize categorical values using aliases + simple snakeish normalization.

    This is intentionally conservative: if no alias matches, return a snake-ish
    version (helps "retirement platform" vs "retirement_platform").
    """

    fp = str(field_path or "").strip()
    if value is None:
        return None
    if isinstance(value, list):
        return [canonicalize_categorical(fp, v) for v in value]

    s = _stringify(value).strip()
    if not s:
        return ""

    if is_state_like_field(fp):
        return canonicalize_state(s)

    aliases = categorical_aliases().get(fp) or {}
    k1 = _norm_key(s)
    if k1 and k1 in aliases:
        return aliases[k1]

    k2 = _snakeish(s)
    if k2 and k2 in aliases:
        return aliases[k2]

    # Fall back to snake-ish (keeps enums closer to schema style).
    return k2 or s


def canonicalize_multichoice(field_path: str, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, list):
        items = [canonicalize_categorical(field_path, v) for v in value]
        # de-dup while preserving order
        seen: set[str] = set()
        out: list[Any] = []
        for it in items:
            key = _stringify(it).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(it)
        return out
    # split string-ish
    s = _stringify(value)
    parts = [p.strip() for p in s.replace(",", "|").split("|") if p.strip()]
    return canonicalize_multichoice(field_path, parts)


def canonicalize_record_ids(*, entity: str, household_id: str, record: Dict[str, Any], primary_key: str) -> Dict[str, Any]:
    """Best-effort canonicalization of record primary keys.

    This improves record pairing during scoring by bringing common ID formats
    (e.g. AST_HH000018_1) back to the generator format (HH000018_A1).
    """

    out = dict(record)
    pk_val = out.get(primary_key)
    if not isinstance(pk_val, str) or not pk_val.strip():
        return out

    raw = pk_val.strip()
    raw_u = raw.replace("-", "_")

    hh = household_id.strip()
    if not hh:
        hh = ""

    def _m(m: Optional[re.Match[str]], fmt: str) -> Optional[str]:
        if not m:
            return None
        g = m.groupdict()
        return fmt.format(**g)

    canon: Optional[str] = None

    if entity == "assets":
        canon = _m(re.match(r"^AST_(?P<hh>HH\d+?)_(?P<n>\d+)$", raw_u), "{hh}_A{n}")
        canon = canon or _m(re.match(r"^(?P<hh>HH\d+?)_AST(?P<n>\d+)$", raw_u), "{hh}_A{n}")
        if not canon:
            m2 = re.match(r"^A(?P<n>\d+)$", raw_u)
            if m2 and hh:
                canon = f"{hh}_A{m2.group('n')}"
    elif entity == "income_lines":
        canon = _m(re.match(r"^INC_(?P<hh>HH\d+?)_(?P<n>\d+)$", raw_u), "{hh}_I{n}")
        canon = canon or _m(re.match(r"^(?P<hh>HH\d+?)_INC(?P<n>\d+)$", raw_u), "{hh}_I{n}")
        canon = canon or _m(re.match(r"^(?P<hh>HH\d+?)_INCOME(?P<n>\d+)$", raw_u), "{hh}_I{n}")
        if not canon:
            m2 = re.match(r"^(?:INC|I)(?P<n>\d+)$", raw_u)
            if m2 and hh:
                canon = f"{hh}_I{m2.group('n')}"
    elif entity == "people":
        canon = _m(re.match(r"^P_(?P<hh>HH\d+?)_(?P<n>\d+)$", raw_u), "{hh}_P{n}")
        canon = canon or _m(re.match(r"^(?P<hh>HH\d+?)_P(?P<n>\d+)$", raw_u), "{hh}_P{n}")
        if not canon:
            m2 = re.match(r"^P(?P<n>\d+)$", raw_u)
            if m2 and hh:
                canon = f"{hh}_P{m2.group('n')}"
    elif entity == "liabilities":
        canon = _m(re.match(r"^(?P<hh>HH\d+?)_L(?P<n>\d+)$", raw_u), "{hh}_L{n}")
        if not canon:
            m2 = re.match(r"^L(?P<n>\d+)$", raw_u)
            if m2 and hh:
                canon = f"{hh}_L{m2.group('n')}"
    elif entity == "protection_policies":
        canon = _m(re.match(r"^(?P<hh>HH\d+?)_POL(?P<n>\d+)$", raw_u), "{hh}_PP{n}")
        canon = canon or _m(re.match(r"^(?P<hh>HH\d+?)_POLICY(?P<n>\d+)$", raw_u), "{hh}_PP{n}")
        if not canon:
            m2 = re.match(r"^POL(?P<n>\d+)$", raw_u)
            if m2 and hh:
                canon = f"{hh}_PP{m2.group('n')}"
        if not canon:
            m3 = re.match(r"^PP(?P<n>\d+)$", raw_u)
            if m3 and hh:
                canon = f"{hh}_PP{m3.group('n')}"

    out[primary_key] = canon or raw_u
    return out

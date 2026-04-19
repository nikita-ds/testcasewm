from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from schema_spec import FieldSpec


_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def _to_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v)


def _parse_bool(v: Any) -> Optional[bool]:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in {"true", "t", "yes", "y", "1"}:
        return True
    if s in {"false", "f", "no", "n", "0"}:
        return False
    return None


def _parse_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    s = str(v)
    s = s.replace(",", "").strip()
    if s == "":
        return None
    try:
        return int(float(s))
    except Exception:
        return None


def _parse_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    # Handle percents "19.48%".
    if s.endswith("%"):
        s2 = s[:-1].strip()
        s2 = s2.replace(",", "")
        try:
            return float(s2)
        except Exception:
            return None
    s = s.replace(",", "")
    # Remove currency symbols.
    s = s.replace("$", "")
    try:
        return float(s)
    except Exception:
        return None


def _parse_date(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        m = _DATE_RE.search(s)
        if m:
            return m.group(1)
        return None
    s = str(v).strip()
    m = _DATE_RE.search(s)
    if m:
        return m.group(1)
    return None


@dataclass
class CoerceIssue:
    entity: str
    record_index: int
    field: str
    problem: str
    raw_value: Any


def coerce_record(
    *,
    entity: str,
    record_index: int,
    record: Dict[str, Any],
    fields: Dict[str, FieldSpec],
) -> Tuple[Dict[str, Any], List[CoerceIssue]]:
    out: Dict[str, Any] = {}
    issues: List[CoerceIssue] = []

    for k, raw in (record or {}).items():
        if k not in fields:
            continue
        spec = fields[k]
        t = str(spec.type)

        if t in {"string", "string_fk", "categorical"}:
            if raw is None:
                # Keep missing as missing (do not inject placeholder here).
                continue
            out[k] = _to_str(raw)
            continue

        if t == "multichoice":
            if raw is None:
                continue
            if isinstance(raw, list):
                out[k] = [str(x) for x in raw if str(x).strip()]
            else:
                s = _to_str(raw).strip()
                out[k] = [x.strip() for x in s.split(",") if x.strip()] if s else []
            continue

        if t == "boolean":
            b = _parse_bool(raw)
            if b is None:
                issues.append(CoerceIssue(entity, record_index, k, "invalid_boolean", raw))
                continue
            out[k] = b
            continue

        if t in {"integer", "integer_nullable"}:
            iv = _parse_int(raw)
            if iv is None:
                issues.append(CoerceIssue(entity, record_index, k, "invalid_integer", raw))
                continue
            out[k] = iv
            continue

        if t == "continuous":
            fv = _parse_float(raw)
            if fv is None:
                issues.append(CoerceIssue(entity, record_index, k, "invalid_number", raw))
                continue
            out[k] = fv
            continue

        if t in {"date", "date_nullable"}:
            dv = _parse_date(raw)
            if dv is None:
                issues.append(CoerceIssue(entity, record_index, k, "invalid_date", raw))
                continue
            out[k] = dv
            continue

        if t == "string_nullable":
            if raw is None:
                continue
            out[k] = _to_str(raw)
            continue

        # Unknown type: preserve as string.
        if raw is not None:
            out[k] = _to_str(raw)

    return out, issues


def compute_derived_household_fields(
    hh: Dict[str, Any],
    liabilities: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Compute a small set of derived fields if inputs are present.

    This is grounded in extracted values (not ground truth).
    """

    out = dict(hh or {})
    inc = out.get("annual_household_gross_income")
    exp_m = out.get("monthly_expenses_total")
    mort_pay_m = out.get("monthly_mortgage_payment_total")
    debt_total_m = out.get("monthly_debt_cost_total")
    has_loan = out.get("has_mortgage_or_loan")

    try:
        inc_f = float(inc) if inc is not None else None
    except Exception:
        inc_f = None
    try:
        exp_f = float(exp_m) if exp_m is not None else None
    except Exception:
        exp_f = None
    try:
        mort_f = float(mort_pay_m) if mort_pay_m is not None else None
    except Exception:
        mort_f = None
    try:
        debt_total_f = float(debt_total_m) if debt_total_m is not None else None
    except Exception:
        debt_total_f = None

    liabilities = [r for r in (liabilities or []) if isinstance(r, dict)]
    derived_debt_total = 0.0
    derived_mortgage_total = 0.0
    saw_any_liability = bool(liabilities)
    saw_liability_cost = False
    saw_mortgage = False

    for liab in liabilities:
        monthly_cost = _parse_float(liab.get("monthly_cost"))
        liab_type = str(liab.get("type") or "").strip().lower()
        is_mortgage = liab_type == "mortgage"

        if monthly_cost is not None:
            saw_liability_cost = True
            derived_debt_total += float(monthly_cost)
            if is_mortgage:
                derived_mortgage_total += float(monthly_cost)

        if is_mortgage:
            saw_mortgage = True

    if debt_total_f is None and (saw_liability_cost or saw_any_liability or has_loan is False):
        out["monthly_debt_cost_total"] = float(derived_debt_total)

    if mort_f is None and (saw_mortgage or saw_any_liability or has_loan is False):
        out["monthly_mortgage_payment_total"] = float(derived_mortgage_total)
        mort_f = float(derived_mortgage_total)

    if has_loan is None and saw_any_liability:
        out["has_mortgage_or_loan"] = saw_liability_cost or saw_mortgage

    if inc_f and exp_f is not None:
        out.setdefault("expense_to_income_ratio", float((exp_f * 12.0) / inc_f))

    if inc_f and mort_f is not None:
        out.setdefault("mortgage_payment_to_income_ratio", float((mort_f * 12.0) / inc_f))

    if isinstance(has_loan, bool):
        out["has_mortgage_or_loan"] = has_loan

    return out

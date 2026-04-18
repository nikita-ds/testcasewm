from __future__ import annotations

from typing import Any


def _round_to_increment(value: float, increment: float) -> float:
    if increment <= 0:
        return value
    return round(value / increment) * increment


def is_money_field_name(name: str) -> bool:
    n = str(name).strip().lower()
    if not n:
        return False

    # Exclusions: numeric but not money.
    if any(x in n for x in [
        "interest_rate",
        "rate",
        "apr",
        "percent",
        "pct",
        "bracket",
        "client_no",
        "num_",
        "_count",
        "years",
        "year",
        "age",
        "date",
        "id",
    ]):
        return False

    money_keywords = [
        "income",
        "expense",
        "expenses",
        "spend",
        "cost",
        "payment",
        "premium",
        "amount",
        "balance",
        "value",
        "assets",
        "asset",
        "liability",
        "debt",
        "mortgage",
        "loan",
        "outstanding",
        "rent",
        "savings",
        "saving",
        "contribution",
        "withdrawal",
    ]
    return any(k in n for k in money_keywords)


def is_money_field_path(field_path: str) -> bool:
    # field_path is like: households.annual_household_gross_income
    # or assets[asset_id=...].value
    return is_money_field_name(field_path)


def round_money_value(value: Any, *, increment: float = 50.0) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        rounded = _round_to_increment(float(value), float(increment))
        # Prefer integer representation for whole-dollar amounts.
        if abs(rounded - round(rounded)) < 1e-9:
            return int(round(rounded))
        return float(rounded)
    return value


def format_usd_rounded(value: Any, *, increment: float = 50.0) -> str:
    try:
        v = float(value)
    except Exception:
        return "unknown"

    v = float(_round_to_increment(v, float(increment)))

    # Avoid -0.0
    if abs(v) < 1e-9:
        v = 0.0

    sign = "-" if v < 0 else ""
    v = abs(v)

    if v >= 1_000_000:
        return f"{sign}${v/1_000_000:.2f}M"

    # Whole dollars with commas; no cents.
    return f"{sign}${int(round(v)): ,}".replace(" ", "")


def round_money_in_obj(obj: Any, *, increment: float = 50.0) -> Any:
    """Recursively round money-like numeric fields for prompt display.

    - Uses dict keys (and `field_path` when present) to detect money-ish values.
    - Leaves IDs, counts, rates, dates untouched.
    """

    if isinstance(obj, dict):
        field_path = obj.get("field_path") if isinstance(obj.get("field_path"), str) else None
        out: dict[Any, Any] = {}
        for k, v in obj.items():
            if k == "source_value" and field_path is not None and is_money_field_path(field_path):
                # Only round numeric values; otherwise recurse.
                out[k] = round_money_value(v, increment=increment) if isinstance(v, (int, float)) and not isinstance(v, bool) else round_money_in_obj(v, increment=increment)
                continue
            if isinstance(k, str) and is_money_field_name(k):
                # If the value is numeric, round it. If it's a container (list/dict),
                # keep recursing so nested money fields don't get skipped.
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    out[k] = round_money_value(v, increment=increment)
                else:
                    out[k] = round_money_in_obj(v, increment=increment)
                continue
            out[k] = round_money_in_obj(v, increment=increment)
        return out

    if isinstance(obj, list):
        return [round_money_in_obj(v, increment=increment) for v in obj]

    return obj

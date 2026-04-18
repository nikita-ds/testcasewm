from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from money_rounding import format_usd_rounded, is_money_field_name


@dataclass(frozen=True)
class RecordIds:
    household_id: str
    person_ids: List[str]
    income_line_ids: List[str]
    asset_ids: List[str]
    liability_ids: List[str]
    policy_ids: List[str]


def extract_record_ids(profile: Dict[str, Any]) -> RecordIds:
    hh = profile.get("households") or {}
    household_id = str(profile.get("household_id") or hh.get("household_id") or "")

    def _ids(rows: Any, key: str) -> List[str]:
        out: List[str] = []
        for r in (rows or []):
            if isinstance(r, dict) and r.get(key) is not None:
                out.append(str(r[key]))
        return out

    return RecordIds(
        household_id=household_id,
        person_ids=_ids(profile.get("people"), "person_id"),
        income_line_ids=_ids(profile.get("income_lines"), "income_line_id"),
        asset_ids=_ids(profile.get("assets"), "asset_id"),
        liability_ids=_ids(profile.get("liabilities"), "liability_id"),
        policy_ids=_ids(profile.get("protection_policies"), "policy_id"),
    )


def build_profile_digest(profile: Dict[str, Any]) -> str:
    """Compact, human-readable summary to force coverage across tables.

    This is used in prompts to reduce token load and to make it explicit
    what records must be discussed.
    """

    hh = profile.get("households") or {}
    household_id = str(profile.get("household_id") or hh.get("household_id") or "")

    def _money(x: Any) -> str:
        # People typically don't remember cents; keep prompts realistic.
        return format_usd_rounded(x, increment=50.0)

    lines: List[str] = []
    lines.append(f"HOUSEHOLD_ID: {household_id}")
    if hh:
        lines.append(
            "HOUSEHOLDS SUMMARY: "
            + ", ".join(
                [
                    f"scenario={hh.get('scenario')}",
                    f"income={_money(hh.get('annual_household_gross_income'))}/yr",
                    f"expenses={_money(hh.get('monthly_expenses_total'))}/mo",
                    f"investable_assets={_money(hh.get('investable_assets_total'))}",
                    f"property_value={_money(hh.get('property_value_total'))}",
                    f"loan_outstanding={_money(hh.get('loan_outstanding_total'))}",
                    f"risk_tolerance={hh.get('risk_tolerance')}",
                    f"tax_bracket={hh.get('tax_bracket_band')}",
                ]
            )
        )

    def _fmt_rows(title: str, rows: List[Dict[str, Any]], cols: List[str]) -> None:
        lines.append(f"{title} (count={len(rows)}):")
        for r in rows:
            parts = []
            for c in cols:
                if c not in r:
                    continue
                val = r.get(c)
                if val is None or val == "":
                    continue
                if is_money_field_name(c):
                    parts.append(f"{c}={_money(val)}")
                else:
                    parts.append(f"{c}={val}")
            rid = r.get(cols[0]) if cols else None
            rid_prefix = f"- {rid}: " if rid is not None else "- "
            lines.append(rid_prefix + ", ".join(parts))

    people = [r for r in (profile.get("people") or []) if isinstance(r, dict)]
    income_lines = [r for r in (profile.get("income_lines") or []) if isinstance(r, dict)]
    assets = [r for r in (profile.get("assets") or []) if isinstance(r, dict)]
    liabilities = [r for r in (profile.get("liabilities") or []) if isinstance(r, dict)]
    policies = [r for r in (profile.get("protection_policies") or []) if isinstance(r, dict)]

    _fmt_rows(
        "PEOPLE",
        people,
        ["person_id", "role", "client_no", "employment_status", "gross_annual_income", "date_of_birth"],
    )
    _fmt_rows(
        "INCOME_LINES",
        income_lines,
        ["income_line_id", "owner", "source_type", "frequency", "amount_annualized"],
    )
    _fmt_rows(
        "ASSETS",
        assets,
        ["asset_id", "owner", "asset_type", "subtype", "provider_type", "value"],
    )
    _fmt_rows(
        "LIABILITIES",
        liabilities,
        ["liability_id", "type", "interest_rate", "monthly_cost", "outstanding", "final_payment_date"],
    )
    _fmt_rows(
        "PROTECTION_POLICIES",
        policies,
        ["policy_id", "owner", "policy_type", "monthly_cost", "amount_assured", "assured_until"],
    )

    lines.append("\nCOVERAGE REQUIREMENT:")
    lines.append("- The conversation must explicitly discuss EVERY record listed above at least once.")
    lines.append("- The advisor should summarize each category (income, assets, liabilities, protection).")

    return "\n".join(lines).strip() + "\n"

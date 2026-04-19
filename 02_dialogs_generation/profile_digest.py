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

    def _humanize_token(v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, bool):
            return "yes" if v else "no"
        s = str(v).strip()
        if not s:
            return ""

        low = s.lower()
        # Owner keys.
        if low in {"client_1", "client_2"}:
            return "Client 1" if low.endswith("_1") else "Client 2"

        # Common enums.
        if low == "married_or_civil_partner":
            return "married"
        if low == "spouse_partner":
            return "spouse/partner"
        if low == "us_ria":
            return "RIA (registered investment advisor)"
        if low == "advisor_platform":
            return "advisor platform"
        if low == "primary_residence":
            return "primary residence"
        if low == "interest_dividends":
            return "interest & dividends"
        if low == "pension_income":
            return "pension"
        if low == "private_markets":
            return "private markets"

        # Generic underscore tokens (avoid leaking snake_case into the dialogue prompts).
        if "_" in s:
            return s.replace("_", " ")

        # ALLCAPS enum tokens like US / etc.
        if s.isupper() and len(s) <= 12:
            return s

        return s

    def _money(x: Any) -> str:
        # People typically don't remember cents; keep prompts realistic.
        return format_usd_rounded(x, increment=50.0)

    lines: List[str] = []
    # Keep the digest human-oriented; record IDs are handled separately in valid_record_ids_json.
    if hh:
        lines.append(
            "HOUSEHOLDS SUMMARY: "
            + ", ".join(
                [
                    f"Scenario: {_humanize_token(hh.get('scenario'))}",
                    f"Gross income: {_money(hh.get('annual_household_gross_income'))}/yr",
                    f"Monthly expenses: {_money(hh.get('monthly_expenses_total'))}/mo",
                    f"Investable assets: {_money(hh.get('investable_assets_total'))}",
                    f"Property value: {_money(hh.get('property_value_total'))}",
                    f"Loans outstanding: {_money(hh.get('loan_outstanding_total'))}",
                    f"Risk tolerance: {_humanize_token(hh.get('risk_tolerance'))}",
                    f"Tax bracket band: {_humanize_token(hh.get('tax_bracket_band'))}",
                ]
            )
        )

    def _fmt_rows(title: str, rows: List[Dict[str, Any]], cols: List[str], *, labels: Dict[str, str]) -> None:
        lines.append(f"{title} (count={len(rows)}):")
        for r in rows:
            parts = []
            for c in cols:
                if c not in r:
                    continue
                val = r.get(c)
                if val is None or val == "":
                    continue
                label = labels.get(c) or c
                if is_money_field_name(c):
                    parts.append(f"{label}: {_money(val)}")
                else:
                    parts.append(f"{label}: {_humanize_token(val)}")
            # Do not include raw internal record IDs in the digest; they are provided separately.
            lines.append("- " + ", ".join(parts))

    people = [r for r in (profile.get("people") or []) if isinstance(r, dict)]
    income_lines = [r for r in (profile.get("income_lines") or []) if isinstance(r, dict)]
    assets = [r for r in (profile.get("assets") or []) if isinstance(r, dict)]
    liabilities = [r for r in (profile.get("liabilities") or []) if isinstance(r, dict)]
    policies = [r for r in (profile.get("protection_policies") or []) if isinstance(r, dict)]

    _fmt_rows(
        "PEOPLE",
        people,
        ["person_id", "role", "client_no", "employment_status", "gross_annual_income"],
        labels={
            "person_id": "ID",
            "role": "Role",
            "client_no": "Client label",
            "employment_status": "Employment",
            "gross_annual_income": "Gross income (annual)",
        },
    )
    _fmt_rows(
        "INCOME_LINES",
        income_lines,
        ["income_line_id", "owner", "source_type", "frequency", "amount_annualized"],
        labels={
            "income_line_id": "ID",
            "owner": "Whose",
            "source_type": "Income type",
            "frequency": "Frequency",
            "amount_annualized": "Amount (annual)",
        },
    )
    _fmt_rows(
        "ASSETS",
        assets,
        ["asset_id", "owner", "asset_type", "subtype", "provider_type", "provider", "value"],
        labels={
            "asset_id": "ID",
            "owner": "Owner",
            "asset_type": "Account type",
            "subtype": "Subtype",
            "provider_type": "Held at (kind)",
            "provider": "Held at",
            "value": "Value",
        },
    )
    _fmt_rows(
        "LIABILITIES",
        liabilities,
        ["liability_id", "type", "interest_rate", "monthly_cost", "outstanding", "final_payment_date"],
        labels={
            "liability_id": "ID",
            "type": "Debt type",
            "interest_rate": "Interest rate",
            "monthly_cost": "Monthly payment/cost",
            "outstanding": "Balance outstanding",
            "final_payment_date": "Final payment date",
        },
    )
    _fmt_rows(
        "PROTECTION_POLICIES",
        policies,
        ["policy_id", "owner", "policy_type", "monthly_cost", "amount_assured", "assured_until"],
        labels={
            "policy_id": "ID",
            "owner": "Whose",
            "policy_type": "Policy type",
            "monthly_cost": "Monthly premium",
            "amount_assured": "Coverage amount",
            "assured_until": "Covered until",
        },
    )

    lines.append("\nCOVERAGE REQUIREMENT:")
    lines.append("- The conversation must explicitly discuss EVERY record listed above at least once.")
    lines.append("- The advisor should summarize each category (income, assets, liabilities, protection).")

    return "\n".join(lines).strip() + "\n"

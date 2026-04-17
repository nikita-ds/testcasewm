from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "config"
ART = ROOT / "artifacts"
ART.mkdir(parents=True, exist_ok=True)

def main():
    cfg = json.loads((CFG / "priors_assumptions.json").read_text(encoding="utf-8"))
    anchors = cfg["official_anchors"]

    public_income_median = anchors["census_median_household_income_2023"]
    public_wealth_median = anchors["sipp_median_household_wealth_2023"]
    affluent_floor = 2.0 * public_income_median

    priors = {
        "meta": {
            "snapshot_date": "2026-04-17",
            "market": "US_RIA",
            "country": "US",
            "public_income_median_2023": public_income_median,
            "public_wealth_median_2023": public_wealth_median,
            "affluent_income_floor": affluent_floor,
        },
        "continuous_targets": {
            "annual_household_gross_income": {
                "p10": affluent_floor,
                "median": 240000.0,
                "p90": 650000.0
            },
            "investable_assets_total": {
                "p10": 120000.0,
                "median": 850000.0,
                "p90": 4500000.0
            },
            "net_worth_proxy": {
                "p10": 180000.0,
                "median": 1450000.0,
                "p90": 6500000.0
            },
            "expense_to_income_ratio": {
                "mean": 0.52,
                "std": 0.12,
                "min": 0.22,
                "max": 0.98
            }
        },
        "categoricals": {
            "marital_status": {
                "married_or_civil_partner": 0.52,
                "cohabiting": 0.10,
                "single": 0.12,
                "divorced": 0.10,
                "widowed": 0.07,
                "secondly_wedded": 0.09
            },
            "risk_tolerance": {
                "conservative": 0.16,
                "moderate": 0.38,
                "growth": 0.31,
                "aggressive": 0.15
            },
            "tax_bracket_band": {
                "24%": 0.10,
                "32%": 0.26,
                "35%": 0.42,
                "37%": 0.22
            },
            "employment_status_primary": {
                "employed": 0.61,
                "self_employed": 0.14,
                "retired": 0.17,
                "inactive": 0.05,
                "unemployed": 0.03
            },
            "residence_state": {
                "CA": 0.17, "NY": 0.10, "TX": 0.09, "FL": 0.10, "IL": 0.06,
                "WA": 0.07, "MA": 0.08, "NJ": 0.09, "PA": 0.08, "NC": 0.06, "Other": 0.10
            }
        },
        "booleans": {
            "has_mortgage_or_loan": 0.59,
            "has_brokerage": 0.83,
            "has_retirement_accounts": 0.78,
            "has_alimony": 0.06,
            "has_children": 0.41,
            "has_protection_policy": 0.55
        },
        "date_rules": {
            "min_parent_age_at_birth": 16,
            "move_in_after_age": 18,
            "employment_start_after_age": 16,
            "retirement_age_range": [55, 75],
            "loan_term_years_range": [2, 35]
        },
        "scenario_catalog": cfg["scenario_catalog"]
    }

    (ART / "computed_priors.json").write_text(json.dumps(priors, indent=2), encoding="utf-8")
    print("Wrote", ART / "computed_priors.json")

if __name__ == "__main__":
    main()

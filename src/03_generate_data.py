from __future__ import annotations
import argparse, json, math
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "artifacts"
OUT = ROOT / "artifacts" / "generated"
OUT.mkdir(parents=True, exist_ok=True)

def parse_date(s: str) -> date:
    return date.fromisoformat(s)

def years_ago(ref: date, years: float) -> date:
    return ref - timedelta(days=int(years * 365.25))

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def sample_cat(prob_map, rng):
    keys = list(prob_map.keys())
    probs = np.array(list(prob_map.values()), dtype=float)
    probs = probs / probs.sum()
    return str(rng.choice(keys, p=probs))

def fit_lognormal_from_p10_p90(x10, x90):
    from statistics import NormalDist
    z10 = NormalDist().inv_cdf(0.1)
    z90 = NormalDist().inv_cdf(0.9)
    sigma = (math.log(x90) - math.log(x10)) / (z90 - z10)
    mu = math.log(x10) - sigma * z10
    return mu, sigma

def sample_lognormal(x10, x90, rng):
    mu, sigma = fit_lognormal_from_p10_p90(x10, x90)
    return float(rng.lognormal(mu, sigma))

def sample_multichoice(rng, universe, max_k=3):
    k = int(rng.integers(1, max_k + 1))
    idx = rng.choice(len(universe), size=k, replace=False)
    return "|".join(sorted(universe[i] for i in idx))

SCENARIOS = [
    "young_dual_income_low_assets",
    "family_with_mortgage_and_children",
    "affluent_couple_brokerage_and_pensions",
    "one_high_earner_one_low_earner",
    "pre_retirement_wealthy",
    "self_employed_business_owner",
    "retired_couple_high_assets_low_income",
    "financially_stressed_with_debt",
    "widowed",
    "divorced",
    "secondly_wedded_paying_alimony",
]

def scenario_weights():
    return np.array([0.08,0.18,0.15,0.10,0.11,0.08,0.08,0.08,0.04,0.05,0.05], dtype=float)

def scenario_profile(s: str):
    return {
        "young_dual_income_low_assets": {"age1": (25,34), "couple": True, "kids": False, "income_mult": 0.85, "wealth_mult": 0.25},
        "family_with_mortgage_and_children": {"age1": (32,48), "couple": True, "kids": True, "income_mult": 1.0, "wealth_mult": 0.9},
        "affluent_couple_brokerage_and_pensions": {"age1": (40,62), "couple": True, "kids": "maybe", "income_mult": 1.35, "wealth_mult": 1.7},
        "one_high_earner_one_low_earner": {"age1": (35,55), "couple": True, "kids": "maybe", "income_mult": 1.15, "wealth_mult": 1.1},
        "pre_retirement_wealthy": {"age1": (55,66), "couple": True, "kids": False, "income_mult": 1.0, "wealth_mult": 2.2},
        "self_employed_business_owner": {"age1": (35,60), "couple": "maybe", "kids": "maybe", "income_mult": 1.2, "wealth_mult": 1.4},
        "retired_couple_high_assets_low_income": {"age1": (67,82), "couple": True, "kids": False, "income_mult": 0.42, "wealth_mult": 2.0},
        "financially_stressed_with_debt": {"age1": (30,52), "couple": "maybe", "kids": "maybe", "income_mult": 0.95, "wealth_mult": 0.35},
        "widowed": {"age1": (58,85), "couple": False, "kids": "maybe", "income_mult": 0.55, "wealth_mult": 1.15},
        "divorced": {"age1": (35,65), "couple": False, "kids": "maybe", "income_mult": 0.9, "wealth_mult": 0.75},
        "secondly_wedded_paying_alimony": {"age1": (40,68), "couple": True, "kids": "maybe", "income_mult": 1.1, "wealth_mult": 1.0},
    }[s]

@dataclass
class Ctx:
    priors: Dict
    snapshot: date
    rng: np.random.Generator

def employment_status(age, rng, scenario, is_primary=True):
    if scenario == "retired_couple_high_assets_low_income" or age >= 68:
        return "retired"
    if scenario == "self_employed_business_owner" and is_primary:
        return "self_employed"
    if age < 23:
        return "employed" if rng.random() < 0.65 else "inactive"
    return sample_cat({
        "employed": 0.67,
        "self_employed": 0.12 if is_primary else 0.08,
        "retired": 0.05,
        "inactive": 0.12 if is_primary else 0.19,
        "unemployed": 0.04
    }, rng)

def employment_started(dob, age, status, snap, rng):
    if status == "inactive" and age < 35 and rng.random() < 0.7:
        return None
    if status == "retired":
        years = rng.uniform(max(18, age - 45), max(20, age - 22))
    else:
        years = rng.uniform(max(0.5, age - 28), max(1.0, age - 18))
    d = years_ago(snap, years)
    min_allowed = dob + timedelta(days=int(16 * 365.25))
    return max(d, min_allowed)

def gen_one(hidx: int, ctx: Ctx):
    pri = ctx.priors
    rng = ctx.rng
    snap = ctx.snapshot

    scenario = str(rng.choice(SCENARIOS, p=scenario_weights()/scenario_weights().sum()))
    sp = scenario_profile(scenario)

    age1 = int(rng.integers(sp["age1"][0], sp["age1"][1] + 1))
    if sp["couple"] is True:
        has_second = True
    elif sp["couple"] is False:
        has_second = False
    else:
        has_second = bool(rng.random() < 0.55)

    marital_map = {"widowed":"widowed", "divorced":"divorced", "secondly_wedded_paying_alimony":"secondly_wedded"}
    marital_status = marital_map.get(scenario, "married_or_civil_partner" if has_second else "single")

    age2 = int(clamp(age1 + rng.integers(-10, 11), 18, 90)) if has_second else None

    dob1 = years_ago(snap, age1 + rng.uniform(-0.49, 0.49))
    dob2 = years_ago(snap, age2 + rng.uniform(-0.49, 0.49)) if age2 is not None else None

    st1 = employment_status(age1, rng, scenario, True)
    st2 = employment_status(age2, rng, scenario, False) if age2 is not None else None

    es1 = employment_started(dob1, age1, st1, snap, rng)
    es2 = employment_started(dob2, age2, st2, snap, rng) if dob2 is not None else None

    move_in = max(years_ago(snap, rng.uniform(0.5, max(1.0, min(age1 - 18, 25)))), dob1 + timedelta(days=int(18 * 365.25)))

    has_children = sp["kids"] is True or (sp["kids"] == "maybe" and rng.random() < pri["booleans"]["has_children"])
    child_dobs = []
    if has_children:
        n_children = int(min(5, rng.poisson(1.4) + 1))
        youngest_parent_age = min(age1, age2 if age2 is not None else age1)
        max_child_age = max(0, min(24, youngest_parent_age - pri["date_rules"]["min_parent_age_at_birth"]))
        for _ in range(n_children):
            c_age = rng.uniform(0, max(1, max_child_age))
            c_dob = years_ago(snap, c_age)
            if c_dob > dob1 + timedelta(days=int(16 * 365.25)):
                child_dobs.append(c_dob)
        child_dobs = sorted(child_dobs)

    income_p = pri["continuous_targets"]["annual_household_gross_income"]
    hh_income = sample_lognormal(income_p["p10"], income_p["p90"], rng) * sp["income_mult"]
    hh_income = max(income_p["p10"], hh_income)

    if scenario == "one_high_earner_one_low_earner" and has_second:
        inc1 = hh_income * rng.uniform(0.72, 0.88)
        inc2 = hh_income - inc1
    elif has_second:
        share2 = rng.uniform(0.20, 0.48)
        inc2 = hh_income * share2
        inc1 = hh_income - inc2
    else:
        inc1, inc2 = hh_income, 0.0

    nw_p = pri["continuous_targets"]["net_worth_proxy"]
    nw = sample_lognormal(nw_p["p10"], nw_p["p90"], rng) * sp["wealth_mult"]
    nw = max(10000.0, nw)

    invest_p = pri["continuous_targets"]["investable_assets_total"]
    investable = min(nw * rng.uniform(0.25, 0.75), sample_lognormal(invest_p["p10"], invest_p["p90"], rng) * sp["wealth_mult"])
    investable = max(0.0, investable)

    retirement_assets = max(0.0, investable * rng.uniform(0.18, 0.42))
    cash_total = max(0.0, investable * rng.uniform(0.05, 0.18))
    alternatives_total = max(0.0, investable * rng.uniform(0.0, 0.15) if nw > 1_500_000 else 0.0)
    prop_val = max(0.0, nw * rng.uniform(0.20, 0.55))

    if scenario == "young_dual_income_low_assets":
        investable *= 0.35; retirement_assets *= 0.45; prop_val *= 0.5; cash_total *= 0.6
    if scenario == "retired_couple_high_assets_low_income":
        investable *= 1.2; retirement_assets *= 1.3
    if scenario == "financially_stressed_with_debt":
        investable *= 0.18; retirement_assets *= 0.25; prop_val *= 0.75; cash_total *= 0.5

    has_loan = scenario in {"family_with_mortgage_and_children","financially_stressed_with_debt"} or bool(rng.random() < pri["booleans"]["has_mortgage_or_loan"])
    loan_outstanding = 0.0
    debt_cost = 0.0
    rate = 0.0
    final_payment = None
    if has_loan:
        loan_outstanding = max(5000.0, prop_val * rng.uniform(0.15, 0.82))
        if scenario == "financially_stressed_with_debt":
            loan_outstanding *= 1.2
        rate = float(clamp(rng.normal(5.0, 1.2), 2.5, 11.0))
        years_remaining = rng.uniform(2, 35)
        final_payment = snap + timedelta(days=int(years_remaining * 365.25))
        debt_cost = loan_outstanding * (rate / 100) / 12 + loan_outstanding / (years_remaining * 12)

    e = pri["continuous_targets"]["expense_to_income_ratio"]
    exp_ratio = float(clamp(rng.normal(e["mean"], e["std"]), e["min"], e["max"]))
    if scenario == "financially_stressed_with_debt":
        exp_ratio = float(clamp(rng.normal(0.92, 0.05), 0.75, 1.1))
    monthly_exp = hh_income / 12 * exp_ratio

    alimony = 0.0
    if scenario == "secondly_wedded_paying_alimony":
        alimony = float(rng.uniform(12000, 72000))
    elif scenario == "divorced" and rng.random() < 0.20:
        alimony = float(rng.uniform(6000, 30000))

    risk = sample_cat(pri["categoricals"]["risk_tolerance"], rng)
    if scenario in {"pre_retirement_wealthy","retired_couple_high_assets_low_income"} and rng.random() < 0.45:
        risk = "moderate"
    if scenario == "young_dual_income_low_assets" and rng.random() < 0.35:
        risk = "growth"

    objectives_universe = ["retirement","wealth_growth","income","education","tax_optimization","estate_planning","capital_preservation"]
    objectives = sample_multichoice(rng, objectives_universe, max_k=3)
    tax_bracket = sample_cat(pri["categoricals"]["tax_bracket_band"], rng)

    hh_id = f"HH{hidx:06d}"
    household = {
        "household_id": hh_id,
        "scenario": scenario,
        "country": "US",
        "market": "US_RIA",
        "marital_status": marital_status,
        "residence_state": sample_cat(pri["categoricals"]["residence_state"], rng),
        "move_in_date": move_in.isoformat(),
        "num_adults": 2 if has_second else 1,
        "num_dependants": len(child_dobs),
        "youngest_child_dob": child_dobs[-1].isoformat() if child_dobs else None,
        "oldest_child_dob": child_dobs[0].isoformat() if child_dobs else None,
        "annual_household_gross_income": round(hh_income, 2),
        "monthly_expenses_total": round(monthly_exp, 2),
        "expense_to_income_ratio": round(exp_ratio, 4),
        "annual_alimony_paid": round(alimony, 2),
        "has_mortgage_or_loan": bool(has_loan),
        "loan_outstanding_total": round(loan_outstanding, 2),
        "monthly_debt_cost_total": round(debt_cost, 2),
        "property_value_total": round(prop_val, 2),
        "investable_assets_total": round(investable, 2),
        "retirement_assets_total": round(retirement_assets, 2),
        "cash_and_cashlike_total": round(cash_total, 2),
        "alternatives_total": round(alternatives_total, 2),
        "net_worth_proxy": round(nw, 2),
        "risk_tolerance": risk,
        "investment_objectives": objectives,
        "tax_bracket_band": tax_bracket,
        "client_segment": "affluent_ria_like"
    }

    people = [{
        "person_id": f"{hh_id}_P1",
        "household_id": hh_id,
        "client_no": 1,
        "role": "primary",
        "date_of_birth": dob1.isoformat(),
        "employment_status": st1,
        "employment_started": es1.isoformat() if es1 else None,
        "desired_retirement_age": int(clamp(round(rng.normal(66, 3)), 55, 75)),
        "occupation_group": str(rng.choice(["exec","professional","finance","sales","operations","business_owner","retired"])),
        "smoker": bool(rng.random() < 0.10),
        "state_of_health": str(rng.choice(["excellent","good","fair","poor"], p=[0.24,0.48,0.22,0.06])),
        "gross_annual_income": round(inc1, 2)
    }]
    if has_second:
        people.append({
            "person_id": f"{hh_id}_P2",
            "household_id": hh_id,
            "client_no": 2,
            "role": "spouse_partner",
            "date_of_birth": dob2.isoformat(),
            "employment_status": st2,
            "employment_started": es2.isoformat() if es2 else None,
            "desired_retirement_age": int(clamp(round(rng.normal(66, 3)), 55, 75)),
            "occupation_group": str(rng.choice(["professional","healthcare","education","operations","business_owner","retired","inactive"])),
            "smoker": bool(rng.random() < 0.08),
            "state_of_health": str(rng.choice(["excellent","good","fair","poor"], p=[0.20,0.50,0.23,0.07])),
            "gross_annual_income": round(inc2, 2)
        })

    income_lines = []
    n_income = max(1, int(rng.poisson(2.2)))
    remaining = hh_income
    sources = ["salary","bonus","business_income","rental_income","social_security","pension_income","interest_dividends"]
    freqs = ["monthly","weekly","annual","quarterly","ad_hoc"]
    probs = [0.64,0.10,0.12,0.08,0.06]
    for i in range(1, n_income + 1):
        amt = remaining if i == n_income else min(remaining, hh_income * rng.uniform(0.08, 0.45))
        remaining -= amt
        income_lines.append({
            "income_line_id": f"{hh_id}_I{i}",
            "household_id": hh_id,
            "owner": "joint" if has_second and rng.random() < 0.15 else ("client_2" if has_second and rng.random() < 0.35 else "client_1"),
            "source_type": str(rng.choice(sources)),
            "frequency": str(rng.choice(freqs, p=probs)),
            "net_or_gross": "gross",
            "amount_annualized": round(max(0.0, amt), 2)
        })

    assets = []
    asset_specs = [
        ("brokerage","taxable", max(0.0, investable - retirement_assets - cash_total - alternatives_total)),
        ("retirement","401k_ira", retirement_assets),
        ("cash","bank", cash_total),
        ("alternatives","private_markets", alternatives_total),
        ("property","primary_residence", prop_val),
    ]
    aidx = 1
    for atype, subtype, val in asset_specs:
        if val <= 0:
            continue
        owner = "joint" if has_second and atype in {"brokerage","property","cash"} and rng.random() < 0.45 else ("client_2" if has_second and rng.random() < 0.35 else "client_1")
        assets.append({
            "asset_id": f"{hh_id}_A{aidx}",
            "household_id": hh_id,
            "owner": owner,
            "asset_type": atype,
            "subtype": subtype,
            "provider_type": str(rng.choice(["bank","brokerage","retirement_platform","insurance","advisor_platform"])),
            "value": round(val, 2),
            "is_joint": owner == "joint"
        })
        aidx += 1

    liabilities = []
    if has_loan:
        liabilities.append({
            "liability_id": f"{hh_id}_L1",
            "household_id": hh_id,
            "type": "mortgage" if prop_val > 0 else "loan",
            "monthly_cost": round(debt_cost, 2),
            "outstanding": round(loan_outstanding, 2),
            "interest_rate": round(rate, 2),
            "final_payment_date": final_payment.isoformat() if final_payment else None
        })
        if scenario == "financially_stressed_with_debt":
            liabilities.append({
                "liability_id": f"{hh_id}_L2",
                "household_id": hh_id,
                "type": "credit_card",
                "monthly_cost": round(rng.uniform(150, 1200), 2),
                "outstanding": round(rng.uniform(4000, 45000), 2),
                "interest_rate": round(rng.uniform(14, 29), 2),
                "final_payment_date": None
            })

    protections = []
    if rng.random() < pri["booleans"]["has_protection_policy"]:
        assured = max(50000.0, hh_income * rng.uniform(1.5, 8.0))
        protections.append({
            "policy_id": f"{hh_id}_PP1",
            "household_id": hh_id,
            "owner": "client_1",
            "policy_type": str(rng.choice(["life","disability","ltc"])),
            "monthly_cost": round(assured * rng.uniform(0.00015, 0.0011), 2),
            "amount_assured": round(assured, 2),
            "assured_until": (snap + timedelta(days=int(rng.uniform(5, 35) * 365.25))).isoformat()
        })

    return household, people, income_lines, assets, liabilities, protections

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-households", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    priors = json.loads((ART / "computed_priors.json").read_text(encoding="utf-8"))
    ctx = Ctx(priors=priors, snapshot=parse_date(priors["meta"]["snapshot_date"]), rng=np.random.default_rng(args.seed))

    hh_rows, people_rows, inc_rows, asset_rows, liab_rows, prot_rows = [], [], [], [], [], []
    for i in range(1, args.n_households + 1):
        hh, people, incs, assets, liabs, prots = gen_one(i, ctx)
        hh_rows.append(hh); people_rows.extend(people); inc_rows.extend(incs); asset_rows.extend(assets); liab_rows.extend(liabs); prot_rows.extend(prots)

    pd.DataFrame(hh_rows).to_csv(OUT / "households.csv", index=False)
    pd.DataFrame(people_rows).to_csv(OUT / "people.csv", index=False)
    pd.DataFrame(inc_rows).to_csv(OUT / "income_lines.csv", index=False)
    pd.DataFrame(asset_rows).to_csv(OUT / "assets.csv", index=False)
    pd.DataFrame(liab_rows).to_csv(OUT / "liabilities.csv", index=False)
    pd.DataFrame(prot_rows).to_csv(OUT / "protection_policies.csv", index=False)
    print("Generated into", OUT)

if __name__ == "__main__":
    main()

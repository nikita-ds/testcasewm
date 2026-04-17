from __future__ import annotations
import json
from datetime import date, timedelta
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "artifacts"
OUT = ROOT / "artifacts" / "generated"

def parse_date_safe(x):
    if pd.isna(x) or x in ("", None):
        return None
    return date.fromisoformat(str(x))

def js_divergence(p, q):
    keys = sorted(set(p) | set(q))
    p_arr = np.array([p.get(k,0.0) for k in keys], dtype=float)
    q_arr = np.array([q.get(k,0.0) for k in keys], dtype=float)
    eps = 1e-12
    p_arr = (p_arr + eps) / (p_arr.sum() + eps * len(keys))
    q_arr = (q_arr + eps) / (q_arr.sum() + eps * len(keys))
    m = 0.5 * (p_arr + q_arr)
    return float(0.5*np.sum(p_arr*np.log(p_arr/m)) + 0.5*np.sum(q_arr*np.log(q_arr/m)))

def population_stability_index(expected, actual, bins=10):
    expected = np.asarray(expected, dtype=float)
    actual = np.asarray(actual, dtype=float)
    breakpoints = np.percentile(expected, np.linspace(0, 100, bins + 1))
    breakpoints = np.unique(breakpoints)
    if len(breakpoints) < 3:
        return 0.0
    exp_counts, _ = np.histogram(expected, bins=breakpoints)
    act_counts, _ = np.histogram(actual, bins=breakpoints)
    exp_perc = exp_counts / max(len(expected), 1)
    act_perc = act_counts / max(len(actual), 1)
    exp_perc = np.where(exp_perc == 0, 1e-6, exp_perc)
    act_perc = np.where(act_perc == 0, 1e-6, act_perc)
    psi = np.sum((act_perc - exp_perc) * np.log(act_perc / exp_perc))
    return float(psi)

def fit_lognormal_reference(p10, p90, size=5000, seed=123):
    import math
    from statistics import NormalDist
    z10 = NormalDist().inv_cdf(0.1)
    z90 = NormalDist().inv_cdf(0.9)
    sigma = (math.log(p90) - math.log(p10)) / (z90 - z10)
    mu = math.log(p10) - sigma * z10
    rng = np.random.default_rng(seed)
    return rng.lognormal(mu, sigma, size=size)

def main():
    pri = json.loads((ART / "computed_priors.json").read_text(encoding="utf-8"))
    hh = pd.read_csv(OUT / "households.csv")
    people = pd.read_csv(OUT / "people.csv")
    liab = pd.read_csv(OUT / "liabilities.csv") if (OUT / "liabilities.csv").exists() else pd.DataFrame()

    snapshot = date.fromisoformat(pri["meta"]["snapshot_date"])
    violations = []

    for _, row in hh.iterrows():
        hid = row["household_id"]
        ppl = people[people["household_id"] == hid].copy()
        p1 = ppl[ppl["client_no"] == 1].iloc[0]
        dob1 = parse_date_safe(p1["date_of_birth"])
        move_in = parse_date_safe(row["move_in_date"])
        if move_in and dob1 and move_in < dob1 + timedelta(days=int(18 * 365.25)):
            violations.append((hid, "move_in_before_18"))

        for _, p in ppl.iterrows():
            dob = parse_date_safe(p["date_of_birth"])
            est = parse_date_safe(p["employment_started"])
            if est and dob and est < dob + timedelta(days=int(16 * 365.25)):
                violations.append((hid, f"employment_start_before_16_client_{int(p['client_no'])}"))
            if est and est > snapshot:
                violations.append((hid, f"employment_start_in_future_client_{int(p['client_no'])}"))

        oldest = parse_date_safe(row["oldest_child_dob"])
        youngest = parse_date_safe(row["youngest_child_dob"])
        if oldest and youngest and youngest < oldest:
            violations.append((hid, "youngest_older_than_oldest"))
        if oldest and dob1 and oldest < dob1 + timedelta(days=int(16 * 365.25)):
            violations.append((hid, "parent_under_16_at_child_birth"))

        if not bool(row["has_mortgage_or_loan"]) and float(row["loan_outstanding_total"]) > 0:
            violations.append((hid, "loan_nonzero_while_has_loan_false"))

        if row["annual_alimony_paid"] > 0 and row["marital_status"] not in {"divorced", "secondly_wedded"}:
            violations.append((hid, "alimony_present_without_divorced_or_secondly_wedded_status"))

    if len(liab) > 0 and "final_payment_date" in liab.columns:
        for _, l in liab.dropna(subset=["final_payment_date"]).iterrows():
            fpd = parse_date_safe(l["final_payment_date"])
            if fpd and fpd <= snapshot and str(l["type"]) != "credit_card":
                violations.append((l["household_id"], "final_payment_not_future"))

    rules = pd.DataFrame(violations, columns=["household_id", "rule_violation"])
    rules.to_csv(OUT / "rule_violations.csv", index=False)

    metrics = []
    obs_marital = hh["marital_status"].value_counts(normalize=True).to_dict()
    metrics.append({"metric":"js_marital_status", "value":js_divergence(pri["categoricals"]["marital_status"], obs_marital)})

    obs_risk = hh["risk_tolerance"].value_counts(normalize=True).to_dict()
    metrics.append({"metric":"js_risk_tolerance", "value":js_divergence(pri["categoricals"]["risk_tolerance"], obs_risk)})

    income_ref = fit_lognormal_reference(pri["continuous_targets"]["annual_household_gross_income"]["p10"], pri["continuous_targets"]["annual_household_gross_income"]["p90"], len(hh), 123)
    invest_ref = fit_lognormal_reference(pri["continuous_targets"]["investable_assets_total"]["p10"], pri["continuous_targets"]["investable_assets_total"]["p90"], len(hh), 456)
    nw_ref = fit_lognormal_reference(pri["continuous_targets"]["net_worth_proxy"]["p10"], pri["continuous_targets"]["net_worth_proxy"]["p90"], len(hh), 789)

    metrics.append({"metric":"psi_income", "value":population_stability_index(income_ref, hh["annual_household_gross_income"])})
    metrics.append({"metric":"psi_investable_assets", "value":population_stability_index(invest_ref, hh["investable_assets_total"])})
    metrics.append({"metric":"psi_net_worth", "value":population_stability_index(nw_ref, hh["net_worth_proxy"])})

    metrics.append({"metric":"median_income", "value":float(hh["annual_household_gross_income"].median())})
    metrics.append({"metric":"median_investable_assets", "value":float(hh["investable_assets_total"].median())})
    metrics.append({"metric":"median_net_worth_proxy", "value":float(hh["net_worth_proxy"].median())})
    metrics.append({"metric":"rule_violations_count", "value":int(len(rules))})

    pd.DataFrame(metrics).to_csv(OUT / "distance_to_priors.csv", index=False)

    scen = hh["scenario"].value_counts().reset_index()
    scen.columns = ["scenario","count"]
    scen["share"] = scen["count"] / len(hh)
    scen.to_csv(OUT / "scenario_coverage.csv", index=False)
    print("Validation complete")

if __name__ == "__main__":
    main()

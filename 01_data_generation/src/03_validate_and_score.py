from __future__ import annotations
import json
from datetime import date, timedelta
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "artifacts"
TABLES = ART / "tables"

def parse_date_safe(x):
    if pd.isna(x) or x in ("", None):
        return None
    return date.fromisoformat(str(x))

def js_divergence(p, q):
    keys = sorted(set(p) | set(q))
    p_arr = np.array([p.get(k,0.0) for k in keys], dtype=float)
    q_arr = np.array([q.get(k,0.0) for k in keys], dtype=float)
    eps=1e-12
    p_arr=(p_arr+eps)/(p_arr.sum()+eps*len(keys))
    q_arr=(q_arr+eps)/(q_arr.sum()+eps*len(keys))
    m=0.5*(p_arr+q_arr)
    return float(0.5*np.sum(p_arr*np.log(p_arr/m))+0.5*np.sum(q_arr*np.log(q_arr/m)))

def psi(expected, actual, bins=10):
    expected=np.asarray(expected,dtype=float); actual=np.asarray(actual,dtype=float)
    qs=np.linspace(0,100,bins+1)
    b=np.percentile(expected, qs); b=np.unique(b)
    if len(b) < 3: return 0.0
    ec,_=np.histogram(expected,bins=b); ac,_=np.histogram(actual,bins=b)
    ep=ec/max(len(expected),1); ap=ac/max(len(actual),1)
    ep=np.where(ep==0,1e-6,ep); ap=np.where(ap==0,1e-6,ap)
    return float(np.sum((ap-ep)*np.log(ap/ep)))

def main():
    pri = json.loads((ART / "computed_priors.json").read_text(encoding="utf-8"))
    hh = pd.read_csv(TABLES / "households.csv")
    people = pd.read_csv(TABLES / "people.csv")
    liab = pd.read_csv(TABLES / "liabilities.csv") if (TABLES / "liabilities.csv").exists() else pd.DataFrame()

    snapshot = date.fromisoformat(pri["meta"]["snapshot_date"])
    violations=[]

    for _, row in hh.iterrows():
        hid=row["household_id"]
        ppl=people[people["household_id"]==hid]
        p1=ppl.iloc[0]
        dob1=parse_date_safe(p1["date_of_birth"])
        move_in=parse_date_safe(row["move_in_date"])
        if move_in and dob1 and move_in < dob1 + timedelta(days=int(18*365.25)):
            violations.append((hid,"move_in_before_18"))
        for _, p in ppl.iterrows():
            dob=parse_date_safe(p["date_of_birth"]); est=parse_date_safe(p["employment_started"])
            if est and dob and est < dob + timedelta(days=int(16*365.25)):
                violations.append((hid,f"employment_start_before_16_client_{int(p['client_no'])}"))
            if est and est > snapshot:
                violations.append((hid,f"employment_start_in_future_client_{int(p['client_no'])}"))

        oldest=parse_date_safe(row["oldest_child_dob"]); youngest=parse_date_safe(row["youngest_child_dob"])
        if oldest and youngest and youngest < oldest:
            violations.append((hid,"youngest_older_than_oldest"))
        if oldest and dob1 and oldest < dob1 + timedelta(days=int(16*365.25)):
            violations.append((hid,"parent_under_16_at_child_birth"))

        if row["mortgage_payment_to_income_ratio"] > 0.70:
            violations.append((hid,"mortgage_payment_ratio_above_70pct"))
        if row["annual_alimony_paid"] > 0 and row["marital_status"] not in {"divorced","secondly_wedded"}:
            violations.append((hid,"alimony_present_without_compatible_marital_status"))

    if len(liab)>0:
        for _, l in liab.dropna(subset=["final_payment_date"]).iterrows():
            fpd=parse_date_safe(l["final_payment_date"])
            if fpd and fpd <= snapshot and str(l["type"]) != "credit_card":
                violations.append((l["household_id"],"final_payment_not_future"))

    rules=pd.DataFrame(violations,columns=["household_id","rule_violation"])
    rules.to_csv(TABLES/"rule_violations.csv",index=False)

    # Build expected income sample from empirical affluent bracket weights
    rng=np.random.default_rng(123)
    weights=pri["income_distribution"]["affluent_bracket_weights"]
    samples=[]
    for _ in range(len(hh)):
        b = weights[int(rng.choice(np.arange(len(weights)), p=np.array([w["weight"] for w in weights])/sum(w["weight"] for w in weights)))]
        if b.get("hi") is not None:
            samples.append(rng.uniform(b["lo"], b["hi"]))
        else:
            # Open-ended top bracket (e.g. 200k+ / 250k+): use the same tail model as generation.
            u=rng.random()
            floor=float(b.get("lo") or 250000)
            mid1_hi=float(max(500000.0, 2.0*floor))
            if u < 0.80:
                samples.append(rng.uniform(floor, mid1_hi))
            elif u < 0.98:
                samples.append(np.clip(rng.lognormal(np.log(700000),0.35), mid1_hi, 1500000))
            else:
                samples.append(np.clip(1000000*(1+rng.pareto(2.5)),1000000,5000000))
    expected_income=np.array(samples)

    # Asset reference by segment mix
    expected_assets=[]
    for _ in range(len(hh)):
        seg=rng.choice(["affluent","hnw","ultra"], p=[0.78,0.215,0.005])
        if seg=="affluent":
            expected_assets.append(np.clip(rng.lognormal(np.log(700000),0.55),250000,2000000))
        elif seg=="hnw":
            expected_assets.append(np.clip(rng.lognormal(np.log(3500000),0.75),1000000,30000000))
        else:
            expected_assets.append(np.clip(rng.lognormal(np.log(45000000),0.55),30000000,150000000))
    expected_assets=np.array(expected_assets)

    metrics=[]
    metrics.append({"metric":"js_marital_status","value":js_divergence(pri["categoricals"]["marital_status"], hh["marital_status"].value_counts(normalize=True).to_dict())})
    metrics.append({"metric":"js_risk_tolerance","value":js_divergence(pri["categoricals"]["risk_tolerance"], hh["risk_tolerance"].value_counts(normalize=True).to_dict())})
    metrics.append({"metric":"psi_income","value":psi(expected_income, hh["annual_household_gross_income"])})
    metrics.append({"metric":"psi_investable_assets","value":psi(expected_assets, hh["investable_assets_total"])})
    metrics.append({"metric":"median_income","value":float(hh["annual_household_gross_income"].median())})
    metrics.append({"metric":"median_investable_assets","value":float(hh["investable_assets_total"].median())})
    metrics.append({"metric":"p95_mortgage_payment_to_income_ratio","value":float(np.nanpercentile(hh["mortgage_payment_to_income_ratio"],95))})
    metrics.append({"metric":"max_mortgage_payment_to_income_ratio","value":float(np.nanmax(hh["mortgage_payment_to_income_ratio"]))})
    metrics.append({"metric":"rule_violations_count","value":int(len(rules))})
    pd.DataFrame(metrics).to_csv(TABLES/"distance_to_priors.csv", index=False)

    scen=hh["scenario"].value_counts().reset_index(); scen.columns=["scenario","count"]; scen["share"]=scen["count"]/len(hh); scen.to_csv(TABLES/"scenario_coverage.csv", index=False)
    seg=hh["wealth_segment"].value_counts().reset_index(); seg.columns=["wealth_segment","count"]; seg["share"]=seg["count"]/len(hh); seg.to_csv(TABLES/"wealth_segment_coverage.csv", index=False)
    print("Validation complete")

if __name__ == "__main__":
    main()

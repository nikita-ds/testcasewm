from __future__ import annotations
import argparse
import json
import math
from datetime import date, timedelta
from pathlib import Path
import numpy as np
import pandas as pd

from runtime_config import ValidationRuntimeConfig, load_validation_runtime_config

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "artifacts"
TABLES = ART / "tables"

def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def lerp(a: float, b: float, t: float) -> float:
    return float(a + (b - a) * float(clamp(t, 0.0, 1.0)))


def retirement_progress(age: int | float, retirement_age: int | float, span_years: int = 35) -> float:
    years_to_ret = float(retirement_age) - float(age)
    return float(clamp((float(span_years) - years_to_ret) / float(span_years), 0.0, 1.0))


def age_income_multiplier(age: int | float, retirement_age: int | float, retired: bool) -> float:
    progress = retirement_progress(age, retirement_age)
    if retired:
        return float(lerp(0.85, 0.62, progress))
    return float(lerp(0.88, 1.15, progress))


def age_assets_multiplier(age: int | float, retirement_age: int | float, retired: bool) -> float:
    progress = retirement_progress(age, retirement_age)
    if retired:
        return float(lerp(1.10, 1.30, progress))
    return float(lerp(0.72, 1.35, progress))


def get_public_income_median(priors: dict) -> float | None:
    meta = priors.get("meta") or {}
    inc = priors.get("income_distribution") or {}
    for k in ("public_income_median", "public_income_median_2024", "public_income_median_2023"):
        if k in meta and meta.get(k) is not None:
            return float(meta[k])
    for k in ("public_income_median", "public_income_median_2024", "public_income_median_2023"):
        if k in inc and inc.get(k) is not None:
            return float(inc[k])
    return None


def get_affluent_income_floor(priors: dict) -> float | None:
    meta = priors.get("meta") or {}
    inc = priors.get("income_distribution") or {}
    for k in ("affluent_income_floor", "affluent_floor_2x_median"):
        if k in meta and meta.get(k) is not None:
            return float(meta[k])
    for k in ("affluent_income_floor", "affluent_floor_2x_median"):
        if k in inc and inc.get(k) is not None:
            return float(inc[k])
    return None


def apply_scenario_income_adjustment(priors: dict, scenario: str, hh_income: float, rng) -> float:
    gp = priors.get("generator_params") or {}
    adj_all = gp.get("scenario_income_adjustments") or {}
    adj = adj_all.get(scenario)
    if not isinstance(adj, dict):
        return float(hh_income)

    hh_income = float(hh_income) * float(rng.uniform(float(adj["mult_lo"]), float(adj["mult_hi"])))
    lo = adj.get("clamp_lo")
    hi = adj.get("clamp_hi")

    def resolve_bound(x):
        if x is None:
            return None
        if isinstance(x, str):
            if x == "affluent_income_floor":
                floor = (priors.get("meta") or {}).get("affluent_income_floor")
                return None if floor is None else float(floor)
        return float(x)

    lo_v = resolve_bound(lo)
    hi_v = resolve_bound(hi)
    if lo_v is not None:
        hh_income = max(float(lo_v), hh_income)
    if hi_v is not None:
        hh_income = min(float(hi_v), hh_income)
    return float(hh_income)


def sample_empirical_income(priors: dict, rng) -> float:
    """Match the generator's household-income sampling logic.

    Primary path is a smooth lognormal model anchored to public median.
    Falls back to bracket weights when public median is missing.
    """
    gp = priors.get("generator_params") or {}
    im = gp.get("income_model") or {}
    if str(im.get("type")) == "lognormal":
        median_public = get_public_income_median(priors)
        if median_public is None or float(median_public) <= 0:
            im = {"type": "brackets"}
        else:
            import math

            median = float(median_public) * float(im["median_multiple_of_public_median"])
            sigma = float(im["sigma"])
            lo = float(im["min_income"])
            hi = float(im["max_income"])
            max_resample = int(im["max_resample"])
            mu = float(math.log(max(median, 1e-9)))
            for _ in range(max_resample):
                x = float(rng.lognormal(mean=mu, sigma=sigma))
                if lo <= x <= hi:
                    return float(x)
            x = float(rng.lognormal(mean=mu, sigma=sigma))
            return float(clamp(x, lo, hi))

    brackets = (priors.get("income_distribution") or {}).get("affluent_bracket_weights")
    if not isinstance(brackets, list) or not brackets:
        raise KeyError("Missing priors.income_distribution.affluent_bracket_weights")
    probs = np.array([float(b["weight"]) for b in brackets], dtype=float)
    probs = probs / probs.sum()
    b = brackets[int(rng.choice(np.arange(len(brackets)), p=probs))]
    if b.get("hi") is not None:
        return float(rng.uniform(float(b["lo"]), float(b["hi"])))

    tail = gp.get("income_tail_model") or {}
    u_breaks = tail.get("u_breaks") or {}
    mid_break = float(u_breaks["mid"])
    high_break = float(u_breaks["high"])

    u = float(rng.random())
    floor = float(b.get("lo") or float(tail["floor_default"]))
    mid1_cfg = tail.get("mid1_hi") or {}
    mid1_hi = float(max(float(mid1_cfg["min"]), float(mid1_cfg["floor_multiplier"]) * floor))

    if u < mid_break:
        return float(rng.uniform(floor, mid1_hi))
    if u < high_break:
        stage = tail.get("lognormal_stage") or {}
        x = float(
            rng.lognormal(
                mean=float(np.log(max(float(stage["median"]), 1e-9))),
                sigma=float(stage["sigma"]),
            )
        )
        return float(clamp(x, mid1_hi, float(stage["low_cap"])))
    stage = tail.get("pareto_stage") or {}
    x = float(float(stage["scale"]) * (1.0 + rng.pareto(float(stage["shape"]))))
    return float(clamp(x, float(stage["low"]), float(stage["high"])))


def sample_investable_assets(priors: dict, scenario: str, income: float, rng) -> float:
    gp = priors.get("generator_params") or {}
    am = gp.get("investable_assets_model") or {}

    incm = am.get("income_multiplier") or {}
    if bool(incm.get("enabled", False)):
        adj = (am.get("scenario_adjustments") or {}).get(scenario)
        scen_mult = 1.0
        if isinstance(adj, dict):
            if "mult" in adj:
                scen_mult = float(adj["mult"])

        k_base = float(incm.get("k_base", 4.0))
        k2_cfg = incm.get("k2") or {}
        k2_mean = float(k2_cfg.get("mean", 1.0))
        q10 = float(k2_cfg.get("q10", 0.75))
        q90 = float(k2_cfg.get("q90", 1.25))
        z90 = 1.2815515655446004
        sigma = (q90 - q10) / (2.0 * z90) if q90 > q10 else 0.0
        sigma = float(max(0.0, sigma))
        k2_tries = int(k2_cfg.get("resample_max_tries", 200))

        base_income = max(float(income), 1.0)
        if sigma <= 0:
            k2 = float(k2_mean)
        else:
            k2 = None
            for _ in range(k2_tries):
                cand = float(rng.normal(k2_mean, sigma))
                if cand > 0:
                    k2 = cand
                    break
            if k2 is None:
                k2 = float(k2_mean)
        return float(base_income * k_base * k2 * scen_mult)

    raise KeyError("Missing generator_params.investable_assets_model.income_multiplier.enabled=true")


def build_expected_samples(priors: dict, n: int, seed: int = 123) -> tuple[np.ndarray, np.ndarray]:
    """Simulate reference samples from priors-driven generator models.

    PSI is computed between these expected samples (reference) and actual generated tables.
    """
    gp = priors.get("generator_params") or {}
    scenarios = list(gp.get("scenarios") or priors.get("scenario_catalog") or [])
    if not scenarios:
        raise KeyError("Missing generator_params.scenarios (or scenario_catalog)")
    w = np.array(gp.get("scenario_weights") or [1.0] * len(scenarios), dtype=float)
    w = w / w.sum()
    income_scale = float((gp.get("income_calibration") or {}).get("scale", 1.0))

    income_floor_cfg = (gp.get("income_floor") or {}) if isinstance(gp.get("income_floor"), dict) else {}
    floor_enabled = bool(income_floor_cfg.get("enabled", False))
    floor = get_affluent_income_floor(priors) if floor_enabled else None
    max_tries = int(income_floor_cfg.get("max_tries", 50)) if floor_enabled else 1
    strategy = str(income_floor_cfg.get("strategy", "resample")) if floor_enabled else ""
    floor_mode = str(income_floor_cfg.get("mode", "affluent_income_floor")) if floor_enabled else ""
    softness = float(income_floor_cfg.get("softness", 30000.0)) if floor_enabled else 0.0
    min_accept_prob = float(income_floor_cfg.get("min_accept_prob", 0.02)) if floor_enabled else 0.0

    rng = np.random.default_rng(seed)
    expected_income = np.empty(n, dtype=float)
    expected_assets = np.empty(n, dtype=float)
    profiles = (gp.get("scenario_profiles") or {})
    dra = ((gp.get("person_model") or {}).get("desired_retirement_age") or {"mean": 65, "std": 5, "min": 55, "max": 75})
    retirement_age_cfg = int(((gp.get("employment_model") or {}).get("retirement_age") or 68))
    for i in range(n):
        scenario = str(rng.choice(scenarios, p=w))
        sp = profiles.get(scenario) or {}
        age_bounds = sp.get("age1") or [35, 65]
        age1 = int(rng.integers(int(age_bounds[0]), int(age_bounds[1]) + 1))
        ret_age1 = int(
            clamp(
                round(float(rng.normal(float(dra["mean"]), float(dra["std"])))),
                int(dra["min"]),
                int(dra["max"]),
            )
        )
        retired = scenario == "retired_couple_high_assets_low_income" or age1 >= retirement_age_cfg
        hh_income = None
        last_final_cand = None
        for _ in range(max(1, max_tries)):
            cand = float(sample_empirical_income(priors, rng)) * income_scale
            cand = float(apply_scenario_income_adjustment(priors, scenario, cand, rng))

            final_cand = float(cand) * float(age_income_multiplier(age1, ret_age1, retired))
            last_final_cand = final_cand

            if floor is None or float(floor) <= 0:
                hh_income = final_cand
                break

            if floor_mode == "soft_affluent_income_floor":
                if softness <= 0:
                    accept_p = 1.0 if final_cand >= float(floor) else float(min_accept_prob)
                else:
                    t = (final_cand - float(floor)) / float(softness)
                    accept_p = float(min_accept_prob) + (1.0 - float(min_accept_prob)) * (1.0 / (1.0 + math.exp(-t)))
                accept_p = float(clamp(accept_p, float(min_accept_prob), 1.0))
                if float(rng.random()) < accept_p:
                    hh_income = final_cand
                    break
                if strategy != "resample":
                    hh_income = final_cand
                    break
                continue

            if final_cand >= float(floor):
                hh_income = final_cand
                break
            if strategy != "resample":
                hh_income = float(max(float(floor), final_cand))
                break
        if hh_income is None:
            hh_income = float(max(float(floor) if floor else 0.0, float(last_final_cand or 0.0)))
        investable = float(sample_investable_assets(priors, scenario, hh_income, rng))
        investable *= age_assets_multiplier(age1, ret_age1, retired)
        expected_income[i] = hh_income
        expected_assets[i] = investable
    return expected_income, expected_assets

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
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=str, default=str(ROOT / "config" / "validation_runtime.json"))
    ap.add_argument("--priors-path", type=str, default=None)
    ap.add_argument("--tables-dir", type=str, default=None)
    ap.add_argument("--expected-samples-seed", type=int, default=None)
    ap.add_argument("--psi-bins", type=int, default=None)
    args = ap.parse_args()

    cfg: ValidationRuntimeConfig = load_validation_runtime_config(args.config)
    if args.priors_path is not None:
        cfg = cfg.model_copy(update={"priors_path": str(args.priors_path)})
    if args.tables_dir is not None:
        cfg = cfg.model_copy(update={"tables_dir": str(args.tables_dir)})
    if args.expected_samples_seed is not None:
        cfg = cfg.model_copy(update={"expected_samples_seed": int(args.expected_samples_seed)})
    if args.psi_bins is not None:
        cfg = cfg.model_copy(update={"psi_bins": int(args.psi_bins)})

    priors_path = (ROOT / cfg.priors_path).resolve() if not Path(cfg.priors_path).is_absolute() else Path(cfg.priors_path)
    tables_dir = (ROOT / cfg.tables_dir).resolve() if not Path(cfg.tables_dir).is_absolute() else Path(cfg.tables_dir)

    pri = json.loads(priors_path.read_text(encoding="utf-8"))
    hh = pd.read_csv(tables_dir / "households.csv")
    people = pd.read_csv(tables_dir / "people.csv")
    liab = pd.read_csv(tables_dir / "liabilities.csv") if (tables_dir / "liabilities.csv").exists() else pd.DataFrame()

    snapshot = date.fromisoformat(pri["meta"]["snapshot_date"])
    violations=[]

    move_in_min_age_days = int(float(cfg.min_move_in_age_years) * 365.25)
    employment_min_age_days = int(float(cfg.min_employment_start_age_years) * 365.25)
    max_mortgage_ratio = float(cfg.max_mortgage_payment_to_income_ratio)

    for _, row in hh.iterrows():
        hid=row["household_id"]
        ppl=people[people["household_id"]==hid]
        p1=ppl.iloc[0]
        dob1=parse_date_safe(p1["date_of_birth"])
        move_in=parse_date_safe(row["move_in_date"])
        if move_in and dob1 and move_in < dob1 + timedelta(days=move_in_min_age_days):
            violations.append((hid,"move_in_before_18"))
        for _, p in ppl.iterrows():
            dob=parse_date_safe(p["date_of_birth"]); est=parse_date_safe(p["employment_started"])
            if est and dob and est < dob + timedelta(days=employment_min_age_days):
                violations.append((hid,f"employment_start_before_16_client_{int(p['client_no'])}"))
            if est and est > snapshot:
                violations.append((hid,f"employment_start_in_future_client_{int(p['client_no'])}"))

        oldest=parse_date_safe(row["oldest_child_dob"]); youngest=parse_date_safe(row["youngest_child_dob"])
        if oldest and youngest and youngest < oldest:
            violations.append((hid,"youngest_older_than_oldest"))
        if oldest and dob1 and oldest < dob1 + timedelta(days=employment_min_age_days):
            violations.append((hid,"parent_under_16_at_child_birth"))

        if row["mortgage_payment_to_income_ratio"] > max_mortgage_ratio:
            violations.append((hid,"mortgage_payment_ratio_above_70pct"))
        if row["annual_alimony_paid"] > 0 and row["marital_status"] not in {"divorced","secondly_wedded"}:
            violations.append((hid,"alimony_present_without_compatible_marital_status"))

    if len(liab)>0:
        for _, l in liab.dropna(subset=["final_payment_date"]).iterrows():
            fpd=parse_date_safe(l["final_payment_date"])
            if fpd and fpd <= snapshot and str(l["type"]) != "credit_card":
                violations.append((l["household_id"],"final_payment_not_future"))

    rules=pd.DataFrame(violations,columns=["household_id","rule_violation"])
    rules.to_csv(tables_dir/"rule_violations.csv",index=False)

    expected_income, expected_assets = build_expected_samples(pri, len(hh), seed=int(cfg.expected_samples_seed))

    metrics=[]
    metrics.append({"metric":"js_marital_status","value":js_divergence(pri["categoricals"]["marital_status"], hh["marital_status"].value_counts(normalize=True).to_dict())})
    metrics.append({"metric":"js_risk_tolerance","value":js_divergence(pri["categoricals"]["risk_tolerance"], hh["risk_tolerance"].value_counts(normalize=True).to_dict())})
    metrics.append({"metric":"psi_income","value":psi(expected_income, hh["annual_household_gross_income"], bins=int(cfg.psi_bins))})
    metrics.append({"metric":"psi_investable_assets","value":psi(expected_assets, hh["investable_assets_total"], bins=int(cfg.psi_bins))})
    metrics.append({"metric":"median_income","value":float(hh["annual_household_gross_income"].median())})
    metrics.append({"metric":"median_investable_assets","value":float(hh["investable_assets_total"].median())})
    metrics.append({"metric":"p95_mortgage_payment_to_income_ratio","value":float(np.nanpercentile(hh["mortgage_payment_to_income_ratio"],95))})
    metrics.append({"metric":"max_mortgage_payment_to_income_ratio","value":float(np.nanmax(hh["mortgage_payment_to_income_ratio"]))})
    metrics.append({"metric":"rule_violations_count","value":int(len(rules))})
    pd.DataFrame(metrics).to_csv(tables_dir/"distance_to_priors.csv", index=False)

    scen=hh["scenario"].value_counts().reset_index(); scen.columns=["scenario","count"]; scen["share"]=scen["count"]/len(hh); scen.to_csv(tables_dir/"scenario_coverage.csv", index=False)
    # Wealth segments intentionally removed (they were a post-hoc label and caused confusion).
    print("Validation complete")

if __name__ == "__main__":
    main()

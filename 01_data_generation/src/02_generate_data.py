from __future__ import annotations
import argparse, json, math
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "artifacts"
TABLES = ART / "tables"
TABLES.mkdir(parents=True, exist_ok=True)

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def years_ago(ref: date, years: float) -> date:
    return ref - timedelta(days=int(years * 365.25))

def sample_cat(prob_map, rng):
    keys = list(prob_map.keys())
    probs = np.array(list(prob_map.values()), dtype=float)
    probs = probs / probs.sum()
    return str(rng.choice(keys, p=probs))


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


def sample_beta_scaled(rng, low, high, a=2.0, b=2.0):
    if high <= low:
        return float(low)
    x = rng.beta(a, b)
    return float(low + x * (high - low))

def sample_lognormal_quantile(rng, median, sigma, low=None, high=None):
    import math
    x = float(rng.lognormal(mean=math.log(max(median, 1e-9)), sigma=sigma))
    if low is not None:
        x = max(low, x)
    if high is not None:
        x = min(high, x)
    return float(x)


def sample_multichoice(rng, universe, max_k=3):
    k = int(rng.integers(1, max_k + 1))
    idx = rng.choice(len(universe), size=k, replace=False)
    return "|".join(sorted(universe[i] for i in idx))

def scenario_profile(priors: dict, s: str) -> dict:
    gp = priors.get("generator_params") or {}
    profiles = gp.get("scenario_profiles") or {}
    if s not in profiles:
        raise KeyError(f"Missing scenario profile for {s!r} in priors.generator_params.scenario_profiles")
    sp = profiles[s]
    age1 = sp.get("age1")
    if not isinstance(age1, (list, tuple)) or len(age1) != 2:
        raise ValueError(f"Invalid scenario profile age1 for {s!r}: {age1!r}")
    return {
        "age1": (int(age1[0]), int(age1[1])),
        "couple": sp.get("couple"),
        "kids": sp.get("kids"),
    }


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
                return float((priors.get("meta") or {}).get("affluent_income_floor"))
        return float(x)

    lo_v = resolve_bound(lo)
    hi_v = resolve_bound(hi)
    if lo_v is not None:
        hh_income = max(float(lo_v), hh_income)
    if hi_v is not None:
        hh_income = min(float(hi_v), hh_income)
    return float(hh_income)

def sample_empirical_income(priors, rng):
    # Primary path: smooth lognormal income model (no bracket-edge artifacts).
    gp = priors.get("generator_params") or {}
    im = gp.get("income_model") or {}
    if str(im.get("type")) == "lognormal":
        median_public = get_public_income_median(priors)
        if median_public is None or float(median_public) <= 0:
            # Fall back to the bracket model if median is missing.
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
                    return x
            x = float(rng.lognormal(mean=mu, sigma=sigma))
            return float(clamp(x, lo, hi))

    # Back-compat fallback: sample from bracket weights with a smooth tail above the top open-ended bracket.
    brackets = (priors.get("income_distribution") or {}).get("affluent_bracket_weights")
    if not isinstance(brackets, list) or not brackets:
        raise KeyError("Missing priors.income_distribution.affluent_bracket_weights")
    probs = np.array([float(b["weight"]) for b in brackets], dtype=float)
    probs = probs / probs.sum()
    idx = int(rng.choice(np.arange(len(brackets)), p=probs))
    b = brackets[idx]
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

def choose_wealth_segment(income, scenario, priors, rng):
    # Scenario and income inform wealth segment. Ultra remains very rare.
    gp = priors.get("generator_params") or {}
    wm = gp.get("wealth_segment_model") or {}

    force_affluent = set(wm.get("force_affluent_scenarios") or [])
    if scenario in force_affluent:
        return "affluent"

    scen_hnw = wm.get("scenario_hnw_probability") or {}
    scen_p = scen_hnw.get(scenario)
    if scen_p is not None and float(rng.random()) < float(scen_p):
        return "hnw"

    if float(income) >= float(wm["hnw_income_threshold"]) and float(rng.random()) < float(wm["hnw_probability"]):
        return "hnw"
    if float(income) >= float(wm["ultra_income_threshold"]) and float(rng.random()) < float(wm["ultra_probability"]):
        return "ultra"
    return "affluent" if float(rng.random()) < float(wm["base_affluent_probability"]) else "hnw"

def sample_assets_for_segment(priors, segment, scenario, income, rng):
    # Truncated lognormal by segment. Ranges reflect the user's desired bands.
    gp = priors.get("generator_params") or {}
    am = gp.get("investable_assets_model") or {}
    segs = am.get("segments") or {}
    spec = segs.get(segment) or {}
    x = float(
        rng.lognormal(
            mean=float(np.log(max(float(spec["median"]), 1e-9))),
            sigma=float(spec["sigma"]),
        )
    )
    investable = float(clamp(x, float(spec["clamp_lo"]), float(spec["clamp_hi"])))

    # Scenario adjustments
    adj = (am.get("scenario_adjustments") or {}).get(scenario)
    if isinstance(adj, dict):
        if "mult" in adj:
            investable = float(investable) * float(adj["mult"])
        if "clamp_lo" in adj or "clamp_hi" in adj:
            investable = float(
                clamp(
                    investable,
                    float(adj.get("clamp_lo", -float("inf"))),
                    float(adj.get("clamp_hi", float("inf"))),
                )
            )

    # Tie to income weakly to avoid absurd mismatch
    tie = am.get("income_tie") or {}
    seg_floor = (tie.get("segment_floor") or {}).get(segment)
    seg_cap = (tie.get("segment_cap") or {}).get(segment)
    lower = max(float(seg_floor), float(income) * float(tie["lower_income_mult"]))
    upper = float(seg_cap)
    investable = float(clamp(investable, lower, upper))
    return investable

def employment_status(priors, age, scenario, is_primary, rng):
    gp = priors.get("generator_params") or {}
    em = gp.get("employment_model") or {}
    if scenario == "retired_couple_high_assets_low_income" or age >= int(em["retirement_age"]):
        return "retired"
    if scenario == str(em["self_employed_primary_scenario"]) and is_primary:
        return "self_employed"
    if age < int(em["youth_age"]):
        return "employed" if float(rng.random()) < float(em["youth_employed_prob"]) else "inactive"
    p = em.get("adult_probs") or {}
    probs = {
        "employed": float(p["employed"]),
        "self_employed": float(p["self_employed_primary" if is_primary else "self_employed_secondary"]),
        "retired": float(p["retired"]),
        "inactive": float(p["inactive_primary" if is_primary else "inactive_secondary"]),
        "unemployed": float(p["unemployed"]),
    }
    return sample_cat(probs, rng)

def employment_started(priors, dob, age, status, snap, rng):
    gp = priors.get("generator_params") or {}
    esm = gp.get("employment_started_model") or {}
    inactive_none = esm.get("inactive_none") or {}
    if status == "inactive" and age < int(inactive_none["age_lt"]) and float(rng.random()) < float(inactive_none["prob"]):
        return None

    if status != "retired":
        nr = esm.get("non_retired_years") or {}
        lo = max(float(nr["min_lo"]), float(age) - float(nr["min_age_ref"]))
        hi = max(float(nr["max_lo"]), float(age) - float(nr["max_age_ref"]))
    else:
        rr = esm.get("retired_years") or {}
        lo = max(float(rr["min_lo"]), float(age) - float(rr["min_age_ref"]))
        hi = max(float(rr["max_lo"]), float(age) - float(rr["max_age_ref"]))
    years = float(rng.uniform(lo, hi))
    d = years_ago(snap, years)
    work_age = float((priors.get("date_rules") or {})["employment_start_after_age"])
    min_allowed = dob + timedelta(days=int(work_age * 365.25))
    return max(d, min_allowed)

@dataclass
class Ctx:
    priors: dict
    snapshot: date
    rng: np.random.Generator

def gen_one(hidx, ctx: Ctx):
    pri = ctx.priors
    rng = ctx.rng
    snap = ctx.snapshot

    gp = pri.get("generator_params") or {}
    scenarios = list(gp.get("scenarios") or pri.get("scenario_catalog") or [])
    if not scenarios:
        raise KeyError("Missing priors.generator_params.scenarios (or priors.scenario_catalog)")
    weights = np.array(gp["scenario_weights"], dtype=float)
    weights = weights / weights.sum()
    scenario = str(rng.choice(scenarios, p=weights))
    sp = scenario_profile(pri, scenario)

    hcm = gp.get("household_composition_model") or {}

    age1 = int(rng.integers(sp["age1"][0], sp["age1"][1] + 1))
    has_second = (
        True
        if sp["couple"] is True
        else False
        if sp["couple"] is False
        else bool(rng.random() < float(hcm["couple_maybe_probability"]))
    )
    marital_map = {"widowed":"widowed", "divorced":"divorced", "secondly_wedded_paying_alimony":"secondly_wedded"}
    marital_map = dict(marital_map)
    marital_map.update(gp.get("marital_overrides") or {})
    marital_status = marital_map.get(scenario, "married_or_civil_partner" if has_second else "single")
    spouse_delta = int(rng.integers(int(hcm["spouse_age_delta_years_min"]), int(hcm["spouse_age_delta_years_max"]) + 1))
    age2 = int(clamp(age1 + spouse_delta, int(hcm["spouse_age_min"]), int(hcm["spouse_age_max"]))) if has_second else None

    dob_jitter = float(hcm["dob_jitter_years"])
    dob1 = years_ago(snap, age1 + rng.uniform(-dob_jitter, dob_jitter))
    dob2 = years_ago(snap, age2 + rng.uniform(-dob_jitter, dob_jitter)) if age2 is not None else None
    st1 = employment_status(pri, age1, scenario, True, rng)
    st2 = employment_status(pri, age2, scenario, False, rng) if age2 is not None else None
    es1 = employment_started(pri, dob1, age1, st1, snap, rng)
    es2 = employment_started(pri, dob2, age2, st2, snap, rng) if dob2 is not None else None

    mi = gp.get("move_in_model") or {}
    years_hi = max(
        float(mi["min_floor"]),
        min(float(age1) - float(mi["age_ref"]), float(mi["cap_years"])),
    )
    years = float(rng.uniform(float(mi["min_years"]), years_hi))
    move_in = max(
        years_ago(snap, years),
        dob1 + timedelta(days=int(float(mi["min_age"]) * 365.25)),
    )

    has_children = sp["kids"] is True or (sp["kids"] == "maybe" and rng.random() < pri["booleans"]["has_children"])
    child_dobs = []
    if has_children:
        cm = gp.get("children_model") or {}
        n_children = int(min(int(cm["max_children"]), int(rng.poisson(float(cm["poisson_lambda"])) + int(cm["poisson_plus"])) ))
        youngest_parent_age = min(age1, age2 if age2 is not None else age1)
        max_child_age = max(
            0.0,
            min(float(cm["max_child_age_cap"]), float(youngest_parent_age) - float(pri["date_rules"]["min_parent_age_at_birth"])),
        )
        for _ in range(n_children):
            c_age = rng.uniform(0, max(1, max_child_age))
            c_dob = years_ago(snap, c_age)
            work_age = float(pri["date_rules"]["employment_start_after_age"])
            if c_dob > dob1 + timedelta(days=int(work_age * 365.25)):
                child_dobs.append(c_dob)
        child_dobs = sorted(child_dobs)

    hh_income = sample_empirical_income(pri, rng)
    income_scale = float((gp.get("income_calibration") or {})["scale"])
    hh_income = float(hh_income) * income_scale
    hh_income = apply_scenario_income_adjustment(pri, scenario, hh_income, rng)

    split = gp.get("spouse_income_split") or {}
    if scenario == "one_high_earner_one_low_earner" and has_second:
        cfg = split.get("one_high_earner_one_low_earner") or {}
        inc1 = hh_income * rng.uniform(float(cfg["high_earner_share_lo"]), float(cfg["high_earner_share_hi"]))
        inc2 = hh_income - inc1
    elif has_second:
        cfg = split.get("default") or {}
        share2 = float(rng.uniform(float(cfg["spouse2_share_lo"]), float(cfg["spouse2_share_hi"])))
        inc2 = hh_income * share2
        inc1 = hh_income - inc2
    else:
        inc1, inc2 = hh_income, 0.0

    wealth_segment = choose_wealth_segment(hh_income, scenario, pri, rng)
    investable = sample_assets_for_segment(pri, wealth_segment, scenario, hh_income, rng)

    # Asset mix by segment and lifecycle
    mix = gp.get("asset_mix_model") or {}
    seg_mix = (mix.get("segments") or {}).get(wealth_segment) or {}
    retirement_share = float(rng.uniform(*[float(x) for x in seg_mix["retirement"]]))
    cash_share = float(rng.uniform(*[float(x) for x in seg_mix["cash"]]))
    alt_share = float(rng.uniform(*[float(x) for x in seg_mix["alts"]]))

    scen_adj = (mix.get("scenario_adjustments") or {}).get(scenario) or {}
    if "retirement_add" in scen_adj:
        retirement_share = float(retirement_share) + float(scen_adj["retirement_add"])
    if "retirement_cap" in scen_adj:
        retirement_share = min(float(scen_adj.get("retirement_cap")), float(retirement_share))
    if "alts_force" in scen_adj:
        alt_share = float(scen_adj.get("alts_force"))

    retirement_assets = investable * retirement_share
    cash_total = investable * cash_share
    alternatives_total = investable * alt_share
    brokerage_total = max(0.0, investable - retirement_assets - cash_total - alternatives_total)

    # Property and leverage
    seg_min = (pri.get("property_value_priors", {}) or {}).get("segment_min", {})
    affluent_floor = float(seg_min["affluent"])
    hnw_floor = float(seg_min["hnw"])
    ultra_floor = float(seg_min["ultra"])

    pm = gp.get("property_model") or {}
    seg_pm = (pm.get("segments") or {}).get(wealth_segment) or {}
    if wealth_segment == "affluent":
        floor = affluent_floor
    elif wealth_segment == "hnw":
        floor = hnw_floor
    else:
        floor = ultra_floor

    prop_hi = float(
        min(
            float(seg_pm["hi_cap"]),
            float(investable) * float(rng.uniform(float(seg_pm["mult_lo"]), float(seg_pm["mult_hi"]))),
        )
    )
    prop_lo = float(min(float(floor), prop_hi))
    prop_val = prop_hi if prop_hi <= prop_lo else float(rng.uniform(prop_lo, prop_hi))
    prop_val = float(prop_val)

    padj = (pm.get("scenario_adjustments") or {}).get(scenario)
    if isinstance(padj, dict):
        if "mult" in padj:
            prop_val = float(prop_val) * float(padj["mult"])
        if "floor" in padj:
            prop_val = max(float(padj.get("floor")), float(prop_val))
        if "cap" in padj:
            prop_val = min(float(padj.get("cap")), float(prop_val))

    force_mort = set(gp.get("mortgage_force_scenarios") or [])
    force_nm = set(gp.get("non_mortgage_force_scenarios") or [])
    has_mortgage = scenario in force_mort or bool(rng.random() < pri["booleans"]["has_mortgage"])
    has_non_mortgage = scenario in force_nm or bool(rng.random() < pri["booleans"]["has_non_mortgage_debt"])

    mortgage_outstanding = 0.0; mortgage_payment = 0.0; mortgage_rate = 0.0; final_payment = None
    if has_mortgage:
        # target realistic mortgage burden by scenario
        # Use overlapping distributions (instead of disjoint uniform ranges) to avoid histogram "steps".
        # Values remain bounded by the 70% cap below.
        mcfg_all = gp.get("mortgage_ratio_beta") or {}
        mcfg = mcfg_all.get(scenario) or mcfg_all.get("default")
        if not isinstance(mcfg, dict):
            raise KeyError(f"Missing mortgage_ratio_beta config for {scenario!r} (and missing 'default')")
        target_ratio = sample_beta_scaled(
            rng,
            float(mcfg["lo"]),
            float(mcfg["hi"]),
            a=float(mcfg["a"]),
            b=float(mcfg["b"]),
        )
        mortgage_payment = hh_income / 12 * target_ratio
        mt = gp.get("mortgage_terms") or {}
        mortgage_payment = min(mortgage_payment, hh_income / 12 * float(mt["payment_ratio_cap"]))

        rnorm = mt.get("rate_normal") or {}
        mortgage_rate = float(
            clamp(
                float(rng.normal(float(rnorm["mean"]), float(rnorm["std"]))),
                float(rnorm["min"]),
                float(rnorm["max"]),
            )
        )

        yrs = mt.get("years_remaining") or {}
        years_remaining = float(rng.uniform(float(yrs["min"]), float(yrs["max"])))
        # approximate outstanding from amortizing payment
        outm = mt.get("outstanding_multiplier") or {}
        mortgage_outstanding = mortgage_payment * 12 * years_remaining * float(rng.uniform(float(outm["min"]), float(outm["max"])))
        # hard caps
        ltv_cap = float(mt["ltv_cap"])
        imc = mt.get("income_multiple_cap") or {}
        inc_mult = float(imc.get(scenario, imc["default"]))
        mortgage_outstanding = min(mortgage_outstanding, prop_val * ltv_cap, hh_income * inc_mult)
        final_payment = snap + timedelta(days=int(years_remaining * 365.25))

    non_mortgage_payment = 0.0; non_mortgage_outstanding = 0.0
    if has_non_mortgage:
        nm_all = gp.get("non_mortgage_payment") or {}
        nm_key = "financially_stressed_with_debt" if scenario == "financially_stressed_with_debt" else "default"
        nm = nm_all.get(nm_key) or nm_all.get("default")
        if not isinstance(nm, dict):
            raise KeyError(f"Missing non_mortgage_payment config for {nm_key!r} (and missing 'default')")
        non_mortgage_payment = sample_lognormal_quantile(
            rng,
            median=float(nm["median"]),
            sigma=float(nm["sigma"]),
            low=float(nm["low"]),
            high=float(nm["high"]),
        )
        non_mortgage_outstanding = non_mortgage_payment * rng.uniform(
            float(nm["out_mult_lo"]),
            float(nm["out_mult_hi"]),
        )

    monthly_debt_cost_total = mortgage_payment + non_mortgage_payment
    mortgage_ratio = mortgage_payment / (hh_income / 12) if hh_income > 0 else 0.0

    # overall expense ratio
    ecfg_all = gp.get("expense_ratio_normal") or {}
    ecfg = ecfg_all.get(scenario) or ecfg_all.get("default")
    if not isinstance(ecfg, dict):
        raise KeyError(f"Missing expense_ratio_normal config for {scenario!r} (and missing 'default')")
    base_ratio = rng.normal(float(ecfg["mean"]), float(ecfg["std"]))
    expense_to_income_ratio = float(clamp(base_ratio, float(ecfg["min"]), float(ecfg["max"])))
    monthly_expenses_total = hh_income / 12 * expense_to_income_ratio

    annual_alimony_paid = 0.0
    alm = gp.get("alimony_model") or {}
    if scenario == "secondly_wedded_paying_alimony":
        cfg = alm.get("secondly_wedded_paying_alimony") or {}
        annual_alimony_paid = float(rng.uniform(float(cfg["min"]), float(cfg["max"])))
    elif scenario == "divorced":
        cfg = alm.get("divorced") or {}
        if float(rng.random()) < float(cfg["prob"]):
            annual_alimony_paid = float(rng.uniform(float(cfg["min"]), float(cfg["max"])))

    risk = sample_cat(pri["categoricals"]["risk_tolerance"], rng)
    ro = gp.get("risk_overrides") or {}
    if wealth_segment == "ultra" and float(rng.random()) < float(ro["ultra_growth_probability"]):
        risk = "growth"
    if scenario == "retired_couple_high_assets_low_income" and isinstance(ro.get("retired_couple_high_assets_low_income"), str):
        risk = str(ro.get("retired_couple_high_assets_low_income"))
    objectives = list(gp.get("objectives") or [])
    if not objectives:
        raise KeyError("Missing priors.generator_params.objectives")
    investment_objectives = sample_multichoice(rng, objectives, int(gp["objectives_max_k"]))
    tax_bracket_band = sample_cat(pri["categoricals"]["tax_bracket_band"], rng)

    # net worth proxy
    nw = gp.get("net_worth_proxy_model") or {}
    net_worth_proxy = investable + prop_val - mortgage_outstanding - non_mortgage_outstanding + float(
        rng.uniform(float(nw["add_uniform_lo"]), float(investable) * float(nw["add_uniform_hi_mult"]))
    )

    hh_id = f"HH{hidx:06d}"
    household = {
        "household_id": hh_id,
        "scenario": scenario,
        "wealth_segment": wealth_segment,
        "country": "US",
        "market": "US_RIA",
        "marital_status": marital_status,
        "residence_state": sample_cat(pri["categoricals"]["residence_state"], rng),
        "move_in_date": move_in.isoformat(),
        "num_adults": 2 if has_second else 1,
        "num_dependants": len(child_dobs),
        "youngest_child_dob": child_dobs[-1].isoformat() if child_dobs else None,
        "oldest_child_dob": child_dobs[0].isoformat() if child_dobs else None,
        "annual_household_gross_income": round(hh_income,2),
        "monthly_expenses_total": round(monthly_expenses_total,2),
        "expense_to_income_ratio": round(expense_to_income_ratio,4),
        "annual_alimony_paid": round(annual_alimony_paid,2),
        "has_mortgage_or_loan": bool(has_mortgage or has_non_mortgage),
        "loan_outstanding_total": round(mortgage_outstanding + non_mortgage_outstanding,2),
        "monthly_debt_cost_total": round(monthly_debt_cost_total,2),
        "monthly_mortgage_payment_total": round(mortgage_payment,2),
        "monthly_non_mortgage_payment_total": round(non_mortgage_payment,2),
        "mortgage_payment_to_income_ratio": round(mortgage_ratio,4),
        "property_value_total": round(prop_val,2),
        "investable_assets_total": round(investable,2),
        "retirement_assets_total": round(retirement_assets,2),
        "cash_and_cashlike_total": round(cash_total,2),
        "alternatives_total": round(alternatives_total,2),
        "net_worth_proxy": round(net_worth_proxy,2),
        "risk_tolerance": risk,
        "investment_objectives": investment_objectives,
        "tax_bracket_band": tax_bracket_band,
        "client_segment": "affluent_ria_like"
    }

    person_model = gp.get("person_model") or {}
    dra = person_model["desired_retirement_age"]
    occ = person_model["occupation_group"]
    smoke = person_model["smoker_probability"]
    soh = person_model["state_of_health"]

    people = [{
        "person_id": f"{hh_id}_P1","household_id":hh_id,"client_no":1,"role":"primary",
        "date_of_birth": dob1.isoformat(),
        "employment_status": st1,
        "employment_started": es1.isoformat() if es1 else None,
        "desired_retirement_age": int(
            clamp(
                round(float(rng.normal(float(dra["mean"]), float(dra["std"])))),
                int(dra["min"]),
                int(dra["max"]),
            )
        ),
        "occupation_group": str(rng.choice(occ["primary"])),
        "smoker": bool(rng.random() < float(smoke["primary"])),
        "state_of_health": str(
            rng.choice(
                soh["values"],
                p=soh["primary_probs"],
            )
        ),
        "gross_annual_income": round(inc1,2)
    }]
    if has_second:
        people.append({
            "person_id": f"{hh_id}_P2","household_id":hh_id,"client_no":2,"role":"spouse_partner",
            "date_of_birth": dob2.isoformat(),
            "employment_status": st2,
            "employment_started": es2.isoformat() if es2 else None,
            "desired_retirement_age": int(
                clamp(
                    round(float(rng.normal(float(dra["mean"]), float(dra["std"])))),
                    int(dra["min"]),
                    int(dra["max"]),
                )
            ),
            "occupation_group": str(rng.choice(occ["secondary"])),
            "smoker": bool(rng.random() < float(smoke["secondary"])),
            "state_of_health": str(
                rng.choice(
                    soh["values"],
                    p=soh["secondary_probs"],
                )
            ),
            "gross_annual_income": round(inc2,2)
        })

    income_lines = []
    il = gp.get("income_lines_model") or {}
    income_sources = list(il["sources"])
    remaining = hh_income
    n_lines = max(1, int(rng.poisson(float(il["lines_poisson_lambda"]))))
    for i in range(1, n_lines+1):
        frac = il.get("split_fraction") or {}
        amt = remaining if i == n_lines else min(remaining, hh_income * rng.uniform(float(frac["lo"]), float(frac["hi"])))
        remaining -= amt
        own = il.get("owner") or {}
        joint_prob = float(own["joint_prob"])
        client2_prob = float(own["client2_prob"])
        freq = il.get("frequency") or {}
        freq_vals = freq["values"]
        freq_probs = freq["probs"]
        income_lines.append({
            "income_line_id": f"{hh_id}_I{i}",
            "household_id": hh_id,
            "owner": "joint" if has_second and rng.random() < joint_prob else ("client_2" if has_second and rng.random() < client2_prob else "client_1"),
            "source_type": str(rng.choice(income_sources)),
            "frequency": str(rng.choice(freq_vals, p=freq_probs)),
            "net_or_gross": "gross",
            "amount_annualized": round(max(0.0, amt),2)
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
        amod = gp.get("asset_model") or {}
        joint_types = set(amod["joint_types"])
        owner = "joint" if has_second and atype in joint_types and rng.random() < float(amod["joint_owner_probability"]) else ("client_2" if has_second and rng.random() < float(amod["client2_owner_probability"]) else "client_1")
        assets.append({
            "asset_id": f"{hh_id}_A{aidx}",
            "household_id": hh_id,
            "owner": owner,
            "asset_type": atype,
            "subtype": subtype,
            "provider_type": str(rng.choice(amod["provider_types"])),
            "value": round(val,2),
            "is_joint": owner == "joint"
        })
        aidx += 1

    liabilities = []
    if has_mortgage and mortgage_outstanding > 0:
        liabilities.append({
            "liability_id": f"{hh_id}_L1","household_id":hh_id,"type":"mortgage",
            "monthly_cost": round(mortgage_payment,2),
            "outstanding": round(mortgage_outstanding,2),
            "interest_rate": round(mortgage_rate,2),
            "final_payment_date": final_payment.isoformat() if final_payment else None
        })
    if has_non_mortgage and non_mortgage_outstanding > 0:
        lm = gp.get("liability_model") or {}
        ir = lm.get("non_mortgage_interest_rate") or {}
        fp = lm.get("non_mortgage_final_payment_years") or {}
        liabilities.append({
            "liability_id": f"{hh_id}_L2","household_id":hh_id,"type":"credit_card" if scenario=="financially_stressed_with_debt" else "loan",
            "monthly_cost": round(non_mortgage_payment,2),
            "outstanding": round(non_mortgage_outstanding,2),
            "interest_rate": round(float(rng.uniform(float(ir["min"]), float(ir["max"]))),2),
            "final_payment_date": None if scenario=="financially_stressed_with_debt" else (snap + timedelta(days=int(float(rng.uniform(float(fp["min"]), float(fp["max"])))*365.25))).isoformat()
        })

    protections = []
    if rng.random() < float(pri["booleans"]["has_protection_policy"]):
        pm = gp.get("protection_model") or {}
        aim = pm.get("assured_income_mult") or {}
        assured = max(float(pm["assured_min"]), hh_income * float(rng.uniform(float(aim["min"]), float(aim["max"]))))
        policy_types = pm["policy_types"]
        protections.append({
            "policy_id": f"{hh_id}_PP1","household_id":hh_id,"owner":"client_1","policy_type": str(rng.choice(policy_types)),
            "monthly_cost": round(assured * float(rng.uniform(float((pm.get("monthly_cost_rate") or {})["min"]), float((pm.get("monthly_cost_rate") or {})["max"]))),2),
            "amount_assured": round(assured,2),
            "assured_until": (snap + timedelta(days=int(float(rng.uniform(float((pm.get("assured_until_years") or {})["min"]), float((pm.get("assured_until_years") or {})["max"])))*365.25))).isoformat()
        })
    return household, people, income_lines, assets, liabilities, protections

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-households", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    priors = json.loads((ART / "computed_priors.json").read_text(encoding="utf-8"))
    ctx = Ctx(priors=priors, snapshot=date.fromisoformat(priors["meta"]["snapshot_date"]), rng=np.random.default_rng(args.seed))

    hh_rows=[]; p_rows=[]; inc_rows=[]; a_rows=[]; l_rows=[]; pp_rows=[]
    for i in range(1,args.n_households+1):
        hh,p,inc,a,l,pp = gen_one(i, ctx)
        hh_rows.append(hh); p_rows.extend(p); inc_rows.extend(inc); a_rows.extend(a); l_rows.extend(l); pp_rows.extend(pp)

    pd.DataFrame(hh_rows).to_csv(TABLES/"households.csv", index=False)
    pd.DataFrame(p_rows).to_csv(TABLES/"people.csv", index=False)
    pd.DataFrame(inc_rows).to_csv(TABLES/"income_lines.csv", index=False)
    pd.DataFrame(a_rows).to_csv(TABLES/"assets.csv", index=False)
    pd.DataFrame(l_rows).to_csv(TABLES/"liabilities.csv", index=False)
    pd.DataFrame(pp_rows).to_csv(TABLES/"protection_policies.csv", index=False)
    print("Generated tables into", TABLES)

if __name__ == "__main__":
    main()

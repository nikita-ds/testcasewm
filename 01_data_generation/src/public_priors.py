from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
import importlib
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:  # pragma: no cover
    np = importlib.import_module("numpy")
except Exception:  # pragma: no cover
    np = None


CENSUS_API = "https://api.census.gov/data"


# Minimal stable mapping (public, not proprietary): state FIPS -> postal abbreviation.
STATE_FIPS_TO_ABBR: Dict[str, str] = {
    "01": "AL",
    "02": "AK",
    "04": "AZ",
    "05": "AR",
    "06": "CA",
    "08": "CO",
    "09": "CT",
    "10": "DE",
    "11": "DC",
    "12": "FL",
    "13": "GA",
    "15": "HI",
    "16": "ID",
    "17": "IL",
    "18": "IN",
    "19": "IA",
    "20": "KS",
    "21": "KY",
    "22": "LA",
    "23": "ME",
    "24": "MD",
    "25": "MA",
    "26": "MI",
    "27": "MN",
    "28": "MS",
    "29": "MO",
    "30": "MT",
    "31": "NE",
    "32": "NV",
    "33": "NH",
    "34": "NJ",
    "35": "NM",
    "36": "NY",
    "37": "NC",
    "38": "ND",
    "39": "OH",
    "40": "OK",
    "41": "OR",
    "42": "PA",
    "44": "RI",
    "45": "SC",
    "46": "SD",
    "47": "TN",
    "48": "TX",
    "49": "UT",
    "50": "VT",
    "51": "VA",
    "53": "WA",
    "54": "WV",
    "55": "WI",
    "56": "WY",
}


@dataclass(frozen=True)
class CensusDataset:
    year: int
    dataset: str  # e.g. "acs/acs1"


class CensusApiError(RuntimeError):
    pass


def _read_json_url(url: str, timeout_s: int = 30) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "testcasewm/priors-builder"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def census_get(
    ds: CensusDataset,
    params: Dict[str, str],
    *,
    cache_dir: Optional[Path] = None,
    cache_key: Optional[str] = None,
) -> List[List[str]]:
    """Call Census API and return the raw row matrix.

    Caches raw responses for reproducibility and offline reruns.
    """
    query = urllib.parse.urlencode(params)
    url = f"{CENSUS_API}/{ds.year}/{ds.dataset}?{query}"

    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        key = cache_key or f"{ds.year}_{ds.dataset.replace('/', '_')}_{hash(url)}"
        cache_path = cache_dir / f"{key}.json"
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))

        data = _read_json_url(url)
        cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return data

    return _read_json_url(url)


def census_variables(
    ds: CensusDataset,
    *,
    cache_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Fetch variables.json as a dict of variables."""
    url = f"{CENSUS_API}/{ds.year}/{ds.dataset}/variables.json"

    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / f"{ds.year}_{ds.dataset.replace('/', '_')}_variables.json"
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))

        payload = _read_json_url(url)
        cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    return _read_json_url(url)


def _find_var_by_label(variables: Dict[str, Any], table_prefix: str, label_contains: str) -> str:
    vars_dict = variables.get("variables", {})
    matches = []
    for name, spec in vars_dict.items():
        if not name.startswith(table_prefix):
            continue
        if not name.endswith("E"):
            continue
        lbl = str(spec.get("label", ""))
        if label_contains in lbl:
            matches.append(name)
    if not matches:
        raise CensusApiError(f"Could not find variable {table_prefix} with label containing: {label_contains!r}")
    # Prefer the shortest (most direct) match.
    matches.sort(key=len)
    return matches[0]


def _parse_int(s: str) -> int:
    try:
        return int(float(s))
    except Exception as e:
        raise CensusApiError(f"Expected numeric value, got {s!r}") from e


def _normalize_weights(d: Dict[str, float]) -> Dict[str, float]:
    total = float(sum(max(0.0, v) for v in d.values()))
    if total <= 0:
        return {k: 0.0 for k in d}
    return {k: float(v) / total for k, v in d.items()}


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _parse_money_range_label(label: str) -> Optional[Tuple[float, Optional[float]]]:
    """Parse ACS value-bin labels like:

    - "Estimate!!Total!!Less than $10,000"
    - "Estimate!!Total!!$10,000 to $14,999"
    - "Estimate!!Total!!$2,000,000 or more"
    """

    if "$" not in label:
        return None

    # Keep only the final segment after the last '!!' (ACS label format).
    seg = label.split("!!")[-1].strip()

    def money(s: str) -> float:
        s = s.replace("$", "").replace(",", "").strip()
        return float(s)

    if seg.lower().startswith("less than"):
        # "Less than $10,000"
        parts = seg.split("$")
        if len(parts) < 2:
            return None
        hi = money("$" + parts[-1])
        return 0.0, hi

    if " to " in seg:
        # "$10,000 to $14,999"
        left, right = seg.split(" to ", 1)
        if "$" not in left or "$" not in right:
            return None
        lo = money(left)
        hi = money(right)
        return lo, hi

    if seg.lower().endswith("or more"):
        # "$2,000,000 or more"
        lo_str = seg[: -len("or more")].strip()
        if "$" not in lo_str:
            return None
        lo = money(lo_str)
        return lo, None

    return None


def _hist_quantile(bins: List[Tuple[float, Optional[float], float]], q: float) -> float:
    """Compute quantile from a histogram with (lo, hi, count).

    Assumes uniform distribution within each finite bin.
    If the quantile falls into an open-ended top bin (hi=None), returns its lo.
    """

    if not (0.0 <= q <= 1.0):
        raise ValueError("q must be in [0, 1]")

    total = float(sum(max(0.0, c) for _, _, c in bins))
    if total <= 0:
        return 0.0

    target = q * total
    acc = 0.0
    for lo, hi, c in bins:
        c = max(0.0, float(c))
        if acc + c >= target:
            if hi is None or hi <= lo or c <= 0:
                return float(lo)
            frac = (target - acc) / c
            return float(lo + frac * (hi - lo))
        acc += c
    # If numerical drift, return the top.
    top_lo, top_hi, _ = bins[-1]
    return float(top_hi if top_hi is not None else top_lo)


def _pick_acs_years() -> List[int]:
    # Keep it conservative to avoid many network calls; expand if needed.
    y = date.today().year
    return [y - 1, y - 2, y - 3, y - 4]


def _try_first_available_acs_dataset(cache_dir: Path) -> CensusDataset:
    # Try ACS 1-year first; if unavailable, fall back to ACS 5-year.
    for year in _pick_acs_years():
        for dataset in ("acs/acs1", "acs/acs5"):
            ds = CensusDataset(year=year, dataset=dataset)
            try:
                _ = census_get(
                    ds,
                    {"get": "NAME", "for": "us:1"},
                    cache_dir=cache_dir,
                    cache_key=f"smoke_{year}_{dataset.replace('/', '_')}",
                )
                return ds
            except Exception:
                continue
    raise CensusApiError("Could not find an available ACS dataset/year via Census API")


def _state_population_weights(ds: CensusDataset, cache_dir: Path) -> Dict[str, float]:
    # Use total population as a stable proxy for client residence mix.
    variables = census_variables(ds, cache_dir=cache_dir)
    pop_var = _find_var_by_label(variables, "B01003_", "Estimate!!Total")

    data = census_get(
        ds,
        {"get": f"NAME,{pop_var}", "for": "state:*"},
        cache_dir=cache_dir,
        cache_key=f"state_pop_{ds.year}_{ds.dataset.replace('/', '_')}",
    )
    header = data[0]
    rows = data[1:]

    idx_pop = header.index(pop_var)
    idx_state = header.index("state")

    abbr_to_pop: Dict[str, int] = {}
    for r in rows:
        fips = r[idx_state].zfill(2)
        abbr = STATE_FIPS_TO_ABBR.get(fips)
        if not abbr:
            continue
        abbr_to_pop[abbr] = abbr_to_pop.get(abbr, 0) + _parse_int(r[idx_pop])

    # Match existing generator categories.
    keep = ["CA", "NY", "TX", "FL", "IL", "WA", "MA", "NJ", "PA", "NC"]
    out: Dict[str, float] = {}
    other = 0
    for abbr, pop in abbr_to_pop.items():
        if abbr in keep:
            out[abbr] = float(pop)
        else:
            other += pop
    out["Other"] = float(other)
    return _normalize_weights(out)


def _us_median_household_income(ds: CensusDataset, cache_dir: Path) -> float:
    variables = census_variables(ds, cache_dir=cache_dir)
    # B19013_001E: Median household income in the past 12 months.
    inc_var = "B19013_001E"
    if inc_var not in variables.get("variables", {}):
        # Fallback to label search if naming changes.
        inc_var = _find_var_by_label(variables, "B19013_", "Median household income")

    data = census_get(
        ds,
        {"get": f"NAME,{inc_var}", "for": "us:1"},
        cache_dir=cache_dir,
        cache_key=f"us_income_median_{ds.year}_{ds.dataset.replace('/', '_')}",
    )
    header = data[0]
    row = data[1]
    return float(row[header.index(inc_var)])


def _income_tail_counts(ds: CensusDataset, cache_dir: Path) -> Tuple[int, int]:
    """Return (count_150_199, count_200_plus) from B19001."""
    variables = census_variables(ds, cache_dir=cache_dir)
    # Locate the two high-income bins by exact label fragments.
    v150_199 = _find_var_by_label(variables, "B19001_", "$150,000 to $199,999")
    v200_plus = _find_var_by_label(variables, "B19001_", "$200,000 or more")

    data = census_get(
        ds,
        {"get": f"NAME,{v150_199},{v200_plus}", "for": "us:1"},
        cache_dir=cache_dir,
        cache_key=f"us_income_tail_{ds.year}_{ds.dataset.replace('/', '_')}",
    )
    header = data[0]
    row = data[1]
    return _parse_int(row[header.index(v150_199)]), _parse_int(row[header.index(v200_plus)])


def _us_home_value_bins(ds: CensusDataset, cache_dir: Path) -> List[Tuple[float, Optional[float], float]]:
    """Return histogram bins of owner-occupied home values from ACS B25075."""
    variables = census_variables(ds, cache_dir=cache_dir)
    vars_dict = variables.get("variables", {})

    bin_vars: List[Tuple[float, Optional[float], str]] = []
    for name, spec in vars_dict.items():
        if not name.startswith("B25075_"):
            continue
        if not name.endswith("E"):
            continue
        if name == "B25075_001E":
            continue  # total
        lbl = str(spec.get("label", ""))
        parsed = _parse_money_range_label(lbl)
        if parsed is None:
            continue
        lo, hi = parsed
        bin_vars.append((float(lo), hi if hi is None else float(hi), name))

    if not bin_vars:
        raise CensusApiError("No parsable B25075 value-bin variables found")

    # Sort by lower bound.
    bin_vars.sort(key=lambda t: t[0])
    get_vars = [v for _, _, v in bin_vars]

    data = census_get(
        ds,
        {"get": "NAME," + ",".join(get_vars), "for": "us:1"},
        cache_dir=cache_dir,
        cache_key=f"us_home_value_bins_{ds.year}_{ds.dataset.replace('/', '_')}",
    )
    header = data[0]
    row = data[1]

    out: List[Tuple[float, Optional[float], float]] = []
    for lo, hi, var in bin_vars:
        count = _parse_int(row[header.index(var)])
        out.append((lo, hi, float(count)))
    return out


def _us_home_value_quantiles(ds: CensusDataset, cache_dir: Path, qs: Iterable[float]) -> Dict[str, float]:
    bins = _us_home_value_bins(ds, cache_dir)
    res: Dict[str, float] = {}
    for q in qs:
        key = f"p{int(round(q * 100)):02d}"
        res[key] = _hist_quantile(bins, float(q))
    return res


def build_priors_from_acs(
    *,
    cache_dir: Path,
    snapshot_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Build priors from open Census ACS via the public API.

    Produces the same high-level structure as config/priors.json for downstream scripts.
    Some fields remain curated where there is no clean ACS counterpart.
    """
    ds = _try_first_available_acs_dataset(cache_dir)
    snap = snapshot_date or date.today().isoformat()

    median_income = _us_median_household_income(ds, cache_dir)
    affluent_floor = 2.0 * median_income

    home_value_q = _us_home_value_quantiles(ds, cache_dir, qs=[0.50, 0.80, 0.95])

    count_150_199, count_200_plus = _income_tail_counts(ds, cache_dir)

    # Allocate the 150-199 bin into 5k brackets starting from the affluent floor.
    bin_lo, bin_hi = 150_000.0, 200_000.0
    active_lo = max(bin_lo, affluent_floor)
    active_hi = bin_hi
    active_width = max(1.0, active_hi - active_lo)

    slices: List[Tuple[str, float, Optional[float]]] = [
        ("165-169k", 165_000.0, 170_000.0),
        ("170-174k", 170_000.0, 175_000.0),
        ("175-179k", 175_000.0, 180_000.0),
        ("180-184k", 180_000.0, 185_000.0),
        ("185-189k", 185_000.0, 190_000.0),
        ("190-194k", 190_000.0, 195_000.0),
        ("195-199k", 195_000.0, 200_000.0),
        ("200k_plus", 200_000.0, None),
    ]

    affluent_weights: Dict[str, float] = {}
    # Portion of the 150-199 bin that lies above the floor.
    # Assume uniform within this bin (explicit approximation).
    for label, lo, hi in slices:
        if hi is None:
            continue
        inter_lo = max(lo, active_lo)
        inter_hi = min(hi, active_hi)
        if inter_hi <= inter_lo:
            affluent_weights[label] = 0.0
            continue
        frac = (inter_hi - inter_lo) / active_width
        affluent_weights[label] = float(count_150_199) * frac

    affluent_weights["200k_plus"] = float(max(0, count_200_plus))
    affluent_weights = _normalize_weights(affluent_weights)

    bracket_specs = []
    for label, lo, hi in slices:
        if hi is None:
            bracket_specs.append({"label": label, "lo": int(lo), "hi": None, "weight": float(affluent_weights.get(label, 0.0))})
        else:
            bracket_specs.append({"label": label, "lo": int(lo), "hi": int(hi), "weight": float(affluent_weights.get(label, 0.0))})

    # Residence state weights from ACS population by state.
    residence_state = _state_population_weights(ds, cache_dir)

    # Has-children and mortgage booleans from ACS are not always cleanly available via a single universal table.
    # Keep these curated defaults for now but include an explicit source note.
    priors: Dict[str, Any] = {
        "meta": {
            "snapshot_date": snap,
            "country": "US",
            "market": "US_RIA",
            "public_income_source": f"Census ACS {ds.dataset} {ds.year} via api.census.gov",
            "public_income_median": float(median_income),
            "affluent_income_floor": float(affluent_floor),
        },
        "categoricals": {
            "marital_status": {
                "married_or_civil_partner": 0.52,
                "cohabiting": 0.10,
                "single": 0.12,
                "divorced": 0.10,
                "widowed": 0.07,
                "secondly_wedded": 0.09,
            },
            "residence_state": residence_state,
            "risk_tolerance": {
                "conservative": 0.18,
                "moderate": 0.38,
                "growth": 0.29,
                "aggressive": 0.15,
            },
            "tax_bracket_band": {
                "24%": 0.12,
                "32%": 0.28,
                "35%": 0.40,
                "37%": 0.20,
            },
        },
        "booleans": {
            "has_children": 0.41,
            "has_mortgage": 0.56,
            "has_non_mortgage_debt": 0.24,
            "has_protection_policy": 0.55,
        },
        "income_distribution": {
            "source": f"Derived from ACS B19001 high-income bins (150-199k, 200k+) for {ds.dataset} {ds.year}; 150-199k subdivided uniformly above affluent floor.",
            "public_income_median": float(median_income),
            "affluent_floor_2x_median": float(affluent_floor),
            "affluent_bracket_weights": bracket_specs,
        },
        "property_value": {
            "source": f"Census ACS B25075 owner-occupied home value bins for {ds.dataset} {ds.year} via api.census.gov",
            "quantiles_us_owner_occupied": home_value_q,
        },
        "property_value_priors": {
            # Data-driven floors by segment: use higher quantiles for wealthier segments.
            "segment_min": {
                "affluent": float(home_value_q["p50"]),
                "hnw": float(home_value_q["p80"]),
                "ultra": float(home_value_q["p95"]),
            }
        },
        "wealth_segments": [
            {"name": "affluent", "assets_lo": 250000, "assets_hi": 2000000, "weight": 0.78},
            {"name": "hnw", "assets_lo": 1000000, "assets_hi": 30000000, "weight": 0.215},
            {"name": "ultra", "assets_lo": 30000000, "assets_hi": 150000000, "weight": 0.005},
        ],
        "date_rules": {
            "min_parent_age_at_birth": 16,
            "move_in_after_age": 18,
            "employment_start_after_age": 16,
            "loan_term_years_range": [2, 35],
        },
        "scenario_catalog": [
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
        ],
    }

    # Optional: include raw dataset info to make reruns easier to interpret.
    priors["meta"]["acs_year"] = ds.year
    priors["meta"]["acs_dataset"] = ds.dataset

    priors = ensure_generator_params(priors)

    priors = calibrate_income_to_target_mean(priors)

    return priors


def default_generator_params() -> Dict[str, Any]:
    """Curated generator parameters that are not cleanly derivable from ACS.

    These are centralized here so generation scripts don't embed "magic numbers".
    Some sub-params can still be influenced by computed priors (e.g. property floors).
    """
    scenarios = [
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
    scenario_weights = [0.08, 0.18, 0.15, 0.10, 0.11, 0.08, 0.08, 0.08, 0.04, 0.05, 0.05]

    return {
        "scenarios": scenarios,
        "scenario_weights": scenario_weights,
        "objectives_max_k": 3,
        "household_composition_model": {
            "couple_maybe_probability": 0.55,
            "spouse_age_delta_years_min": -10,
            "spouse_age_delta_years_max": 10,
            "spouse_age_min": 18,
            "spouse_age_max": 90,
            "dob_jitter_years": 0.49,
        },
        "marital_overrides": {
            "widowed": "widowed",
            "divorced": "divorced",
            "secondly_wedded_paying_alimony": "secondly_wedded",
        },
        "mortgage_force_scenarios": ["family_with_mortgage_and_children", "financially_stressed_with_debt"],
        "non_mortgage_force_scenarios": ["financially_stressed_with_debt"],
        "objectives": [
            "retirement",
            "wealth_growth",
            "income",
            "education",
            "tax_optimization",
            "estate_planning",
            "capital_preservation",
        ],
        "scenario_profiles": {
            "young_dual_income_low_assets": {"age1": [25, 34], "couple": True, "kids": False},
            "family_with_mortgage_and_children": {"age1": [32, 48], "couple": True, "kids": True},
            "affluent_couple_brokerage_and_pensions": {"age1": [40, 62], "couple": True, "kids": "maybe"},
            "one_high_earner_one_low_earner": {"age1": [35, 55], "couple": True, "kids": "maybe"},
            "pre_retirement_wealthy": {"age1": [55, 66], "couple": True, "kids": False},
            "self_employed_business_owner": {"age1": [35, 60], "couple": "maybe", "kids": "maybe"},
            "retired_couple_high_assets_low_income": {"age1": [67, 82], "couple": True, "kids": False},
            "financially_stressed_with_debt": {"age1": [30, 52], "couple": "maybe", "kids": "maybe"},
            "widowed": {"age1": [58, 85], "couple": False, "kids": "maybe"},
            "divorced": {"age1": [35, 65], "couple": False, "kids": "maybe"},
            "secondly_wedded_paying_alimony": {"age1": [40, 68], "couple": True, "kids": "maybe"},
        },
        "mortgage_ratio_beta": {
            "default": {"lo": 0.08, "hi": 0.50, "a": 2.0, "b": 3.2},
            "family_with_mortgage_and_children": {"lo": 0.12, "hi": 0.55, "a": 2.4, "b": 2.8},
            "financially_stressed_with_debt": {"lo": 0.18, "hi": 0.70, "a": 3.2, "b": 1.9},
            "pre_retirement_wealthy": {"lo": 0.02, "hi": 0.35, "a": 1.6, "b": 4.0},
            "retired_couple_high_assets_low_income": {"lo": 0.02, "hi": 0.35, "a": 1.6, "b": 4.0},
        },
        "mortgage_terms": {
            "payment_ratio_cap": 0.70,
            "rate_normal": {"mean": 5.0, "std": 1.1, "min": 2.5, "max": 10.0},
            "years_remaining": {"min": 3.0, "max": 30.0},
            "outstanding_multiplier": {"min": 0.75, "max": 0.95},
            "ltv_cap": 0.80,
            "income_multiple_cap": {"default": 4.5, "financially_stressed_with_debt": 6.0},
        },
        "expense_ratio_normal": {
            "default": {"mean": 0.48, "std": 0.10, "min": 0.20, "max": 0.95},
            "family_with_mortgage_and_children": {"mean": 0.58, "std": 0.08, "min": 0.20, "max": 0.95},
            "financially_stressed_with_debt": {"mean": 0.82, "std": 0.08, "min": 0.20, "max": 0.95},
            "pre_retirement_wealthy": {"mean": 0.45, "std": 0.07, "min": 0.20, "max": 0.95},
        },
        "non_mortgage_payment": {
            "default": {"median": 280.0, "sigma": 0.70, "low": 25.0, "high": 2500.0, "out_mult_lo": 4.0, "out_mult_hi": 18.0},
            "financially_stressed_with_debt": {"median": 950.0, "sigma": 0.55, "low": 150.0, "high": 3500.0, "out_mult_lo": 10.0, "out_mult_hi": 40.0},
        },
        "income_tail_model": {
            "floor_default": 250000.0,
            "u_breaks": {"mid": 0.80, "high": 0.98},
            "mid1_hi": {"min": 500000.0, "floor_multiplier": 2.0},
            "lognormal_stage": {"median": 700000.0, "sigma": 0.35, "low_cap": 1500000.0},
            "pareto_stage": {"scale": 1000000.0, "shape": 2.5, "low": 1000000.0, "high": 5000000.0},
        },
        "income_model": {
            "type": "lognormal",
            "median_multiple_of_public_median": 2.0,
            "sigma": 0.65,
            "min_income": 15000.0,
            "max_income": 20000000.0,
            "max_resample": 50,
        },
        "income_calibration": {
            "target_mean_multiple_of_public_median": 2.0,
            "scale": 1.0,
            "simulation_n": 20000,
            "simulation_seed": 0,
            "iterations": 3,
        },
        "scenario_income_adjustments": {
            # Keep scenario effects smooth: multipliers only by default (no hard clamp cutoffs).
            "young_dual_income_low_assets": {"mult_lo": 0.90, "mult_hi": 1.05},
            "pre_retirement_wealthy": {"mult_lo": 0.90, "mult_hi": 1.15},
            "retired_couple_high_assets_low_income": {"mult_lo": 0.35, "mult_hi": 0.60},
            "financially_stressed_with_debt": {"mult_lo": 0.90, "mult_hi": 1.05},
            "self_employed_business_owner": {"mult_lo": 1.00, "mult_hi": 1.30},
        },
        "spouse_income_split": {
            "one_high_earner_one_low_earner": {"high_earner_share_lo": 0.72, "high_earner_share_hi": 0.88},
            "default": {"spouse2_share_lo": 0.20, "spouse2_share_hi": 0.48},
        },
        "wealth_segment_model": {
            "force_affluent_scenarios": ["young_dual_income_low_assets"],
            "scenario_hnw_probability": {
                "retired_couple_high_assets_low_income": 0.25,
                "pre_retirement_wealthy": 0.25,
            },
            "hnw_income_threshold": 600000.0,
            "hnw_probability": 0.35,
            "ultra_income_threshold": 1200000.0,
            "ultra_probability": 0.08,
            "base_affluent_probability": 0.78,
        },
        "investable_assets_model": {
            "segments": {
                "affluent": {"median": 700000.0, "sigma": 0.55, "clamp_lo": 250000.0, "clamp_hi": 2000000.0},
                "hnw": {"median": 3500000.0, "sigma": 0.75, "clamp_lo": 1000000.0, "clamp_hi": 30000000.0},
                "ultra": {"median": 45000000.0, "sigma": 0.55, "clamp_lo": 30000000.0, "clamp_hi": 150000000.0},
            },
            "scenario_adjustments": {
                "young_dual_income_low_assets": {"mult": 0.55, "clamp_lo": 250000.0, "clamp_hi": 1200000.0},
                "financially_stressed_with_debt": {"mult": 0.40, "clamp_lo": 100000.0, "clamp_hi": 3000000.0},
                "retired_couple_high_assets_low_income": {"mult": 1.15},
            },
            "income_tie": {
                "lower_income_mult": 0.50,
                "segment_floor": {"affluent": 250000.0, "hnw": 1000000.0, "ultra": 30000000.0},
                "segment_cap": {"affluent": 2000000.0, "hnw": 30000000.0, "ultra": 150000000.0},
            },
        },
        "asset_mix_model": {
            "segments": {
                "affluent": {"retirement": [0.18, 0.38], "cash": [0.06, 0.18], "alts": [0.00, 0.05]},
                "hnw": {"retirement": [0.12, 0.30], "cash": [0.04, 0.12], "alts": [0.03, 0.18]},
                "ultra": {"retirement": [0.08, 0.20], "cash": [0.03, 0.10], "alts": [0.12, 0.35]},
            },
            "scenario_adjustments": {
                "retired_couple_high_assets_low_income": {"retirement_add": 0.10, "retirement_cap": 0.60},
                "young_dual_income_low_assets": {"retirement_cap": 0.30, "alts_force": 0.0},
            },
        },
        "property_model": {
            "segments": {
                "affluent": {"hi_cap": 2500000.0, "mult_lo": 0.35, "mult_hi": 1.20},
                "hnw": {"hi_cap": 8000000.0, "mult_lo": 0.25, "mult_hi": 1.50},
                "ultra": {"hi_cap": 40000000.0, "mult_lo": 0.15, "mult_hi": 1.20},
            },
            "scenario_adjustments": {
                "financially_stressed_with_debt": {"mult": 0.65, "floor": 350000.0},
                "young_dual_income_low_assets": {"floor": 300000.0, "cap": 1200000.0},
            },
        },
        "employment_model": {
            "retirement_age": 68,
            "youth_age": 23,
            "youth_employed_prob": 0.65,
            "self_employed_primary_scenario": "self_employed_business_owner",
            "adult_probs": {
                "employed": 0.68,
                "self_employed_primary": 0.12,
                "self_employed_secondary": 0.08,
                "retired": 0.04,
                "inactive_primary": 0.12,
                "inactive_secondary": 0.18,
                "unemployed": 0.04,
            },
        },
        "employment_started_model": {
            "inactive_none": {"age_lt": 35, "prob": 0.70},
            "non_retired_years": {"min_lo": 0.5, "min_age_ref": 28, "max_lo": 1.0, "max_age_ref": 18},
            "retired_years": {"min_lo": 18.0, "min_age_ref": 45, "max_lo": 20.0, "max_age_ref": 22},
        },
        "move_in_model": {"min_years": 0.5, "min_floor": 1.0, "age_ref": 18, "cap_years": 25, "min_age": 18},
        "children_model": {"max_children": 5, "poisson_lambda": 1.4, "poisson_plus": 1, "max_child_age_cap": 24.0},
        "alimony_model": {
            "secondly_wedded_paying_alimony": {"min": 12000.0, "max": 72000.0},
            "divorced": {"prob": 0.18, "min": 6000.0, "max": 30000.0},
        },
        "risk_overrides": {
            "ultra_growth_probability": 0.35,
            "retired_couple_high_assets_low_income": "moderate",
        },
        "net_worth_proxy_model": {"add_uniform_lo": 0.0, "add_uniform_hi_mult": 0.08},
        "person_model": {
            "desired_retirement_age": {"mean": 66.0, "std": 3.0, "min": 55, "max": 75},
            "occupation_group": {
                "primary": ["exec", "professional", "finance", "sales", "operations", "business_owner", "retired"],
                "secondary": ["professional", "healthcare", "education", "operations", "business_owner", "retired", "inactive"],
            },
            "smoker_probability": {"primary": 0.10, "secondary": 0.08},
            "state_of_health": {
                "values": ["excellent", "good", "fair", "poor"],
                "primary_probs": [0.24, 0.48, 0.22, 0.06],
                "secondary_probs": [0.20, 0.50, 0.23, 0.07],
            },
        },
        "income_lines_model": {
            "sources": ["salary", "bonus", "business_income", "rental_income", "social_security", "pension_income", "interest_dividends"],
            "lines_poisson_lambda": 2.1,
            "split_fraction": {"lo": 0.08, "hi": 0.45},
            "owner": {"joint_prob": 0.12, "client2_prob": 0.30},
            "frequency": {
                "values": ["monthly", "weekly", "annual", "quarterly", "ad_hoc"],
                "probs": [0.64, 0.10, 0.12, 0.08, 0.06],
            },
        },
        "asset_model": {
            "provider_types": ["bank", "brokerage", "retirement_platform", "insurance", "advisor_platform"],
            "joint_owner_probability": 0.45,
            "client2_owner_probability": 0.30,
            "joint_types": ["brokerage", "cash", "property"],
        },
        "liability_model": {
            "non_mortgage_interest_rate": {"min": 8.0, "max": 29.0},
            "non_mortgage_final_payment_years": {"min": 1.0, "max": 7.0},
        },
        "protection_model": {
            "assured_min": 50000.0,
            "assured_income_mult": {"min": 1.5, "max": 8.0},
            "policy_types": ["life", "disability", "ltc"],
            "monthly_cost_rate": {"min": 0.00015, "max": 0.0011},
            "assured_until_years": {"min": 5.0, "max": 35.0},
        },
    }


def _get_public_income_median(priors: Dict[str, Any]) -> Optional[float]:
    meta = priors.get("meta") or {}
    inc = priors.get("income_distribution") or {}
    for k in ("public_income_median", "public_income_median_2024"):
        v = meta.get(k)
        if v is not None:
            return float(v)
    for k in ("public_income_median", "public_income_median_2024"):
        v = inc.get(k)
        if v is not None:
            return float(v)
    return None


def _apply_income_adjustment(
    priors: Dict[str, Any],
    scenario: str,
    hh_income: float,
    rng: Any,
) -> float:
    gp = priors.get("generator_params") or {}
    adj_all = gp.get("scenario_income_adjustments") or {}
    adj = adj_all.get(scenario)
    if not isinstance(adj, dict):
        return float(hh_income)

    mult_lo = float(adj.get("mult_lo", 1.0))
    mult_hi = float(adj.get("mult_hi", 1.0))
    hh_income = float(hh_income) * float(rng.uniform(mult_lo, mult_hi))

    def resolve_bound(x: Any) -> Optional[float]:
        if x is None:
            return None
        if isinstance(x, (int, float)):
            return float(x)
        if isinstance(x, str):
            if x == "affluent_income_floor":
                return float((priors.get("meta") or {}).get("affluent_income_floor", 0.0))
        return float(x)

    lo = resolve_bound(adj.get("clamp_lo"))
    hi = resolve_bound(adj.get("clamp_hi"))
    if lo is not None:
        hh_income = max(float(lo), hh_income)
    if hi is not None:
        hh_income = min(float(hi), hh_income)
    return float(hh_income)


def _sample_affluent_income_with_tail(priors: Dict[str, Any], rng: Any) -> float:
    brackets = (priors.get("income_distribution") or {}).get("affluent_bracket_weights")
    if not isinstance(brackets, list) or not brackets:
        raise ValueError("priors.income_distribution.affluent_bracket_weights is missing")

    weights = [float(b.get("weight", 0.0)) for b in brackets]
    total = float(sum(weights))
    if total <= 0:
        raise ValueError("income bracket weights sum to 0")
    probs = [w / total for w in weights]
    b = brackets[int(rng.choice(list(range(len(brackets))), p=probs))]

    lo = float(b.get("lo") or 0.0)
    hi = b.get("hi")
    if hi is not None:
        return float(rng.uniform(lo, float(hi)))

    gp = priors.get("generator_params") or {}
    tail = gp.get("income_tail_model") or {}
    u_breaks = tail.get("u_breaks") or {}
    mid_break = float(u_breaks.get("mid", 0.80))
    high_break = float(u_breaks.get("high", 0.98))

    floor_default = float(tail.get("floor_default", 250000.0))
    floor = float(lo or floor_default)

    mid1 = tail.get("mid1_hi") or {}
    mid1_hi = float(max(float(mid1.get("min", 500000.0)), float(mid1.get("floor_multiplier", 2.0)) * floor))

    u = float(rng.random())
    if u < mid_break:
        return float(rng.uniform(floor, mid1_hi))
    if u < high_break:
        stage = tail.get("lognormal_stage") or {}
        med = float(stage.get("median", 700000.0))
        sigma = float(stage.get("sigma", 0.35))
        hi_cap = float(stage.get("low_cap", 1500000.0))
        import math

        x = float(rng.lognormal(mean=float(math.log(max(med, 1e-9))), sigma=sigma))
        return float(_clamp(x, mid1_hi, hi_cap))

    stage = tail.get("pareto_stage") or {}
    scale = float(stage.get("scale", 1000000.0))
    shape = float(stage.get("shape", 2.5))
    lo_cap = float(stage.get("low", 1000000.0))
    hi_cap = float(stage.get("high", 5000000.0))
    x = float(scale * (1.0 + rng.pareto(shape)))
    return float(_clamp(x, lo_cap, hi_cap))


def _sample_income_lognormal(priors: Dict[str, Any], rng: Any) -> float:
    """Sample smooth household income from a lognormal model.

    Parameters are anchored to the public (ACS) median. This avoids bracket-edge artifacts.
    """
    gp = priors.get("generator_params") or {}
    im = gp.get("income_model") or {}
    median_public = _get_public_income_median(priors)
    if median_public is None or median_public <= 0:
        raise ValueError("public income median is missing")

    import math

    median = float(median_public) * float(im.get("median_multiple_of_public_median", 2.0))
    sigma = float(im.get("sigma", 0.65))
    lo = float(im.get("min_income", 15000.0))
    hi = float(im.get("max_income", 20000000.0))
    max_resample = int(im.get("max_resample", 50))

    mu = float(math.log(max(median, 1e-9)))
    for _ in range(max_resample):
        x = float(rng.lognormal(mean=mu, sigma=sigma))
        if lo <= x <= hi:
            return x

    # Fallback (extremely rare): clamp if repeated resample failed.
    x = float(rng.lognormal(mean=mu, sigma=sigma))
    return float(_clamp(x, lo, hi))


def _sample_household_income_base(priors: Dict[str, Any], rng: Any) -> float:
    gp = priors.get("generator_params") or {}
    im = gp.get("income_model") or {}
    if str(im.get("type", "lognormal")) == "lognormal":
        return _sample_income_lognormal(priors, rng)
    # Back-compat fallback.
    return _sample_affluent_income_with_tail(priors, rng)


def calibrate_income_to_target_mean(priors: Dict[str, Any]) -> Dict[str, Any]:
    """Calibrate income scaling so generated mean household income hits target.

    Target is expressed as a multiple of public median household income.
    We do a small deterministic Monte Carlo to estimate the implied mean.
    """
    priors = ensure_generator_params(priors)
    if np is None:
        # Local/editor environment without numpy: keep priors deterministic, but skip calibration.
        return priors
    np_mod = np
    assert np_mod is not None
    gp = priors.get("generator_params") or {}
    cal = gp.get("income_calibration") or {}
    if not isinstance(cal, dict):
        cal = {}

    median = _get_public_income_median(priors)
    if median is None or median <= 0:
        return priors

    target_mult = float(cal.get("target_mean_multiple_of_public_median", 2.0))
    target_mean = float(target_mult * float(median))
    n = int(cal.get("simulation_n", 20000))
    seed = int(cal.get("simulation_seed", 0))
    iters = int(cal.get("iterations", 3))
    scale = float(cal.get("scale", 1.0))

    scenarios = list(gp.get("scenarios") or priors.get("scenario_catalog") or [])
    weights = np_mod.array(gp.get("scenario_weights") or [1.0] * len(scenarios), dtype=float)
    weights = weights / weights.sum()

    if not scenarios:
        return priors

    def estimate_mean(scale_factor: float) -> float:
        rng = np_mod.random.default_rng(seed)
        vals = np_mod.empty(n, dtype=float)
        for i in range(n):
            scenario = str(rng.choice(scenarios, p=weights))
            base = _sample_household_income_base(priors, rng)
            hh_income = float(base) * float(scale_factor)
            hh_income = _apply_income_adjustment(priors, scenario, hh_income, rng)
            vals[i] = hh_income
        return float(vals.mean())

    baseline_mean = None
    for _ in range(max(1, iters)):
        m = estimate_mean(scale)
        baseline_mean = m
        if m <= 0:
            break
        scale = float(scale * (target_mean / m))

    priors = dict(priors)
    priors["generator_params"] = dict(gp)
    priors["generator_params"]["income_calibration"] = {
        "target_mean_multiple_of_public_median": target_mult,
        "public_income_median": float(median),
        "target_mean": float(target_mean),
        "baseline_mean_estimate": float(baseline_mean) if baseline_mean is not None else None,
        "scale": float(scale),
        "simulation_n": n,
        "simulation_seed": seed,
        "iterations": iters,
    }
    return priors


def _deep_merge_defaults(value: Any, defaults: Any) -> Any:
    if isinstance(value, dict) and isinstance(defaults, dict):
        out = dict(defaults)
        for k, v in value.items():
            if k in out:
                out[k] = _deep_merge_defaults(v, out[k])
            else:
                out[k] = v
        return out
    return value if value is not None else defaults


def ensure_generator_params(priors: Dict[str, Any]) -> Dict[str, Any]:
    priors = dict(priors)
    existing = priors.get("generator_params")
    if not isinstance(existing, dict):
        existing = {}
    priors["generator_params"] = _deep_merge_defaults(existing, default_generator_params())
    return priors


def build_priors_with_fallback(
    *,
    cfg_priors_path: Path,
    artifacts_path: Path,
    prefer_acs: bool = True,
) -> Dict[str, Any]:
    """Prefer ACS-derived priors, fall back to config priors if offline."""
    cache_dir = artifacts_path / "public_data_cache"
    if prefer_acs:
        try:
            return build_priors_from_acs(cache_dir=cache_dir)
        except Exception:
            # Fall back to local priors for offline/CI environments.
            pass

    priors = ensure_generator_params(json.loads(cfg_priors_path.read_text(encoding="utf-8")))
    priors = calibrate_income_to_target_mean(priors)
    return priors

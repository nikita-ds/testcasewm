
"""
uk_household_synth_bootstrap.py

Purpose
-------
Bootstraps a household-finance synthetic data generator for the UK using the
freshest official public sources that are practical in 2026:

1) DWP Family Resources Survey (FRS) 2024-2025 publication tables
2) ONS Wealth and Assets Survey (WAS) / Total wealth tables for Apr 2020-Mar 2022

This script does four things:
- downloads the official files (or reuses cached copies)
- lists workbook sheet names and previews tables for manual mapping
- exposes helper functions to build calibration dictionaries
- generates a simple household-level synthetic dataset with household/person/asset tables

Notes
-----
- The official spreadsheets are publication tables, not clean microdata.
- You will usually need one manual pass to map sheet names / row labels you care about.
- This script is meant to be practical and editable, not "magic".

Run:
    python uk_household_synth_bootstrap.py

Then inspect the generated files under ./outputs
"""

from __future__ import annotations

import io
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

# Optional, but strongly recommended for URL discovery / parsing
try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover
    BeautifulSoup = None

# -----------------------------
# Official source pages / files
# -----------------------------

FRS_MAIN_PAGE = "https://www.gov.uk/government/statistics/family-resources-survey-financial-year-2024-to-2025/family-resources-survey-financial-year-2024-to-2025"
WAS_BULLETIN_PAGE = "https://www.ons.gov.uk/peoplepopulationandcommunity/personalandhouseholdfinances/incomeandwealth/bulletins/totalwealthingreatbritain/april2020tomarch2022"
WAS_DATASET_PAGE = "https://www.ons.gov.uk/peoplepopulationandcommunity/personalandhouseholdfinances/incomeandwealth/datasets/totalwealthwealthingreatbritain"

# Direct files visible from the official pages as of April 2026.
FRS_INCOME_XLS = "https://assets.publishing.service.gov.uk/media/69c3c0f493cc6e8b87a6f610/ch2_income_and_state_support.xlsx"
FRS_SAVINGS_XLS = "https://assets.publishing.service.gov.uk/media/69b96b05a564b64fbe35ab52/ch7_savings_and_investments.xlsx"
WAS_TOTAL_WEALTH_XLSX = "https://www.ons.gov.uk/file?uri=%2Fpeoplepopulationandcommunity%2Fpersonalandhouseholdfinances%2Fincomeandwealth%2Fdatasets%2Ftotalwealthwealthingreatbritain%2Fjuly2006tojune2016andapril2014tomarch2022%2Ftotalwealthtables.xlsx"

USER_AGENT = "Mozilla/5.0 (compatible; ChatGPT synthetic-data bootstrap/1.0)"

OUTPUT_DIR = Path("outputs")
CACHE_DIR = Path("cache")


# ---------------------------------
# Small helpers: download and parse
# ---------------------------------

def ensure_dirs() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    CACHE_DIR.mkdir(exist_ok=True)


def download(url: str, dest: Path, timeout: int = 60) -> Path:
    """Download URL to dest if needed."""
    if dest.exists() and dest.stat().st_size > 0:
        return dest

    headers = {"User-Agent": USER_AGENT}
    with requests.get(url, headers=headers, timeout=timeout, stream=True) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 128):
                if chunk:
                    f.write(chunk)
    return dest


def fetch_text(url: str, timeout: int = 60) -> str:
    headers = {"User-Agent": USER_AGENT}
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.text


def list_workbook_sheets(path_or_url: str) -> List[str]:
    xls = pd.ExcelFile(path_or_url)
    return xls.sheet_names


def preview_workbook(path_or_url: str, max_rows: int = 8) -> Dict[str, pd.DataFrame]:
    xls = pd.ExcelFile(path_or_url)
    previews: Dict[str, pd.DataFrame] = {}
    for sheet in xls.sheet_names:
        try:
            df = pd.read_excel(path_or_url, sheet_name=sheet, header=None, nrows=max_rows)
            previews[sheet] = df
        except Exception:
            continue
    return previews


def save_workbook_preview(previews: Dict[str, pd.DataFrame], out_path: Path) -> None:
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        for sheet, df in previews.items():
            safe_sheet = re.sub(r"[\[\]\*\?\/\\:]", "_", sheet)[:31]
            df.to_excel(writer, sheet_name=safe_sheet, index=False)


# ------------------------------------------
# Fitting simple distributions from percentiles
# ------------------------------------------

def fit_lognormal_from_two_percentiles(
    p_lo: float,
    x_lo: float,
    p_hi: float,
    x_hi: float,
) -> Tuple[float, float]:
    """
    Fit lognormal(mu, sigma) from two percentiles.
    """
    from statistics import NormalDist

    z_lo = NormalDist().inv_cdf(p_lo)
    z_hi = NormalDist().inv_cdf(p_hi)
    log_lo = math.log(max(x_lo, 1e-9))
    log_hi = math.log(max(x_hi, 1e-9))

    sigma = (log_hi - log_lo) / (z_hi - z_lo)
    mu = log_lo - sigma * z_lo
    return mu, sigma


def sample_lognormal_from_percentiles(
    n: int,
    p_lo: float,
    x_lo: float,
    p_hi: float,
    x_hi: float,
    rng: np.random.Generator,
) -> np.ndarray:
    mu, sigma = fit_lognormal_from_two_percentiles(p_lo, x_lo, p_hi, x_hi)
    return rng.lognormal(mean=mu, sigma=sigma, size=n)


# ------------------------------------------
# Calibration objects
# ------------------------------------------

@dataclass
class WealthCalibration:
    median_total_wealth: float = 293_700.0
    p10_total_wealth: float = 16_500.0
    p90_total_wealth: float = 1_200_500.0
    wealth_share_property: float = 0.40
    wealth_share_pension: float = 0.35
    wealth_share_financial: float = 0.14
    wealth_share_physical: float = 0.10

    # coarse age anchors from ONS bulletin headline text
    wealth_median_age_16_24: float = 15_200.0
    wealth_median_age_65_74: float = 502_500.0


@dataclass
class IncomeCalibration:
    # You should replace these with values parsed from FRS tables after inspection.
    # These are placeholders until you map your preferred FRS row labels.
    annual_income_median: float = 38_000.0
    annual_income_p10: float = 16_000.0
    annual_income_p90: float = 95_000.0


@dataclass
class GeneratorConfig:
    n_households: int = 10_000
    seed: int = 42
    married_share: float = 0.58
    one_adult_share: float = 0.32
    retired_share: float = 0.18
    region_choices: Tuple[str, ...] = (
        "North East",
        "North West",
        "Yorkshire and The Humber",
        "East Midlands",
        "West Midlands",
        "East of England",
        "London",
        "South East",
        "South West",
    )


# ------------------------------------------
# Manual calibration file helpers
# ------------------------------------------

DEFAULT_CALIBRATION = {
    "wealth": WealthCalibration().__dict__,
    "income": IncomeCalibration().__dict__,
}


def write_default_calibration(path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_CALIBRATION, f, indent=2)


def load_calibration(path: Path) -> Tuple[WealthCalibration, IncomeCalibration]:
    if not path.exists():
        write_default_calibration(path)

    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)

    wealth = WealthCalibration(**d["wealth"])
    income = IncomeCalibration(**d["income"])
    return wealth, income


# ------------------------------------------
# Synthetic generator
# ------------------------------------------

def age_band_to_age(band: str, rng: np.random.Generator) -> int:
    mapping = {
        "16-24": (16, 24),
        "25-34": (25, 34),
        "35-44": (35, 44),
        "45-54": (45, 54),
        "55-64": (55, 64),
        "65-74": (65, 74),
        "75+": (75, 90),
    }
    lo, hi = mapping[band]
    return int(rng.integers(lo, hi + 1))


def sample_age_band(rng: np.random.Generator) -> str:
    bands = np.array(["16-24", "25-34", "35-44", "45-54", "55-64", "65-74", "75+"])
    probs = np.array([0.08, 0.16, 0.18, 0.18, 0.16, 0.14, 0.10])
    return str(rng.choice(bands, p=probs))


def age_wealth_multiplier(age_band: str) -> float:
    """
    Coarse shape based on ONS headline age pattern:
    wealth rises strongly with age, peaks near 65-74, then softens.
    """
    return {
        "16-24": 0.10,
        "25-34": 0.28,
        "35-44": 0.55,
        "45-54": 0.85,
        "55-64": 1.15,
        "65-74": 1.70,
        "75+": 1.35,
    }[age_band]


def tenure_probs(age_band: str) -> Dict[str, float]:
    # Replace after calibrating from FRS tenure table if you want tighter numbers.
    if age_band in {"16-24", "25-34"}:
        return {"rent": 0.58, "mortgage": 0.32, "own_outright": 0.10}
    if age_band in {"35-44", "45-54"}:
        return {"rent": 0.22, "mortgage": 0.58, "own_outright": 0.20}
    if age_band in {"55-64"}:
        return {"rent": 0.16, "mortgage": 0.30, "own_outright": 0.54}
    return {"rent": 0.22, "mortgage": 0.08, "own_outright": 0.70}


def sample_categorical(prob_map: Dict[str, float], rng: np.random.Generator) -> str:
    keys = np.array(list(prob_map.keys()))
    probs = np.array(list(prob_map.values()), dtype=float)
    probs = probs / probs.sum()
    return str(rng.choice(keys, p=probs))


def household_archetype(age_band: str, married: bool, retired: bool, income: float, rng: np.random.Generator) -> str:
    if retired:
        return "retired_couple" if married else "retired_single"
    if income >= 120_000 and married:
        return "affluent_dual_earner"
    if income >= 90_000:
        return "high_income_professional"
    if age_band in {"25-34", "35-44"} and married:
        return "family_with_mortgage"
    if income < 28_000:
        return "financially_stretched"
    return "midcareer_standard"


def generate_households(
    wealth_cal: WealthCalibration,
    income_cal: IncomeCalibration,
    cfg: GeneratorConfig,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(cfg.seed)

    # Sample household-level income and wealth.
    incomes = sample_lognormal_from_percentiles(
        cfg.n_households,
        0.10,
        income_cal.annual_income_p10,
        0.90,
        income_cal.annual_income_p90,
        rng,
    )
    wealths = sample_lognormal_from_percentiles(
        cfg.n_households,
        0.10,
        wealth_cal.p10_total_wealth,
        0.90,
        wealth_cal.p90_total_wealth,
        rng,
    )

    households: List[dict] = []
    persons: List[dict] = []
    assets: List[dict] = []
    ownership_links: List[dict] = []

    for i in range(cfg.n_households):
        hh_id = f"HH{i+1:06d}"
        age_band = sample_age_band(rng)
        head_age = age_band_to_age(age_band, rng)

        married = bool(rng.random() < cfg.married_share)
        one_adult = bool((not married) and (rng.random() < cfg.one_adult_share))
        n_adults = 2 if married else 1
        retired = bool((head_age >= 67 and rng.random() < 0.65) or (rng.random() < cfg.retired_share * 0.2))
        tenure = sample_categorical(tenure_probs(age_band), rng)
        region = str(rng.choice(np.array(cfg.region_choices)))

        annual_income = float(incomes[i])
        total_wealth = float(wealths[i] * age_wealth_multiplier(age_band))

        # Constrain low-income young households from becoming implausibly wealthy too often.
        if age_band == "16-24":
            total_wealth *= rng.uniform(0.4, 0.8)
        if retired:
            annual_income *= rng.uniform(0.35, 0.7)

        archetype = household_archetype(age_band, married, retired, annual_income, rng)

        # Asset composition with noise, centered on ONS headline shares.
        shares = np.array([
            wealth_cal.wealth_share_property,
            wealth_cal.wealth_share_pension,
            wealth_cal.wealth_share_financial,
            wealth_cal.wealth_share_physical,
        ], dtype=float)
        noise = rng.normal(0, 0.035, size=4)
        shares = np.clip(shares + noise, 0.03, None)
        shares = shares / shares.sum()

        # Tenure-driven property logic.
        property_share = shares[0]
        if tenure == "rent":
            property_share *= rng.uniform(0.02, 0.18)
        elif tenure == "mortgage":
            property_share *= rng.uniform(0.85, 1.20)
        else:  # own_outright
            property_share *= rng.uniform(1.00, 1.35)

        shares[0] = property_share
        shares = shares / shares.sum()

        component_values = total_wealth * shares
        property_val, pension_val, financial_val, physical_val = map(float, component_values)

        households.append({
            "household_id": hh_id,
            "region": region,
            "age_band_head": age_band,
            "head_age": head_age,
            "married_or_cohabiting": married,
            "num_adults": n_adults,
            "retired_household": retired,
            "tenure": tenure,
            "archetype": archetype,
            "annual_household_income": round(annual_income, 2),
            "total_wealth": round(total_wealth, 2),
            "property_wealth": round(property_val, 2),
            "pension_wealth": round(pension_val, 2),
            "financial_wealth": round(financial_val, 2),
            "physical_wealth": round(physical_val, 2),
        })

        # Persons
        p1_id = f"P{i+1:06d}_1"
        persons.append({
            "person_id": p1_id,
            "household_id": hh_id,
            "role": "primary",
            "age": head_age,
            "employment_status": "retired" if retired else ("employed" if annual_income > 18_000 else "inactive"),
            "personal_income": round(annual_income * (0.55 if married else 1.0), 2),
        })

        spouse_id = None
        if married:
            spouse_id = f"P{i+1:06d}_2"
            spouse_age = int(np.clip(head_age + rng.integers(-7, 8), 18, 90))
            spouse_income = annual_income * rng.uniform(0.25, 0.45) if not retired else annual_income * rng.uniform(0.30, 0.50)
            persons.append({
                "person_id": spouse_id,
                "household_id": hh_id,
                "role": "spouse",
                "age": spouse_age,
                "employment_status": "retired" if retired and spouse_age >= 60 else ("employed" if spouse_income > 15_000 else "inactive"),
                "personal_income": round(spouse_income, 2),
            })

        # Assets and ownership
        def add_asset(asset_type: str, value: float, owners: List[Tuple[str, float]], joint: bool) -> None:
            asset_id = f"A{len(assets)+1:07d}"
            assets.append({
                "asset_id": asset_id,
                "household_id": hh_id,
                "asset_type": asset_type,
                "asset_value": round(float(max(value, 0.0)), 2),
                "is_joint": joint,
            })
            for owner_id, share in owners:
                ownership_links.append({
                    "asset_id": asset_id,
                    "household_id": hh_id,
                    "owner_person_id": owner_id,
                    "ownership_share": float(share),
                })

        # Property
        if tenure in {"mortgage", "own_outright"} and property_val > 1_000:
            if married and rng.random() < 0.78:
                add_asset("primary_residence", property_val, [(p1_id, 0.5), (spouse_id, 0.5)], True)
            else:
                owner = p1_id if (not married or rng.random() < 0.65) else spouse_id
                add_asset("primary_residence", property_val, [(owner, 1.0)], False)

        # Pension: almost always personal, split across adults if married
        if pension_val > 250:
            if married:
                split = rng.uniform(0.40, 0.70)
                add_asset("pension", pension_val * split, [(p1_id, 1.0)], False)
                add_asset("pension", pension_val * (1 - split), [(spouse_id, 1.0)], False)
            else:
                add_asset("pension", pension_val, [(p1_id, 1.0)], False)

        # Financial wealth: mix of current/savings/brokerage
        if financial_val > 250:
            cash_share = rng.uniform(0.30, 0.65)
            brokerage_share = rng.uniform(0.10, 0.40)
            savings_share = max(0.05, 1 - cash_share - brokerage_share)
            fin_parts = {
                "current_account": financial_val * cash_share,
                "savings_account": financial_val * savings_share,
                "brokerage": financial_val * brokerage_share,
            }

            for asset_type, value in fin_parts.items():
                if value <= 100:
                    continue

                if asset_type == "brokerage":
                    # brokerage more often personal
                    if married and rng.random() < 0.22:
                        add_asset(asset_type, value, [(p1_id, 0.5), (spouse_id, 0.5)], True)
                    else:
                        owner = p1_id if (not married or rng.random() < 0.60) else spouse_id
                        add_asset(asset_type, value, [(owner, 1.0)], False)
                else:
                    # current/savings can be joint
                    if married and rng.random() < 0.48:
                        add_asset(asset_type, value, [(p1_id, 0.5), (spouse_id, 0.5)], True)
                    else:
                        owner = p1_id if (not married or rng.random() < 0.60) else spouse_id
                        add_asset(asset_type, value, [(owner, 1.0)], False)

        # Physical wealth: model at household/joint level by splitting equally if married
        if physical_val > 250:
            if married:
                add_asset("vehicles_and_contents", physical_val, [(p1_id, 0.5), (spouse_id, 0.5)], True)
            else:
                add_asset("vehicles_and_contents", physical_val, [(p1_id, 1.0)], False)

    hh_df = pd.DataFrame(households)
    person_df = pd.DataFrame(persons)
    asset_df = pd.DataFrame(assets)
    own_df = pd.DataFrame(ownership_links)

    return hh_df, person_df, asset_df, own_df


# ------------------------------------------
# Validation / evaluation helpers
# ------------------------------------------

def validate_synthetic(
    households: pd.DataFrame,
    assets: pd.DataFrame,
    ownership_links: pd.DataFrame,
) -> pd.DataFrame:
    results = []

    # ownership sums
    if not ownership_links.empty:
        own_sums = ownership_links.groupby("asset_id", as_index=False)["ownership_share"].sum()
        bad_own = own_sums.loc[~np.isclose(own_sums["ownership_share"], 1.0, atol=1e-6)]
        results.append({"check": "ownership_sum_to_1", "violations": int(len(bad_own)), "total": int(len(own_sums))})

    # household wealth reconciliation
    if not assets.empty:
        agg_assets = assets.groupby("household_id", as_index=False)["asset_value"].sum().rename(columns={"asset_value": "asset_sum"})
        merged = households.merge(agg_assets, on="household_id", how="left").fillna({"asset_sum": 0.0})
        merged["diff"] = (merged["asset_sum"] - merged["total_wealth"]).abs()
        bad_recon = merged.loc[merged["diff"] > 1.0]
        results.append({"check": "household_asset_sum_matches_total_wealth", "violations": int(len(bad_recon)), "total": int(len(merged))})

    # pension not joint
    if not assets.empty:
        bad_pension_joint = assets.loc[(assets["asset_type"] == "pension") & (assets["is_joint"] == True)]
        results.append({"check": "pension_not_joint", "violations": int(len(bad_pension_joint)), "total": int((assets["asset_type"] == "pension").sum())})

    return pd.DataFrame(results)


# ------------------------------------------
# Workbook inspection / mapping
# ------------------------------------------

def inspect_sources() -> None:
    ensure_dirs()

    frs_income_path = download(FRS_INCOME_XLS, CACHE_DIR / "frs_income_state_support_2024_2025.xlsx")
    frs_savings_path = download(FRS_SAVINGS_XLS, CACHE_DIR / "frs_savings_investments_2024_2025.xlsx")
    was_wealth_path = download(WAS_TOTAL_WEALTH_XLSX, CACHE_DIR / "was_total_wealth_2020_2022.xlsx")

    print("\nDownloaded:")
    print(f"  FRS income/state support: {frs_income_path}")
    print(f"  FRS savings/investments: {frs_savings_path}")
    print(f"  WAS total wealth: {was_wealth_path}")

    for label, path in [
        ("frs_income", frs_income_path),
        ("frs_savings", frs_savings_path),
        ("was_total_wealth", was_wealth_path),
    ]:
        print(f"\n=== SHEETS: {label} ===")
        try:
            sheets = list_workbook_sheets(str(path))
            print("\n".join(f"  - {s}" for s in sheets))
            previews = preview_workbook(str(path), max_rows=12)
            save_workbook_preview(previews, OUTPUT_DIR / f"{label}_preview.xlsx")
        except Exception as e:
            print(f"Failed to inspect {label}: {e}")


# ------------------------------------------
# Main
# ------------------------------------------

def main() -> None:
    ensure_dirs()

    # 1) Download + inspect official sources
    inspect_sources()

    # 2) Create editable calibration file if missing
    cal_path = OUTPUT_DIR / "calibration.json"
    wealth_cal, income_cal = load_calibration(cal_path)
    print(f"\nCalibration file: {cal_path.resolve()}")

    # 3) Generate synthetic data
    cfg = GeneratorConfig(n_households=10_000, seed=42)
    households, persons, assets, ownership = generate_households(wealth_cal, income_cal, cfg)

    # 4) Validate
    validation = validate_synthetic(households, assets, ownership)

    # 5) Save
    households.to_csv(OUTPUT_DIR / "synthetic_households.csv", index=False)
    persons.to_csv(OUTPUT_DIR / "synthetic_persons.csv", index=False)
    assets.to_csv(OUTPUT_DIR / "synthetic_assets.csv", index=False)
    ownership.to_csv(OUTPUT_DIR / "synthetic_ownership_links.csv", index=False)
    validation.to_csv(OUTPUT_DIR / "validation_summary.csv", index=False)

    # 6) Basic summaries
    summary = {
        "n_households": int(len(households)),
        "median_income": float(households["annual_household_income"].median()),
        "median_total_wealth": float(households["total_wealth"].median()),
        "p10_total_wealth": float(households["total_wealth"].quantile(0.10)),
        "p90_total_wealth": float(households["total_wealth"].quantile(0.90)),
        "asset_type_counts": assets["asset_type"].value_counts().to_dict(),
    }
    with open(OUTPUT_DIR / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\nDone.")
    print("Outputs written to:", OUTPUT_DIR.resolve())
    print(validation.to_string(index=False))


if __name__ == "__main__":
    main()

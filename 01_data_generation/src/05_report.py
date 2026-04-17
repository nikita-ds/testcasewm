from __future__ import annotations
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "artifacts"
TABLES = ART / "tables"
FIGS = ART / "figures"
FIGS.mkdir(parents=True, exist_ok=True)
REP = ART / "report"
REP.mkdir(parents=True, exist_ok=True)

def positive_clipped(series, upper_q=99.5):
    s = pd.Series(series).dropna().astype(float)
    s = s[s > 0]
    if len(s) == 0:
        return s
    upper = np.percentile(s, upper_q)
    return s[s <= upper]

def save_hist(series, title, path, log_x=False, bins=40, xlim=None):
    s = positive_clipped(series)
    if len(s) == 0:
        return
    plt.figure(figsize=(8,5))
    plt.hist(s, bins=bins)
    if log_x:
        plt.xscale("log")
    if xlim is not None:
        plt.xlim(*xlim)
    plt.title(title)
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()

def save_ratio_hist(numer, denom, title, path, *, log_x=True, bins=40, xlim=None, denom_min=1e-9):
    n = pd.Series(numer).dropna().astype(float)
    d = pd.Series(denom).dropna().astype(float)
    df = pd.DataFrame({"n": n, "d": d})
    df = df[(df["d"] > denom_min) & np.isfinite(df["n"]) & np.isfinite(df["d"])]
    if len(df) == 0:
        return
    r = df["n"] / df["d"]
    r = positive_clipped(r)
    if len(r) == 0:
        return
    plt.figure(figsize=(8,5))
    if log_x:
        rpos = r[r > 0]
        if len(rpos) == 0:
            return
        lo = float(rpos.min())
        hi = float(rpos.max())
        if xlim is not None:
            lo = max(lo, float(xlim[0]))
            hi = min(hi, float(xlim[1]))
        lo = max(lo, 1e-6)
        if hi <= lo:
            return
        edges = np.logspace(np.log10(lo), np.log10(hi), int(bins) + 1)
        plt.hist(rpos, bins=edges)
        plt.xscale("log")
    else:
        plt.hist(r, bins=bins)
    if xlim is not None:
        plt.xlim(*xlim)
    plt.title(title)
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()


def save_income_vs_assets_plot(hh: pd.DataFrame, path: Path) -> None:
    df = hh[["annual_household_gross_income", "investable_assets_total"]].copy()
    df = df.dropna()
    df["annual_household_gross_income"] = df["annual_household_gross_income"].astype(float)
    df["investable_assets_total"] = df["investable_assets_total"].astype(float)
    df = df[(df["annual_household_gross_income"] > 0) & (df["investable_assets_total"] > 0)]
    if len(df) == 0:
        return

    x = df["annual_household_gross_income"].to_numpy()
    y = df["investable_assets_total"].to_numpy()

    plt.figure(figsize=(7.5, 5.5))
    if len(df) >= 1500:
        plt.hexbin(x, y, gridsize=55, xscale="log", yscale="log", mincnt=1)
        cb = plt.colorbar()
        cb.set_label("count")
    else:
        plt.scatter(x, y, s=10, alpha=0.25)
        plt.xscale("log")
        plt.yscale("log")
    plt.xlabel("Annual household gross income")
    plt.ylabel("Investable assets total")
    plt.title("Income vs investable assets")
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()

def main():
    hh = pd.read_csv(TABLES / "households.csv")
    people = pd.read_csv(TABLES / "people.csv")
    distance = pd.read_csv(TABLES / "distance_to_priors.csv")
    scenario = pd.read_csv(TABLES / "scenario_coverage.csv")
    wealth_seg = pd.read_csv(TABLES / "wealth_segment_coverage.csv")
    rules = pd.read_csv(TABLES / "rule_violations.csv") if (TABLES / "rule_violations.csv").exists() else pd.DataFrame(columns=["household_id","rule_violation"])
    top5 = pd.read_csv(TABLES / "top5_anomalous_households.csv") if (TABLES / "top5_anomalous_households.csv").exists() else pd.DataFrame()

    save_hist(hh["annual_household_gross_income"], "Household annual gross income", FIGS / "income_hist.png", log_x=True)
    save_hist(hh["investable_assets_total"], "Investable assets total", FIGS / "investable_assets_hist.png", log_x=True)
    save_hist(hh["net_worth_proxy"], "Net worth proxy", FIGS / "net_worth_hist.png", log_x=True)
    save_hist(hh["monthly_mortgage_payment_total"], "Monthly mortgage payment total", FIGS / "mortgage_payment_hist.png", log_x=False)
    save_hist(hh["monthly_non_mortgage_payment_total"], "Monthly non-mortgage payment total", FIGS / "non_mortgage_payment_hist.png", log_x=False)

    save_income_vs_assets_plot(hh, FIGS / "income_vs_investable_assets.png")

    ratio = pd.Series(hh["mortgage_payment_to_income_ratio"]).dropna().astype(float)
    ratio = ratio[(ratio > 0) & (ratio <= 0.70)]
    if len(ratio) > 0:
        plt.figure(figsize=(8,5))
        plt.hist(ratio, bins=35)
        plt.xlim(0, 0.70)
        plt.title("Mortgage payment share of income")
        plt.tight_layout()
        plt.savefig(FIGS / "mortgage_payment_to_income_ratio_hist.png", dpi=180)
        plt.close()

    # Total debt service share of income (mortgage + non-mortgage).
    income_m = pd.Series(hh["annual_household_gross_income"]).dropna().astype(float) / 12.0
    debt_cost = pd.Series(hh["monthly_debt_cost_total"]).dropna().astype(float)
    tds = pd.DataFrame({"income_m": income_m, "debt_cost": debt_cost}).dropna()
    tds = tds[(tds["income_m"] > 1e-9) & (tds["debt_cost"] >= 0)]
    if len(tds) > 0:
        share = (tds["debt_cost"] / tds["income_m"]).astype(float)
        share = share[(share >= 0) & (share <= 0.95)]
        if len(share) > 0:
            plt.figure(figsize=(8,5))
            plt.hist(share, bins=35)
            plt.xlim(0, 0.95)
            plt.title("Total debt cost share of income")
            plt.tight_layout()
            plt.savefig(FIGS / "total_debt_cost_to_income_ratio_hist.png", dpi=180)
            plt.close()

    # Income / debt ratios (annual income divided by outstanding debt).
    save_ratio_hist(
        hh["annual_household_gross_income"],
        hh["loan_outstanding_total"],
        "Annual household income / total outstanding debt",
        FIGS / "income_to_total_debt_ratio_hist.png",
        log_x=True,
        bins=90,
    )

    net_debt = pd.Series(hh["loan_outstanding_total"]).astype(float) - pd.Series(hh["cash_and_cashlike_total"]).astype(float)
    save_ratio_hist(
        hh["annual_household_gross_income"],
        net_debt,
        "Annual household income / net debt (debt - cash)",
        FIGS / "income_to_net_debt_ratio_hist.png",
        log_x=True,
        bins=90,
    )

    plt.figure(figsize=(10,5))
    scenario.sort_values("count", ascending=False).plot(x="scenario", y="count", kind="bar", legend=False)
    plt.title("Scenario coverage")
    plt.tight_layout()
    plt.savefig(FIGS / "scenario_coverage.png", dpi=180)
    plt.close()

    plt.figure(figsize=(7,5))
    wealth_seg.sort_values("count", ascending=False).plot(x="wealth_segment", y="count", kind="bar", legend=False)
    plt.title("Wealth segment coverage")
    plt.tight_layout()
    plt.savefig(FIGS / "wealth_segment_coverage.png", dpi=180)
    plt.close()

    plt.figure(figsize=(8,5))
    hh["risk_tolerance"].value_counts(normalize=True).plot(kind="bar")
    plt.title("Risk tolerance share")
    plt.tight_layout()
    plt.savefig(FIGS / "risk_tolerance.png", dpi=180)
    plt.close()

    mort_pos = positive_clipped(hh["monthly_mortgage_payment_total"])
    nonmort_pos = positive_clipped(hh["monthly_non_mortgage_payment_total"])
    mort_med = float(mort_pos.median()) if len(mort_pos) > 0 else 0.0
    nonmort_med = float(nonmort_pos.median()) if len(nonmort_pos) > 0 else 0.0

    sanity = hh[["annual_household_gross_income", "investable_assets_total"]].dropna().astype(float)
    n_low_inc_high_assets = int(((sanity["annual_household_gross_income"] < 100000.0) & (sanity["investable_assets_total"] > 10000000.0)).sum())

    md = f"""# US RIA-like synthetic household report

## Counts
- households: {len(hh)}
- people: {len(people)}
- rule violations: {len(rules)}

## Medians
- annual household gross income: {hh['annual_household_gross_income'].median():,.2f}
- investable assets total: {hh['investable_assets_total'].median():,.2f}
- net worth proxy: {hh['net_worth_proxy'].median():,.2f}
- monthly mortgage payment total (positive only): {mort_med:,.2f}
- monthly non-mortgage payment total (positive only): {nonmort_med:,.2f}

## Figures

### Income vs assets

![Income vs investable assets](../figures/income_vs_investable_assets.png)

## Notes
- Income generation uses a smooth lognormal model anchored to the public median (from open Census ACS where available).
- Amount plots filter out zeros and clip the upper tail for readability.
- Mortgage payment to income ratio is capped at 70%.
- Total debt cost share of income is capped at 95% for plotting.
- Top 5 anomalous households are saved for manual review.
- Sanity: households with income < $100k and investable assets > $10M: {n_low_inc_high_assets}
"""
    (REP / "report.md").write_text(md, encoding="utf-8")
    print("Wrote report to", REP)
    print("Wrote figures to", FIGS)

if __name__ == "__main__":
    main()

from __future__ import annotations
from pathlib import Path
import json
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


def load_snapshot_date() -> pd.Timestamp | None:
    # Prefer computed priors (normal pipeline output), fall back to config priors.
    for p in (ART / "computed_priors.json", ROOT / "config" / "priors.json"):
        try:
            if not p.exists():
                continue
            obj = json.loads(p.read_text(encoding="utf-8"))
            meta = obj.get("meta") or {}
            snap = meta.get("snapshot_date")
            if snap:
                ts = pd.to_datetime(str(snap), errors="coerce")
                if pd.notna(ts):
                    return pd.Timestamp(ts).normalize()
        except Exception:
            continue
    return None

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
    if log_x:
        s = s[s > 0]
        if len(s) == 0:
            return
        lo = float(s.min())
        hi = float(s.max())
        lo = max(lo, 1e-9)
        if hi <= lo:
            return
        edges = np.logspace(np.log10(lo), np.log10(hi), int(bins) + 1)
        plt.hist(s, bins=edges)
        plt.xscale("log")
    else:
        plt.hist(s, bins=bins)
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
        plt.hexbin(
            x,
            y,
            gridsize=110,
            xscale="log",
            yscale="log",
            mincnt=1,
            bins="log",
            linewidths=0.0,
            edgecolors="none",
        )
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


def save_conditional_stacked_bar(
    df: pd.DataFrame,
    *,
    group_col: str,
    target_col: str,
    path: Path,
    title: str,
    top_n: int | None = None,
) -> None:
    x = df[[group_col, target_col]].dropna().copy()
    if len(x) == 0:
        return

    if top_n is not None:
        top_vals = x[target_col].value_counts().head(int(top_n)).index.tolist()
        x[target_col] = x[target_col].where(x[target_col].isin(top_vals), other="Other")

    tab = pd.crosstab(x[group_col], x[target_col], normalize="index")
    if tab.empty:
        return

    plt.figure(figsize=(10, 5.2))
    tab.plot(kind="bar", stacked=True, ax=plt.gca(), width=0.86)
    plt.ylim(0, 1)
    plt.ylabel("P(" + target_col + " | " + group_col + ")")
    plt.title(title)
    plt.legend(title=target_col, bbox_to_anchor=(1.02, 1.0), loc="upper left")
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()


def save_conditional_prob_bar(
    df: pd.DataFrame,
    *,
    group_col: str,
    bool_col: str,
    path: Path,
    title: str,
) -> None:
    x = df[[group_col, bool_col]].dropna().copy()
    if len(x) == 0:
        return

    # Try to coerce into 0/1.
    x[bool_col] = x[bool_col].astype(float)
    p = x.groupby(group_col)[bool_col].mean().sort_values(ascending=False)
    if len(p) == 0:
        return

    plt.figure(figsize=(10, 4.8))
    p.plot(kind="bar")
    plt.ylim(0, 1)
    plt.ylabel(f"P({bool_col}=1 | {group_col})")
    plt.title(title)
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()


def retirement_bucket_labels(series: pd.Series) -> pd.Categorical:
    vals = pd.Series(series).astype(float)
    bins = [-100.0, 0.0, 5.0, 10.0, 20.0, 30.0, 200.0]
    labels = ["Retired", "0-5y", "6-10y", "11-20y", "21-30y", "31y+"]
    return pd.cut(vals, bins=bins, labels=labels, include_lowest=True)


def save_retirement_proximity_plot(
    hh: pd.DataFrame,
    *,
    value_col: str,
    path: Path,
    title: str,
    ylabel: str,
    positive_only: bool = False,
) -> None:
    if "primary_years_to_retirement" not in hh.columns or value_col not in hh.columns:
        return
    df = hh[["primary_years_to_retirement", value_col]].dropna().copy()
    if len(df) == 0:
        return
    df["primary_years_to_retirement"] = df["primary_years_to_retirement"].astype(float)
    df[value_col] = df[value_col].astype(float)
    if positive_only:
        df = df[df[value_col] > 0]
    buckets = retirement_bucket_labels(df["primary_years_to_retirement"])
    grp = df.groupby(buckets, observed=False)[value_col].median().dropna()
    if len(grp) == 0:
        return
    plt.figure(figsize=(8.5, 4.8))
    grp.plot(marker="o")
    plt.title(title)
    plt.ylabel(ylabel)
    plt.xlabel("Years to retirement")
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close()


def save_age_vs_term_plots(
    hh: pd.DataFrame,
    liabilities: pd.DataFrame,
    protections: pd.DataFrame,
    *,
    snapshot: pd.Timestamp,
    path: Path,
) -> None:
    """Age vs remaining term (years) for mortgage and protection policies."""

    if "household_id" not in hh.columns or "primary_age" not in hh.columns:
        return
    age = hh[["household_id", "primary_age"]].dropna().copy()
    if len(age) == 0:
        return
    age["primary_age"] = age["primary_age"].astype(float)

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.0), sharex=True)

    # Mortgage: years remaining
    ax = axes[0]
    if liabilities is not None and len(liabilities) > 0 and "final_payment_date" in liabilities.columns:
        li = liabilities.copy()
        if "type" in li.columns:
            li = li[li["type"].astype(str) == "mortgage"]
        li["final_payment_date"] = pd.to_datetime(li["final_payment_date"], errors="coerce")
        li = li.dropna(subset=["household_id", "final_payment_date"])
        if len(li) > 0:
            li = li.merge(age, on="household_id", how="inner")
            li["years_remaining"] = (li["final_payment_date"] - snapshot).dt.days.astype(float) / 365.25
            li = li[np.isfinite(li["years_remaining"]) & (li["years_remaining"] >= 0) & (li["years_remaining"] <= 60)]
            if len(li) > 0:
                ax.scatter(li["primary_age"], li["years_remaining"], s=10, alpha=0.25)
    ax.set_title("Mortgage: age vs years remaining")
    ax.set_xlabel("Primary age (years)")
    ax.set_ylabel("Years remaining")
    ax.set_xlim(18, 100)
    ax.set_ylim(0, 60)

    # Protection policies: years remaining
    ax = axes[1]
    if protections is not None and len(protections) > 0 and "assured_until" in protections.columns:
        pp = protections.copy()
        pp["assured_until"] = pd.to_datetime(pp["assured_until"], errors="coerce")
        pp = pp.dropna(subset=["household_id", "assured_until"])
        if len(pp) > 0:
            pp = pp.merge(age, on="household_id", how="inner")
            pp["years_remaining"] = (pp["assured_until"] - snapshot).dt.days.astype(float) / 365.25
            pp = pp[np.isfinite(pp["years_remaining"]) & (pp["years_remaining"] >= 0) & (pp["years_remaining"] <= 60)]
            if len(pp) > 0:
                ax.scatter(pp["primary_age"], pp["years_remaining"], s=10, alpha=0.25)
    ax.set_title("Protection: age vs years remaining")
    ax.set_xlabel("Primary age (years)")
    ax.set_ylabel("Years remaining")
    ax.set_xlim(18, 100)
    ax.set_ylim(0, 60)

    plt.suptitle(f"Age vs remaining term (snapshot={snapshot.date().isoformat()})")
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close(fig)

def main():
    hh = pd.read_csv(TABLES / "households.csv")
    people = pd.read_csv(TABLES / "people.csv")
    liabilities = pd.read_csv(TABLES / "liabilities.csv") if (TABLES / "liabilities.csv").exists() else pd.DataFrame()
    protections = (
        pd.read_csv(TABLES / "protection_policies.csv")
        if (TABLES / "protection_policies.csv").exists()
        else pd.DataFrame()
    )
    distance = pd.read_csv(TABLES / "distance_to_priors.csv")
    scenario = pd.read_csv(TABLES / "scenario_coverage.csv")
    rules = pd.read_csv(TABLES / "rule_violations.csv") if (TABLES / "rule_violations.csv").exists() else pd.DataFrame(columns=["household_id","rule_violation"])
    top5 = pd.read_csv(TABLES / "top5_anomalous_households.csv") if (TABLES / "top5_anomalous_households.csv").exists() else pd.DataFrame()
    top5_if = pd.read_csv(TABLES / "top5_anomalous_households_iforest.csv") if (TABLES / "top5_anomalous_households_iforest.csv").exists() else pd.DataFrame()

    snap = load_snapshot_date()
    if snap is not None:
        save_age_vs_term_plots(
            hh,
            liabilities,
            protections,
            snapshot=snap,
            path=FIGS / "age_vs_terms_mortgage_and_protection.png",
        )

    save_hist(hh["annual_household_gross_income"], "Household annual gross income", FIGS / "income_hist.png", log_x=True)
    save_hist(hh["investable_assets_total"], "Investable assets total", FIGS / "investable_assets_hist.png", log_x=True)
    save_hist(hh["net_worth_proxy"], "Net worth proxy", FIGS / "net_worth_hist.png", log_x=True)
    save_hist(hh["monthly_mortgage_payment_total"], "Monthly mortgage payment total", FIGS / "mortgage_payment_hist.png", log_x=False)
    save_hist(hh["monthly_non_mortgage_payment_total"], "Monthly non-mortgage payment total", FIGS / "non_mortgage_payment_hist.png", log_x=False)

    save_income_vs_assets_plot(hh, FIGS / "income_vs_investable_assets.png")
    save_retirement_proximity_plot(
        hh,
        value_col="investable_assets_total",
        path=FIGS / "retirement_proximity_vs_assets.png",
        title="Closer to retirement -> higher investable assets",
        ylabel="Median investable assets total",
    )
    save_retirement_proximity_plot(
        hh,
        value_col="annual_household_gross_income",
        path=FIGS / "retirement_proximity_vs_income.png",
        title="Closer to retirement -> higher household income",
        ylabel="Median annual household gross income",
    )
    save_retirement_proximity_plot(
        hh,
        value_col="mortgage_outstanding_total",
        path=FIGS / "retirement_proximity_vs_mortgage_outstanding.png",
        title="Closer to retirement -> lower mortgage outstanding",
        ylabel="Median mortgage outstanding",
        positive_only=True,
    )
    save_retirement_proximity_plot(
        hh,
        value_col="monthly_mortgage_payment_total",
        path=FIGS / "retirement_proximity_vs_mortgage_payment.png",
        title="Closer to retirement -> lower mortgage payment",
        ylabel="Median monthly mortgage payment",
        positive_only=True,
    )
    if "has_mortgage_or_loan" in hh.columns:
        save_conditional_prob_bar(
            hh,
            group_col="scenario",
            bool_col="has_mortgage_or_loan",
            title="P(has_mortgage_or_loan | scenario)",
            path=FIGS / "condprob_has_mortgage_by_scenario.png",
        )

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

    # Debt service share of monthly expenses (what the user actually feels in cashflow).
    expenses_m = pd.Series(hh["monthly_expenses_total"]).dropna().astype(float)
    debt_cost = pd.Series(hh["monthly_debt_cost_total"]).dropna().astype(float)
    dte = pd.DataFrame({"expenses_m": expenses_m, "debt_cost": debt_cost}).dropna()
    dte = dte[(dte["expenses_m"] > 1e-9) & (dte["debt_cost"] >= 0)]
    if len(dte) > 0:
        share = (dte["debt_cost"] / dte["expenses_m"]).astype(float)
        share = share[(share >= 0) & (share <= 1.5)]
        if len(share) > 0:
            plt.figure(figsize=(8,5))
            plt.hist(share, bins=35)
            plt.xlim(0, 1.5)
            plt.title("Debt payments share of expenses")
            plt.tight_layout()
            plt.savefig(FIGS / "debt_cost_to_expenses_ratio_hist.png", dpi=180)
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

### Retirement proximity trends

![Closer to retirement -> higher investable assets](../figures/retirement_proximity_vs_assets.png)

![Closer to retirement -> higher household income](../figures/retirement_proximity_vs_income.png)

![Closer to retirement -> lower mortgage outstanding](../figures/retirement_proximity_vs_mortgage_outstanding.png)

![Closer to retirement -> lower mortgage payment](../figures/retirement_proximity_vs_mortgage_payment.png)

### Conditional probabilities

![P(has_mortgage_or_loan | scenario)](../figures/condprob_has_mortgage_by_scenario.png)

### Debt burden

![Debt payments share of expenses](../figures/debt_cost_to_expenses_ratio_hist.png)

### Age vs terms

![Age vs remaining term (mortgage and protection)](../figures/age_vs_terms_mortgage_and_protection.png)

## Notes
- Income generation uses a smooth lognormal model anchored to the public median (from open Census ACS where available).
- Amount plots filter out zeros and clip the upper tail for readability.
- Mortgage payment to income ratio is capped at 70%.
- Total debt cost share of income is capped at 95% for plotting.
- Top 5 anomalous households are saved for manual review (autoencoder; plus IsolationForest when available).
- Sanity: households with income < $100k and investable assets > $10M: {n_low_inc_high_assets}
"""
    (REP / "report.md").write_text(md, encoding="utf-8")
    print("Wrote report to", REP)
    print("Wrote figures to", FIGS)

if __name__ == "__main__":
    main()

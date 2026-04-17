from __future__ import annotations
from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "artifacts" / "generated"
REP = ROOT / "artifacts" / "report"
REP.mkdir(parents=True, exist_ok=True)

def main():
    hh = pd.read_csv(OUT / "households.csv")
    people = pd.read_csv(OUT / "people.csv")
    distance = pd.read_csv(OUT / "distance_to_priors.csv")
    scenario = pd.read_csv(OUT / "scenario_coverage.csv")
    rules = pd.read_csv(OUT / "rule_violations.csv") if (OUT / "rule_violations.csv").exists() else pd.DataFrame(columns=["household_id","rule_violation"])
    top5 = pd.read_csv(OUT / "top5_anomalous_households.csv") if (OUT / "top5_anomalous_households.csv").exists() else pd.DataFrame()

    plt.figure(figsize=(8,5))
    plt.hist(hh["annual_household_gross_income"], bins=40)
    plt.xscale("log")
    plt.title("Household annual gross income")
    plt.tight_layout()
    plt.savefig(REP / "income_hist.png", dpi=180)
    plt.close()

    plt.figure(figsize=(8,5))
    plt.hist(hh["investable_assets_total"], bins=40)
    plt.xscale("log")
    plt.title("Investable assets total")
    plt.tight_layout()
    plt.savefig(REP / "investable_assets_hist.png", dpi=180)
    plt.close()

    plt.figure(figsize=(8,5))
    plt.hist(hh["net_worth_proxy"], bins=40)
    plt.xscale("log")
    plt.title("Net worth proxy")
    plt.tight_layout()
    plt.savefig(REP / "net_worth_hist.png", dpi=180)
    plt.close()

    plt.figure(figsize=(10,5))
    scenario.sort_values("count", ascending=False).plot(x="scenario", y="count", kind="bar", legend=False)
    plt.title("Scenario coverage")
    plt.tight_layout()
    plt.savefig(REP / "scenario_coverage.png", dpi=180)
    plt.close()

    plt.figure(figsize=(8,5))
    hh["risk_tolerance"].value_counts(normalize=True).plot(kind="bar")
    plt.title("Risk tolerance share")
    plt.tight_layout()
    plt.savefig(REP / "risk_tolerance.png", dpi=180)
    plt.close()

    distance.to_csv(REP / "distance_to_priors.csv", index=False)
    scenario.to_csv(REP / "scenario_coverage.csv", index=False)
    rules.to_csv(REP / "rule_violations.csv", index=False)
    if len(top5) > 0:
        cols = [c for c in ["household_id","scenario","annual_household_gross_income","investable_assets_total","loan_outstanding_total","reconstruction_error"] if c in top5.columns]
        top5[cols].to_csv(REP / "top5_anomalous_households.csv", index=False)

    md = f"""# US RIA-like synthetic household report

## Counts
- households: {len(hh)}
- people: {len(people)}
- rule violations: {len(rules)}

## Medians
- annual household gross income: {hh['annual_household_gross_income'].median():,.2f}
- investable assets total: {hh['investable_assets_total'].median():,.2f}
- net worth proxy: {hh['net_worth_proxy'].median():,.2f}

## Notes
- Categorical stability is monitored with JS divergence.
- Continuous stability is monitored with PSI.
- Top 5 anomalous households are saved for manual review.
"""
    (REP / "report.md").write_text(md, encoding="utf-8")
    print("Wrote report to", REP)

if __name__ == "__main__":
    main()

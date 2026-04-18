# US RIA-like synthetic household report

## Counts
- households: 10000
- people: 18372
- rule violations: 0

## Medians
- annual household gross income: 176,408.46
- investable assets total: 710,598.90
- net worth proxy: 997,042.98
- monthly mortgage payment total (positive only): 3,962.40
- monthly non-mortgage payment total (positive only): 397.60

## Figures

### Income vs assets

![Income vs investable assets](../figures/income_vs_investable_assets.png)

### Conditional probabilities

![P(has_mortgage_or_loan | scenario)](../figures/condprob_has_mortgage_by_scenario.png)

### Debt burden

![Debt payments share of expenses](../figures/debt_cost_to_expenses_ratio_hist.png)

## Notes
- Income generation uses a smooth lognormal model anchored to the public median (from open Census ACS where available).
- Amount plots filter out zeros and clip the upper tail for readability.
- Mortgage payment to income ratio is capped at 70%.
- Total debt cost share of income is capped at 95% for plotting.
- Top 5 anomalous households are saved for manual review (autoencoder; plus IsolationForest when available).
- Sanity: households with income < $100k and investable assets > $10M: 0

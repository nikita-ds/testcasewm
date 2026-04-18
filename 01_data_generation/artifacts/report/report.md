# US RIA-like synthetic household report

## Counts
- households: 5000
- people: 9175
- rule violations: 0

## Medians
- annual household gross income: 133,173.45
- investable assets total: 496,674.35
- net worth proxy: 729,966.20
- monthly mortgage payment total (positive only): 2,869.51
- monthly non-mortgage payment total (positive only): 355.88

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
- Sanity: households with income < $100k and investable assets > $10M: 0

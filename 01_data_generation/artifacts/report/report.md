# US RIA-like synthetic household report

## Counts
- households: 5000
- people: 9177
- rule violations: 0

## Medians
- annual household gross income: 130,062.90
- investable assets total: 806,169.57
- net worth proxy: 1,127,772.42
- monthly mortgage payment total (positive only): 2,740.64
- monthly non-mortgage payment total (positive only): 362.27

## Notes
- Income generation uses a smooth lognormal model anchored to the public median (from open Census ACS where available).
- Amount plots filter out zeros and clip the upper tail for readability.
- Mortgage payment to income ratio is capped at 70%.
- Total debt cost share of income is capped at 95% for plotting.
- Top 5 anomalous households are saved for manual review.
- Sanity: households with income < $100k and investable assets > $10M: 24

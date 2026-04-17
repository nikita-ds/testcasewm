# Synthetic Data Generation for US RIA-like Households

## Objective

Generate realistic synthetic household-level financial data for advisor-served affluent US households, with a focus on internal consistency, plausible distributions, business-rule validity, and scenario coverage.

## Design decisions

### Target population
The synthetic population is intentionally **not** the general US population.  
It represents **affluent households typically served by US RIA firms**.

Working assumption:
- annual household gross income >= 2x US median household income

### Use of public data
Public US data are used as **anchors**, not exact targets:
- Census median household income (2023)
- Census SIPP household wealth (2023)
- BLS Consumer Expenditure Survey (2024)
- Federal Reserve SCF (2022)

These anchors define:
- scale
- floor values
- plausible ranges

Then distributions are shifted upward to reflect the advisor-served segment.

In the pipeline, priors are computed into a single persisted artifact:
- `artifacts/computed_priors.json` is the only priors input consumed downstream.
- `src/01_compute_priors.py --source acs` prefers open Census ACS via `api.census.gov` (cached under `artifacts/public_data_cache/`).
- `src/01_compute_priors.py --source config` builds priors from `config/priors.json` for offline/CI.

### Data model
Relational schema:
- households
- people
- income_lines
- assets
- liabilities
- protection_policies

This supports:
- individual vs joint assets
- multiple income streams
- multiple liabilities
- dates and lifecycle events
- mixed data types including multichoice fields

### Generation strategy
The generator combines:
1. **Scenario-based generation**
2. **Conditional sampling**
3. **Rule-based lifecycle constraints**

### Dates
Dates are derived, not sampled independently:
- date_of_birth from age
- employment_started after `date_rules.employment_start_after_age`
- move_in_date after `date_rules.move_in_after_age`
- child DOB implies parent age >= `date_rules.min_parent_age_at_birth`
- loan final payment date in the future for non-revolving loans

These date thresholds live in priors/config (not in generator code).

### Validation
#### Statistical validation
- Jensen-Shannon divergence for categorical variables
- **Population Stability Index (PSI)** for continuous variables
- median comparisons vs priors

PSI is used because it is widely adopted in financial services for stability and drift monitoring.

Rule of thumb:
- PSI < 0.10 : no meaningful shift
- 0.10 <= PSI < 0.25 : moderate shift
- PSI >= 0.25 : large shift

#### Business-rule validation
- age/date consistency
- household structure consistency
- loan/final-payment consistency
- alimony and marital-state coherence

### Determinism
For reproducible runs (especially in Docker), `run_all.py` supports:
- `SYNTH_SEED` (default: 42)
- `SYNTH_N_HOUSEHOLDS` (default: 5000)
- `SYNTH_PRIORS_SOURCE` (default: acs)

### Scenario coverage
The generator explicitly covers:
- young dual-income low-assets
- family with mortgage and children
- affluent couple with brokerage and pensions
- one high earner + one low earner
- pre-retirement wealthy
- self-employed / business-owner
- retired couple, high assets low income
- financially stressed with debt
- widowed
- divorced
- secondly wedded and paying alimony

### Anomaly detection
After generation and metric calculation, a real **PyTorch autoencoder** is trained on household-level numeric features.
The pipeline surfaces:
- anomaly scores
- top 5 anomalous households

These can then be inspected manually.

## Summary
The solution combines:
- public anchors
- affluent-segment assumptions
- conditional synthetic generation
- lifecycle-derived dates
- business rules
- PSI/JS monitoring
- scenario coverage
- anomaly detection

Additionally:
- income is generated from a smooth lognormal model anchored to the public median and calibrated to a target mean multiple.
- investable assets are capped relative to income (configurable) to reduce implausible combinations (e.g. very low income with ultra-high liquid assets).
- report includes a cross-plot `income_vs_investable_assets.png` to visually inspect income/asset consistency.

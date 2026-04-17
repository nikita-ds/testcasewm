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
- employment_started after age 16
- move_in_date after age 18
- child DOB implies parent age >= 16
- loan final payment date in the future for non-revolving loans

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

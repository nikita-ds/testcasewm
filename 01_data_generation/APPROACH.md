# Synthetic Data Generation for US RIA-like Households

This document explains (1) assumptions and how requirements are formalized in code, (2) validation and anomaly detection, and (3) external data and priors.

---

## 1) Assumptions and formalized requirements

### Segment and scope

Assumption: the target population is **affluent US households served by an RIA-like advisor** (not the general population).

Additional assumption: the target customer base is **conditioned on being affluent**, operationalized as:

- $\text{household income} \ge 2\times$ public median household income (the “affluent income floor”)

How this is formalized:

- Generation is scenario-driven (explicit household archetypes).
- Income and wealth distributions are shifted upward from public anchors.
- Wealth segments (affluent/HNW/ultra) have floors/caps and are sampled using explicit weights in `priors.wealth_segments`.
- The income floor is enforced in generation via `generator_params.income_floor` (resampling under a floor, not hard-clamping).

### Single source of truth and reproducibility

All downstream steps consume exactly one priors artifact:

- `artifacts/computed_priors.json`

It is produced by `src/01_compute_priors.py`:

- `--source acs`: uses open Census ACS via `api.census.gov`, caching raw responses under `artifacts/public_data_cache/`
- `--source config`: uses `config/priors.json` (offline/CI)

Determinism (especially for Docker) is controlled by env vars read by `run_all.py`:

- `SYNTH_SEED`
- `SYNTH_N_HOUSEHOLDS`
- `SYNTH_PRIORS_SOURCE` (`acs|config`)

### Data model (schema)

- Authoritative contract (fields + types + primary keys): `config/schema.json`
- Materialized tables: `artifacts/tables/*.csv`

Entities and relationships (PK/FK):

- `households` (PK `household_id`)
- `people` (PK `person_id`, FK `household_id`)
- `income_lines` (PK `income_line_id`, FK `household_id`)
- `assets` (PK `asset_id`, FK `household_id`)
- `liabilities` (PK `liability_id`, FK `household_id`)
- `protection_policies` (PK `policy_id`, FK `household_id`)

### Scenario catalog (coverage requirement)

Scenarios are explicitly enumerated in priors/config and sampled with weights (no “implicit” rare cases):

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

### Distributional requirements (formalized by model families)

Generator behavior is controlled by `computed_priors.json → generator_params` (to avoid hard-coded constants).
Key modeling choices are:

- **Income**: smooth **lognormal** anchored to public median (`generator_params.income_model`) and scaled by calibration (`generator_params.income_calibration.scale`) so that the mean income matches a target multiple of the public median.
- **Income floor (affluent conditioning)**: enforce $income \ge 2\times$ public median (`meta.affluent_income_floor`) via `generator_params.income_floor`.
- **Investable assets**: truncated **lognormal** per wealth segment (`generator_params.investable_assets_model.segments`).
- **Income ↔ assets coherence**: assets are clamped to a segment floor/cap and an income-based envelope (`generator_params.investable_assets_model.income_tie`) to avoid extreme mismatches.
- **Mortgage payment**: sampled as a bounded share of income using a beta-shaped distribution (`generator_params.mortgage_ratio_beta`), then capped by `generator_params.mortgage_terms.payment_ratio_cap`.
- **Mortgage tapering toward retirement**: as household age approaches `employment_model.retirement_age`, both mortgage payment burden and remaining term are smoothly reduced (`generator_params.mortgage_age_adjustment`).
- **Mortgage outstanding**: derived from payment × years remaining × multiplier, and constrained by LTV and income multiple caps; caps are applied via resampling under the cap (to avoid boundary-mass spikes in ratio histograms).
- **Non-mortgage debt**: payment sampled from bounded lognormal (`generator_params.non_mortgage_payment`), then outstanding via a multiplier.
- **Expenses**: bounded normal for expense-to-income ratio (`generator_params.expense_ratio_normal`).

### Lifecycle and date constraints

Dates are derived and constrained using priors (`date_rules`), not independently sampled:

- employment start not before `date_rules.employment_start_after_age`
- move-in not before `date_rules.move_in_after_age`
- child DOB implies parent age ≥ `date_rules.min_parent_age_at_birth`
- final loan payment date must be in the future for non-revolving liabilities

---

## 2) Validation, diagnostics, and anomaly detection

Outputs are separated by type:

- `artifacts/tables/` — CSV tables
- `artifacts/figures/` — PNG diagnostics
- `artifacts/report/` — `report.md` with embedded figures

### Business-rule validation

Implemented in `src/03_validate_and_score.py`, exported as `artifacts/tables/rule_violations.csv`.
Checks include:

- move-in before age threshold
- employment start before minimum working age
- employment start in the future
- youngest/oldest child DOB ordering
- parent under minimum age at child birth
- mortgage payment share above cap
- alimony present with incompatible marital status
- final payment date not in the future for non-credit-card liabilities

### Statistical validation

Implemented in `src/03_validate_and_score.py`, exported as `artifacts/tables/distance_to_priors.csv`.
Metrics include:

- Jensen–Shannon divergence for categorical distributions (example: marital status, risk tolerance)
- Population Stability Index (PSI) for continuous distributions (income, investable assets)
- summary statistics (medians and tail metrics)

Important: PSI is computed between:

- a **reference sample** simulated from the same priors-driven models (expected)
- the generated dataset (actual)

This makes PSI interpretable as “distance from priors” rather than “distance from a mismatched baseline”.

### Conditional probability histograms

Implemented in `src/05_report.py` (figures under `artifacts/figures/`):

- `condprob_scenario_given_wealth_segment.png` : $P(\text{scenario} \mid \text{wealth segment})$ (top scenarios + Other)
- `condprob_risk_given_wealth_segment.png` : $P(\text{risk tolerance} \mid \text{wealth segment})$
- `condprob_has_mortgage_by_scenario.png` : $P(\text{has mortgage} \mid \text{scenario})$

These are used to spot incoherent dependence structure (e.g., a “retired couple” scenario frequently having high mortgage incidence).

### Anomaly detection

Implemented in `src/04_autoencoder_anomalies.py`.
Two complementary detectors are run on household numeric features:

- **Autoencoder (PyTorch)** reconstruction error
- **IsolationForest (scikit-learn)** anomaly score

Artifacts:

- `artifacts/tables/anomaly_scores.csv` (both scores)
- `artifacts/tables/top5_anomalous_households.csv` (top‑5 by autoencoder)
- `artifacts/tables/top5_anomalous_households_iforest.csv` (top‑5 by IsolationForest, when available)

---

## 3) External data used for priors and defined priors

### External sources used

The only external source currently used programmatically is **US Census ACS via `api.census.gov`** (no API key).
Raw responses are cached under `artifacts/public_data_cache/` for reproducibility.

ACS-derived anchors include:

- Median household income (ACS variable `B19013_001E`)
- High-income tail counts used to derive “affluent bracket weights” (ACS table `B19001`, bins `$150k–$199,999` and `$200k+`)
- Owner-occupied home value bins used to derive home-value quantiles (ACS table `B25075`)
- State population weights used for residence state distribution

Note: for many attributes (household structure details, some booleans, asset mix, etc.) there is no single clean ACS variable/table used in this repo yet; those parts are currently driven by curated priors in `config/priors.json` and defaults in code. The design intent is to keep these priors explicit and swappable as more public-data-derived priors are added.

### Priors defined (what goes into computed_priors.json)

Priors are split into:

1) **Data-derived anchors** (from ACS where available)
2) **Curated priors and generator parameters** where there is no clean ACS counterpart

High-level keys include:

- `meta`: snapshot date, ACS dataset/year, public median income, affluent income floor
- `categoricals`: marital status, residence state, risk tolerance, tax bracket band
- `booleans`: has_children, has_mortgage, has_non_mortgage_debt, has_protection_policy
- `income_distribution`: bracket weights (used for back-compat fallback), plus public median
- `property_value_priors`: segment floors derived from ACS home-value quantiles
- `wealth_segments`: segment bounds and weights
- `date_rules`: lifecycle/date constraints
- `scenario_catalog`
- `generator_params`: the core “knobs” (distribution family parameters, caps, ties, scenario profiles/weights)

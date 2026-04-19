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
- **Investable assets**: generated as a **noisy multiple of income** (`generator_params.investable_assets_model.income_multiplier`):
	- $assets = income \times k_{base} \times k_2 \times scenario\_mult$
	- $k_2$ is sampled from a normal distribution calibrated by quantiles (no clipping; only rejects non-positive samples).
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

- `condprob_has_mortgage_by_scenario.png` : $P(\text{has mortgage} \mid \text{scenario})$

These are used to spot incoherent dependence structure (e.g., a “retired couple” scenario frequently having high mortgage incidence).

### Diagnostic figures (what each plot shows)

All figures are generated by `src/05_report.py` into `artifacts/figures/`:

- `income_hist.png` — distribution of annual household gross income (log-x).
- `investable_assets_hist.png` — distribution of investable assets total (log-x).
- `net_worth_hist.png` — distribution of net worth proxy (log-x; see definition in the field mapping below).
- `income_vs_investable_assets.png` — income vs investable assets cross-plot on log-log axes (spots coherence issues and boundary artifacts).
- `mortgage_payment_hist.png` — distribution of monthly mortgage payment (positive only).
- `non_mortgage_payment_hist.png` — distribution of monthly non-mortgage payment (positive only).
- `mortgage_payment_to_income_ratio_hist.png` — distribution of mortgage payment share of income (bounded to 0–0.70).
- `total_debt_cost_to_income_ratio_hist.png` — distribution of total debt service share of income (bounded to 0–0.95).
- `debt_cost_to_expenses_ratio_hist.png` — distribution of debt payments share of monthly expenses (bounded to 0–1.5).
- `income_to_total_debt_ratio_hist.png` — distribution of annual income divided by total outstanding debt (log-x).
- `income_to_net_debt_ratio_hist.png` — distribution of annual income divided by net debt (debt − cash; log-x).
- `scenario_coverage.png` — scenario counts bar chart (coverage sanity check).
- `risk_tolerance.png` — risk tolerance share bar chart.

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

The full data description is here  https://www2.census.gov/programs-surveys/cps/techdocs/cpsmar25.pdf  

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
- `property_value_priors`: a conservative global floor for primary-residence value
- `date_rules`: lifecycle/date constraints
- `scenario_catalog`
- `generator_params`: the core “knobs” (distribution family parameters, caps, ties, scenario profiles/weights)


## 4) How fields are generated (per schema)

Below is a human-readable “map” of field generation. Each line corresponds to one field.

**households.household_id** — synthetic household identifier like `HH000001`, `HH000002`, …

**households.scenario** — household scenario (archetype), sampled from `generator_params.scenarios` using weights `generator_params.scenario_weights`.

**households.country** — constant `US`.

**households.market** — constant `US_RIA`.

**households.marital_status** — categorical value sampled from `categoricals.marital_status`, with scenario-specific overrides via `generator_params.marital_overrides`.

**households.residence_state** — state sampled from `categoricals.residence_state`.

**households.move_in_date** — move-in date: take `snapshot_date` and shift backwards by a random number of years from `generator_params.move_in_model`, constrained to be “not earlier than age `date_rules.move_in_after_age`”.

**households.num_adults** — 1 or 2 (depending on whether a second adult was generated).

**households.num_dependants** — number of children, sampled from `generator_params.children_model` (may be 0).

**households.youngest_child_dob** — youngest child date of birth (if children exist), derived from `snapshot_date` and sampled child age; otherwise `null`.

**households.oldest_child_dob** — oldest child date of birth (if children exist); otherwise `null`.

**households.annual_household_gross_income** — annual gross household income: lognormal anchored to the public median (`generator_params.income_model`), then a scenario multiplier (`generator_params.scenario_income_adjustments`), then an “affluent floor” (resample until above `meta.affluent_income_floor` / `generator_params.income_floor`).

**households.monthly_expenses_total** — monthly expenses: start with “non-debt” expenses as a share of income (normal within min/max from `generator_params.expense_ratio_normal`), then add required debt payments; if a cap is needed, only the non-debt portion is reduced to fit.

**households.expense_to_income_ratio** — `monthly_expenses_total / (annual_household_gross_income/12)`.

**households.annual_alimony_paid** — annual alimony: non-zero only for scenarios `divorced` and `secondly_wedded_paying_alimony` per `generator_params.alimony_model`.

**households.has_mortgage_or_loan** — `true` if there is a mortgage or any non-mortgage debt.

**households.loan_outstanding_total** — total outstanding across mortgage and non-mortgage debt.

**households.monthly_debt_cost_total** — total monthly debt payments (mortgage + non-mortgage debt).

**households.monthly_mortgage_payment_total** — monthly mortgage payment (0 if there is no mortgage).

**households.monthly_non_mortgage_payment_total** — monthly non-mortgage debt payment (0 if there is no such debt).

**households.mortgage_payment_to_income_ratio** — mortgage payment share of monthly income; the payment ratio is sampled from a beta-like distribution in `generator_params.mortgage_ratio_beta` and capped by `generator_params.mortgage_terms.payment_ratio_cap`.

**households.property_value_total** — primary residence value: tied to `investable_assets_total` via a multiplier (`generator_params.property_model.default`) and floored by `property_value_priors.default_min`; scenario-specific multipliers may apply via `property_model.scenario_adjustments`.

**households.investable_assets_total** — investable assets: $income \times k_{base} \times k_2 \times scenario\_mult$ (see `generator_params.investable_assets_model.income_multiplier` and `investable_assets_model.scenario_adjustments`).

**households.retirement_assets_total** — slice of `investable_assets_total` allocated to retirement accounts using shares from `generator_params.asset_mix_model.default` plus scenario adjustments.

**households.cash_and_cashlike_total** — slice of `investable_assets_total` allocated to cash / cash-like.

**households.alternatives_total** — slice of `investable_assets_total` allocated to alternatives.

**households.net_worth_proxy** — proxy net worth: `investable_assets_total + property_value_total - mortgage_outstanding - non_mortgage_outstanding + U(0, investable_assets_total*mult)` (`generator_params.net_worth_proxy_model`).

**households.risk_tolerance** — categorical value from `categoricals.risk_tolerance`, with optional scenario overrides via `generator_params.risk_overrides`.

**households.investment_objectives** — random set of 1..K objectives drawn from `generator_params.objectives` (K capped by `generator_params.objectives_max_k`).

**households.tax_bracket_band** — categorical value from `categoricals.tax_bracket_band`.

**households.client_segment** — constant `affluent_ria_like`.

**people.person_id** — synthetic person identifier like `HH000001_P1`, `HH000001_P2`.

**people.household_id** — FK to `households.household_id`.

**people.client_no** — 1 for primary, 2 for spouse/partner.

**people.role** — `primary` or `spouse_partner`.

**people.date_of_birth** — date of birth: sample an age from the scenario profile (`generator_params.scenario_profiles`) plus jitter (`household_composition_model.dob_jitter_years`), then shift `snapshot_date` backwards by that age.

**people.employment_status** — employment status from `generator_params.employment_model` (with “retired” logic for age ≥ retirement_age or for the `retired` scenario).

**people.employment_started** — employment start date: sampled as “years ago” from `generator_params.employment_started_model`, constrained to be no earlier than age `date_rules.employment_start_after_age`; may be `null` for some inactive cases.

**people.desired_retirement_age** — normal distribution with min/max constraints (`generator_params.person_model.desired_retirement_age`).

**people.occupation_group** — sampled from `generator_params.person_model.occupation_group`, with a consistency constraint against `people.employment_status`:

- If `employment_status == retired`, then `occupation_group` is set to `retired`.
- If `employment_status == employed`, then `occupation_group` is never `retired`.

**people.smoker** — Bernoulli draw using `generator_params.person_model.smoker_probability`.

**people.state_of_health** — categorical value from `generator_params.person_model.state_of_health`.

**people.gross_annual_income** — per-person gross income: household income split across adults using `generator_params.spouse_income_split`.

**income_lines.income_line_id** — synthetic income line identifier `HH000001_I1`, `HH000001_I2`, …

**income_lines.household_id** — FK to `households.household_id`.

**income_lines.owner** — `client_1`, `client_2`, or `joint` based on `generator_params.income_lines_model.owner` probabilities.

**income_lines.source_type** — income source type from `generator_params.income_lines_model.sources`.

**income_lines.frequency** — pay frequency from `generator_params.income_lines_model.frequency`.

**income_lines.net_or_gross** — constant `gross`.

**income_lines.amount_annualized** — annualized amount: household income is split into N lines (N ~ Poisson) using fractions from `income_lines_model.split_fraction`; the final line takes the remainder.

**assets.asset_id** — synthetic asset identifier `HH000001_A1`, `HH000001_A2`, …

**assets.household_id** — FK to `households.household_id`.

**assets.owner** — `client_1`, `client_2`, or `joint` based on `generator_params.asset_model` probabilities and asset type.

**assets.asset_type** — one of: `brokerage`, `retirement`, `cash`, `alternatives`, `property`.

**assets.subtype** — subtype by asset_type (e.g., `taxable`, `401k_ira`, `bank`, `private_markets`, `primary_residence`).

**assets.provider_type** — provider type from `generator_params.asset_model.provider_types`.

**assets.value** — value: decompose `investable_assets_total` by mix shares, plus `property_value_total` for the primary residence.

**assets.is_joint** — `true` if `owner == joint`.

**liabilities.liability_id** — synthetic liability identifier `HH000001_L1`, `HH000001_L2`.

**liabilities.household_id** — FK to `households.household_id`.

**liabilities.type** — `mortgage`, `loan`, or `credit_card` (`credit_card` is used for the financial-stress scenario).

**liabilities.monthly_cost** — monthly payment: mortgage is derived from `mortgage_ratio_beta` plus constraints / retirement taper; non-mortgage debt uses `generator_params.non_mortgage_payment`.

**liabilities.outstanding** — outstanding balance: mortgage is a function of payment/term/rate with LTV and income-multiple constraints; non-mortgage debt uses `monthly_cost × multiplier`.

**liabilities.interest_rate** — interest rate: mortgage from `generator_params.mortgage_terms.rate_normal`, non-mortgage debt from `generator_params.liability_model.non_mortgage_interest_rate`.

**liabilities.final_payment_date** — final payment date: for mortgages `snapshot_date + years_remaining`; for `credit_card` it is `null`; for `loan` it is `snapshot_date + U(min,max)` years.

Protection policies (`protection_policies.*`) represent synthetic insurance-like coverages (e.g., life / disability / long-term-care style). They exist to make household cashflow and “risk protection footprint” more realistic: policies create a recurring premium (monthly cost) and a coverage amount/duration, which are commonly relevant in wealth management planning and downstream analytics.

**protection_policies.policy_id** — synthetic policy identifier `HH000001_PP1`.

**protection_policies.household_id** — FK to `households.household_id`.

**protection_policies.owner** — currently fixed to `client_1`.

**protection_policies.policy_type** — policy type sampled from `generator_params.protection_model.policy_types`.

**protection_policies.monthly_cost** — monthly premium: `amount_assured × U(min,max)` where the rate comes from `protection_model.monthly_cost_rate`.

**protection_policies.amount_assured** — coverage amount: `max(assured_min, annual_household_gross_income × U(min,max))`, where the multiplier comes from `protection_model.assured_income_mult`.

**protection_policies.assured_until** — coverage end date: `snapshot_date + U(min,max)` years (`protection_model.assured_until_years`).

# Synthetic Data Generation for US RIA-like Households

## Objective

Generate realistic synthetic household-level financial data for an affluent US RIA-like segment, with a focus on:

- internal consistency across tables (households/people/assets/liabilities)
- smooth, plausible distributions (no obvious “stepped” artifacts)
- explicit scenario coverage
- rule-based validity and diagnostics

## What this pipeline actually does

### Single source of truth: priors

All downstream steps consume exactly one priors artifact:

- `artifacts/computed_priors.json`

It is produced by `src/01_compute_priors.py`:

- `--source acs`: fetches open Census ACS via `api.census.gov` and caches raw API responses under `artifacts/public_data_cache/`
- `--source config`: uses `config/priors.json` (offline/CI friendly)

In ACS mode, the computed priors are a deep-merge of:

- public anchors (medians/quantiles) derived from the API response
- curated generation knobs (`generator_params`) to keep the generator stable and explainable

### Target population

This dataset is intentionally **not** the general US population.
It targets **affluent households typically served by US RIA firms**.

Operationally, the segment is enforced by:

- income model anchored to public median but shifted upward (see “Income model”)
- wealth segments with floors and caps
- scenario-specific adjustments

### Config-first generator knobs (no “magic constants”)

The generator reads its behavior from:

- `computed_priors.json` → `generator_params` (plus categorical/boolean priors)

This includes the “knobs” that would otherwise become hard-coded constants:

- scenario catalog + weights
- household composition rules (couple/kids heuristics, spouse age ranges, DOB jitter)
- income model configuration
- assets model and income↔assets tie
- mortgage/non-mortgage debt models and caps
- expense model
- property model

### Pipeline entrypoint and determinism

The default entrypoint is `run_all.py`, typically executed via Docker Compose.
Reproducibility is controlled by environment variables (read by `run_all.py` and passed to scripts):

- `SYNTH_SEED` (default: 42)
- `SYNTH_N_HOUSEHOLDS` (default: 5000)
- `SYNTH_PRIORS_SOURCE` (default: `acs`, choices: `acs|config`)

`docker-compose.yml` forwards these variables into the container (with defaults), so a `.env` file or shell env can control runs.

## Data model

Relational schema (CSV outputs):

- Authoritative contract (fields + types + primary keys): `config/schema.json`
- Materialized outputs: `artifacts/tables/*.csv`

- households
- people
- income_lines
- assets
- liabilities
- protection_policies

### Schema summary (keys and relationships)

- `households` (PK: `household_id`)
	- Household-level aggregates and derived metrics (income, expenses, debt totals, investable totals, ratios, scenario/segment labels)
- `people` (PK: `person_id`, FK: `household_id` → `households.household_id`)
	- Individuals in the household (role, DOB, employment, person-level income)
- `income_lines` (PK: `income_line_id`, FK: `household_id`)
	- Multiple income streams per household (owner, source_type, frequency, gross/net, annualized amount)
- `assets` (PK: `asset_id`, FK: `household_id`)
	- Asset inventory (type/subtype/provider, owner, joint flag, value)
- `liabilities` (PK: `liability_id`, FK: `household_id`)
	- Liability inventory (type, monthly cost, outstanding, interest rate, optional final payment date)
- `protection_policies` (PK: `policy_id`, FK: `household_id`)
	- Protection policies (policy type, owner, monthly cost, amount assured, optional end date)

This supports:

- individual vs joint ownership
- multiple income streams and liabilities per household
- date fields for lifecycle events
- mixed feature types (categoricals + multichoice)

## Generation strategy

The generator (`src/02_generate_data.py`) combines:

1) **Scenario-based generation** (explicit set of household archetypes)
2) **Conditional sampling** (values depend on scenario and wealth segment)
3) **Lifecycle/date constraints** (derived dates + rule checks)

### Scenarios

Covered scenarios are explicitly enumerated in priors (and mirrored in config):

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

### Income model

Income is generated as a **smooth lognormal** distribution anchored to a public median.
Then it is calibrated so that the generated mean matches a configurable multiple of that public median.

Goal: preserve a “public anchor” while producing an affluent segment without bracket/step artifacts.

### Investable assets model (and income↔assets consistency)

Investable assets are sampled by wealth segment (affluent/hnw/ultra) with segment-specific bounds.

To avoid implausible combinations (e.g., very low income with ultra-high investable assets), assets generation includes a configurable tie to income with a **lower and upper** envelope.
This is an explicit modeling choice to keep the dataset coherent for downstream consumers.

### Property, leverage, and debt

Property value is derived from investable assets and scenario adjustments, then bounded by segment-specific constraints.

Mortgage payment is sampled as a share of income (scenario-specific beta-like shape), then amortization-like logic derives an outstanding balance.

Important detail: caps are applied in a way that avoids visual artifacts.

- Some values are naturally bounded (e.g., payment share cap) to keep the domain realistic.
- For “outstanding balance” caps (LTV and income multiple), the generator avoids hard-clipping onto the boundary; it resamples under the cap. This prevents boundary-mass spikes that show up as tall single-bin peaks in ratio histograms.

Non-mortgage debt is generated from a smooth lognormal payment distribution with an outstanding multiplier.

### Dates and lifecycle rules

Dates are derived, not sampled independently:

- date_of_birth from age
- employment_started after `date_rules.employment_start_after_age`
- move_in_date after `date_rules.move_in_after_age`
- child DOB implies parent age ≥ `date_rules.min_parent_age_at_birth`
- loan final payment date in the future for non-revolving loans

All thresholds live in priors/config (not in generator code).

## Outputs and diagnostics

Artifacts are separated by type:

- `artifacts/tables/` — CSV tables
- `artifacts/figures/` — PNG figures
- `artifacts/report/` — report markdown
- `artifacts/public_data_cache/` — raw public API responses cache

### Validation

Statistical validation (`src/03_validate_and_score.py`):

- Jensen–Shannon divergence for categorical distributions
- Population Stability Index (PSI) for continuous distributions
- median comparisons vs priors

Rule-of-thumb PSI thresholds (common in financial services):

- PSI < 0.10: no meaningful shift
- 0.10 ≤ PSI < 0.25: moderate shift
- PSI ≥ 0.25: large shift

Business-rule validation:

- age/date consistency
- household structure consistency
- loan/final-payment consistency
- alimony and marital-state coherence

### Anomaly detection

An optional anomaly step trains a small PyTorch autoencoder on household-level numeric features.
The pipeline surfaces anomaly scores and exports top anomalous households for inspection.

### Reporting

The report step (`src/05_report.py`) produces:

- distribution histograms and ratio plots
- a cross-plot `income_vs_investable_assets.png` for spotting incoherent income/asset pairs

The generated report markdown embeds the figures so the cross-plot is visible in the report.

## Summary

This approach is intentionally “config- and priors-driven”:

- public anchors (ACS + cached raw responses)
- a single computed priors artifact consumed by all steps
- generator behavior controlled via `generator_params` rather than hard-coded constants
- deterministic runs via env vars (especially for Docker)
- diagnostics: PSI/JS, rule violations, anomalies, and report figures (including income↔assets cross-plot)

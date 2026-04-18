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

---

## 4) Как генерятся поля (по схеме)

Ниже — человекочитаемая “карта” генерации полей. Каждая строка — одно поле.

**households.household_id** — синтетический идентификатор домохозяйства вида `HH000001`, `HH000002`, …

**households.scenario** — сценарий (архетип) домохозяйства, выбирается из `generator_params.scenarios` по весам `generator_params.scenario_weights`.

**households.country** — константа `US`.

**households.market** — константа `US_RIA`.

**households.marital_status** — категориальное значение из `categoricals.marital_status` с принудительными переопределениями для отдельных сценариев (`generator_params.marital_overrides`).

**households.residence_state** — выбор штата по распределению `categoricals.residence_state`.

**households.move_in_date** — дата заселения: берётся `snapshot_date` и сдвигается назад на случайное число лет из `generator_params.move_in_model`, с ограничением “не раньше возраста `date_rules.move_in_after_age`”.

**households.num_adults** — 1 или 2 (в зависимости от того, сгенерирован ли второй взрослый).

**households.num_dependants** — число детей, сэмплируется из `generator_params.children_model` и может быть 0.

**households.youngest_child_dob** — дата рождения самого младшего ребёнка (если дети есть), рассчитывается от `snapshot_date` и возраста ребёнка; иначе `null`.

**households.oldest_child_dob** — дата рождения самого старшего ребёнка (если дети есть); иначе `null`.

**households.annual_household_gross_income** — годовой валовый доход домохозяйства: логнормаль, привязанная к публичной медиане (`generator_params.income_model`), затем сценарный мультипликатор (`generator_params.scenario_income_adjustments`), затем “affluent floor” (resample под `meta.affluent_income_floor` / `generator_params.income_floor`).

**households.monthly_expenses_total** — ежемесячные расходы: сначала “не-долговые” расходы как доля дохода (нормаль в рамках min/max из `generator_params.expense_ratio_normal`), затем добавляются обязательные платежи по долгам; при необходимости режется только не-долговая часть, чтобы уложиться в cap.

**households.expense_to_income_ratio** — `monthly_expenses_total / (annual_household_gross_income/12)`.

**households.annual_alimony_paid** — алименты в год: ненулевые только для сценариев `divorced` и `secondly_wedded_paying_alimony` по `generator_params.alimony_model`.

**households.has_mortgage_or_loan** — `true`, если есть ипотека или не-ипотечный долг.

**households.loan_outstanding_total** — сумма outstanding по ипотеке и не-ипотечному долгу.

**households.monthly_debt_cost_total** — сумма ежемесячных платежей (ипотека + не-ипотечный долг).

**households.monthly_mortgage_payment_total** — ежемесячный ипотечный платёж (0, если ипотеки нет).

**households.monthly_non_mortgage_payment_total** — ежемесячный платёж по не-ипотечному долгу (0, если долга нет).

**households.mortgage_payment_to_income_ratio** — доля ипотечного платежа от месячного дохода; платёж сэмплируется из beta-подобного распределения в рамках `generator_params.mortgage_ratio_beta` и ограничивается `generator_params.mortgage_terms.payment_ratio_cap`.

**households.property_value_total** — стоимость основного жилья: зависит от `investable_assets_total` через мультипликатор (`generator_params.property_model.default`) и ограничивается floor `property_value_priors.default_min`; для отдельных сценариев применяется дополнительный множитель (`property_model.scenario_adjustments`).

**households.investable_assets_total** — инвестируемые активы: $income \times k_{base} \times k_2 \times scenario\_mult$ (см. `generator_params.investable_assets_model.income_multiplier` + `investable_assets_model.scenario_adjustments`).

**households.retirement_assets_total** — часть `investable_assets_total`, выделенная под пенсионные счета по долям из `generator_params.asset_mix_model.default` и сценарным корректировкам.

**households.cash_and_cashlike_total** — часть `investable_assets_total`, выделенная под кэш/кэш‑аналоги.

**households.alternatives_total** — часть `investable_assets_total`, выделенная под альтернативы.

**households.net_worth_proxy** — прокси‑чистая стоимость: `investable_assets_total + property_value_total - mortgage_outstanding - non_mortgage_outstanding + U(0, investable_assets_total*mult)` (`generator_params.net_worth_proxy_model`).

**households.risk_tolerance** — категориальное значение из `categoricals.risk_tolerance`, с возможным override для отдельных сценариев (`generator_params.risk_overrides`).

**households.investment_objectives** — случайный набор 1..K целей из `generator_params.objectives` (K ограничен `generator_params.objectives_max_k`).

**households.tax_bracket_band** — категориальное значение из `categoricals.tax_bracket_band`.

**households.client_segment** — константа `affluent_ria_like`.

**people.person_id** — синтетический идентификатор человека вида `HH000001_P1`, `HH000001_P2`.

**people.household_id** — FK на `households.household_id`.

**people.client_no** — 1 для primary, 2 для spouse/partner.

**people.role** — `primary` или `spouse_partner`.

**people.date_of_birth** — дата рождения: берётся возраст из профиля сценария (`generator_params.scenario_profiles`) + джиттер (`household_composition_model.dob_jitter_years`), затем `snapshot_date` сдвигается назад на возраст.

**people.employment_status** — статус занятости из `generator_params.employment_model` (с логикой “retired” при возрасте ≥ retirement_age или для сценария retired).

**people.employment_started** — дата начала работы: сэмплируется как “years ago” из `generator_params.employment_started_model`, при этом не раньше возраста `date_rules.employment_start_after_age`; для части inactive может быть `null`.

**people.desired_retirement_age** — нормаль с ограничениями min/max (`generator_params.person_model.desired_retirement_age`).

**people.occupation_group** — выбор из списков `generator_params.person_model.occupation_group`.

**people.smoker** — Бернулли по `generator_params.person_model.smoker_probability`.

**people.state_of_health** — категориальное значение из `generator_params.person_model.state_of_health`.

**people.gross_annual_income** — доход конкретного клиента: домохозяйственный доход делится между взрослыми по `generator_params.spouse_income_split`.

**income_lines.income_line_id** — синтетический идентификатор строки дохода `HH000001_I1`, `HH000001_I2`, …

**income_lines.household_id** — FK на `households.household_id`.

**income_lines.owner** — `client_1`, `client_2` или `joint` по вероятностям `generator_params.income_lines_model.owner`.

**income_lines.source_type** — тип источника дохода из `generator_params.income_lines_model.sources`.

**income_lines.frequency** — частота выплат из `generator_params.income_lines_model.frequency`.

**income_lines.net_or_gross** — константа `gross`.

**income_lines.amount_annualized** — годовая сумма по линии: домохозяйственный доход разбивается на N линий (N ~ Poisson) с долями из `income_lines_model.split_fraction`; последняя линия добирает остаток.

**assets.asset_id** — синтетический идентификатор актива `HH000001_A1`, `HH000001_A2`, …

**assets.household_id** — FK на `households.household_id`.

**assets.owner** — `client_1`, `client_2` или `joint` по вероятностям из `generator_params.asset_model` и типу актива.

**assets.asset_type** — один из: `brokerage`, `retirement`, `cash`, `alternatives`, `property`.

**assets.subtype** — подтип по asset_type (например `taxable`, `401k_ira`, `bank`, `private_markets`, `primary_residence`).

**assets.provider_type** — провайдер из `generator_params.asset_model.provider_types`.

**assets.value** — стоимость: декомпозиция `investable_assets_total` по долям + отдельно `property_value_total`.

**assets.is_joint** — `true`, если `owner == joint`.

**liabilities.liability_id** — синтетический идентификатор обязательства `HH000001_L1`, `HH000001_L2`.

**liabilities.household_id** — FK на `households.household_id`.

**liabilities.type** — `mortgage`, `loan` или `credit_card` (credit_card используется для сценария финансового стресса).

**liabilities.monthly_cost** — ежемесячный платёж: ипотека из `mortgage_ratio_beta` и ограничений/retirement‑taper, не-ипотечный долг из `generator_params.non_mortgage_payment`.

**liabilities.outstanding** — остаток долга: ипотека — функция платежа/срока/ставки с ограничениями LTV и income multiple; не-ипотечный долг — `monthly_cost × multiplier`.

**liabilities.interest_rate** — ставка: ипотека из `generator_params.mortgage_terms.rate_normal`, не-ипотечный долг из `generator_params.liability_model.non_mortgage_interest_rate`.

**liabilities.final_payment_date** — дата финального платежа: для ипотеки — `snapshot_date + years_remaining`; для `credit_card` — `null`; для `loan` — `snapshot_date + U(min,max)` лет.

**protection_policies.policy_id** — синтетический идентификатор полиса `HH000001_PP1`.

**protection_policies.household_id** — FK на `households.household_id`.

**protection_policies.owner** — сейчас фиксированно `client_1`.

**protection_policies.policy_type** — тип полиса из `generator_params.protection_model.policy_types`.

**protection_policies.monthly_cost** — месячная стоимость: `amount_assured × U(min,max)` из `protection_model.monthly_cost_rate`.

**protection_policies.amount_assured** — страховая сумма: max(`assured_min`, `annual_household_gross_income × U(min,max)`), где множитель из `protection_model.assured_income_mult`.

**protection_policies.assured_until** — дата окончания покрытия: `snapshot_date + U(min,max)` лет (`protection_model.assured_until_years`).

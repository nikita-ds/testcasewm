# Approach

This document describes how the `03_data_extraction` pipeline works: how ground truth is built, how structured data is extracted from dialogs, how errors are counted, and which artifacts are used for quality and error analysis.

## 1. Ground Truth

The goal of ground truth in `03` is to create one evaluation pair per dialog:

- `dialog`: the advisor-client dialog text;
- `profile`: the structured household profile used as the extraction target.

The main pairs file is created by `run.py` and written to:

```text
artifacts/ground_truth_pairs.jsonl
```

or to another directory when `OUTPUT_DIR` is set.

### Data Sources

The pipeline reads:

- dialogs from `REALISM_PASSED_DIR`;
- full synthetic profiles from `FINANCIAL_PROFILES_JSON`;
- optional dialog-grounded profiles from `GROUNDED_PROFILES_JSON`.

If a household exists in `GROUNDED_PROFILES_JSON`, that grounded profile is used as ground truth instead of the full synthetic profile. This is important because a dialog may mention only part of the full profile. The extractor should not be penalized for failing to recover fields that were never present in the dialog.

### Dialog-Grounded GT

A dialog-grounded profile is built from `DIALOG_*_evidence.json` files with:

```bash
python export_grounded_profiles.py \
  --dialogs-dir <dir-with-evidence-files> \
  --out-json <grounded_financial_profiles.json>
```

By default, only evidence items with `status="present"` are included. This means a field enters grounded GT only when it was explicitly found in the dialog. Approximate evidence can be included with `INCLUDE_APPROXIMATE_GROUNDED=1`, but this is disabled by default for honest extractor evaluation.

`run_pipeline.py` can build grounded GT automatically before pairing:

- `AUTO_EXPORT_GROUNDED_PROFILES=1`;
- `EVIDENCE_DIALOGS_DIR=<dir>`;
- `GROUNDED_PROFILES_JSON=<out-json>`;
- `FORCE_REBUILD_GROUNDED_PROFILES=1` when the file should be rebuilt.

### Pair Contents

Each row in `ground_truth_pairs.jsonl` contains:

- `household_id`;
- `dialog_id`;
- `scenario`;
- `profile`;
- `dialog`;
- `ground_truth_is_grounded`.

`ground_truth_is_grounded=true` means the scoring denominator will include only fields present in the grounded GT. This protects the evaluation from penalizing the extractor for facts that were not spoken in the dialog.

For diagnostic dataset plots, `run.py` still uses the full profile even when scoring uses grounded GT. This keeps income/assets/scenario distributions stable and representative of the generated household set.

## 2. Extraction

Extraction is performed by `extract_from_dialogs.py`. It reads `.txt` dialogs, the schema, and priors, then writes one structured JSON per dialog:

```text
artifacts/extracted/DIALOG_<household_id>.extracted.json
```

### Model and Prompt

The model is configured with `OPENAI_MODEL` or the `--model` argument. The current code default is:

```text
gpt-5.2
```

The system prompt is stored in:

```text
prompts/extraction_system_prompt.txt
```

The compact schema from `schema.json` is injected into the prompt. For categorical and multichoice fields, allowed values are also injected from the schema and priors so the model selects valid values instead of inventing new categories.

Core prompt rules:

- use only facts stated or strongly implied in the dialog;
- omit a field when it is not mentioned;
- if an entity record is clearly present, create the record even if some fields are unknown;
- return numbers for numeric fields and booleans for boolean fields;
- use `YYYY-MM-DD` for explicit dates;
- use the midpoint for ranges when no later precise value is given;
- use `owner=joint` only for explicit joint/shared/both-names language;
- for `provider_type`, choose the underlying institution rather than an aggregator/platform that merely displays the asset.

### Extracted Entities and Fields

The extractor returns a top-level JSON object with these keys:

- `households`;
- `people`;
- `income_lines`;
- `assets`;
- `liabilities`;
- `protection_policies`.

Fields come from `01_data_generation/config/schema.json`.

`households`:

```text
household_id, scenario, country, market, marital_status, residence_state, move_in_date,
primary_age, primary_years_to_retirement, secondary_age, secondary_years_to_retirement,
num_adults, num_dependants, youngest_child_dob, oldest_child_dob,
annual_household_gross_income, monthly_expenses_total, expense_to_income_ratio,
annual_alimony_paid, has_mortgage_or_loan, loan_outstanding_total,
mortgage_outstanding_total, non_mortgage_outstanding_total, monthly_debt_cost_total,
monthly_mortgage_payment_total, monthly_non_mortgage_payment_total,
mortgage_payment_to_income_ratio, property_value_total, investable_assets_total,
retirement_assets_total, cash_and_cashlike_total, alternatives_total, net_worth_proxy,
risk_tolerance, investment_objectives, tax_bracket_band, client_segment,
household_head_email, household_head_mobile_phone
```

`people`:

```text
person_id, household_id, client_no, role, title, first_name, middle_names, last_name,
known_as, pronouns, place_of_birth, nationality, gender, legal_sex, home_phone,
mobile_phone, email_address, date_of_birth, employment_status, employment_started,
desired_retirement_age, occupation_group, smoker, state_of_health, gross_annual_income
```

`income_lines`:

```text
income_line_id, household_id, owner, source_type, frequency, net_or_gross, amount_annualized
```

`assets`:

```text
asset_id, household_id, owner, asset_type, subtype, provider_type, value, is_joint
```

`liabilities`:

```text
liability_id, household_id, type, monthly_cost, outstanding, interest_rate, final_payment_date
```

`protection_policies`:

```text
policy_id, household_id, owner, policy_type, monthly_cost, amount_assured, assured_until
```

### Extraction Post-Processing

After the LLM call, the extractor performs several deterministic steps:

- unwrap common response wrappers such as `{"result": ...}` or `{"extracted": ...}`;
- coerce values to schema types;
- drop unknown fields and unknown entities;
- normalize categorical values and primary key formats;
- compute derived household fields from liabilities where applicable;
- save raw attempts and the final extracted JSON.

If an attempt returns an invalid shape or an empty extraction, the script retries up to `EXTRACTION_RETRY_LIMIT`.

### Rescue Passes

The current implementation has two targeted rescue passes:

- liability/protection rescue: used when the dialog clearly contains mortgage, loan, card, or policy hints, but the extractor returned empty `liabilities` or `protection_policies`;
- asset/owner rescue: used when assets are missing `owner`, `is_joint`, or `provider_type`, or people are missing `occupation_group`, and the dialog contains relevant hints.

Rescue does not replace the whole extraction. It extracts only a narrow set of entities/fields and merges them back into the base result, which prevents one local repair from changing unrelated parts of the profile.

There is also a deterministic repair for a specific bank-type retirement asset pattern, where the dialog text indicates the record should be cash/bank account rather than retirement.

### Evaluated Improvement: Asset Rescue Overwrite

The baseline discrepancy reports showed that most remaining extraction errors were concentrated in `assets`, especially `owner`, `is_joint`, `provider_type`, `asset_type`, and `subtype`.

The improvement keeps the existing narrow asset/owner rescue pass, but changes how it is merged:

- before: rescue values only filled missing base fields;
- after: when a rescue asset matches a base asset by exact extracted `value`, the rescue may overwrite `owner`, `is_joint`, `provider_type`, `asset_type`, and `subtype`.

This pass does **not** read ground truth, dialog-grounded profiles, evidence files, discrepancy tables, or evaluation results. It only consumes:

- the baseline extracted JSON;
- the asset/owner rescue output generated from the dialog text.

The main Docker pipeline now evaluates both versions:

- baseline scoring is written to `baseline/merged/merged_ground_truth_extracted.jsonl`;
- improved scoring is written to `merged/merged_ground_truth_extracted.jsonl`;
- before/after deltas are written to `improvement_delta.json` and `improvement_delta.md`.

Train delta from `docker compose up --build`:

| Metric | Baseline | Improved | Delta |
| --- | ---: | ---: | ---: |
| Dialogs with 100% correct fields | 201/316 = 0.636 | 203/316 = 0.642 | +0.006 |
| Dialogs with >=95% correct fields | 296/316 = 0.937 | 297/316 = 0.940 | +0.003 |
| Dialogs with >=90% correct fields | 316/316 = 1.000 | 315/316 = 0.997 | -0.003 |
| Mean dialog field accuracy | 0.988 | 0.988 | +0.000 |
| Asset error rate | 1.9% | 1.8% | -0.1 pp |

OOS holdout delta from the same Docker pipeline with OOS environment variables:

| Metric | Baseline | Improved | Delta |
| --- | ---: | ---: | ---: |
| Dialogs with 100% correct fields | 58/99 = 0.586 | 59/99 = 0.596 | +0.010 |
| Dialogs with >=95% correct fields | 95/99 = 0.960 | 96/99 = 0.970 | +0.010 |
| Dialogs with >=90% correct fields | 99/99 = 1.000 | 99/99 = 1.000 | +0.000 |
| Mean dialog field accuracy | 0.987 | 0.988 | +0.001 |
| Asset error rate | 1.7% | 1.5% | -0.2 pp |

## 3. Error Counting

Evaluation is performed by `evaluate_extraction.py`; detailed discrepancy analysis is performed by `analyze_discrepancies.py`.

### Normalization Before Comparison

Before scoring, both sides are normalized:

- the ground truth profile;
- the extracted profile.

This reduces noise from primary key formats, categorical aliases, and trivial string differences.

### Record Pairing

For each entity, GT records must first be matched to extracted records.

Primary keys are used when possible. However, extractor-generated IDs can be unstable, so content-based pairing is enabled by default for several entities:

- `income_lines`;
- `people`;
- `assets`;
- `liabilities`;
- `protection_policies`.

Content pairing uses weighted similarity over meaningful fields. For example:

- assets: owner, asset_type, subtype, provider_type, value;
- income_lines: owner, source_type, frequency, net_or_gross, amount_annualized;
- people: client_no, role, employment_status, occupation_group, first_name, gross_annual_income;
- liabilities: type, final_payment_date, monthly_cost, outstanding, interest_rate;
- protection_policies: owner, policy_type, assured_until, monthly_cost, amount_assured.

If a record exists only in GT, its status is `gt_only`. If it exists only in extraction, its status is `ex_only`. If both sides are matched, its status is `both`.

### Value Comparison

Comparison is cell-by-cell over schema fields.

Rules:

- numeric fields (`continuous`, `integer`, `integer_nullable`) match when they differ by no more than `numeric_rel_tol`; the default is `0.01`, meaning 1%;
- booleans are compared as booleans;
- `date` and `date_nullable` fields are compared as normalized strings;
- `multichoice` fields are compared as sorted sets; strings may be separated by `|` or commas;
- other string/categorical fields are compared case-insensitively after trimming.

Two `None` values count as a match, but the scoring denominator depends on the GT mode.

### Grounded-Aware Denominator

If `ground_truth_is_grounded=true`, a field enters the denominator only when it was present in grounded GT. This is the key assumption for honest dialog-level evaluation: the extractor is not required to recover facts that were not present in the dialog.

If GT is not grounded, the denominator includes scoreable schema fields regardless of whether the GT value was `None`.

### Scoring Exclusions

By default, these fields are not scored:

- primary key fields;
- fields ending with `_id`;
- fields ending with `_ratio`;
- fields listed in `config/scoring_exclusions.json`.

The current exclusions file contains PII/person-detail fields that are either not central to extractor quality or create unnecessary scoring noise:

```text
households.household_head_email
households.household_head_mobile_phone
people.title
people.middle_names
people.last_name
people.known_as
people.pronouns
people.place_of_birth
people.nationality
people.gender
people.legal_sex
people.home_phone
people.mobile_phone
people.email_address
people.date_of_birth
people.employment_started
people.desired_retirement_age
people.smoker
people.state_of_health
```

ID fields can be included with `--include-ids`, but that is usually undesirable for extractor-quality evaluation: we care about semantic correctness, not whether the model guessed synthetic primary keys.

### Error Types

`analyze_discrepancies.py` breaks errors into:

- `missing_extracted`: GT has an expected value, but extraction did not provide it;
- `extra_extracted`: GT did not expect the field, but extraction filled it;
- `value_mismatch`: extraction provided a value, but it did not match GT;
- record-level statuses: `both`, `gt_only`, `ex_only`, `both_missing`.

For missing and extra values, the analysis also distinguishes:

- errors caused by record pairing (`gt_only` / `ex_only`);
- errors inside already matched records (`both`).

This helps separate "the model missed the entire asset" from "the model found the asset but got owner wrong."

## 4. Metrics, Tables, and Figures

The pipeline writes several layers of diagnostics.

### Dataset Plots

`run.py` writes:

- `figures/assets_hist.png`;
- `figures/income_hist.png`;
- `figures/scenario_distribution.png`.

These plots check the composition of the evaluation set: whether it is skewed by wealth, income, or scenario, and whether an OOS/test set resembles the expected population.

### Extraction Accuracy

`evaluate_extraction.py` writes:

- `merged/merged_ground_truth_extracted.jsonl`;
- `merged/accuracy_report.json`;
- `figures/extraction_accuracy_hist.png`.

`accuracy_report.json` contains:

- household count;
- scored household count;
- `numeric_rel_tol`;
- `include_ids`;
- `mean_fraction`.

The histogram shows the household-level accuracy distribution. It helps distinguish many small errors spread across households from a few severe outliers.

### Discrepancy Analysis

`analyze_discrepancies.py` writes:

- `discrepancy_summary.json`;
- `report/discrepancy_report.md`;
- `tables/discrepancy_field_stats.csv`;
- `tables/discrepancy_entity_record_pairing.csv`;
- `tables/discrepancy_record_pair_status.csv`;
- `tables/discrepancy_examples.csv`;
- `tables/value_mismatch_cells.csv`;
- `tables/discrepancy_missing_extracted_samples.csv`;
- `tables/discrepancy_extra_extracted_samples.csv`;
- `figures/discrepancy_worst_fields.png`;
- `figures/discrepancy_error_type_breakdown.png`;
- `figures/discrepancy_record_pairing.png`.

How to use these artifacts:

- `discrepancy_report.md` is the quick human-readable overview;
- `discrepancy_field_stats.csv` is the main file for ranking weak fields;
- `value_mismatch_cells.csv` is the best file for debugging specific wrong values;
- `discrepancy_entity_record_pairing.csv` shows whether the problem is missing/extra records rather than wrong field values;
- `discrepancy_error_type_breakdown.png` shows whether errors are dominated by missing values, extra values, or mismatches;
- `discrepancy_worst_fields.png` shows the weakest fields;
- `discrepancy_record_pairing.png` shows record-level recall/precision behavior by entity.

### Final Metrics Table

`compute_metrics.py` writes:

```text
metrics_table.txt
```

It contains two blocks:

- share of dialogs with `100%`, `>=95%`, and `>=90%` correct fields;
- per-entity rates: missed, errors, invented, total cells.

This table is useful as a high-level checkpoint for an OOS/test run. For root-cause analysis, go one layer deeper: first `discrepancy_report.md`, then the CSV tables.

## 5. OOS/Test Discipline

For a fair holdout test:

- generate OOS dialogs from households that were not used to tune the extractor or evaluator;
- write OOS outputs to a separate `OUTPUT_DIR`, for example `artifacts/OOS`;
- do not mix extracted JSON, merged files, figures, or metrics with tuning artifacts;
- use the same code, prompt, scoring exclusions, and thresholds;
- explicitly verify that household IDs do not overlap between the tuning extracted set and the OOS extracted set.

The current `run_pipeline.py` supports this through `OUTPUT_DIR`, `REALISM_PASSED_DIR`, `EVIDENCE_DIALOGS_DIR`, and `GROUNDED_PROFILES_JSON`.

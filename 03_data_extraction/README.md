# 03_data_extraction

Build a ground-truth pairs file from realism-passed dialogs.

## What it does
- Reads dialogs from `../02_dialogs_generation/artifacts/dialogs/realism_passed/`
- Reads financial profiles from `../02_dialogs_generation/artifacts/financial_profiles.json`
- Writes a single pairs file to `artifacts/ground_truth_pairs.jsonl`
- Writes figures to `artifacts/figures/`

## Run (Docker)
From this directory:

```bash
docker compose up --build
```

## Outputs
- `artifacts/ground_truth_pairs.jsonl` — one JSON object per line with:
  - `household_id`, `dialog_id`, `scenario`, `profile`, `dialog`
- `artifacts/figures/assets_hist.png`
- `artifacts/figures/income_hist.png`
- `artifacts/figures/scenario_distribution.png`
- `artifacts/summary.json`

## Config (optional env vars)
- `REALISM_PASSED_DIR` (default: `../02_dialogs_generation/artifacts/dialogs/realism_passed`)
- `FINANCIAL_PROFILES_JSON` (default: `../02_dialogs_generation/artifacts/financial_profiles.json`)
- `OUTPUT_DIR` (default: `./artifacts`)
- `PAIRS_BASENAME` (default: `ground_truth_pairs.jsonl`)

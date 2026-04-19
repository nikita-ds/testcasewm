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

This runs the full pipeline via `run_pipeline.py`:
- ground-truth pairing + basic plots
- LLM extraction (skips already-extracted when possible)
- merge + scoring + histogram
- discrepancy analysis report

## Run (Local)
- `python run.py` builds ground-truth pairs + plots, and if `artifacts/extracted/DIALOG_*.extracted.json` exists it also runs merge/eval/discrepancy analysis.
- Use `python run.py --reports-only` to skip merge/eval/discrepancy.

## Outputs
- `artifacts/ground_truth_pairs.jsonl` — one JSON object per line with:
  - `household_id`, `dialog_id`, `scenario`, `profile`, `dialog`
- `artifacts/figures/assets_hist.png`
- `artifacts/figures/income_hist.png`
- `artifacts/figures/scenario_distribution.png`
- `artifacts/merged/merged_ground_truth_extracted.jsonl`
- `artifacts/figures/extraction_accuracy_hist.png`
- `artifacts/report/discrepancy_report.md`
- `artifacts/tables/discrepancy_field_stats.csv`
- `artifacts/tables/discrepancy_entity_record_pairing.csv`
- `artifacts/figures/discrepancy_worst_fields.png`
- `artifacts/figures/discrepancy_error_type_breakdown.png`
- `artifacts/figures/discrepancy_record_pairing.png`
- `artifacts/summary.json`

## Config (optional env vars)
- `REALISM_PASSED_DIR` (default: `../02_dialogs_generation/artifacts/dialogs/realism_passed`)
- `FINANCIAL_PROFILES_JSON` (default: `../02_dialogs_generation/artifacts/financial_profiles.json`)
- `GROUNDED_PROFILES_JSON` (default: `../02_dialogs_generation/artifacts/grounded_financial_profiles.json`) — if present, `run.py` uses these sparse dialog-grounded profiles as GT (per-household) and marks rows with `ground_truth_is_grounded=true`.
- `OUTPUT_DIR` (default: `./artifacts`)
- `PAIRS_BASENAME` (default: `ground_truth_pairs.jsonl`)
- `AUTO_EXPORT_GROUNDED_PROFILES` (default: `1`) — if enabled, `run_pipeline.py` will generate `GROUNDED_PROFILES_JSON` from `*_evidence.json` artifacts before pairing.
- `EVIDENCE_DIALOGS_DIR` (default: `../02_dialogs_generation/artifacts/dialogs`) — where to look for `DIALOG_*_evidence.json`.
- `FORCE_REBUILD_GROUNDED_PROFILES` (default: `0`) — rebuild grounded profiles even if the output JSON already exists.
- `INCLUDE_APPROXIMATE_GROUNDED` (default: `0`) — also include evidence items with `status="approximate"`.

## Generate grounded GT (from evidence)
If you generated `*_evidence.json` artifacts in 02, you can export a sparse, dialog-grounded GT file (used by `GROUNDED_PROFILES_JSON`):

```bash
python export_grounded_profiles.py \
  --dialogs-dir ../02_dialogs_generation/artifacts/dialogs \
  --out-json ../02_dialogs_generation/artifacts/grounded_financial_profiles.json
```

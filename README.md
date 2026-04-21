# Synthetic Household Dialog Extraction Benchmark

This repository contains an end-to-end synthetic benchmark for financial household data extraction from advisor-client dialogs.

The pipeline has three main stages:

1. generate synthetic US RIA-like household financial profiles;
2. generate realistic advisor-client dialogs grounded in those profiles;
3. extract structured data from dialogs and evaluate extraction quality against dialog-grounded ground truth.

For a high-level visual overview, open [`approach.html`](approach.html) from the repository root.

## Repository Layout

```text
.
├── 00_initial_task/
│   └── Source task material and example transcript files.
├── 01_data_generation/
│   └── Synthetic household data generator, validation, diagnostics, and reports.
├── 02_dialogs_generation/
│   └── Dialog generation pipeline, evidence extraction, and realism checks.
├── 03_data_extraction/
│   └── Ground-truth pairing, LLM extraction, scoring, metrics, and discrepancy analysis.
└── approach.html
    └── High-level HTML report with methodology, plots, Train/holdout results, and links.
```

Each stage has its own `README.md` with deeper operational details:

- [`01_data_generation/README.md`](01_data_generation/README.md)
- [`02_dialogs_generation/README.md`](02_dialogs_generation/README.md)
- [`03_data_extraction/README.md`](03_data_extraction/README.md)

## Data Flow

```text
01_data_generation
  └── artifacts/tables/*.csv
        ↓
02_dialogs_generation/build_financial_dataset.py
  └── artifacts/financial_profiles.json
        ↓
02_dialogs_generation
  └── artifacts/dialogs/DIALOG_*.json|txt|evidence.json|metrics.json
  └── artifacts/dialogs/realism_passed/
        ↓
03_data_extraction/export_grounded_profiles.py
  └── grounded_financial_profiles.json
        ↓
03_data_extraction
  └── ground_truth_pairs.jsonl
  └── extracted/DIALOG_*.extracted.json
  └── merged/merged_ground_truth_extracted.jsonl
  └── metrics_table.txt
  └── report/ and tables/ discrepancy artifacts
```

The key design choice is that extraction evaluation uses dialog-grounded ground truth when available. This means the extractor is scored only on facts that were actually present in the dialog, not on every field in the full synthetic profile.

## Prerequisites

You can run the pipelines either with Docker Compose or locally with Python.

For local runs:

- Python 3.11+ is recommended.
- Install per-stage dependencies from each folder's `requirements.txt`.
- Set `OPENAI_API_KEY` for dialog generation and extraction.
- Set `DEEPSEEK_KEY` only if you want the optional DeepSeek realism gate in dialog generation.

For Docker runs:

- Install Docker and Docker Compose.
- Put required API keys into the relevant `.env` files:
  - `02_dialogs_generation/.env`
  - `03_data_extraction/.env`

## Stage 01: Generate Synthetic Household Data

Folder:

```bash
cd 01_data_generation
```

### Docker

```bash
docker compose up --build
```

Optional environment variables:

```bash
SYNTH_SEED=42 \
SYNTH_N_HOUSEHOLDS=5000 \
SYNTH_PRIORS_SOURCE=acs \
docker compose up --build
```

`SYNTH_PRIORS_SOURCE=acs` fetches public Census ACS aggregates and caches them under `artifacts/public_data_cache/`. Use `config` for offline/CI-style runs:

```bash
SYNTH_PRIORS_SOURCE=config docker compose up --build
```

### Local

```bash
pip install -r requirements.txt
python run_all.py
```

Example deterministic small run:

```bash
SYNTH_SEED=42 SYNTH_N_HOUSEHOLDS=200 SYNTH_PRIORS_SOURCE=config python run_all.py
```

### Main Outputs

- `artifacts/computed_priors.json`
- `artifacts/tables/households.csv`
- `artifacts/tables/people.csv`
- `artifacts/tables/income_lines.csv`
- `artifacts/tables/assets.csv`
- `artifacts/tables/liabilities.csv`
- `artifacts/tables/protection_policies.csv`
- `artifacts/tables/rule_violations.csv`
- `artifacts/tables/anomaly_scores.csv`
- `artifacts/figures/*.png`
- `artifacts/report/report.md`

Quality controls include business-rule validation, distance-to-priors diagnostics, and anomaly detection via autoencoder and IsolationForest.

## Stage 02: Generate Dialogs

Folder:

```bash
cd 02_dialogs_generation
```

This stage consumes synthetic financial profiles and generates advisor-client dialogs. It can also write evidence files and run a DeepSeek realism judge.

### Build Financial Profiles JSON

If `02_dialogs_generation/artifacts/financial_profiles.json` does not exist, build it from the CSV tables produced by Stage 01:

```bash
python build_financial_dataset.py \
  --tables-dir ../01_data_generation/artifacts/tables \
  --out-json artifacts/financial_profiles.json
```

### Docker

Create or update `02_dialogs_generation/.env`:

```text
OPENAI_API_KEY=...
DIALOG_N=25
DIALOG_WORKERS=5
SAVE_EVIDENCE_JSON=1
SAVE_METRICS_JSON=1
REQUIRE_VALIDATION_PASS=1
FINALIZE_TRANSCRIPT=1
DEEPSEEK_REALISM_CHECK=1
DEEPSEEK_KEY=...
DEEPSEEK_REALISM_THRESHOLD=4
```

Then run:

```bash
docker compose up --build
```

### Local

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=...
python generate_dialogs.py \
  --priors ../01_data_generation/config/priors.json \
  --financial-dataset-json artifacts/financial_profiles.json \
  --out artifacts/dialogs \
  --n 25 \
  --min-turns 1000 \
  --max-turns 1700 \
  --model gpt-4.1 \
  --max-output-tokens 8000
```

### Main Outputs

- `artifacts/dialogs/DIALOG_<household_id>.json`
- `artifacts/dialogs/DIALOG_<household_id>.txt`
- `artifacts/dialogs/DIALOG_<household_id>_evidence.json`
- `artifacts/dialogs/DIALOG_<household_id>_metrics.json`
- `artifacts/dialogs/DIALOG_<household_id>_deepseek_judge.json`
- `artifacts/dialogs/realism_passed/`
- `artifacts/dialogs/dialog_registry.csv`

Dialog quality controls include chunked generation, evidence mapping, validation metrics, regex/normalization-based grounding checks, and optional DeepSeek realism scoring.

## Stage 03: Extract Data and Evaluate

Folder:

```bash
cd 03_data_extraction
```

This stage builds dialog-grounded GT pairs, runs LLM extraction, applies the evaluated asset rescue overwrite improvement, scores extracted profiles against GT, and writes metrics, deltas, and discrepancy reports.

### Docker

Create or update `03_data_extraction/.env`:

```text
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.2
EXTRACTION_WORKERS=20
EXTRACTION_LIMIT=0
AUTO_EXPORT_GROUNDED_PROFILES=1
```

Then run:

```bash
docker compose up --build
```

### Local

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=...
python3 run_pipeline.py
```

### Run Only Ground-Truth Pairing and Dataset Plots

```bash
python3 run.py --reports-only
```

### Run Extraction Only

```bash
python3 extract_from_dialogs.py \
  --dialogs-dir ../02_dialogs_generation/artifacts/dialogs/realism_passed \
  --out-dir artifacts/extracted \
  --workers 20
```

### Recompute Evaluation from Existing Extracted JSON

```bash
python3 build_joint_dataset.py
python3 evaluate_extraction.py
python3 analyze_discrepancies.py
python3 compute_metrics.py
```

### Main Outputs

- `artifacts/ground_truth_pairs.jsonl`
- `artifacts/grounded_financial_profiles.json` when exported into this stage
- `artifacts/extracted/DIALOG_*.extracted.json`
- `artifacts/baseline/merged/merged_ground_truth_extracted.jsonl`
- `artifacts/extracted_improved/DIALOG_*.extracted.json`
- `artifacts/joint_dataset.jsonl`
- `artifacts/merged/merged_ground_truth_extracted.jsonl`
- `artifacts/merged/accuracy_report.json`
- `artifacts/improvement_delta.md`
- `artifacts/improvement_delta.json`
- `artifacts/metrics_table.txt`
- `artifacts/report/discrepancy_report.md`
- `artifacts/tables/*.csv`
- `artifacts/figures/*.png`

Extraction quality controls include schema coercion, categorical normalization, targeted rescue passes, the measured asset rescue overwrite improvement, content-based record pairing, grounded-aware scoring, and discrepancy analysis.

## Holdout Test Run

The repository currently contains a held-out evaluation under:

```text
03_data_extraction/artifacts/OOS/
```

The folder name is `OOS` for historical reasons, but the report refers to it as the holdout test.

Example Docker run for a prepared holdout input folder:

```bash
cd 03_data_extraction

OUTPUT_DIR=/repo/03_data_extraction/artifacts/OOS \
REALISM_PASSED_DIR=/repo/03_data_extraction/artifacts/OOS/dialogs_input \
EVIDENCE_DIALOGS_DIR=/repo/03_data_extraction/artifacts/OOS/dialogs_input \
GROUNDED_PROFILES_JSON=/repo/03_data_extraction/artifacts/OOS/grounded_financial_profiles.json \
FORCE_REBUILD_GROUNDED_PROFILES=1 \
AUTO_EXPORT_GROUNDED_PROFILES=1 \
EXTRACTION_LIMIT=999 \
EXTRACTION_FORCE_REEXTRACT=0 \
docker compose up --build
```

After completion, verify counts:

```bash
python3 -c 'from pathlib import Path
root = Path("artifacts/OOS")
print("input_txt", len(list((root / "dialogs_input").glob("DIALOG_HH*.txt"))))
print("pairs", sum(1 for _ in open(root / "ground_truth_pairs.jsonl", encoding="utf-8")))
print("extracted", len(list((root / "extracted").glob("DIALOG_*.extracted.json"))))
print("joint", sum(1 for _ in open(root / "joint_dataset.jsonl", encoding="utf-8")))
print("merged", sum(1 for _ in open(root / "merged/merged_ground_truth_extracted.jsonl", encoding="utf-8")))
'
```

## Current Benchmark Summary

Current local artifacts include:

- Train/development set: 316 dialogs.
- Holdout test set: 99 dialogs.
- Train mean household field accuracy after the measured improvement: 98.81%.
- Holdout test mean household field accuracy after the measured improvement: 98.81%.
- Holdout test dialogs with at least 95% correct fields: 96/99.
- Holdout test dialogs with at least 90% correct fields: 99/99.

See [`approach.html`](approach.html) for tables, plots, and links to detailed artifacts.

## Useful Documents

- [`approach.html`](approach.html) - high-level methodology and results report.
- [`01_data_generation/APPROACH.md`](01_data_generation/APPROACH.md) - detailed data generation assumptions and validation.
- [`02_dialogs_generation/README.md`](02_dialogs_generation/README.md) - dialog generation operations.
- [`03_data_extraction/approach.md`](03_data_extraction/approach.md) - extraction and scoring methodology.
- [`03_data_extraction/README.md`](03_data_extraction/README.md) - extraction pipeline operations.

## Notes

- Do not mix Train/development artifacts and holdout test artifacts. Use a separate `OUTPUT_DIR` for holdout runs.
- If running inside Docker, avoid symlinks that point to host-only paths such as `/Users/...`; copy files or use container-visible paths.
- The existing `artifacts/` directories contain generated outputs and may be large.

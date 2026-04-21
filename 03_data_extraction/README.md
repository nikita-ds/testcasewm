# 03_data_extraction

The `03` pipeline builds ground-truth pairs for realism-passed dialogs, runs LLM extraction, compares extraction output against ground truth, and writes metrics, plots, error tables, and a markdown discrepancy report.

Methodological details are documented in [`approach.md`](approach.md).

## Quick Docker Run

From `03_data_extraction`:

```bash
docker compose up --build
```

This runs `run_pipeline.py` and executes the full pipeline:

1. export grounded profiles from evidence files when `AUTO_EXPORT_GROUNDED_PROFILES` is enabled;
2. build `ground_truth_pairs.jsonl` and basic dataset plots;
3. run LLM extraction over `.txt` dialogs;
4. score the original extraction into `baseline/merged/` for before/after comparison;
5. apply the asset rescue overwrite improvement without reading ground truth or evidence;
6. build `joint_dataset.jsonl` from the improved extraction;
7. score improved extraction and write `merged/merged_ground_truth_extracted.jsonl`;
8. write `improvement_delta.json` and `improvement_delta.md`;
9. run discrepancy analysis;
10. write the final improved `metrics_table.txt`.

## Local Run

Install dependencies from `requirements.txt` and provide `OPENAI_API_KEY` through the environment or `.env`.

```bash
python3 run_pipeline.py
```

To build only pairs and plots, without extraction/evaluation:

```bash
python3 run.py --reports-only
```

To run extraction separately:

```bash
python3 extract_from_dialogs.py \
  --dialogs-dir ../02_dialogs_generation/artifacts/dialogs/realism_passed \
  --out-dir artifacts/extracted \
  --workers 20
```

To recompute evaluation from already existing extracted JSON files:

```bash
python3 build_joint_dataset.py
python3 evaluate_extraction.py
python3 analyze_discrepancies.py
python3 compute_metrics.py
```

## Main Environment Variables

`REALISM_PASSED_DIR` is the directory with `DIALOG_*.txt`. Default:

```text
../02_dialogs_generation/artifacts/dialogs/realism_passed
```

`FINANCIAL_PROFILES_JSON` is the full synthetic profiles JSON. Default:

```text
../02_dialogs_generation/artifacts/financial_profiles.json
```

`GROUNDED_PROFILES_JSON` is the sparse dialog-grounded profiles JSON. If the file exists, `run.py` uses it as GT for matching households.

`OUTPUT_DIR` is the root artifact directory. Default:

```text
./artifacts
```

`PAIRS_BASENAME` is the pairs filename inside `OUTPUT_DIR`. Default:

```text
ground_truth_pairs.jsonl
```

`AUTO_EXPORT_GROUNDED_PROFILES` controls whether grounded profiles are generated before pairing. Default: `1`.

`EVIDENCE_DIALOGS_DIR` is the directory containing `DIALOG_*_evidence.json` files for grounded profile export.

`FORCE_REBUILD_GROUNDED_PROFILES` rebuilds `GROUNDED_PROFILES_JSON` even if it already exists. Default: `0`.

`INCLUDE_APPROXIMATE_GROUNDED` includes evidence items with `status="approximate"`. Default: `0`.

`EXTRACTION_LIMIT` limits dialogs for extraction/evaluation. `0` means all.

`EXTRACTION_WORKERS` sets the number of parallel extraction workers.

`EXTRACTION_FORCE_REEXTRACT` overwrites extraction outputs when set to `1`; otherwise the pipeline can skip valid existing outputs.

`OPENAI_MODEL` sets the extractor model. The current code default is `gpt-5.2`.

`OPENAI_TIMEOUT_S` and `OPENAI_MAX_RETRIES` configure the OpenAI client.

## OOS Run

For a holdout test, write everything to a separate `OUTPUT_DIR` so OOS artifacts do not mix with tuning artifacts.

Example Docker run for an already prepared OOS dialog directory:

```bash
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

After an OOS run, verify counts:

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

Also verify that household IDs do not overlap with the tuning extracted set.

## Outputs

In the standard run, outputs are written to `artifacts/`. In OOS or any isolated run, outputs are written to `OUTPUT_DIR`.

Main files:

- `ground_truth_pairs.jsonl` - dialog + GT profile pairs;
- `summary.json` - pairing/build summary;
- `grounded_financial_profiles.json` - dialog-grounded GT when generated in this output directory;
- `extracted/DIALOG_*.extracted.json` - final extraction outputs;
- `baseline/merged/merged_ground_truth_extracted.jsonl` - baseline scoring before the improvement pass;
- `extracted_improved/DIALOG_*.extracted.json` - extraction outputs after the asset rescue overwrite improvement;
- `extracted/DIALOG_*.raw.json` - raw model outputs;
- `extracted/extracted_index.jsonl` - extraction status by dialog;
- `extracted/coerce_issues.json` - coercion issues;
- `extracted/coverage_aggregate.json` - coverage by extracted field;
- `joint_dataset.jsonl` - side-by-side GT/extracted dataset;
- `merged/merged_ground_truth_extracted.jsonl` - scored field-level merge;
- `merged/accuracy_report.json` - aggregate evaluation report;
- `improvement_delta.json` - structured before/after metrics;
- `improvement_delta.md` - markdown before/after metrics;
- `metrics_table.txt` - high-level quality metrics.

Plots:

- `figures/assets_hist.png`;
- `figures/income_hist.png`;
- `figures/scenario_distribution.png`;
- `figures/extraction_accuracy_hist.png`;
- `figures/discrepancy_worst_fields.png`;
- `figures/discrepancy_error_type_breakdown.png`;
- `figures/discrepancy_record_pairing.png`.

Discrepancy outputs:

- `discrepancy_summary.json`;
- `report/discrepancy_report.md`;
- `tables/discrepancy_field_stats.csv`;
- `tables/discrepancy_entity_record_pairing.csv`;
- `tables/discrepancy_record_pair_status.csv`;
- `tables/discrepancy_examples.csv`;
- `tables/value_mismatch_cells.csv`;
- `tables/discrepancy_missing_extracted_samples.csv`;
- `tables/discrepancy_extra_extracted_samples.csv`.

## Common Tasks

Rebuild only grounded GT:

```bash
python3 export_grounded_profiles.py \
  --dialogs-dir ../02_dialogs_generation/artifacts/dialogs \
  --out-json ../02_dialogs_generation/artifacts/grounded_financial_profiles.json
```

Run only reports/pairs into a separate directory:

```bash
OUTPUT_DIR=artifacts/debug \
REALISM_PASSED_DIR=../02_dialogs_generation/artifacts/dialogs/realism_passed \
GROUNDED_PROFILES_JSON=../02_dialogs_generation/artifacts/grounded_financial_profiles.json \
python3 run.py --reports-only
```

Run evaluation with a custom tolerance:

```bash
python3 evaluate_extraction.py \
  --pairs artifacts/ground_truth_pairs.jsonl \
  --extracted-dir artifacts/extracted \
  --out-jsonl artifacts/merged/merged_ground_truth_extracted.jsonl \
  --hist-path artifacts/figures/extraction_accuracy_hist.png \
  --numeric-rel-tol 0.01
```

Include ID fields in scoring:

```bash
python3 evaluate_extraction.py --include-ids
python3 analyze_discrepancies.py --include-ids
```

ID fields are usually excluded because extractor quality is evaluated on semantic data, not on guessing synthetic primary keys.

## Notes

For OOS/test runs, do not reuse the old `artifacts/extracted` as `--extracted-dir`. Always set a separate `OUTPUT_DIR` and a separate `REALISM_PASSED_DIR`.

If Docker sees the repository through `/repo`, do not use symlinks inside `REALISM_PASSED_DIR` that point to host paths such as `/Users/...`; those links may be unavailable inside the container. For OOS input, copy files or create symlinks using container-visible paths.

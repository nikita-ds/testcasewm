# Dialogs generation (02_dialogs_generation)

This folder contains a production-oriented pipeline that generates long, realistic advisor–client dialogue transcripts grounded in **existing generated financial profiles** and **existing scenario definitions**.

Key properties:
- Uses `generator_params.scenarios` + `generator_params.scenario_weights` from priors (with fallback to `scenario_catalog`) to sample scenarios with the same distribution as the upstream generator.
- Multi-stage generation (no single-pass full transcript):
  1) persona generation
  2) conversation outline
  3) phase-by-phase dialogue generation
  4) state update after each phase
- Optional: evidence extraction that maps each input field/value to a short advisor-question + client-answer excerpt for downstream verification.
- Prompts are stored as separate `.md` files under `prompts/` and loaded dynamically.
- Uses the OpenAI Python SDK (Responses API). Set `OPENAI_API_KEY`.

## Repository constraints
- This module does **not** modify upstream data generation.
- Grounding validation is implemented locally, and an optional DeepSeek judge can score post-finalized transcripts for realism.

## Inputs

### A) Financial dataset JSON (required by generator)
The dialogue generator consumes a JSON file containing a list of per-household financial profiles. Each item is a dict containing the same fields as the generated tables:

- `households` (single row as dict)
- `people` (list)
- `income_lines` (list)
- `assets` (list)
- `liabilities` (list)
- `protection_policies` (list)

If you only have the CSV tables (default output of `01_data_generation`), first build the JSON:

```bash
python 02_dialogs_generation/build_financial_dataset.py \
  --tables-dir 01_data_generation/artifacts/tables \
  --out-json 02_dialogs_generation/artifacts/financial_profiles.json
```

### B) Priors
Use either:
- `01_data_generation/config/priors.json`, or
- `01_data_generation/artifacts/computed_priors.json`

## Install

From repo root:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r 02_dialogs_generation/requirements.txt
export OPENAI_API_KEY=...  # required
```

## Run in Docker

This pipeline is designed to run via Docker Compose (so you don't need a local Python environment).

From the `02_dialogs_generation/` directory:

```bash
cd 02_dialogs_generation

# Put your OpenAI key into 02_dialogs_generation/.env
# OPENAI_API_KEY=...

# End-to-end run (builds financial_profiles.json from 01_data_generation tables,
# then generates dialogs). Defaults to 1 dialog.
docker compose up --build

# To generate more dialogs, set DIALOG_N in 02_dialogs_generation/.env, e.g.
# DIALOG_N=25

# By default, the pipeline skips households that already have a dialog JSON in OUTPUT_DIR
# (e.g. artifacts/dialogs/DIALOG_HH000123.json). You can control this with:
# DIALOG_SKIP_EXISTING=1   # default
# DIALOG_SKIP_EXISTING=0   # regenerate even if a dialog file already exists
#
# There is also an optional dialog registry (CSV) that can be used for skipping by status:
# DIALOG_REGISTRY_PATH=... (default: <OUTPUT_DIR>/dialog_registry.csv)
# DIALOG_REGISTRY_SKIP_STATUSES=success,validation_failed  # default
# (Set to "success" if you want to re-try previously validation-failed households.)

# If phases get truncated (invalid JSON), increase output budget, e.g.
# MAX_OUTPUT_TOKENS=8000

# Evidence / verification artifacts (recommended while debugging grounding)
# SAVE_EVIDENCE_JSON=1
# EVIDENCE_BATCH_SIZE=25
# EVIDENCE_MAX_OUTPUT_TOKENS=1800
# SAVE_METRICS_JSON=1
# REQUIRE_VALIDATION_PASS=1
# VALIDATION_STRICT=0

# Alternative mode to avoid a second LLM pass for evidence:
# - field_chunks generates the transcript in batches of input fields and returns inline evidence for each batch.
# DIALOG_MODE=field_chunks
# EVIDENCE_POSTHOC=0
# FIELD_CHUNK_GROUP_BY_RECORD_TYPE=1
# FIELD_CHUNK_SHUFFLE_WITHIN_GROUP=1

# Optional but now recommended: after validation passes, finalize the transcript into a more realistic conversation.
# FINALIZE_TRANSCRIPT=1
# FINALIZE_STRATEGY=realism_merge
# FINALIZE_MAX_OUTPUT_TOKENS=3200
#
# Optional DeepSeek realism gate after finalization.
# DEEPSEEK_KEY=...
# DEEPSEEK_REALISM_CHECK=1
# DEEPSEEK_MODEL=deepseek-chat
# DeepSeek returns a single realism score 1..5.
# The transcript is copied into artifacts/dialogs/realism_passed/ when realism_score >= threshold.
# DEEPSEEK_REALISM_THRESHOLD=4
# DEEPSEEK_PASS_SUBDIR=realism_passed
```

### Example transcript guidance in prompts

The phase-generation prompt injects two style exemplars from `00_initial_task/`:
- `synthetic_transcript1.txt`
- `synthetic_transcript2.txt`

Because those files are very large, the default mode injects **excerpts** only.
You can control this via `EXAMPLE_TRANSCRIPTS_MODE` in `.env`:
- `excerpt` (default, recommended)
- `full` (very large; may exceed context limits)
- `none`

## Generate dialogues

```bash
python 02_dialogs_generation/generate_dialogs.py \
  --priors 01_data_generation/config/priors.json \
  --financial-dataset-json 02_dialogs_generation/artifacts/financial_profiles.json \
  --out 02_dialogs_generation/artifacts/dialogs \
  --n 25 \
  --min-turns 1000 \
  --max-turns 1700 \
  --model gpt-4.1 \
  --max-output-tokens 8000
```

Outputs:
- One JSON per transcript: `DIALOG_<household_id>.json`
- Optional plain-text transcript alongside: `DIALOG_<household_id>.txt`
- Optional evidence JSON alongside: `DIALOG_<household_id>_evidence.json`
- Optional metrics JSON alongside: `DIALOG_<household_id>_metrics.json`
- Optional DeepSeek judge JSON alongside: `DIALOG_<household_id>_deepseek_judge.json`
- If the DeepSeek realism score passes threshold (default: 4), the transcript is also copied into `artifacts/dialogs/realism_passed/`

Validation failure report:
- `validation_failures.csv` is intentionally minimal: it contains only `household_id` and `failed_field_paths`.
  (If an older, wider-schema file exists, the pipeline rotates it to `validation_failures_full.csv` on the next write.)

## Aggregate validation across dialogs

If you generated evidence artifacts (`*_evidence.json`), you can aggregate them into a sparse error matrix
and summaries:

```bash
python 02_dialogs_generation/aggregate_validation.py \
  --dialogs-dir 02_dialogs_generation/artifacts/dialogs \
  --out-dir 02_dialogs_generation/artifacts/validation

# Strict mode: mark a field as error if its source_value (or simple variants) is not found in evidence_text
python 02_dialogs_generation/aggregate_validation.py \
  --dialogs-dir 02_dialogs_generation/artifacts/dialogs \
  --out-dir 02_dialogs_generation/artifacts/validation_strict \
  --strict
```

Outputs:
- `errors_sparse.parquet`: (household_id, scenario_name, field_path) → error flag (sparse matrix)
- `summary_by_field.csv`: error rates by field_path
- `summary_by_scenario.csv`: error rates by scenario_name

## Output format
Each transcript JSON:

```json
{
  "id": "...",
  "scenario": "...",
  "financial_profile": { ... },
  "personas": [ {"id": "client_1", "profile": {...}}, ... ],
  "transcript": "Advisor: ...\nClient: ...\n...",
  "phases": [ ... ],
  "evidence": {
    "meta": {"num_targets": 123, "batch_size": 25, "mode": "phases_posthoc"},
    "targets": [ ... ],
    "items": [ ... ]
  },
  "metadata": {
    "num_turns": 123,
    "household_type": "single",
    "scenario_name": "family_with_mortgage_and_children"
  }
}
```

## Architecture
- `generate_dialogs.py`: CLI entrypoint
- `pipeline.py`: orchestration (persona → outline → phases → state updates)
- `openai_client.py`: OpenAI Responses API wrapper + JSON extraction
- `scenario.py`: scenario sampling logic (matches upstream)
- `financial_dataset.py`: build profile JSON from CSV tables
- `schemas.py`: pydantic models for LLM outputs
- `state.py`: structured state object
- `prompt_loader.py`: loads `.md` prompts and performs placeholder substitution
- `prompts/`: prompt templates (no inline prompts in Python)

## Design decisions
- Keep prompts external and versionable (`prompts/*.md`).
- Use JSON-only LLM outputs for robust parsing.
- Keep deterministic components deterministic (scenario sampling uses `--seed`).

## Limitations
- Determinism of the language model output depends on the underlying model; `--openai-seed` is passed when supported.
- The generator assumes the financial dataset JSON is a list of household profiles.

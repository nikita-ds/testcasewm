# Dialogs generation (02_dialogs_generation)

This folder contains a production-oriented pipeline that generates long, realistic advisor–client dialogue transcripts grounded in **existing generated financial profiles** and **existing scenario definitions**.

Key properties:
- Uses `generator_params.scenarios` + `generator_params.scenario_weights` from priors (with fallback to `scenario_catalog`) to sample scenarios with the same distribution as the upstream generator.
- Current benchmark configuration uses `field_chunks` mode: the generator groups profile fields into batches, writes transcript segments around those batches, and returns inline evidence for the generated facts.
- The older `phases` mode is still supported by the codebase, but it is not the mode used for the reported Train/OOS benchmark.
- Optional: evidence artifacts map each input field/value to a short advisor-question + client-answer excerpt for downstream verification. In `field_chunks` mode this evidence is produced inline with generation rather than through a separate post-hoc LLM pass.
- Prompts are stored as separate `.md` files under `prompts/` and loaded dynamically.
- Uses the OpenAI Python SDK (Responses API). Set `OPENAI_API_KEY`.
- The current project configuration uses OpenAI `gpt-5.2` for dialog generation (`MODEL` in `.env`).

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
# MODEL=gpt-5.2
# DIALOG_MODE=field_chunks
# EVIDENCE_POSTHOC=0

# End-to-end run (builds financial_profiles.json from 01_data_generation tables,
# then generates dialogs). Without .env overrides, the code default is 1 dialog;
# the repository .env used for the benchmark sets DIALOG_N explicitly.
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

# If a generation response gets truncated (invalid JSON), increase output budget, e.g.
# MAX_OUTPUT_TOKENS=8000

# Evidence / verification artifacts (recommended while debugging grounding)
# SAVE_EVIDENCE_JSON=1
# EVIDENCE_BATCH_SIZE=25
# EVIDENCE_MAX_OUTPUT_TOKENS=1800
# SAVE_METRICS_JSON=1
# REQUIRE_VALIDATION_PASS=1
# VALIDATION_STRICT=0

# Current benchmark mode:
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
# In the DeepSeek API, deepseek-chat currently maps to DeepSeek-V3.2 non-thinking mode.
# DeepSeek returns a single realism score 1..5.
# The transcript is copied into artifacts/dialogs/realism_passed/ when realism_score >= threshold.
# DEEPSEEK_REALISM_THRESHOLD=4
# DEEPSEEK_PASS_SUBDIR=realism_passed
```

### Example transcript style guidance

The two source transcripts in `00_initial_task/` were used to distill style guidance for realistic advisor-client calls:
- `synthetic_transcript1.txt`
- `synthetic_transcript2.txt`

For the reported Train/OOS dialogs, the source transcripts themselves were not copied into generation prompts. The intent was to capture conversational style without leaking or reproducing example transcript content.

## Generate dialogues

```bash
python 02_dialogs_generation/generate_dialogs.py \
  --priors 01_data_generation/config/priors.json \
  --financial-dataset-json 02_dialogs_generation/artifacts/financial_profiles.json \
  --out 02_dialogs_generation/artifacts/dialogs \
  --n 25 \
  --min-turns 1000 \
  --max-turns 1700 \
  --model gpt-5.2 \
  --mode field_chunks \
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
python 02_dialogs_generation/src/aggregate_validation.py \
  --dialogs-dir 02_dialogs_generation/artifacts/dialogs \
  --out-dir 02_dialogs_generation/artifacts/validation

# Strict mode: mark a field as error if its source_value (or simple variants) is not found in evidence_text
python 02_dialogs_generation/src/aggregate_validation.py \
  --dialogs-dir 02_dialogs_generation/artifacts/dialogs \
  --out-dir 02_dialogs_generation/artifacts/validation_strict \
  --strict
```

Outputs:
- `errors_sparse.parquet`: (household_id, scenario_name, field_path) → error flag (sparse matrix)
- `summary_by_field.csv`: error rates by field_path
- `summary_by_scenario.csv`: error rates by scenario_name

## Export dialog-grounded ground truth (for 03_data_extraction)

If you have `*_evidence.json` artifacts, you can export a **sparse** (dialog-grounded) version of the financial profiles that keeps only fields with evidence (by default `status="present"`). This is useful as a “fair” ground-truth for extraction evaluation.

```bash
python 03_data_extraction/src/export_grounded_profiles.py \
  --dialogs-dir 02_dialogs_generation/artifacts/dialogs \
  --out-json 02_dialogs_generation/artifacts/grounded_financial_profiles.json

# Optional: also include fields with status="approximate"
python 03_data_extraction/src/export_grounded_profiles.py --include-approximate
```

## Output format
Each transcript JSON:

```json
{
  "id": "...",
  "scenario": "...",
  "financial_profile": { ... },
  "personas": [ {"id": "client_1", "profile": {...}}, ... ],
  "transcript": "Advisor: ...\nClient: ...\n...",
  "phases": [],
  "evidence": {
    "meta": {"num_targets": 123, "batch_size": 25, "mode": "field_chunks"},
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
- `src/pipeline.py`: orchestration (persona → field chunks with inline evidence → validation → optional finalization and realism judging)
- `src/openai_client.py`: OpenAI Responses API wrapper + JSON extraction
- `src/scenario.py`: scenario sampling logic (matches upstream)
- `src/financial_dataset.py`: build profile JSON from CSV tables
- `src/schemas.py`: pydantic models for LLM outputs
- `src/state.py`: structured state object
- `src/prompt_loader.py`: loads `.md` prompts and performs placeholder substitution
- `prompts/`: prompt templates (no inline prompts in Python)

## Design decisions
- Keep prompts external and versionable (`prompts/*.md`).
- Use JSON-only LLM outputs for robust parsing.
- Keep deterministic components deterministic (scenario sampling uses `--seed`).

## Limitations
- Determinism of the language model output depends on the underlying model; `--openai-seed` is passed when supported.
- The generator assumes the financial dataset JSON is a list of household profiles.

from __future__ import annotations

import os
import sys
from pathlib import Path


# Allow running from repo root or any working directory.
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))


from config import GenerationConfig, ModelConfig
from env_utils import load_dotenv_if_present
from financial_dataset import build_financial_profiles_from_tables, save_financial_profiles_json
from pipeline import DialogGenerationPipeline


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    return default if v is None or str(v).strip() == "" else int(v)


def _env_str(name: str, default: str) -> str:
    v = os.getenv(name)
    return default if v is None or str(v).strip() == "" else str(v)


def main() -> None:
    load_dotenv_if_present(Path(__file__).resolve().parent)

    # Paths inside container (repo is mounted to /app by docker-compose.yml)
    tables_dir = Path(_env_str("TABLES_DIR", "/app/01_data_generation/artifacts/tables"))
    priors_path = Path(_env_str("PRIORS_PATH", "/app/01_data_generation/config/priors.json"))

    dataset_out = Path(_env_str("DATASET_JSON", "/app/02_dialogs_generation/artifacts/financial_profiles.json"))
    out_dir = Path(_env_str("OUTPUT_DIR", "/app/02_dialogs_generation/artifacts/dialogs"))

    rebuild_dataset = bool(int(os.getenv("REBUILD_DATASET", "0")))

    n = _env_int("DIALOG_N", 1)
    workers = _env_int("DIALOG_WORKERS", 10)
    seed = _env_int("SEED", 42)
    min_turns = _env_int("MIN_TURNS", 200)
    max_turns = _env_int("MAX_TURNS", 350)
    max_output_tokens = _env_int("MAX_OUTPUT_TOKENS", 2000)

    personas_max_output_tokens = _env_int("PERSONAS_MAX_OUTPUT_TOKENS", 900)
    outline_max_output_tokens = _env_int("OUTLINE_MAX_OUTPUT_TOKENS", 1100)
    phase_max_output_tokens = _env_int("PHASE_MAX_OUTPUT_TOKENS", 1400)
    state_max_output_tokens = _env_int("STATE_MAX_OUTPUT_TOKENS", 800)

    save_evidence_json = bool(int(os.getenv("SAVE_EVIDENCE_JSON", "1")))
    evidence_batch_size = _env_int("EVIDENCE_BATCH_SIZE", 25)
    evidence_max_output_tokens = _env_int("EVIDENCE_MAX_OUTPUT_TOKENS", 1800)

    save_metrics_json = bool(int(os.getenv("SAVE_METRICS_JSON", "1")))
    require_validation_pass = bool(int(os.getenv("REQUIRE_VALIDATION_PASS", "1")))
    validation_strict = bool(int(os.getenv("VALIDATION_STRICT", "0")))

    finalize_transcript = bool(int(os.getenv("FINALIZE_TRANSCRIPT", "1")))
    finalize_max_output_tokens = _env_int("FINALIZE_MAX_OUTPUT_TOKENS", 2200)
    finalize_strategy = _env_str("FINALIZE_STRATEGY", "realism_merge")
    finalize_bridge_max_output_tokens = _env_int("FINALIZE_BRIDGE_MAX_OUTPUT_TOKENS", 500)
    deepseek_realism_check = bool(int(os.getenv("DEEPSEEK_REALISM_CHECK", "1")))
    deepseek_model = _env_str("DEEPSEEK_MODEL", "deepseek-chat")
    deepseek_max_output_tokens = _env_int("DEEPSEEK_MAX_OUTPUT_TOKENS", 900)
    deepseek_realism_threshold = float(os.getenv("DEEPSEEK_REALISM_THRESHOLD", "4"))
    deepseek_pass_subdir = _env_str("DEEPSEEK_PASS_SUBDIR", "realism_passed")

    field_chunk_group_by_record_type = bool(int(os.getenv("FIELD_CHUNK_GROUP_BY_RECORD_TYPE", "1")))
    field_chunk_shuffle_within_group = bool(int(os.getenv("FIELD_CHUNK_SHUFFLE_WITHIN_GROUP", "1")))

    recap_window_utterances = _env_int("RECAP_WINDOW_UTTERANCES", 10)
    recap_max_per_window = _env_int("RECAP_MAX_PER_WINDOW", 1)
    misunderstanding_window_utterances = _env_int("MISUNDERSTANDING_WINDOW_UTTERANCES", 10)
    misunderstanding_max_per_window = _env_int("MISUNDERSTANDING_MAX_PER_WINDOW", 1)

    context_last_utterances = _env_int("CONTEXT_LAST_UTTERANCES", 30)
    context_summary_last_phases = _env_int("CONTEXT_SUMMARY_LAST_PHASES", 4)
    context_summary_max_chars = _env_int("CONTEXT_SUMMARY_MAX_CHARS", 1200)

    model = _env_str("MODEL", "gpt-4.1")
    mode = _env_str("DIALOG_MODE", "phases")
    evidence_posthoc = bool(int(os.getenv("EVIDENCE_POSTHOC", "1")))

    sample_mode = _env_str("DIALOG_SAMPLE_MODE", "stratified")
    income_bins = _env_int("DIALOG_INCOME_BINS", 3)
    assets_bins = _env_int("DIALOG_ASSETS_BINS", 3)
    skip_existing = bool(int(os.getenv("DIALOG_SKIP_EXISTING", "1")))
    registry_path = Path(_env_str("DIALOG_REGISTRY_PATH", str(out_dir / "dialog_registry.csv")))
    registry_skip_statuses = _env_str("DIALOG_REGISTRY_SKIP_STATUSES", "success,validation_failed")
    continue_on_error = bool(int(os.getenv("DIALOG_CONTINUE_ON_ERROR", "1")))

    # Step 1: Build the big JSON dataset from the generated tables.
    # If it already exists, do not rebuild (saves time during iterative runs).
    if (not rebuild_dataset) and dataset_out.exists() and dataset_out.stat().st_size > 0:
        print(f"Using existing financial dataset: {dataset_out}")
    else:
        profiles = build_financial_profiles_from_tables(tables_dir)
        save_financial_profiles_json(profiles, dataset_out)
        print(f"Built financial dataset: {dataset_out} (profiles={len(profiles)})")

    # Step 2: Generate dialogs in order from that JSON.
    cfg = GenerationConfig(
        mode=mode,
        priors_path=priors_path,
        financial_dataset_json_path=dataset_out,
        output_dir=out_dir,
        n=n,
        workers=max(1, int(workers)),
        min_turns=min_turns,
        max_turns=max_turns,
        context_last_utterances=context_last_utterances,
        context_summary_last_phases=context_summary_last_phases,
        context_summary_max_chars=context_summary_max_chars,
        personas_max_output_tokens=personas_max_output_tokens,
        outline_max_output_tokens=outline_max_output_tokens,
        phase_max_output_tokens=phase_max_output_tokens,
        state_max_output_tokens=state_max_output_tokens,
        save_evidence_json=save_evidence_json,
        evidence_batch_size=evidence_batch_size,
        evidence_max_output_tokens=evidence_max_output_tokens,
        evidence_posthoc=evidence_posthoc,
        save_metrics_json=save_metrics_json,
        require_validation_pass=require_validation_pass,
        validation_strict=validation_strict,
        finalize_transcript=finalize_transcript,
        finalize_strategy=finalize_strategy,
        finalize_max_output_tokens=finalize_max_output_tokens,
        finalize_bridge_max_output_tokens=finalize_bridge_max_output_tokens,
        deepseek_realism_check=deepseek_realism_check,
        deepseek_model=deepseek_model,
        deepseek_max_output_tokens=deepseek_max_output_tokens,
        deepseek_realism_threshold=deepseek_realism_threshold,
        deepseek_pass_subdir=deepseek_pass_subdir,
        field_chunk_group_by_record_type=field_chunk_group_by_record_type,
        field_chunk_shuffle_within_group=field_chunk_shuffle_within_group,
        recap_window_utterances=recap_window_utterances,
        recap_max_per_window=recap_max_per_window,
        misunderstanding_window_utterances=misunderstanding_window_utterances,
        misunderstanding_max_per_window=misunderstanding_max_per_window,
        sample_mode=sample_mode,
        income_bins=income_bins,
        assets_bins=assets_bins,
        skip_existing=skip_existing,
        registry_path=registry_path,
        registry_skip_statuses=registry_skip_statuses,
        continue_on_error=continue_on_error,
        seed=seed,
        model=ModelConfig(
            model=model,
            temperature=0.0,
            max_output_tokens=max_output_tokens,
            seed=seed,
        ),
        save_txt=True,
    )

    DialogGenerationPipeline().run(cfg)


if __name__ == "__main__":
    main()

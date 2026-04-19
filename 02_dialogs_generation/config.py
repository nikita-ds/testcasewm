from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class ModelConfig:
    model: str = "gpt-4.1"
    temperature: float = 0.0
    max_output_tokens: int = 1200
    seed: Optional[int] = 42


@dataclass(frozen=True)
class Paths:
    repo_root: Path

    @property
    def prompt_dir(self) -> Path:
        return self.repo_root / "02_dialogs_generation" / "prompts"


@dataclass(frozen=True)
class GenerationConfig:
    priors_path: Path
    financial_dataset_json_path: Path
    output_dir: Path

    n: int = 1
    workers: int = 1

    # Generation strategy:
    # - "phases": personas + outline + multi-phase generation + state updates (existing)
    # - "field_chunks": walk financial profile fields in batches and generate transcript chunks
    mode: str = "phases"
    # Fast-by-default: keep dialogs short for iteration/testing.
    min_turns: int = 200
    max_turns: int = 350
    save_txt: bool = True

    # Prompt context trimming: keep the full transcript for output, but only feed a bounded
    # window of recent utterances + a rolling summary back into the model.
    context_last_utterances: int = 30
    context_summary_last_phases: int = 4
    context_summary_max_chars: int = 1200

    # Per-step output limits (lets us keep phase/state updates cheap even if one step would otherwise bloat).
    personas_max_output_tokens: int = 700
    outline_max_output_tokens: int = 800
    phase_max_output_tokens: int = 900
    state_max_output_tokens: int = 500

    # Evidence extraction: post-process transcript into field-level QA excerpts.
    save_evidence_json: bool = True
    evidence_batch_size: int = 25
    evidence_max_output_tokens: int = 1800

    # If True and mode=="phases", evidence is extracted in a second pass (current behavior).
    # If mode=="field_chunks", evidence is produced inline during generation.
    evidence_posthoc: bool = True

    # Field-chunks ergonomics: keep chunks topically coherent.
    field_chunk_group_by_record_type: bool = True
    field_chunk_shuffle_within_group: bool = True

    # Validation + metrics (primarily for mode=="field_chunks")
    save_metrics_json: bool = True
    require_validation_pass: bool = True
    # strict=True requires exact string match of source_value in evidence/transcript.
    # strict=False allows "approximate" evidence statuses to count as covered.
    validation_strict: bool = False

    # Optional final step: rewrite/expand a skeleton transcript with extra "banter",
    # without changing facts. Runs only after validation passes.
    finalize_transcript: bool = False
    # - "bridges": insert bridging utterances between chunks (keeps chunk lines verbatim; best for validation)
    # - "polish": rewrite/expand entire skeleton transcript (may rephrase)
    # - "realism_merge": rewrite/expand with stronger emphasis on natural recall, uncertainty, and granular expenses
    finalize_strategy: str = "realism_merge"
    finalize_max_output_tokens: int = 2200
    finalize_bridge_max_output_tokens: int = 500

    # Optional DeepSeek realism judging after the final transcript is produced.
    deepseek_realism_check: bool = True
    deepseek_model: str = "deepseek-chat"
    deepseek_max_output_tokens: int = 900
    # Threshold for passing/copying to deepseek_pass_subdir.
    # Units: 1..5 (a single realism score). Default pass threshold is 4.
    # Backward-compatible: values in 0..1 are treated as probability and scaled to 1..5; values in 0..100 are scaled down.
    deepseek_realism_threshold: float = 4.0
    deepseek_pass_subdir: str = "realism_passed"

    model: ModelConfig = ModelConfig()
    seed: int = 42

    # Profile selection + bookkeeping
    # - "sequential": first N profiles (existing behavior)
    # - "stratified": stratify by scenario + income/assets buckets
    sample_mode: str = "sequential"
    income_bins: int = 3
    assets_bins: int = 3

    # Registry of already-generated dialogs (to avoid re-generating the same household).
    skip_existing: bool = True
    registry_path: Optional[Path] = None
    # Comma-separated statuses to skip when selecting profiles (e.g. "success" or "success,validation_failed").
    registry_skip_statuses: str = "success,validation_failed"

    # When generating in parallel, keep going if some dialogs fail, then raise at the end if required.
    continue_on_error: bool = True

    # Realism beat throttles (to avoid repetitive misunderstanding/recap loops).
    # Interpreted as: within the last `*_window_utterances` turns, allow at most
    # `*_max_per_window` recap/misunderstanding beats.
    # Defaults target roughly "1 per 10 utterances".
    recap_window_utterances: int = 10
    recap_max_per_window: int = 1
    misunderstanding_window_utterances: int = 10
    misunderstanding_max_per_window: int = 1


def default_repo_root() -> Path:
    # Assumes scripts are run from within the repo.
    return Path(__file__).resolve().parents[1]

from __future__ import annotations

import argparse
import sys
from pathlib import Path


# Allow running from repo root or any working directory.
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))


from config import GenerationConfig, ModelConfig
from pipeline import DialogGenerationPipeline


def main() -> None:
    p = argparse.ArgumentParser(description="Generate synthetic advisor-client dialogue transcripts grounded in financial profiles.")
    p.add_argument("--priors", type=Path, required=True, help="Path to priors.json (or computed_priors.json)")
    p.add_argument("--financial-dataset-json", type=Path, required=True, help="Path to household-level financial profiles JSON")
    p.add_argument("--out", type=Path, required=True, help="Output directory")

    p.add_argument("--n", type=int, default=10, help="Number of transcripts to generate")
    p.add_argument("--workers", type=int, default=10, help="Parallel workers (1 = sequential)")
    p.add_argument(
        "--sample-mode",
        type=str,
        default="stratified",
        choices=["sequential", "stratified"],
        help="How to select profiles when n < dataset size",
    )
    p.add_argument("--income-bins", type=int, default=3, help="(stratified) number of income buckets")
    p.add_argument("--assets-bins", type=int, default=3, help="(stratified) number of assets buckets")
    p.add_argument("--registry", type=Path, default=None, help="Path to dialog registry CSV (default: <out>/dialog_registry.csv)")
    p.add_argument(
        "--registry-skip-statuses",
        type=str,
        default="success",
        help="Comma-separated statuses to skip when selecting profiles (default: success)",
    )
    p.add_argument("--no-skip-existing", action="store_true", help="Do not skip already-generated households")
    p.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Keep generating other dialogs even if some fail, then raise at end if required",
    )
    p.add_argument("--min-turns", type=int, default=200)
    p.add_argument("--max-turns", type=int, default=350)
    p.add_argument("--context-last-utterances", type=int, default=60, help="How many most-recent utterances to include in the prompt")
    p.add_argument(
        "--context-summary-last-phases",
        type=int,
        default=8,
        help="How many recent phase summaries to include as rolling context",
    )
    p.add_argument(
        "--context-summary-max-chars",
        type=int,
        default=3500,
        help="Max characters for the rolling summary included in the prompt",
    )
    p.add_argument("--no-txt", action="store_true", help="Do not save .txt transcript alongside JSON")

    p.add_argument("--no-evidence", action="store_true", help="Do not save evidence JSON alongside outputs")
    p.add_argument("--evidence-batch-size", type=int, default=25, help="How many field targets to extract per LLM call")
    p.add_argument("--evidence-max-output-tokens", type=int, default=1800)
    p.add_argument(
        "--mode",
        type=str,
        default="phases",
        choices=["phases", "field_chunks"],
        help="Generation strategy (phases = existing multi-step; field_chunks = generate transcript by field batches with inline evidence)",
    )
    p.add_argument(
        "--evidence-posthoc",
        action="store_true",
        help="If set (phases mode), run a post-hoc evidence extraction pass (default True in docker/env).",
    )

    p.add_argument("--no-metrics", action="store_true", help="Do not save metrics JSON alongside outputs")
    p.add_argument(
        "--no-require-validation-pass",
        action="store_true",
        help="Do not fail the run when validation fails (still saves artifacts)",
    )
    p.add_argument("--validation-strict", action="store_true", help="Require exact matches for values in evidence/transcript")

    p.add_argument("--finalize-transcript", action="store_true", help="After validation passes, polish/expand transcript with banter")
    p.add_argument("--finalize-max-output-tokens", type=int, default=2200)
    p.add_argument(
        "--finalize-strategy",
        type=str,
        default="bridges",
        choices=["bridges", "polish"],
        help="Finalization strategy: insert bridges between chunks (recommended) or rewrite full skeleton",
    )
    p.add_argument("--finalize-bridge-max-output-tokens", type=int, default=500)

    p.add_argument(
        "--field-chunk-group-by-record-type",
        action="store_true",
        help="(field_chunks mode) Build chunks as coherent blocks by record_type",
    )
    p.add_argument(
        "--no-field-chunk-shuffle-within-group",
        action="store_true",
        help="(field_chunks mode) Disable shuffling within each record_type group",
    )

    p.add_argument("--model", type=str, default="gpt-4.1")
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--max-output-tokens", type=int, default=2000)
    p.add_argument("--seed", type=int, default=42, help="Deterministic seed for scenario sampling and ordering")
    p.add_argument("--openai-seed", type=int, default=None, help="Optional seed passed to OpenAI Responses API")

    args = p.parse_args()

    cfg = GenerationConfig(
        mode=str(args.mode),
        priors_path=args.priors,
        financial_dataset_json_path=args.financial_dataset_json,
        output_dir=args.out,
        n=args.n,
        workers=max(1, int(args.workers)),
        sample_mode=str(args.sample_mode),
        income_bins=int(args.income_bins),
        assets_bins=int(args.assets_bins),
        skip_existing=not bool(args.no_skip_existing),
        registry_path=(args.registry or (args.out / "dialog_registry.csv")),
        registry_skip_statuses=str(args.registry_skip_statuses),
        continue_on_error=bool(args.continue_on_error),
        min_turns=args.min_turns,
        max_turns=args.max_turns,
        context_last_utterances=args.context_last_utterances,
        context_summary_last_phases=args.context_summary_last_phases,
        context_summary_max_chars=args.context_summary_max_chars,
        save_txt=not args.no_txt,
        save_evidence_json=not args.no_evidence,
        evidence_batch_size=int(args.evidence_batch_size),
        evidence_max_output_tokens=int(args.evidence_max_output_tokens),
        evidence_posthoc=bool(args.evidence_posthoc),
        save_metrics_json=not args.no_metrics,
        require_validation_pass=not args.no_require_validation_pass,
        validation_strict=bool(args.validation_strict),
        finalize_transcript=bool(args.finalize_transcript),
        finalize_strategy=str(args.finalize_strategy),
        finalize_max_output_tokens=int(args.finalize_max_output_tokens),
        finalize_bridge_max_output_tokens=int(args.finalize_bridge_max_output_tokens),
        field_chunk_group_by_record_type=bool(args.field_chunk_group_by_record_type),
        field_chunk_shuffle_within_group=not bool(args.no_field_chunk_shuffle_within_group),
        seed=args.seed,
        model=ModelConfig(
            model=args.model,
            temperature=float(args.temperature),
            max_output_tokens=int(args.max_output_tokens),
            seed=args.openai_seed,
        ),
    )

    DialogGenerationPipeline().run(cfg)


if __name__ == "__main__":
    main()

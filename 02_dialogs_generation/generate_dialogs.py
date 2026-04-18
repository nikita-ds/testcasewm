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

    p.add_argument("--n", type=int, default=1, help="Number of transcripts to generate")
    p.add_argument("--workers", type=int, default=1, help="Parallel workers (1 = sequential)")
    p.add_argument("--min-turns", type=int, default=1000)
    p.add_argument("--max-turns", type=int, default=1700)
    p.add_argument("--no-txt", action="store_true", help="Do not save .txt transcript alongside JSON")

    p.add_argument("--model", type=str, default="gpt-4.1")
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--max-output-tokens", type=int, default=6000)
    p.add_argument("--seed", type=int, default=42, help="Deterministic seed for scenario sampling and ordering")
    p.add_argument("--openai-seed", type=int, default=None, help="Optional seed passed to OpenAI Responses API")

    args = p.parse_args()

    cfg = GenerationConfig(
        priors_path=args.priors,
        financial_dataset_json_path=args.financial_dataset_json,
        output_dir=args.out,
        n=args.n,
        workers=max(1, int(args.workers)),
        min_turns=args.min_turns,
        max_turns=args.max_turns,
        save_txt=not args.no_txt,
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

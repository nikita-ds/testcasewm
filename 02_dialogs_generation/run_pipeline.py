from __future__ import annotations

import os
import sys
from pathlib import Path


# Allow running from repo root or any working directory.
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))


from config import GenerationConfig, ModelConfig
from financial_dataset import build_financial_profiles_from_tables, save_financial_profiles_json
from pipeline import DialogGenerationPipeline


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    return default if v is None or str(v).strip() == "" else int(v)


def _env_str(name: str, default: str) -> str:
    v = os.getenv(name)
    return default if v is None or str(v).strip() == "" else str(v)


def main() -> None:
    # Paths inside container (repo is mounted to /app by docker-compose.yml)
    tables_dir = Path(_env_str("TABLES_DIR", "/app/01_data_generation/artifacts/tables"))
    priors_path = Path(_env_str("PRIORS_PATH", "/app/01_data_generation/config/priors.json"))

    dataset_out = Path(_env_str("DATASET_JSON", "/app/02_dialogs_generation/artifacts/financial_profiles.json"))
    out_dir = Path(_env_str("OUTPUT_DIR", "/app/02_dialogs_generation/artifacts/dialogs"))

    n = _env_int("DIALOG_N", 1)
    seed = _env_int("SEED", 42)
    min_turns = _env_int("MIN_TURNS", 1000)
    max_turns = _env_int("MAX_TURNS", 1700)
    max_output_tokens = _env_int("MAX_OUTPUT_TOKENS", 8000)

    model = _env_str("MODEL", "gpt-4.1")

    # Step 1: Build the big JSON dataset from the generated tables.
    profiles = build_financial_profiles_from_tables(tables_dir)
    save_financial_profiles_json(profiles, dataset_out)
    print(f"Built financial dataset: {dataset_out} (profiles={len(profiles)})")

    # Step 2: Generate dialogs in order from that JSON.
    cfg = GenerationConfig(
        priors_path=priors_path,
        financial_dataset_json_path=dataset_out,
        output_dir=out_dir,
        n=n,
        min_turns=min_turns,
        max_turns=max_turns,
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

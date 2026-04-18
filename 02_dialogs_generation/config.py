from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class ModelConfig:
    model: str = "gpt-4.1"
    temperature: float = 0.0
    max_output_tokens: int = 6000
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
    min_turns: int = 1000
    max_turns: int = 1700
    save_txt: bool = True

    model: ModelConfig = ModelConfig()
    seed: int = 42


def default_repo_root() -> Path:
    # Assumes scripts are run from within the repo.
    return Path(__file__).resolve().parents[1]

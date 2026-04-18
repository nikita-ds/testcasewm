from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict


class PromptNotFoundError(FileNotFoundError):
    pass


@dataclass(frozen=True)
class PromptBundle:
    system: str
    persona_generation: str
    outline: str
    phase_generation: str
    state_update: str
    evidence_extraction: str
    field_chunk_generation: str
    transcript_polish: str
    chunk_bridge: str
    deepseek_realism_judge: str


def _read_text(path: Path) -> str:
    if not path.exists():
        raise PromptNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


def load_prompts(prompt_dir: Path) -> PromptBundle:
    return PromptBundle(
        system=_read_text(prompt_dir / "system_prompt.md"),
        persona_generation=_read_text(prompt_dir / "persona_generation_prompt.md"),
        outline=_read_text(prompt_dir / "outline_prompt.md"),
        phase_generation=_read_text(prompt_dir / "phase_generation_prompt.md"),
        state_update=_read_text(prompt_dir / "state_update_prompt.md"),
        evidence_extraction=_read_text(prompt_dir / "evidence_extraction_prompt.md"),
        field_chunk_generation=_read_text(prompt_dir / "field_chunk_generation_prompt.md"),
        transcript_polish=_read_text(prompt_dir / "transcript_polish_prompt.md"),
        chunk_bridge=_read_text(prompt_dir / "chunk_bridge_prompt.md"),
        deepseek_realism_judge=_read_text(prompt_dir / "deepseek_realism_judge_prompt.md"),
    )


def render_prompt(template: str, variables: Dict[str, str]) -> str:
    rendered = template
    for k, v in variables.items():
        rendered = rendered.replace("{{" + k + "}}", v)
    return rendered

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
    )


def render_prompt(template: str, variables: Dict[str, str]) -> str:
    rendered = template
    for k, v in variables.items():
        rendered = rendered.replace("{{" + k + "}}", v)
    return rendered

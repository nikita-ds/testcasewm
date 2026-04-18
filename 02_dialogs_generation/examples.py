from __future__ import annotations

from pathlib import Path
from typing import Literal


ExamplesMode = Literal["excerpt", "full", "none"]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _excerpt(text: str, max_lines: int) -> str:
    lines = text.splitlines()
    return "\n".join(lines[:max_lines]).strip() + "\n"


def load_example_transcripts(
    *,
    repo_root: Path,
    mode: ExamplesMode = "excerpt",
    excerpt_lines_per_file: int = 120,
) -> str:
    if mode == "none":
        return ""

    t1 = repo_root / "00_initial_task" / "synthetic_transcript1.txt"
    t2 = repo_root / "00_initial_task" / "synthetic_transcript2.txt"

    text1 = _read_text(t1)
    text2 = _read_text(t2)

    if mode == "full":
        part1 = text1
        part2 = text2
    else:
        part1 = _excerpt(text1, excerpt_lines_per_file)
        part2 = _excerpt(text2, excerpt_lines_per_file)

    return (
        "STYLE EXEMPLARS (DO NOT COPY FACTS/NAMES; DO NOT OUTPUT TIMESTAMPS)\n"
        "These are synthetic transcript examples illustrating the desired imperfection, interruptions, and pacing.\n"
        "Use them only as style guidance.\n\n"
        "EXAMPLE TRANSCRIPT A\n"
        "---\n"
        + part1
        + "\nEXAMPLE TRANSCRIPT B\n"
        "---\n"
        + part2
    )

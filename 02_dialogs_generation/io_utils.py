from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, List


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> List[Any]:
    items: List[Any] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items


def save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def iter_json_objects(path: Path) -> Iterable[Any]:
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        yield from load_jsonl(path)
        return

    obj = load_json(path)
    if isinstance(obj, list):
        yield from obj
    else:
        # Single object
        yield obj

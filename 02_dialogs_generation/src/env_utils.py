from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Iterable


_ENV_LOAD_LOCK = threading.Lock()
_ENV_LOADED_FROM: set[str] = set()


def _parse_env_line(line: str) -> tuple[str, str] | None:
    s = line.strip()
    if not s or s.startswith("#") or "=" not in s:
        return None
    key, value = s.split("=", 1)
    key = key.strip()
    if not key:
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return key, value


def _candidate_env_paths(start_dir: Path) -> Iterable[Path]:
    seen: set[Path] = set()
    cur = start_dir.resolve()
    for base in [cur, *cur.parents]:
        p = base / ".env"
        if p not in seen:
            seen.add(p)
            yield p
    module_env = Path(__file__).resolve().parent / ".env"
    if module_env not in seen:
        yield module_env


def load_dotenv_if_present(start_dir: Path | None = None) -> None:
    base = start_dir or Path.cwd()
    for path in _candidate_env_paths(base):
        if not path.exists() or not path.is_file():
            continue
        key = str(path.resolve())
        with _ENV_LOAD_LOCK:
            if key in _ENV_LOADED_FROM:
                continue
            for raw in path.read_text(encoding="utf-8").splitlines():
                parsed = _parse_env_line(raw)
                if not parsed:
                    continue
                env_key, env_value = parsed
                os.environ.setdefault(env_key, env_value)
            _ENV_LOADED_FROM.add(key)


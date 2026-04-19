from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from openai import OpenAI

from env_utils import load_dotenv_if_present


logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


def _extract_json(text: str) -> Any:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except Exception:
        pass

    decoder = json.JSONDecoder()
    starts = [m.start() for m in re.finditer(r"[\{\[]", text)]
    for pos in starts:
        try:
            obj, _end = decoder.raw_decode(text[pos:])
            return obj
        except Exception:
            continue

    raise LLMError("Model did not return JSON")


def _usage_summary(resp: Any) -> str:
    usage = getattr(resp, "usage", None)
    if not usage:
        return "usage=n/a"
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    total_tokens = getattr(usage, "total_tokens", None)
    if isinstance(usage, dict):
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        total_tokens = usage.get("total_tokens")
    parts = []
    if input_tokens is not None:
        parts.append(f"in={input_tokens}")
    if output_tokens is not None:
        parts.append(f"out={output_tokens}")
    if total_tokens is not None:
        parts.append(f"total={total_tokens}")
    return "usage=" + (" ".join(parts) if parts else "n/a")


@dataclass(frozen=True)
class OpenAIResponsesClient:
    model: str = "gpt-5.2"
    temperature: float = 0.0
    max_output_tokens: int = 6000
    seed: Optional[int] = None

    def __post_init__(self) -> None:
        load_dotenv_if_present()
        if not os.getenv("OPENAI_API_KEY"):
            raise LLMError("OPENAI_API_KEY is not set (expected in 03_data_extraction/.env)")

    def _client(self) -> OpenAI:
        timeout_s = os.getenv("OPENAI_TIMEOUT_S")
        max_retries = os.getenv("OPENAI_MAX_RETRIES")
        kwargs: Dict[str, Any] = {}
        if timeout_s is not None and str(timeout_s).strip() != "":
            try:
                kwargs["timeout"] = float(timeout_s)
            except ValueError:
                logger.warning("Invalid OPENAI_TIMEOUT_S=%r; ignoring", timeout_s)
        if max_retries is not None and str(max_retries).strip() != "":
            try:
                kwargs["max_retries"] = int(max_retries)
            except ValueError:
                logger.warning("Invalid OPENAI_MAX_RETRIES=%r; ignoring", max_retries)
        return OpenAI(**kwargs)

    def create_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: Optional[int] = None,
    ) -> Any:
        client = self._client()
        out_lim = self.max_output_tokens if max_output_tokens is None else int(max_output_tokens)
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "instructions": system_prompt,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": user_prompt}]}],
            "temperature": float(self.temperature),
            "max_output_tokens": out_lim,
        }
        if self.seed is not None:
            kwargs["seed"] = int(self.seed)

        logger.info(
            "openai.responses.create | model=%s max_output_tokens=%s temp=%s seed=%s | prompt_chars=%s",
            self.model,
            out_lim,
            self.temperature,
            self.seed,
            len(system_prompt) + len(user_prompt),
        )
        t0 = time.perf_counter()
        try:
            resp = client.responses.create(**kwargs)
        except TypeError as e:
            if "seed" in kwargs and "unexpected keyword" in str(e):
                kwargs.pop("seed", None)
                resp = client.responses.create(**kwargs)
            else:
                raise
        dt = time.perf_counter() - t0
        out_text = getattr(resp, "output_text", "") or ""
        logger.info(
            "openai.responses.create | done | dt=%.2fs %s | output_chars=%s",
            dt,
            _usage_summary(resp),
            len(out_text),
        )
        return _extract_json(out_text)

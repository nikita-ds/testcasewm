from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Type, TypeVar

from openai import OpenAI
from pydantic import BaseModel


logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


T = TypeVar("T", bound=BaseModel)


def _extract_json(text: str) -> Any:
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass

    # Try to extract the first JSON object/array.
    match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
    if not match:
        raise LLMError("Model did not return JSON")
    candidate = match.group(1)
    return json.loads(candidate)


@dataclass(frozen=True)
class OpenAIResponsesClient:
    model: str
    temperature: float
    max_output_tokens: int
    seed: Optional[int] = None

    def __post_init__(self) -> None:
        if not os.getenv("OPENAI_API_KEY"):
            raise LLMError("OPENAI_API_KEY is not set")

    def _client(self) -> OpenAI:
        return OpenAI()

    def _usage_summary(self, resp: Any) -> str:
        usage = getattr(resp, "usage", None)
        if not usage:
            return "usage=n/a"
        # OpenAI SDK may return pydantic-like objects or dicts.
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

    def create_text(self, *, system_prompt: str, user_prompt: str) -> str:
        client = self._client()
        t0 = time.perf_counter()
        kwargs: Dict[str, Any] = {
            "model": self.model,
            # Prefer Responses API "instructions" for the system prompt.
            "instructions": system_prompt,
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": user_prompt}],
                },
            ],
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
        }
        if self.seed is not None:
            kwargs["seed"] = self.seed

        logger.info(
            "openai.responses.create | model=%s max_output_tokens=%s temp=%s seed=%s | prompt_chars=%s",
            self.model,
            self.max_output_tokens,
            self.temperature,
            self.seed,
            len(system_prompt) + len(user_prompt),
        )

        try:
            resp = client.responses.create(**kwargs)
        except TypeError as e:
            # Some OpenAI SDK versions do not support passing `seed` into Responses API.
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
            self._usage_summary(resp),
            len(out_text),
        )
        return resp.output_text

    def create_json(self, *, system_prompt: str, user_prompt: str, schema: Type[T]) -> T:
        text = self.create_text(system_prompt=system_prompt, user_prompt=user_prompt)
        obj = _extract_json(text)
        return schema.model_validate(obj)

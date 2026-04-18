from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Type, TypeVar

from openai import OpenAI
from pydantic import BaseModel


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

    def create_text(self, *, system_prompt: str, user_prompt: str) -> str:
        client = self._client()
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [{"type": "text", "text": user_prompt}],
                },
            ],
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
        }
        if self.seed is not None:
            kwargs["seed"] = self.seed

        resp = client.responses.create(**kwargs)
        return resp.output_text

    def create_json(self, *, system_prompt: str, user_prompt: str, schema: Type[T]) -> T:
        text = self.create_text(system_prompt=system_prompt, user_prompt=user_prompt)
        obj = _extract_json(text)
        return schema.model_validate(obj)

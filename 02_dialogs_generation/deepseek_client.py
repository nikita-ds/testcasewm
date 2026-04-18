from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Type, TypeVar

from openai import OpenAI
from pydantic import BaseModel

from env_utils import load_dotenv_if_present
from openai_client import LLMError, _extract_json


logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class DeepSeekChatClient:
    model: str
    max_output_tokens: int
    temperature: float = 0.0

    def __post_init__(self) -> None:
        load_dotenv_if_present(Path(__file__).resolve().parent)
        if not os.getenv("DEEPSEEK_KEY"):
            raise LLMError("DEEPSEEK_KEY is not set")

    def _client(self) -> OpenAI:
        timeout_s = os.getenv("DEEPSEEK_TIMEOUT_S") or os.getenv("OPENAI_TIMEOUT_S")
        max_retries = os.getenv("DEEPSEEK_MAX_RETRIES") or os.getenv("OPENAI_MAX_RETRIES")
        kwargs: Dict[str, Any] = {
            "api_key": os.environ["DEEPSEEK_KEY"],
            "base_url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        }
        if timeout_s is not None and str(timeout_s).strip() != "":
            try:
                kwargs["timeout"] = float(timeout_s)
            except ValueError:
                logger.warning("Invalid DEEPSEEK_TIMEOUT_S=%r; ignoring", timeout_s)
        if max_retries is not None and str(max_retries).strip() != "":
            try:
                kwargs["max_retries"] = int(max_retries)
            except ValueError:
                logger.warning("Invalid DEEPSEEK_MAX_RETRIES=%r; ignoring", max_retries)
        return OpenAI(**kwargs)

    def create_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: Type[T],
        max_output_tokens: Optional[int] = None,
    ) -> T:
        client = self._client()
        out_lim = self.max_output_tokens if max_output_tokens is None else int(max_output_tokens)
        t0 = time.perf_counter()
        logger.info(
            "deepseek.chat.completions.create | model=%s max_output_tokens=%s temp=%s | prompt_chars=%s",
            self.model,
            out_lim,
            self.temperature,
            len(system_prompt) + len(user_prompt),
        )
        resp = client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=out_lim,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        dt = time.perf_counter() - t0
        text = ""
        try:
            text = resp.choices[0].message.content or ""
        except Exception as exc:
            raise LLMError(f"DeepSeek returned no content: {exc!r}") from exc
        logger.info(
            "deepseek.chat.completions.create | done | dt=%.2fs | output_chars=%s",
            dt,
            len(text),
        )
        try:
            obj = _extract_json(text)
            return schema.model_validate(obj)
        except Exception as exc:
            logger.warning("DeepSeek JSON parse/validate failed: %s", repr(exc))
            preview = text[:400].replace("\n", " ")
            raise LLMError(f"DeepSeek returned invalid JSON: {preview}") from exc

    def create_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: Optional[int] = None,
    ) -> str:
        client = self._client()
        out_lim = self.max_output_tokens if max_output_tokens is None else int(max_output_tokens)
        t0 = time.perf_counter()
        logger.info(
            "deepseek.chat.completions.create | model=%s max_output_tokens=%s temp=%s | prompt_chars=%s",
            self.model,
            out_lim,
            self.temperature,
            len(system_prompt) + len(user_prompt),
        )
        resp = client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=out_lim,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        dt = time.perf_counter() - t0
        text = ""
        try:
            text = resp.choices[0].message.content or ""
        except Exception as exc:
            raise LLMError(f"DeepSeek returned no content: {exc!r}") from exc
        logger.info(
            "deepseek.chat.completions.create | done | dt=%.2fs | output_chars=%s",
            dt,
            len(text),
        )
        return text

    def create_realism_score_0_100(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: Optional[int] = None,
    ) -> int:
        """Return an integer realism score in [0, 100].

        The prompt is expected to instruct the model to output a single integer. We still
        parse defensively to tolerate extra whitespace or accidental prose.
        """

        text = self.create_text(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_output_tokens=max_output_tokens,
        )
        s = (text or "").strip()
        if s.isdigit():
            score = int(s)
        else:
            m = re.search(r"-?\d+", s)
            if not m:
                preview = s[:200].replace("\n", " ")
                raise LLMError(f"DeepSeek did not return a number: {preview}")
            score = int(m.group(0))
        if score < 0 or score > 100:
            raise LLMError(f"DeepSeek score out of range [0,100]: {score}")
        return score


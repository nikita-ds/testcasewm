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

    # Try to parse the first JSON value inside the text, even if the model
    # accidentally appends extra trailing text or a second JSON value.
    decoder = json.JSONDecoder()
    starts = [m.start() for m in re.finditer(r"[\{\[]", text)]
    for pos in starts:
        try:
            obj, _end = decoder.raw_decode(text[pos:])
            return obj
        except Exception:
            continue

    raise LLMError("Model did not return JSON")


def _truncate_for_prompt(text: str, *, max_chars: int = 12000) -> str:
    s = (text or "").strip()
    if max_chars <= 0 or len(s) <= max_chars:
        return s
    # Keep the head and tail to preserve structure hints.
    head = s[: max_chars // 2]
    tail = s[-(max_chars - len(head)) :]
    return head + "\n...<truncated>...\n" + tail


@dataclass(frozen=True)
class OpenAIResponsesClient:
    model: str
    temperature: float
    max_output_tokens: int
    seed: Optional[int] = None

    def __post_init__(self) -> None:
        load_dotenv_if_present(Path(__file__).resolve().parent)
        if not os.getenv("OPENAI_API_KEY"):
            raise LLMError("OPENAI_API_KEY is not set")

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

    def create_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        client = self._client()
        t0 = time.perf_counter()
        out_lim = self.max_output_tokens if max_output_tokens is None else int(max_output_tokens)
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
            "max_output_tokens": out_lim,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format
        if self.seed is not None:
            kwargs["seed"] = self.seed

        logger.info(
            "openai.responses.create | model=%s max_output_tokens=%s temp=%s seed=%s | prompt_chars=%s",
            self.model,
            out_lim,
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

    def create_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: Type[T],
        max_output_tokens: Optional[int] = None,
    ) -> T:
        response_format: Optional[Dict[str, Any]] = None
        try:
            # Structured Outputs: force the model to emit valid JSON matching this schema.
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": getattr(schema, "__name__", "Schema"),
                    "schema": schema.model_json_schema(),
                    "strict": True,
                },
            }
        except Exception:
            response_format = None

        try:
            text = self.create_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_output_tokens=max_output_tokens,
                response_format=response_format,
            )
        except TypeError:
            # Older SDKs may not support response_format for Responses API.
            text = self.create_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_output_tokens=max_output_tokens,
            )
        try:
            obj = _extract_json(text)
            if isinstance(obj, dict) and obj.keys() == {"root"} and bool(getattr(schema, "__pydantic_root_model__", False)):
                obj = obj["root"]
            return schema.model_validate(obj)
        except Exception as e:
            # Common failure mode: output truncated at max_output_tokens or minor JSON mistakes.
            # Retry once by asking the model to return corrected JSON only.
            logger.warning("create_json parse/validate failed; retrying once: %s", repr(e))
            is_root_model = bool(getattr(schema, "__pydantic_root_model__", False))
            if is_root_model:
                repair_prompt = (
                    user_prompt
                    + "\n\n"
                    + "IMPORTANT: Your previous response was invalid or truncated JSON. "
                    + "Regenerate the answer from scratch.\n"
                    + "Return ONLY ONE valid JSON ARRAY (not an object, not markdown, no extra text).\n"
                    + "No extra text. Keep strings/bullets short.\n\n"
                    + "PREVIOUS (INVALID/TRUNCATED) OUTPUT (for debugging only, do not reuse verbatim):\n"
                    + _truncate_for_prompt(text)
                )
            else:
                # Make the repair prompt schema-aware to avoid returning a bare list/array.
                top_keys = list(getattr(schema, "model_fields", {}).keys())
                keys_hint = ", ".join(f"{k}" for k in top_keys) if top_keys else "(unknown)"
                repair_prompt = (
                    user_prompt
                    + "\n\n"
                    + "IMPORTANT: Your previous response was invalid or truncated JSON. "
                    + "Regenerate the answer from scratch.\n"
                    + "Return ONLY ONE valid JSON OBJECT (not an array, not markdown, no extra text).\n"
                    + f"Top-level keys must be exactly: [{keys_hint}].\n"
                    + "No extra keys. Keep strings/bullets short.\n\n"
                    + "PREVIOUS (INVALID/TRUNCATED) OUTPUT (for debugging only, do not reuse verbatim):\n"
                    + _truncate_for_prompt(text)
                )
            try:
                text2 = self.create_text(
                    system_prompt=system_prompt,
                    user_prompt=repair_prompt,
                    max_output_tokens=max_output_tokens,
                    response_format=response_format,
                )
            except TypeError:
                text2 = self.create_text(
                    system_prompt=system_prompt,
                    user_prompt=repair_prompt,
                    max_output_tokens=max_output_tokens,
                )
            obj2 = _extract_json(text2)
            if isinstance(obj2, dict) and obj2.keys() == {"root"} and bool(getattr(schema, "__pydantic_root_model__", False)):
                obj2 = obj2["root"]
            return schema.model_validate(obj2)

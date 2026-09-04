"""
RECON OS — NVIDIA NIM provider (optional).

Implements `LLMProvider.generate_structured` against an NVIDIA NIM endpoint
using its OpenAI-compatible `/chat/completions` API (works identically for
NVIDIA's hosted API catalog and a self-hosted NIM container — only
`NVIDIA_NIM_BASE_URL` differs). Uses `httpx` (already a project dependency —
no new package).

Mirrors integrations/llm/gemini.py's exact safety contract:
  * The API key is read from server-side settings only, sent as a Bearer
    `Authorization` header (never in the URL, never in logs).
  * On ANY problem (timeout, 429, 5xx, bad JSON, empty response) this returns
    `StructuredLLMResult(ok=False, ...)` so the caller falls back to the
    deterministic engine. It never raises.
  * This class only returns structured JSON. It has no capability to call
    Razorpay, move money, or influence the deterministic policy/prediction.

NOTE on structured output: uses NVIDIA NIM's `guided_json` request field
(https://docs.nvidia.com/nim/large-language-models/latest/structured-generation.html),
which NVIDIA's own docs recommend over `response_format: {"type":
"json_object"}` specifically because `json_object` "permits the model to
produce any valid JSON, including empty objects" — i.e. it does not enforce
the caller's schema at all, which is exactly what caused an early NVIDIA
response to omit required fields (`probable_cause`, `rationale`) during
local validation. `guided_json` is passed as a plain top-level field in the
JSON request body (this is what the OpenAI SDK's `extra_body={"guided_json":
schema}` parameter actually sends over the wire — this provider talks HTTP
directly via httpx, so the field is set explicitly here instead).

This is defense in depth, not the sole safety mechanism: even if a given
NIM deployment or model ignores `guided_json` (an unrecognised field is
just extra JSON, never a source of code execution or an error by itself),
every caller (ai_diagnosis.py, ai_intent.py) still independently and
strictly re-validates the returned dict against its own Pydantic schema
before using it — exactly as it does for Gemini's output — and falls back
to the deterministic result on any validation failure, missing field
included. Nothing about that fallback safety net changed.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

import httpx

from config import settings
from integrations.llm.provider import LLMProvider, StructuredLLMResult

logger = logging.getLogger("recon.integrations.llm.nvidia_nim")


class NvidiaNimProvider(LLMProvider):
    name = "NVIDIA_NIM"

    def __init__(self) -> None:
        self._model = settings.resolved_llm_model("nvidia_nim")
        self._key = settings.resolved_llm_key("nvidia_nim")
        self._base_url = (settings.NVIDIA_NIM_BASE_URL or "").rstrip("/")
        self._timeout = float(settings.LLM_TIMEOUT_SECONDS or 8.0)
        if not self._key:
            # get_llm_provider() guards against this, but stay defensive.
            raise ValueError("NVIDIA NIM API key not configured")
        if not self._model:
            # Deliberately no hardcoded default model — NVIDIA's NIM catalog
            # spans many models with different capabilities/costs; guessing
            # one would be exactly the kind of invented configuration this
            # project avoids. NVIDIA_NIM_MODEL must be set explicitly.
            raise ValueError("NVIDIA_NIM_MODEL not configured")
        if not self._base_url:
            raise ValueError("NVIDIA_NIM_BASE_URL not configured")

    # ------------------------------------------------------------------
    def generate_structured(
        self,
        *,
        system: str,
        prompt: str,
        json_schema: Dict[str, Any],
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> StructuredLLMResult:
        url = f"{self._base_url}/chat/completions"
        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            # Schema-enforced structured output (NVIDIA's recommended
            # mechanism — see the module docstring). The caller's actual
            # json_schema is passed through untouched; RECON never narrows
            # or invents a schema here.
            "guided_json": json_schema,
        }
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}

        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(url, json=body, headers=headers)
        except httpx.TimeoutException:
            logger.warning("NVIDIA NIM request timed out after %.1fs", self._timeout)
            return self._fail("timeout")
        except httpx.HTTPError as e:
            logger.warning("NVIDIA NIM transport error: %s", type(e).__name__)
            return self._fail("api_error")

        if resp.status_code == 429:
            logger.warning("NVIDIA NIM rate limited (429)")
            return self._fail("rate_limited")
        if resp.status_code >= 400:
            # Never log the response body — it can echo the request/key context.
            logger.warning("NVIDIA NIM API error: HTTP %s", resp.status_code)
            return self._fail("api_error")

        try:
            payload = resp.json()
        except (json.JSONDecodeError, ValueError):
            logger.warning("NVIDIA NIM returned a non-JSON envelope")
            return self._fail("invalid_json")

        text = self._extract_text(payload)
        if not text:
            logger.warning("NVIDIA NIM returned an empty completion")
            return self._fail("empty_response")

        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            logger.warning("NVIDIA NIM structured output was not valid JSON")
            return self._fail("invalid_json", raw_text=text)

        if not isinstance(data, dict):
            return self._fail("invalid_json", raw_text=text)

        usage = payload.get("usage", {}) or {}
        return StructuredLLMResult(
            ok=True,
            data=data,
            raw_text=text,  # transient only; caller must not persist it
            provider="NVIDIA_NIM",
            model=self._model,
            usage={
                "prompt_tokens": usage.get("prompt_tokens"),
                "output_tokens": usage.get("completion_tokens"),
            },
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _extract_text(payload: Dict[str, Any]) -> str:
        try:
            return (payload["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError):
            return ""

    def _fail(self, error: str, raw_text: str | None = None) -> StructuredLLMResult:
        return StructuredLLMResult(
            ok=False, error=error, raw_text=raw_text, provider="NVIDIA_NIM", model=self._model
        )

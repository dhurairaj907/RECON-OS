"""
RECON OS — Gemini provider (optional).

Implements `LLMProvider.generate_structured` against the Google Generative
Language REST API using `httpx` (already a project dependency — no new package).

SAFETY / SECRECY:
  * The API key is read from server-side settings only, sent as the
    `x-goog-api-key` request header (never in the URL, never in logs).
  * On ANY problem (timeout, 429, 5xx, bad JSON, empty response) this returns
    `StructuredLLMResult(ok=False, ...)` so the caller falls back to the
    deterministic engine. It never raises.
  * This class only returns structured JSON. It has no capability to call
    Razorpay, move money, or influence the deterministic policy/prediction.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

import httpx

from config import settings
from integrations.llm.provider import LLMProvider, StructuredLLMResult

logger = logging.getLogger("recon.integrations.llm.gemini")

_API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(LLMProvider):
    name = "GEMINI"

    def __init__(self) -> None:
        self._model = settings.resolved_llm_model("gemini")
        self._key = settings.resolved_llm_key("gemini")
        self._timeout = float(settings.LLM_TIMEOUT_SECONDS or 8.0)
        if not self._key:
            # get_llm_provider() guards against this, but stay defensive.
            raise ValueError("Gemini API key not configured")

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
        url = f"{_API_ROOT}/{self._model}:generateContent"
        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "responseMimeType": "application/json",
                "responseSchema": json_schema,
            },
        }
        headers = {"x-goog-api-key": self._key, "Content-Type": "application/json"}

        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(url, json=body, headers=headers)
        except httpx.TimeoutException:
            logger.warning("Gemini request timed out after %.1fs", self._timeout)
            return self._fail("timeout")
        except httpx.HTTPError as e:
            logger.warning("Gemini transport error: %s", type(e).__name__)
            return self._fail("api_error")

        if resp.status_code == 429:
            logger.warning("Gemini rate limited (429)")
            return self._fail("rate_limited")
        if resp.status_code >= 400:
            # Never log the response body — it can echo the request/key context.
            logger.warning("Gemini API error: HTTP %s", resp.status_code)
            return self._fail("api_error")

        try:
            payload = resp.json()
        except (json.JSONDecodeError, ValueError):
            logger.warning("Gemini returned a non-JSON envelope")
            return self._fail("invalid_json")

        text = self._extract_text(payload)
        if not text:
            logger.warning("Gemini returned an empty / blocked candidate")
            return self._fail("empty_response")

        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Gemini structured output was not valid JSON")
            return self._fail("invalid_json", raw_text=text)

        if not isinstance(data, dict):
            return self._fail("invalid_json", raw_text=text)

        usage = payload.get("usageMetadata", {}) or {}
        return StructuredLLMResult(
            ok=True,
            data=data,
            raw_text=text,  # transient only; caller must not persist it
            provider="GEMINI",
            model=self._model,
            usage={
                "prompt_tokens": usage.get("promptTokenCount"),
                "output_tokens": usage.get("candidatesTokenCount"),
            },
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _extract_text(payload: Dict[str, Any]) -> str:
        try:
            parts = payload["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts).strip()
        except (KeyError, IndexError, TypeError):
            return ""

    def _fail(self, error: str, raw_text: str | None = None) -> StructuredLLMResult:
        return StructuredLLMResult(
            ok=False, error=error, raw_text=raw_text, provider="GEMINI", model=self._model
        )

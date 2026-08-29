"""
RECON OS — LLM provider interface.

A provider takes a system prompt + user prompt + a JSON schema and returns
structured data. Implementations are added later (Anthropic, Gemini, ...). No
provider is hardcoded; selection is driven by `settings.LLM_PROVIDER`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class StructuredLLMResult:
    ok: bool
    data: Optional[Dict[str, Any]] = None
    raw_text: Optional[str] = None          # kept transient only; never persisted
    error: Optional[str] = None
    provider: str = "NONE"
    model: str = ""
    usage: Dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    def generate_structured(
        self,
        *,
        system: str,
        prompt: str,
        json_schema: Dict[str, Any],
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> StructuredLLMResult:
        """Return structured JSON matching `json_schema`, or ok=False on failure."""
        raise NotImplementedError


class NullProvider(LLMProvider):
    """Used when LLM_ENABLED=false. Always signals 'unavailable' so callers fall
    back to the deterministic implementation."""

    name = "NULL"

    def generate_structured(self, **kwargs) -> StructuredLLMResult:  # noqa: ARG002
        return StructuredLLMResult(
            ok=False,
            error="LLM disabled — deterministic fallback in use",
            provider="NULL",
        )

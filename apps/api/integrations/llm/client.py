"""
RECON OS — LLM provider factory.

`get_llm_provider()` returns a concrete provider when LLM_ENABLED is true and a
provider/key are configured; otherwise it returns `NullProvider` so every caller
transparently falls back to deterministic intelligence.

Concrete providers (Anthropic / Gemini / ...) are intentionally not implemented
yet — Phase 2 ships deterministic-first. Adding one means implementing
`LLMProvider.generate_structured` and registering it in `_PROVIDERS`.
"""

import logging

from config import settings
from integrations.llm.provider import LLMProvider, NullProvider

logger = logging.getLogger("recon.integrations.llm")

# name -> factory callable. Populated as real providers are added.
_PROVIDERS: dict = {}


def llm_available() -> bool:
    return bool(
        settings.LLM_ENABLED
        and settings.LLM_PROVIDER
        and settings.LLM_API_KEY
        and settings.LLM_PROVIDER.lower() in _PROVIDERS
    )


def get_llm_provider() -> LLMProvider:
    if not settings.LLM_ENABLED:
        return NullProvider()

    key = (settings.LLM_PROVIDER or "").lower()
    factory = _PROVIDERS.get(key)
    if factory is None:
        logger.warning(
            "LLM_ENABLED is true but provider '%s' is not implemented — "
            "using deterministic fallback.", settings.LLM_PROVIDER,
        )
        return NullProvider()

    if not settings.LLM_API_KEY:
        logger.warning("LLM provider '%s' selected but no API key configured — "
                       "using deterministic fallback.", key)
        return NullProvider()

    try:
        return factory()
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to initialise LLM provider '%s' — deterministic fallback.", key)
        return NullProvider()

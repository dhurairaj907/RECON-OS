"""
RECON OS — LLM provider factory.

`get_llm_provider()` returns a concrete provider when LLM_ENABLED is true and a
provider + key are configured; otherwise it returns `NullProvider` so every
caller transparently falls back to the deterministic intelligence core.

Registered providers live in `_PROVIDERS`. Adding one means implementing
`LLMProvider.generate_structured` and registering its factory here.
"""

import logging

from config import settings
from integrations.llm.provider import LLMProvider, NullProvider

logger = logging.getLogger("recon.integrations.llm")


def _make_gemini() -> LLMProvider:
    from integrations.llm.gemini import GeminiProvider
    return GeminiProvider()


# name -> factory callable
_PROVIDERS: dict = {
    "gemini": _make_gemini,
}


def _resolved_key(provider: str) -> str:
    return settings.resolved_llm_key(provider)


def llm_available() -> bool:
    """True only when a real provider could actually be constructed."""
    if not settings.LLM_ENABLED:
        return False
    name = (settings.LLM_PROVIDER or "").lower()
    return bool(name in _PROVIDERS and _resolved_key(name))


def get_llm_provider() -> LLMProvider:
    if not settings.LLM_ENABLED:
        return NullProvider()

    name = (settings.LLM_PROVIDER or "").lower()
    factory = _PROVIDERS.get(name)
    if factory is None:
        logger.warning(
            "LLM_ENABLED is true but provider '%s' is not registered — "
            "using deterministic fallback.", settings.LLM_PROVIDER,
        )
        return NullProvider()

    if not _resolved_key(name):
        logger.warning(
            "LLM provider '%s' selected but no API key configured — "
            "using deterministic fallback.", name,
        )
        return NullProvider()

    try:
        return factory()
    except Exception:
        logger.exception(
            "Failed to initialise LLM provider '%s' — deterministic fallback.", name
        )
        return NullProvider()

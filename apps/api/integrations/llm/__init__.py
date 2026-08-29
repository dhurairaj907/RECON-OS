"""
RECON OS — LLM Provider Abstraction  (Phase 2, optional)

The deterministic intelligence core is the baseline and the fallback. This
package exists so that, later, specific components (diagnosis, rationale,
customer-communication drafts) can OPTIONALLY be assisted by an LLM.

Hard rules enforced by design:
  * The application runs fully with LLM_ENABLED=false.
  * API keys are read only from server-side settings — never returned in a
    response, never logged, never exposed to the frontend.
  * An LLM may NEVER drive: recovery-probability calculation, policy decisions,
    approvals, retry authorisation, Payment Link creation, or any money movement.
    Those remain deterministic (Phase 2) / Phase 3.
"""

from integrations.llm.provider import LLMProvider, NullProvider, StructuredLLMResult
from integrations.llm.client import get_llm_provider, llm_available

__all__ = [
    "LLMProvider",
    "NullProvider",
    "StructuredLLMResult",
    "get_llm_provider",
    "llm_available",
]

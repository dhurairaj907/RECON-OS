"""
RECON OS — Multi-provider LLM abstraction tests.

Covers the NVIDIA NIM provider added alongside Gemini:
 - provider registry / get_llm_provider() resolution and safe fallback
 - NvidiaNimProvider unit-level transport/parsing behaviour (mirrors the
   existing GeminiProvider unit tests in test_ai_diagnosis.py)
 - ai_diagnosis.diagnose_case() stays provider-agnostic: NVIDIA NIM success
   normalises the same way Gemini's does, and every NVIDIA failure mode
   falls back to the deterministic core exactly like Gemini's does
 - the diagnosis_source() UI label generalises to any real AI provider,
   not just "GEMINI"
 - the provider_version hardcode bug (previously always resolved via
   resolved_llm_model("gemini") regardless of the active provider) is fixed
"""

from decimal import Decimal

import httpx
import pytest

from config import settings
from integrations.llm.client import get_llm_provider, llm_available
from integrations.llm.provider import NullProvider, StructuredLLMResult
from models.case_intelligence import CaseIntelligence
from schemas.intelligence import CaseContext
from services.intelligence import ai_diagnosis as aid
from services.intelligence.weights import amount_band


def make_context(**overrides) -> CaseContext:
    base = dict(
        case_id="00000000-0000-0000-0000-000000000000",
        case_number="RC-NIM",
        case_status="DETECTED",
        amount=Decimal("4999.00"),
        currency="INR",
        attempt_count=0,
        max_attempts=3,
        hours_since_failure=0.5,
        payment_id="pay_nim",
        payment_status="failed",
        payment_method="wallet",
        failure_code="BAD_REQUEST_ERROR",
        failure_reason="payment_failed",
        failure_description=(
            "Your payment didn't go through due to a temporary issue. "
            "Any debited amount will be refunded in 4-5 business days."
        ),
        customer_successful_payments=0,
        customer_failed_payments=1,
        customer_success_rate=0.0,
        customer_has_history=False,
    )
    base.update(overrides)
    base["amount_band"] = amount_band(Decimal(base["amount"]))
    return CaseContext(**base)


class FakeProvider:
    def __init__(self, result: StructuredLLMResult):
        self.result = result
        self.calls = []

    def generate_structured(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


def _valid_ai_payload(category="TECHNICAL_GATEWAY", confidence=0.6):
    return {
        "failure_category": category,
        "probable_cause": "Temporary issuer-side processing issue, amount to be refunded",
        "confidence": confidence,
        "rationale": "error_code=BAD_REQUEST_ERROR with a temporary/refund-guaranteed description.",
        "evidence": ["failure_code=BAD_REQUEST_ERROR", "failure_reason=payment_failed"],
    }


# ==========================================================================
# 1. Provider registry
# ==========================================================================
def test_nvidia_nim_registered_in_provider_factory():
    from integrations.llm.client import _PROVIDERS
    assert "nvidia_nim" in _PROVIDERS
    assert "gemini" in _PROVIDERS


def test_get_llm_provider_returns_nvidia_nim_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "nvidia_nim")
    monkeypatch.setattr(settings, "NVIDIA_NIM_API_KEY", "nim-secret-DO-NOT-LEAK")
    monkeypatch.setattr(settings, "NVIDIA_NIM_MODEL", "meta/llama-3.1-8b-instruct")
    assert llm_available() is True
    from integrations.llm.nvidia_nim import NvidiaNimProvider
    provider = get_llm_provider()
    assert isinstance(provider, NvidiaNimProvider)


def test_get_llm_provider_falls_back_when_nvidia_key_missing(monkeypatch):
    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "nvidia_nim")
    monkeypatch.setattr(settings, "NVIDIA_NIM_API_KEY", "")
    monkeypatch.setattr(settings, "LLM_API_KEY", "")
    monkeypatch.setattr(settings, "NVIDIA_NIM_MODEL", "meta/llama-3.1-8b-instruct")
    assert llm_available() is False
    assert isinstance(get_llm_provider(), NullProvider)


def test_get_llm_provider_falls_back_when_nvidia_model_missing(monkeypatch):
    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "nvidia_nim")
    monkeypatch.setattr(settings, "NVIDIA_NIM_API_KEY", "nim-secret")
    monkeypatch.setattr(settings, "NVIDIA_NIM_MODEL", "")
    monkeypatch.setattr(settings, "LLM_MODEL", "")
    # llm_available() only checks the key, matching llm_available()'s existing
    # contract — the empty-model guard lives in the provider constructor and
    # get_llm_provider()'s own try/except, exactly like a Gemini construction
    # failure would be handled.
    provider = get_llm_provider()
    assert isinstance(provider, NullProvider)


# ==========================================================================
# 2. NvidiaNimProvider unit — transport/parsing (mirrors GeminiProvider)
# ==========================================================================
def _nim_settings(monkeypatch):
    monkeypatch.setattr(settings, "NVIDIA_NIM_API_KEY", "k")
    monkeypatch.setattr(settings, "NVIDIA_NIM_MODEL", "meta/llama-3.1-8b-instruct")
    monkeypatch.setattr(settings, "NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")


def test_nvidia_nim_provider_maps_timeout(monkeypatch):
    _nim_settings(monkeypatch)
    from integrations.llm.nvidia_nim import NvidiaNimProvider

    class _C:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, *a, **k): raise httpx.TimeoutException("slow")

    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _C())
    r = NvidiaNimProvider().generate_structured(system="s", prompt="p", json_schema={})
    assert r.ok is False and r.error == "timeout"


def test_nvidia_nim_provider_maps_429(monkeypatch):
    _nim_settings(monkeypatch)
    from integrations.llm.nvidia_nim import NvidiaNimProvider

    class _Resp:
        status_code = 429
        def json(self): return {}

    class _C:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, *a, **k): return _Resp()

    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _C())
    r = NvidiaNimProvider().generate_structured(system="s", prompt="p", json_schema={})
    assert r.ok is False and r.error == "rate_limited"


def test_nvidia_nim_provider_maps_server_error(monkeypatch):
    _nim_settings(monkeypatch)
    from integrations.llm.nvidia_nim import NvidiaNimProvider

    class _Resp:
        status_code = 500
        def json(self): return {}

    class _C:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, *a, **k): return _Resp()

    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _C())
    r = NvidiaNimProvider().generate_structured(system="s", prompt="p", json_schema={})
    assert r.ok is False and r.error == "api_error"


def test_nvidia_nim_provider_maps_invalid_json_content(monkeypatch):
    _nim_settings(monkeypatch)
    from integrations.llm.nvidia_nim import NvidiaNimProvider

    class _Resp:
        status_code = 200
        def json(self):
            return {"choices": [{"message": {"content": "not json"}}]}

    class _C:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, *a, **k): return _Resp()

    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _C())
    r = NvidiaNimProvider().generate_structured(system="s", prompt="p", json_schema={})
    assert r.ok is False and r.error == "invalid_json"


def test_nvidia_nim_provider_maps_empty_completion(monkeypatch):
    _nim_settings(monkeypatch)
    from integrations.llm.nvidia_nim import NvidiaNimProvider

    class _Resp:
        status_code = 200
        def json(self):
            return {"choices": [{"message": {"content": ""}}]}

    class _C:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, *a, **k): return _Resp()

    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _C())
    r = NvidiaNimProvider().generate_structured(system="s", prompt="p", json_schema={})
    assert r.ok is False and r.error == "empty_response"


def test_nvidia_nim_provider_success_returns_structured_data(monkeypatch):
    _nim_settings(monkeypatch)
    from integrations.llm.nvidia_nim import NvidiaNimProvider
    import json as _json

    content = _json.dumps({"failure_category": "TECHNICAL_GATEWAY", "confidence": 0.6,
                            "probable_cause": "x", "rationale": "y", "evidence": []})

    class _Resp:
        status_code = 200
        def json(self):
            return {"choices": [{"message": {"content": content}}],
                     "usage": {"prompt_tokens": 10, "completion_tokens": 5}}

    class _C:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, *a, **k): return _Resp()

    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _C())
    r = NvidiaNimProvider().generate_structured(system="s", prompt="p", json_schema={})
    assert r.ok is True
    assert r.provider == "NVIDIA_NIM"
    assert r.model == "meta/llama-3.1-8b-instruct"
    assert r.data["failure_category"] == "TECHNICAL_GATEWAY"
    assert r.usage["prompt_tokens"] == 10
    assert r.usage["output_tokens"] == 5


def test_nvidia_nim_provider_key_never_in_url_only_header(monkeypatch):
    """Same secrecy contract as Gemini: the key goes in a header, never the URL."""
    _nim_settings(monkeypatch)
    monkeypatch.setattr(settings, "NVIDIA_NIM_API_KEY", "SECRET-KEY-DO-NOT-LEAK")
    from integrations.llm.nvidia_nim import NvidiaNimProvider

    captured = {}

    class _Resp:
        status_code = 200
        def json(self): return {"choices": [{"message": {"content": "{}"}}]}

    class _C:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["headers"] = headers
            return _Resp()

    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _C())
    NvidiaNimProvider().generate_structured(system="s", prompt="p", json_schema={})
    assert "SECRET-KEY-DO-NOT-LEAK" not in captured["url"]
    assert captured["headers"]["Authorization"] == "Bearer SECRET-KEY-DO-NOT-LEAK"


def test_nvidia_nim_provider_sends_guided_json_with_caller_schema(monkeypatch):
    """
    Regression for the real gap found during local validation: NVIDIA's
    response_format=json_object mode does not enforce any schema at all
    (confirmed live — the model omitted required fields), so the provider
    must send the caller's actual json_schema via NVIDIA's documented
    guided_json field instead of silently discarding it.
    """
    _nim_settings(monkeypatch)
    from integrations.llm.nvidia_nim import NvidiaNimProvider

    schema = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}
    captured = {}

    class _Resp:
        status_code = 200
        def json(self): return {"choices": [{"message": {"content": '{"x": "y"}'}}]}

    class _C:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, json=None, headers=None):
            captured["body"] = json
            return _Resp()

    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _C())
    NvidiaNimProvider().generate_structured(system="s", prompt="p", json_schema=schema)
    assert captured["body"]["guided_json"] == schema
    assert captured["body"]["guided_json"] is schema  # passed through untouched, never narrowed


def test_nvidia_nim_provider_reasoning_content_never_extracted(monkeypatch):
    """
    Nemotron reasoning models return a sibling `reasoning_content` field
    alongside `content` in the message object (confirmed live). The
    extractor must only ever read `content` — reasoning_content must never
    reach StructuredLLMResult.data, and therefore can never reach
    DiagnosisResult.evidence/rationale/probable_cause, logs, audit records,
    or the frontend.
    """
    _nim_settings(monkeypatch)
    from integrations.llm.nvidia_nim import NvidiaNimProvider
    import json as _json

    real_content = _json.dumps({"failure_category": "TECHNICAL_GATEWAY", "confidence": 0.6,
                                 "probable_cause": "x", "rationale": "y", "evidence": []})
    secret_chain_of_thought = "SECRET_INTERNAL_REASONING_MUST_NEVER_LEAK"

    class _Resp:
        status_code = 200
        def json(self):
            return {"choices": [{"message": {
                "role": "assistant",
                "content": real_content,
                "reasoning_content": secret_chain_of_thought,
            }}]}

    class _C:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, *a, **k): return _Resp()

    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _C())
    r = NvidiaNimProvider().generate_structured(system="s", prompt="p", json_schema={})
    assert r.ok is True
    assert secret_chain_of_thought not in (r.raw_text or "")
    assert secret_chain_of_thought not in str(r.data)
    assert secret_chain_of_thought not in _json.dumps(r.data)


# ==========================================================================
# 3. ai_diagnosis.diagnose_case() stays provider-agnostic
# ==========================================================================
@pytest.fixture
def enable_nvidia_ai(monkeypatch):
    monkeypatch.setattr(settings, "LLM_ENABLED", True)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "nvidia_nim")
    monkeypatch.setattr(settings, "NVIDIA_NIM_API_KEY", "nim-secret")
    monkeypatch.setattr(settings, "NVIDIA_NIM_MODEL", "meta/llama-3.1-8b-instruct")
    monkeypatch.setattr(aid, "llm_available", lambda: True)

    def set_result(result: StructuredLLMResult):
        provider = FakeProvider(result)
        monkeypatch.setattr(aid, "get_llm_provider", lambda: provider)
        return provider

    return set_result


def test_nvidia_nim_valid_response_normalized(enable_nvidia_ai):
    enable_nvidia_ai(StructuredLLMResult(
        ok=True, data=_valid_ai_payload("TECHNICAL_GATEWAY", 0.6),
        provider="NVIDIA_NIM", model="meta/llama-3.1-8b-instruct",
    ))
    d, meta = aid.diagnose_case(make_context())
    assert d.provider == "NVIDIA_NIM"
    assert meta.used_ai is True
    # Regression: provider_version must reflect the ACTUAL active provider's
    # model, not be hardcoded to resolved_llm_model("gemini").
    assert d.provider_version == "meta/llama-3.1-8b-instruct"
    assert "gemini" not in d.provider_version.lower()


@pytest.mark.parametrize("result,expected_error", [
    (StructuredLLMResult(ok=False, error="timeout", provider="NVIDIA_NIM"), "timeout"),
    (StructuredLLMResult(ok=False, error="rate_limited", provider="NVIDIA_NIM"), "rate_limited"),
    (StructuredLLMResult(ok=False, error="invalid_json", provider="NVIDIA_NIM"), "invalid_json"),
])
def test_nvidia_nim_errors_fall_back_to_deterministic(enable_nvidia_ai, result, expected_error):
    enable_nvidia_ai(result)
    d, meta = aid.diagnose_case(make_context())
    assert d.provider == "DETERMINISTIC"
    assert meta.attempted is True
    assert meta.used_ai is False
    assert meta.error_type == expected_error
    # The real deterministic fallback fix from Phase 0 still applies —
    # BAD_REQUEST_ERROR/payment_failed resolves to TECHNICAL_GATEWAY even
    # when the AI attempt itself failed.
    assert d.failure_category.value == "TECHNICAL_GATEWAY"


def test_nvidia_nim_schema_violation_falls_back(enable_nvidia_ai):
    enable_nvidia_ai(StructuredLLMResult(
        ok=True, data={"failure_category": "NOT_A_REAL_CATEGORY", "confidence": 0.5,
                       "probable_cause": "x", "rationale": "y", "evidence": []},
        provider="NVIDIA_NIM", model="m",
    ))
    d, meta = aid.diagnose_case(make_context())
    assert d.provider == "DETERMINISTIC"
    assert meta.error_type == "schema_validation"


def test_nvidia_nim_missing_required_fields_falls_back(enable_nvidia_ai):
    """
    Exact regression for the real failure observed during local validation
    BEFORE the guided_json fix: NVIDIA returned syntactically valid JSON —
    failure_category, confidence, evidence — but omitted the two required
    fields probable_cause and rationale. This must still be rejected and
    fall back cleanly, never accepted as a partial result — proving the
    guided_json fix is defense in depth, not a replacement for validation.
    """
    enable_nvidia_ai(StructuredLLMResult(
        ok=True,
        data={"failure_category": "TECHNICAL_GATEWAY", "confidence": 0.7,
              "evidence": ["failure_code: BAD_REQUEST_ERROR"]},  # no probable_cause/rationale
        provider="NVIDIA_NIM", model="nvidia/nemotron-3-super-120b-a12b",
    ))
    d, meta = aid.diagnose_case(make_context())
    assert d.provider == "DETERMINISTIC"
    assert meta.used_ai is False
    assert meta.error_type == "schema_validation"
    # Phase 0 mapping still resolves correctly under fallback.
    assert d.failure_category.value == "TECHNICAL_GATEWAY"


def test_nvidia_nim_reasoning_content_isolated_through_full_diagnosis(enable_nvidia_ai):
    """End-to-end (diagnose_case + diagnosis_source), not just the provider
    unit test above: even if a FakeProvider's data dict somehow carried a
    reasoning_content-shaped key, AIDiagnosisSchema has no field for it, so
    strict validation strips/rejects anything outside the declared schema
    fields — it can never reach DiagnosisResult or the AI-ENHANCED label."""
    secret_chain_of_thought = "SECRET_INTERNAL_REASONING_MUST_NEVER_LEAK"
    payload = _valid_ai_payload("TECHNICAL_GATEWAY", 0.6)
    payload["reasoning_content"] = secret_chain_of_thought  # not a real schema field
    enable_nvidia_ai(StructuredLLMResult(
        ok=True, data=payload, provider="NVIDIA_NIM", model="nvidia/nemotron-3-super-120b-a12b",
    ))
    d, meta = aid.diagnose_case(make_context())
    assert meta.used_ai is True
    assert d.provider == "NVIDIA_NIM"
    assert secret_chain_of_thought not in d.rationale
    assert secret_chain_of_thought not in d.probable_cause
    assert secret_chain_of_thought not in " ".join(d.evidence)

    from routers.intelligence import diagnosis_source
    ci = CaseIntelligence(provider=d.provider, diagnosis_json=d.model_dump(mode="json"))
    assert diagnosis_source(ci) == "AI-ENHANCED"
    assert secret_chain_of_thought not in str(ci.diagnosis_json)


# ==========================================================================
# 4. diagnosis_source() UI label generalises beyond "GEMINI"
# ==========================================================================
def test_diagnosis_source_ai_enhanced_for_nvidia_nim():
    from routers.intelligence import diagnosis_source
    ci = CaseIntelligence(provider="NVIDIA_NIM", diagnosis_json={})
    assert diagnosis_source(ci) == "AI-ENHANCED"


def test_diagnosis_source_still_ai_enhanced_for_gemini():
    from routers.intelligence import diagnosis_source
    ci = CaseIntelligence(provider="GEMINI", diagnosis_json={})
    assert diagnosis_source(ci) == "AI-ENHANCED"


def test_diagnosis_source_deterministic_when_no_ai_attempted():
    from routers.intelligence import diagnosis_source
    ci = CaseIntelligence(provider="DETERMINISTIC", diagnosis_json={})
    assert diagnosis_source(ci) == "DETERMINISTIC"


def test_diagnosis_source_fallback_label_preserved():
    from routers.intelligence import diagnosis_source
    ci = CaseIntelligence(provider="DETERMINISTIC", diagnosis_json={"fallback_reason": "AI provider error (timeout)"})
    assert diagnosis_source(ci) == "DETERMINISTIC FALLBACK"

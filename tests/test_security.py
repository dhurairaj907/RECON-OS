"""
RECON OS — Phase 4: Minimal endpoint protection tests (security.py)

Covers the two independent controls placed in front of financial action
endpoints: the shared API key and the per-IP rate limiter. Does not touch
the Policy Engine / idempotency guards those endpoints already enforce —
those are covered in test_actions.py / test_phase4_safety.py.
"""

import pytest
from fastapi import HTTPException

from config import settings
import security


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    security._request_log.clear()
    security._warned_unset = False
    yield
    security._request_log.clear()


class _FakeClient:
    def __init__(self, host):
        self.host = host


class _FakeRequest:
    def __init__(self, host):
        self.client = _FakeClient(host)


def test_api_key_open_when_unset(monkeypatch):
    monkeypatch.setattr(settings, "RECON_API_KEY", "")
    security.require_api_key(x_recon_api_key=None)   # does not raise


def test_api_key_rejects_missing_key(monkeypatch):
    monkeypatch.setattr(settings, "RECON_API_KEY", "sekret123")
    with pytest.raises(HTTPException) as exc:
        security.require_api_key(x_recon_api_key=None)
    assert exc.value.status_code == 401


def test_api_key_rejects_wrong_key(monkeypatch):
    monkeypatch.setattr(settings, "RECON_API_KEY", "sekret123")
    with pytest.raises(HTTPException) as exc:
        security.require_api_key(x_recon_api_key="wrong")
    assert exc.value.status_code == 401


def test_api_key_accepts_correct_key(monkeypatch):
    monkeypatch.setattr(settings, "RECON_API_KEY", "sekret123")
    security.require_api_key(x_recon_api_key="sekret123")   # does not raise


def test_rate_limit_disabled_when_zero(monkeypatch):
    monkeypatch.setattr(settings, "RECON_RATE_LIMIT_PER_MINUTE", 0)
    req = _FakeRequest("1.2.3.4")
    for _ in range(100):
        security.rate_limit(req)   # never raises


def test_rate_limit_blocks_after_threshold(monkeypatch):
    monkeypatch.setattr(settings, "RECON_RATE_LIMIT_PER_MINUTE", 3)
    req = _FakeRequest("5.6.7.8")
    security.rate_limit(req)
    security.rate_limit(req)
    security.rate_limit(req)
    with pytest.raises(HTTPException) as exc:
        security.rate_limit(req)
    assert exc.value.status_code == 429


def test_rate_limit_is_per_client(monkeypatch):
    monkeypatch.setattr(settings, "RECON_RATE_LIMIT_PER_MINUTE", 1)
    req_a = _FakeRequest("10.0.0.1")
    req_b = _FakeRequest("10.0.0.2")
    security.rate_limit(req_a)   # consumes client A's only slot
    security.rate_limit(req_b)   # client B is unaffected
    with pytest.raises(HTTPException):
        security.rate_limit(req_a)


# ---------------------------------------------------------------------------
# End-to-end, over the real HTTP surface (client fixture) — not just the
# unit-level checks above. Confirms require_api_key is actually wired onto a
# real financial-action route, and that read-only/health routes are exempt.
# ---------------------------------------------------------------------------
def test_cors_allows_configured_origin_and_rejects_others(client):
    """Deployment-hardening: CORSMiddleware (main.py) must reflect
    Access-Control-Allow-Origin only for an origin actually present in
    CORS_ORIGINS — never a wildcard (incompatible with the credentialed
    session cookie anyway; see main.py's own comment), and never silently
    allow an arbitrary origin."""
    allowed = settings.CORS_ORIGINS[0]
    res_allowed = client.get("/api/v1/health", headers={"Origin": allowed})
    assert res_allowed.headers.get("access-control-allow-origin") == allowed

    res_disallowed = client.get("/api/v1/health", headers={"Origin": "https://not-allowed.example.com"})
    assert res_disallowed.headers.get("access-control-allow-origin") is None


def test_public_health_endpoint_requires_no_api_key(client, monkeypatch):
    monkeypatch.setattr(settings, "RECON_API_KEY", "sekret123")
    res = client.get("/api/v1/health")
    assert res.status_code == 200


def test_protected_endpoint_end_to_end_missing_invalid_valid_key(client, monkeypatch):
    sim = client.post("/api/v1/simulator/events", json={
        "event_type": "payment.failed", "customer_name": "API Key Test Customer",
        "customer_email": "apikeytest@recon.test", "customer_phone": "+919800001111",
        "amount": "2999.00", "payment_method": "upi", "failure_code": "BAD_REQUEST_ERROR",
        "failure_reason": "payment_failed",
        "error_description": "UPI handle authorization timeout on customer app",
    })
    assert sim.status_code == 201, sim.text
    case_number = sim.json()["case_number"]
    client.post(f"/api/v1/recovery-cases/{case_number}/intelligence:analyze")

    monkeypatch.setattr(settings, "RECON_API_KEY", "sekret123")

    missing = client.post(f"/api/v1/recovery-cases/{case_number}/actions/propose")
    assert missing.status_code == 401
    assert "sekret123" not in missing.text   # the key itself must never appear in a response

    invalid = client.post(
        f"/api/v1/recovery-cases/{case_number}/actions/propose",
        headers={"X-RECON-API-KEY": "wrong-key"},
    )
    assert invalid.status_code == 401

    valid = client.post(
        f"/api/v1/recovery-cases/{case_number}/actions/propose",
        headers={"X-RECON-API-KEY": "sekret123"},
    )
    assert valid.status_code == 200

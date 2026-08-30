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

"""
RECON OS — Evaluation harness: deterministic Razorpay double.

Same shape as the `razorpay_env` fixture in tests/test_actions.py, adapted
for standalone (non-pytest) use so evaluation scenarios can exercise the
REAL adapter/executor/verification code paths without a network call.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from unittest.mock import patch

import httpx

from config import settings


class RazorpayState:
    def __init__(self):
        self.mode = "success"          # success | timeout | transport
        self.status = 200
        self.body = None
        self.calls: list[dict] = []
        self.link_status = "created"
        self.link_amount = 0
        self.link_amount_paid = 0
        self.link_currency = "INR"
        self.get_calls: list[str] = []
        self.search_items: list[dict] = []


def _client_factory(state: RazorpayState):
    class _PostResp:
        def __init__(self, ref, amt):
            self.status_code = state.status
            self._ref, self._amt = ref, amt

        def json(self):
            if state.body is not None:
                return state.body
            return {
                "id": "plink_EVAL_" + uuid.uuid4().hex[:8],
                "short_url": "https://rzp.io/i/EVALLINK",
                "status": "created",
                "reference_id": self._ref,
                "amount": self._amt,
                "currency": "INR",
            }

    class _GetResp:
        status_code = 200

        def json(self):
            return {
                "id": state.get_calls[-1] if state.get_calls else "plink_EVAL",
                "status": state.link_status,
                "amount": state.link_amount,
                "amount_paid": state.link_amount_paid,
                "currency": state.link_currency,
                "payments": [],
            }

    class _ListResp:
        status_code = 200

        def json(self):
            return {"items": state.search_items}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None, auth=None, **k):
            state.calls.append({"url": url, "json": json, "auth": auth})
            if state.mode == "timeout":
                raise httpx.TimeoutException("slow")
            if state.mode == "transport":
                raise httpx.ConnectError("boom")
            return _PostResp(json["reference_id"], json["amount"])

        def get(self, url, auth=None, **k):
            if url.endswith("/payment_links"):
                if state.mode == "timeout":
                    raise httpx.TimeoutException("slow")
                return _ListResp()
            state.get_calls.append(url.rsplit("/", 1)[-1])
            if state.mode == "timeout":
                raise httpx.TimeoutException("slow")
            return _GetResp()

    return _Client


@contextmanager
def fake_razorpay(monkeypatch_settings=True):
    """Configures test-mode Razorpay credentials and patches the outbound
    httpx.Client used by integrations/razorpay/adapter.py. Yields the mutable
    RazorpayState so a scenario can flip mode/status/search_items mid-flow."""
    state = RazorpayState()
    key_id, key_secret, test_mode = settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET, settings.RAZORPAY_TEST_MODE
    settings.RAZORPAY_KEY_ID = "rzp_test_EVALFAKEKEY0001"
    settings.RAZORPAY_KEY_SECRET = "eval_fake_secret_never_leaked"
    settings.RAZORPAY_TEST_MODE = True
    try:
        with patch("integrations.razorpay.adapter.httpx.Client", _client_factory(state)):
            yield state
    finally:
        settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET, settings.RAZORPAY_TEST_MODE = key_id, key_secret, test_mode

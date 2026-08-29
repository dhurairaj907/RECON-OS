"""
RECON OS — Webhook Endpoint Tests

Validates:
1. Valid signature acceptance
2. Invalid signature rejection
3. Missing signature rejection
4. Idempotency on duplicate delivery
5. Malformed payload handling
6. Empty payload handling
"""

import json
import pytest
from config import settings


def test_valid_webhook_signature(client, sample_payment_failed_payload, make_signature, monkeypatch, webhook_secret):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", webhook_secret)
    raw_body = json.dumps(sample_payment_failed_payload).encode("utf-8")
    sig = make_signature(raw_body)

    response = client.post(
        "/api/v1/webhooks/razorpay",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": sig,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["event_type"] == "payment.failed"
    assert data["case_number"] is not None


def test_invalid_webhook_signature(client, sample_payment_failed_payload, monkeypatch, webhook_secret):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", webhook_secret)
    raw_body = json.dumps(sample_payment_failed_payload).encode("utf-8")

    response = client.post(
        "/api/v1/webhooks/razorpay",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": "invalid_signature_hex_digest_here",
        },
    )

    assert response.status_code == 400
    assert "Invalid webhook signature" in response.json()["detail"]


def test_missing_webhook_signature(client, sample_payment_failed_payload, monkeypatch, webhook_secret):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", webhook_secret)
    raw_body = json.dumps(sample_payment_failed_payload).encode("utf-8")

    response = client.post(
        "/api/v1/webhooks/razorpay",
        content=raw_body,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400


def test_duplicate_webhook_idempotency(client, sample_payment_failed_payload, make_signature, monkeypatch, webhook_secret):
    """
    CRITICAL: Delivering the same webhook twice must NOT create duplicate events or cases.
    """
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", webhook_secret)
    raw_body = json.dumps(sample_payment_failed_payload).encode("utf-8")
    sig = make_signature(raw_body)

    # First delivery
    res1 = client.post(
        "/api/v1/webhooks/razorpay",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
    )
    assert res1.status_code == 200
    case_number1 = res1.json().get("case_number")

    # Second delivery (identical event_id)
    res2 = client.post(
        "/api/v1/webhooks/razorpay",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
    )
    assert res2.status_code == 200
    case_number2 = res2.json().get("case_number")

    assert case_number1 == case_number2

    # Verify total events in DB is only 1
    events_res = client.get("/api/v1/events")
    assert events_res.status_code == 200
    assert events_res.json()["total"] == 1

    # Verify total recovery cases in DB is only 1
    cases_res = client.get("/api/v1/recovery-cases")
    assert cases_res.status_code == 200
    assert cases_res.json()["total"] == 1


def test_malformed_json_webhook(client, monkeypatch, webhook_secret):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", "")
    response = client.post(
        "/api/v1/webhooks/razorpay",
        content=b"not a valid json payload",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert "Malformed JSON" in response.json()["detail"]

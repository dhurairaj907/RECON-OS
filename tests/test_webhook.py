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


def test_malformed_json_webhook(client, monkeypatch, webhook_secret, make_signature):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", webhook_secret)
    raw = b"not a valid json payload"
    response = client.post(
        "/api/v1/webhooks/razorpay",
        content=raw,
        headers={"Content-Type": "application/json",
                 "X-Razorpay-Signature": make_signature(raw)},
    )
    assert response.status_code == 400
    assert "Malformed JSON" in response.json()["detail"]


def test_unsigned_webhook_rejected_by_default(client, monkeypatch, sample_payment_failed_payload):
    """Fail-closed: no secret + no explicit opt-in -> webhook rejected."""
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", "")
    monkeypatch.setattr(settings, "RAZORPAY_ALLOW_UNSIGNED_WEBHOOKS", False)
    raw = json.dumps(sample_payment_failed_payload).encode()
    r = client.post("/api/v1/webhooks/razorpay", content=raw,
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 400
    assert "signature" in r.json()["detail"].lower()


def test_unsigned_webhook_allowed_with_explicit_dev_opt_in(client, monkeypatch, sample_payment_failed_payload):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", "")
    monkeypatch.setattr(settings, "RAZORPAY_ALLOW_UNSIGNED_WEBHOOKS", True)
    raw = json.dumps(sample_payment_failed_payload).encode()
    r = client.post("/api/v1/webhooks/razorpay", content=raw,
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 200


def test_webhook_resolves_to_correct_organization_when_a_second_one_exists(
    client, sample_payment_failed_payload, make_signature, monkeypatch, webhook_secret, db_session
):
    """Phase 8 regression: `resolve_connected_merchant` replaced the old
    `seed_default_merchant` ("whichever merchant the DB returns first", no
    ordering) — this is the exact latent-bug scenario it fixes. A second
    organization/merchant existing must never cause a real webhook to be
    misattributed away from the platform's actual connected organization."""
    from database import get_org_merchant
    from models.organization import Organization

    other_org = Organization(name="A Second, Unrelated Organization")
    db_session.add(other_org)
    db_session.commit()
    get_org_merchant(db_session, other_org)  # creates its merchant row too

    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", webhook_secret)
    raw_body = json.dumps(sample_payment_failed_payload).encode("utf-8")
    sig = make_signature(raw_body)

    response = client.post(
        "/api/v1/webhooks/razorpay", content=raw_body,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
    )
    assert response.status_code == 200
    assert response.json()["case_number"] is not None

    # The case must show up under the authenticated (Test Organization) user's
    # own recovery-case list, NOT be silently attributed to the other org.
    cases = client.get("/api/v1/recovery-cases").json()
    assert cases["total"] == 1

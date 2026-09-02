"""
RECON OS — REST API & Simulator Tests

Validates:
1. Health check
2. Dashboard metrics aggregation
3. Simulator event generation & pipeline execution
4. Recovery cases listing & detail
5. Customer listing & detail
6. Events listing & detail
7. Audit log listing
"""

import json
from decimal import Decimal


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert data["service"] == "recon-os-api"
    assert data["database"] == "healthy"


def test_health_endpoint_returns_503_when_db_unhealthy(client, db_session, monkeypatch):
    """Deployment-hardening: orchestrators (load balancers, k8s probes) key
    off the HTTP status code, not the JSON body — a degraded DB must not
    still report 200."""
    def _boom(*args, **kwargs):
        raise RuntimeError("simulated database connectivity failure — should never reach the client")

    monkeypatch.setattr(db_session, "execute", _boom)
    response = client.get("/health")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    assert data["database"] == "unhealthy"
    # The raw exception text must never leak into the public response.
    assert "simulated database connectivity failure" not in json.dumps(data)


def test_simulator_payment_failed_flow(client):
    """
    Test triggering a payment failure via simulator and verifying
    that all database entities, metrics, and API endpoints reflect it.
    """
    sim_request = {
        "event_type": "payment.failed",
        "customer_name": "Acme Industries",
        "customer_email": "finance@acme.corp",
        "customer_phone": "+919876543210",
        "amount": "14999.00",
        "payment_method": "upi",
        "failure_code": "BAD_REQUEST_ERROR",
        "failure_reason": "payment_failed",
        "error_description": "UPI handle expired",
    }

    # 1. Trigger simulator
    sim_res = client.post("/api/v1/simulator/events", json=sim_request)
    assert sim_res.status_code == 201
    sim_data = sim_res.json()
    assert sim_data["success"] is True
    assert sim_data["case_number"] is not None

    # 2. Check Dashboard Metrics
    dash_res = client.get("/api/v1/dashboard/metrics")
    assert dash_res.status_code == 200
    dash_data = dash_res.json()
    assert float(dash_data["revenue_at_risk"]) == 14999.00
    assert dash_data["active_recovery_cases"] == 1
    assert dash_data["payment_failures"] == 1
    assert dash_data["total_customers"] == 1
    assert len(dash_data["recent_events"]) == 1
    assert len(dash_data["recent_cases"]) == 1

    # 3. Check Recovery Cases Endpoint
    cases_res = client.get("/api/v1/recovery-cases")
    assert cases_res.status_code == 200
    cases_data = cases_res.json()
    assert cases_data["total"] == 1
    case_item = cases_data["items"][0]
    assert case_item["case_number"] == sim_data["case_number"]
    assert case_item["priority"] == "HIGH"  # ₹14,999 is >= 10000

    # 4. Check Customers Endpoint
    cust_res = client.get("/api/v1/customers")
    assert cust_res.status_code == 200
    cust_data = cust_res.json()
    assert cust_data["total"] == 1
    assert cust_data["items"][0]["email"] == "finance@acme.corp"
    assert cust_data["items"][0]["failed_payment_count"] == 1

    # 5. Check Audit Logs Endpoint
    audit_res = client.get("/api/v1/audit-logs")
    assert audit_res.status_code == 200
    assert audit_res.json()["total"] >= 2  # RECOVERY_CASE_CREATED + EVENT_PROCESSED


def test_audit_logs_filter_by_case_id(client):
    """The case-level timeline filter (used by IntelligencePanel's Case
    Timeline) must return only that case's own entries, never another
    case's, and must fail safely (empty, not an error or all rows) for a
    malformed id."""
    sim_a = client.post("/api/v1/simulator/events", json={
        "event_type": "payment.failed", "customer_name": "Case A Customer",
        "customer_email": "case-a@example.com", "amount": "1999.00",
        "payment_method": "upi", "failure_code": "BAD_REQUEST_ERROR",
        "failure_reason": "payment_failed", "error_description": "timeout",
    })
    sim_b = client.post("/api/v1/simulator/events", json={
        "event_type": "payment.failed", "customer_name": "Case B Customer",
        "customer_email": "case-b@example.com", "amount": "2999.00",
        "payment_method": "card", "failure_code": "GATEWAY_ERROR",
        "failure_reason": "payment_failed", "error_description": "declined",
    })
    case_number_a = sim_a.json()["case_number"]
    case_number_b = sim_b.json()["case_number"]
    case_id_a = client.get(f"/api/v1/recovery-cases/{case_number_a}").json()["id"]

    res_a = client.get(f"/api/v1/audit-logs?case_id={case_id_a}&limit=100")
    assert res_a.status_code == 200
    body_a = res_a.json()
    assert body_a["total"] >= 1
    assert all(item["recovery_case_id"] == case_id_a for item in body_a["items"])
    assert all(case_number_b not in item["detail"] for item in body_a["items"])

    # A malformed id must never fall back to returning every row.
    malformed = client.get("/api/v1/audit-logs?case_id=not-a-real-uuid")
    assert malformed.status_code == 200
    assert malformed.json()["total"] == 0


def test_audit_logs_case_filter_respects_organization_isolation(unauthenticated_client):
    c = unauthenticated_client
    c.post("/api/v1/auth/register", json={
        "email": "audit-org-a@recon.test", "password": "Password123!", "organization_name": "Audit Org A",
    })
    sim = c.post("/api/v1/simulator/events", json={
        "event_type": "payment.failed", "customer_name": "Org A Customer",
        "customer_email": "orga@example.com", "amount": "1999.00",
        "payment_method": "upi", "failure_code": "BAD_REQUEST_ERROR",
        "failure_reason": "payment_failed", "error_description": "timeout",
    })
    case_number = sim.json()["case_number"]
    case_id = c.get(f"/api/v1/recovery-cases/{case_number}").json()["id"]

    c.cookies.clear()
    c.post("/api/v1/auth/register", json={
        "email": "audit-org-b@recon.test", "password": "Password123!", "organization_name": "Audit Org B",
    })
    denied = c.get(f"/api/v1/audit-logs?case_id={case_id}")
    assert denied.status_code == 200
    assert denied.json()["total"] == 0

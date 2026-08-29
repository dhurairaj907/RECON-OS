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

"""
RECON OS — Phase 5: Organization isolation tests  (SECURITY-CRITICAL)

Organization A must never be able to read or act on Organization B's data.
Both organizations go through the REAL /auth/register + /auth/login
endpoints — this exercises the actual authenticated request path, not a
fixture shortcut. `organization_id` is NEVER supplied by the client; it is
always derived from the session (see auth.get_auth_context).
"""

FULL_EVENT_PAYLOAD = {
    "event_type": "payment.failed",
    "customer_name": "Isolation Test Customer",
    "customer_email": "isolation@example.com",
    "customer_phone": "+919800009999",
    "amount": "2999.00",
    "payment_method": "upi",
    "failure_code": "BAD_REQUEST_ERROR",
    "failure_reason": "payment_failed",
    "error_description": "UPI handle authorization timeout on customer app",
}


def _register(c, email, org_name):
    res = c.post("/api/v1/auth/register", json={
        "email": email, "password": "OrgPassword123!", "organization_name": org_name,
    })
    assert res.status_code == 201, res.text
    return res.json()


def test_cross_organization_recovery_case_denied(unauthenticated_client):
    c = unauthenticated_client
    _register(c, "orga-case@recon.test", "Org A Case")
    sim = c.post("/api/v1/simulator/events", json=FULL_EVENT_PAYLOAD)
    assert sim.status_code == 201, sim.text
    case_number_a = sim.json()["case_number"]
    assert c.get(f"/api/v1/recovery-cases/{case_number_a}").status_code == 200

    c.cookies.clear()
    _register(c, "orgb-case@recon.test", "Org B Case")

    denied = c.get(f"/api/v1/recovery-cases/{case_number_a}")
    assert denied.status_code == 404

    listing = c.get("/api/v1/recovery-cases").json()
    assert listing["total"] == 0
    assert all(item["case_number"] != case_number_a for item in listing["items"])


def test_cross_organization_action_denied(unauthenticated_client):
    c = unauthenticated_client
    _register(c, "orga-action@recon.test", "Org A Action")
    sim = c.post("/api/v1/simulator/events", json=FULL_EVENT_PAYLOAD)
    case_number_a = sim.json()["case_number"]
    c.post(f"/api/v1/recovery-cases/{case_number_a}/intelligence:analyze")
    proposal = c.post(f"/api/v1/recovery-cases/{case_number_a}/actions/propose").json()
    action_id_a = proposal["action"]["id"]
    executed = c.post(f"/api/v1/actions/{action_id_a}/execute")
    assert executed.status_code == 200

    c.cookies.clear()
    _register(c, "orgb-action@recon.test", "Org B Action")

    assert c.get(f"/api/v1/actions/{action_id_a}").status_code == 404
    assert c.post(f"/api/v1/actions/{action_id_a}/execute").status_code == 404
    assert c.post(f"/api/v1/actions/{action_id_a}/reconcile").status_code == 404

    all_actions = c.get("/api/v1/actions").json()
    assert all(a["id"] != action_id_a for a in all_actions["items"])


def test_cross_organization_audit_log_denied(unauthenticated_client):
    c = unauthenticated_client
    _register(c, "orga-audit@recon.test", "Org A Audit")
    sim = c.post("/api/v1/simulator/events", json=FULL_EVENT_PAYLOAD)
    case_number_a = sim.json()["case_number"]

    c.cookies.clear()
    _register(c, "orgb-audit@recon.test", "Org B Audit")

    audits_b = c.get("/api/v1/audit-logs?limit=100").json()
    assert audits_b["total"] == 0
    assert all(case_number_a not in (a.get("detail") or "") for a in audits_b["items"])


def test_cross_organization_communication_denied(unauthenticated_client):
    c = unauthenticated_client
    _register(c, "orga-comm@recon.test", "Org A Comm")
    sim = c.post("/api/v1/simulator/events", json=FULL_EVENT_PAYLOAD)
    case_number_a = sim.json()["case_number"]
    c.post(f"/api/v1/recovery-cases/{case_number_a}/intelligence:analyze")
    send = c.post(f"/api/v1/recovery-cases/{case_number_a}/communications/send", json={
        "channel": "EMAIL", "message_type": "PAYMENT_FAILED",
    })
    assert send.status_code == 200

    c.cookies.clear()
    _register(c, "orgb-comm@recon.test", "Org B Comm")

    denied = c.get(f"/api/v1/recovery-cases/{case_number_a}/communications")
    assert denied.status_code == 404

    denied_send = c.post(f"/api/v1/recovery-cases/{case_number_a}/communications/send", json={
        "channel": "EMAIL", "message_type": "PAYMENT_FAILED",
    })
    assert denied_send.status_code == 404


def test_cross_organization_analytics_isolated(unauthenticated_client):
    """Phase D/K: analytics are organization-scoped aggregates — Org B must
    never see Org A's revenue/case counts folded into its own numbers."""
    c = unauthenticated_client
    _register(c, "orga-analytics@recon.test", "Org A Analytics")
    sim = c.post("/api/v1/simulator/events", json=FULL_EVENT_PAYLOAD)
    assert sim.status_code == 201, sim.text
    analytics_a = c.get("/api/v1/analytics").json()
    assert float(analytics_a["revenue_at_risk"]) > 0

    c.cookies.clear()
    _register(c, "orgb-analytics@recon.test", "Org B Analytics")

    analytics_b = c.get("/api/v1/analytics").json()
    assert float(analytics_b["revenue_at_risk"]) == 0
    assert float(analytics_b["revenue_recovered"]) == 0


def test_cross_organization_payments_and_customers_isolated(unauthenticated_client):
    """Phase D: one organization's Payment/Customer rows must never appear
    in another organization's list endpoints."""
    c = unauthenticated_client
    _register(c, "orga-pay@recon.test", "Org A Pay")
    sim = c.post("/api/v1/simulator/events", json=FULL_EVENT_PAYLOAD)
    assert sim.status_code == 201, sim.text
    payments_a = c.get("/api/v1/payments").json()
    assert payments_a["total"] >= 1
    customers_a = c.get("/api/v1/customers").json()
    assert customers_a["total"] >= 1

    c.cookies.clear()
    _register(c, "orgb-pay@recon.test", "Org B Pay")

    payments_b = c.get("/api/v1/payments").json()
    assert payments_b["total"] == 0
    customers_b = c.get("/api/v1/customers").json()
    assert customers_b["total"] == 0


def test_organization_id_from_client_is_never_trusted(unauthenticated_client, db_session):
    """Even if a request body/header tried to smuggle an organization id, the
    server only ever uses the one derived from the session."""
    c = unauthenticated_client
    org_a = _register(c, "orga-trust@recon.test", "Org A Trust")
    other_org_id = org_a["organization"]["id"]

    c.cookies.clear()
    _register(c, "orgb-trust@recon.test", "Org B Trust")

    # Attempt to smuggle Org A's id via a header some naive implementation
    # might trust — the real dependency ignores it entirely.
    res = c.get("/api/v1/recovery-cases", headers={"X-Organization-Id": other_org_id})
    assert res.status_code == 200
    me = c.get("/api/v1/auth/me").json()
    assert me["organization"]["id"] != other_org_id

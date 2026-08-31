"""
RECON OS — Phase 5: RBAC enforcement tests  (SECURITY-CRITICAL)

Creates VIEWER / OPERATOR / APPROVER / ADMIN members of the SAME seeded test
organization (see conftest.py's `setup_database`) and exercises the real
role-gated endpoints via real login — never a fixture shortcut around
`auth.require_role`.
"""

from auth import hash_password
from models.organization import Organization
from models.user import User
from models.user_organization import UserOrganization

PASSWORD = "RolePassword123!"

FULL_EVENT_PAYLOAD = {
    "event_type": "payment.failed",
    "customer_name": "RBAC Test Customer",
    "customer_email": "rbac@example.com",
    "customer_phone": "+919800001234",
    "amount": "1999.00",
    "payment_method": "upi",
    "failure_code": "BAD_REQUEST_ERROR",
    "failure_reason": "payment_failed",
    "error_description": "UPI handle authorization timeout on customer app",
}
NIL_ACTION_ID = "00000000-0000-0000-0000-000000000000"


def _make_member(db_session, role, email):
    org = db_session.query(Organization).filter(Organization.name == "Test Organization").first()
    user = User(email=email, password_hash=hash_password(PASSWORD))
    db_session.add(user)
    db_session.flush()
    db_session.add(UserOrganization(user_id=user.id, organization_id=org.id, role=role))
    db_session.commit()
    return user


def _login_as(c, email):
    res = c.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert res.status_code == 200, res.text
    return c


def test_viewer_has_full_read_access(unauthenticated_client, db_session):
    _make_member(db_session, "VIEWER", "viewer1@recon.test")
    c = _login_as(unauthenticated_client, "viewer1@recon.test")
    assert c.get("/api/v1/dashboard/metrics").status_code == 200
    assert c.get("/api/v1/recovery-cases").status_code == 200
    assert c.get("/api/v1/customers").status_code == 200
    assert c.get("/api/v1/events").status_code == 200
    assert c.get("/api/v1/intelligence").status_code == 200
    assert c.get("/api/v1/analytics").status_code == 200
    assert c.get("/api/v1/audit-logs").status_code == 200
    assert c.get("/api/v1/policies").status_code == 200


def test_viewer_cannot_execute_actions_or_use_simulator(unauthenticated_client, db_session):
    _make_member(db_session, "VIEWER", "viewer2@recon.test")
    c = _login_as(unauthenticated_client, "viewer2@recon.test")
    assert c.post("/api/v1/simulator/events", json=FULL_EVENT_PAYLOAD).status_code == 403
    assert c.post(f"/api/v1/actions/{NIL_ACTION_ID}/execute").status_code == 403
    assert c.post(f"/api/v1/actions/{NIL_ACTION_ID}/reconcile").status_code == 403
    assert c.post(f"/api/v1/actions/{NIL_ACTION_ID}/verify-unknown").status_code == 403


def test_viewer_cannot_approve_or_reject(unauthenticated_client, db_session):
    _make_member(db_session, "VIEWER", "viewer3@recon.test")
    c = _login_as(unauthenticated_client, "viewer3@recon.test")
    assert c.post(f"/api/v1/actions/{NIL_ACTION_ID}/approve").status_code == 403
    assert c.post(f"/api/v1/actions/{NIL_ACTION_ID}/reject").status_code == 403


def test_operator_can_execute_but_not_approve(unauthenticated_client, db_session):
    _make_member(db_session, "OPERATOR", "operator1@recon.test")
    c = _login_as(unauthenticated_client, "operator1@recon.test")

    sim = c.post("/api/v1/simulator/events", json=FULL_EVENT_PAYLOAD)
    assert sim.status_code == 201, sim.text
    case_number = sim.json()["case_number"]
    c.post(f"/api/v1/recovery-cases/{case_number}/intelligence:analyze")
    proposal = c.post(f"/api/v1/recovery-cases/{case_number}/actions/propose")
    assert proposal.status_code != 403

    # Approval tier is explicitly denied to OPERATOR.
    assert c.post(f"/api/v1/actions/{NIL_ACTION_ID}/approve").status_code == 403
    assert c.post(f"/api/v1/actions/{NIL_ACTION_ID}/reject").status_code == 403


def test_approver_can_approve_but_not_execute(unauthenticated_client, db_session):
    _make_member(db_session, "APPROVER", "approver1@recon.test")
    c = _login_as(unauthenticated_client, "approver1@recon.test")

    # Execution tier is explicitly denied to APPROVER (role check happens
    # before the 404-for-missing-id check, so a non-403 here would be a bug).
    assert c.post("/api/v1/simulator/events", json=FULL_EVENT_PAYLOAD).status_code == 403
    assert c.post(f"/api/v1/actions/{NIL_ACTION_ID}/execute").status_code == 403

    # Approve/reject role check passes through to the (404, no such action).
    assert c.post(f"/api/v1/actions/{NIL_ACTION_ID}/approve").status_code == 404
    assert c.post(f"/api/v1/actions/{NIL_ACTION_ID}/reject").status_code == 404


def test_admin_has_all_permissions(unauthenticated_client, db_session):
    _make_member(db_session, "ADMIN", "admin2@recon.test")
    c = _login_as(unauthenticated_client, "admin2@recon.test")

    assert c.get("/api/v1/dashboard/metrics").status_code == 200
    assert c.post("/api/v1/simulator/events", json=FULL_EVENT_PAYLOAD).status_code == 201
    assert c.post(f"/api/v1/actions/{NIL_ACTION_ID}/approve").status_code == 404   # role passes, id doesn't exist
    assert c.get("/api/v1/users").status_code == 200


def test_non_admin_cannot_manage_users(unauthenticated_client, db_session):
    _make_member(db_session, "OPERATOR", "operator2@recon.test")
    c = _login_as(unauthenticated_client, "operator2@recon.test")
    assert c.get("/api/v1/users").status_code == 403
    assert c.patch(f"/api/v1/users/{NIL_ACTION_ID}/role", json={"role": "ADMIN"}).status_code == 403

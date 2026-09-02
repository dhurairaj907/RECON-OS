"""
RECON OS — Evaluation harness safety regression.

The evaluation harness (apps/api/evaluation/) is meant to be a completely
safe demo/CI lane — it must never be able to reach a real external provider,
regardless of whatever RECON_COMMUNICATIONS_MODE happens to be set to in the
ambient environment (which, when run with CWD=apps/api, is the REAL .env —
including real Brevo credentials if configured). This guards against a real
incident: an earlier version of the harness let RECON_COMMUNICATIONS_MODE
leak through from the real .env, causing scenario_26 (Recovery
communication) to instantiate the real SmtpEmailProvider and attempt a live
SMTP send during what was supposed to be an isolated, safe evaluation run.
"""

from config import settings
from evaluation.harness import isolated_db
from services.communications.providers import get_communication_provider


def test_isolated_db_forces_fake_communications_mode(monkeypatch):
    monkeypatch.setattr(settings, "RECON_COMMUNICATIONS_MODE", "real")
    with isolated_db() as (db, merchant):
        assert settings.RECON_COMMUNICATIONS_MODE == "fake"
        assert get_communication_provider("EMAIL").name == "FAKE_EMAIL"
    # Restored afterward — never leaks a changed setting into the next scenario/test.
    assert settings.RECON_COMMUNICATIONS_MODE == "real"


def test_isolated_db_restores_mode_even_if_scenario_raises(monkeypatch):
    monkeypatch.setattr(settings, "RECON_COMMUNICATIONS_MODE", "real")
    try:
        with isolated_db() as (db, merchant):
            assert settings.RECON_COMMUNICATIONS_MODE == "fake"
            raise RuntimeError("simulated scenario failure")
    except RuntimeError:
        pass
    assert settings.RECON_COMMUNICATIONS_MODE == "real"


def test_evaluation_scenario_26_never_uses_real_provider(monkeypatch):
    """End-to-end: the actual communication scenario must record the FAKE
    provider even when the ambient config says 'real' — reproduces the
    exact original incident conditions."""
    monkeypatch.setattr(settings, "RECON_COMMUNICATIONS_MODE", "real")
    from evaluation.scenarios import scenario_26, _Recorder

    r = _Recorder(26, "Recovery communication", ["communication"])
    scenario_26(r)
    assert r.result.passed, r.result.checks
    provider_check = next(c for c in r.result.checks if c[0] == "provider_recorded")
    assert provider_check[1] is True


def test_isolated_db_forces_automation_flags_off(monkeypatch):
    """Phase 8, same incident class as the SMTP leak above: this deployment's
    real .env now has AUTOMATIC_ACTION_EXECUTION_ENABLED and
    AUTOMATIC_COMMUNICATIONS_ENABLED both True (the fully-automatic chain is
    the default posture). Most scenarios construct a case and then
    deliberately drive propose/execute/approve/reject themselves to assert
    specific intermediate states — an ambient auto-execute during
    run_intelligence() would race ahead of that. Both flags must be forced
    off for the duration of every scenario and restored afterward."""
    monkeypatch.setattr(settings, "AUTOMATIC_ACTION_EXECUTION_ENABLED", True)
    monkeypatch.setattr(settings, "AUTOMATIC_COMMUNICATIONS_ENABLED", True)
    with isolated_db() as (db, merchant):
        assert settings.AUTOMATIC_ACTION_EXECUTION_ENABLED is False
        assert settings.AUTOMATIC_COMMUNICATIONS_ENABLED is False
    # Restored afterward — never leaks a changed setting into the next scenario/test.
    assert settings.AUTOMATIC_ACTION_EXECUTION_ENABLED is True
    assert settings.AUTOMATIC_COMMUNICATIONS_ENABLED is True


def test_all_scenarios_pass_with_real_deployment_automation_flags_on(monkeypatch):
    """Reproduces the exact incident conditions: runs the FULL scenario suite
    with both automation flags forced True in the ambient config (as they
    now are in this deployment's real .env), proving `isolated_db`'s
    per-scenario override is what actually protects every scenario, not an
    accident of the ambient default happening to be off."""
    monkeypatch.setattr(settings, "AUTOMATIC_ACTION_EXECUTION_ENABLED", True)
    monkeypatch.setattr(settings, "AUTOMATIC_COMMUNICATIONS_ENABLED", True)
    from evaluation.scenarios import run_all

    results = run_all()
    failed = [r for r in results if not r.passed]
    assert not failed, [(r.scenario_id, r.name, r.checks) for r in failed]

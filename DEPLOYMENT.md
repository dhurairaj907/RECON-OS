# RECON OS — Deployment Guide

This document covers the operational steps to deploy RECON OS, and — most
importantly — the deliberate checklist required before ever switching
Razorpay from TEST mode to LIVE (real money) mode. **RECON OS ships and
runs in Razorpay TEST mode today. Nothing in this document enables LIVE
mode. That switch is a separate, explicit, human-reviewed decision.**

---

## 1. Standard deployment (TEST mode, demo/staging)

1. `cp .env.example .env` and fill in TEST-mode Razorpay credentials
   (`rzp_test_...`), a real `RECON_API_KEY`, and a real `SESSION_COOKIE_NAME`
   secret is not needed (it's a name, not a secret) but do set:
   - `SESSION_COOKIE_SECURE=true` — **required** once served over HTTPS
     (see §2).
   - `CORS_ORIGINS=["https://your-deployed-frontend.example.com"]` — the
     real frontend origin, not the `localhost:3000` default (see §3).
2. Build with the real frontend API origin baked in (Next.js inlines
   `NEXT_PUBLIC_*` at build time, not runtime):
   ```bash
   NEXT_PUBLIC_API_URL=https://your-deployed-api.example.com docker-compose build web
   docker-compose build api
   docker-compose up
   ```
3. Confirm `/health` (or `/api/v1/health`) returns `200` with
   `"database": "healthy"` before considering the deployment live. It
   returns `503` if the database is unreachable — treat that as a hard
   deployment failure, not a soft warning.
4. Register the Razorpay TEST-mode webhook (Dashboard → Settings →
   Webhooks) pointing at `https://<your-domain>/api/v1/webhooks/razorpay`,
   and set the resulting secret as `RAZORPAY_WEBHOOK_SECRET`.

## 2. HTTPS and session cookies

`SESSION_COOKIE_SECURE=false` is the correct **local HTTP development**
default — browsers refuse to send a `Secure` cookie back over plain HTTP, so
`true` would silently break login on `localhost`. Any deployment reachable
over the public internet **must**:
- Terminate HTTPS (at a load balancer, reverse proxy, or the app itself).
- Set `SESSION_COOKIE_SECURE=true`.

Never deploy a public-facing instance with this left at `false` — the
session cookie would be sent in plaintext.

## 3. CORS

`CORS_ORIGINS` defaults to `["http://localhost:3000"]`. Set it to your real
deployed frontend origin(s) as a JSON array before deploying — the browser
enforces CORS client-side, so leaving the default in place doesn't expose
anything, it just means the real frontend's requests get silently rejected.
Never set a wildcard `"*"` origin — it's incompatible with the credentialed
session cookie (`allow_credentials=True`) regardless, and is rejected by
browsers when combined with credentials.

## 4. Reproducible backend dependencies

`apps/api/Dockerfile` installs from `apps/api/requirements-lock.txt` (exact,
version-pinned, verified against the full test suite) rather than
`requirements.txt` (loose `>=` ranges used for day-to-day development). See
that file's header for how to regenerate it after a deliberate dependency
change — always re-run the full test suite before regenerating.

## 5. CI

`.github/workflows/ci.yml` runs the backend test suite, frontend
typecheck/lint/build on every pull request and push to `main`. It does
**not** deploy anything — there is no deployment job. Passing CI is a
prerequisite for considering a change deployable, not a guarantee of
production readiness by itself.

---

## 6. The Razorpay TEST → LIVE cutover

**This is the one step in this entire document that involves real money.**
Everything above is safe to automate; this is not, and must never be done
casually, by a script, or as a side effect of another change.

### What TEST mode enforces today

RECON OS's Action Engine (`apps/api/integrations/razorpay/adapter.py`,
`apps/api/services/actions/executor.py`) refuses to execute any payment
action unless **all** of the following hold:
- `RAZORPAY_TEST_MODE=true`
- `RAZORPAY_KEY_ID` starts with `rzp_test_`

Either check failing returns a structured `RAZORPAY_TEST_MODE_DISABLED` /
`RAZORPAY_NOT_TEST_KEY` error — no live call is ever attempted. This is a
deliberate, structural safety property, not a default that happens to be
off.

### What flipping to LIVE actually requires

Going live means changing, together, in a reviewed deployment:

| Setting | TEST (today) | LIVE |
|---|---|---|
| `RAZORPAY_TEST_MODE` | `true` | `false` |
| `RAZORPAY_KEY_ID` | `rzp_test_...` | `rzp_live_...` |
| `RAZORPAY_KEY_SECRET` | test secret | live secret |
| `RAZORPAY_WEBHOOK_SECRET` | test webhook secret | live webhook secret (a **separate** value — Razorpay issues distinct webhook secrets per mode) |
| Transport | may be HTTP (local) | HTTPS only |
| `CORS_ORIGINS` | localhost default OK | real production origin, reviewed |
| `SESSION_COOKIE_SECURE` | `false` OK locally | `true`, required |

**No code change is required to go live** — this is entirely a
configuration change. That is precisely why it must be gated by process, not
by code: there is no compiler error, no failing test, and no code review
diff to catch a mistake here. The checklist below is the only safeguard.

### The live-cutover checklist

Do not set `RAZORPAY_TEST_MODE=false` in any real deployment until every
item below has been explicitly completed and signed off by a human:

1. **Database backup** — a verified, restorable backup taken immediately
   before the cutover. (RECON OS does not currently automate this — see the
   deployment-readiness audit's P2 list. Take one manually if no automation
   exists yet.)
2. **Deployment verification** — the target environment has been running
   in TEST mode successfully for a meaningful period, with `/health`
   green and no unexplained errors in logs.
3. **Webhook verification** — the LIVE-mode webhook is registered in the
   Razorpay dashboard against the LIVE endpoint, using the LIVE webhook
   secret (not the TEST one), and a real signature-verified test event has
   been observed end-to-end.
4. **Authentication verification** — `SESSION_COOKIE_SECURE=true`, HTTPS
   confirmed end-to-end (no mixed content, no HTTP fallback), and
   `RECON_API_KEY` is set to a real, non-empty secret (financial-action
   endpoints are open by default otherwise — see `security.py`).
5. **CORS verification** — `CORS_ORIGINS` contains only the real production
   frontend origin(s), nothing left over from testing.
6. **Policy / Action safety verification** — `POLICY_AUTO_APPROVAL_AMOUNT_LIMIT`
   and the other `POLICY_*` constants have been reviewed for the real
   amounts this deployment will handle; `AUTOMATIC_ACTION_EXECUTION_ENABLED`
   and `AUTOMATIC_COMMUNICATIONS_ENABLED` have been deliberately reviewed
   (on or off), not left at whatever they happened to be during testing.
7. **Payment verification testing** — at least one real, small-value LIVE
   transaction has been manually executed and reconciled end-to-end
   (capture → webhook → recovery/reconciliation) before relying on the
   system for real customer traffic. **This has not been done as part of
   this hardening pass or any prior phase** — the LIVE path is
   structurally safe (refuses to run without live-mode config) but has
   never actually been exercised. Do not assume it works from the TEST-mode
   test suite alone.
8. **Rollback plan** — a documented, tested way to set
   `RAZORPAY_TEST_MODE=true` (or otherwise stop the deployment) quickly if
   something goes wrong after cutover, and to restore the database backup
   from step 1 if needed.
9. **Monitoring** — someone is actively watching logs/`/health` immediately
   after cutover, not relying on passive alerting alone (RECON OS does not
   currently ship metrics/alerting — see the audit's P2 list).
10. **Explicit human approval** — a named person has reviewed items 1-9 and
    explicitly approved activating LIVE mode, on the record. Never flip
    `RAZORPAY_TEST_MODE=false` as an incidental part of an unrelated
    deployment or config change.

If any item above is not yet true, **stay in TEST mode.**

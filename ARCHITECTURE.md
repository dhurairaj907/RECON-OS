# RECON OS — Architecture

One real, end-to-end flow. No step here is simulated in production; the Simulator
(`RECON_SIMULATOR_ENABLED`) only substitutes the *first* trigger (a synthetic
Razorpay event) or a payment confirmation — every step after that is the same real
code path a genuine webhook would drive.

## System flow

```
 Payment fails at Razorpay
          |
          v
 Razorpay Webhook  (HMAC-SHA256 verified, fails closed)
          |
          v
 Event Processor  (idempotent — unique razorpay_event_id)
   - normalizes the payload
   - upserts Customer / Payment aggregates
   - creates a RecoveryCase (deterministic priority)
          |
          v
 Intelligence Pipeline  (Phase 2 — THINK; isolated transaction, never fails the webhook)
   Context Builder -> Diagnosis (deterministic, or Gemini-assisted) -> Prediction
   -> Strategy -> Policy Engine (deterministic, zero LLM)
          |
          v
 Policy Verdict
   APPROVED ----------------------------+
   NEEDS_APPROVAL -> Approvals UI ------+---> Action Engine
   REJECTED -> hard stop (never reachable via any path below)
          |
          v
 Action Engine  (execute_action — SAFETY CRITICAL)
   - re-derives case/diagnosis/prediction/strategy from CURRENT state
   - RE-EVALUATES the Policy Engine fresh (never trusts a stored verdict,
     a frontend value, or a human decision made under now-stale conditions)
   - idempotency guard (EXECUTED/EXECUTING short-circuits — no duplicate calls)
          |
          v
 Razorpay Adapter  (the ONLY component that talks to Razorpay; TEST MODE only)
   POST /v1/payment_links
     success        -> EXECUTED / outcome PENDING  (a link exists; nothing recovered yet)
     definitive fail -> FAILED (4xx/5xx/rate-limited — safely retryable, policy-gated)
     TIMEOUT        -> UNKNOWN (ambiguous — see below)
          |
          v
 Verification  (the ONLY path that can mark RECOVERED)
   signature-verified payment_link.paid webhook, OR
   POST /actions/{id}/reconcile -> GET /v1/payment_links/{id}
     RECOVERED only if Razorpay reports status=="paid" in FULL
          |
          v
 Revenue Recovered  (RecoveryCase.status -> RESOLVED, amount_recovered set)
          |
          v
 Audit Trail  (every transition above writes an AuditLog row:
   actor, event, previous/new state, policy result, human decision,
   provider result, verification result, timestamp, rationale — never a secret)
          |
          v
 Analytics  (GET /api/v1/analytics — computed live from the rows above)
```

## The UNKNOWN branch (Phase 4 P0)

A client-side timeout on the Razorpay create call is genuinely ambiguous — the
request may have reached Razorpay despite the timeout. RECON OS never guesses:

```
Action Engine -> Razorpay create times out
   -> outcome = UNKNOWN, status stays EXECUTING
   -> the SAME idempotency guard above refuses any further execute_action call
      (no special-casing needed — EXECUTING already short-circuits)
   -> POST /actions/{id}/verify-unknown
        -> Razorpay Adapter searches Razorpay's own recent Payment Links
           for RECON's deterministic reference_id
        -> FOUND      -> adopt as EXECUTED/PENDING (no duplicate ever created)
        -> CONFIRMED absent -> FAILED (now a verified fact; a retry is safe and
                                        still fully policy-gated)
        -> inconclusive     -> stays UNKNOWN; audited; surfaced to the operator
```

## The human-approval branch (Phase 4 P0)

```
Action Engine -> policy re-evaluates to NEEDS_APPROVAL -> BLOCKED
          |
          v
 Approvals UI -> operator reviews case/customer/payment/amount/diagnosis/
                 probability/strategy/policy-reason/risk/current-state
          |
     Approve -----------------------------+----- Reject
          |                                        |
          v                                        v
 POST /actions/{id}/approve            POST /actions/{id}/reject
   records human_decision=APPROVED       records human_decision=REJECTED
   -> calls the SAME execute_action()    -> status=BLOCKED, blocked_reason=
      used everywhere else                  HUMAN_REJECTED — terminal, never
   -> policy re-evaluated FRESH             executes
        still NEEDS_APPROVAL -> honour the decision, proceed
        now REJECTED         -> clear the decision, block anyway
                                 (a human can never override a hard REJECTED)
```

## Non-negotiable invariants

1. **`LLM -> Razorpay` never exists as a code path.** The LLM (when enabled) only
   produces a `DiagnosisResult`; prediction, strategy eligibility, and the Policy
   Engine are deterministic Python with no model call in the loop.
2. **The Policy Engine is re-evaluated at execution time, every time** — a value
   computed at analysis time, stored on the action, or supplied by the frontend is
   never trusted as the verdict that gates a Razorpay call.
3. **Idempotency is structural, not defensive.** `EXECUTED`/`EXECUTING` status and
   unique `reference_id`/`idempotency_key` make a duplicate Payment Link
   structurally impossible, not just discouraged.
4. **UNKNOWN is a first-class outcome**, never collapsed into `FAILED` or silently
   retried.
5. **A human decision is a vote, not an override.** It only ever unlocks proceeding
   through a policy check that would otherwise block; it can never force a path the
   fresh policy re-evaluation itself would reject.

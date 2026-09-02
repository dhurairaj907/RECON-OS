# RECON OS — Revenue Recovery and Optimization Network

[![Phase](https://img.shields.io/badge/Phase-4%20%28PROVE%29-blue.svg)](https://github.com/recon-os)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.13-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-teal.svg)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14.2%20App%20Router-black.svg)](https://nextjs.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue.svg)](https://www.postgresql.org)

> **"Razorpay moves the money. RECON OS decides how to recover the money that is at risk."**

RECON OS is an autonomous revenue recovery operating system designed for the **Razorpay AI Buildathon**. It operates as an intelligent decision and operational layer over payment infrastructure, transforming passive payment failure notifications into an active recovery loop:

$$\text{OBSERVE} \longrightarrow \text{DETECT} \longrightarrow \text{INVESTIGATE} \longrightarrow \text{PREDICT} \longrightarrow \text{DECIDE} \longrightarrow \text{VALIDATE} \longrightarrow \text{ACT} \longrightarrow \text{VERIFY} \longrightarrow \text{LEARN}$$

---

## 1. Phase 1 Scope (CONNECT)

Phase 1 establishes the rock-solid **Data Plane** foundation:
- ✅ **Inbound Razorpay Webhook Ingestion**: With HMAC-SHA256 signature verification over raw request body.
- ✅ **Idempotency Engine**: Rejection of duplicate deliveries using `UNIQUE` event IDs at the database level.
- ✅ **Event Normalization**: Standardizes diverse Razorpay JSON payloads into unified internal representations.
- ✅ **Deterministic Recovery Cases**: Payment failure events automatically create tracked `RecoveryCase` records with deterministic priorities (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`).
- ✅ **Case Resolution**: Successful payment capture events automatically resolve active recovery cases.
- ✅ **Financial Command Center**: High-density operational dashboard with real-time KPI aggregations, event stream, and customer ledgers.
- ✅ **Event Simulator Laboratory**: Pre-configured test failure scenarios that execute through the real backend pipeline.
- ✅ **Full Immutable Audit Trail**: Detailed record of all ingested events, case creations, and deduplication actions.

> **Note on AI & Autonomy**: In strict accordance with the Master Specification, **Phase 1 does NOT contain AI agents or outbound financial transactions**. The intelligence plane (Diagnosis, Prediction, Strategy, Policy Engine) is introduced in Phase 2, and bounded recovery execution in Phase 3.

---

## 2. Architecture Overview

```
                      +-----------------------------+
                      |   Razorpay Test Mode /      |
                      |   Event Simulator Lab       |
                      +--------------+--------------+
                                     |
                             Webhook / Event
                                     |
                                     v
                      +-----------------------------+
                      |   FastAPI Ingestion Layer   |
                      |   - Signature Verification  |
                      |   - Event Normalization     |
                      |   - Idempotency Guard       |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |   Event Processor Service   |
                      |   - Customer Aggregates     |
                      |   - Payment State Guard     |
                      |   - Recovery Case Engine    |
                      |   - Audit Logger            |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |   PostgreSQL 16 Database    |
                      |   - revenue_events          |
                      |   - recovery_cases          |
                      |   - payments                |
                      |   - customers               |
                      |   - audit_logs              |
                      +--------------+--------------+
                                     |
                               REST APIs (v1)
                                     |
                                     v
                      +-----------------------------+
                      |   RECON OS Command Center   |
                      |   (Next.js 14 Dark Ops UI)  |
                      +-----------------------------+
```

---

## 3. Technology Stack

- **Frontend**: Next.js 14 (App Router), TypeScript, Tailwind CSS, Lucide Icons, SWR polling.
- **Backend**: Python 3.11+, FastAPI, SQLAlchemy 2.0, Pydantic v2.
- **Database**: PostgreSQL 16 (UUID primary keys, JSONB raw payloads, indexes).
- **Testing**: `pytest` with SQLite in-memory fixtures (147 automated tests) plus a
  standalone 25-scenario evaluation harness (`apps/api/evaluation/`).
- **Containerization**: Docker & Docker Compose.

---

## 4. Quickstart with Docker Compose

### Prerequisites
- Docker Engine and Docker Compose installed.

### 1. Configure Environment
```bash
cp .env.example .env
```
For anything beyond local Docker Compose — a real staging/demo deployment,
and especially the Razorpay TEST→LIVE cutover — see **[DEPLOYMENT.md](DEPLOYMENT.md)**.

### 2. Launch All Services
```bash
docker-compose up --build
```

This launches:
- **PostgreSQL Database** on `localhost:5432`
- **FastAPI Backend** on `http://localhost:8000` (API docs at `http://localhost:8000/docs`)
- **Next.js Command Center** on `http://localhost:3000`

**Deploying beyond localhost:** `NEXT_PUBLIC_API_URL` is a Next.js *build-time*
variable — it gets inlined into the frontend's client JS bundle when the
image is built, not read at container start. The default above is correct
for local Docker Compose only. For a real deployment, set it before
building:
```bash
NEXT_PUBLIC_API_URL=https://your-deployed-api.example.com docker-compose build web
docker-compose up
```
The backend image installs from `apps/api/requirements-lock.txt` (exact,
verified versions) rather than `requirements.txt` (loose ranges) — see that
file's header comment for how to regenerate it after an intentional
dependency change.

---

## 5. Local Development Setup (Without Docker)

### Backend API

```bash
# 1. Navigate to API directory
cd apps/api

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set environment variables
export DATABASE_URL="postgresql://recon:recon_secret@localhost:5432/reconos"
export RAZORPAY_WEBHOOK_SECRET="your_webhook_secret"

# 5. Start the backend server
uvicorn main:app --reload --port 8000
```

### Frontend Dashboard

```bash
# 1. Navigate to Web directory
cd apps/web

# 2. Install dependencies
npm install

# 3. Run development server
npm run dev
```

Visit **`http://localhost:3000`** in your browser.

---

## 6. Running Automated Tests

Run the full pytest suite (147 tests, 100% pass rate):

```bash
python -m pytest tests/ -v
```

Test Coverage Highlights:
- **Webhook Security**: Valid signature, invalid signature rejection, missing signature.
- **Idempotency**: Duplicate webhook delivery guarantees zero duplicate cases.
- **Event Processor**: Payment failure recovery case creation, out-of-order webhook protection, case auto-resolution upon payment capture.
- **API Endpoints**: Dashboard metrics aggregation, simulator trigger, pagination, customer ledgers.
- **Phase 4 safety** (`tests/test_phase4_safety.py`): human approval idempotency/
  rejection/staleness/audit, UNKNOWN timeout/no-blind-retry/never-bypasses-policy/
  resolution, plus 3 full end-to-end chains.
- **Security** (`tests/test_security.py`): API key gate, per-IP rate limiting.

Then run the deterministic evaluation harness against the real pipeline (see §10.6):

```bash
cd apps/api && python -m evaluation.runner
```

---

## 7. Razorpay Test Mode & Webhook Integration

### Setting Up Live Webhooks
1. Open your **Razorpay Dashboard** in **Test Mode**.
2. Navigate to **Settings → Webhooks → Add New Webhook**.
3. Expose your local server via a tunnel (e.g. `ngrok http 8000`).
4. Set Webhook URL to: `https://<your-tunnel>.ngrok.app/api/v1/webhooks/razorpay`.
5. Enter a secret key and add it to your `.env` as `RAZORPAY_WEBHOOK_SECRET`.
6. Select events:
   - `payment.failed`
   - `payment.captured`
   - `payment.authorized`
   - `order.paid`

---

## 8. REST API Documentation

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | System health check & database connectivity status |
| `POST` | `/api/v1/webhooks/razorpay` | Inbound Razorpay webhook receiver with HMAC check |
| `GET` | `/api/v1/dashboard/metrics` | Real-time aggregated KPIs for Command Center |
| `GET` | `/api/v1/events` | Paginated revenue event stream with filters |
| `GET` | `/api/v1/events/{id}` | Detailed event view with raw payload |
| `GET` | `/api/v1/recovery-cases` | Paginated recovery cases with status & priority |
| `GET` | `/api/v1/recovery-cases/{id}`| Case detail with customer & payment context |
| `GET` | `/api/v1/customers` | Customer directory with lifetime revenue |
| `GET` | `/api/v1/payments` | Payment ledger with status & error reasons |
| `GET` | `/api/v1/audit-logs` | Immutable system audit records |
| `POST` | `/api/v1/simulator/events` | Trigger synthetic payment events |
| `GET` | `/api/v1/recovery-cases/{id}/intelligence` | Latest Phase 2 intelligence result for a case |
| `POST` | `/api/v1/recovery-cases/{id}/intelligence:analyze` | Run the deterministic intelligence pipeline (safe to repeat) |
| `GET` | `/api/v1/intelligence` | List analysed recovery cases (latest analysis per case) |
| `POST` | `/api/v1/recovery-cases/{id}/actions/propose` | Build/return a policy-gated action proposal (protected*) |
| `POST` | `/api/v1/actions/{id}/execute` | Execute an action — re-validates policy server-side (protected*) |
| `POST` | `/api/v1/actions/{id}/approve` | Human approval — re-validates, then executes (protected*) |
| `POST` | `/api/v1/actions/{id}/reject` | Human rejection — terminal, never executes (protected*) |
| `POST` | `/api/v1/actions/{id}/verify-unknown` | Resolve an UNKNOWN outcome — never a blind retry (protected*) |
| `POST` | `/api/v1/actions/{id}/reconcile` | Ask Razorpay directly whether a Payment Link was paid (protected*) |
| `GET` | `/api/v1/actions` / `/api/v1/actions/{id}` | Action history / single action status |
| `GET` | `/api/v1/analytics` | Real-data revenue recovery + operational analytics |
| `GET` | `/api/v1/policies` | Read-only description of the live Policy Engine + thresholds |

\* protected by `RECON_API_KEY` (open by default for local dev — see §10.3) and a
per-IP rate limit.

Interactive Swagger documentation is available at `http://localhost:8000/docs`.

---

## 9. Phase 2 (THINK) — Intelligence Layer

Phase 2 layers a **deterministic, explainable** intelligence pipeline over the Phase 1
data plane. It runs after the Phase 1 transaction commits, in an isolated transaction —
a Phase 2 failure can never fail a webhook or roll back a recovery case.

```
Recovery Case → Context Builder → Diagnosis → Recovery Prediction
             → Strategy Recommendation → Deterministic Policy Engine
             → CaseIntelligence (persisted) + Audit Trail
```

- **Context Builder** — deterministic `CaseContext` from real DB rows, no side effects.
- **Diagnosis** — controlled failure categories (`AUTH_TIMEOUT`, `INSUFFICIENT_FUNDS`,
  `BANK_DECLINE`, `TECHNICAL_GATEWAY`, `RISK_BLOCK`, `USER_ABANDONED`, `UNKNOWN`) from
  transparent keyword/rule classification.
- **Recovery Prediction** — additive scorecard (`weights.py`); same input → same output.
- **Strategy** — recommends one of `RETRY_NOW`, `RETRY_DELAYED`, `SEND_PAYMENT_LINK`,
  `CUSTOMER_OUTREACH`, `MANUAL_REVIEW`, `NO_ACTION`. Recommends only — never executes.
- **Policy Engine** — authoritative, deterministic, no LLM. Verdicts `APPROVED` /
  `NEEDS_APPROVAL` / `REJECTED`. Constants configurable via `POLICY_*` env vars.

Enable automatic analysis with `INTELLIGENCE_ENABLED=true` (the `intelligence:analyze`
endpoint works regardless).

### Phase 2.5 — optional AI-assisted diagnosis (Gemini)

The **diagnosis step only** can optionally be produced by an LLM (Google Gemini) via
`apps/api/integrations/llm/`. It is strictly bounded:

- Enable with `LLM_ENABLED=true`, `LLM_PROVIDER=gemini`, `GEMINI_API_KEY=...` (server-side
  only — never `NEXT_PUBLIC_*`, never in a response / log / DB row).
- The LLM is asked for **structured JSON** validated against a strict Pydantic schema
  (`AIDiagnosisSchema`). Invalid JSON / bad enum / out-of-range confidence / missing
  fields / timeout / 429 / API error → **automatic deterministic fallback**. The system
  is fully functional and demoable with `LLM_ENABLED=false`.
- **Prediction and the Policy Engine stay 100% deterministic** and are not influenced by
  the LLM or its confidence. The LLM has no field through which to authorise an action.
- `CaseIntelligence` records `provider` (`DETERMINISTIC` | `GEMINI`), `provider_version`,
  and `intelligence_version`. Audit events: `AI_DIAGNOSIS_STARTED` /
  `AI_DIAGNOSIS_COMPLETED` / `AI_DIAGNOSIS_FALLBACK` / `AI_DIAGNOSIS_FAILED`.
- The Intelligence UI shows the real source: **AI-ENHANCED** / **DETERMINISTIC FALLBACK**
  / **DETERMINISTIC**.

### Phase 3 — ACT (policy-gated recovery actions)

Phase 3 adds ONE outbound action — a **Razorpay TEST MODE Payment Link** — behind the
authoritative Policy Engine:

```
Strategy → Policy → ActionProposal → Action Executor → Razorpay Adapter → POST /v1/payment_links
```

- `POST /api/v1/recovery-cases/{id}/actions/propose` turns the deterministic
  strategy/policy result into an `ActionProposal` (idempotent — one action per case).
- `POST /api/v1/actions/{id}/execute` **re-loads the case and RE-EVALUATES the Policy
  Engine server-side** before any Razorpay call. A frontend- or AI-supplied "approved"
  value is never trusted. `NEEDS_APPROVAL` / `REJECTED` → execution BLOCKED.
- **Test Mode only:** `RAZORPAY_TEST_MODE=true` (default) and an `rzp_test_*` key are
  required. Missing credentials return `RAZORPAY_NOT_CONFIGURED` — the app never crashes.
- **Idempotent:** unique `idempotency_key` + `reference_id` (`RECON-RC10001-ACT001`);
  a Payment Link is never created twice.
- **Creating a Payment Link is NOT revenue recovered.** The action stays `EXECUTED /
  outcome PENDING` until Razorpay itself confirms payment, via **one** of:
  1. a **signature-verified** `payment_link.paid` webhook, or
  2. `POST /api/v1/actions/{id}/reconcile` — RECON calls `GET /v1/payment_links/{id}`
     and marks `RECOVERED` **only if Razorpay reports `status == "paid"` in full**.
  Then the case is RESOLVED and `amount_recovered` is set. A short payment →
  `PARTIAL` (case NOT resolved). Duplicate webhooks/reconciles never double-count.
- **Webhooks fail closed:** rejected unless signed against `RAZORPAY_WEBHOOK_SECRET`
  (`RAZORPAY_ALLOW_UNSIGNED_WEBHOOKS=true` opts in for local dev only). `apply_recovery`
  validates action-state, currency match, and full amount before RECOVERED.
- Audit lifecycle: `ACTION_PROPOSED → ACTION_EXECUTION_STARTED → ACTION_POLICY_CHECKED
  → ACTION_APPROVED / ACTION_BLOCKED → PAYMENT_LINK_CREATED → ACTION_EXECUTED →
  RECOVERY_PENDING → (RECONCILE_STARTED/STATUS) → RECOVERY_VERIFIED` (or
  `RECOVERY_PARTIAL` / `RECOVERY_REJECTED` / `RECOVERY_FAILED` / `RECOVERY_ALREADY_VERIFIED`).
- **Simulator is off by default** (`RECON_SIMULATOR_ENABLED=false` → `/api/v1/simulator/*`
  return 403). It is NOT part of the real recovery path. When enabled, every record and
  audit entry it produces is stamped `simulated=true` and its "recovered" amount is
  excluded from real `revenue_recovered` (reported as `simulated_revenue_recovered`).

**Not in Phase 3:** live mode, refunds, payouts, card retries / direct capture of failed
payments, or SMS/email providers. The human-approval workflow and UNKNOWN-outcome safety
net mentioned above as gaps are now implemented — see Phase 4 below.

---

## 10. Phase 4 (PROVE) — Human Approval, UNKNOWN Safety, Analytics, Evaluation, Security

Phase 4 closes the two safety gaps Phase 3 left open, then proves the whole system
actually works with a real evaluation harness and honest, real-data analytics —
without touching the architecture: **LLM → Policy Engine → Action Engine → Razorpay
Adapter → Razorpay**. The LLM still never talks to Razorpay directly, and a human
decision never bypasses the Policy Engine — it only unlocks proceeding when a *fresh*
re-evaluation still allows it.

### 10.1 Human Approval Workflow

```
NEEDS_APPROVAL → POST /actions/{id}/approve → re-derive case/diagnosis/prediction/
strategy → RE-EVALUATE Policy Engine → still NEEDS_APPROVAL? honour the decision :
now REJECTED? clear the decision and block anyway → Action Engine → Razorpay → Audit
```

- `POST /api/v1/actions/{id}/approve` and `POST /api/v1/actions/{id}/reject` —
  `approve` records the decision then calls the **same** `execute_action()` used for
  every other execution; it never sets `EXECUTED` directly. `reject` is terminal.
- A `REJECTED` policy verdict is checked **before** any human decision is consulted
  and always wins — a stale `APPROVED` decision is cleared, not honoured, the moment
  policy re-evaluates to `REJECTED` (e.g. attempts exhausted or payment state changed
  since the decision was made).
- New fields on `RecoveryAction`: `human_decision` / `human_decided_at` /
  `human_decided_by` — distinct from `approved_at` (automatic policy approval).
- Dedicated **Approvals** page (`/approvals`) — a queue of cases whose *current* action
  is blocked on `NEEDS_APPROVAL` (not a stale analysis-time snapshot), each opening the
  real case drawer with the actual Approve/Reject controls.

### 10.2 UNKNOWN Payment State / Timeout Safety

```
Action → Razorpay create times out → outcome=UNKNOWN, status stays EXECUTING
       → existing EXECUTING-idempotency guard refuses any blind retry
       → POST /actions/{id}/verify-unknown → adapter searches Razorpay's own
         recent Payment Links for our reference_id
       → FOUND: adopt as EXECUTED/PENDING (no duplicate)
       → CONFIRMED absent: mark FAILED (now a verified fact — a retry is policy-gated, not blind)
       → inconclusive: stays UNKNOWN, never guessed
```

- A `RAZORPAY_TIMEOUT` on create is the ONLY thing that produces `outcome=UNKNOWN` —
  every other failure (4xx/5xx/rate-limited) is a definitive `FAILED` and safely
  retryable immediately.
- Resolution never bypasses policy: once resolved to `FAILED`, a retry still goes
  through the full `execute_action()` re-evaluation.
- Frontend renders `UNKNOWN` as a distinct amber state (never the same as red
  `FAILED`) with a **"Verify with Razorpay"** action — there is no retry button while
  an action is `UNKNOWN`.

### 10.3 Minimal Security Hardening

RECON OS has one seeded demo merchant and no user accounts — a full identity platform
would be scope well beyond the product. Instead:

- **API key** (`RECON_API_KEY`, unset/open by default for local dev) gates every
  action-mutating endpoint (propose / execute / approve / reject / verify-unknown /
  reconcile) via the `X-RECON-API-KEY` header. Set it before exposing the API beyond
  localhost — a startup log warns when it's unset.
- **Per-IP rate limiting** (`RECON_RATE_LIMIT_PER_MINUTE`, default 30/min) on the same
  endpoints — in-memory, single-process by design; a multi-instance deployment would
  need a shared store instead.
- Baseline response headers (`X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`) on every response.
- Webhook signature verification, secret handling, and idempotency are unchanged from
  Phase 3 (already fail-closed) — see `security.py` and `tests/test_security.py`.

### 10.4 Revenue Recovery Analytics

`GET /api/v1/analytics` (`services/analytics_service.py`) computes, live, from the
same `RecoveryCase` / `RecoveryAction` / `CaseIntelligence` rows every other page
reads — no new tracking tables, no fabricated numbers, and a metric with no honest
basis in current data (e.g. no recoveries yet) is `null`, never a fake zero:

revenue at risk, potential recoverable revenue (excludes policy-rejected dead ends),
revenue recovered, recovery rate, average recovery probability, automation rate,
human approval/rejection rate, recovery failure rate, UNKNOWN case count, policy
rejection count, average recovery time, average recovery attempts, and per-strategy
success rates. Presented on the **Analytics** page (`/analytics`).

### 10.5 Policies (read-only)

`GET /api/v1/policies` (`/policies` page) describes the ONE real deterministic Policy
Engine — condition → decision → restriction for each of the 7 rules — with every
threshold read live from `config.settings`, never a hardcoded copy. Deliberately
read-only: an editor would need its own re-validation against the engine's actual
rule logic to avoid a config that looks enforced but isn't; change `POLICY_*` env
vars and restart instead.

### 10.6 Deterministic Evaluation Framework

```bash
cd apps/api
python -m evaluation.runner
```

Runs 25 scenarios (`apps/api/evaluation/scenarios.py`) against the REAL pipeline —
`process_inbound_event → run_intelligence → get_or_create_action → execute_action →
approve/reject → verify_unknown_action → reconcile` — each in its own isolated
in-memory database with a deterministic fake Razorpay double
(`evaluation/fake_razorpay.py`). Nothing is hardcoded: pass/fail and the per-category
percentages (diagnosis, prediction, strategy, policy safety, action safety,
verification, recovery outcome, idempotency, UNKNOWN safety, approval safety) are
computed from what actually happened, printed as a human-readable report and written
to `evaluation/last_run.json`.

### 10.7 Demo Scenarios

All three use the real backend end-to-end — nothing here fakes a result:

1. **Automatic recovery** — Simulator preset *"UPI Session Timeout"* (₹4,999) →
   Recovery/Intelligence page → Analyze → Create Payment Link → Confirm/Simulate
   payment → `RECOVERED`.
2. **Human approval** — Simulator preset *"Card Insufficient Funds"* (₹14,999,
   exceeds the ₹5,000 auto-approval ceiling) → Approvals page → Approve →
   `execute_action()` re-validates and creates the Payment Link.
3. **UNKNOWN safety** — reproduced and verified end-to-end by
   `evaluation.scenarios.scenario_13` through `scenario_19` and
   `tests/test_phase4_safety.py::test_e2e_full_timeout_to_unknown_to_verification_chain`
   (a real Razorpay test-mode timeout is not reliably triggerable on demand from a
   live UI click, so this is proven via the deterministic harness rather than staged
   in the browser — the UNKNOWN badge, "Verify with Razorpay" control, and resolution
   flow shown on the Recovery/Intelligence drawer are the same real components those
   tests exercise).

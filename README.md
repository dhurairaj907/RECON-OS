# RECON OS — Revenue Recovery and Optimization Network

[![Phase](https://img.shields.io/badge/Phase-2%20%28THINK%29-blue.svg)](https://github.com/recon-os)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://python.org)
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
- **Testing**: `pytest` with SQLite in-memory fixtures (10/10 automated tests).
- **Containerization**: Docker & Docker Compose.

---

## 4. Quickstart with Docker Compose

### Prerequisites
- Docker Engine and Docker Compose installed.

### 1. Configure Environment
```bash
cp .env.example .env
```

### 2. Launch All Services
```bash
docker-compose up --build
```

This launches:
- **PostgreSQL Database** on `localhost:5432`
- **FastAPI Backend** on `http://localhost:8000` (API docs at `http://localhost:8000/docs`)
- **Next.js Command Center** on `http://localhost:3000`

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

Run the full pytest suite (100% pass rate):

```bash
python -m pytest tests/ -v
```

Test Coverage Highlights:
- **Webhook Security**: Valid signature, invalid signature rejection, missing signature.
- **Idempotency**: Duplicate webhook delivery guarantees zero duplicate cases.
- **Event Processor**: Payment failure recovery case creation, out-of-order webhook protection, case auto-resolution upon payment capture.
- **API Endpoints**: Dashboard metrics aggregation, simulator trigger, pagination, customer ledgers.

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
- **Creating a Payment Link is NOT revenue recovered.** The action is `EXECUTED /
  outcome PENDING` until a `payment_link.paid` webhook is verified → `RECOVERED`,
  the case is RESOLVED, and `amount_recovered` is set. Duplicate webhooks never
  double-count.
- Audit lifecycle: `ACTION_PROPOSED → ACTION_EXECUTION_STARTED → ACTION_POLICY_CHECKED
  → ACTION_APPROVED / ACTION_BLOCKED → PAYMENT_LINK_CREATED → ACTION_EXECUTED →
  RECOVERY_PENDING → RECOVERY_VERIFIED` (or `ACTION_EXECUTION_FAILED` / `RECOVERY_FAILED`).
- Demo: `POST /api/v1/simulator/payment-link-paid` simulates the confirming webhook so
  the loop completes without a real Test Mode payment.

**Not in Phase 3:** live mode, refunds, payouts, card retries / direct capture of failed
payments, SMS/email providers, a full human-approval workflow, or any Phase 4 learning.

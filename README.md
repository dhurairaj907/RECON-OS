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
endpoint works regardless). An **optional** LLM provider abstraction lives in
`apps/api/integrations/llm/` — the system is fully functional with `LLM_ENABLED=false`.

**Not in Phase 2:** any Razorpay API call, money movement, action execution, or human-
approval workflow — those are Phase 3 (ACT).

# CloudPilot — Architecture

## Overview

CloudPilot is a clean-architecture, async-first platform that unifies Azure, AWS and
GCP cost and telemetry into a single intelligent cockpit. The system is organized in
**five layers** with strict separation of concerns: routes never contain business
logic, services own the ORM, and the AI layer is decoupled from the request path.

```
┌─────────────────────────────────────────────────────┐
│  LAYER 1 — FRONTEND                                  │
│  React 18 · TypeScript · Vite · Tailwind · shadcn/ui │
└──────────────────────┬──────────────────────────────┘
                       │ REST/JSON over HTTPS (JWT bearer)
┌──────────────────────▼──────────────────────────────┐
│  LAYER 2 — BACKEND API                               │
│  FastAPI · Pydantic v2 · JWT · APScheduler           │
│  routes → services → repositories (SQLAlchemy ORM)   │
└──────┬───────────────┬──────────────────┬───────────┘
       │               │                  │
┌──────▼──────┐ ┌──────▼──────┐  ┌────────▼─────────┐
│ LAYER 3     │ │ LAYER 4     │  │ LAYER 5          │
│ AI LAYER    │ │ CLOUD LAYER │  │ DATA LAYER       │
│ 4 agents    │ │ Azure SDK   │  │ PostgreSQL 16    │
│ RAG engine  │ │ boto3 (AWS) │  │ ChromaDB         │
│ Ollama LLM  │ │ GCP SDK     │  │ Redis 7          │
│ Prophet ML  │ │ (read-only) │  │ Supabase (prod)  │
└─────────────┘ └─────────────┘  └──────────────────┘
```

## Layer responsibilities

- **Frontend** — a Vite SPA. Server state is owned by TanStack Query, client UI state
  by Zustand. The access token lives in memory only; refresh is an HttpOnly cookie.
- **Backend API** — FastAPI with a master router under `/api/v1`. Every endpoint is
  authenticated by default; security headers, request IDs and Prometheus metrics are
  applied via middleware. Business logic lives in `services/`, never in routes.
- **AI layer** — four agents (`cost`, `rightsizing`, `forecast`, `architect`).
  The first three run on an APScheduler process (`cloudpilot.ai.orchestrator`); the
  ArchitectAgent runs on-demand inside the chat endpoint. The RAG engine wraps
  ChromaDB + nomic-embed-text embeddings + the Ollama/OpenAI LLM client.
- **Cloud layer** — one adapter per provider implementing a read-only contract
  (`get_resources`, `get_billing`, `get_metrics`, `validate_credentials`). In
  `DEMO_MODE` (or when credentials are absent) adapters return deterministic mock data.
- **Data layer** — PostgreSQL is the system of record (with a range-partitioned
  `metric_samples` table); Redis backs caching, rate limiting and JWT revocation;
  ChromaDB stores document embeddings for RAG.

## Request lifecycle (example: `GET /api/v1/costs/summary`)

1. Browser → nginx (TLS termination, rate-limit check).
2. nginx → FastAPI.
3. Security-headers middleware adds CSP/HSTS/etc to every response.
4. `get_token_payload` validates the JWT (HS256, audience pinned, jti revocation check).
5. `get_current_user` resolves the user **and binds the tenant context** via a `ContextVar`.
6. RBAC dependency (`require_permission`) checks the role's permission.
7. The route delegates to `CostService.get_summary()`.
8. The SQLAlchemy tenant listener auto-appends `WHERE organization_id = :org` to every SELECT.
9. The response is serialized through a Pydantic schema.
10. Sensitive operations write a signed `audit_log` row (hash-chained).
11. Response returned with `X-Request-ID` and `X-Response-Time`.

## Agent execution model

```
APScheduler process (orchestrator)
  ├─ CostAgent.run()          every 60 min   → INSERT recommendations (agent='cost')
  ├─ RightSizingAgent.run()   daily 02:00    → INSERT recommendations (agent='rightsizing')
  ├─ ForecastAgent.run()      daily 03:00    → UPSERT forecast_snapshots + budget alert
  └─ cloud sync               hourly         → refresh resources/billing/metrics

Chat endpoint (on-demand)
  └─ ArchitectAgent.trigger() → RAG.retrieve() → LLM.generate() → INSERT chat_messages
```

The API never invokes scheduled agents inline — it only reads their persisted output.

## Caching strategy

| Cache | Backend | TTL |
|-------|---------|-----|
| Dashboard aggregates | Redis (`dashboard:{org}:{period}`) | 5 min |
| Pricing catalog | Redis | 1 week |
| JWT revocation list | Redis (`revoked:{jti}`) | token expiry |
| RAG query results | in-process LRU (100 entries) | process life |

## Technology choices — rationale

- **FastAPI over Django/Flask** — native async, automatic OpenAPI, Pydantic v2 validation.
- **SQLAlchemy 2.0 async** — single ORM for the whole app; the tenant listener gives
  defense-in-depth that a raw-SQL approach could not.
- **ChromaDB (embedded) over Qdrant/Pinecone** — zero extra infra, proven in EchoLearn.
- **Ollama + Qwen 2.5 4B** — privacy-by-design local inference that fits 8 GB RAM;
  OpenAI is an optional fallback only.
- **Prophet over ARIMA/LSTM** — robust to missing data and weekly seasonality with
  minimal tuning.
- **IsolationForest + Z-score** — unsupervised anomaly detection that needs no labels.
- **React + Vite over Next.js** — no SSR requirement; sub-second HMR; full control of the SPA.

See [`security.md`](security.md) for the trust-boundary model.

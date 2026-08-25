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
  Live `get_billing`/`get_metrics` raise `NotImplementedError` on every provider by
  design — see the README's "Connecting Real Cloud Accounts".
- **Pricing + simulation** — `pricing/` holds a provenance-carrying rate card read from
  a committed snapshot (`pricing/data/pricing_snapshot.json`, refreshed by
  `python -m cloudpilot.pricing.refresh`); `simulation/` invents *usage* only and
  multiplies it by that rate card. See "Where the numbers come from" below.
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

| Cache | Backend | TTL | Status |
|-------|---------|-----|--------|
| JWT revocation list | Redis (`revoked:{jti}`) | token expiry | implemented (`core/rate_limit.py`) |
| RAG query results | in-process dict, keyed `(query, k)`, capped at 100 | process life | implemented (`ai/rag/engine.py`) |
| Pricing catalog | `functools.lru_cache` over the committed snapshot | process life | implemented (`pricing/catalog.py`) |
| Dashboard aggregates | Redis (`dashboard:{org}:{name}[:part]`) | `CACHE_DASHBOARD_TTL` (5 min) | implemented (`core/cache.py`) — covers the cost summary, breakdown and timeseries |

`CACHE_PRICING_TTL` is defined but unused: the rate card is not fetched at
request time at all, so it needs no expiry — it is a snapshot refreshed by `make pricing`.

Three rules govern the dashboard cache, and `core/cache.py` exists to enforce them:

- **Every key is tenant-scoped.** A cache sits *in front of* the ORM tenant filter, so
  a key that was not org-scoped would serve one tenant's figures to another without
  `core/tenant.py` ever running. `org_key()` is the only way to build a key and always
  takes an organization id.
- **It fails open.** Redis being unreachable degrades to a slower correct answer, never
  an error — deliberately the opposite of the auth surface, where `is_revoked` fails
  *closed* (see [security.md](security.md)).
- **It is invalidated on write, not just on TTL.** Actioning a recommendation changes
  the summary's pending count and savings total; waiting out five minutes would leave
  the KPI row disagreeing with what the user just did. Invalidation is hooked into
  recommendation status changes, cloud syncs, and agent runs that create
  recommendations.

## Technology choices — rationale

- **FastAPI over Django/Flask** — native async, automatic OpenAPI, Pydantic v2 validation.
- **SQLAlchemy 2.0 async** — single ORM for the whole app; the tenant listener gives
  defense-in-depth that a raw-SQL approach could not.
- **ChromaDB over Qdrant/Pinecone** — one small container, proven in EchoLearn. Pinned to
  `chromadb/chroma:0.5.23`: `:latest` dropped the v1 API the pinned 0.5 client speaks, so
  the server image and the Python client must move together.
- **Ollama + Qwen 2.5 3B** — privacy-by-design local inference that fits 8 GB RAM;
  OpenAI is an optional fallback only. On CPU a 3B model routinely needs more than a
  minute, hence `LLM_TIMEOUT_SECONDS=180` — too low a timeout does not error, it
  silently routes every answer to the offline fallback.
- **Prophet over ARIMA/LSTM** — robust to missing data and weekly seasonality with
  minimal tuning.
- **IsolationForest + Z-score** — unsupervised anomaly detection that needs no labels.
- **React + Vite over Next.js** — no SSR requirement; sub-second HMR; full control of the SPA.

## Where the numbers come from

The invariant: **CloudPilot never invents a price.** It invents *usage* and multiplies
by a published rate.

```
pricing/sources.py   → fetch rates from public, keyless pricing APIs
pricing/refresh.py   → write pricing/data/pricing_snapshot.json  (make pricing)
pricing/catalog.py   → load the snapshot, lru_cached, each Price carrying its
                       PriceSource (azure_retail_api | published_list_price) + as-of date
        ↓
simulation/fleet.py  → what the estate is: resources, SKUs, node counts, regions
simulation/engine.py → what it did: hours run, GB stored, CPU/RAM samples
        ↓
billing_entry rows = published_rate × simulated_usage
        ↓
CostAgent / RightSizingAgent / ForecastAgent read those rows
```

Two consequences worth stating, because they are the point of the design:

- **Anomalies are physical, not arithmetic.** The demo's Kubernetes spike is not
  `cost *= 4.4`; it is `aks-prod-cluster` going 4 → 18 nodes for three days, and the
  extra spend is exactly what 14 more `Standard_D4s_v3` nodes cost. CostAgent's
  root-cause narrative is therefore *true* of the estate it describes.
- **Savings are real deltas.** "Downsize `Standard_D4s_v3` → `Standard_D2s_v3`, save
  $88/month" is the genuine gap between two Azure rates, not a chosen number.

The snapshot is committed deliberately: the AWS offer files are tens of MB, the demo
must work offline, and a pinned rate card makes the seeded dataset reproducible.
Downsize pairs live in `catalog.py` rather than the rate card — "the next size down in
the same family" is a modelling decision about the fleet, not a fact about pricing.

Everything in `simulation/` is seeded per resource name, so a re-seed reproduces the
same estate and a demo shows the same numbers twice.

See [`security.md`](security.md) for the trust-boundary model.

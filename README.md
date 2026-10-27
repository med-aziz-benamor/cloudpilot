# CloudPilot

**AI-Powered FinOps & Cloud Intelligence Platform**

CloudPilot unifies **Azure, AWS and GCP** into a single intelligent cockpit — with
live cost tracking, autonomous AI agents, and a RAG-powered Cloud Advisor. It turns
raw multi-cloud telemetry into actionable optimization decisions in minutes, not months.

Built as an internship project at **AMC Ernst & Young Tunisie (IA & Data)** by
**Mohammed Aziz Ben Amor** — ESPRIT ARCTIC, June 2026.

> 32% of enterprise cloud spend is wasted on idle or oversized resources, and 78% of
> IT teams lack real-time visibility across providers. CloudPilot makes cloud cost
> management *proactive* instead of retrospective: four autonomous AI agents watch the
> entire cloud estate continuously, surface defensible recommendations, forecast future
> spend, and answer infrastructure questions in natural language with cited sources.

---

## Where to Start

| If you want to… | Read |
|---|---|
| Understand the project in 10 minutes | This README, then [Where the Numbers Come From](#where-the-numbers-come-from) |
| See the full internship record (context, decisions, chronology, results) | [`docs/internship-dossier.md`](docs/internship-dossier.md) |
| Understand the system design | [`docs/architecture.md`](docs/architecture.md) → [`docs/ai-agents.md`](docs/ai-agents.md) → [`docs/data-model.md`](docs/data-model.md) |
| Review security and multi-tenancy | [`docs/security.md`](docs/security.md) |
| Run it locally | [Quick Start](#quick-start-3-commands--full-demo) below, then [`docs/development.md`](docs/development.md) |
| Follow the engineering work session by session | the dated [session reports](#documentation) |

---

## Key Features

- **Multi-cloud cost cockpit.** Azure, AWS and GCP spend in one place: month-to-date,
  projected month-end, and breakdowns by provider, service and region.
- **Four AI agents** ([details](docs/ai-agents.md)):
  - **CostAgent** detects billing anomalies with IsolationForest + Z-score, behind
    materiality gates (≥ 25 % and ≥ $5 above baseline).
  - **RightSizingAgent** finds over-provisioned resources from P95 CPU/RAM and prices
    the downsize from real published rates.
  - **ForecastAgent** projects spend 30/60/90 days ahead with Prophet and raises an
    alert when the month is heading more than 10 % over budget.
  - **ArchitectAgent** (the Cloud Advisor) answers questions in natural language using
    RAG over a FinOps knowledge base plus the tenant's live data, with citations.
- **Every figure is traceable.** Each recommendation shows *how it was calculated*,
  including both rates, their publisher and the snapshot date. The full rate card is
  browsable under Settings → Pricing.
- **Real prices, simulated usage.** No dollar amount is hand-written; see
  [Where the Numbers Come From](#where-the-numbers-come-from).
- **Enterprise security.** JWT with rotating refresh tokens, RBAC (admin / analyst /
  viewer), two independent tenant-isolation layers, Fernet-encrypted cloud credentials,
  and a hash-chained audit log ([details](docs/security.md)).
- **Private by default.** The LLM runs locally through Ollama, so no infrastructure
  data leaves the machine. When the model is unavailable, the Advisor says so instead of
  inventing an answer.

### Screens

| Screen | What it shows |
|---|---|
| **Overview** | KPI row, multi-cloud spend chart, top cost drivers, latest agent findings |
| **Resources** | Inventory tree (provider → region → service) with per-resource metrics and cost trend |
| **Costs** | Breakdown by provider / service / region, daily time series, anomaly timeline |
| **Recommendations** | Agent findings: accept / reject / snooze, each with its calculation basis |
| **Forecast** | 30/60/90-day projection with uncertainty band, budget line and overrun verdict |
| **Cloud Advisor** | RAG chat with citation chips and a trace of the live data consulted |
| **Settings** | Cloud accounts, pricing rate card, profile, audit log |

See [`docs/frontend.md`](docs/frontend.md) for how the UI is built.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  LAYER 1 — FRONTEND                                  │
│  React 18 + TypeScript + Vite + Tailwind + shadcn/ui │
│  Login · Overview · Resources · Costs ·              │
│  Recommendations · Forecast · Chat · Settings        │
└──────────────────────┬──────────────────────────────┘
                       │ REST/JSON over HTTPS (JWT)
┌──────────────────────▼──────────────────────────────┐
│  LAYER 2 — BACKEND API                               │
│  FastAPI + Pydantic v2 + JWT + APScheduler           │
│  /api/v1/auth · /cloud-accounts · /resources         │
│  /costs · /recommendations · /forecast · /chat       │
└──────┬───────────────┬──────────────────┬───────────┘
       │               │                  │
┌──────▼──────┐ ┌──────▼──────┐  ┌────────▼─────────┐
│  LAYER 3    │ │  LAYER 4    │  │  LAYER 5         │
│  AI LAYER   │ │  CLOUD      │  │  DATA LAYER      │
│  4 Agents   │ │  LAYER      │  │  PostgreSQL      │
│  RAG Engine │ │  Azure SDK  │  │  ChromaDB        │
│  Ollama LLM │ │  boto3 AWS  │  │  Redis           │
│  Prophet ML │ │  GCP SDK    │  │  Supabase        │
└─────────────┘ └─────────────┘  └──────────────────┘
```

See [`docs/architecture.md`](docs/architecture.md) for the full narrative.

### Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript (strict), Vite, Tailwind CSS, Radix UI, TanStack Query, Zustand, Recharts, Framer Motion |
| Backend | FastAPI, Pydantic v2, SQLAlchemy 2.0 (async) + asyncpg, Alembic, APScheduler, PyJWT, bcrypt, cryptography (Fernet), loguru |
| AI / ML | Ollama (Qwen 2.5 3B + nomic-embed-text), ChromaDB, Prophet, scikit-learn (IsolationForest), pandas, numpy |
| Cloud SDKs | Azure SDK (`azure-mgmt-*`, `azure-identity`), boto3, Google Cloud client libraries (all read-only) |
| Data | PostgreSQL 16 (partitioned metrics table), Redis 7, ChromaDB |
| Infrastructure | Docker Compose, nginx, Kubernetes manifests, Terraform (Azure: AKS, PostgreSQL Flexible Server, Redis), Prometheus, Grafana, GitHub Actions |
| Quality | pytest, Vitest + Testing Library, Playwright, ruff, mypy (strict), ESLint |

---

## Prerequisites

| Tool | Version |
|------|---------|
| Docker + Docker Compose | 24+ / v2 |
| Python | 3.11 |
| Poetry | 1.8+ (backend dependency management) |
| Node.js | 20+ |
| pnpm | 9.x (frontend package manager) |
| Make | any |

Everything runs locally via Docker. On an Apple Silicon (M1/ARM64) machine all images
are ARM-compatible. The default local LLM is **Qwen 2.5 3B via Ollama** (≈2 GB RAM). Pull it with `ollama pull qwen2.5:3b`.

---

## Quick Start (3 commands → full demo)

```bash
cd cloudpilot
cp .env.example .env
make dev
# In a second terminal, once services are healthy:
make seed
```

Then open **http://localhost:5173** and sign in with:

```
Email:    demo@cloudpilot.dev
Password: demo1234
```

Or click **"Try Demo"** on the login page to log in instantly.

`make seed` populates a fully realistic dataset with **no cloud credentials required**:
1 organization (Acme Corp) on a $7,500/month budget, 3 cloud accounts, **50 resources**
(22 Azure · 18 AWS · 10 GCP), **90 days** of billing priced from the real rate card
(including 2 deliberate anomalies), **14 days** of CPU/RAM metrics, and 3 chat sessions.

The **recommendations are not seeded** — after building the estate, `make seed` runs the
real CostAgent, RightSizingAgent and ForecastAgent against it. However many findings the
recommendations page shows, those are genuine agent output, so the count varies with the
estate rather than being a fixed number. Same for the agent run logs on the admin page.

---

## Environment Variables

All configuration is environment-driven. Copy `.env.example` to `.env` and adjust.

| Variable | Purpose | Default |
|----------|---------|---------|
| `APP_ENV` | Runtime environment | `development` |
| `DATABASE_URL` | Async Postgres DSN | `postgresql+asyncpg://cp:cp@postgres:5432/cloudpilot` |
| `REDIS_URL` | Redis connection | `redis://redis:6379/0` |
| `JWT_SECRET` | HS256 signing key (≥32 chars) | _change in prod_ |
| `FERNET_MASTER_KEY` | Credential encryption key | _generate; see below_ |
| `DEMO_MODE` | Use mock data, no cloud creds needed | `true` |
| `OLLAMA_BASE_URL` | Local LLM server | `http://ollama:11434` |
| `OLLAMA_MODEL` | LLM model id | `qwen2.5:3b` |
| `LLM_TIMEOUT_SECONDS` | Give a CPU-bound local model room to finish | `180` |
| `CHROMADB_HOST` / `CHROMADB_PORT` | Vector store | `chromadb` / `8000` |
| `OPENAI_API_KEY` | Optional LLM fallback | _empty_ |
| `AZURE_*` / `AWS_*` / `GCP_*` | Real cloud credentials | _empty (demo mode)_ |
| `VITE_API_BASE_URL` | Frontend → backend URL | `http://localhost:8000` |

Generate a Fernet key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## API

Once running, the interactive API documentation is available at:

- **Swagger UI** → http://localhost:8000/docs
- **ReDoc** → http://localhost:8000/redoc
- **Prometheus metrics** → http://localhost:8000/metrics

See [`docs/api-reference.md`](docs/api-reference.md) for endpoint-by-endpoint details.

---

## Project Structure

```
cloudpilot/
├── backend/        FastAPI app
│   └── cloudpilot/
│       ├── api/v1/     routes (auth, cloud-accounts, resources, costs,
│       │               recommendations, forecast, chat, admin)
│       ├── services/   business logic — routes never touch the ORM
│       ├── ai/         4 agents + RAG engine + LLM client
│       ├── cloud/      one read-only adapter per provider
│       ├── pricing/    published rate cards + provenance (see below)
│       ├── simulation/ the simulated estate the rates are applied to
│       ├── models/     SQLAlchemy models · schemas/ Pydantic v2
│       └── core/       auth, RBAC, tenant filter, audit chain
├── frontend/       React + Vite SPA — premium macOS-style UI
├── infrastructure/ Kubernetes manifests, Terraform (Azure), Prometheus/Grafana
├── docs/           Internship dossier, technical guides, dated session reports
└── .github/        CI (lint/type/test) and Docker build workflows
```

---

## Documentation

**Project record**

| Document | What's in it |
|-------|--------------|
| [`docs/internship-dossier.md`](docs/internship-dossier.md) | The complete internship record: business problem, architecture, the central pricing-simulator decision, security design, a dated journal of all work, technical inventory, notable bugs, methodology, current state and open items |

**Technical guides**

| Guide | What's in it |
|-------|--------------|
| [`docs/architecture.md`](docs/architecture.md) | The five layers, request lifecycle, agent scheduling, how pricing feeds simulation, caching (and which caches are not built), technology rationale |
| [`docs/ai-agents.md`](docs/ai-agents.md) | Each agent's algorithm, thresholds and why they are set there; the RAG pipeline, its relevance cut-off and caching; the LLM client's honest failure modes |
| [`docs/data-model.md`](docs/data-model.md) | Every table and its columns, the partitioned metrics table, multi-tenancy in the schema, the migration history, the demo dataset |
| [`docs/frontend.md`](docs/frontend.md) | Screens and routes, source layout, state management, the in-memory token + refresh flow, provenance components, unit and e2e suites |
| [`docs/api-reference.md`](docs/api-reference.md) | Every endpoint, permissions, error envelope, curl examples |
| [`docs/security.md`](docs/security.md) | Trust boundaries, JWT/refresh design, RBAC + tenant filter, the startup secrets guard, credential encryption and key rotation, audit-log chain, incident runbook |
| [`docs/deployment.md`](docs/deployment.md) | Docker Compose (dev + prod), Kubernetes, Azure Terraform, CI/CD, health and observability |
| [`docs/development.md`](docs/development.md) | Local setup, running tests, migrations, refreshing the rate card, adding a provider or an agent, code style |

**Session reports** (dated engineering record, oldest first)

| Report | What's in it |
|-------|--------------|
| [`docs/session-report-2026-07-14.md`](docs/session-report-2026-07-14.md) | Dated engineering record of the pricing-grounded-simulator rework and the bugs it surfaced |
| [`docs/session-report-2026-07-20.md`](docs/session-report-2026-07-20.md) | Security/agent hardening pass — tenant filter fix, anomaly recalibration, RAG cache fixes |
| [`docs/session-report-2026-07-20b.md`](docs/session-report-2026-07-20b.md) | Denormalizing `organization_id` onto `resources`/`billing_entries` to restore two-layer tenant isolation |
| [`docs/session-report-2026-08-05.md`](docs/session-report-2026-08-05.md) | Status audit: zero commits since 20 July, 116 tests still passing, `make seed` still not re-run, RBAC has no test coverage |
| [`docs/session-report-2026-08-25.md`](docs/session-report-2026-08-25.md) | Demo-readiness hardening pass — auth/RBAC security fixes, RBAC test coverage added, and four Cloud Advisor crash bugs found by driving the app in a real browser |
| [`docs/session-report-2026-08-25b.md`](docs/session-report-2026-08-25b.md) | Closing the carried-forward gaps — budget read/write (the Forecast and Recommendations pages disagreed about it), `metric_samples` isolation, dashboard caching, a 3x RAG corpus, and a fully type-clean backend |
| [`docs/session-report-2026-08-31.md`](docs/session-report-2026-08-31.md) | Pricing provenance surfaced in the UI, the committed Playwright suite, frontend unit tests added to CI, and a session-bootstrap race fix |

---

## Testing & Quality

| Suite | Tool | Tests | Run with |
|---|---|---|---|
| Backend unit + integration | pytest | 203 | `make test` (in the container; DB-backed suites need `CLOUDPILOT_TEST_DB`) |
| Frontend unit / component | Vitest + Testing Library | 36 | `cd frontend && pnpm test` |
| End-to-end (real browser, live stack) | Playwright | 18 | `make e2e` |

Static checks: `ruff` and strict `mypy` on the backend, `tsc --noEmit` and ESLint on the
frontend (`make lint`, `make typecheck`). CI (`.github/workflows/ci.yml`) runs lint,
type-check, unit tests and the build for both sides on every push and pull request. The
e2e suite needs a running stack, so it runs locally.

Notable suites: the tenant-isolation tests (`test_tenant_isolation*.py`) and the RBAC
tests were **mutation-verified**: deliberately breaking the guard they protect makes them
fail. Every e2e spec corresponds to a bug that reached a running application. See
[`docs/development.md`](docs/development.md#running-tests).

---

## Makefile Targets

```
make dev          # Start the full stack in dev mode (hot reload)
make up           # Start the stack detached
make down         # Stop the stack
make build        # Build all Docker images
make migrate      # Run Alembic migrations
make seed         # Seed demo data
make pricing      # Refresh the rate card (Azure API + published list prices)
make pricing-deep # Also fetch the large AWS offer files (slow)
make test         # Run backend + frontend tests
make lint         # ruff + mypy + eslint
make typecheck    # mypy + tsc
make format       # ruff format + eslint --fix
make logs         # Tail all service logs
make clean        # Remove containers + volumes (DESTROYS data)
make shell-be     # Bash into the backend container
make shell-db     # psql into Postgres
make docs         # Serve docs locally
```

---

## Where the Numbers Come From

CloudPilot runs on a **simulated cloud estate priced from real, published rate cards**.
This is deliberate, and the split matters:

| | Simulated | Real |
|---|---|---|
| **Usage** — which resources exist, how many nodes they run, how busy they are, how many GB they store | ✅ | |
| **Price** — the $/hour and $/GB-month every cost is computed from | | ✅ |

No dollar figure in the platform is hand-written. Billing is always
`published_rate × simulated_usage`, so any number on screen can be traced back to the
provider that published it. `RightSizingAgent` saying "downsize `Standard_D4s_v3` →
`Standard_D2s_v3`, save $88/month" is the genuine delta between two Azure rates
($0.24/hr − $0.12/hr, × 730 hours), not an invented figure.

Rates come from the providers' **public, keyless** pricing APIs — no cloud account, no
subscription, and no spend required:

- **Azure** → the [Retail Prices API](https://prices.azure.com/api/retail/prices), queried live.
- **AWS** → the Price List bulk offer files. These run to hundreds of MB, so the default
  refresh uses AWS's published list prices and `make pricing-deep` fetches the real files.
- **GCP** → the Cloud Billing Catalog API needs an API key, so GCP uses published list prices.

Every rate carries its **provenance** (`azure_retail_api` vs `published_list_price`) and
an as-of date, both surfaced on the recommendations that depend on it. Refresh the
committed snapshot with:

```bash
make pricing         # fast: Azure API + published list prices
make pricing-deep    # also fetch the large AWS offer files
```

Cost **anomalies are physical, not arithmetic.** The demo's Kubernetes spike is not a
`cost *= 4.4` fudge — it is a misconfigured autoscaler taking `aks-prod-cluster` from 4
nodes to 18 for three days, and the $80.64/day of extra spend is exactly what 14 more
`Standard_D4s_v3` nodes cost. That is why the CostAgent's root-cause explanation is
actually true of the estate it is describing.

The recommendations in the demo are **not seeded** — `make seed` builds the estate and
then runs the real CostAgent, RightSizingAgent and ForecastAgent against it. What you
see on the recommendations page is what the agents genuinely found.

---

## Connecting Real Cloud Accounts

> **Status: partially implemented.** Resource *inventory* works for Azure and AWS.
> Live **billing and metrics are not implemented for any provider** — those adapter
> methods raise `NotImplementedError` rather than silently returning simulated figures,
> because presenting invented costs as a real invoice would have the agents raise
> anomalies against spend that never happened. Keep `DEMO_MODE=true` until they are wired.

When implementing them, the entry points are:

- **Azure** → `CostManagementClient.query.usage()` and `MonitorManagementClient.metrics.list()`.
  Service principal needs *Reader* + *Cost Management Reader*.
- **AWS** → Cost Explorer `get_cost_and_usage()` and CloudWatch `get_metric_statistics()`.
  Read-only IAM role with an external id.
- **GCP** → the BigQuery billing export and Cloud Monitoring `list_time_series()`.

CloudPilot is **read-only by design** — it never creates, updates or deletes cloud resources.

---

## Project Status

Everything in the Quick Start works end to end in demo mode. These are the honest gaps —
listed so nobody discovers them the hard way:

| Area | Status |
|------|--------|
| Demo mode (`DEMO_MODE=true`) | ✅ Complete — the intended way to run this today |
| Cost tracking, agents, RAG advisor, forecasting | ✅ Working against the simulated estate |
| Auth, RBAC, audit chain | ✅ Implemented and tested; production boot is guarded against placeholder secrets. Brute-force lockout, IP-spoofing and timing-side-channel fixes landed 2026-08-25 — see the session report |
| Tenant isolation | ✅ Two independent layers (RBAC + ORM filter) over **every** org-scoped model — `metric_samples` joined the rest in migration `005`. See [security.md](docs/security.md#what-layer-2-covers) |
| Live resource inventory | ⚠️ Azure and AWS implemented, but exercised far less than demo mode. **GCP is not implemented** — `Compute Engine aggregatedList()` is still a stub |
| Live billing + metrics (all providers) | ❌ `NotImplementedError` by design — see above |
| Setting an org's monthly budget | ✅ `GET`/`PATCH /api/v1/forecast/budget` (admin-only, audited) and a working control on the Forecast page |
| Dashboard aggregate caching | ✅ Redis-backed, tenant-scoped, invalidated on write, validated on read (`core/cache.py`) |
| `make dev` on a machine other than the original | ✅ Fixed 2026-08-25 — the `ollama` volume is now a named Docker volume |
| Backend tests on the host | ⚠️ Need Python 3.11; a newer interpreter fails at collection. Run them in the container |
| Pricing provenance in the UI | ✅ A per-recommendation derivation (both rates, their publisher, the as-of date) and a full rate card at Settings → Pricing, backed by `GET /api/v1/pricing/catalog` |
| Frontend end-to-end tests | ✅ A committed Playwright suite (`make e2e`), run against a live stack. Not in CI — it needs a stack to run against |

---

## Contributing

1. Branch with conventional naming: `feature/...`, `fix/...`, `chore/...`.
2. Conventional commits: `feat(auth): add refresh token rotation`.
3. `make lint && make test` must pass before opening a PR.
4. Schema changes go through Alembic — never hand-written SQL.

---

## License

MIT © 2026 Mohammed Aziz Ben Amor — built at AMC Ernst & Young Tunisie (IA & Data).

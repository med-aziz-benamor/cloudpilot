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

`make seed` populates a fully realistic dataset: 1 organization (Acme Corp),
3 cloud accounts, 50 resources, 90 days of billing data (with 2 deliberate anomalies),
14 days of CPU/RAM metrics, 8 AI recommendations, and 3 chat sessions — so the platform
is immediately interactive with **no cloud credentials required**.

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
| `OLLAMA_MODEL` | LLM model id | `qwen2.5:4b` |
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
├── backend/        FastAPI app — models, services, AI agents, cloud adapters
├── frontend/       React + Vite SPA — premium macOS-style UI
├── infrastructure/ Kubernetes manifests, Terraform (Azure), Prometheus/Grafana
├── docs/           Architecture, API, security, deployment, development guides
└── .github/        CI (lint/type/test) and Docker build workflows
```

---

## Makefile Targets

```
make dev          # Start the full stack in dev mode
make build        # Build all Docker images
make test         # Run backend + frontend tests
make lint         # ruff + mypy + eslint
make migrate      # Run Alembic migrations
make seed         # Seed demo data
make logs         # Tail all service logs
make clean        # Remove containers + volumes
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

## Contributing

1. Branch with conventional naming: `feature/...`, `fix/...`, `chore/...`.
2. Conventional commits: `feat(auth): add refresh token rotation`.
3. `make lint && make test` must pass before opening a PR.
4. Schema changes go through Alembic — never hand-written SQL.

---

## License

MIT © 2026 Mohammed Aziz Ben Amor — built at AMC Ernst & Young Tunisie (IA & Data).

# CloudPilot — Internship Dossier

**A complete record of the project and everything done on it, assembled as raw material
for the *rapport de stage* and the *journal de stage*.**

Author: Mohammed Aziz Ben Amor · ESPRIT ARCTIC · AMC Ernst & Young Tunisie (IA & Data)
Period covered: 22 June 2026 → 31 August 2026 · Compiled 31 August 2026

> This document is written in English to match the codebase and the existing `docs/`.
> A French glossary of the recurring technical terms is at the end (§14), and §13
> suggests how to map this material onto a French report structure.

---

## Table of contents

1. [Project identity card](#1-project-identity-card)
2. [The business problem](#2-the-business-problem)
3. [What CloudPilot is](#3-what-cloudpilot-is)
4. [Architecture](#4-architecture)
5. [The central technical decision: the pricing-grounded simulator](#5-the-central-technical-decision-the-pricing-grounded-simulator)
6. [Security design](#6-security-design)
7. [Chronological journal](#7-chronological-journal)
8. [Technical inventory](#8-technical-inventory)
9. [The bugs worth telling](#9-the-bugs-worth-telling)
10. [Methodology and engineering practices](#10-methodology-and-engineering-practices)
11. [Current state](#11-current-state)
12. [What remains open](#12-what-remains-open)
13. [Angles for the written report](#13-angles-for-the-written-report)
14. [Glossary FR/EN](#14-glossary-fren)

---

## 1. Project identity card

| | |
|---|---|
| **Name** | CloudPilot — AI-Powered FinOps & Cloud Intelligence Platform |
| **Host organisation** | AMC Ernst & Young Tunisie, département IA & Data |
| **School** | ESPRIT — ARCTIC |
| **Author** | Mohammed Aziz Ben Amor (solo developer) |
| **Period** | 22 June 2026 → 31 August 2026 (~10 weeks) |
| **Repository** | `github.com/med-aziz-benamor/cloudpilot` |
| **Working branch** | `feat/pricing-grounded-simulator` (54 commits ahead of `main`, open as PR #1) |
| **Total commits** | 55 |
| **Code volume** | ~8,900 lines backend Python · ~6,100 lines frontend TypeScript · ~3,800 lines of tests |
| **Test suites** | 199 backend · 36 frontend unit · 15 end-to-end |
| **Languages** | Python 3.11, TypeScript 5.4 |
| **Status** | Fully working in demo mode; live billing/metrics deliberately not implemented |

### The one-sentence version

> CloudPilot never invents a price: it invents *usage* and multiplies by what Microsoft,
> Amazon and Google actually charge — so a cost anomaly is fourteen extra Kubernetes
> nodes for three days, and the $80.64/day it costs is a number you can defend in a room.

---

## 2. The business problem

Two figures frame the project:

- **32%** of enterprise cloud spend is wasted on idle or oversized resources.
- **78%** of IT teams lack real-time visibility across providers.

The underlying dynamic is that cloud cost management is **retrospective**. Teams
discover overspend when the invoice arrives, weeks after the decisions that caused it.
Each provider has its own console, its own billing model and its own vocabulary, so a
company on Azure + AWS + GCP maintains three mental models and reconciles them by hand
in a spreadsheet.

CloudPilot's thesis is that this should be **proactive**: autonomous agents watch the
whole estate continuously, surface defensible recommendations, forecast future spend,
and answer infrastructure questions in natural language with cited sources.

The word doing the work in that sentence is **defensible**. A FinOps tool that says
"you can save $4,200/month" and cannot say where that number comes from is not usable
in an enterprise conversation — the first question in the room is always *"where does
that figure come from?"*. This is what drove the project's single most important
technical decision (§5).

---

## 3. What CloudPilot is

A multi-cloud FinOps cockpit with eight screens and four autonomous AI agents.

### The screens

| Screen | What it does |
|---|---|
| **Login** | JWT authentication, demo tenant one-click |
| **Overview** | KPI row (MTD spend, potential savings, optimisation score, connected clouds), multi-cloud spend chart, top cost drivers, latest agent findings |
| **Resources** | Inventory as a provider → region → service tree, per-resource detail with metrics and cost trend |
| **Costs** | Breakdown by provider / service / region, daily timeseries, anomaly timeline |
| **Recommendations** | The agents' findings, filterable by agent and status, accept / reject / snooze, and the calculation basis behind each figure |
| **Forecast** | Prophet projections at 30/60/90 days, budget line, overrun verdict, budget setting (admin) |
| **Cloud Advisor** | RAG chat over a FinOps knowledge base, with citations and live estate data |
| **Settings** | Cloud accounts, the pricing rate card, profile, audit log |

### The four agents

| Agent | Cadence | Method | Output |
|---|---|---|---|
| **CostAgent** | every 60 min | Z-score + IsolationForest over per-(account, service) daily series | anomaly recommendations with root-cause narrative |
| **RightSizingAgent** | daily 02:00 | P95 CPU/RAM over a lookback window vs. a utilisation threshold | downsize recommendations with priced savings |
| **ForecastAgent** | daily 03:00 | Prophet time-series fit | 30/60/90-day forecast snapshots + budget-overrun alerts |
| **ArchitectAgent** | on demand | RAG retrieval over ChromaDB + local LLM generation | chat answers with citations |

The first three run in a separate APScheduler process and only ever write to the
database. The API never invokes them inline — it reads their persisted output. The
ArchitectAgent runs inside the chat request.

---

## 4. Architecture

Five layers, strict separation: routes never contain business logic, services own the
ORM, the AI layer is decoupled from the request path.

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

### Request lifecycle — `GET /api/v1/costs/summary`

1. Browser → nginx (TLS termination, rate-limit check)
2. nginx → FastAPI
3. Security-headers middleware adds CSP/HSTS/etc. to every response
4. `get_token_payload` validates the JWT (HS256, audience pinned, jti revocation check)
5. `get_current_user` resolves the user **and binds the tenant context** via a `ContextVar`
6. RBAC dependency (`require_permission`) checks the role's permission
7. The route delegates to `CostService.get_summary()`
8. The SQLAlchemy tenant listener auto-appends `WHERE organization_id = :org` to every SELECT
9. The response is serialised through a Pydantic schema
10. Sensitive operations write a signed `audit_log` row (hash-chained)
11. Response returns with `X-Request-ID` and `X-Response-Time`

### Caching strategy

| Cache | Backend | TTL |
|---|---|---|
| JWT revocation list | Redis (`revoked:{jti}`) | token expiry |
| RAG query results | in-process dict keyed `(query, k)`, capped at 100 | process life |
| Pricing catalog | `functools.lru_cache` over the committed snapshot | process life |
| Dashboard aggregates | Redis (`dashboard:{org}:{name}`) | 5 min |

Three rules govern the dashboard cache, and `core/cache.py` exists to enforce them:

- **Every key is tenant-scoped.** A cache sits *in front of* the ORM tenant filter, so a
  key that was not org-scoped would serve one tenant's figures to another without the
  isolation layer ever running. `org_key()` is the only way to build a key.
- **It fails open.** Redis unreachable → a slower correct answer, never an error.
  Deliberately the opposite of the auth surface, which fails *closed*. The two are
  commented against each other so neither reads as an oversight.
- **It is invalidated on write, not just on TTL.** Actioning a recommendation changes
  the summary's pending count; waiting out five minutes would leave the KPI row
  disagreeing with what the user just did.

Measured: `/costs/summary` ~42 ms cold → ~5.5 ms warm.

### Technology choices and their rationale

| Choice | Why |
|---|---|
| **FastAPI** over Django/Flask | native async, automatic OpenAPI, Pydantic v2 validation |
| **SQLAlchemy 2.0 async** | one ORM for the whole app; the tenant listener gives defence-in-depth raw SQL could not |
| **ChromaDB** over Qdrant/Pinecone | one small container. Pinned to `0.5.23` — `:latest` dropped the v1 API the 0.5 client speaks |
| **Ollama + Qwen 2.5 3B** | privacy-by-design local inference that fits 8 GB RAM; OpenAI is an optional fallback only |
| **Prophet** over ARIMA/LSTM | robust to missing data and weekly seasonality with minimal tuning |
| **IsolationForest + Z-score** | unsupervised anomaly detection needing no labels |
| **React + Vite** over Next.js | no SSR requirement; sub-second HMR; full control of the SPA |

---

## 5. The central technical decision: the pricing-grounded simulator

**This is the heart of the project and should be the heart of the report.**

### The constraint

No Azure credits remained. Real cloud billing data was off the table.

### The finding that forced the decision (14 July audit)

The README told users to set `DEMO_MODE=false` and connect real cloud accounts. But in
all three adapters, the *non-demo* branch of `get_billing` and `get_metrics` simply
called the mock generator:

```python
# cloud/azure_adapter.py  (before)
return await asyncio.to_thread(lambda: self._mock_billing(start, end))
```

**Consequence:** connecting a real Azure subscription produced a *real resource
inventory* joined to *fabricated billing and fabricated CPU/memory metrics*. The
CostAgent would raise "unusual spend" alerts and the RightSizingAgent would recommend
downsizing real VMs — all computed from invented numbers, with confidence scores
attached, and nothing anywhere signalling the data was synthetic.

### The reframing

The instinct was "make the fake data better". That was the wrong goal.

The adapters fabricated **two** things: *usage* (which VM ran, for how long) and *price*
(the dollar figure). Fabricating usage is fine — that is what a simulator is.
Fabricating **price** is what made the numbers indefensible.

So the goal became:

> **synthetic usage × real published pricing = defensible cost**

And the key discovery: real published pricing is **free and keyless**. No cloud account,
no subscription, no spend.

### Options considered

| Option | Verdict |
|---|---|
| **A. Pricing-grounded simulator** — synthesise usage, price it from public rate-card APIs | **Chosen.** Highest payoff; makes every number traceable |
| **B. LocalStack** — run the real boto3 path against an AWS-compatible API | Deferred. Proves the adapter code works, gives no billing |
| **C. Replay FOCUS / AWS CUR sample datasets** | Deferred. Real-shaped, but someone else's fleet — won't line up with the seeded estate |
| **D. OpenCost on a local kind cluster** | Rejected. Most "real", but too heavy for an 8 GB M1 where Ollama already takes ~5 GB |

### Verifying the rate-card APIs

Both confirmed working with **no authentication**:

- **Azure Retail Prices API** — `https://prices.azure.com/api/retail/prices`, OData-filterable, JSON, HTTP 200 with no credentials.
- **AWS Price List** — per-service, per-region bulk JSON offer files. HTTP 200, but **18–100+ MB per file**.

Two non-obvious traps found and handled:

1. **Azure returns six meters per VM SKU** (Linux/Windows × on-demand/low-priority/spot). Only the plain Linux on-demand meter is what a steady-state workload pays.
2. **Azure bundles storage and operations meters under one product.** A naive `min()` over "Hot LRS" returned **$0.0027/GB-month** — an *operations* meter — instead of the real **$0.0196/GB-month** data-at-rest rate. A ~7× under-pricing, caught and fixed with an exact meter-name filter.

The change also **corrected real numbers**, not merely re-sourced them:

| SKU | Fetched rate | Old hardcoded value |
|---|---|---|
| `Standard_D2s_v3` | **$0.12/hr** | $0.096 |
| `Standard_D4s_v3` | **$0.24/hr** | $0.192 |
| `Standard_D8s_v3` | **$0.48/hr** | $0.384 |

The old catalog held stale US-East figures.

### What was built

**`cloudpilot/pricing/` — the rate card**

| File | Purpose |
|---|---|
| `models.py` | `Price` with explicit **unit** (`HOUR`/`GB_MONTH`), **provenance** (`PriceSource`), currency, as-of date |
| `sources.py` | Fetchers for the Azure Retail API and the AWS Price List; transcribed list prices where no keyless API exists |
| `catalog.py` | The catalog + the `DOWNSIZE_MAP`. Refuses to return a downsize target it cannot price |
| `refresh.py` | CLI: `python -m cloudpilot.pricing.refresh` |
| `data/pricing_snapshot.json` | The committed, pinned rate card |

Three design decisions worth defending in the report:

- **Unit is explicit.** Compute is billed per hour, storage per GB-month. The old model assumed `hourly × 730` for everything, silently mis-pricing storage by ~730×.
- **Provenance is explicit.** Every rate is flagged `azure_retail_api`, `aws_price_list`, or `published_list_price`. GCP's Cloud Billing Catalog API needs an API key, so GCP rates are transcribed and **honestly flagged rather than passed off as API-verified**.
- **The snapshot is committed, not fetched at import.** The demo must work offline, the AWS files are huge, and a pinned rate card makes the seeded dataset reproducible.

**`cloudpilot/simulation/` — the estate**

| File | Purpose |
|---|---|
| `fleet.py` | 50 resources as a *physical* description: node counts, gigabytes, region, SKU, `UsageProfile`. **Carries no prices** |
| `engine.py` | Usage curves, physical events, and costing. The only place a dollar figure is produced |

The `UsageProfile` set is chosen so the fleet contains exactly what the agents should find:

- `OVERSIZED` — low P95 CPU/RAM. RightSizingAgent **should** flag these.
- `BURSTY` — low mean, **high P95**. RightSizingAgent must **not** flag these; they exist to catch false positives. Downsizing them would throttle a batch job.
- `DEV` — idle nights and weekends. Produces the weekday/weekend shape in the charts *as a consequence of behaviour*, replacing an arbitrary `1.2 weekday / 0.85 weekend` fudge factor.
- `STEADY` — healthy production baseline.

### Anomalies became physical, not arithmetic

This is the single most quotable change in the project.

```python
# before — mock_data.py
if res.id == aks_prod.id and anomaly1_start <= day < ...:
    cost *= 4.4   # +340%
```

```python
# after — simulation/engine.py
FleetEvent(
    resource_name="aks-prod-cluster",
    days_ago=45, duration_days=3,
    quantity_factor=4.5,          # 4 nodes -> 18
    cause="A misconfigured HPA target drove the cluster autoscaler from 4 to 18 "
          "nodes and it stayed scaled out for three days...",
)
```

The cost delta is now **derived**: 14 extra nodes × $0.24/hr × 24h = **$80.64/day**,
exactly. The CostAgent's root-cause explanation is therefore *true of the estate it is
describing*.

### The seeder stopped fabricating recommendations

The old seeder hardcoded 8 recommendations with invented savings ($2,400, $890, $485…)
— a **second fabrication layer** feeding the UI directly. Two even referenced
`compute-engine-02`, a resource that no longer existed and would have crashed the seed.

`make seed` now builds the estate and then **runs the real CostAgent, RightSizingAgent
and ForecastAgent against it**. Each runs inside a savepoint (`db.begin_nested()`) — a
bug caught during self-review: a bare `db.rollback()` on agent failure would have
discarded the entire seeded estate.

### One shared simulation source

The three adapters each carried their own `_mock_*` generators, which disagreed with the
seeder **and with each other** — the seeder created `vm-analytics-01` while the Azure
adapter invented `virtual-machine-00`, and billing was a flat `rng.uniform(120, 380)`.
A sync after a seed therefore replaced a coherent estate with unrelated noise.
`cloud/simulated.py` is now the single source for all paths, so a sync is idempotent
against a seed.

### The live branches stopped lying

```python
async def get_billing(self, start, end):
    if self.demo_mode:
        return simulated_billing("azure", start, end)
    raise NotImplementedError(
        "Live Azure billing is not implemented. Wire CostManagementClient.query.usage() "
        "here. Until then, set DEMO_MODE=true — returning simulated costs for a real "
        "subscription would make the agents raise anomalies against figures that were "
        "never billed."
    )
```

### Verification results

**Right-sizing — no misses, no false positives:**

```
FLAG vm-analytics-01   oversized  P95 cpu=24.9 mem=45.5   ok
     vm-api-01         steady     P95 cpu=69.6 mem=73.3   ok
     vm-batch-01       bursty     P95 cpu=93.4 mem=86.2   ok   <- correctly NOT flagged
FLAG aks-analytics     oversized  P95 cpu=25.0 mem=45.1   ok
```

All 11 `OVERSIZED` resources flagged; every `STEADY` and `BURSTY` resource left alone.

**The estate, priced from real rate cards:**

| Provider | Monthly run-rate |
|---|---|
| Azure | $4,747 |
| AWS | $1,487 |
| GCP | $1,355 |
| **Total** | **$7,589/mo** (50 resources) |

**Identified savings: $1,369/month — 18% of spend**, in line with FinOps benchmarks.

Prophet's month-end projection (**$8,358.56**) independently cross-checks the API's
linear projection (**$8,364.68**) — two different methods, same answer.

### Net effect

**437 lines added, 808 deleted.** The change removed more code than it added, by
collapsing three duplicated fake-data generators into one.

---

## 6. Security design

Security is stated as priority #2 (above UI) because CloudPilot handles cloud
credentials for enterprise clients.

### Six principles

1. **Least privilege** — read-only IAM roles; there is no write API to any cloud.
2. **Defence in depth** — independent trust boundaries; RBAC *and* an ORM tenant filter.
3. **Zero trust** — every request authenticated, every query tenant-scoped.
4. **Secure by default** — all endpoints require JWT unless explicitly public.
5. **Fail closed** — auth failure → 401, permission failure → 403; never silent.
6. **Privacy by design** — local LLM default, no telemetry, minimal PII.

### Trust boundaries

```
Internet
  ↓  TLS 1.2/1.3, HSTS, WAF, rate limiting (nginx)
Reverse proxy
  ↓  security-headers + request-id middleware
Auth middleware      JWT verify (HS256, aud pinned), jti revocation, brute-force lockout
  ↓
RBAC middleware      role → permission matrix
  ↓
Business logic       SQLAlchemy tenant filter (auto org_id scoping)
  ↓
Data + AI            Fernet-encrypted credentials at rest, local LLM
  ↓
Cloud providers      read-only IAM roles
```

### Authentication

- **Access token** — HS256 JWT, 60-min TTL, claims `{sub, org, role, jti, iat, exp, aud}`. The algorithm whitelist rejects `none` and asymmetric algorithms; `aud` is pinned. Stored **in browser memory only** — never `localStorage`.
- **Refresh token** — opaque 64-hex string (not a JWT), 7-day TTL, HttpOnly + Secure + SameSite=Strict cookie. Rotated on every use; the old token consumed atomically in Redis.
- **Revocation** — on logout the `jti` goes into a Redis set with a TTL matching its remaining lifetime.
- **Brute force** — 5 failed logins / 5 min / IP → 429; 10 failures / email / hour → 423 Locked.

### Two-layer tenant isolation — the architectural centrepiece

Roles: `admin` > `analyst` > `viewer`.

- **Layer 1** — the `require_permission` dependency against a permission matrix in `core/rbac.py`.
- **Layer 2** — a SQLAlchemy `do_orm_execute` listener (`core/tenant.py`) that appends `WHERE organization_id = :current_org` to every SELECT against an entity declaring that column.

**All ten org-scoped models now carry the column:** `user`, `cloud_account`,
`recommendation`, `chat_session`, `forecast_snapshot`, `agent_run_log`, `audit_log`,
plus — since migration `004` — `resource` and `billing_entry`, and — since `005` —
`metric_sample`.

**The redundancy is the point.** A service that forgets to scope its query, or scopes it
to the wrong tenant, still cannot read another organization's rows. Demonstrated live:

```
resources listed (correct bound org):     50
resources under WRONG bound org:           0   <- listener overrides service filter
```

`ResourceService.list_resources()` was called with org A's id — its own explicit filter
was correct — and still returned nothing because the ambient context said otherwise.

**A deliberate third case: the scheduler.** It has no request lifecycle, so nothing binds
the ContextVar and the listener is a no-op for every query it makes. The agents take
`organization_id` as a parameter and filter explicitly. This is documented as
deliberate so it is not "fixed" later.

### Startup secrets guard

`Settings._guard_secrets` refuses to construct the settings object — so the app cannot
boot — when `APP_ENV=production` and any of `JWT_SECRET`, `APP_SECRET_KEY` or
`FERNET_MASTER_KEY` is empty or still at its placeholder. The error names exactly which.

This closes a specific hole: an empty `FERNET_MASTER_KEY` fell back to a key derived
from a **source-code constant**, so anyone holding the repo could decrypt every stored
cloud credential. A *malformed* key is rejected in **every** environment, dev included.

### Audit log integrity

`audit_log` is append-only. Each row stores `signature = SHA-256(prev_sig + canonical_row)`,
chaining from a 64-zero genesis. `GET /admin/audit-log/verify` recomputes the chain; any
retroactive edit breaks every subsequent signature.

### Compliance mapping

| Standard | Status | Coverage |
|---|---|---|
| OWASP ASVS 4.0 L2 | Aligned | auth, session, access control, validation |
| NIST SP 800-53 (Moderate) | Aligned | AC, AU, IA, SC families |
| ISO 27001:2022 | Partial | A.5, A.8, A.9 controls |
| GDPR | Aligned | data minimization, local processing, no telemetry |

---

## 7. Chronological journal

**This section is the raw material for the *journal de stage*.** Each entry gives the
date, what was attempted, what was found, and what changed.

### Commit distribution

| Date | Commits | Session |
|---|---|---|
| 22 June 2026 | 1 | Initial scaffold |
| 14 July 2026 | 6 | Audit + pricing-grounded simulator + first live run |
| 15–16 July 2026 | 2 | Cost-by-region fix; production secrets guard |
| 20 July 2026 | 10 | Hardening pass + tenant isolation layer 2 |
| 25 August 2026 | 28 | Demo-readiness hardening + carried-forward gap closing |
| 31 August 2026 | 8 | Pricing provenance in the UI + e2e suite |
| **Total** | **55** | |

---

### 22 June 2026 — Initial scaffold

One commit establishing the full five-layer structure: FastAPI backend, React/Vite SPA,
four AI agents, read-only cloud adapters, Docker Compose stack (Postgres, Redis,
ChromaDB, Ollama, Prometheus, Grafana). ~14k lines.

---

### 14 July 2026 — Audit, the pricing simulator, and the first end-to-end run

The largest single session. Three parts.

**Part 1 — a full audit of the codebase.**

What was genuinely strong:
- Layering clean and consistently applied — routes thin, services hold logic, agents behind an `AgentBase` contract.
- Config fully type-safe via pydantic-settings; nothing reads `os.environ` directly.
- Security primitives centralised; the JWT decode correctly pins an algorithm whitelist and audience — the thing most projects get wrong.
- A ContextVar-based tenant filter and a SHA-256 hash-chained audit log. Rare at this level.

What the audit found:

| Severity | Finding |
|---|---|
| **High** | Fernet fallback key derived from a source constant — anyone with the repo could decrypt stored cloud credentials |
| **High** | `JWT_SECRET` defaults to a placeholder; no startup guard |
| Medium | Redis failure silently disabled auth protections (`is_revoked` returned `False` on error) |
| Low | `/metrics` unauthenticated |
| **Structural** | **The adapters never fetched real data** — the non-demo branch called the mock generator |

Correctness findings: the LLM fabricated when Ollama was down *and it looked real*; the
tenant filter only covered one entity per query; `ForecastAgent` hardcoded a $45,000
budget; the Ollama volume was a machine-specific path; `qwen2.5:4b` was probably not a
real tag.

Process findings: tests were thin (four files, all pure unit tests — **nothing tested an
API route, RBAC, or tenant isolation**, the very claims the architecture is built
around); CI ran mypy and ESLint with `continue-on-error: true`, so strict type-checking
was advisory only; git history was a single commit with 10 uncommitted modified files.

**Part 2 — the pricing-grounded simulator.** Fully described in §5.

**Part 3 — actually running the stack.** Six containers up, migrations `001 → 002 → 003`,
`make seed` against a real database for the first time, every endpoint driven.

| Check | Result |
|---|---|
| Containers | 6/6 up, postgres/redis/backend healthy |
| Seed | 50 resources, **$24,185 billed over 90 days** |
| Agents | **All four produce real output** — nothing hardcoded |
| Endpoints | 12/12 return `200`; unauthenticated → `401` |
| Audit chain | `{"intact": true}` |

**Four bugs that only running it could find:**

1. **Right-sizing under-reported every node pool** — a bug in code written earlier the same session. `Resource` had no node-count column, so a 3-node `aks-analytics` pool priced its downsize as a single node: $87.60 instead of $262.80. Invisible to static analysis — the simulation modelled node counts correctly and the agent's arithmetic was internally consistent; the two just never met. Fixed with migration `002`.
2. **`OLLAMA_MODEL=qwen2.5:4b` does not exist.** Every LLM call was returning 404.
3. **`LLM_TIMEOUT_SECONDS = 30` was far too short.** A 3B model doing RAG on CPU takes ~96 seconds, so *every* chat answer was silently routed to the offline fallback.
4. **The LLM fallback leaked the entire prompt** — it echoed the fully assembled prompt (context documents and live infrastructure data included) into the chat window, dressed up as a grounded answer **with a real citation chip attached**.

> **Bugs 2, 3 and 4 compounded.** The Cloud Advisor — a headline feature — had **never
> once produced a real model answer**, and looked like it was working the whole time:
> plausible prose, real citations, no error.

**Two audit findings confirmed live, then fixed:** ChromaDB `:latest` had drifted to a
1.0.0 server that removed the v1 API the pinned 0.5 client speaks (every connection
returned 410, and the RAG engine silently fell back to an in-memory store — the
knowledge base *looked* fine but never persisted); and the hardcoded $45,000 budget
meant ForecastAgent produced zero recommendations, since the real estate costs ~$8.4k/mo.

> **The headline lesson of the session:** the single highest-value thing done was not the
> audit and not the refactor — it was *starting the application and clicking through it*.

---

### 15–16 July 2026 — Two follow-ups

- `d3f9bac` — populated cost-by-region and fixed the production typecheck.
- `77c84de` — the production secrets guard, closing the one outright-dangerous audit finding.

---

### 20 July 2026 — Hardening pass (morning) — 6 commits

Closing the highest-priority audit items, plus an accuracy review of the AI agents.
**Two of the six briefed tasks rested on assumptions that were wrong, and are called out
rather than quietly "fixed".**

| # | Task | Outcome |
|---|---|---|
| 1 | Production secrets guard | **Already done** on 16 July. No change |
| 2 | Tenant filter multi-entity bug | **Real bug, fixed.** Narrower than described |
| 3 | Scheduler tenant context | **Not broken.** Premise wrong; added the missing proof |
| 4 | RightSizingAgent `node_count` | Correct already; regression tests added |
| 5 | CostAgent anomaly thresholds | **Clear miscalibration found, recalibrated** |
| 6 | ArchitectAgent / RAG quality | **Two real bugs, fixed** |

Backend suite: **107 tests** (was 83).

**Task 2 — why the bug survived so long.** The listener `break`s after the first entity
carrying `organization_id`. An FK-correlated join masks this: once one side is filtered,
`Recommendation.cloud_account_id == CloudAccount.id` transitively constrains the other.
Realistic service queries came back correct. Only *uncorrelated* multi-entity selects
leak — verified empirically before fixing. The regression test was written first and
confirmed **red on both leak directions**.

**Task 5 — the anomaly-gate miscalibration.** Detection groups by `(account, service)`,
so a physical anomaly on one resource arrives diluted by its siblings:

| siblings added | peak pct | z | verdict |
|---|---|---|---|
| 0 | +57.4% | 5.12 | surfaced |
| 1 | +48.4% | 5.12 | **missed** |
| 3 | +36.9% | 5.12 | **missed** |
| 5 | +29.8% | 5.12 | **missed** |

One extra comparable RDS instance makes a genuine 4× incident invisible — **while its
Z-score never moves**. The percentage was eroding with estate size even though the signal
was not. The old `pct >= 50` gate was calibrated when costs were fabricated
*arithmetically*; physical anomalies do not behave that way. Now
`pct >= 25% AND delta >= $5` — the absolute floor is what actually expresses "material".

**Task 6 — two RAG bugs.** The query cache **memoised its own failures** (a Chroma query
that threw, or an embedding that fell back to a hash stub, was cached as fresh for the
process lifetime — a transient blip left the Advisor permanently ungrounded until
restart). And retrieval had **no relevance floor**: *"What is the capital of France?"*
came back with five authoritative-looking sources about AKS node pools. Cosine distance
separates cleanly:

```
Why did my Azure costs spike last month?   0.2546
Is my Azure AKS cluster correctly sized?   0.3097
How do I reduce S3 storage costs?          0.4231
asdfgh qwerty zxcvbn                       0.5567
What is the capital of France?             0.6587
```

A `MAX_COSINE_DISTANCE = 0.55` floor now drops the rest.

---

### 20 July 2026 — Tenant isolation, second layer (afternoon) — 4 commits

Migration `004_denormalize_organization_id` adds the column to `resources` and
`billing_entries` in three steps: **add nullable → backfill from
`cloud_accounts.organization_id` → apply NOT NULL** with FK and indexes.

Step 2 **refuses to continue** if any row cannot be traced to an organization. It raises
with the count and a sample rather than defaulting — an untraceable row means the data is
already inconsistent, and picking an owner would invent a tenancy claim, precisely what
this column exists to prevent.

Applied against the dev database holding real seeded data:

| Table | Rows | Backfilled | NULL | Mismatched vs. the join |
|---|---|---|---|---|
| `resources` | 50 | 50 | 0 | 0 |
| `billing_entries` | 4292 | 4292 | 0 | 0 |

**Mutation testing on the test suite:** the listener was temporarily mutated to skip both
tables, reproducing the pre-`004` blindness exactly. **8 of 9 tests failed.** The
survivor asserts the unbound case and correctly passes either way. Mutation reverted.

Backend suite: **116 tests**.

---

### 5 August 2026 — Status audit, zero commits

A verification session, not a development one. **Headline finding: nothing had happened
since 20 July** — `HEAD` was still `0f136c1`, 16 days later.

The audit verified everything against the running system rather than the docs, and found
three things not in any prior report:

1. **Seeded `COST` recommendations were stale against the fix meant to correct them.** The 5 cost-agent recommendations in the dev database were generated at 10:04, *30 minutes before* the 10:34 anomaly-gate recalibration.
2. **The budget input on the Forecast page was non-functional, not merely unimplemented** — an editable field with no `onChange`, no state, no submit. Worse than omitting it, since it invites a click that does nothing.
3. **RBAC had zero test coverage**, despite gating five permission-sensitive endpoint groups, sitting next to a tenant-isolation suite with 18 mutation-verified tests.

---

### 25 August 2026 — Demo-readiness hardening — 17 commits

Security gaps and correctness bugs from a fresh audit, the RBAC coverage hole, and a
portability fix — followed by a **live browser walkthrough that found four more bugs the
audit and the unit tests had both missed**.

Backend: **155 tests** (was 116). Frontend: **16 tests** (was 0 meaningful coverage).

**Four security fixes:**

- **Email lockout was tracked but never enforced** — `_record_failed_login` called `check_rate_limit` and discarded the return value. Now the 11th failed attempt against one email returns `423 Locked`. Separately, `verify_password` was only reached when a user existed, so response timing revealed which emails were registered — closed with a fixed dummy hash.
- **`X-Forwarded-For` was trusted** — `client_ip()` took the first, client-suppliable value, letting an attacker reset the IP rate limiter on every request. Now prefers `X-Real-IP` (nginx sets it itself, unspoofable), falling back to the *last* segment.
- **JWT revocation failed open** — `is_revoked` returned `False` on a Redis error, contradicting the module's own documented principle. Now fails closed: **an accepted availability tradeoff**, a Redis blip costs a 401 storm instead of silently honouring revoked credentials.
- **Refresh-token TOCTOU** — GET-then-DELETE let one token be consumed twice under concurrency. Replaced with an atomic `GETDEL`.

**The Cloud Advisor: four bugs, three found only by opening a browser.**

The chat flow was driven in a real headless Chromium and **crashed on the very first
message**:

1. `citations_json`/`tool_calls_json` are nullable ORM columns. The response schema's `default_factory=list` only fills a field that is *absent*, not one explicitly `None`. Every chat session containing such a message **500'd on GET**.
2. The seeder never set `tool_calls_json` at all, so all 3 seeded demo conversations were broken by bug 1 **out of the box**.
3. The schema used `alias=` to map the ORM attribute. **FastAPI serialises response models by alias by default** — so once bug 1 was fixed, the API was still sending `citations_json` as the JSON key, while the frontend type reads `citations`. Every assistant reply crashed `ChatBubble`.

> **The headline finding of the session:** three of these four bugs were invisible to
> code review and to unit tests, and would have crashed the chat page in front of the
> supervisor on the very first demo click.

**Backend/AI correctness:** CostAgent's anomaly dedup key was `(service, date)` with no
account, so two accounts with an anomaly in the same service on the same day collided;
`pricing/sources.py`'s docstring promised graceful degradation the Azure fetchers did not
have; `forecast_agent.py`'s MTD filter matched on month number with no year.

**Frontend:** the first message in any new chat posted to the **wrong session** —
`useSendMessage(activeId ?? "")` bound the mutation's target at render time. Plus five
smaller fixes: honest (disabled) budget controls, dead store state removed, a top-level
`ErrorBoundary` (its first real catch was the chat crash above), confirm dialogs on
destructive deletes, and `useAuth()` selecting individual fields instead of subscribing
to the whole store.

**RBAC: zero → 12 mutation-verified tests.** The suite's first HTTP-level test client
(`httpx.AsyncClient` over `ASGITransport`) rather than only unit-testing
`role_has_permission` — a unit test cannot catch a route that forgot to apply the guard
at all. **`users.manage` gates no endpoint anywhere in the codebase** (confirmed by
grep), covered as a direct unit test instead and called out explicitly.

---

### 25 August 2026 (b) — Closing the carried-forward gaps — 8 commits

Backend: **189 tests**. **mypy: 94 errors → 0** across all 85 files.

| # | Item | Outcome |
|---|---|---|
| 1 | Budget-setting had no write path | **Done** — and the read path was wrong too |
| 2 | `metric_samples` single-layer isolation | **Done** — migration `005` |
| 3 | `CACHE_DASHBOARD_TTL` defined but unused | **Done** — Redis cache |
| 4 | RAG corpus stuck at 7 chunks | **Done** — 23 chunks, and ingestion can now pick up a change |
| 5 | ~80 mypy errors | **Done** — zero |
| — | *(new)* CI's ruff job was red | **Fixed** — 24 pre-existing violations |
| — | *(new)* Ollama was saturating the machine | **Fixed** |

**The budget contradiction.** `ForecastService` had `_DEFAULT_BUDGET = 45_000.0`
hardcoded while `ForecastAgent` read the real per-tenant column. On the seeded demo
(**$7,500/month**) that put two screens in direct contradiction:

- **Recommendations page**: *"this month projects to $8,277 (10% over the $7,500 budget)."*
- **Forecast page**: budget **$45,000**, verdict **"Within budget"**.

Same data, same month, opposite answers, on adjacent pages. Neither the audit nor the
test suite caught it because **each side was internally consistent** — it only shows up
when you read both screens together.

The budget is now nullable end to end rather than falling back to a number nobody chose.
Making it nullable immediately caught a second spot: the forecast chart's budget
reference line, which would have drawn at 0 and read as a budget of zero that all spend
overruns.

**Migration `005`** closes the last single-layer table. `metric_samples` is
RANGE-partitioned by month, so all DDL is applied to the parent — Postgres propagates
`ADD COLUMN`, `SET NOT NULL` and `CREATE INDEX` to every partition. Verified against
**24,864 rows across 6 partitions**. The revision id had to be abbreviated because
`alembic_version.version_num` is `VARCHAR(32)` and the descriptive name was 34
characters — it fails on the version bump *after* the DDL has run, caught on the first
attempt and only harmless because Postgres transactional DDL rolled it back cleanly.

**The RAG corpus grew 7 → 23 chunks — but growing it alone would have changed nothing.**
`ingest()` skipped whenever the collection was non-empty, making the corpus
**effectively immutable after first boot**. It now compares the stored count against the
corpus it would write and re-ingests on a mismatch.

**Ollama was cooking the machine.** Docker Desktop passes **no GPU through on Apple
Silicon**, so the containerised Ollama runs the 3B model on pure CPU with no resource
limits. Measured on an 8-core M-series machine:

| | |
|---|---|
| One RAG answer, 256 output tokens | **462 s** |
| Same request through the API | 187 s, i.e. **past the 180 s timeout** |
| Whole stack idle, Ollama stopped | ~3.4% CPU, ~520 MB |

So the Advisor was paying the full CPU cost of a request and *still* falling back,
because the answer arrived after the client had given up.

---

### 31 August 2026 — Provenance on screen, and a committed e2e suite — 8 commits

Backend: **199 tests**. Frontend: **36 unit tests** + a new **15-test Playwright suite**.

**Pricing provenance in the UI.** The backend had tracked per-rate provenance since July
and none of it reached a screen. Two surfaces now expose it:

A collapsed *"How this saving was calculated"* disclosure on each recommendation:

```
Standard_D4s_v3   $0.2400/hr   [Azure Retail API]   westeurope
     ↓ downsize to
Standard_D2s_v3   $0.1200/hr   [Azure Retail API]   westeurope
($0.2400/hr − $0.1200/hr) × 730 h × 3 nodes = $263/month
Rates quoted as of 14 Jul 2026.
```

And a rate card at Settings → Pricing: all 23 SKUs with rate, region, source and meter,
plus snapshot-level provenance (age, staleness, API-verified share).

**The e2e suite.** 15 Playwright specs, `make e2e`. Every spec corresponds to a bug that
reached a running app and that no unit test could have caught. It refuses to run against
a half-up stack — `global-setup.ts` checks `/health` first and fails with the exact
commands to run.

**Four new defects found, three of them *because* the provenance work put data on screen:**

1. **`metadata` never reached clients under the name anything read.** `alias=` vs `validation_alias=` again — the same class of bug as the chat serialisation issue in August. Every recommendation had been carrying its pricing provenance to a key no client looked at.
2. **All 15 transcribed rates cited the wrong pricing page.** Every AWS SKU — EC2, RDS, ElastiCache included — cited `aws.amazon.com/s3/pricing`. Latent while nothing displayed the field; wrong the moment the rate card did.
3. **The session bootstrap raced itself.** React StrictMode double-invokes effects, refresh tokens are single-use, so the losing call reported the user as signed out — and every reload or deep link silently dumped the user on the Overview. **Found by the e2e suite on its first run.**
4. **CI never ran the frontend unit tests**, and `pnpm test` was watch-mode, which would have hung the job.

---

## 8. Technical inventory

### Code volume

| Area | Files | Lines |
|---|---|---|
| Backend source | 87 `.py` | 8,889 |
| Backend tests | 29 files | 3,463 |
| Frontend source | 77 `.ts`/`.tsx` | 6,127 |
| Frontend e2e | 6 files | 359 |

### Database

**12 models:** `organization`, `user`, `cloud_account`, `resource`, `billing_entry`,
`metric_sample`, `recommendation`, `forecast_snapshot`, `chat_session`, `chat_message`,
`agent_run_log`, `audit_log`.

**5 migrations:**

| Migration | What it does |
|---|---|
| `001_initial_schema` | The full schema |
| `002_resource_node_count` | `resources.node_count` — pools were under-priced by node count |
| `003_org_monthly_budget` | `organizations.monthly_budget_usd`, nullable |
| `004_denormalize_organization_id` | The column onto `resources` + `billing_entries` |
| `005_metric_samples_org_id` | The column onto the partitioned `metric_samples` |

`metric_samples` is RANGE-partitioned by month.

### API — 35 endpoints across 9 routers

| Router | Endpoints |
|---|---|
| `auth` | 5 — register, login, refresh, logout, me |
| `cloud_accounts` | 6 — CRUD + test + sync |
| `resources` | 3 — list, tree, detail |
| `costs` | 5 — summary, breakdown, timeseries, top-drivers, anomalies |
| `recommendations` | 3 — list, savings, status update |
| `forecast` | 3 — forecast, get budget, set budget |
| `pricing` | 1 — catalog |
| `chat` | 5 — session CRUD + messages |
| `admin` | 4 — audit log, verify, agent runs, trigger agent |

Plus `/health` and `/metrics` (Prometheus).

### The rate card — 23 SKUs

| Provider | SKUs | Source |
|---|---|---|
| Azure | 8 | `azure_retail_api` (API-verified) |
| AWS | 9 | `published_list_price` (transcribed) |
| GCP | 6 | `published_list_price` (transcribed) |

**34.8% API-verified.** Regions: `westeurope`, `eu-west-1`, `europe-west1`.
Snapshot as of 14 July 2026.

### RAG corpus — 23 entries

12 provider-agnostic (budgets and forecasting, investigating a cost spike, rightsizing
method, idle and orphaned resources, commitment discounts, tagging and allocation,
storage tiering, network egress, Kubernetes cost allocation), 4 Azure, 4 AWS, 3 GCP.

### Stack

| Layer | Technology |
|---|---|
| Frontend | React 18.3, TypeScript 5.4, Vite 5.2, Tailwind 3.4, Radix UI, TanStack Query 5.40, Zustand 4.5, Recharts 2.12, Framer Motion 11 |
| Backend | FastAPI 0.110, Pydantic v2.6, SQLAlchemy 2.0 (async), asyncpg, Alembic 1.13, APScheduler 3.10, PyJWT, bcrypt, cryptography (Fernet), loguru, prometheus-client |
| AI/ML | LangChain 0.2, Ollama 0.2 (Qwen 2.5 3B + nomic-embed-text), ChromaDB 0.5.23, Prophet 1.1, scikit-learn 1.5, numpy, pandas |
| Cloud SDKs | azure-mgmt-{costmanagement,monitor,compute}, azure-identity, boto3, google-cloud-{billing,monitoring} |
| Data | PostgreSQL 16, Redis 7, ChromaDB |
| Infra | Docker Compose (9 services), nginx, Prometheus, Grafana, GitHub Actions |
| Tooling | Poetry, pnpm, ruff, mypy, ESLint, pytest, Vitest, Playwright |

### Test coverage

| Suite | Count | Notes |
|---|---|---|
| Backend | **199** | 149 run anywhere; 50 need `CLOUDPILOT_TEST_DB` |
| Frontend unit | **36** | Vitest + Testing Library, jsdom |
| End-to-end | **15** | Playwright, against a live stack |

Notable suites: `test_tenant_isolation*.py` (three files, mutation-verified),
`test_rbac.py` (12 tests, mutation-verified), `test_pricing*.py`,
`test_scheduler_isolation.py`, `test_config.py`.

---

## 9. The bugs worth telling

A shortlist for the report — each illustrates a different *class* of failure.

| # | Bug | Class | Why it matters |
|---|---|---|---|
| 1 | Adapters returned mock billing in "live" mode | **Design dishonesty** | Real inventory + fake costs = agents raising alerts against spend that never happened |
| 2 | Cloud Advisor had never produced a real answer | **Compounding failures that look like success** | Wrong model tag + too-short timeout + a fallback dressed as a grounded answer |
| 3 | Node pools priced as a single node | **Two correct components that never met** | Simulation modelled node counts; the agent's arithmetic was internally consistent |
| 4 | Anomaly gate missed a real 4× incident | **Calibration drift after a data-model change** | The gate was tuned for arithmetic anomalies; physical ones dilute differently |
| 5 | RAG cache memoised its own failures | **Caching a failure as a success** | A transient blip left the Advisor permanently ungrounded until restart |
| 6 | Retrieval had no relevance floor | **Confident wrong answers** | "Capital of France?" returned five sources about AKS node pools |
| 7 | Forecast/Recommendations disagreed on the budget | **Two internally-consistent screens** | $45,000 vs $7,500 on adjacent pages; no single-screen test could see it |
| 8 | `alias` vs `validation_alias` (chat, then recommendations) | **Framework default nobody reads** | FastAPI serialises by alias; the same bug recurred two months apart |
| 9 | Session bootstrap raced itself | **Interaction between two correct designs** | Single-use refresh tokens + StrictMode double-invoke = lost deep links |
| 10 | Every transcribed rate cited the wrong page | **Latent until displayed** | Harmless while hidden; wrong the moment the UI showed it |

---

## 10. Methodology and engineering practices

Worth a dedicated section in the report — these are transferable practices, not
project trivia.

### Running the application is not optional

The single most repeated lesson. Three separate sessions found bugs that **static
analysis and the unit-test suite had both missed**, and in each case the bug was in a
headline feature that appeared to be working:

- 14 July — the Cloud Advisor had never once produced a real answer.
- 25 August — the chat page crashed on the very first message; three of the four bugs were invisible to code review.
- 31 August — the session bootstrap race, found by the e2e suite on its first run.

### Mutation testing to prove tests have teeth

A test that passes proves nothing until you have seen it fail for the right reason.
Applied systematically:

- Tenant isolation — mutated the listener to skip both tables: **8 of 9 tests failed**.
- RBAC — inverted `role_has_permission`: **all 12 went red**.
- `metric_samples` isolation — skipped `MetricSample` in the listener: **4 of 5 red**, with the join case leaking 6 rows where 3 were in-tenant.
- `node_count` — dropped the `* nodes` multiplier: **2 of 4 failed**.

### Writing the regression test first, and confirming it red

The tenant-filter multi-entity fix had its regression coverage written *before* the fix,
and confirmed failing on both leak directions.

### Correcting the brief rather than silently complying

Two of the six tasks briefed on 20 July rested on wrong premises — the scheduler was not
broken, and the example given for the tenant-filter bug did not apply. Both were called
out explicitly in the report rather than "fixed". This matters: quietly implementing a
fix for a non-problem adds a second, invisible source of truth.

### Honest failure modes as a design principle

A recurring theme, stated as an invariant across the codebase:

- Live billing raises `NotImplementedError` rather than returning simulated figures.
- The LLM fallback states plainly that the model was unavailable, and never echoes the prompt.
- Retrieval returns no citations rather than irrelevant ones.
- A budget nobody set reads "Not set", not `$0` and not `$45,000`.
- A rate with no recorded provenance shows "source not recorded", not a blank badge.
- A downsize that cannot be priced is never recommended.

### Fail-closed vs fail-open, decided per surface

Deliberately opposite choices, commented against each other so neither reads as an
oversight: the **auth surface fails closed** (a Redis blip costs a 401 storm rather than
honouring revoked tokens), the **dashboard cache fails open** (a Redis blip costs
latency, never an error).

### Migrations that refuse to guess

The `004` and `005` backfills stop and report if any row cannot be traced to an owner,
rather than defaulting. An untraceable row means the data is already inconsistent, and
picking an owner would invent a tenancy claim.

### Documenting the *why*, in the code and in session reports

Every session produced a report recording not just what changed but what was found, what
was wrong in the brief, and what was deliberately left. Seven reports, ~1,700 lines.
Constants carry the evidence for their values at the definition site.

---

## 11. Current state

**Everything in the Quick Start works end to end in demo mode.**

| Area | Status |
|---|---|
| Demo mode (`DEMO_MODE=true`) | ✅ Complete — the intended way to run this today |
| Cost tracking, agents, RAG advisor, forecasting | ✅ Working against the simulated estate |
| Auth, RBAC, audit chain | ✅ Implemented and tested; production boot guarded against placeholder secrets |
| Tenant isolation | ✅ Two independent layers over **every** org-scoped model |
| Live resource inventory | ⚠️ Azure and AWS implemented but lightly exercised; **GCP is a stub** |
| Live billing + metrics (all providers) | ❌ `NotImplementedError` by design |
| Budget setting | ✅ `GET`/`PATCH /api/v1/forecast/budget`, admin-only, audited |
| Dashboard caching | ✅ Redis-backed, tenant-scoped, invalidated on write |
| Pricing provenance in the UI | ✅ Per-recommendation derivation + full rate card |
| Frontend e2e tests | ✅ Committed Playwright suite; not in CI |
| Backend tests on the host | ⚠️ Need Python 3.11; run in the container |

**Quality gates, all green as of 31 August:**

```
ruff check .                       clean
mypy cloudpilot                    0 issues, 87 files
pytest                             199 passed
pnpm test                          36 passed
pnpm typecheck / lint / build      clean
make e2e                           15 passed
```

The last CI run on PR #1 was green on both jobs. **The CI/CD workflows are currently
disabled manually** (`gh workflow disable`), reversible with `gh workflow enable`.

---

## 12. What remains open

Listed honestly, with the reason each is open.

1. **Live multi-cloud billing and metrics — not implemented for any provider.** The adapter methods raise `NotImplementedError` by design. Implementing them needs real cloud credentials to test against; writing them blind would reintroduce exactly the "presenting invented figures as a real invoice" risk the design exists to avoid. **This is the single largest functional gap.**
   - Entry points, if resumed: Azure → `CostManagementClient.query.usage()` and `MonitorManagementClient.metrics.list()`; AWS → Cost Explorer `get_cost_and_usage()` and CloudWatch `get_metric_statistics()`; GCP → the BigQuery billing export and Cloud Monitoring `list_time_series()`.
2. **GCP live resource inventory is also a stub** — `Compute Engine aggregatedList()` was never wired. Azure and AWS have it.
3. **The e2e suite is not in CI** — it needs a running stack (Postgres, Redis, the API). `make e2e` locally is the supported path.
4. **The rate card snapshot is 47 days old.** Not stale by the 90-day window, but `make pricing` would refresh it and could raise the API-verified share above 34.8%.
5. **Backend tests need Python 3.11 on the host** — 3.14 has no scikit-learn/prophet wheels, so `poetry install` never completes. Run them in the container.
6. **Redundancy is not self-enforcing** — nothing stops a future write path setting an `organization_id` that disagrees with its `cloud_account_id`. A composite FK or a periodic consistency check would close that.
7. **`users.manage` gates no endpoint** anywhere in the codebase.

---

## 13. Angles for the written report

Suggestions for structuring the *rapport de stage* around this material.

### The strongest narrative thread

**"Making numbers defensible."** Nearly every significant decision in the project
reduces to one question: *can you defend this figure in a room?* It connects:

- the pricing-grounded simulator (don't invent prices),
- physical rather than arithmetic anomalies (the cause is real),
- provenance tracked per rate (say where it came from),
- provenance surfaced in the UI (let a reviewer check it),
- honest failure modes (say "unavailable" rather than fabricate),
- the two-layer tenant isolation (prove the data is yours).

This is a much better spine than a feature list.

### A possible French chapter structure

| Chapter | Source in this document |
|---|---|
| **1. Contexte et problématique** | §2 — the 32% / 78% figures, retrospective vs proactive |
| **2. État de l'art / positionnement** | §4 technology rationale, §5 options considered |
| **3. Architecture de la solution** | §4 — five layers, request lifecycle, agent model |
| **4. Contribution principale : le simulateur ancré sur les prix réels** | §5 in full — this deserves its own chapter |
| **5. Sécurité et isolation multi-tenant** | §6 — two layers, migrations 004/005, mutation testing |
| **6. Intelligence artificielle : les quatre agents** | §3 agents table, §7 anomaly recalibration, RAG fixes |
| **7. Démarche qualité et méthodologie** | §10 — the transferable practices |
| **8. Résultats et validation** | §8 inventory, §11 current state, verification figures throughout §5 and §7 |
| **9. Limites et perspectives** | §12 |

### Numbers that carry weight in a defence

- **$80.64/day** — the derived anomaly cost (14 nodes × $0.24/hr × 24h)
- **$7,589/month** across 50 resources, **$1,369/month identified savings (18%)**
- **$0.0027 vs $0.0196** — the 7× storage mis-pricing trap
- **8 of 9** tests failing under mutation — proof the isolation tests have teeth
- **94 → 0** mypy errors
- **7 → 23** RAG corpus chunks
- **462 seconds** for one CPU-only RAG answer on Apple Silicon
- **199 + 36 + 15** tests

### Things worth being candid about

A report that states its limits is stronger than one that hides them. The three worth
foregrounding:

1. **Live billing is not implemented, deliberately** — and the reasoning is a *design* argument, not an excuse: returning simulated costs for a real subscription would make the agents raise anomalies against spend that never happened.
2. **The demo runs on simulated usage.** But the *prices* are real, and that is the distinction the whole project rests on.
3. **Several headline features were broken for weeks while appearing to work.** Saying so, and explaining what practice now catches it, is a stronger engineering story than claiming it always worked.

### For the *journal de stage*

§7 is already chronological. Each dated entry gives: what was attempted, what was found,
what changed, and the test count at the end — enough to expand into daily or weekly
entries. Note the two gaps in activity (20 July → 25 August) which the 5 August status
audit records explicitly.

---

## 14. Glossary FR/EN

| English | Français | Meaning in this project |
|---|---|---|
| FinOps | FinOps / gestion financière du cloud | The discipline of managing cloud spend |
| Rate card | grille tarifaire | The table of published prices per SKU |
| Provenance | provenance / traçabilité | Where a rate came from and when |
| SKU | référence / SKU | A billable product identifier (e.g. `Standard_D4s_v3`) |
| Meter | compteur de facturation | The provider-side identifier a rate is billed under |
| Right-sizing | dimensionnement / redimensionnement | Matching resource size to actual utilisation |
| Multi-tenant | multi-locataire | One deployment serving several isolated organisations |
| Tenant isolation | cloisonnement des locataires | Guaranteeing one org cannot read another's data |
| RBAC | contrôle d'accès basé sur les rôles | Role → permission matrix |
| Defence in depth | défense en profondeur | Independent, redundant security layers |
| Fail closed / fail open | échec sécurisé / échec permissif | Deny vs allow when a check cannot run |
| Audit chain | chaîne d'audit | Hash-chained append-only log |
| Mutation testing | test par mutation | Deliberately breaking code to prove tests detect it |
| Regression test | test de non-régression | A test pinning a fixed bug |
| End-to-end (e2e) | test de bout en bout | Driving the real app in a browser |
| Anomaly detection | détection d'anomalies | Finding abnormal spend |
| Baseline | référence / ligne de base | The expected value an anomaly is measured against |
| Z-score | score Z / cote Z | Standard deviations from the mean |
| P95 | 95ᵉ centile | The value 95% of samples fall below |
| Forecast horizon | horizon de prévision | How far ahead a projection runs (30/60/90 days) |
| RAG | génération augmentée par récupération | Retrieval-Augmented Generation |
| Embedding | plongement vectoriel | Vector representation of text |
| Cosine distance | distance cosinus | Similarity measure between embeddings |
| Chunk | fragment / segment | One indexed piece of the knowledge base |
| Citation | citation / source citée | The source a generated answer points to |
| Snapshot | instantané | A pinned, committed copy of data |
| Stale | périmé / obsolète | Older than its freshness window |
| Migration | migration de schéma | A versioned database schema change |
| Backfill | remplissage rétroactif | Populating a new column for existing rows |
| Denormalise | dénormaliser | Duplicating a column to avoid a join |
| Partitioned table | table partitionnée | A table split by range (here, by month) |
| Idempotent | idempotent | Running it twice gives the same result |
| Savepoint | point de sauvegarde | A nested, individually-rollbackable transaction |
| Race condition | situation de compétition | A bug depending on operation ordering |
| TOCTOU | TOCTOU (temps de vérification / temps d'usage) | Check-then-act race |
| Deep link | lien profond | A URL pointing directly at an inner page |
| Fallback | repli / solution de repli | The behaviour when the primary path fails |
| Read-only | lecture seule | No write operations to the cloud |
| Least privilege | moindre privilège | Grant only the access strictly required |

---

## Appendix — key commands

```bash
# Bring the stack up and seed it
make up && make migrate && make seed

# Tests
docker compose exec backend pytest -q                    # backend, no DB-backed suites
docker compose run --rm --no-deps \
  -e CLOUDPILOT_TEST_DB="postgresql+asyncpg://cp:cp@postgres:5432/cloudpilot_test" \
  backend pytest -p no:warnings                          # backend, all 199
cd frontend && pnpm test                                 # 36 unit tests
make e2e                                                 # 15 Playwright specs

# Quality gates
make lint          # ruff + mypy (backend), eslint (frontend)
make typecheck     # mypy + tsc

# The rate card
make pricing       # refresh from the public rate-card APIs (~4s, no cloud creds)
make pricing-deep  # also fetch the large AWS offer files (slow)

# Demo credentials
demo@cloudpilot.dev / demo1234
```

## Appendix — the seven session reports

| Report | Date | Subject |
|---|---|---|
| [`session-report-2026-07-14.md`](session-report-2026-07-14.md) | 14 Jul | Audit, pricing simulator, first live run |
| [`session-report-2026-07-20.md`](session-report-2026-07-20.md) | 20 Jul | Hardening pass, agent accuracy |
| [`session-report-2026-07-20b.md`](session-report-2026-07-20b.md) | 20 Jul | Tenant isolation, second layer |
| [`session-report-2026-08-05.md`](session-report-2026-08-05.md) | 5 Aug | Status audit, zero commits |
| [`session-report-2026-08-25.md`](session-report-2026-08-25.md) | 25 Aug | Demo-readiness hardening |
| [`session-report-2026-08-25b.md`](session-report-2026-08-25b.md) | 25 Aug | Closing carried-forward gaps |
| [`session-report-2026-08-31.md`](session-report-2026-08-31.md) | 31 Aug | Provenance on screen, e2e suite |

Supporting docs: [`architecture.md`](architecture.md) · [`security.md`](security.md) ·
[`api-reference.md`](api-reference.md) · [`development.md`](development.md) ·
[`deployment.md`](deployment.md)

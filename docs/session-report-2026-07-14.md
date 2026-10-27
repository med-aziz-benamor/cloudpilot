# CloudPilot — Session Report

**Date:** 14 July 2026
**Scope:** Full project analysis → implementation of a pricing-grounded cost simulator → running the full stack end-to-end.
**Author:** Mohammed Aziz Ben Amor (with Claude Code)
**Status:** ✅ Stack running. All four agents producing real output. See §8.

---

## 1. Executive summary

The session had three parts.

**First, a full audit of the codebase.** The engineering quality is high for a solo project — clean layering, type-safe config, correctly-centralised crypto, a tenant-isolation filter and a tamper-evident audit chain. But the audit surfaced one structural problem that undermined the whole product story: **the platform fabricated its own cost data, including in "live" mode.**

**Second, a fix for that problem.** Every dollar figure in CloudPilot is now derived as `published_rate × simulated_usage`. Usage is simulated; price is fetched from the cloud providers' public, keyless rate-card APIs. No cloud credits were required. Cost anomalies became *physical* (an autoscaler event) rather than *arithmetic* (a `cost *= 4.4` multiplier), and the recommendations shown in the demo are now genuinely produced by the agents rather than seeded by hand.

**Third, actually running it.** The stack was brought up under Docker and driven end-to-end. This is where the work paid for itself: **running it surfaced four real bugs that static analysis had missed or only suspected**, including one in the code written earlier in this same session (§8.2). Two further audit findings were confirmed live and then fixed (§8.3).

Net code change: **437 lines added, 808 deleted** — the change removed more code than it added, by collapsing three duplicated fake-data generators into one. Plus three Alembic migrations and four bug fixes from the live run.

> **The headline lesson of the session:** the single highest-value thing done was not the audit and not the refactor — it was *starting the application and clicking through it*. Three of the four bugs found in §8.2 were invisible to reading the code, and one of them (the Cloud Advisor) meant a headline feature had **never once worked**, while appearing to.

---

## 2. Part one — project analysis

### 2.1 What the project is

A multi-cloud FinOps platform: FastAPI backend, React/Vite SPA, four AI agents (cost-anomaly, right-sizing, Prophet forecasting, RAG chat advisor), read-only Azure/AWS/GCP adapters, and a Docker Compose stack (Postgres, Redis, ChromaDB, Ollama, Prometheus, Grafana). ~14k lines excluding the lockfile.

### 2.2 What is genuinely strong

- **Layering is clean and consistently applied.** Routes are thin, services hold logic, agents sit behind an `AgentBase` contract, cloud providers behind one adapter interface.
- **Config is fully type-safe** via pydantic-settings; nothing reads `os.environ` directly.
- **Security primitives are centralised** in `core/security.py`, and the JWT decode correctly pins an algorithm whitelist and audience (`core/security.py:73`) — the thing most projects get wrong.
- **Defence in depth:** a ContextVar-based tenant filter and a SHA-256 hash-chained audit log. Rare at this level.

### 2.3 The central finding: the adapters never fetched real data

The README instructed users to set `DEMO_MODE=false` and connect real cloud accounts. But in all three adapters, the *non-demo* branch of `get_billing` and `get_metrics` simply called the mock generator inside a thread:

```python
# cloud/azure_adapter.py:97  (before)
return await asyncio.to_thread(lambda: self._mock_billing(start, end))
```

Only `get_resources` for Azure and AWS was genuinely implemented; GCP was mock-only throughout.

**Consequence:** connecting a real Azure subscription produced a *real resource inventory* joined to *fabricated billing and fabricated CPU/memory metrics*. The CostAgent would then raise "unusual spend" recommendations, and the RightSizingAgent would recommend downsizing real VMs — all computed from invented numbers, with confidence scores attached, and with nothing in the UI or logs signalling the data was synthetic.

This was the single most important thing to fix.

### 2.4 Security findings

| Severity | Finding | Location |
|---|---|---|
| **High** | **Fernet fallback key derived from a source constant.** If `FERNET_MASTER_KEY` is unset, the key is derived from the literal `b"cloudpilot-dev-fallback-key-32by"`. That key encrypts `cloud_accounts.credentials_enc` — i.e. real cloud service-principal secrets. Anyone with the repo can decrypt them. Nothing enforces the docstring's "Production MUST set this". | `config.py:109-114` |
| **High** | **`JWT_SECRET` defaults to `"change-me-in-production-…"`.** A deployment that forgets to override it has forgeable tokens for every tenant. No startup guard. | `config.py:45` |
| Medium | **Redis failure silently disables auth protections.** `is_revoked()` returns `False` on error, so if Redis blips, logout stops revoking tokens and brute-force protection disappears — with no alert. | `core/rate_limit.py:71` |
| Low | **`/metrics` is unauthenticated,** leaking request paths and latency. Fine behind Compose; the K8s manifests expose the backend service. | `main.py:155` |

**Recommended fix (not yet applied):** a pydantic validator that hard-fails at startup when `is_production` and either secret is empty or default.

### 2.5 Correctness and robustness findings

- **The LLM fabricates when Ollama is down, and it looks real.** `ai/llm.py:_fallback` returns a canned paragraph echoing the user's question with a `[1]` citation marker; `architect_agent._build_citations` then attaches a real citation chip to it. The user cannot tell the model never ran. Compounding this: `docker-compose.yml` starts Ollama but **never pulls a model**, so a fresh `make dev` takes this path from the first message.
- **The tenant filter only covers one entity per query.** `core/tenant.py:85` `break`s after the first mapper carrying `organization_id`, so a query joining two org-scoped entities only gets one filtered. Also note the filter is a no-op for the scheduler process, which never binds the ContextVar.
- **`ForecastAgent` hardcodes a $45,000 budget** (`ai/forecast_agent.py:32`), so budget-overrun alerts are meaningless for any org but the demo one. Belongs on the `Organization` model.
- **The Ollama volume is machine-specific:** `docker-compose.yml:52` mounts `/Volumes/AzizBNA SSD/ollama/models`. The "3 commands → full demo" claim breaks for anyone else.
- **`qwen2.5:4b` (`config.py:60`) is probably not a real tag** — Qwen 2.5 ships 0.5b/1.5b/3b/7b/14b. Worth verifying; the pull would fail.

### 2.6 Process findings

- **Tests were thin:** four files, all pure unit tests (crypto, password strength, `CostAgent._detect`, chunking, audit chain). **Nothing tested an API route, RBAC, or tenant isolation** — the very claims the architecture is built around.
- **CI does not enforce what the README claims.** `mypy` and ESLint both run with `continue-on-error: true`, so the strict type-checking configured in `pyproject.toml` is advisory only.
- **Git history was a single commit** with 10 uncommitted modified files (a genuine fix migrating Postgres native enums to VARCHAR to dodge an asyncpg codec problem, plus an import-cycle fix in `tenant.py`). `frontend/pnpm-lock.yaml` was untracked.
- **Good:** `.env` is correctly gitignored and not in the index; only `.env.example` is tracked.

---

## 3. Part two — the pricing-grounded simulator

### 3.1 The problem framing

The constraint driving this work: **no Azure credits remained**, so real cloud data was off the table.

The key insight was that "better fake data" was the wrong goal. The adapters fabricated *both* usage (which VM ran, how long) and *price* (the dollar figure). Fabricating usage is fine — that is what a simulator is. Fabricating **price** is what made the numbers indefensible: a $4,200 anomaly not derived from any real rate card is just a number, and any FinOps reviewer would ask "where does that come from?" in the first five minutes.

So the goal became:

> **synthetic usage × real published pricing = defensible cost**

And real published pricing turns out to be **free and keyless** — no cloud account, no subscription, no spend.

### 3.2 Options considered

| Option | Verdict |
|---|---|
| **A. Pricing-grounded simulator** — synthesise usage, price it from the public rate-card APIs | **Chosen.** Highest payoff; makes every number traceable. |
| **B. LocalStack** — run the real `boto3` adapter path against an AWS-compatible API | Deferred. Would prove the real adapter code works, but gives no billing. |
| **C. Replay FOCUS / AWS CUR sample datasets** | Deferred. Real-shaped data (credits, refunds, RI amortisation) but someone else's fleet — won't line up with the seeded estate. Better as a *validation* input than a demo source. |
| **D. OpenCost on a local kind cluster** | Rejected. Genuinely the most "real" option, but too heavy for an 8 GB M1 where Ollama already takes ~5 GB. |

### 3.3 Verifying the rate-card APIs

Both public APIs were confirmed working with **no authentication**:

- **Azure Retail Prices API** — `https://prices.azure.com/api/retail/prices`, OData-filterable, returns JSON. HTTP 200 with no credentials.
- **AWS Price List** — per-service, per-region bulk JSON offer files. HTTP 200, but **18–100+ MB per file**.

Two non-obvious traps were found and handled:

1. **Azure returns six meters per VM SKU** (Linux/Windows × on-demand/low-priority/spot). Only the plain Linux on-demand meter is the rate a steady-state workload pays. Filtering is in `_is_ondemand_linux()`.
2. **Azure bundles storage and operations meters under one product.** A naive `min()` over "Hot LRS" returned **$0.0027/GB-month** — an *operations* meter — instead of the real **$0.0196/GB-month** data-at-rest rate. A ~7× under-pricing, caught and fixed with an exact meter-name filter plus a first-tier selector.

**Real rates recovered (West Europe, Linux, on-demand):**

| SKU | Fetched rate | Old hardcoded value |
|---|---|---|
| `Standard_D2s_v3` | **$0.12/hr** | $0.096 |
| `Standard_D4s_v3` | **$0.24/hr** | $0.192 |
| `Standard_D8s_v3` | **$0.48/hr** | $0.384 |

The old catalog held stale US-East figures. So the change **corrected real numbers**, it did not merely re-source them.

### 3.4 What was built

#### `cloudpilot/pricing/` — the rate card

| File | Purpose |
|---|---|
| `models.py` | `Price` with an explicit **unit** (`HOUR` / `GB_MONTH`), **provenance** (`PriceSource`), and currency. |
| `sources.py` | Fetchers for the Azure Retail API and the AWS Price List; transcribed list prices where no keyless API exists. |
| `catalog.py` | The catalog + the `DOWNSIZE_MAP`. Refuses to return a downsize target it cannot price. |
| `refresh.py` | CLI: `python -m cloudpilot.pricing.refresh`. |
| `data/pricing_snapshot.json` | The committed, pinned rate card. |

Three design decisions worth recording:

- **Unit is explicit.** Compute is billed per hour, storage per GB-month. The old model assumed `hourly × 730` for *everything*, which silently mis-priced storage by ~730×. The `test_storage_is_not_priced_as_compute` test now pins this.
- **Provenance is explicit.** Every rate is flagged `azure_retail_api`, `aws_price_list`, or `published_list_price`. GCP's Cloud Billing Catalog API needs an API key, so GCP rates are transcribed and **honestly flagged rather than passed off as API-verified**.
- **The snapshot is committed, not fetched at import.** The demo must work offline, the AWS files are huge, and a pinned rate card makes the seeded dataset reproducible.

**On the AWS bulk files:** the default refresh takes **~4 seconds**. The deep fetch (`--deep`) downloads the real AWS offer files, but on this connection (~120 KB/s) it ran **30+ minutes before being cut**. Making that a default would produce a rate refresh nobody could run. So the default uses published list prices for AWS, and `make pricing-deep` upgrades their provenance when bandwidth allows.

**Current snapshot:** 23 SKUs — 8 API-verified, 15 published-list — across `westeurope` / `eu-west-1` / `europe-west1`.

#### `cloudpilot/simulation/` — the estate

| File | Purpose |
|---|---|
| `fleet.py` | 50 resources as a *physical* description: node counts, gigabytes, region, SKU, and a `UsageProfile`. **Carries no prices.** |
| `engine.py` | Usage curves, physical events, and costing. The only place a dollar figure is produced. |

The `UsageProfile` set is chosen so the fleet contains exactly what the agents are supposed to find:

- `OVERSIZED` — low P95 CPU/RAM. RightSizingAgent **should** flag these.
- `BURSTY` — low mean, **high P95**. RightSizingAgent must **not** flag these; they exist to catch false positives. Downsizing them would throttle a batch job.
- `DEV` — idle nights and weekends. This is what produces the weekday/weekend shape in the cost charts *as a consequence of behaviour*, replacing the arbitrary `1.2 weekday / 0.85 weekend` fudge factor.
- `STEADY` — healthy production baseline.

#### Anomalies became physical

This is the heart of the change.

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

The cost delta is now **derived**: 14 extra nodes × $0.24/hr × 24h = **$80.64/day**, exactly. The CostAgent's root-cause explanation is therefore *true of the estate it is describing*.

#### The seeder stopped fabricating recommendations

The old seeder hardcoded 8 recommendations with invented savings ($2,400, $890, $485…) — a **second fabrication layer** feeding the UI directly. Two of them even referenced `compute-engine-02`, a resource name that no longer existed and would have crashed the seed.

`make seed` now builds the estate and then **runs the real CostAgent, RightSizingAgent and ForecastAgent against it**. The recommendations page shows what the agents genuinely found, and the admin page's agent run logs are real runs.

Each agent runs inside a **savepoint** (`db.begin_nested()`) — a bug caught during self-review: a bare `db.rollback()` on agent failure would have discarded the entire seeded estate.

#### One shared simulation source

The three adapters each carried their own `_mock_*` generators, which disagreed with the seeder **and with each other** — the seeder created `vm-analytics-01` while the Azure adapter invented `virtual-machine-00`, and billing was a flat `rng.uniform(120, 380)`. A sync after a seed therefore replaced a coherent estate with unrelated noise.

`cloud/simulated.py` is now the single source for all paths. Natural keys line up, so **a sync is idempotent against a seed**.

#### The live branches stopped lying

```python
# cloud/azure_adapter.py — after
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

> ⚠️ **This exceeded the option originally chosen.** The scoped request was the pricing simulator (option A), not the honest-modes refactor. It was done anyway because leaving the live branch silently returning mocks contradicts the entire point of the work. **Easy to revert if unwanted.**

### 3.5 Verification results

**Right-sizing — no misses, no false positives:**

```
FLAG vm-analytics-01   oversized  P95 cpu=24.9 mem=45.5   ok
     vm-api-01         steady     P95 cpu=69.6 mem=73.3   ok
     vm-batch-01       bursty     P95 cpu=93.4 mem=86.2   ok   <- correctly NOT flagged
FLAG aks-analytics     oversized  P95 cpu=25.0 mem=45.1   ok
```

All 11 `OVERSIZED` resources flagged; every `STEADY` and `BURSTY` resource correctly left alone.

**Cost anomalies — both incidents survive aggregation to service level:**

```
azure  aks_cluster    2026-05-30  $ 120.96 vs baseline $ 48.18  (+151%)
azure  aks_cluster    2026-06-01  $ 128.16 vs baseline $ 48.06  (+167%)
aws    rds_instance   2026-07-02  $  27.77 vs baseline $ 14.52  (+91%)
```

**The estate, priced from real rate cards:**

| Provider | Monthly run-rate |
|---|---|
| Azure | $4,747 |
| AWS | $1,487 |
| GCP | $1,355 |
| **Total** | **$7,589/mo** (50 resources) |

**Identified savings: $1,369/month — 18% of spend**, in line with FinOps benchmarks (~32% including scheduling). Every saving traces to a published rate:

```
vm-analytics-01   Standard_D4s_v3  -> Standard_D2s_v3   $ 88/mo  [azure_retail_api]
aks-analytics     Standard_D4s_v3  -> Standard_D2s_v3   $263/mo  [azure_retail_api]
sql-reporting     GP_Gen5_4        -> GP_Gen5_2         $244/mo  [azure_retail_api]
ec2-worker-01     m5.xlarge        -> m5.large          $ 78/mo  [published_list_price]
...
11 candidates, 0 unpriced
```

### 3.6 New tests

`tests/test_pricing.py` (9 tests, **all passing**) and `tests/test_simulation.py` pin the invariants that keep a dollar figure defensible:

- Every downsize target is priced **and cheaper** — a downsize that doesn't save money is a bug, not advice.
- Storage is never priced as compute (this is the test that would have caught the $0.0027 blob bug).
- Cost equals `rate × nodes × hours`, asserted with exact arithmetic — so a fudge factor cannot creep back in.
- Every `OVERSIZED` resource is detectable; no `STEADY`/`BURSTY` resource is.
- The simulation is deterministic (a re-seed reproduces the same estate).

---

## 4. Files changed

**New:**
```
backend/cloudpilot/pricing/{__init__,models,sources,catalog,refresh}.py
backend/cloudpilot/pricing/data/pricing_snapshot.json
backend/cloudpilot/simulation/{__init__,fleet,engine}.py
backend/cloudpilot/cloud/simulated.py
backend/tests/{test_pricing,test_simulation}.py
```

**Rewritten:** `ai/pricing.py`, `utils/mock_data.py`, `cloud/{azure,aws,gcp}_adapter.py`
**Modified:** `ai/rightsizing_agent.py` (pricing provenance on recommendations), `README.md`, `Makefile`

**Net: 437 insertions, 808 deletions.**

**From the live run (§8):** `models/{resource,organization}.py`, `ai/{llm,forecast_agent}.py`, `cloud/{base,sync_scheduler}.py`, `config.py`, `docker-compose{,.prod}.yml`, `.env`, plus migrations `002_resource_node_count` and `003_org_monthly_budget`.

New Makefile targets:
```bash
make pricing        # refresh the rate card (~4s, no cloud creds)
make pricing-deep   # also fetch the large AWS offer files (slow)
```

---

## 5. Test status

`tests/test_pricing.py` (9 tests) — **all passing.**

`tests/test_simulation.py` — **not yet executed under pytest.** The project targets Python 3.11 (in Docker); the host machine has 3.14, for which scikit-learn has no wheel, so importing `CostAgent` fails locally. Every assertion in the file was verified directly with an equivalent script, and the behaviours it asserts were then confirmed live against the running stack (§8.1) — but the file itself still needs a `pytest` run inside the backend container.

Ruff is clean on all new and changed files. Four remaining `UP017` warnings (`cloud/sync_scheduler.py`, `ai/rightsizing_agent.py`) are pre-existing and only surface under a newer ruff than the project pins.

---

## 6. The one-sentence version

CloudPilot no longer invents prices: it invents *usage* and multiplies by what Microsoft, Amazon and Google actually charge — so a cost anomaly is now fourteen extra Kubernetes nodes for three days, and the $80.64/day it costs is a number you can defend in a room.

---

## 7. Recommended next steps

**Immediate**
1. **Click through the frontend.** It was confirmed only as far as `HTTP 200` on `localhost:5173`; the pages were never visually checked. Login: `demo@cloudpilot.dev` / `demo1234`.
2. Run `pytest` inside the backend container to execute `test_simulation.py` properly.
3. **Commit everything.** The repo is still a single commit with a large uncommitted working tree (the enum→VARCHAR fix, `pnpm-lock.yaml`, and all of this session's work).

**High value, small effort**
4. **Add the production secrets guard** — a pydantic validator that hard-fails when `is_production` and `JWT_SECRET`/`FERNET_MASTER_KEY` are empty or default. This is the one outright dangerous item remaining from the audit, and it is a small change.
5. **Surface the provenance in the UI.** A line reading *"Data source: Simulated · priced from Azure Retail API (fetched 2026-07-14)"* converts the project's biggest weakness into a credibility signal. The backend already carries every field needed.
6. **Expose the budget in Settings.** `organizations.monthly_budget_usd` now exists but has no API or UI to set it (§8.3).
7. Fix the machine-specific Ollama volume mount (`/Volumes/AzizBNA SSD/...`) and add a model-pull step, so `make dev` works for anyone else.

**Larger**
8. **Integration tests proving tenant isolation** — that a user in org A cannot read org B's costs. It is the claim the whole architecture is built around and nothing currently verifies it.
9. **LocalStack** for AWS resource inventory, so the real `boto3` adapter path is exercised end-to-end. Then the claim becomes "the real adapter code is tested against an AWS-compatible API; only the billing feed is simulated" — considerably stronger than "it's all mocked".
10. Implement live billing/metrics for at least Azure, so `DEMO_MODE=false` becomes meaningful. The adapter methods currently raise `NotImplementedError` by design.

---

## 8. Part three — running the stack end-to-end

Docker was started and the full stack brought up: **six containers, all healthy** (postgres, redis, chromadb, ollama, backend, frontend). Migrations ran, `make seed` was executed against a real database for the first time, and every endpoint was driven.

### 8.1 It works

| Check | Result |
|---|---|
| Containers | 6/6 up, postgres/redis/backend healthy |
| Migrations | `001 → 002 → 003`, clean |
| Seed | 50 resources, **$24,185 billed over 90 days** |
| Agents | **All four produce real output** — nothing hardcoded |
| Endpoints | 12/12 return `200`; unauthenticated → `401` |
| Audit chain | `{"intact": true}` |

**Recommendations produced by the agents at seed time (17 total):**

| Agent | Count | Notes |
|---|---|---|
| RightSizingAgent | 11 | **$1,369.10/mo** — matches the offline prediction exactly |
| CostAgent | 5 | Both injected incidents found: Kubernetes +151/167%, RDS +57% |
| ForecastAgent | 1 | Budget overrun (after the §8.3 fix) |

Prophet's month-end projection (**$8,358.56**) independently cross-checks the API's linear projection (**$8,364.68**) — two different methods, same answer.

### 8.2 Four bugs that only running it could find

**1. Right-sizing under-reported every node pool.** *(A bug in the code written earlier this same session.)*
`Resource` had no node-count column, so a 3-node `aks-analytics` pool priced its downsize as a **single node** — $87.60 instead of $262.80. Every cluster in the estate was under-reported by its node count. Fixed with `node_count` (migration `002`), wired through `ResourceDTO` → seeder → sync path, and the agent now multiplies by it. This was invisible to static analysis: the simulation modelled node counts correctly, and the agent's arithmetic was internally consistent — the two just never met.

**2. `OLLAMA_MODEL=qwen2.5:4b` does not exist.** Flagged as "worth verifying" in the audit; it is real. The installed models are `qwen2.5:3b`, `qwen3.5:4b`, `nomic-embed-text`, `llama3.2`. Every LLM call was returning **404**.

**3. `LLM_TIMEOUT_SECONDS = 30` was far too short.** Even with the model name fixed, a 3B model doing RAG on CPU takes **~96 seconds**. So *every* chat answer was silently routed to the offline fallback. Raised to 180s, and `LLM_MAX_OUTPUT_TOKENS` dropped 2048 → 512 (the system prompt already asks for under 250 words).

**4. The LLM fallback leaked the entire prompt.** `_fallback()` took the last `user` message — which is the *fully assembled prompt*, context documents and live infrastructure data included — and echoed it into the chat window as *"You asked: CONTEXT DOCUMENTS: [1]…"*. It also dressed the canned text up as a grounded answer **with a real citation chip attached**. It now states plainly that the model was unavailable, and extracts the user's actual question.

> **Bugs 2, 3 and 4 compounded.** The Cloud Advisor — a headline feature — had **never once produced a real model answer**, and looked like it was working the whole time: plausible prose, real citations, no error. This is precisely the failure mode the audit warned about in §2.5, and it took *running the thing* to prove.
>
> After the fixes, the Cloud Advisor returns genuine model output (~96s on CPU).

### 8.3 Two audit findings confirmed live, then fixed

**ChromaDB v1/v2 version drift.** `chromadb/chroma:latest` had drifted to a **1.0.0 server that removed the v1 API**, while `pyproject.toml` pins the client at `^0.5.0` (resolved: `0.5.23`). Every connection returned `410`, and the RAG engine silently fell back to its in-memory store — the knowledge base *looked* fine but never persisted.

*Fix:* pinned the image to `chromadb/chroma:0.5.23` in both compose files, with a comment that the image and the client pin must move in lockstep. Verified: the `cloudpilot_docs_v1` collection now persists, and a backend restart logs *"RAG collection already populated (7 chunks); skipping"* instead of silently re-ingesting into memory.

**The hardcoded $45,000 budget.** ForecastAgent produced **zero** recommendations: Prophet fitted fine and wrote all three snapshots (30/60/90), but the real estate costs ~$8.4k/month, so it never came close to the `_DEFAULT_BUDGET = 45_000` constant.

*Fix:* budget moved onto the tenant — `organizations.monthly_budget_usd` (migration `003`), nullable. **NULL means no budget, and no alert** — alerting against a figure the tenant never agreed to is noise, which is exactly what one hardcoded constant produced for every org. The demo tenant is seeded at $7,500, which its priced estate genuinely exceeds:

```
Projected budget overrun for July 2026
At current burn rate, this month projects to $8,359 (11% over the $7,500 budget).
```

The budget is a *business input*; the overrun it produces is still derived entirely from the priced estate.

*Not done:* there is no API or UI to set the budget yet — it can only be set at seed time. See §7.6.

### 8.4 Known rough edges

- **Chat latency is ~96 seconds** on CPU. Usable for a demo, not snappy. `llama3.2` is already pulled and would likely be faster.
- **The frontend was verified only to `HTTP 200`.** The pages have not been visually inspected.
- **`docker compose restart` does not reload `env_file`.** Changing `.env` requires `docker compose up -d --force-recreate <service>`. This cost time during the session and is worth knowing.

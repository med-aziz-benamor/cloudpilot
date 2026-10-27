# CloudPilot — AI Agents & Cloud Advisor

CloudPilot's intelligence lives in four agents under `backend/cloudpilot/ai/`. Three run
on a schedule and write their findings to the database; the fourth answers questions
on demand in the chat. This guide explains what each one does, the algorithm behind
it, and why its thresholds are set where they are.

```
                        ┌──────────────────────────────────────────┐
                        │ APScheduler process (ai/orchestrator.py) │
                        └──────┬───────────────┬───────────────┬───┘
                    every 60 min        daily 02:00      daily 03:00   (UTC)
                               │               │               │
                        ┌──────▼─────┐ ┌───────▼───────┐ ┌─────▼────────┐
billing_entries ───────▶│ CostAgent  │ │ RightSizing   │ │ ForecastAgent│◀── billing_entries
                        │ anomalies  │ │ Agent         │ │ Prophet      │
                        └──────┬─────┘ └───────┬───────┘ └─────┬────────┘
metric_samples ──────────────────────────────▶ │               │
pricing catalog ─────────────────────────────▶ │               │
                               ▼               ▼               ▼
                        recommendations   recommendations   forecast_snapshots
                                                            (+ budget alert)

Chat request ──▶ ArchitectAgent ──▶ RAG retrieve (ChromaDB) ──▶ LLM (Ollama) ──▶ answer + citations
```

## Contents

1. [The agent contract](#the-agent-contract)
2. [CostAgent — anomaly detection](#costagent--anomaly-detection)
3. [RightSizingAgent — over-provisioning](#rightsizingagent--over-provisioning)
4. [ForecastAgent — spend projection and budget alerts](#forecastagent--spend-projection-and-budget-alerts)
5. [ArchitectAgent — the Cloud Advisor](#architectagent--the-cloud-advisor)
6. [The RAG engine](#the-rag-engine)
7. [The LLM client and its failure modes](#the-llm-client-and-its-failure-modes)
8. [Scheduling and tenant isolation](#scheduling-and-tenant-isolation)
9. [Summary of tunable constants](#summary-of-tunable-constants)

---

## The agent contract

Every agent subclasses `AgentBase` (`ai/base_agent.py`) and implements one of two
tracks:

| Method | Used by | Contract |
|---|---|---|
| `run(organization_id, db) -> int` | the scheduler | Batch execution; writes `Recommendation` rows and returns how many it created |
| `trigger(organization_id, db, payload)` | the chat endpoint | On-demand execution with a custom payload; returns a result directly |

The scheduler never calls `run()` directly but `run_with_logging()`, which wraps it in
an `agent_run_logs` row (`running` → `success`/`failed`, with the count created or the
error message). Those rows feed the agent history on the admin page
(`GET /api/v1/admin/agent-runs`). When a run creates at least one recommendation,
`run_with_logging()` also invalidates the organization's dashboard cache, since the
pending count and potential-savings KPIs just changed.

Every recommendation carries a `metadata_json` object holding the numbers it was
derived from. The frontend renders this as the *"How this was calculated"* disclosure
on each recommendation card (`components/domain/CalculationBasis.tsx`), so no figure is
shown without its basis.

---

## CostAgent — anomaly detection

**File:** `ai/cost_agent.py` · **Cadence:** every 60 minutes · **Output:** `agent = 'cost'` recommendations

### Algorithm

1. Load the last **60 days** of `billing_entries` for the organization.
2. Group daily totals by **(cloud account, service)**, so each series is one service
   on one account.
3. Skip series with fewer than **14 points**: too little history to call anything
   unusual.
4. Flag a day if **either** detector fires (union, not intersection):
   - **IsolationForest** (`contamination=0.05`, `random_state=42`) on the 1-D cost
     series, keeping only predictions with an anomaly score below −0.1;
   - **Z-score**: cost above `μ + 2σ` of the series.
5. For each flagged day, compute the baseline as the mean of the *other* days, then
   apply two **materiality gates**. Both must hold:
   - at least **25 %** above baseline, and
   - at least **$5** above baseline in absolute terms.
6. Skip anything already reported: deduplication is keyed on
   `(cloud_account_id, service, anomaly_date)` against pending cost recommendations.
7. Write a recommendation with a plain-language description, the excess spend as
   `estimated_saving_usd`, and a confidence of `0.6 + 0.1 × (z − 2)`, capped at 0.95.

### Why the gates are 25 % and $5

Statistical detection decides whether a day is *unusual*; the gates decide whether it
is *worth a human's attention*. The percentage gate was originally 50 %, calibrated
when demo costs were fabricated with `cost *= 4.4`. Once costs became
`published_rate × simulated_usage`, a real incident confined to one resource arrives
**diluted by its sibling resources** in the same service group. The `rds-production`
incident (a genuine 4× event) landed at only +57 %. Adding one comparable RDS instance
pushed it to +48 % and made it disappear, while its Z-score stayed at 5.12.

Sweeping the gate from 50 % down to 10 % surfaced **zero** additional unexplained
anomalies, so the gate was lowered to 25 % and paired with a $5 absolute floor. The
floor carries the actual notion of "material": a 30 % spike on a $2/day service is
noise whatever the percentage. The calibration is pinned by
`tests/test_cost_anomaly_thresholds.py`.

### What a finding records

| `metadata_json` field | Meaning |
|---|---|
| `anomaly_date` | the flagged day |
| `service`, `provider` | the series it was found in |
| `expected_cost` | the baseline (mean of the other days) |
| `actual_cost` | what was billed that day |
| `delta_usd` | `actual − expected`, also the recommendation's `estimated_saving_usd` |
| `z_score` | `delta / σ`, which drives the confidence |

The demo's Kubernetes spike is physical: `aks-prod-cluster` scaled from 4 to 18 nodes
for three days. The $80.64/day delta is exactly 14 extra `Standard_D4s_v3` nodes ×
$0.24/hr × 24 h, so the root-cause narrative is literally true of the estate.

---

## RightSizingAgent — over-provisioning

**File:** `ai/rightsizing_agent.py` · **Cadence:** daily at 02:00 UTC · **Output:** `agent = 'rightsizing'` recommendations

### Algorithm

1. Load every **active** resource that has a SKU (VMs, node pools, databases).
2. Compute the **95th percentile** of `cpu_percent` and `memory_percent` over the last
   **14 days** of `metric_samples`.
3. The resource is a downsize candidate when **P95 CPU < 40 % and P95 RAM < 60 %**.
   P95 rather than the mean means a resource is only shrunk if it stays under the
   threshold during its busy periods too, not just on average.
4. Look up the **next size down in the same family** (`pricing.catalog` downsize
   pairs, e.g. `Standard_D4s_v3 → Standard_D2s_v3`). If there is none, skip.
5. Saving = `(current_rate − target_rate) × 730 h × node_count`. A node pool
   downsizes every node, so the saving scales with the count. Migration `002` added
   `node_count` after pools were found to be under-priced.
6. Confidence = `0.7 + 0.2 × (40 − P95_cpu) / 40`, capped at 0.92: the idler the
   resource, the more certain the recommendation.
7. Skip resources that already have a pending or accepted rightsizing recommendation.

### Provenance

The recommendation's metadata stores both hourly rates and, for each, where the rate
came from (`azure_retail_api`, `aws_price_list` or `published_list_price`), the meter
or page it was read from, and the snapshot date. A saving can be traced back to the
provider's published price list from the UI, without reading the code. See
[architecture.md → Where the numbers come from](architecture.md#where-the-numbers-come-from).

---

## ForecastAgent — spend projection and budget alerts

**File:** `ai/forecast_agent.py` · **Cadence:** daily at 03:00 UTC · **Output:** `forecast_snapshots` rows, plus at most one `agent = 'forecast'` recommendation

### Algorithm

1. Load up to **400 days** of org-wide daily billing totals (enough for a full
   seasonal cycle). Needs at least **30 days**; otherwise the run is a no-op.
2. Fit **Prophet** with weekly seasonality on, yearly and daily seasonality off, an
   80 % uncertainty interval, and a **`month_end` regressor** (1 for days ≥ 26) that
   captures end-of-month billing effects.
3. Predict **30, 60 and 90 days** ahead and upsert one `forecast_snapshots` row per
   horizon (`yhat`, `yhat_lower`, `yhat_upper`, `trend` per day). The Forecast page
   reads these through `GET /api/v1/forecast?horizon_days=…`.
4. **Budget check.** Projected month-end = month-to-date actual + the forecast for the
   remaining days. When it exceeds the organization's budget by more than **10 %**, a
   "Projected budget overrun" recommendation is raised, unless one is already pending.

### Design decisions

- **No budget, no alert.** If the organization has not set `monthly_budget_usd`, the
  overrun check is skipped. An earlier version compared every tenant against one
  hardcoded constant, which made alerts against a number nobody had chosen.
- **Month-to-date matches month *and* year.** Matching on month alone silently summed
  the same month from previous years once history exceeded twelve months.
- **The 10 % margin** stops a projection that lands a rounding error over budget from
  paging anyone.

The budget is set by an admin through `PATCH /api/v1/forecast/budget` (audited) or the
control on the Forecast page.

---

## ArchitectAgent — the Cloud Advisor

**File:** `ai/architect_agent.py` · **Cadence:** on demand, once per chat message · **Output:** a chat answer with citations

The ArchitectAgent's scheduled `run()` is a no-op; it works only through `trigger()`,
called by the chat service for each user message.

### Pipeline

1. **Retrieve** the top-5 knowledge-base chunks for the question from the RAG engine.
2. **Gather live context** from the tenant's own data:
   - any resource whose name or service matches a token in the question (up to 5),
     with its service, region and SKU;
   - the total recorded spend across all accounts, always included as grounding.

   Each lookup is recorded as a `tool_calls` trace that the chat UI displays. These are
   deterministic lookups made by the agent, **not** LLM tool-calling: the model never
   chooses what to query.
3. **Build the prompt** (`ai/rag/prompts.py`): a system prompt plus numbered context
   documents, the live data and the question, with prior turns as history. The system
   prompt instructs the model to cite sources as `[1]`, `[2]`, to prefer the user's
   live data over generic documentation, to stay under ~250 words, and to **say so
   plainly when it lacks the data rather than invent figures**.
4. **Generate** the answer through the LLM client.
5. **Map citations**: `[n]` markers in the answer are resolved back to the retrieved
   documents and returned as citation chips.

---

## The RAG engine

**Files:** `ai/rag/engine.py`, `ai/rag/ingestor.py`, `ai/rag/prompts.py`

| Aspect | Implementation |
|---|---|
| Vector store | ChromaDB (`chromadb/chroma:0.5.23`), collection created with `hnsw:space=cosine` |
| Embeddings | `nomic-embed-text` via Ollama |
| Corpus | 23 curated FinOps entries in `ingestor.py`: 12 provider-agnostic (budgets, spike investigation, rightsizing, idle resources, commitment discounts, tagging, storage tiering, egress, Kubernetes cost allocation), 4 Azure, 4 AWS, 3 GCP |
| Relevance cut-off | chunks with cosine distance > **0.55** are dropped |
| Query cache | in-process, keyed `(query, k)`, 100 entries, FIFO eviction |
| Offline fallback | in-memory store with cosine scoring when ChromaDB is unreachable |

### The relevance cut-off

Without a cut-off, `retrieve()` always returns the top-k, however poor the matches.
Asking the Advisor *"What is the capital of France?"* produced five
authoritative-looking citations about AKS node pools. Measured best-match distances on
the seeded corpus:

| Query | Best distance |
|---|---|
| Why did my Azure costs spike last month? | 0.2546 |
| Is my Azure AKS cluster correctly sized? | 0.3097 |
| How do I reduce S3 storage costs? | 0.4231 |
| asdfgh qwerty zxcvbn | 0.5567 |
| What is the capital of France? | 0.6587 |

On-domain questions sit well below 0.5 and unrelated ones above it; 0.55 falls in the
gap. The cut-off is deliberately loose: its job is to reject questions the corpus cannot
speak to, not to fine-tune ranking.

### Only confident results are cached

The query cache has no TTL, so caching a degraded result would freeze it for the life
of the process. Two cases are therefore **never** cached:

- the embedding fell back to the hash stub because Ollama was unreachable, so the query
  vector is meaningless;
- retrieval returned nothing. A ChromaDB outage and an empty collection look identical
  to "no relevant documents" at this point.

### Re-ingestion

Ingestion is skip-if-non-empty, so growing the corpus would never reach an environment
whose collection already held the older, smaller corpus. `RAGEngine.reset()` drops the
collection and clears the query cache so the corpus can be re-ingested.

---

## The LLM client and its failure modes

**File:** `ai/llm.py`

| Setting | Default | Notes |
|---|---|---|
| Provider | **Ollama** (local) | OpenAI (`gpt-4o-mini`) is used only when `OPENAI_API_KEY` is set **and** `DEMO_MODE=false` |
| Chat model | `qwen2.5:3b` (`OLLAMA_MODEL`) | fits an 8 GB machine; privacy by design, as no data leaves the host |
| Embedding model | `nomic-embed-text` (`OLLAMA_EMBED_MODEL`) | |
| Timeout | `LLM_TIMEOUT_SECONDS=180` | a 3B model on CPU routinely needs more than a minute |

The client is built to **fail honestly**:

- **Model unreachable or empty response → an explicit notice, not an answer.** The
  fallback opens with "⚠️ The local language model is unavailable, so this is not a
  generated answer", quotes only the user's actual question (never the assembled prompt
  with its context documents), and says how to fix it. An empty `content` (for example a
  tool-calling model returning `null`) is treated the same way instead of crashing
  downstream code.
- **Embedding unreachable → deterministic hash vector, flagged as not real.**
  `embed_with_status()` returns `(vector, is_real)` so callers that cache can refuse to
  cache meaningless results.

Too short a timeout produces no error: every answer silently routes to the fallback. On
Apple Silicon, run Ollama natively for Metal acceleration (see
[development.md](development.md)); in Docker it runs on pure CPU, and one RAG answer
was measured at ~460 s.

The e2e spec `frontend/e2e/advisor.spec.ts` asserts the "model unavailable" notice when
no model is running.

---

## Scheduling and tenant isolation

`ai/orchestrator.py` runs as its own process (`python -m cloudpilot.ai.orchestrator`,
the `scheduler` service in Docker Compose):

| Job | Trigger |
|---|---|
| CostAgent | every 60 minutes, plus one immediate pass at startup |
| RightSizingAgent | cron 02:00 UTC |
| ForecastAgent | cron 03:00 UTC |
| Cloud sync | every hour |

Each agent runs **once per organization, in its own transaction**. A failure for one
tenant is rolled back and logged without affecting the others.

The scheduler has no request lifecycle, so the ORM tenant filter (which keys off a
request-bound `ContextVar`) is inactive. That is deliberate: isolation comes from the
`organization_id` passed explicitly into `run()`, and every agent filters on it
directly. `tests/test_scheduler_isolation.py` locks this behaviour in. Run the scheduler
as a **single replica**, or every agent run is duplicated.

Admins can also trigger an agent manually with `POST /api/v1/admin/agents/{agent}/run`.

---

## Summary of tunable constants

| Agent | Constant | Value | Meaning |
|---|---|---|---|
| CostAgent | `_LOOKBACK_DAYS` | 60 | billing history analysed |
| CostAgent | `_MIN_POINTS` | 14 | minimum series length |
| CostAgent | IsolationForest `contamination` | 0.05 | expected anomaly share |
| CostAgent | Z-score threshold | 2σ | backup detector |
| CostAgent | `_MIN_PCT_ABOVE_BASELINE` | 25 % | materiality, relative |
| CostAgent | `_MIN_DELTA_USD` | $5 | materiality, absolute |
| RightSizingAgent | `_METRIC_DAYS` | 14 | metric window |
| RightSizingAgent | `_CPU_THRESHOLD` | 40 % | P95 CPU ceiling |
| RightSizingAgent | `_MEM_THRESHOLD` | 60 % | P95 RAM ceiling |
| RightSizingAgent | `_HOURS_PER_MONTH` | 730 | billable hours |
| ForecastAgent | `_LOOKBACK_DAYS` | 400 | history fed to Prophet |
| ForecastAgent | minimum history | 30 days | below this, no forecast |
| ForecastAgent | `_OVERRUN_TRIGGER` | 1.10 | alert at budget + 10 % |
| RAG | `MAX_COSINE_DISTANCE` | 0.55 | relevance cut-off |
| RAG | `k` | 5 | documents per question |

To add an agent, see [development.md → Adding a new AI agent](development.md#adding-a-new-ai-agent).

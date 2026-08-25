# Session report — 2026-08-25 (b): closing the carried-forward gaps

Follow-up to [`session-report-2026-08-25.md`](session-report-2026-08-25.md), which
fixed the bugs a code audit and a browser walkthrough had turned up. This session
works through the items that report listed as "still open", plus two problems found
along the way that nothing had flagged. Eight commits.

Backend suite: **189 tests, all passing** (was 155). `ruff check .` clean across the
whole backend, and **mypy reports zero issues across all 85 source files** (was 94
errors). Frontend: 16 tests passing, typecheck clean.

---

## Summary

| # | Carried-forward item | Outcome |
|---|---|---|
| 1 | Budget-setting had no write path | **Done** — and it turned out the read path was wrong too |
| 2 | `metric_samples` single-layer isolation | **Done** — migration `005`, every org-scoped table now two-layer |
| 3 | `CACHE_DASHBOARD_TTL` defined but unused | **Done** — Redis cache, tenant-scoped, invalidated on write |
| 4 | RAG corpus stuck at 7 chunks | **Done** — 23 chunks, and ingestion can now actually pick up a change |
| 5 | ~80 mypy errors | **Done** — zero, across the whole backend |
| — | *(new)* CI's ruff job was red | **Fixed** — 24 pre-existing violations |
| — | *(new)* Ollama was saturating the machine | **Fixed** — capped, and the real fix documented |
| — | Live multi-cloud billing/metrics | **Deliberately not attempted** — see the end |

---

## 1. The budget: the write path was missing, and the read path was wrong

The carried-forward item was "no API to set `organizations.monthly_budget_usd`".
That was true, but looking at it surfaced something worse.

`ForecastService` had `_DEFAULT_BUDGET = 45_000.0` hardcoded and reported it as the
tenant's budget, while `ForecastAgent` has always read the real per-tenant column. On
the seeded demo — Acme Corp, **$7,500/month** — that put two screens in direct
contradiction:

- **Recommendations page**: *"At current burn rate, this month projects to $8,277
  (10% over the $7,500 budget)."*
- **Forecast page**: budget **$45,000**, verdict **"Within budget"**.

Same data, same month, opposite answers, on adjacent pages. This would have been an
awkward thing to be asked about mid-demo. The service now reads the tenant's budget,
and the two agree exactly: $7,500, over budget, +10.4%.

On top of that:

- `GET`/`PATCH /api/v1/forecast/budget`, admin-only via a new `budget.manage`
  permission — it changes the threshold every overrun alert in the platform is
  measured against, so it belongs with org-wide configuration — and audited with
  the previous and new value.
- The budget is now **nullable end to end** rather than falling back to a number
  nobody chose: with none set the API returns `null`, `over_budget` is false, and the
  UI says "Not set". Making it nullable immediately caught a second spot — the
  forecast chart's budget reference line, which would have drawn at 0 and read as a
  budget of zero that all spend overruns.
- `BudgetUpdate` lost the `warning_threshold_pct` / `danger_threshold_pct` /
  `alerts_enabled` fields it declared. None had a column to be stored in, so
  accepting them would have silently dropped what the caller sent — the API-level
  version of the decorative control the previous session removed from this very page.
  `extra='forbid'` now rejects them outright.
- The Forecast page's budget input, disabled last session for being decorative, is now
  genuinely wired: controlled input, Save button, pending and saved states.

Verified in the browser: the input shows 7500 (not 45000), saving 8600 fires exactly
one PATCH, the value persists, and `budget.update` appears in the audit log.

## 2. `metric_samples` — the last single-layer table

Migration `005` denormalises `organization_id` onto `metric_samples`, on the same
add-nullable → backfill → refuse-on-orphans → NOT NULL pattern as `004`. **Every
org-scoped table is now covered by both isolation layers**; `security.md`'s "still
uncovered" section becomes a record of how it was closed.

Two things worth noting:

- `metric_samples` is RANGE-partitioned by month. All DDL is applied to the parent —
  Postgres propagates `ADD COLUMN`, `SET NOT NULL` and `CREATE INDEX` to every
  partition, and has supported a partitioned→non-partitioned FK since PG12. Verified
  against the dev database's real **24,864 rows across 6 partitions**: all backfilled,
  zero nulls, zero mismatches against the join, and `downgrade` → `upgrade`
  round-trips with no data loss.
- The revision id is abbreviated to `005_metric_samples_org_id` because
  `alembic_version.version_num` is `VARCHAR(32)`. The unabbreviated name is 34
  characters and fails on the version bump *after* the DDL has run — caught on the
  first attempt, and only harmless because Postgres transactional DDL rolled the whole
  migration back cleanly.

`tests/test_tenant_isolation_metrics.py` mirrors the resources suite: every query is
deliberately naive (`select(MetricSample)` with no manual `resource_id` scoping) so it
exercises the ORM guard rather than the service code that was already correct.
Mutation-verified — skipping `MetricSample` in the listener turns 4 of the 5 red (the
fifth asserts the deliberate unbound-scheduler no-op and correctly stays green), with
the join case leaking 6 rows where 3 are in-tenant.

## 3. Dashboard aggregate caching

`CACHE_DASHBOARD_TTL` had been defined and referenced nowhere. The cost summary,
breakdown and timeseries are now cached in Redis under `dashboard:{org}:{name}`.
Measured: `/costs/summary` **~42 ms cold → ~5.5 ms warm**.

`core/cache.py` exists to enforce three properties, all of which matter more than the
speed:

- **Every key is tenant-scoped.** A cache sits *in front of* the ORM tenant filter, so
  a key that wasn't org-scoped would serve one tenant's figures to another without
  `core/tenant.py` ever running. `org_key()` is the only way to build a key.
- **It fails open** — Redis down means a slower correct answer, never an error. This
  is deliberately the opposite of the auth surface's fail-*closed* choice from the
  previous session, and the two are commented against each other so neither reads as
  an oversight.
- **It is invalidated on write, not just on TTL.** Actioning a recommendation changes
  the summary's pending count and savings total; waiting out five minutes would leave
  the KPI row disagreeing with what the user just did. Hooked into recommendation
  status changes, cloud syncs, and agent runs. Verified live: both cached keys vanish
  the instant a recommendation is accepted.

## 4. RAG corpus — and why growing it wasn't enough

The corpus went from **7 to 23 chunks**, covering the ground the Advisor is actually
asked about: budgets and forecasting, investigating a cost spike, rightsizing method,
idle and orphaned resources, commitment discounts, tagging and allocation, storage
tiering, network egress, Kubernetes cost allocation, plus per-provider material for
all three clouds.

Growing it alone would have changed nothing, though. `ingest()` skipped whenever the
collection was non-empty, which made the corpus **effectively immutable after first
boot** — adding an entry would never reach an environment that had already ingested
once, so the stored corpus would sit at 7 while the source file said 23. It now
compares the stored count against the corpus it would write and re-ingests on a
mismatch; `RAGEngine.reset()` is the supporting primitive and `--force` rebuilds
unconditionally.

## 5. Lint and types

Two separate problems, one of them a red build:

- **`ruff check cloudpilot` was failing with 24 violations**, and CI runs exactly that
  command with **no `continue-on-error`** (unlike the mypy step, which has it). So the
  backend CI job had been red on every push — nothing to do with this session's work.
  All auto-fixable: import ordering, the deprecated `datetime.timezone.utc` spelling,
  and three genuinely unused imports.
- **mypy: 94 errors → 0**, across all 85 source files. Mostly mechanical, but three
  needed judgement rather than an annotation:
  - `LLMClient._ollama_generate`/`_openai_generate` now declare `str | None`. They
    genuinely can return None — that is the crash the previous session fixed at the
    `generate()` level — so the annotation had been lying about the exact behaviour
    that bit us.
  - `KNOWLEDGE_BASE` became a `TypedDict`. It was `list[dict[str, str]]` while every
    provider-agnostic entry carries `provider: None`, mistyping a third of the corpus.
  - Two suppressions, both upstream stub gaps rather than our bugs, each with a
    reason: redis-py ships no annotation for `from_url`, and SQLAlchemy types
    `ARRAY.any()` as the relationship-level `PropComparator.any()`.

`make lint` now passes, so the project's own stated rule — *"`make lint && make test`
must pass before opening a PR"* — is satisfiable for the first time.

## 6. Ollama was cooking the machine

Raised mid-session by the machine getting hot, and worth recording because it changes
what can honestly be demoed.

Docker Desktop passes **no GPU through on Apple Silicon**, so the containerized Ollama
runs the 3B model on pure CPU, and it had no resource limits — it takes every core it
can for the length of an inference. Measured on this 8-core M-series machine:

| | |
|---|---|
| One RAG answer, 256 output tokens | **462 s** |
| Same request through the API | 187 s, i.e. **past the 180 s timeout** |
| Whole stack idle, Ollama stopped | ~3.4% CPU, ~520 MB |

So the Advisor was paying the full CPU cost of a request and *still* falling back,
because the answer arrived after the client had given up. Fixed three ways:

- Hard caps on the container (4 CPUs, 3 GB), `OLLAMA_KEEP_ALIVE=60s` so it stops
  holding ~2 GB resident between questions, and `OLLAMA_NUM_PARALLEL=1`.
- `OLLAMA_BASE_URL` is now overridable from `.env` for both backend and scheduler, so
  the stack can point at a **host-run Ollama** — Metal-accelerated, and the only way
  to get genuinely usable Advisor latency on this hardware — with the container
  scaled to zero. Documented in `development.md` and `.env.example`.
- `LLM_MAX_OUTPUT_TOKENS` 512 → 384. The system prompt asks for ~250 words (≈330
  tokens); the rest was headroom that only ever cost generation time.

**For the demo:** everything except the Cloud Advisor works with no Ollama running at
all — the chat returns an explicit "model unavailable" notice rather than a fabricated
answer, which is the designed behaviour. To demo the Advisor live, run Ollama on the
host first.

---

## New findings from this pass

1. **The Forecast page and the Recommendations page disagreed about the budget** — a
   hardcoded $45,000 against the real $7,500. Neither the audit nor the test suite
   caught it because each side was internally consistent; it only shows up when you
   read both screens together.
2. **CI's backend lint job had been failing** on pre-existing ruff violations, with no
   `continue-on-error` to hide it.
3. **RAG ingestion could never pick up a corpus change** after first boot.
4. **`alembic_version.version_num` is `VARCHAR(32)`** — a descriptive revision id can
   exceed it and fail *after* the DDL has run.
5. **The containerized Ollama is not viable on Apple Silicon**, with numbers (§6).

## Still open

- **Live multi-cloud billing/metrics** — deliberately not attempted. Those adapter
  methods raise `NotImplementedError` by design, and implementing them needs real
  cloud credentials to test against; writing them blind and unable to verify would
  reintroduce exactly the "presenting invented figures as a real invoice" risk the
  design exists to avoid.
- **Pricing provenance in the UI** — tracked per-rate in the backend, still not
  surfaced on screen.
- **Frontend e2e tooling** — the browser checks this session and last are ad-hoc
  Playwright scripts, not a committed suite.
- **Backend tests on the host** still need Python 3.11; run them in the container.

## How to reproduce this session's verification

```bash
docker compose up -d postgres redis
docker compose run --rm --no-deps backend alembic upgrade head
docker compose run --rm --no-deps \
  -e CLOUDPILOT_TEST_DB="postgresql+asyncpg://cp:cp@postgres:5432/cloudpilot_test" \
  backend pytest -p no:warnings          # 189 passed

docker compose run --rm --no-deps backend ruff check .        # clean
docker compose run --rm --no-deps backend mypy cloudpilot     # zero issues, 85 files
cd frontend && pnpm exec vitest run && pnpm run typecheck     # 16 passed, clean

# The budget contradiction, before and after:
docker compose exec -T postgres psql -U cp -d cloudpilot \
  -c "SELECT name, monthly_budget_usd FROM organizations;"    # 7500.00
curl -s localhost:8000/api/v1/forecast?horizon_days=30 -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['budget_usd'], d['over_budget'])"
```

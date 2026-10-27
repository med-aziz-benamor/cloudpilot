# Session report — 2026-07-20

A hardening pass closing the highest-priority items from the 14 July audit, plus an
accuracy review of the AI agents. Six commits on `feat/pricing-grounded-simulator`.

Two of the six briefed tasks turned out to rest on assumptions that were wrong. Both
are called out below rather than quietly "fixed".

---

## Summary

| # | Task | Outcome |
|---|------|---------|
| 1 | Production secrets guard | **Already done** (commit `77c84de`, 16 July). No change. |
| 2 | Tenant filter multi-entity bug | **Real bug, fixed.** Narrower than described. |
| 3 | Scheduler tenant context | **Not broken.** Premise wrong; added the missing proof. |
| 4 | RightSizingAgent `node_count` | Correct already; regression tests added. |
| 5 | CostAgent anomaly thresholds | **Clear miscalibration found, recalibrated.** |
| 6 | ArchitectAgent / RAG quality | **Two real bugs, fixed.** |

Backend suite: **107 tests, all passing** (was 83 at session start). Ruff clean on every
file touched.

---

## Task 1 — Production secrets guard

Already implemented on this branch in `77c84de`, and `backend/tests/test_config.py`
already contained all four requested cases (empty-in-prod, placeholder-in-prod,
malformed-in-dev, dev-boots-on-placeholders) plus a production happy path.

`Settings._guard_secrets` names every offending variable at once, and rejects a
malformed `FERNET_MASTER_KEY` in all environments. No change was warranted.

---

## Task 2 — Tenant filter multi-entity bug

**Fixed** in `09f69a9`.

The `do_orm_execute` listener in `core/tenant.py` broke out of its mapper loop after
the first entity carrying `organization_id`, leaving every later org-scoped entity in
the same statement unfiltered.

Two corrections to the brief:

**The example given does not apply.** `Resource` and `BillingEntry` do **not** carry
`organization_id` — they are scoped transitively through `cloud_account_id →
CloudAccount.organization_id`. The listener never touches them in any query. Only
seven models are org-scoped at the column level: `user`, `cloud_account`,
`recommendation`, `chat_session`, `forecast_snapshot`, `agent_run_log`, `audit_log`.
Resource/billing isolation rests entirely on services filtering explicitly — which,
audited, they do correctly (`CostService`/`ResourceService` resolve `account_ids` from
the org first, then constrain by `cloud_account_id.in_(...)`).

**Why it survived so long.** An FK-correlated join masks the bug: once one side is
filtered, `Recommendation.cloud_account_id == CloudAccount.id` transitively constrains
the other. Realistic service queries came back correct. Only uncorrelated multi-entity
selects leak — verified empirically before fixing.

Regression coverage (`tests/test_tenant_isolation.py`) was written first and confirmed
red on both leak directions before the fix. This is the cross-org test the audit
flagged as missing entirely.

---

## Task 3 — Scheduler tenant context

**No production change.** The premise was half right.

True: the scheduler has no request lifecycle, so nothing binds the `ContextVar` and the
ORM tenant filter is a genuine no-op for every query it makes.

False: that the agents are therefore broken. Auditing all three, none has ever relied
on the ContextVar:

| Agent | Scoping |
|-------|---------|
| `CostAgent` | `CloudAccount.organization_id == org`, then `BillingEntry.cloud_account_id.in_(...)` |
| `RightSizingAgent` | same for `Resource`; `MetricSample` keyed by a resource id already proven in-org |
| `ForecastAgent` | `ForecastSnapshot`/`Recommendation` filtered on `organization_id`; `Organization` read by PK |

`sync_scheduler` is account-scoped throughout, and the `/sync` endpoint validates
ownership via `CloudAccountService.get_account` before dispatching — no IDOR.

The requested fix — pass `organization_id` explicitly rather than rely on ambient
context — **is already the implemented design**. Wrapping the loop in a `TenantContext`
would add a second, invisible source of truth without removing the explicit filtering
doing the real work.

What was missing was the proof, so `tests/test_scheduler_isolation.py` now runs
CostAgent for two orgs in one pass with no context bound and asserts each org's
findings reference only its own account, that one tenant's spend never enters
another's baseline, and that an org with no accounts inherits nothing. Verified the
tests have teeth by mutating the agent to drop its org filter — 2 of 3 fail.

The invariant is documented on `_run_for_all_orgs` so it is not "fixed" later.

---

## Task 4 — RightSizingAgent `node_count`

The multiplication was already correct (`rightsizing_agent.py:84-85`). Added tests
pinning it: savings scale linearly at 1, 3 and 4 nodes against the per-node rate delta,
plus the `max(1, ...)` clamp. Mutation-verified — dropping `* nodes` fails 2 of 4.

Audited the rest of the chain for stale single-instance assumptions and found none:
`CloudResourceDTO.node_count` defaults to 1, the simulated adapter and seeder both set
it from fleet quantity, `sync_scheduler` persists it, and `sku_hourly_price` has exactly
one caller. The billing side agrees — `simulation/engine.py` prices by
`billable_quantity`, so a 4-node pool is charged 4x and the saving is quoted on the
same basis.

---

## Task 5 — CostAgent anomaly thresholds

**Recalibrated** in `7f10966`. The suspicion in the brief was correct, and worse than
suspected.

Measured against the seeded estate (16 service series, 60-day lookback):

```
aks-prod-cluster  +166.7 / +151.1 / +151.1 %   z = 4.25-4.68   clears the gate
rds-production    +57.4 % (2 days)             z = 5.12        clears it by 7 points
```

Both incidents surfaced, with zero false positives. But `rds-production` is only **20%
of its service group's spend**, which is why a real 4x event reads as +57%: detection
groups by `(account, service)`, so a physical anomaly on one resource arrives diluted
by its siblings.

The fragility that exposes:

| siblings added | peak pct | z | verdict |
|---|---|---|---|
| 0 | +57.4% | 5.12 | surfaced |
| 1 | +48.4% | 5.12 | **missed** |
| 3 | +36.9% | 5.12 | **missed** |
| 5 | +29.8% | 5.12 | **missed** |

One extra comparable RDS instance makes a genuine 4x incident invisible — while its
Z-score never moves. The percentage was eroding with estate size even though the signal
was not. The old `pct >= 50` gate was calibrated when costs were fabricated
arithmetically (`cost *= 4.4` across a whole series trivially clears any percentage);
physical anomalies do not behave that way.

Sweeping the gate from 50% down to 10% surfaced **zero** additional unexplained
anomalies, so it was buying no noise reduction to pay for those misses.

Now `_MIN_PCT_ABOVE_BASELINE = 25.0` paired with `_MIN_DELTA_USD = 5.0`. The absolute
floor is what actually expresses "material" — a 3x spike on a $2/day service is noise
at any percentage — and having it lets the relative gate come down safely. Both seeded
incidents ($80/day and $13/day deltas) clear it with room. Constants are named and the
evidence is recorded at the definition.

---

## Task 6 — ArchitectAgent / RAG quality

**Two real bugs**, fixed in `d155dbb`. Measured with Ollama and ChromaDB running against
the seeded estate.

**The query cache memoised its own failures.** `retrieve()` cached whatever it produced,
unconditionally, and the cache has no TTL — so anything stored during an outage was
served as fresh for the process lifetime. Two paths reached it: a Chroma query that
threw (`results = []`, cached), and an embedding that fell back to the hash stub when
Ollama was unreachable (a meaningless vector, whatever it matched cached as if real).
A transient blip left the Advisor permanently ungrounded until restart.

Worth stating precisely, since the brief asked: model *answers* were never cached —
`generate()` has no cache — so serving a stale "model unavailable" reply was not
possible. The retrieval cache was the one carrying the hazard.

**Retrieval had no relevance floor.** It returned the top-k however bad k was, and chat
renders those as citation chips. *"What is the capital of France?"* came back with five
authoritative-looking sources about AKS node pools. Best-match cosine distance separates
cleanly:

```
Why did my Azure costs spike last month?   0.2546
Is my Azure AKS cluster correctly sized?   0.3097
How do I reduce S3 storage costs?          0.4231
asdfgh qwerty zxcvbn                       0.5567
What is the capital of France?             0.6587
```

Chunks beyond `MAX_COSINE_DISTANCE = 0.55` are now dropped. Live verification:
on-domain queries keep 3–5 chunks; off-domain and gibberish return none, and are not
cached, so ingesting missing docs fixes them.

**On k:** deliberate, not a leftover — `k=5` is explicit at the single call site and
matches ArchitectAgent's docstring. But it is mis-scaled against a **7-chunk corpus**:
returning 5 of 7 means ranking barely discriminates, which is why every query returned
almost the same set. That is a corpus-size problem, not a k problem, and was left as an
open item rather than papered over by tuning k.

**Latency** (M-series, CPU-only):

| Operation | Cold | Warm |
|---|---|---|
| Retrieval | 0.11s | 0.04–0.06s |
| Cached retrieval | — | ~0s |
| Generation (end-to-end) | 97.3s | 32.8s |

The cold generation confirms the earlier 30s → 180s timeout fix was necessary rather
than precautionary: at 30s that query would have fallen through to the offline stub,
which is exactly the "bad answer, not a failure" symptom from 14 July.

---

## Still open

1. **RAG corpus is 7 chunks.** The real constraint on Advisor quality. Until it grows,
   `k=5` returns most of the corpus regardless of the question and citations are weak
   evidence. Grow the corpus before tuning retrieval further.
2. **`Resource` / `BillingEntry` have no `organization_id`.** The ORM tenant filter
   cannot protect them; they depend entirely on services filtering correctly. Services
   currently do, and Task 3's tests cover the agent paths, but the defence-in-depth the
   security doc claims does not extend to the two largest tables. Denormalising
   `organization_id` onto them is a schema change and was out of scope for a hardening
   pass — worth a decision.
3. **Dashboard aggregate cache** still unbuilt (`CACHE_DASHBOARD_TTL` unused).
4. **Frontend never clicked through** — still only ever confirmed to HTTP 200.
5. **Org budget** has no API/UI (`organizations.monthly_budget_usd`, seeder only).
6. **Ollama volume mount** in `docker-compose.yml` is still a hardcoded machine-specific
   path; documented as a known issue but not fixed.
7. **Seeded recommendations predate the recalibration** — the dev database holds 17
   recommendations produced under the old gates. Re-run `make seed` to regenerate
   against the new thresholds.

---

## How to run what changed

```bash
docker compose up -d postgres
docker compose exec -T postgres psql -U cp -d postgres -c "CREATE DATABASE cloudpilot_test;"

# full suite including the new DB-backed tests
docker compose run --rm --no-deps \
  -e CLOUDPILOT_TEST_DB="postgresql+asyncpg://cp:cp@postgres:5432/cloudpilot_test" \
  backend pytest -q
```

The DB-backed files (`test_tenant_isolation.py`, `test_scheduler_isolation.py`,
`test_rightsizing_node_count.py`) skip cleanly when `CLOUDPILOT_TEST_DB` is unset, so
the default suite still runs anywhere.

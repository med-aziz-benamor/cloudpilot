# Session report — 2026-08-05: status check, zero new commits

A status audit, not a development session. No code was changed. This verifies, against
the running system rather than against the docs, everything that happened between the
14 July audit and today, and what is still open.

**Headline finding: nothing has happened since the last session.** `HEAD` on
`feat/pricing-grounded-simulator` is still `0f136c1`, the exact commit that closed the
[20 July "b" report](session-report-2026-07-20b.md), 16 days ago. Zero commits, zero
branches, zero open work landed in between.

---

## 1. Commits since 20 July

`git log --since="2026-07-20" --all` returns 10 commits — but all 10 are dated
**20 July, between 10:24 and 11:08**, i.e. they are the same six-commit hardening pass
plus the four-commit follow-up already written up in the two existing reports. There is
no commit newer than `0f136c1`.

| Commit | What it did |
|---|---|
| `6f75cd1` | Fixed a wrong Ollama model tag in `.env.example` |
| `da566a1` | Docs: corrected stale claims, documented pricing/secrets work |
| `09f69a9` | **Fix:** tenant filter listener stopped after the first org-scoped entity in a statement, leaving later entities in the same query unfiltered |
| `35793e8` | **Test:** proved the scheduler cannot leak spend across orgs (it never relied on the ambient tenant context to begin with) |
| `53c4e99` | **Test:** pinned the `node_count` multiplier on RightSizingAgent's downsize savings |
| `7f10966` | **Fix:** recalibrated CostAgent's anomaly gate from a bare 50% threshold to `pct >= 25% AND delta >= $5`, after finding the old gate missed a genuine 4x incident once one sibling resource was added to its comparison group |
| `d155dbb` | **Fix:** RAG retrieval cache was memoizing its own failures (empty results, hash-stub embeddings) with no TTL; added a cosine-distance floor (`0.55`) so off-topic queries stop returning confident-looking citations |
| `5337baa` | Docs: `docs/session-report-2026-07-20.md`, and corrected `security.md`'s overstated tenant-isolation claim |
| `4a3598d` | **Feat:** denormalized `organization_id` onto `resources` and `billing_entries` (migration `004`), closing the gap `5337baa` had just documented |
| `0f136c1` | Docs: `docs/session-report-2026-07-20b.md` |

Full commit-by-commit detail is already in
[`session-report-2026-07-20.md`](session-report-2026-07-20.md) and
[`session-report-2026-07-20b.md`](session-report-2026-07-20b.md); this table exists so
this report is self-contained. Nothing below repeats that narrative — it verifies the
end state against the live repo, database, and test suite instead of trusting the docs.

---

## 2. Test suite

Ran inside Docker (host pytest still fails on the system's Python 3.14):

```
docker compose up -d postgres
docker compose run --rm --no-deps backend alembic upgrade head
docker compose run --rm --no-deps \
  -e CLOUDPILOT_TEST_DB="postgresql+asyncpg://cp:cp@postgres:5432/cloudpilot_test" \
  backend pytest -p no:warnings -q
```

**116 tests, all passing, exit code 0.** Same as the `4a3598d`/"b"-session count — expected,
since no test file has changed. This is **not** the 107 baseline from the 20 July
morning report; that number was superseded the same day by the `organization_id`
denormalization, which added the 9-test `test_tenant_isolation_resources.py` file
(107 + 9 = 116).

---

## 3. Status of the 20 July "on the horizon" items

### `make seed` re-run under the recalibrated thresholds — **not done**

Queried the dev database directly:

```
recommendations: 17 rows, all created_at = 2026-07-20 10:04:49.719
  by agent: RIGHTSIZING 11, COST 5, FORECAST 1
resources:       50
billing_entries: 4292
```

`10:04:49` is *before* `7f10966` (10:34, the anomaly-gate recalibration) and before
`d155dbb` (10:46, the RAG fixes). The 5 `COST`-agent recommendations currently sitting
in the database were generated under the **old** `pct >= 50%` gate, not the new
`pct >= 25% AND delta >= $5` one — they predate the fix that was supposed to make them
correct. `make seed` was flagged as the very next step in the 07-20 report and has not
been run since. Resource/billing counts (50 / 4292) match the "b" report's backfill
table exactly, confirming the dataset itself hasn't been touched either, just left stale.

### `organization_id` denormalization — **done, verified in the live tree**

- Migration `backend/alembic/versions/004_denormalize_organization_id.py` present, and
  `alembic upgrade head` runs clean against the current dev database.
- `Resource.organization_id` and `BillingEntry.organization_id` are declared NOT NULL
  with indexes `ix_resources_org` / `ix_billing_org_date`
  (`backend/cloudpilot/models/resource.py:36`, `billing_entry.py:38`).
- `core/tenant.py`'s `do_orm_execute` listener applies to both — confirmed by reading
  the mapper loop, not just by the docs' claim.
- `backend/tests/test_tenant_isolation_resources.py` — 9 tests, all passing in the run
  above, covering naive queries, IDOR-shaped lookups, aggregates, and joins across both
  tables.

This item is genuinely closed. It's also the one piece of "on the horizon" work that
*did* get done — just 16 days before this report, not since it.

### RAG corpus — **still 7 chunks, unchanged**

`backend/cloudpilot/ai/rag/ingestor.py`'s `KNOWLEDGE_BASE` list has exactly 7 entries
(2 Azure, 2 AWS, 1 GCP, 2 FinOps Foundation), each short enough to produce exactly one
chunk. `git log` on that file shows only the initial scaffold commit — it has never
been edited, including during the 20 July RAG-quality pass that flagged the corpus size
as the real constraint on Advisor quality. `k=5` against 7 chunks is still barely
discriminating.

### Provenance/citations in UI — **already fully implemented, not new**

`ArchitectAgent._build_citations` (`architect_agent.py:133`) returns up to 5 citations
per answer; `ChatBubble.tsx` renders them as numbered chips with source/section. Wiring
traces cleanly from RAG retrieval → chat API → frontend. `git log` on `ChatBubble.tsx`
and `CitationChip.tsx` shows only the initial scaffold commit — this was never an open
item in the first place, it just wasn't explicitly confirmed working end-to-end before.

### Budget-setting API/UI — **still no write path, and the UI is decorative**

Grepped every `backend/cloudpilot/api/v1/*.py` file for `budget`: zero matches.
`monthly_budget_usd` is read in `forecast_service.py`/`forecast_agent.py` and rendered
in the forecast response — read-only. On the frontend, `ForecastPage.tsx:97-101` renders
a `<input type="number" defaultValue={data.budget_usd}>` with no `onChange`, no state,
and no submit button — it cannot actually change anything a user types into it. This
is worth flagging as slightly worse than "no UI": there's a control that looks
functional and silently does nothing.

### Frontend visual QA — **still HTTP-200-only**

No Playwright, Cypress, or other browser-driving test tool in the repo
(`frontend/package.json` has no e2e script, `find` turns up no `*.spec.ts` /
`*cypress*` files). Unchanged from 20 July.

### RBAC / tenant-isolation test coverage — **tenant-isolation side is strong, RBAC side has none**

Tenant isolation: 9 + 9 dedicated tests across `test_tenant_isolation.py` and
`test_tenant_isolation_resources.py`, both mutation-verified (the July reports document
deliberately breaking the listener and confirming the tests go red).

RBAC: `core/rbac.py`'s `PERMISSIONS` matrix gates 5 endpoint groups
(`recommendations.write`, `chat.use`, `cloud_accounts.manage`, `users.manage`,
`audit.read`) via `role_has_permission`/`require_roles`, used in `deps.py` and four
`api/v1/*.py` route files. **No test file references `role_has_permission`,
`require_roles`, a 403, or `UserRole.VIEWER`/`ANALYST` anywhere in `backend/tests/`.**
`test_auth.py` covers password hashing and token round-trips only. This is a real,
previously-undocumented gap: the permission matrix is exercised in production code
paths but has zero coverage proving a viewer is actually blocked from, say,
`cloud_accounts.manage`.

---

## 4. New features, endpoints, or agents

**None.** Confirmed by listing `backend/cloudpilot/ai/*.py` (still exactly `cost_agent`,
`rightsizing_agent`, `forecast_agent`, `architect_agent` plus the shared `base_agent`)
and `backend/cloudpilot/api/v1/*.py` (`auth`, `cloud_accounts`, `forecast`,
`recommendations`, `chat`, `admin`, `costs`, `resources` — same set as before). Nothing
was added because nothing was committed.

---

## 5. New bugs / findings from this pass

1. **Seeded `COST` recommendations are stale against the fix that was supposed to
   correct them.** 5 of the 17 recommendations in the dev database were generated
   under the pre-recalibration 50%-only anomaly gate, 30 minutes before `7f10966`
   changed it. They are exactly the artifact item 7 of the 07-20 report warned about,
   and remain unaddressed.
2. **The budget input on the Forecast page is non-functional, not just unimplemented.**
   It renders as an editable field with no wiring — worse for a demo than omitting it,
   since it invites a click that does nothing.
3. **RBAC has no regression tests at all**, despite gating five permission-sensitive
   endpoint groups in production code. This sits next to a tenant-isolation suite that
   is unusually thorough (mutation-verified, 18 tests) — the two layers of authorization
   described in `core/rbac.py`'s own module docstring ("FIRST layer... SECOND, redundant
   layer is the tenant filter") are asymmetrically tested.

No new architectural issues were found beyond what the existing docs already flagged
(`metric_samples` still single-layer, `CACHE_DASHBOARD_TTL` still unused, the Ollama
volume mount is still a hardcoded machine path) — all reconfirmed unchanged in the
current tree.

---

## 6. Still open (carried forward, re-verified)

1. `make seed` needs re-running so the 5 stale `COST` recommendations reflect the
   current anomaly gate (§3).
2. RAG corpus is still 7 chunks — the real ceiling on Advisor answer quality.
3. Budget-setting has no backend write endpoint; the frontend control should either be
   wired up or removed until it is.
4. No RBAC test coverage — new finding, not in either prior report.
5. No frontend e2e/visual test tooling.
6. `metric_samples` still has no `organization_id` (single-layer isolation via
   `resource_id`, documented as deliberate scope-out of migration `004`).
7. `CACHE_DASHBOARD_TTL` declared, unused. Ollama volume mount still machine-specific.

---

## How to reproduce this check

```bash
git log --oneline --since="2026-07-20" --all   # confirms HEAD == 0f136c1, no new work

docker compose up -d postgres
docker compose run --rm --no-deps backend alembic upgrade head
docker compose run --rm --no-deps \
  -e CLOUDPILOT_TEST_DB="postgresql+asyncpg://cp:cp@postgres:5432/cloudpilot_test" \
  backend pytest -p no:warnings -q          # 116 passed

docker compose exec -T postgres psql -U cp -d cloudpilot \
  -c "SELECT agent, count(*), min(created_at) FROM recommendations GROUP BY agent;"
```

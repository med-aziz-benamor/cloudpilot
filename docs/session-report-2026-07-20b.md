# Session report — 2026-07-20 (b): tenant isolation, second layer

Follow-up to [`session-report-2026-07-20.md`](session-report-2026-07-20.md), which found
that `resources` and `billing_entries` carried no `organization_id` and were therefore
invisible to the ORM tenant listener. One commit: `4a3598d`.

Backend suite: **116 tests, all passing** (was 107). Ruff clean on every file touched.

---

## What changed

### Migration `004_denormalize_organization_id`

Adds `organization_id` to both tables in three steps, in this order:

1. **Add nullable** — existing rows stay valid.
2. **Backfill** from `cloud_accounts.organization_id` via `cloud_account_id`.
3. **Apply NOT NULL**, plus an FK to `organizations` (`ON DELETE CASCADE`) and the
   indexes the filter will use: `ix_resources_org`, `ix_billing_org_date`
   (organization first, since it now leads nearly every read).

Step 2 **refuses to continue** if any row cannot be traced to an organization. It
raises with the count and a sample of `(id, cloud_account_id)` rather than defaulting.
An untraceable row means the data is already inconsistent, and picking an owner would
invent a tenancy claim — precisely what this column exists to prevent.

Applied against the dev database, which holds real seeded data:

| Table | Rows | Backfilled | NULL | Mismatched vs. the join |
|---|---|---|---|---|
| `resources` | 50 | 50 | 0 | 0 |
| `billing_entries` | 4292 | 4292 | 0 | 0 |

**No orphans found** — nothing to report under the stop-and-report instruction.
`downgrade` → `upgrade` round-trips cleanly and re-backfills to 0 nulls.

### Write paths

Audited by grepping the constructors. Four sites, all updated to set the column
directly rather than leaning on the join:

- `mock_data._seed_resources` / `_seed_billing`
- `sync_scheduler._sync_resources` / `_sync_billing`

`FleetResource` in `simulation/fleet.py` matches the grep but is a different dataclass
(the simulated estate, not the ORM model) and needed no change.

Verified by running the seeder end to end rather than by inspection: 50 resources and
4292 billing rows written, every one populated, zero mismatches against the join, and
all three agents ran clean afterwards.

### Tenant listener

Verified explicitly rather than assumed. With the column present and the multi-mapper
fix from the previous session in place, `do_orm_execute` now appends
`WHERE organization_id = :current_org` to statements against both tables — confirmed by
the naive-query tests below, and by the live check that a correctly-scoped service call
still returns nothing under a mismatched context.

---

## Regression tests

`tests/test_tenant_isolation_resources.py`, 9 tests. Every query is **deliberately
naive** — `select(Resource)` with no `cloud_account_id.in_(...)` — because the point is
to exercise the ORM guard in isolation from the service-layer filtering that was
already correct.

| Test | What it pins |
|---|---|
| `test_naive_resource_query_is_scoped` | bare `select(Resource)` returns only org A |
| `test_naive_resource_query_scoped_for_other_org` | symmetric for org B, so it is not passing by luck |
| `test_resource_get_by_id_across_tenants_returns_nothing` | the IDOR shape — caller already knows the id |
| `test_resource_aggregate_is_scoped` | `COUNT` does not leak the other tenant's row count |
| `test_naive_billing_query_is_scoped` | bare `select(BillingEntry)` returns only org A |
| `test_billing_sum_is_scoped` | `SUM` returns $20, not the $40 an unfiltered query would report |
| `test_resource_billing_join_is_scoped_on_both_sides` | both tables joined, neither side contributes |
| `test_uncorrelated_two_table_select_is_scoped` | the cartesian shape that exposed the old `break` bug |
| `test_no_context_sees_everything` | unbound context still spans tenants — the seeder and scheduler need this |

### Confirming the tests have teeth

Mutated `core/tenant.py` to skip `resources` and `billing_entries`, reproducing the
pre-`004` blindness exactly (before the migration the listener skipped them because
they had no column; the mutation makes it skip them despite having one):

```
FAILED test_naive_resource_query_is_scoped
FAILED test_naive_resource_query_scoped_for_other_org
FAILED test_resource_get_by_id_across_tenants_returns_nothing
FAILED test_resource_aggregate_is_scoped
FAILED test_naive_billing_query_is_scoped
FAILED test_billing_sum_is_scoped
FAILED test_resource_billing_join_is_scoped_on_both_sides
FAILED test_uncorrelated_two_table_select_is_scoped
```

**8 of 9 fail.** The survivor is `test_no_context_sees_everything`, which asserts the
unbound case and correctly passes either way. Mutation reverted.

### The layer demonstrated live

Beyond the unit tests, against the seeded dev database:

```
resources listed (correct bound org):     50
resources under WRONG bound org:           0   <- listener overrides service filter
```

`ResourceService.list_resources()` was called with org A's id — its own explicit filter
was correct — and still returned nothing because the ambient context said otherwise.
That is the second layer doing its job: a service being right is no longer what stands
between tenants.

Services otherwise behave normally under the correct context (MTD $5,376.32, 3
providers, 15 services, 4 regions, 90 timeseries points, 50 resources), so the added
filter costs nothing in normal operation.

### Existing tests updated

`test_scheduler_isolation.py` and `test_rightsizing_node_count.py` construct these rows
directly and now fail the NOT NULL constraint without the column. Both fixtures updated
— fixtures only, no assertion changes.

---

## Docs

`security.md`'s "What layer 2 does not cover" is now "What layer 2 covers", rewritten
rather than reverted: nine models carry the column, the two largest joined the list in
`004`, and the redundancy is explained as the mechanism that makes a forgetful service
survivable. The honest caveats that remain are kept — `metric_samples` is still
single-layer, and the scheduler's no-op is still documented as deliberate.

---

## Still open

1. **`metric_samples` has no `organization_id`.** Same class of problem, scoped through
   `resource_id`. Isolation there is still single-layer, via callers constraining on
   resource ids already proven in-org (`RightSizingAgent._p95`,
   `ResourceService.get_resource`). Left out of `004` deliberately to keep the migration
   scoped; it is the obvious next step. Note the table is range-partitioned by month, so
   the migration is not a copy of `004`.
2. **Redundancy is not self-enforcing.** Nothing stops a future write path setting an
   `organization_id` that disagrees with its `cloud_account_id`. A composite FK
   `(cloud_account_id, organization_id)` against a matching unique key on
   `cloud_accounts`, or a periodic consistency check, would close that. Currently the
   only guarantee is that all four write paths derive the value from
   `account.organization_id`.
3. Items 3–7 from the previous report are unchanged.

---

## Running it

```bash
docker compose up -d postgres
docker compose run --rm --no-deps backend alembic upgrade head

docker compose run --rm --no-deps \
  -e CLOUDPILOT_TEST_DB="postgresql+asyncpg://cp:cp@postgres:5432/cloudpilot_test" \
  backend pytest -p no:warnings -q
```

Existing deployments need `alembic upgrade head` before the new code runs — the models
declare the column NOT NULL, so writes fail against an unmigrated database.

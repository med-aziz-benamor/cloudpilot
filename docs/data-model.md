# CloudPilot — Data Model

PostgreSQL 16 is the system of record. The schema is defined by SQLAlchemy 2.0 models in
`backend/cloudpilot/models/` and evolved **only** through Alembic migrations in
`backend/alembic/versions/`. Redis and ChromaDB hold caches and embeddings, never
primary data.

## Entity–relationship overview

```
                              ┌──────────────────┐
                              │  organizations   │  tenant root · plan · monthly_budget_usd
                              └────────┬─────────┘
          ┌──────────────┬─────────────┼──────────────┬───────────────┬──────────────────┐
          ▼              ▼             ▼              ▼               ▼                  ▼
     ┌─────────┐  ┌──────────────┐ ┌──────────────┐ ┌───────────────┐ ┌────────────────┐ ┌───────────┐
     │  users  │  │cloud_accounts│ │recommendations│ │forecast_      │ │ agent_run_logs │ │ audit_log │
     └────┬────┘  └──────┬───────┘ └──────────────┘ │snapshots      │ └────────────────┘ └───────────┘
          │              │                          └───────────────┘
          ▼              ▼
   ┌─────────────┐ ┌───────────┐
   │chat_sessions│ │ resources │──────────────┐
   └──────┬──────┘ └─────┬─────┘              │
          ▼              ▼                    ▼
   ┌─────────────┐ ┌────────────────┐  ┌────────────────────────────┐
   │chat_messages│ │billing_entries │  │ metric_samples             │
   └─────────────┘ └────────────────┘  │ (RANGE-partitioned by month)│
                                       └────────────────────────────┘
```

Every table except `metric_samples` inherits `id` (UUID v4), `created_at` and
`updated_at` from `BaseModel` (`database.py`). All foreign keys to `organizations`
cascade on delete, so removing a tenant removes all of its data.

## Tables

### `organizations` — the tenant

| Column | Type | Notes |
|---|---|---|
| `name` | varchar(120) | |
| `plan` | enum `free` · `pro` · `enterprise` | |
| `monthly_budget_usd` | numeric, **nullable** | added in `003`. Null means "no budget set": the ForecastAgent skips its overrun check and the UI shows "Not set" |

### `users`

| Column | Type | Notes |
|---|---|---|
| `organization_id` | FK → organizations | |
| `email` | varchar(255), unique | |
| `password_hash` | varchar(255) | bcrypt |
| `role` | enum `admin` · `analyst` · `viewer` | drives RBAC, see [security.md](security.md) |
| `mfa_enabled`, `mfa_secret_enc` | bool, text | reserved for MFA; the columns exist but no login flow uses them yet |
| `last_login_at`, `is_active` | | |

### `cloud_accounts` — a connected Azure subscription, AWS account or GCP project

| Column | Type | Notes |
|---|---|---|
| `organization_id` | FK → organizations | |
| `provider` | enum `azure` · `aws` · `gcp` | |
| `account_identifier`, `display_name` | | unique per `(organization, provider, account_identifier)` |
| `credentials_enc` | text | **Fernet-encrypted**; never returned by the API |
| `status` | enum `active` · `error` · `paused` | |
| `last_synced_at`, `error_message` | | set by the hourly cloud sync |

### `resources` — the inventory

| Column | Type | Notes |
|---|---|---|
| `organization_id` | FK → organizations | denormalised in `004` for the tenant filter |
| `cloud_account_id` | FK → cloud_accounts | |
| `provider_resource_id` | varchar(512) | the provider's own id / ARN |
| `name`, `service`, `region` | | |
| `sku` | nullable | the priced unit, e.g. `Standard_D4s_v3` |
| `node_count` | int, default 1 | added in `002`; node pools are priced per node |
| `tags_json` | JSONB | |
| `is_active`, `last_seen_at` | | |

### `billing_entries` — daily cost lines

| Column | Type | Notes |
|---|---|---|
| `organization_id` | FK → organizations | denormalised in `004` |
| `cloud_account_id` | FK → cloud_accounts | |
| `resource_id` | FK → resources, nullable (`SET NULL`) | |
| `usage_date` | date | |
| `service` | varchar(80) | |
| `cost_usd` | numeric(12,4) | in demo mode, always `published_rate × simulated_usage` |
| `raw_currency`, `raw_amount` | | the provider's original figure before conversion |

Indexed on `(cloud_account_id, usage_date)`, `(resource_id, usage_date)` and
`(organization_id, usage_date)`, the access paths used by the cost dashboards and agents.

### `metric_samples` — utilisation time series

| Column | Type | Notes |
|---|---|---|
| `organization_id` | FK → organizations | denormalised in `005` |
| `resource_id` | FK → resources | |
| `metric_name` | varchar(80) | e.g. `cpu_percent`, `memory_percent` |
| `timestamp` | timestamptz | |
| `value`, `unit` | | |

The primary key is `(resource_id, metric_name, timestamp)`, with no surrogate id, because
the table is **RANGE-partitioned by month on `timestamp`**, and a partitioned table's
primary key must include the partition column. Migration `001` creates monthly partitions
`cloudpilot_metrics_2026_05` through `cloudpilot_metrics_2026_09` plus a `DEFAULT`
partition that catches anything outside them. It is the largest table, and partitioning
lets old months be dropped wholesale. Rows past September 2026 land in `DEFAULT` until
new monthly partitions are added in a migration.

### `recommendations` — agent findings

| Column | Type | Notes |
|---|---|---|
| `organization_id` | FK → organizations | |
| `cloud_account_id` | FK, nullable | null for org-wide findings such as budget overruns |
| `agent` | enum `cost` · `rightsizing` · `forecast` · `architect` | |
| `title`, `description` | | human-readable finding |
| `estimated_saving_usd` | numeric, nullable | null when no saving applies, as for budget alerts |
| `confidence` | float 0–1 | |
| `status` | enum `pending` · `accepted` · `rejected` · `snoozed` | |
| `snoozed_until` | timestamptz | |
| `affected_resource_ids` | UUID[] | |
| `metadata_json` | JSONB | **the calculation basis** (rates, provenance, baseline, Z-score…), rendered in the UI. Exposed by the API as `metadata` |

See [ai-agents.md](ai-agents.md) for what each agent writes into `metadata_json`.

### `forecast_snapshots`

| Column | Type | Notes |
|---|---|---|
| `organization_id` | FK | |
| `snapshot_date` | date | |
| `horizon_days` | int | 30, 60 or 90 |
| `forecast_json` | JSONB | `dates`, `yhat`, `yhat_lower`, `yhat_upper`, `trend` |

Unique per `(organization_id, snapshot_date, horizon_days)`; the ForecastAgent upserts.

### `chat_sessions` and `chat_messages` — the Cloud Advisor

| Table | Key columns |
|---|---|
| `chat_sessions` | `organization_id`, `user_id`, `title`, `is_archived` |
| `chat_messages` | `session_id` (cascade), `role` (`user` · `assistant` · `system`), `content`, `citations_json`, `tool_calls_json`, `tokens_used` |

### `agent_run_logs` — agent observability

`agent`, `organization_id`, `started_at`, `finished_at`, `status` (`running` · `success`
· `failed`), `recommendations_created`, `error_message`. Written by
`AgentBase.run_with_logging()` for every scheduled or manual run.

### `audit_log` — tamper-evident trail

| Column | Notes |
|---|---|
| `organization_id`, `actor_user_id` | who |
| `event_type`, `resource_type`, `resource_id` | what |
| `payload_json` | detail, e.g. the previous and new budget |
| `ip_address` (INET), `user_agent` | where from |
| `signature` | `SHA-256(previous_signature + canonical_row)` |

Append-only and hash-chained from a 64-zero genesis, so editing any past row breaks every
later signature. `GET /api/v1/admin/audit-log/verify` recomputes the chain.

## Multi-tenancy in the schema

Every org-scoped table **declares its own `organization_id` column**: ten tables in
total. That is what makes the second isolation layer possible. The SQLAlchemy listener in
`core/tenant.py` appends `WHERE organization_id = :current_org` to every SELECT, but it
can only see columns on the entity being queried; it cannot follow a join.

`resources`, `billing_entries` and `metric_samples` were originally scoped only
transitively, through their cloud account or resource. Migrations `004` and `005`
denormalised the column onto them so the listener engages directly. The full reasoning
is in [security.md → What layer 2 covers](security.md#what-layer-2-covers).

## Migration history

| Migration | Change | Why |
|---|---|---|
| `001_initial_schema` | The full schema, including the partitioned `metric_samples` | Initial scaffold |
| `002_resource_node_count` | `resources.node_count` (default 1) | Node pools were priced as a single node |
| `003_org_monthly_budget` | `organizations.monthly_budget_usd`, nullable | Replace a hardcoded budget shared by every tenant |
| `004_denormalize_organization_id` | `organization_id` on `resources` and `billing_entries` | Two-layer tenant isolation on the largest tables |
| `005_metric_samples_org_id` | `organization_id` on `metric_samples` | Close the last single-layer table |

`004` and `005` follow the same safe pattern: **add nullable → backfill from the owning
row → refuse to continue if any orphan remains → set NOT NULL**. A migration that cannot
backfill every row stops with an error instead of guessing a tenant.

```bash
make migrate                                              # upgrade to head
docker compose exec backend alembic revision -m "describe change"   # new migration
```

## Demo dataset

`make seed` (`utils/mock_data.py` + `simulation/`) creates one organization (Acme Corp,
$7,500/month budget), three cloud accounts, **50 resources** (22 Azure · 18 AWS · 10 GCP),
**90 days** of billing priced from the committed rate card, **14 days** of CPU/RAM
samples and three chat sessions. It then runs the real Cost, RightSizing and Forecast
agents, so every recommendation in the demo is genuine agent output. The simulation is
seeded per resource name, so re-seeding reproduces the same estate.

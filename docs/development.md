# CloudPilot — Development Guide

## Local setup (step by step)

1. **Clone & env**
   ```bash
   cd cloudpilot
   cp .env.example .env
   ```
2. **Start the stack**
   ```bash
   make dev      # postgres, redis, chromadb, ollama, backend, scheduler, frontend
   ```

   The `ollama` service stores its models in a named Docker volume
   (`ollama_models`), so this works unmodified on any machine. Pull the models
   once the stack is up:
   `docker compose exec ollama ollama pull qwen2.5:3b && docker compose exec ollama ollama pull nomic-embed-text`.
3. **Seed demo data** (second terminal)
   ```bash
   make seed
   ```
4. Open http://localhost:5173 and sign in with `demo@cloudpilot.dev` / `demo1234`.

### Running the backend without Docker

```bash
cd backend
poetry install
cp .env.example .env   # set localhost hosts
poetry run alembic upgrade head
poetry run uvicorn cloudpilot.main:app --reload
poetry run python -m cloudpilot.utils.mock_data    # seed
poetry run python -m cloudpilot.ai.orchestrator    # scheduler (optional)
```

### Running the frontend without Docker

```bash
cd frontend
pnpm install
pnpm dev
```

## Running tests

```bash
# Backend — run inside the container (this is the supported path)
docker compose exec backend pytest -q

# Frontend
cd frontend && pnpm test --run

# Everything (backend in-container + frontend on host)
make test
```

The backend tests need no database or running infra, but they **do** need the project's
dependency set on **Python 3.11** (`pyproject.toml` pins `^3.11`, mypy targets 3.11).
Running `poetry run pytest` on a host with a newer interpreter fails at collection —
Python 3.14 has no wheels for `scikit-learn`/`prophet`, so `poetry install` never
completes and every test module dies on a missing import. Use the container, or create
the venv against a real 3.11:

```bash
cd backend && poetry env use 3.11 && poetry install && poetry run pytest -q
```

## Linting & types

```bash
make lint        # ruff + mypy (backend), eslint (frontend)
make typecheck   # mypy + tsc
make format      # ruff format + eslint --fix
```

## Making a new migration

```bash
docker compose exec backend alembic revision -m "describe change"
# edit backend/alembic/versions/<id>_describe_change.py
make migrate
```

Schema changes go through Alembic only — never hand-written SQL against the DB.

## Adding a new cloud provider adapter

1. Create `backend/cloudpilot/cloud/<provider>_adapter.py` implementing
   `CloudProviderAdapter` (`get_resources`, `get_billing`, `get_metrics`,
   `validate_credentials`). Fall back to deterministic mock data when `self.demo_mode`.
2. Register it in `cloud/base.get_adapter`.
3. Add the provider to the `CloudProvider` enum + a new Alembic migration.
4. Add a mock blueprint in `utils/mock_data.py` and wizard fields in
   `frontend/src/pages/settings/ConnectCloudPage.tsx`.

## Refreshing the pricing snapshot

Costs are `published_rate × simulated_usage`, and the rate card is a committed snapshot
at `backend/cloudpilot/pricing/data/pricing_snapshot.json` — not a live lookup. Refresh
it when rates drift:

```bash
make pricing        # Azure Retail Prices API (live) + AWS/GCP published list prices
make pricing-deep   # also pulls AWS's bulk offer files (tens of MB, slow)
```

Both are keyless — no cloud account or spend required. Commit the regenerated snapshot:
a pinned rate card is what makes the seeded dataset reproducible. Re-seed afterwards
(`make seed`) so billing rows are recomputed against the new rates.

Adding a SKU means adding it to the snapshot **and**, if right-sizing should be able to
recommend shrinking it, adding a downsize pair in `pricing/catalog.py`. Each hop must be
a genuine halving within the same instance family, or the "saving" is meaningless.

## Adding a new AI agent

1. Subclass `AgentBase` in `backend/cloudpilot/ai/<name>_agent.py`; implement `run()`
   (and `trigger()` if on-demand). Pull real data, apply the algorithm, write
   `Recommendation` rows, log with loguru.
2. Add the agent to the `AgentType` enum (migration) and `AGENT_META` on the frontend.
3. Register it in `ai/orchestrator.build_scheduler` (for scheduled agents) and/or
   `api/v1/admin._AGENTS` for manual triggering.

## Code style

- **Backend** — snake_case files, PascalCase classes, strict mypy, Google-style
  docstrings, loguru (never `print`), everything async.
- **Frontend** — PascalCase components, camelCase hooks/utils, strict TS (no `any`),
  Tailwind utilities only, `@/` import alias.
- **Commits** — conventional commits; branches `feature/…`, `fix/…`, `chore/…`.

## Serving docs locally

```bash
make docs    # http://localhost:8080
```

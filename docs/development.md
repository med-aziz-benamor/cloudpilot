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
# Backend (unit tests run with no DB/infra needed)
cd backend && poetry run pytest -q

# Frontend
cd frontend && pnpm test --run

# Everything
make test
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

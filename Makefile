# ═══════════════════════════════════════════════════════════════
# CloudPilot — developer shortcuts
# ═══════════════════════════════════════════════════════════════
.DEFAULT_GOAL := help
COMPOSE := docker compose
COMPOSE_FILE := docker-compose.yml

.PHONY: help dev build up down test lint migrate seed logs clean shell-be shell-db docs format typecheck

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

dev: ## Start the full stack in dev mode (hot reload)
	$(COMPOSE) -f $(COMPOSE_FILE) up --build

up: ## Start the stack detached
	$(COMPOSE) -f $(COMPOSE_FILE) up -d --build

down: ## Stop the stack
	$(COMPOSE) -f $(COMPOSE_FILE) down

build: ## Build all Docker images
	$(COMPOSE) -f $(COMPOSE_FILE) build

migrate: ## Run Alembic migrations inside the backend container
	$(COMPOSE) -f $(COMPOSE_FILE) exec backend alembic upgrade head

seed: ## Seed the demo dataset (Acme Corp + 90 days of data)
	$(COMPOSE) -f $(COMPOSE_FILE) exec backend python -m cloudpilot.utils.mock_data

test: ## Run backend + frontend tests
	$(COMPOSE) -f $(COMPOSE_FILE) exec backend pytest -q
	cd frontend && pnpm test --run

lint: ## Run ruff + mypy (backend) and eslint (frontend)
	$(COMPOSE) -f $(COMPOSE_FILE) exec backend ruff check cloudpilot
	$(COMPOSE) -f $(COMPOSE_FILE) exec backend mypy cloudpilot
	cd frontend && pnpm lint

format: ## Auto-format backend (ruff) and frontend (prettier/eslint --fix)
	$(COMPOSE) -f $(COMPOSE_FILE) exec backend ruff format cloudpilot
	cd frontend && pnpm lint --fix

typecheck: ## Type-check both stacks
	$(COMPOSE) -f $(COMPOSE_FILE) exec backend mypy cloudpilot
	cd frontend && pnpm typecheck

logs: ## Tail all service logs
	$(COMPOSE) -f $(COMPOSE_FILE) logs -f

clean: ## Remove containers + volumes (DESTROYS data)
	$(COMPOSE) -f $(COMPOSE_FILE) down -v --remove-orphans

shell-be: ## Bash into the backend container
	$(COMPOSE) -f $(COMPOSE_FILE) exec backend bash

shell-db: ## psql into Postgres
	$(COMPOSE) -f $(COMPOSE_FILE) exec postgres psql -U cp -d cloudpilot

docs: ## Serve docs locally with Python http server
	cd docs && python -m http.server 8080

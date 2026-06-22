# CloudPilot — Deployment

## Local (Docker Compose)

```bash
cp .env.example .env
make dev          # builds + starts the full stack
make seed         # seed the demo dataset (second terminal)
```

Services: postgres, redis, chromadb, ollama, backend, scheduler, frontend,
prometheus, grafana. Frontend at `:5173`, API at `:8000`, Grafana at `:3001`.

> First run pulls the Ollama model. To pre-pull: `docker compose exec ollama ollama pull qwen2.5:4b && docker compose exec ollama ollama pull nomic-embed-text`.

## Production (Docker Compose + nginx)

```bash
docker compose -f docker-compose.prod.yml up -d
```

Differences from dev: built images (no source mounts), `uvicorn --workers 4`,
nginx terminating TLS in front (`nginx.conf`), `DEBUG=false`. Provide secrets via
`.env` (`POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `JWT_SECRET`, `FERNET_MASTER_KEY`,
`GF_SECURITY_ADMIN_PASSWORD`) and TLS certs in `./certs`.

## Kubernetes

Manifests live in `infrastructure/kubernetes/`. Apply in order:

```bash
kubectl apply -f infrastructure/kubernetes/namespace.yaml
kubectl apply -f infrastructure/kubernetes/postgres-statefulset.yaml
kubectl apply -f infrastructure/kubernetes/redis-deployment.yaml
kubectl apply -f infrastructure/kubernetes/backend-deployment.yaml
kubectl apply -f infrastructure/kubernetes/frontend-deployment.yaml
kubectl apply -f infrastructure/kubernetes/network-policies.yaml
kubectl apply -f infrastructure/kubernetes/ingress.yaml
```

Notes:
- Populate `cloudpilot-secrets` via Sealed Secrets / External Secrets — do not commit real values.
- The scheduler runs as a **single replica** to avoid duplicate agent runs.
- `network-policies.yaml` enforces default-deny ingress with explicit allows; the AKS
  module enables Calico to make these effective.

## Azure (Terraform)

```bash
cd infrastructure/terraform
terraform init
terraform plan  -var "pg_admin_password=$(openssl rand -base64 24)"
terraform apply -var "pg_admin_password=$(openssl rand -base64 24)"
```

Provisions a resource group, an AKS cluster (`modules/aks`, autoscaling, Calico),
a PostgreSQL Flexible Server (v16) + `cloudpilot` database, and a Standard Redis cache.
Fetch the kubeconfig from the `aks_kube_config` output.

## CI/CD (GitHub Actions)

- `ci.yml` — backend (ruff, mypy, pytest) and frontend (eslint, tsc, build) on every push/PR.
- `docker-build.yml` — multi-arch (amd64/arm64) image build & push to GHCR on `main` and tags.

## Migrations

```bash
make migrate                                   # alembic upgrade head (in container)
docker compose exec backend alembic revision -m "add X"  # new migration
```

## Health & observability

- `GET /health` — liveness/readiness probe target.
- `GET /metrics` — Prometheus scrape (`infrastructure/prometheus/prometheus.yml`).
- Grafana dashboard: import `infrastructure/grafana/dashboards/cloudpilot.json`.

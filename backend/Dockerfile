# ═══════════════════════════════════════════════════════════════
# CloudPilot backend — multi-stage build (ARM64 compatible)
# ═══════════════════════════════════════════════════════════════
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=1.8.2 \
    POETRY_VIRTUALENVS_CREATE=false

# System deps: build tools for prophet/numpy, libpq for asyncpg, curl for healthchecks.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install "poetry==${POETRY_VERSION}"

WORKDIR /app

# Install dependencies first (layer caching).
COPY pyproject.toml ./
RUN poetry install --no-root --no-interaction --no-ansi || \
    poetry lock --no-interaction && poetry install --no-root --no-interaction --no-ansi

# Copy application source.
COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "cloudpilot.main:app", "--host", "0.0.0.0", "--port", "8000"]

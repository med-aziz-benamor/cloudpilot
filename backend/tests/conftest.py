"""Pytest fixtures and shared test configuration.

These tests exercise the security, crypto, pricing and agent-algorithm layers in
isolation — they need no database or external services, so they run anywhere
(`pytest` in the backend dir or via `make test`). Integration tests that require a
live Postgres are gated behind the ``CLOUDPILOT_TEST_DB`` env var.
"""

from __future__ import annotations

import os

import pytest

# Ensure deterministic, dependency-free settings for the test process.
os.environ.setdefault("DEMO_MODE", "true")
os.environ.setdefault("JWT_SECRET", "test-secret-key-at-least-32-chars-long!!")
os.environ.setdefault(
    "FERNET_MASTER_KEY", "dGVzdC1mZXJuZXQta2V5LTMyLWJ5dGVzLWxvbmchMTI="
)


@pytest.fixture(scope="session")
def anomaly_series() -> list[float]:
    """A daily cost series with one obvious spike on the last day."""
    base = [100.0 + i * 0.5 for i in range(30)]
    base[-1] = 600.0  # 6x spike
    return base

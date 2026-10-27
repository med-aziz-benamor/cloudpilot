"""Tests for the production secrets guard in ``Settings``.

These exercise the real ``Settings`` class. ``_env_file=None`` keeps a developer's
local ``.env`` from leaking real secrets into the assertions.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from cloudpilot.config import Settings

STRONG = "s" * 40

# conftest.py seeds JWT_SECRET / FERNET_MASTER_KEY into os.environ for the rest of the
# suite, and pydantic reads the OS environment even with _env_file=None. Clear the
# secret vars here so each case starts from the code defaults, not the test harness.
_SECRET_ENV_VARS = ("JWT_SECRET", "APP_SECRET_KEY", "FERNET_MASTER_KEY")


@pytest.fixture(autouse=True)
def _clear_secret_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _SECRET_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def _settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


def test_dev_boots_on_insecure_defaults() -> None:
    """Dev/demo must still start without any secrets configured."""
    s = _settings(APP_ENV="development")
    assert not s.is_production


def test_production_rejects_default_secrets() -> None:
    """Every insecure secret is named so the operator knows what to fix."""
    with pytest.raises(ValueError) as exc:
        _settings(APP_ENV="production")
    msg = str(exc.value)
    assert "JWT_SECRET" in msg
    assert "APP_SECRET_KEY" in msg
    assert "FERNET_MASTER_KEY" in msg


def test_production_boots_with_strong_secrets() -> None:
    key = Fernet.generate_key().decode()
    s = _settings(
        APP_ENV="production",
        JWT_SECRET=STRONG,
        APP_SECRET_KEY=STRONG,
        FERNET_MASTER_KEY=key,
    )
    assert s.is_production
    assert s.fernet_key_bytes == key.encode()


def test_production_rejects_only_missing_fernet() -> None:
    with pytest.raises(ValueError) as exc:
        _settings(APP_ENV="production", JWT_SECRET=STRONG, APP_SECRET_KEY=STRONG)
    msg = str(exc.value)
    assert "FERNET_MASTER_KEY" in msg
    assert "JWT_SECRET" not in msg


def test_malformed_fernet_key_rejected_in_any_env() -> None:
    """A set-but-invalid key is always wrong, dev included."""
    with pytest.raises(ValueError, match="not a valid Fernet key"):
        _settings(APP_ENV="development", FERNET_MASTER_KEY="not-a-valid-key")

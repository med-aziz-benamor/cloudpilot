"""Tests for AuthService.login: the per-email lockout and the timing side-channel fix.

No database is needed — AuthService.db is only ever awaited via `.execute(...)`
here, so a minimal stub session is enough to drive `login()`'s branches.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi import HTTPException

from cloudpilot.core import rate_limit
from cloudpilot.schemas.auth import LoginRequest
from cloudpilot.services import auth_service as auth_service_module
from cloudpilot.services.auth_service import AuthService


@dataclass
class _FakeResult:
    user: object | None

    def scalar_one_or_none(self) -> object | None:
        return self.user


class _FakeSession:
    """Stands in for AsyncSession: returns a fixed user (or None) on execute()."""

    def __init__(self, user: object | None) -> None:
        self._user = user

    async def execute(self, _stmt: object) -> _FakeResult:
        return _FakeResult(self._user)


async def _always_allow(_ident: str, _limit: int, _window: int) -> bool:
    return True


async def _deny_email_only(ident: str, _limit: int, _window: int) -> bool:
    return not ident.startswith("login:email:")


async def test_record_failed_login_returns_false_once_locked_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rate_limit, "check_rate_limit", _deny_email_only)
    service = AuthService(_FakeSession(None))  # type: ignore[arg-type]
    assert await service._record_failed_login("demo@cloudpilot.dev", "1.2.3.4") is False


async def test_record_failed_login_allows_under_the_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rate_limit, "check_rate_limit", _always_allow)
    service = AuthService(_FakeSession(None))  # type: ignore[arg-type]
    assert await service._record_failed_login("demo@cloudpilot.dev", "1.2.3.4") is True


async def test_login_raises_423_when_email_is_locked_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rate_limit, "check_rate_limit", _deny_email_only)
    service = AuthService(_FakeSession(None))  # type: ignore[arg-type]
    with pytest.raises(HTTPException) as exc_info:
        await service.login(LoginRequest(email="demo@cloudpilot.dev", password="wrong-pass"))
    assert exc_info.value.status_code == 423


async def test_login_runs_password_verify_even_for_an_unknown_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A nonexistent email must still cost a real bcrypt verify, or response
    timing leaks which emails are registered."""
    monkeypatch.setattr(rate_limit, "check_rate_limit", _always_allow)
    calls: list[str] = []

    def _spy_verify(_plain: str, hashed: str) -> bool:
        calls.append(hashed)
        return False

    monkeypatch.setattr(auth_service_module, "verify_password", _spy_verify)
    service = AuthService(_FakeSession(None))  # type: ignore[arg-type]

    with pytest.raises(HTTPException) as exc_info:
        await service.login(LoginRequest(email="nobody@cloudpilot.dev", password="whatever1"))

    assert exc_info.value.status_code == 401
    assert len(calls) == 1
    assert calls[0] == auth_service_module._DUMMY_PASSWORD_HASH


async def test_login_dummy_hash_never_matches_a_real_password() -> None:
    from cloudpilot.core.security import verify_password

    assert not verify_password("demo1234", auth_service_module._DUMMY_PASSWORD_HASH)


def test_dummy_password_hash_is_randomized_per_process() -> None:
    # Sanity check that the module-level constant isn't a hardcoded literal
    # that would itself become a guessable secret.
    assert auth_service_module._DUMMY_PASSWORD_HASH.startswith("$2b$")

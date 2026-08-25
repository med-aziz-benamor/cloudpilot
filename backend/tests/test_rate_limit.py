"""Tests for core.rate_limit: fail-closed JWT revocation, and atomic refresh
token consumption (GETDEL instead of GET-then-DELETE)."""

from __future__ import annotations

import asyncio

import pytest

from cloudpilot.core import rate_limit


class _RaisingRedis:
    async def exists(self, _key: str) -> int:
        raise ConnectionError("redis unreachable")


async def test_is_revoked_fails_closed_when_redis_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rate_limit, "get_redis", lambda: _RaisingRedis())
    assert await rate_limit.is_revoked("some-jti") is True


class _FakeSingleUseRedis:
    """A minimal stand-in whose getdel is a single atomic step (no internal
    await between the read and the delete), the way real Redis GETDEL is."""

    def __init__(self, store: dict[str, str]) -> None:
        self._store = store

    async def getdel(self, key: str) -> str | None:
        return self._store.pop(key, None)


async def test_consume_refresh_token_uses_a_single_atomic_getdel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = {"refresh:tok-123": "user-abc"}
    monkeypatch.setattr(rate_limit, "get_redis", lambda: _FakeSingleUseRedis(store))

    result = await rate_limit.consume_refresh_token("tok-123")

    assert result == "user-abc"
    assert "refresh:tok-123" not in store  # consumed exactly once


async def test_consume_refresh_token_is_single_use_under_concurrent_callers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = {"refresh:tok-456": "user-xyz"}
    monkeypatch.setattr(rate_limit, "get_redis", lambda: _FakeSingleUseRedis(store))

    results = await asyncio.gather(
        rate_limit.consume_refresh_token("tok-456"),
        rate_limit.consume_refresh_token("tok-456"),
    )

    # Exactly one of the two concurrent calls gets the token; the race that
    # GET-then-DELETE was vulnerable to (both reading before either deletes)
    # cannot happen through a single atomic GETDEL.
    assert sorted(results, key=lambda r: r is None) == ["user-xyz", None]


async def test_consume_refresh_token_returns_none_on_redis_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Raising:
        async def getdel(self, _key: str) -> str | None:
            raise ConnectionError("redis unreachable")

    monkeypatch.setattr(rate_limit, "get_redis", lambda: _Raising())
    assert await rate_limit.consume_refresh_token("tok-789") is None

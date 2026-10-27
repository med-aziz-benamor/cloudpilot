"""Dashboard aggregate cache: tenant scoping, fail-open, and invalidation.

``CACHE_DASHBOARD_TTL`` was defined in config and referenced nowhere — every
cost query hit Postgres on every request. These cover the three properties
that make caching these aggregates safe rather than just fast.

The tenant-scoping test is the important one: a cache sits *in front of* the
ORM tenant filter, so a key that isn't org-scoped would serve one tenant's
figures to another without the guard in ``core/tenant.py`` ever running.
"""

from __future__ import annotations

import uuid

import pytest

from cloudpilot.core import cache


class _FakeRedis:
    """Minimal in-memory stand-in supporting the calls cache.py makes."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def setex(self, key: str, _ttl: int, value: str) -> None:
        self.store[key] = value

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self.store.pop(key, None)

    async def scan_iter(self, match: str, count: int = 100):  # noqa: ARG002
        prefix = match.rstrip("*")
        for key in list(self.store):
            if key.startswith(prefix):
                yield key


class _DeadRedis:
    """Every call raises, like Redis being unreachable."""

    async def get(self, key: str) -> str | None:
        raise ConnectionError("redis unreachable")

    async def setex(self, key: str, ttl: int, value: str) -> None:
        raise ConnectionError("redis unreachable")

    def scan_iter(self, match: str, count: int = 100):  # noqa: ARG002
        raise ConnectionError("redis unreachable")


# ─── Tenant scoping ───
def test_keys_are_namespaced_per_organization() -> None:
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    assert cache.org_key(org_a, "summary") != cache.org_key(org_b, "summary")
    assert str(org_a) in cache.org_key(org_a, "summary")


def test_key_parts_separate_different_questions() -> None:
    """7/30/90-day timeseries are different answers and must not collide."""
    org = uuid.uuid4()
    assert cache.org_key(org, "timeseries", 7) != cache.org_key(org, "timeseries", 90)


async def test_one_orgs_cached_value_is_never_served_to_another(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr(cache, "get_redis", lambda: fake)
    org_a, org_b = uuid.uuid4(), uuid.uuid4()

    await cache.set_json(cache.org_key(org_a, "summary"), {"mtd_usd": 999.0}, 300)

    assert await cache.get_json(cache.org_key(org_a, "summary")) == {"mtd_usd": 999.0}
    assert await cache.get_json(cache.org_key(org_b, "summary")) is None


# ─── Round-trip and fail-open ───
async def test_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr(cache, "get_redis", lambda: fake)
    key = cache.org_key(uuid.uuid4(), "breakdown")
    await cache.set_json(key, {"by_provider": [{"provider": "azure"}]}, 300)
    assert await cache.get_json(key) == {"by_provider": [{"provider": "azure"}]}


async def test_miss_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr(cache, "get_redis", lambda: fake)
    assert await cache.get_json(cache.org_key(uuid.uuid4(), "summary")) is None


async def test_reads_fail_open_when_redis_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unlike the auth surface, a cache must degrade to a slower correct
    answer, never an error."""
    monkeypatch.setattr(cache, "get_redis", lambda: _DeadRedis())
    assert await cache.get_json(cache.org_key(uuid.uuid4(), "summary")) is None


async def test_writes_fail_open_when_redis_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cache, "get_redis", lambda: _DeadRedis())
    await cache.set_json(cache.org_key(uuid.uuid4(), "summary"), {"x": 1}, 300)  # must not raise


async def test_invalidation_failure_does_not_break_the_triggering_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cache, "get_redis", lambda: _DeadRedis())
    await cache.invalidate_org(uuid.uuid4())  # must not raise


async def test_corrupt_entry_is_treated_as_a_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr(cache, "get_redis", lambda: fake)
    key = cache.org_key(uuid.uuid4(), "summary")
    fake.store[key] = "{not valid json"
    assert await cache.get_json(key) is None


# ─── Invalidation ───
async def test_invalidate_org_drops_only_that_orgs_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeRedis()
    monkeypatch.setattr(cache, "get_redis", lambda: fake)
    org_a, org_b = uuid.uuid4(), uuid.uuid4()

    await cache.set_json(cache.org_key(org_a, "summary"), {"a": 1}, 300)
    await cache.set_json(cache.org_key(org_a, "timeseries", 30), {"a": 2}, 300)
    await cache.set_json(cache.org_key(org_b, "summary"), {"b": 1}, 300)

    await cache.invalidate_org(org_a)

    assert await cache.get_json(cache.org_key(org_a, "summary")) is None
    assert await cache.get_json(cache.org_key(org_a, "timeseries", 30)) is None
    assert await cache.get_json(cache.org_key(org_b, "summary")) == {"b": 1}


async def test_invalidate_org_leaves_unrelated_namespaces_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rate-limit and revocation keys share the Redis instance."""
    fake = _FakeRedis()
    monkeypatch.setattr(cache, "get_redis", lambda: fake)
    org = uuid.uuid4()
    fake.store["rl:login:ip:1.2.3.4"] = "3"
    fake.store["revoked:some-jti"] = "1"
    await cache.set_json(cache.org_key(org, "summary"), {"a": 1}, 300)

    await cache.invalidate_org(org)

    assert "rl:login:ip:1.2.3.4" in fake.store
    assert "revoked:some-jti" in fake.store


async def test_pydantic_models_survive_a_round_trip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cached model must come back as data, not as its repr.

    ``json.dumps(default=str)`` stringifies anything it cannot encode, so a
    Pydantic model was stored as ``"provider=<CloudProvider.AZURE: 'azure'>
    cost_usd=3953.16 pct_of_total=59.0"``. Nothing failed on the write. The next
    request hit the cache, tried to validate a list of strings against the
    response model, and returned 500 — so /costs/breakdown worked on first load
    and broke on every reload for the length of the TTL.
    """
    from cloudpilot.models.cloud_account import CloudProvider
    from cloudpilot.schemas.cost import ProviderCost

    fake = _FakeRedis()
    monkeypatch.setattr(cache, "get_redis", lambda: fake)
    key = cache.org_key(uuid.uuid4(), "breakdown")

    model = ProviderCost(provider=CloudProvider.AZURE, cost_usd=3953.16, pct_of_total=59.0)
    await cache.set_json(key, {"by_provider": [model]}, 300)

    hit = await cache.get_json(key)
    assert hit == {
        "by_provider": [{"provider": "azure", "cost_usd": 3953.16, "pct_of_total": 59.0}]
    }
    # And the round-tripped form must reconstruct the model it came from.
    assert ProviderCost.model_validate(hit["by_provider"][0]) == model


async def test_scalars_json_cannot_encode_still_stringify(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """UUIDs, dates and Decimals stringify correctly and keep that path."""
    import datetime
    import decimal

    fake = _FakeRedis()
    monkeypatch.setattr(cache, "get_redis", lambda: fake)
    key = cache.org_key(uuid.uuid4(), "misc")
    uid = uuid.uuid4()

    await cache.set_json(
        key,
        {"id": uid, "day": datetime.date(2026, 8, 31), "amount": decimal.Decimal("12.34")},
        300,
    )
    assert await cache.get_json(key) == {
        "id": str(uid),
        "day": "2026-08-31",
        "amount": "12.34",
    }


async def test_an_entry_whose_shape_changed_is_treated_as_a_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same rule as a corrupt entry, one step later.

    A cached payload that parses but no longer validates used to propagate as a
    500. That makes any schema change to a cached response break every user
    holding a pre-deploy entry until its TTL runs out.
    """
    from cloudpilot.schemas.cost import CostSummary

    fake = _FakeRedis()
    monkeypatch.setattr(cache, "get_redis", lambda: fake)
    key = cache.org_key(uuid.uuid4(), "summary")

    await cache.set_json(key, {"fields": "from an older release"}, 300)
    assert await cache.get_model(key, CostSummary) is None


async def test_get_model_returns_the_model_on_a_valid_hit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cloudpilot.models.cloud_account import CloudProvider
    from cloudpilot.schemas.cost import ProviderCost

    fake = _FakeRedis()
    monkeypatch.setattr(cache, "get_redis", lambda: fake)
    key = cache.org_key(uuid.uuid4(), "provider")

    model = ProviderCost(provider=CloudProvider.AWS, cost_usd=1618.65, pct_of_total=24.2)
    await cache.set_json(key, model, 300)
    assert await cache.get_model(key, ProviderCost) == model

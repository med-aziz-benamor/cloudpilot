"""Redis-backed cache for dashboard aggregates.

The cost aggregates behind the Overview and Costs pages are the platform's
most expensive reads — ``get_summary`` alone issues five queries, and every
page load re-runs them against the full billing history. They are also the
most repetitive: the numbers only move when a sync lands or a recommendation
is actioned.

Three rules this module exists to enforce:

* **Every key is tenant-scoped.** A cache is a classic cross-tenant leak
  vector — serve org A's cached summary to org B once and the ORM tenant
  filter that guards the underlying query never even runs. ``org_key`` is the
  only way to build a key here, and it always takes an organization id.
* **It fails open.** Unlike the auth surface (see ``core/rate_limit.is_revoked``,
  which fails *closed* deliberately), a cache miss caused by Redis being down
  should degrade to a slower correct answer, never an error.
* **It is invalidated on write, not just on TTL.** Accepting a recommendation
  changes ``potential_savings_usd`` and ``pending_recommendations`` in the
  summary; waiting out a 5-minute TTL would leave the dashboard visibly
  disagreeing with the action the user just took.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, TypeVar

from loguru import logger
from pydantic import BaseModel, ValidationError

from cloudpilot.core.rate_limit import get_redis

#: Namespace for every dashboard aggregate key, so one org's cache can be
#: dropped with a single scan without touching rate-limit or revocation keys.
_PREFIX = "dashboard"

M = TypeVar("M", bound=BaseModel)


def org_key(organization_id: uuid.UUID, name: str, *parts: object) -> str:
    """Build a tenant-scoped cache key: ``dashboard:{org}:{name}[:part...]``."""
    suffix = ":".join(str(p) for p in parts)
    return f"{_PREFIX}:{organization_id}:{name}" + (f":{suffix}" if suffix else "")


async def get_json(key: str) -> Any | None:
    """Return the decoded cached value, or None on miss/unavailable/corrupt."""
    try:
        raw = await get_redis().get(key)
    except Exception as exc:  # pragma: no cover - resilience
        logger.debug("Cache unavailable on read, computing fresh: {}", exc)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        # A corrupt entry must not be more disruptive than a miss.
        logger.warning("Discarding corrupt cache entry at {}", key)
        return None


def _encode(value: Any) -> Any:
    """Fallback encoder for values ``json`` cannot serialize on its own.

    Pydantic models are handled explicitly rather than left to ``str``. Falling
    back to ``str`` for a model stores its *repr* — ``"provider=<CloudProvider.
    AZURE: 'azure'> cost_usd=3953.16"`` — which round-trips as a string and then
    fails validation on the next cache hit, turning a caching layer into a 500 on
    every request after the first. UUIDs, dates and Decimals do stringify
    correctly, so they keep the plain ``str`` path.
    """
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return str(value)


async def get_model(key: str, model: type[M]) -> M | None:
    """Return a cached value validated into ``model``, or None on miss or mismatch.

    An entry whose *shape* no longer matches is discarded exactly like an entry
    that will not parse: same rule, one step later. Without this, any schema
    change to a cached response 500s every user still holding a pre-deploy entry
    until its TTL runs out — a cache is meant to cost latency when it is wrong,
    never correctness.
    """
    raw = await get_json(key)
    if raw is None:
        return None
    try:
        return model.model_validate(raw)
    except ValidationError:
        logger.warning(
            "Discarding cache entry at {} that no longer matches {}", key, model.__name__
        )
        return None


async def set_json(key: str, value: Any, ttl_seconds: int) -> None:
    """Store a JSON-serializable value under ``key`` with a TTL."""
    try:
        await get_redis().setex(key, ttl_seconds, json.dumps(value, default=_encode))
    except Exception as exc:  # pragma: no cover - resilience
        logger.debug("Cache unavailable on write, skipping: {}", exc)


async def invalidate_org(organization_id: uuid.UUID) -> None:
    """Drop every dashboard aggregate cached for one organization.

    Uses SCAN rather than KEYS so a large keyspace does not block Redis.
    """
    pattern = f"{_PREFIX}:{organization_id}:*"
    try:
        client = get_redis()
        keys = [key async for key in client.scan_iter(match=pattern, count=100)]
        if keys:
            await client.delete(*keys)
            logger.debug("Invalidated {} cached aggregates for org {}", len(keys), organization_id)
    except Exception as exc:  # pragma: no cover - resilience
        # Failing to invalidate is worse than failing to cache — it serves
        # stale numbers — but it still must not break the write that
        # triggered it. The TTL remains the backstop.
        logger.warning("Could not invalidate dashboard cache for {}: {}", organization_id, exc)

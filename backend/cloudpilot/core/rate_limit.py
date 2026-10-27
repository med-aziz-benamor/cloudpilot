"""Redis-backed rate limiting and JWT revocation list.

Uses a fixed-window counter keyed by identifier (IP, email, or JWT subject).
Also exposes helpers for the JWT revocation set used on logout / refresh rotation.

Redis is optional in local/test runs: if it is unreachable the limiter fails
*open* for non-auth surfaces (so the demo never breaks) but the auth surface still
benefits from nginx-level limiting in production.
"""

from __future__ import annotations

import redis.asyncio as redis
from loguru import logger

from cloudpilot.config import settings

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    """Return a lazily-initialized async Redis client."""
    global _client
    if _client is None:
        # redis-py ships no annotation for from_url.
        _client = redis.from_url(  # type: ignore[no-untyped-call]
            settings.REDIS_URL, decode_responses=True
        )
    return _client


async def check_rate_limit(identifier: str, limit: int, window_seconds: int) -> bool:
    """Fixed-window rate limit. Returns True if the call is allowed.

    Args:
        identifier: unique key, e.g. ``"login:ip:1.2.3.4"``.
        limit: max number of calls allowed in the window.
        window_seconds: window size.
    """
    key = f"rl:{identifier}"
    try:
        client = get_redis()
        current = await client.incr(key)
        if current == 1:
            await client.expire(key, window_seconds)
        return bool(current <= limit)
    except Exception as exc:  # pragma: no cover - resilience
        logger.warning("Rate limiter unavailable, failing open: {}", exc)
        return True


async def reset_rate_limit(identifier: str) -> None:
    """Clear the counter for an identifier (e.g. after a successful login)."""
    try:
        await get_redis().delete(f"rl:{identifier}")
    except Exception as exc:  # pragma: no cover
        logger.warning("Could not reset rate limit: {}", exc)


# ─── JWT revocation list ───
async def revoke_jti(jti: str, ttl_seconds: int) -> None:
    """Add a token id to the revocation set with a TTL matching its remaining life."""
    try:
        await get_redis().setex(f"revoked:{jti}", ttl_seconds, "1")
    except Exception as exc:  # pragma: no cover
        logger.warning("Could not revoke jti {}: {}", jti, exc)


async def is_revoked(jti: str) -> bool:
    """Return True if a token id has been revoked.

    Unlike the rest of this module, this check fails *closed*: if Redis is
    unreachable we cannot prove a token hasn't been revoked, so we treat it as
    revoked rather than silently accepting a possibly-logged-out token for the
    rest of its access-token TTL. Both compose files already gate the backend's
    own startup on Redis health, so this mainly bites during a live Redis
    outage — an availability cost accepted in exchange for not silently
    honouring revoked credentials.
    """
    try:
        return bool(await get_redis().exists(f"revoked:{jti}") == 1)
    except Exception as exc:  # pragma: no cover - resilience
        logger.warning("Revocation check unavailable, failing closed: {}", exc)
        return True


async def store_refresh_token(token: str, user_id: str, ttl_seconds: int) -> None:
    """Persist a valid refresh token → user binding."""
    try:
        await get_redis().setex(f"refresh:{token}", ttl_seconds, user_id)
    except Exception as exc:  # pragma: no cover
        logger.warning("Could not store refresh token: {}", exc)


async def consume_refresh_token(token: str) -> str | None:
    """Return the bound user id and atomically delete the token (rotation).

    Uses GETDEL rather than GET-then-DELETE: the latter is a TOCTOU race where
    two concurrent refresh calls for the same token can both read the value
    before either deletes it, letting the token be used twice — defeating the
    single-use rotation this function exists to enforce.
    """
    try:
        client = get_redis()
        user_id: str | None = await client.getdel(f"refresh:{token}")
        return user_id
    except Exception:  # pragma: no cover
        return None

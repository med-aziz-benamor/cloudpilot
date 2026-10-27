"""Shared API dependencies: DB session, current user, RBAC guards, tenant binding."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable, Coroutine
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from cloudpilot.core import rate_limit
from cloudpilot.core.rbac import role_has_permission
from cloudpilot.core.security import TokenPayload, verify_token
from cloudpilot.core.tenant import set_current_org
from cloudpilot.database import AsyncSessionLocal
from cloudpilot.models.user import User, UserRole

_bearer = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a request-scoped async session, committing on success."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_token_payload(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> TokenPayload:
    """Validate the bearer token and return its decoded payload."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = verify_token(credentials.credentials)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid token.") from exc

    if await rate_limit.is_revoked(payload.jti):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token revoked.")
    return payload


async def get_current_user(
    payload: TokenPayload = Depends(get_token_payload),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the authenticated user and bind the tenant context for this request."""
    # Bind tenant BEFORE any query so the tenant filter applies even here.
    set_current_org(payload.org_id)
    user = await db.get(User, payload.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    if user.organization_id != payload.org_id:
        # Token org and stored org disagree — refuse.
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Organization mismatch.")
    return user


def require_permission(
    permission: str,
) -> Callable[[User], Coroutine[Any, Any, User]]:
    """Build a dependency enforcing a logical permission from the RBAC matrix."""

    async def _guard(user: User = Depends(get_current_user)) -> User:
        if not role_has_permission(user.role, permission):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role.value}' lacks permission '{permission}'.",
            )
        return user

    return _guard


def require_roles(
    *roles: UserRole,
) -> Callable[[User], Coroutine[Any, Any, User]]:
    """Build a dependency enforcing membership in an explicit role set."""

    async def _guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, detail="Insufficient role."
            )
        return user

    return _guard


def client_ip(request: Request) -> str:
    """Best-effort client IP, trusting only the reverse proxy's own hop.

    nginx sets `X-Real-IP` to `$remote_addr` on every proxied request (see
    nginx.conf) — a client cannot spoof it, since nginx overwrites rather than
    appends. `X-Forwarded-For` is attacker-suppliable at its *first* value (a
    client can send its own), so if `X-Real-IP` is absent we fall back to the
    *last* segment of `X-Forwarded-For` — the one nginx itself appended via
    `$proxy_add_x_forwarded_for` — never the first.
    """
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"

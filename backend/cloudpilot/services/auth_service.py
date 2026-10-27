"""Authentication service — registration, login, refresh rotation, logout."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cloudpilot.config import settings
from cloudpilot.core import rate_limit
from cloudpilot.core.audit import write_audit
from cloudpilot.core.security import (
    check_password_strength,
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from cloudpilot.models.organization import Organization, OrgPlan
from cloudpilot.models.user import User, UserRole
from cloudpilot.schemas.auth import LoginRequest, RegisterRequest

# Precomputed at import time so a login against a nonexistent email still pays
# for one real bcrypt verify — otherwise response timing reveals which emails
# are registered (verify_password is only reached when `user` is truthy).
_DUMMY_PASSWORD_HASH = hash_password(uuid4().hex)


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def register(self, payload: RegisterRequest, ip: str | None = None) -> User:
        ok, msg = check_password_strength(payload.password)
        if not ok:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg)

        existing = (
            await self.db.execute(select(User).where(User.email == payload.email))
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status.HTTP_409_CONFLICT, detail="Email already registered."
            )

        org = Organization(name=payload.organization_name, plan=OrgPlan.FREE)
        self.db.add(org)
        await self.db.flush()

        user = User(
            organization_id=org.id,
            email=payload.email,
            password_hash=hash_password(payload.password),
            full_name=payload.full_name,
            role=UserRole.ADMIN,  # first user of an org is its admin
        )
        self.db.add(user)
        await self.db.flush()

        await write_audit(
            self.db,
            organization_id=org.id,
            actor_user_id=user.id,
            event_type="auth.register",
            resource_type="user",
            resource_id=str(user.id),
            ip_address=ip,
        )
        logger.info("auth.register email={} org={}", user.email, org.id)
        return user

    async def login(
        self, payload: LoginRequest, ip: str | None = None
    ) -> tuple[User, str, str]:
        # Brute-force protection per IP.
        ident = f"login:ip:{ip or 'unknown'}"
        allowed = await rate_limit.check_rate_limit(
            ident, settings.LOGIN_MAX_ATTEMPTS_PER_IP, settings.LOGIN_WINDOW_SECONDS
        )
        if not allowed:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts. Try again later.",
            )

        user = (
            await self.db.execute(select(User).where(User.email == payload.email))
        ).scalar_one_or_none()

        # Always run the bcrypt check, even for a nonexistent user, against a
        # fixed dummy hash — otherwise the missing verify_password call makes
        # "no such account" measurably faster than "wrong password".
        password_hash = user.password_hash if user else _DUMMY_PASSWORD_HASH
        password_ok = verify_password(payload.password, password_hash)

        if not user or not password_ok:
            still_allowed = await self._record_failed_login(payload.email, ip)
            if not still_allowed:
                raise HTTPException(
                    status.HTTP_423_LOCKED,
                    detail="Too many failed attempts for this account. Try again later.",
                )
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password."
            )
        if not user.is_active:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Account is disabled.")

        await rate_limit.reset_rate_limit(ident)
        await rate_limit.reset_rate_limit(f"login:email:{payload.email}")
        user.last_login_at = datetime.now(UTC)

        access = create_access_token(user.id, user.organization_id, user.role.value)
        refresh = create_refresh_token(user.id)
        await rate_limit.store_refresh_token(
            refresh, str(user.id), settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400
        )

        await write_audit(
            self.db,
            organization_id=user.organization_id,
            actor_user_id=user.id,
            event_type="auth.login.success",
            ip_address=ip,
        )
        logger.info("auth.login.success email={}", user.email)
        return user, access, refresh

    async def refresh(self, refresh_token: str) -> tuple[User, str, str]:
        user_id = await rate_limit.consume_refresh_token(refresh_token)
        if not user_id:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token."
            )
        user = await self.db.get(User, user_id)
        if not user or not user.is_active:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="User not found.")

        access = create_access_token(user.id, user.organization_id, user.role.value)
        new_refresh = create_refresh_token(user.id)
        await rate_limit.store_refresh_token(
            new_refresh, str(user.id), settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400
        )
        return user, access, new_refresh

    async def logout(self, refresh_token: str | None, jti: str, exp: int) -> None:
        if refresh_token:
            await rate_limit.consume_refresh_token(refresh_token)
        ttl = max(1, exp - int(datetime.now(UTC).timestamp()))
        await rate_limit.revoke_jti(jti, ttl)

    async def _record_failed_login(self, email: str, ip: str | None) -> bool:
        """Record a failed attempt and return False once the email is locked out."""
        email_ident = f"login:email:{email}"
        allowed = await rate_limit.check_rate_limit(
            email_ident, settings.LOGIN_MAX_ATTEMPTS_PER_EMAIL, settings.LOGIN_LOCKOUT_SECONDS
        )
        logger.warning("auth.login.failed email={} ip={}", email, ip)
        return allowed

"""Authentication endpoints: register, login, refresh, logout, me."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from cloudpilot.api.deps import client_ip, get_current_user, get_db, get_token_payload
from cloudpilot.config import settings
from cloudpilot.core.security import TokenPayload
from cloudpilot.models.user import User
from cloudpilot.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from cloudpilot.schemas.common import MessageResponse
from cloudpilot.services.auth_service import AuthService

router = APIRouter()

_REFRESH_COOKIE = "cp_refresh"


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=settings.is_production,
        samesite="strict",
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/v1/auth",
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Create a new organization and its first (admin) user."""
    service = AuthService(db)
    return await service.register(payload, ip=client_ip(request))


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate and issue an access token + rotating refresh token cookie."""
    service = AuthService(db)
    _, access, refresh = await service.login(payload, ip=client_ip(request))
    _set_refresh_cookie(response, refresh)
    return TokenResponse(
        access_token=access,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        refresh_token=refresh,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Rotate the refresh token and mint a fresh access token."""
    token = payload.refresh_token or request.cookies.get(_REFRESH_COOKIE)
    if not token:
        from fastapi import HTTPException

        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token.")
    service = AuthService(db)
    _, access, new_refresh = await service.refresh(token)
    _set_refresh_cookie(response, new_refresh)
    return TokenResponse(
        access_token=access,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        refresh_token=new_refresh,
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    payload: TokenPayload = Depends(get_token_payload),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Revoke the current access token (jti) and invalidate the refresh token."""
    service = AuthService(db)
    await service.logout(request.cookies.get(_REFRESH_COOKIE), payload.jti, payload.exp)
    response.delete_cookie(_REFRESH_COOKIE, path="/api/v1/auth")
    return MessageResponse(message="Logged out.")


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)) -> User:
    """Return the currently authenticated user."""
    return user

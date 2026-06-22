"""Authentication schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import EmailStr, Field

from cloudpilot.models.user import UserRole
from cloudpilot.schemas.common import APISchema, ResponseSchema


class RegisterRequest(APISchema):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)
    organization_name: str = Field(min_length=1, max_length=120)


class LoginRequest(APISchema):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(ResponseSchema):
    """Issued on login/refresh. The refresh token is also set as an HttpOnly cookie."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    refresh_token: str | None = None


class UserResponse(ResponseSchema):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    organization_id: uuid.UUID
    mfa_enabled: bool
    is_active: bool
    last_login_at: datetime | None = None
    created_at: datetime


class RefreshRequest(APISchema):
    refresh_token: str | None = None  # falls back to the cookie if omitted

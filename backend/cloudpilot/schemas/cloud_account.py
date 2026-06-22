"""Cloud account schemas. Credentials are write-only — never serialized back out."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from cloudpilot.models.cloud_account import CloudAccountStatus, CloudProvider
from cloudpilot.schemas.common import APISchema, ResponseSchema


class CloudAccountCreate(APISchema):
    provider: CloudProvider
    display_name: str = Field(min_length=1, max_length=120)
    account_identifier: str = Field(min_length=1, max_length=255)
    # Provider-specific credential payload (encrypted server-side, never stored raw).
    credentials: dict[str, Any]


class CloudAccountUpdate(APISchema):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    status: CloudAccountStatus | None = None


class CloudAccountResponse(ResponseSchema):
    id: uuid.UUID
    provider: CloudProvider
    display_name: str
    account_identifier: str
    status: CloudAccountStatus
    last_synced_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime
    resource_count: int = 0
    monthly_cost_usd: float = 0.0


class CredentialTestResponse(ResponseSchema):
    valid: bool
    message: str
    resource_count: int | None = None

"""Cloud account endpoints — CRUD, credential testing, manual sync."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from cloudpilot.api.deps import get_current_user, get_db, require_permission
from cloudpilot.cloud.sync_scheduler import sync_account_by_id
from cloudpilot.models.cloud_account import CloudAccount
from cloudpilot.models.user import User
from cloudpilot.schemas.cloud_account import (
    CloudAccountCreate,
    CloudAccountResponse,
    CloudAccountUpdate,
    CredentialTestResponse,
)
from cloudpilot.schemas.common import MessageResponse
from cloudpilot.services.cloud_account_service import CloudAccountService

router = APIRouter()


async def _to_response(
    service: CloudAccountService, account: CloudAccount
) -> CloudAccountResponse:
    extra = await service.enrich(account)
    return CloudAccountResponse(
        id=account.id,
        provider=account.provider,
        display_name=account.display_name,
        account_identifier=account.account_identifier,
        status=account.status,
        last_synced_at=account.last_synced_at,
        error_message=account.error_message,
        created_at=account.created_at,
        **extra,
    )


@router.get("", response_model=list[CloudAccountResponse])
async def list_cloud_accounts(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CloudAccountResponse]:
    service = CloudAccountService(db, user.organization_id)
    return [await _to_response(service, a) for a in await service.list_accounts()]


@router.post(
    "", response_model=CloudAccountResponse, status_code=status.HTTP_201_CREATED
)
async def create_cloud_account(
    payload: CloudAccountCreate,
    user: User = Depends(require_permission("cloud_accounts.manage")),
    db: AsyncSession = Depends(get_db),
) -> CloudAccountResponse:
    service = CloudAccountService(db, user.organization_id)
    account = await service.create_account(payload, user.id)
    return await _to_response(service, account)


@router.post("/test", response_model=CredentialTestResponse)
async def test_credentials(
    payload: CloudAccountCreate,
    user: User = Depends(require_permission("cloud_accounts.manage")),
    db: AsyncSession = Depends(get_db),
) -> CredentialTestResponse:
    service = CloudAccountService(db, user.organization_id)
    valid, message, count = await service.test_credentials(payload)
    return CredentialTestResponse(valid=valid, message=message, resource_count=count)


@router.patch("/{account_id}", response_model=CloudAccountResponse)
async def update_cloud_account(
    account_id: uuid.UUID,
    payload: CloudAccountUpdate,
    user: User = Depends(require_permission("cloud_accounts.manage")),
    db: AsyncSession = Depends(get_db),
) -> CloudAccountResponse:
    service = CloudAccountService(db, user.organization_id)
    account = await service.update_account(account_id, payload)
    return await _to_response(service, account)


@router.delete("/{account_id}", response_model=MessageResponse)
async def delete_cloud_account(
    account_id: uuid.UUID,
    user: User = Depends(require_permission("cloud_accounts.manage")),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    service = CloudAccountService(db, user.organization_id)
    await service.delete_account(account_id, user.id)
    return MessageResponse(message="Cloud account deleted.")


@router.post("/{account_id}/sync", response_model=MessageResponse)
async def sync_cloud_account(
    account_id: uuid.UUID,
    user: User = Depends(require_permission("cloud_accounts.manage")),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    # Ensure ownership before kicking off the sync (own session inside).
    service = CloudAccountService(db, user.organization_id)
    await service.get_account(account_id)
    result = await sync_account_by_id(account_id)
    return MessageResponse(message=f"Synced: {result}")

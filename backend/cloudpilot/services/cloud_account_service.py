"""Cloud account service — CRUD with credential encryption and connection testing."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cloudpilot.cloud.base import get_adapter
from cloudpilot.core.audit import write_audit
from cloudpilot.core.security import encrypt_credential
from cloudpilot.models.billing_entry import BillingEntry
from cloudpilot.models.cloud_account import CloudAccount, CloudAccountStatus
from cloudpilot.models.resource import Resource
from cloudpilot.schemas.cloud_account import CloudAccountCreate, CloudAccountUpdate


class CloudAccountService:
    def __init__(self, db: AsyncSession, organization_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = organization_id

    async def list_accounts(self) -> list[CloudAccount]:
        rows = (
            await self.db.execute(
                select(CloudAccount)
                .where(CloudAccount.organization_id == self.org_id)
                .order_by(CloudAccount.created_at)
            )
        ).scalars().all()
        return list(rows)

    async def get_account(self, account_id: uuid.UUID) -> CloudAccount:
        account = await self.db.get(CloudAccount, account_id)
        if account is None or account.organization_id != self.org_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cloud account not found.")
        return account

    async def create_account(
        self, payload: CloudAccountCreate, actor_user_id: uuid.UUID
    ) -> CloudAccount:
        account = CloudAccount(
            organization_id=self.org_id,
            provider=payload.provider,
            account_identifier=payload.account_identifier,
            display_name=payload.display_name,
            credentials_enc=encrypt_credential(payload.credentials),
            status=CloudAccountStatus.ACTIVE,
        )
        self.db.add(account)
        await self.db.flush()
        await write_audit(
            self.db,
            organization_id=self.org_id,
            actor_user_id=actor_user_id,
            event_type="cloud_account.created",
            resource_type="cloud_account",
            resource_id=str(account.id),
            payload={"provider": payload.provider.value},
        )
        logger.info("cloud_account.created provider={} org={}", payload.provider.value, self.org_id)
        return account

    async def update_account(
        self, account_id: uuid.UUID, payload: CloudAccountUpdate
    ) -> CloudAccount:
        account = await self.get_account(account_id)
        if payload.display_name is not None:
            account.display_name = payload.display_name
        if payload.status is not None:
            account.status = payload.status
        await self.db.flush()
        return account

    async def delete_account(
        self, account_id: uuid.UUID, actor_user_id: uuid.UUID
    ) -> None:
        account = await self.get_account(account_id)
        await write_audit(
            self.db,
            organization_id=self.org_id,
            actor_user_id=actor_user_id,
            event_type="cloud_account.deleted",
            resource_type="cloud_account",
            resource_id=str(account.id),
        )
        await self.db.delete(account)
        await self.db.flush()

    async def test_credentials(self, payload: CloudAccountCreate) -> tuple[bool, str, int | None]:
        adapter = get_adapter(payload.provider, payload.credentials)
        valid = await adapter.validate_credentials()
        if not valid:
            return False, "Credentials could not be validated.", None
        resources = await adapter.get_resources()
        return True, "Connection successful.", len(resources)

    async def enrich(self, account: CloudAccount) -> dict:
        """Compute resource count + monthly cost for an account response."""
        resource_count = (
            await self.db.execute(
                select(func.count(Resource.id)).where(
                    Resource.cloud_account_id == account.id
                )
            )
        ).scalar_one()
        monthly = (
            await self.db.execute(
                select(func.coalesce(func.sum(BillingEntry.cost_usd), 0)).where(
                    BillingEntry.cloud_account_id == account.id
                )
            )
        ).scalar_one()
        return {
            "resource_count": int(resource_count),
            "monthly_cost_usd": round(float(monthly), 2),
        }

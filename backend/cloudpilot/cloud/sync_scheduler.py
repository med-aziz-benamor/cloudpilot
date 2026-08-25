"""Cloud sync — pulls resources, billing and metrics from adapters into the DB.

Invoked by the orchestrator on an hourly cadence and on-demand after a cloud account
is connected. All writes are idempotent (upsert-by-natural-key) so repeated syncs do
not create duplicates.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from loguru import logger
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from cloudpilot.cloud.base import get_adapter
from cloudpilot.core import cache
from cloudpilot.core.security import decrypt_credential
from cloudpilot.database import AsyncSessionLocal
from cloudpilot.models.billing_entry import BillingEntry
from cloudpilot.models.cloud_account import CloudAccount, CloudAccountStatus
from cloudpilot.models.metric_sample import MetricSample
from cloudpilot.models.resource import Resource

_BILLING_DAYS = 90
_METRIC_DAYS = 14


async def sync_account(db: AsyncSession, account: CloudAccount) -> dict[str, int]:
    """Sync one cloud account. Returns counts of synced entities."""
    try:
        creds = decrypt_credential(account.credentials_enc) if account.credentials_enc else {}
    except Exception:  # pragma: no cover - corrupted/blank in demo
        creds = {}
    adapter = get_adapter(account.provider, creds)

    resources = await _sync_resources(db, account, adapter)
    billing = await _sync_billing(db, account, adapter, resources)
    metrics = await _sync_metrics(db, adapter, resources)

    account.last_synced_at = datetime.now(UTC)
    account.status = CloudAccountStatus.ACTIVE
    account.error_message = None
    await db.flush()
    # Resources, billing and metrics all just changed underneath the cached
    # dashboard aggregates for this tenant.
    await cache.invalidate_org(account.organization_id)
    logger.info(
        "Synced account {} ({}): {} resources, {} billing, {} metrics",
        account.display_name,
        account.provider.value,
        len(resources),
        billing,
        metrics,
    )
    return {"resources": len(resources), "billing": billing, "metrics": metrics}


async def _sync_resources(
    db: AsyncSession, account: CloudAccount, adapter: Any
) -> dict[str, Resource]:
    dtos = await adapter.get_resources()
    existing = (
        (await db.execute(
            select(Resource).where(Resource.cloud_account_id == account.id)
        )).scalars().all()
    )
    by_pid = {r.provider_resource_id: r for r in existing}
    out: dict[str, Resource] = {}
    now = datetime.now(UTC)
    for dto in dtos:
        res = by_pid.get(dto.provider_resource_id)
        if res is None:
            res = Resource(
                organization_id=account.organization_id,
                cloud_account_id=account.id,
                provider_resource_id=dto.provider_resource_id,
            )
            db.add(res)
        res.name = dto.name
        res.service = dto.service
        res.region = dto.region
        res.sku = dto.sku
        res.node_count = dto.node_count
        res.tags_json = dto.tags
        res.is_active = True
        res.last_seen_at = now
        out[dto.provider_resource_id] = res
    await db.flush()
    return out


async def _sync_billing(
    db: AsyncSession, account: CloudAccount, adapter: Any, resources: dict[str, Resource]
) -> int:
    end = date.today()
    start = end - timedelta(days=_BILLING_DAYS)
    # Replace the window to keep idempotency simple and correct.
    await db.execute(
        delete(BillingEntry).where(
            BillingEntry.cloud_account_id == account.id,
            BillingEntry.usage_date >= start,
        )
    )
    dtos = await adapter.get_billing(start, end)
    for dto in dtos:
        resource_id = None
        if dto.provider_resource_id and dto.provider_resource_id in resources:
            resource_id = resources[dto.provider_resource_id].id
        db.add(
            BillingEntry(
                organization_id=account.organization_id,
                cloud_account_id=account.id,
                resource_id=resource_id,
                usage_date=dto.usage_date,
                service=dto.service,
                cost_usd=Decimal(str(round(dto.cost_usd, 4))),
                raw_currency=dto.raw_currency,
                raw_amount=Decimal(str(round(dto.raw_amount, 4))),
            )
        )
    await db.flush()
    return len(dtos)


async def _sync_metrics(
    db: AsyncSession, adapter: Any, resources: dict[str, Resource]
) -> int:
    count = 0
    cutoff = datetime.now(UTC) - timedelta(days=_METRIC_DAYS)
    for pid, res in resources.items():
        if not res.sku:  # only collect metrics for sized resources
            continue
        await db.execute(
            delete(MetricSample).where(
                MetricSample.resource_id == res.id,
                MetricSample.timestamp >= cutoff,
            )
        )
        for metric in ("cpu_percent", "memory_percent"):
            samples = await adapter.get_metrics(pid, metric, _METRIC_DAYS)
            for s in samples:
                db.add(
                    MetricSample(
                        organization_id=res.organization_id,
                        resource_id=res.id,
                        metric_name=s.metric_name,
                        timestamp=s.timestamp,
                        value=s.value,
                        unit=s.unit,
                    )
                )
                count += 1
        await db.flush()
    return count


async def run_all_syncs() -> None:
    """Sync every active cloud account across all organizations."""
    async with AsyncSessionLocal() as db:
        accounts = (
            (await db.execute(
                select(CloudAccount).where(
                    CloudAccount.status != CloudAccountStatus.PAUSED
                )
            )).scalars().all()
        )
        for account in accounts:
            try:
                await sync_account(db, account)
                await db.commit()
            except Exception as exc:
                await db.rollback()
                logger.exception("Sync failed for account {}", account.id)
                account.status = CloudAccountStatus.ERROR
                account.error_message = str(exc)[:500]
                await db.commit()


async def sync_account_by_id(account_id: uuid.UUID) -> dict[str, int]:
    """Sync a single account by id (used right after connection)."""
    async with AsyncSessionLocal() as db:
        account = await db.get(CloudAccount, account_id)
        if account is None:
            return {}
        result = await sync_account(db, account)
        await db.commit()
        return result

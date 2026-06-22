"""Audit logging — append-only, tamper-evident hash chain.

Each audit row's ``signature`` is ``SHA-256(prev_signature + canonical_row_json)``.
The first row in an organization's chain uses a genesis previous-signature of 64
zeros. Any retroactive modification of a row breaks every subsequent signature,
making tampering detectable.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from cloudpilot.models.audit_log import AuditLog

GENESIS_SIGNATURE = "0" * 64


def compute_signature(prev_sig: str, row_data: dict[str, Any]) -> str:
    """Compute the chained SHA-256 signature for an audit row."""
    payload = prev_sig + json.dumps(row_data, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _latest_signature(db: AsyncSession, organization_id: uuid.UUID) -> str:
    """Return the signature of the most recent audit row for an org (or genesis)."""
    result = await db.execute(
        select(AuditLog.signature)
        .where(AuditLog.organization_id == organization_id)
        .order_by(desc(AuditLog.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none() or GENESIS_SIGNATURE


async def write_audit(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    event_type: str,
    actor_user_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    payload: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    """Append a signed, immutable audit event and flush it within the caller's tx."""
    payload = payload or {}
    prev_sig = await _latest_signature(db, organization_id)
    row_data = {
        "organization_id": str(organization_id),
        "actor_user_id": str(actor_user_id) if actor_user_id else None,
        "event_type": event_type,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "payload": payload,
    }
    signature = compute_signature(prev_sig, row_data)
    entry = AuditLog(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        payload_json=payload,
        ip_address=ip_address,
        user_agent=user_agent,
        signature=signature,
    )
    db.add(entry)
    await db.flush()
    return entry


async def verify_chain(db: AsyncSession, organization_id: uuid.UUID) -> bool:
    """Recompute the full hash chain for an org and confirm integrity."""
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.organization_id == organization_id)
        .order_by(AuditLog.created_at)
    )
    prev_sig = GENESIS_SIGNATURE
    for row in result.scalars().all():
        row_data = {
            "organization_id": str(row.organization_id),
            "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
            "event_type": row.event_type,
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "payload": row.payload_json,
        }
        if compute_signature(prev_sig, row_data) != row.signature:
            return False
        prev_sig = row.signature
    return True

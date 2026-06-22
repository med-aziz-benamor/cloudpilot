"""Audit log model — append-only, tamper-evident event log.

Rows are never updated or deleted. Each row carries a SHA-256 ``signature`` that
chains to the previous row (see ``core/audit.py``), making any retroactive
modification detectable.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CHAR, Index, String, Text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from cloudpilot.database import BaseModel


class AuditLog(BaseModel):
    """An immutable audit event. ``organization_id`` is intentionally not a FK so
    the audit trail survives organization deletion."""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_org_event_created", "organization_id", "event_type", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    signature: Mapped[str] = mapped_column(CHAR(64), nullable=False)
